import os
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest
from conftest import commit, sql, wt_calls
from fastapi.testclient import TestClient
from controllers.test_pages_api import add_round
from controllers.test_runs import (H, LEGACY, LEGACY_HINT, OLD, SKILL, add_running_run, add_task,  # noqa: F401
                                   cap, cap_detail, events, fake, project, run, run_row, started, task_row, wait)

from claude_factories.adapters.claude import SubprocessClaude
from claude_factories.adapters.git import SubprocessGit
from claude_factories.handlers import runs as runs_handler
from claude_factories.server.app import create_app
from claude_factories.server.deps import transaction

BASE = "http://127.0.0.1:4545"
NOTE = "Make the limit configurable via settings."


def until(check, seconds=5):
    """check()'s first truthy value within `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if found := check():
            return found
        time.sleep(0.05)
    raise AssertionError(f"timed out after {seconds} s")


def gone(pid) -> bool:
    """os.kill(pid, 0) raises ProcessLookupError within a 5 s deadline (Setup)."""
    def check():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False
    try:
        return until(check)
    except AssertionError:
        return False


def stop(c, run_id, headers=H):
    return c.post(f"/api/runs/{run_id}/stop", headers=headers)


def reaped(run_id):
    """The run row once its exit thread has recorded exit_code."""
    return until(lambda: (row := run_row(run_id))["exit_code"] is not None and row, 10)


@pytest.fixture
def long(client, project, fake):
    """long(c=client, task=None) starts the long-running fake on an in_progress · build task and returns
    once its child is up. At teardown every run it started is stopped and reaped, so no late exit
    lands in the next test's database."""
    fake(long=True)
    started_ids = []

    def start(c=client, task=None):
        fake.clear()
        task = task or add_task(project, status="in_progress", stage="build")
        r = run(c, task)
        assert r.status_code == 202, r.text
        started_ids.append(r.json()["run_id"])
        child = until(lambda: fake.recorded("child"))
        return SimpleNamespace(task=task, run_id=r.json()["run_id"], body=r.json(),
                               pid=fake.recorded("run")["pid"], child=child)

    yield start
    for run_id in started_ids:
        if run_row(run_id)["status"] == "running":
            stop(client, run_id)
        reaped(run_id)


@pytest.fixture
def stopped(client, long):
    """AC1's stop: the started run, the task and events before the stop, the response, and the row
    as it was when the response arrived."""
    s = long()
    s.task_before, s.events_before = task_row(s.task), events(s.task)
    s.response = stop(client, s.run_id)
    s.row = run_row(s.run_id)
    return s


@pytest.fixture
def sleeper():
    """A live `sleep 60` in its own session, killed at teardown."""
    proc = subprocess.Popen(["sleep", "60"], start_new_session=True)
    yield proc
    proc.kill()
    proc.wait()


# --- Stop ---------------------------------------------------------------------


def test_stop(stopped):  # AC1
    assert (stopped.response.status_code, stopped.response.json()) == (200, {"id": stopped.run_id, "status": "stopped"})
    assert stopped.row["status"] == "stopped"
    assert stopped.row["ended_at"] and stopped.row["error"] is None


def test_stop_signals_group(stopped):  # AC2
    assert gone(stopped.pid)
    assert gone(stopped.child)


def test_stop_then_exit(stopped):  # AC3
    row = reaped(stopped.run_id)
    assert (row["status"], row["error"], row["ended_at"]) == ("stopped", None, stopped.row["ended_at"])
    assert row["exit_code"] is not None


def test_stop_leaves_task(stopped):  # AC4
    reaped(stopped.run_id)
    assert task_row(stopped.task) == stopped.task_before
    assert events(stopped.task) == stopped.events_before


@pytest.mark.parametrize("status", ["succeeded", "failed", "stopped"])
def test_stop_not_running(client, project, sleeper, status):  # AC5
    task = add_task(project, status="in_progress")
    run_id = sql(
        "INSERT INTO runs (task_id, session_id, pid, status, exit_code, log_path, started_at, ended_at)"
        " VALUES (?, 's', ?, ?, 0, 'l', ?, ?) RETURNING id", (task, sleeper.pid, status, OLD, OLD),
    )[0][0]
    before = run_row(run_id)
    r = stop(client, run_id)
    assert (r.status_code, r.json()) == (409, {"detail": f"run #{run_id} is not running"})
    assert run_row(run_id) == before
    assert sleeper.poll() is None
    r = stop(client, 999)
    assert (r.status_code, r.json()) == (404, {"detail": "run #999 not found"})


