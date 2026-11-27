"""104: the scheduler, calling tick(tx, git, claude, base_url, now) directly (AC14–AC22)."""

import os
import time
from types import SimpleNamespace

import pytest
from conftest import commit, sql
from controllers.test_automation_runs import AUTO_SKILL, NOT_COMMITTED, add_factory, auto, automation_running  # noqa: F401
from controllers.test_automation_runs import cap_409, row
from controllers.test_run_accounts import ByDir, snapshot
from controllers.test_runs import OLD, add_running_run, add_task, cap, fake, project, wait  # noqa: F401
from fastapi.testclient import TestClient

from workcell.adapters.claude import SubprocessClaude
from workcell.adapters.git import SubprocessGit
from workcell.dto.schedules import SchedulePatch
from workcell.handlers import runs as runs_handler
from workcell.handlers import schedules as handler
from workcell.lib.cron import next_after
from workcell.repositories.schedules import SchedulesRepo
from workcell.server.app import create_app
from workcell.server.deps import transaction as tx

REAL_START_LOOP = handler.start_loop  # before conftest swaps it for a no-op (Q10)
BASE = "http://127.0.0.1:4545"
GIT = SubprocessGit()


def add_schedule(factory_id, cron="0 9 * * *", due=True, enabled=1, account_id=None, now=None) -> int:
    now = time.time() if now is None else now
    at = handler.iso(now - 60 if due else now + 3600) if enabled else None
    return sql("INSERT INTO schedules (factory_id, cron, enabled, account_id, next_run_at, created_at, updated_at)"
               " VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id", (factory_id, cron, enabled, account_id, at, OLD, OLD))[0][0]


def schedule(schedule_id) -> dict:
    cols = ("cron", "enabled", "account_id", "next_run_at", "last_run_id", "last_skip", "last_skip_at", "updated_at")
    return dict(zip(cols, sql(f"SELECT {', '.join(cols)} FROM schedules WHERE id = ?", (schedule_id,))[0]))


def run_ids() -> list[int]:
    return [i for (i,) in sql("SELECT id FROM runs ORDER BY id")]


def tick(claude=None, now=None):
    now = time.time() if now is None else now
    handler.tick(tx, GIT, claude or SubprocessClaude(), BASE, now)
    return now


def skipped(schedule_id, now, reason) -> dict:
    return {"last_skip": reason, "last_skip_at": handler.iso(now),
            "next_run_at": handler.iso(next_after(schedule(schedule_id)["cron"], now))}


# --- Starts -------------------------------------------------------------------------------------------------


def test_due_tick_starts(client, project, auto, fake):  # AC14
    sid = add_schedule(auto, "*/5 * * * *")
    sql("UPDATE schedules SET last_skip = 'old', last_skip_at = ? WHERE id = ?", (OLD, sid))
    now = tick()
    [run_id] = run_ids()
    wait(run_id)
    assert row(run_id) | {"status": None, "worktree_path": None} == {
        "task_id": None, "factory_id": auto, "kind": "automation", "trigger": "schedule", "status": None,
        "account_id": 1, "worktree_path": None, "error": None}
    assert fake.recorded("run")["env"]["FCTL_URL"] == BASE
    s = schedule(sid)
    assert (s["last_run_id"], s["last_skip"], s["last_skip_at"]) == (run_id, None, None)
    assert s["next_run_at"] == handler.iso(next_after("*/5 * * * *", now))


def test_due_tick_uses_its_account(client, project, auto, fake, tmp_path):  # AC14
    two = str(tmp_path / "account-2")
    account = sql("INSERT INTO claude_accounts (config_dir, active, email, created_at) VALUES (?, 0, 'b@y', ?)"
                  " RETURNING id", (two, OLD))[0][0]
    add_schedule(auto, account_id=account)
    tick(ByDir({os.environ["CLAUDE_CONFIG_DIR"], two}))
    [run_id] = run_ids()
    wait(run_id)
    assert (row(run_id)["account_id"], row(run_id)["trigger"]) == (account, "schedule")
    assert fake.recorded("run")["env"]["CLAUDE_CONFIG_DIR"] == two


def test_not_due_or_paused(client, project, auto, fake):  # AC15
    later = add_schedule(auto, due=False)
    paused = add_schedule(add_factory(project, "Paused"), enabled=0)
    before = [schedule(later), schedule(paused)]
    for minutes in range(3):
        tick(now=time.time() + minutes * 60)
    assert run_ids() == [] and not fake.invoked()
    assert [schedule(later), schedule(paused)] == before


# --- Skips --------------------------------------------------------------------------------------------------


def test_skip_while_running(client, project, auto, fake):  # AC16: a manual run counts
    sid = add_schedule(auto)
    earlier = automation_running(auto)
    sql("UPDATE runs SET status = 'succeeded' WHERE id = ?", (earlier,))
    sql("UPDATE schedules SET last_run_id = ? WHERE id = ?", (earlier, sid))
    running = automation_running(auto)
    now = tick()
    assert run_ids() == [earlier, running] and not fake.invoked()
    s = schedule(sid)
    assert {k: s[k] for k in ("last_skip", "last_skip_at", "next_run_at")} == skipped(
        sid, now, f"run #{running} of Security audit is still running")
    assert s["last_run_id"] == earlier


def test_skip_at_cap(client, project, auto, fake):  # AC17
    sid = add_schedule(auto)
    task = add_task(project, status="in_progress")
    on_task = add_running_run(task)
    cap(1)
    now = tick()
    assert run_ids() == [on_task] and not fake.invoked()
    s = schedule(sid)
    assert {k: s[k] for k in ("last_skip", "last_skip_at", "next_run_at")} == skipped(
        sid, now, cap_409(f"#{on_task} on #{task}", limit=1)["detail"])
    assert s["last_run_id"] is None


class SpawnFails(SubprocessClaude):
    def spawn(self, *args):
        raise OSError("no such file")


@pytest.mark.parametrize("case", ["auth", "low", "logged out", "uncommitted", "wt", "spawn"])
def test_skip_when_refused(client, project, repo, fake, monkeypatch, tmp_path, case):  # AC18, Q9
    if case != "uncommitted":
        commit(repo, {AUTO_SKILL: "# security-audit\n"})
    factory = add_factory(project)
    claude, account, detail = None, None, None
    if case == "auth":
        fake(auth='{"authMethod":"console"}')
        detail = "not on subscription auth"
    elif case == "low":
        snapshot(1, five=0.95)
    elif case == "logged out":
        account = sql("INSERT INTO claude_accounts (config_dir, active, email, created_at) VALUES (?, 0, 'b@y', ?)"
                      " RETURNING id", (str(tmp_path / "account-2"), OLD))[0][0]
        claude = ByDir({os.environ["CLAUDE_CONFIG_DIR"]})
        detail = ("Claude account b@y isn't logged in to claude.ai; log it in under Settings → Claude accounts,"
                  " or pick another")
    elif case == "uncommitted":
        detail = NOT_COMMITTED
    elif case == "wt":
        monkeypatch.setenv("FAKE_WT_FAIL", "switch")
        detail = "wt switch failed: wt: switch broke"
    else:
        claude = SpawnFails()
        detail = "can't start claude: no such file"
    sid = add_schedule(factory, account_id=account)
    runs_before = run_ids()
    now = tick(claude)
    s = schedule(sid)
    if case == "low":
        assert s["last_skip"].startswith("all accounts near their limits: claude-config 5h 95%")
        detail = s["last_skip"]
    assert {k: s[k] for k in ("last_skip", "last_skip_at", "next_run_at")} == skipped(sid, now, detail)
    assert s["last_run_id"] is None
    if case == "spawn":  # Q9: the failed row stays, and the schedule doesn't point at it
        [failed] = [r for r in run_ids() if r not in runs_before]
        assert (row(failed)["status"], row(failed)["trigger"]) == ("failed", "schedule")
    else:
        assert run_ids() == runs_before


# --- Races --------------------------------------------------------------------------------------------------


def test_no_double_start(client, project, auto, fake, monkeypatch):  # AC19, Q8
    sid = add_schedule(auto)
    real, starts = runs_handler.start_automation, []

    def overlapping(*args, **kwargs):
        starts.append(args[3])
        tick()  # a second tick while the first is starting: the time is already claimed
        return real(*args, **kwargs)

    monkeypatch.setattr(runs_handler, "start_automation", overlapping)
    tick()
    assert starts == [auto]
    [run_id] = run_ids()
    wait(run_id)
    assert schedule(sid)["last_run_id"] == run_id
    now = time.time()
    sql("UPDATE schedules SET next_run_at = ? WHERE id = ?", (handler.iso(now - 60), sid))
    with tx() as conn:  # the claim itself: once only
        repo = SchedulesRepo(conn)
        assert repo.claim(sid, "0 9 * * *", handler.iso(now), handler.iso(now + 3600)) is not None
        assert repo.claim(sid, "0 9 * * *", handler.iso(now), handler.iso(now + 3600)) is None