def test_stop_needs_header(client, long):  # AC6
    s = long()
    assert stop(client, s.run_id, headers={}).status_code == 403
    assert run_row(s.run_id)["status"] == "running"
    os.kill(s.pid, 0)  # still there


def test_stop_without_live_pid(client, project):  # AC7
    task = add_task(project, status="in_progress")
    no_pid = add_running_run(task)
    r = stop(client, no_pid)
    assert (r.status_code, r.json()) == (200, {"id": no_pid, "status": "stopped"})
    exited = subprocess.Popen(["true"], start_new_session=True)
    exited.wait()
    dead = add_running_run(task)
    sql("UPDATE runs SET pid = ? WHERE id = ?", (exited.pid, dead))
    r = stop(client, dead)
    assert (r.status_code, r.json()) == (200, {"id": dead, "status": "stopped"})
    assert [run_row(i)["status"] for i in (no_pid, dead)] == ["stopped", "stopped"]


# --- Stopping fctl serve, and startup -------------------------------------------


def test_shutdown_stops_runs(long):  # AC8
    with TestClient(create_app(), base_url=BASE) as c:
        s = long(c)
    row = run_row(s.run_id)
    assert row["status"] == "stopped" and row["ended_at"]
    assert gone(s.pid) and gone(s.child)


def test_startup_fails_leftover_runs(client, project, sleeper):  # AC9
    task = add_task(project, status="in_progress", stage="build")
    a = add_running_run(task)
    sql("UPDATE runs SET pid = ? WHERE id = ?", (sleeper.pid, a))
    b = sql("INSERT INTO runs (task_id, session_id, status, exit_code, log_path, started_at, ended_at)"
            " VALUES (?, 's2', 'succeeded', 0, 'l', ?, ?) RETURNING id", (task, OLD, OLD))[0][0]
    before = run_row(b), sql("SELECT * FROM tasks"), sql("SELECT * FROM events")
    with TestClient(create_app(), base_url=BASE):
        row = run_row(a)
        assert (row["status"], row["error"], row["exit_code"]) == ("failed", "app restarted", None)
        assert row["ended_at"]
        assert (run_row(b), sql("SELECT * FROM tasks"), sql("SELECT * FROM events")) == before
    assert sleeper.poll() is None


# --- Retry --------------------------------------------------------------------


def test_retry_after_stop(client, stopped, fake):  # AC10
    fake()
    r = run(client, stopped.task)
    assert r.status_code == 202, r.text
    body = r.json()
    wait(body["run_id"])
    assert body["worktree"] == stopped.body["worktree"]
    assert sql("SELECT COUNT(*) FROM runs WHERE task_id = ?", (stopped.task,)) == [(2,)]
    assert body["session_id"] != stopped.row["session_id"]
    seen = fake.recorded("run")
    assert seen["argv"][:2] == ["-p", f"/factory {stopped.task}"]
    assert seen["cwd"] == os.path.realpath(task_row(stopped.task)["worktree_path"])
    assert (task_row(stopped.task)["status"], task_row(stopped.task)["stage"]) == ("in_progress", "build")
    assert events(stopped.task) == stopped.events_before


def test_retry_after_restart(client, project):  # AC11
    task = add_task(project)
    first = started(client, task)
    sql("UPDATE tasks SET stage = 'approval' WHERE id = ?", (task,))
    leftover = add_running_run(task)
    with TestClient(create_app(), base_url=BASE):
        pass
    assert run_row(leftover)["status"] == "failed"
    r = run(client, task)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    assert r.json()["worktree"] == first["worktree"]
    assert (task_row(task)["status"], task_row(task)["stage"]) == ("in_progress", "approval")


# --- Run log ------------------------------------------------------------------

FIXTURE_LOG = r"""{"type":"system","subtype":"init","session_id":"S"}
{"type":"assistant","message":{"content":[{"type":"text","text":"Reading #12"}]},"parent_tool_use_id":null}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tu1","name":"Agent","input":{"subagent_type":"builder","name":"builder-12","description":"Build round 1","prompt":"go"}}]},"parent_tool_use_id":null}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tu2","name":"Bash","input":{"command":"pytest -q\necho done"}}]},"parent_tool_use_id":"tu1"}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"tu2","is_error":false,"content":"3 passed"}]},"parent_tool_use_id":"tu1"}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"tu3","is_error":true,"content":[{"type":"text","text":"Permission to use Bash with command git commit -m x has been denied.\nmore"}]}]},"parent_tool_use_id":"tu1"}
warn
{"type":"result","subtype":"success","is_error":false,"result":"#12 is in review","session_id":"S"}
"""
FIXTURE_ITEMS = [
    {"t": "text", "text": "orchestrator · Reading #12"},
    {"t": "tool", "text": "orchestrator · Agent builder-12"},
    {"t": "tool", "text": "builder-12 · Bash pytest -q"},
    {"t": "error", "text": "builder-12 · Permission to use Bash with command git commit -m x has been denied."},
    {"t": "raw", "text": "warn"},
    {"t": "result", "text": "#12 is in review"},
]