@pytest.mark.parametrize("body", [{"enabled": False}, {"cron": "30 7 * * 2"}])
def test_patch_during_start_kept(client, project, auto, monkeypatch, body):  # AC20
    sid = add_schedule(auto)
    sql("UPDATE schedules SET last_skip = 'old', last_skip_at = ? WHERE id = ?", (OLD, sid))

    def start(*args, **kwargs):
        handler.update(tx, sid, SchedulePatch(**body))
        return SimpleNamespace(run_id=automation_running(auto))

    monkeypatch.setattr(runs_handler, "start_automation", start)
    tick()
    patched = schedule(sid)
    [run_id] = run_ids()
    assert (patched["last_run_id"], patched["last_skip"], patched["last_skip_at"]) == (run_id, None, None)
    if "enabled" in body:  # what the PATCH wrote is what's there
        assert (patched["enabled"], patched["next_run_at"]) == (0, None)
    else:
        assert patched["cron"] == "30 7 * * 2" and patched["enabled"] == 1
        assert handler.iso(next_after("30 7 * * 2", time.time() - 5)) == patched["next_run_at"]


# --- Startup and the loop -----------------------------------------------------------------------------------


def test_missed_times_not_caught_up(client, project, auto, fake):  # AC21
    missed = add_schedule(auto, "0 * * * *", now=time.time() - 3600)
    later = add_schedule(add_factory(project, "Later"), due=False)
    paused = add_schedule(add_factory(project, "Paused"), enabled=0)
    before = [schedule(later), schedule(paused)]
    started = time.time()
    with TestClient(create_app(), base_url=BASE):
        pass
    s = schedule(missed)
    assert s["next_run_at"] in {handler.iso(next_after("0 * * * *", t)) for t in (started, time.time())}
    assert s["next_run_at"] > handler.iso(time.time())
    assert (s["last_skip"], s["last_skip_at"], s["last_run_id"]) == (None, None, None)
    assert [schedule(later), schedule(paused)] == before
    assert run_ids() == [] and not fake.invoked()


def test_lifespan_order(monkeypatch):  # AC21, AC22, Q4
    seen = []
    monkeypatch.setattr(runs_handler, "fail_leftovers", lambda tx: seen.append("fail_leftovers"))
    monkeypatch.setattr(runs_handler, "stop_all", lambda tx, claude: seen.append("stop_all"))
    monkeypatch.setattr(handler, "skip_missed", lambda tx: seen.append("skip_missed"))
    monkeypatch.setattr(handler, "start_loop", lambda tx, git, claude, url: seen.append(("start_loop", url)) or "h")
    monkeypatch.setattr(handler, "stop_loop", lambda h: seen.append(("stop_loop", h)))
    with TestClient(create_app(port=5000), base_url=BASE):
        assert seen == ["fail_leftovers", "skip_missed", ("start_loop", "http://127.0.0.1:5000")]
    assert seen[3:] == [("stop_loop", "h"), "stop_all"]


def test_loop_ticks_and_survives(monkeypatch):  # AC22, Q10
    calls = []

    def flaky(tx, git, claude, base_url):
        calls.append(base_url)
        if len(calls) == 1:
            raise RuntimeError("the DB is gone")

    monkeypatch.setattr(handler, "tick", flaky)
    handle = REAL_START_LOOP(tx, GIT, SubprocessClaude(), BASE, interval=0.05)
    stop, thread = handle
    assert thread.daemon and thread.name == "scheduler"
    deadline = time.monotonic() + 5
    while len(calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    handler.stop_loop(handle)
    assert len(calls) >= 3 and set(calls) == {BASE}  # the first tick's exception didn't end the loop
    assert not thread.is_alive()
    handler.stop_loop(None)  # the tests' no-op start_loop has nothing to stop


def test_one_schedule_failing_spares_the_others(client, project, auto, fake, monkeypatch):  # AC22
    broken = add_schedule(add_factory(project, "Broken"), "*/5 * * * *")
    fine = add_schedule(auto)
    real = runs_handler.start_automation

    def start(tx, git, claude, factory_id, *args, **kwargs):
        if factory_id != auto:
            raise RuntimeError("boom")
        return real(tx, git, claude, factory_id, *args, **kwargs)

    monkeypatch.setattr(runs_handler, "start_automation", start)
    now = tick()
    [run_id] = run_ids()
    wait(run_id)
    assert schedule(fine)["last_run_id"] == run_id
    assert {k: schedule(broken)[k] for k in ("last_skip", "last_skip_at", "next_run_at")} == skipped(
        broken, now, "can't start: boom")