@pytest.fixture
def log(project, tmp_path):
    """(run id, its log_path), the file not yet written."""
    path = tmp_path / "run.jsonl"
    run_id = sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
                 " VALUES (?, 's', 'succeeded', ?, ?) RETURNING id",
                 (add_task(project, status="in_progress"), str(path), OLD))[0][0]
    return run_id, path


def get_log(client, run_id, query=""):
    r = client.get(f"/api/runs/{run_id}/log{query}")
    assert r.status_code == 200, r.text
    return r.json()


def test_log(client, log):  # AC12
    run_id, path = log
    path.write_text(FIXTURE_LOG)
    assert get_log(client, run_id) == {"next": 8, "lines": FIXTURE_ITEMS}


def test_log_after(client, log):  # AC13
    run_id, path = log
    path.write_text(FIXTURE_LOG)
    assert get_log(client, run_id, "?after=3") == {"next": 8, "lines": FIXTURE_ITEMS[-4:]}


def test_log_subagent_type(client, log):  # AC14
    run_id, path = log
    path.write_text(
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tu9","name":"Agent",'
        '"input":{"subagent_type":"review-code","description":"Review round 1"}}]},"parent_tool_use_id":null}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tu10","name":"Bash",'
        '"input":{"command":"fctl verdict 12 code PASS"}}]},"parent_tool_use_id":"tu9"}\n'
    )
    assert get_log(client, run_id)["lines"] == [
        {"t": "tool", "text": "orchestrator · Agent review-code"},
        {"t": "tool", "text": "review-code · Bash fctl verdict 12 code PASS"},
    ]


def test_log_partial_line(client, log):  # AC15
    run_id, path = log
    path.write_text("".join(FIXTURE_LOG.splitlines(keepends=True)[:2]) + '{"type":"assistant"')
    assert get_log(client, run_id) == {"next": 2, "lines": [FIXTURE_ITEMS[0]]}
    with path.open("a") as f:
        f.write(',"message":{"content":[{"type":"text","text":"Done"}]}}\n')
    assert get_log(client, run_id, "?after=2") == {"next": 3, "lines": [{"t": "text", "text": "orchestrator · Done"}]}


def test_log_odd_shapes(client, log):  # AC16
    run_id, path = log
    path.write_text('{"type":"assistant","message":null}\n{"type":"assistant","message":{"content":"plain"}}\n'
                    '{"type":"user","message":{"content":[null,3]}}\n\n[1,2]\n')
    assert get_log(client, run_id) == {"next": 5, "lines": [{"t": "raw", "text": "[1,2]"}]}


def test_log_missing_and_bad(client, log):  # AC17
    run_id, _ = log
    r = client.get(f"/api/runs/{run_id}/log")  # no X-Requested-By
    assert (r.status_code, r.json()) == (200, {"next": 0, "lines": []})
    r = client.get("/api/runs/999/log")
    assert (r.status_code, r.json()) == (404, {"detail": "run #999 not found"})
    assert client.get(f"/api/runs/{run_id}/log?after=-1").status_code == 422


# --- Request changes spawns the rework run ---------------------------------------


@pytest.fixture
def factory_task(client, project, fake):
    """Q11: branch and worktree from an earlier /run, the worktree on disk; now review · human_review
    with round 1. (task id, the earlier /run's body)."""
    task = add_task(project, "Rate-limit login endpoint")
    first = started(client, task)
    sql("UPDATE tasks SET status = 'review', stage = 'human_review' WHERE id = ?", (task,))
    add_round(task, 1)
    fake.clear()
    return task, first


def rework(client, task):
    return client.post(f"/api/tasks/{task}/request-changes", json={"body_md": NOTE}, headers=H)


def decisions(task):
    return sql("SELECT actor, decision FROM decisions WHERE task_id = ?", (task,))


def counts():
    """The decisions, events, and runs counts."""
    return sql("SELECT (SELECT COUNT(*) FROM decisions), (SELECT COUNT(*) FROM events), (SELECT COUNT(*) FROM runs)")[0]


def stage(task):
    row = task_row(task)
    return row["status"], row["stage"]


def test_rework_spawns_run(client, factory_task, fake):  # AC18
    task, first = factory_task
    before = events(task)
    r = rework(client, task)
    assert r.status_code == 202, r.text
    [(new,)] = sql("SELECT id FROM runs WHERE task_id = ? AND id != ?", (task, first["run_id"]))
    assert r.json() == {"status": "in_progress", "stage": "rework", "run_id": new}
    row = wait(new)
    seen = fake.recorded("run")
    assert seen["argv"][:2] == ["-p", f"/factory {task}"]
    assert seen["cwd"] == os.path.realpath(task_row(task)["worktree_path"])
    assert row["session_id"] != first["session_id"]
    assert stage(task) == ("in_progress", "rework")
    assert decisions(task) == [("me", "CHANGES_REQUESTED")]
    assert events(task) == before + [("me", "review", "in_progress", "rework", None)]


def test_rework_standalone(client, project, fake):  # AC19
    task = add_task(project, status="review", stage="human_review")
    add_round(task, 1)
    add_running_run(add_task(project, "other", status="in_progress"))
    r = rework(client, task)
    assert (r.status_code, r.json()) == (202, {"status": "in_progress", "stage": "rework", "run_id": None})
    assert sql("SELECT COUNT(*) FROM runs") == [(1,)]
    assert not fake.invoked()


def test_rework_while_running(client, project, factory_task, fake):  # AC20; 096 AC20: at the cap
    task, _ = factory_task
    other = add_task(project, "other", status="in_progress")
    running = add_running_run(other)
    cap(1)
    before = counts(), task_row(task)
    r = rework(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": cap_detail((running, other))})
    assert (counts(), task_row(task)) == before
    assert not fake.invoked()


def test_rework_under_cap(client, project, factory_task, fake):  # 096 AC18
    task, first = factory_task
    add_running_run(add_task(project, "other", status="in_progress"))
    r = rework(client, task)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    assert fake.recorded("run")["argv"][1] == f"/factory {task}"
    assert decisions(task) == [("me", "CHANGES_REQUESTED")]


def test_rework_own_run(client, project, factory_task, fake):  # 096 AC19, Q4
    task, _ = factory_task
    running = add_running_run(task)
    before = counts(), task_row(task)
    r = rework(client, task)
    assert (r.status_code, r.json()) == (
        409, {"detail": f"run #{running} is already running on #{task}; wait for it or stop it"})
    assert (counts(), task_row(task)) == before
    assert not fake.invoked()


def test_rework_spawn_refused(client, factory_task, fake):  # AC21
    task, _ = factory_task
    fake(auth='{"authMethod":"console"}')
    runs = counts()[2]
    r = rework(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})
    assert decisions(task) == [("me", "CHANGES_REQUESTED")]
    assert stage(task) == ("in_progress", "rework")
    assert counts()[2] == runs
    fake()
    r = run(client, task)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    assert stage(task) == ("in_progress", "rework")


def test_rework_legacy_factory(client, factory_task, repo, fake):  # 059 BE8
    task, _ = factory_task
    commit(repo, {SKILL: LEGACY})  # main now holds the file-based loop's SKILL.md
    runs = counts()[2]
    r = rework(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": LEGACY_HINT})
    assert decisions(task) == [("me", "CHANGES_REQUESTED")]
    assert stage(task) == ("in_progress", "rework")
    assert counts()[2] == runs and not fake.invoked()


def test_rework_fctl_url_ignores_host(client, factory_task, fake):  # 028 Q5: every spawn, not just /run
    task, first = factory_task
    client.post(f"/api/tasks/{task}/request-changes", json={"body_md": NOTE}, headers=H | {"Host": "127.0.0.1"})
    [(new,)] = sql("SELECT id FROM runs WHERE task_id = ? AND id != ?", (task, first["run_id"]))
    wait(new)
    assert fake.recorded("run")["env"]["FCTL_URL"] == BASE


# --- Round 2 review findings ------------------------------------------------------


def test_stop_skips_reaped_leader(client, project, sleeper):  # security review, round 1
    run_id = add_running_run(add_task(project, status="in_progress"))
    sql("UPDATE runs SET pid = ?, exit_code = 0 WHERE id = ?", (sleeper.pid, run_id))
    r = stop(client, run_id)
    assert (r.status_code, r.json()) == (200, {"id": run_id, "status": "stopped"})
    time.sleep(0.2)
    assert sleeper.poll() is None


# --- 096: concurrent runs with a cap ---------------------------------------------------


def alive(pid) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def two(project, long):
    """096: backlog tasks A and B, both started (cap 2, the default)."""
    a = long(task=add_task(project, "A"))
    b = long(task=add_task(project, "B"))
    return a, b


def test_two_runs_at_once(two, fake):  # 096 AC5
    a, b = two
    assert run_row(a.run_id)["status"] == run_row(b.run_id)["status"] == "running"
    assert a.pid != b.pid and alive(a.pid) and alive(b.pid)


def test_third_over_cap(client, project, two, fake):  # 096 AC6
    a, b = two
    c = add_task(project, "C")
    before, wt_before = counts()[2], len(wt_calls())
    fake.clear()
    r = run(client, c)
    assert (r.status_code, r.json()) == (409, {"detail": cap_detail((a.run_id, a.task), (b.run_id, b.task))})
    assert counts()[2] == before and len(wt_calls()) == wt_before
    assert not fake.invoked()


def test_cap_one_singular(client, project, long, fake):  # 096 AC7
    cap(1)
    a = long(task=add_task(project, "A"))
    r = run(client, add_task(project, "C"))
    assert (r.status_code, r.json()) == (409, {"detail": f"1 run active (#{a.run_id} on #{a.task}); the limit is 1."
                                                         " Wait, stop one, or raise it in Settings"})


def test_raise_cap_starts_third(client, project, two, long):  # 096 AC8
    r = client.put("/api/settings", json={"max_concurrent_runs": 3}, headers=H)
    assert r.status_code == 200, r.text
    c = long(task=add_task(project, "C"))
    assert run_row(c.run_id)["status"] == "running"


def test_same_task_twice(client, two, fake):  # 096 AC9, Q1: own run first, even with the cap full
    a, _ = two
    before = counts()[2]
    r = run(client, a.task)
    assert (r.status_code, r.json()) == (
        409, {"detail": f"run #{a.run_id} is already running on #{a.task}; wait for it or stop it"})
    assert counts()[2] == before


def test_stop_one_of_two(client, two):  # 096 AC10
    a, b = two
    assert stop(client, a.run_id).status_code == 200
    assert run_row(a.run_id)["status"] == "stopped"
    assert gone(a.pid)
    assert run_row(b.run_id)["status"] == "running"
    assert alive(b.pid) and alive(b.child)


def test_shutdown_stops_both(project, long):  # 096 AC14
    with TestClient(create_app(), base_url=BASE) as c:
        a = long(c, add_task(project, "A"))
        b = long(c, add_task(project, "B"))
    assert run_row(a.run_id)["status"] == run_row(b.run_id)["status"] == "stopped"
    assert all(gone(pid) for pid in (a.pid, a.child, b.pid, b.child))


def test_startup_fails_both_leftovers(client, project, monkeypatch):  # 096 AC15
    a = add_running_run(add_task(project, "A", status="in_progress"))
    b = add_running_run(add_task(project, "B", status="in_progress"))
    collected = []
    monkeypatch.setattr(runs_handler, "collect", lambda tx, run_id: collected.append(run_id))
    with TestClient(create_app(), base_url=BASE):
        rows = [run_row(a), run_row(b)]
    assert [(r["status"], r["error"]) for r in rows] == [("failed", "app restarted")] * 2
    assert sorted(collected) == [a, b]


def test_parallel_starts_take_turns(client, project, fake, monkeypatch):  # 096 AC13, Q7
    """Two starts at once on one repo: the exclude write, wt_create, and trust_project never overlap."""
    state = {"in": 0, "max": 0}
    lock = threading.Lock()

    def tracked(fn):
        def call(*args, **kwargs):
            with lock:
                state["in"] += 1
                state["max"] = max(state["max"], state["in"])
            time.sleep(0.2)
            try:
                return fn(*args, **kwargs)
            finally:
                with lock:
                    state["in"] -= 1
        return call

    class TrackedGit(SubprocessGit):
        wt_create = tracked(SubprocessGit.wt_create)

    monkeypatch.setattr(runs_handler, "exclude_worktrees", tracked(runs_handler.exclude_worktrees))
    monkeypatch.setattr(runs_handler, "trust_project", tracked(runs_handler.trust_project))
    tasks = [add_task(project, "A"), add_task(project, "B")]
    results = []

    def go(task):
        results.append(runs_handler.start(transaction, TrackedGit(), SubprocessClaude(), task, BASE).run_id)

    threads = [threading.Thread(target=go, args=(t,)) for t in tasks]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert len(results) == 2
    for run_id in results:
        wait(run_id)
    assert state["max"] == 1