"""095: recording a run's rate-limit snapshot (AC6–AC8), account labels (AC12), and GET /api/usage's data
(AC13–AC18), against a real database."""

import json
from datetime import date
from types import SimpleNamespace

import pytest
from conftest import sql

from workcell import db
from workcell.domain.errors import Invalid
from workcell.handlers import runs
from workcell.handlers.usage import accounts_usage, label, stats, usage
from workcell.repositories.claude_accounts import ClaudeAccountsRepo
from workcell.repositories.usage import UsageRepo
from workcell.server.deps import transaction

OLD = "2026-01-01T00:00:00Z"
TODAY = date(2026, 11, 13)


def event(five=0.34, status="allowed") -> str:
    return json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": status, "isUsingOverage": False, "unifiedWindows": {
            "five_hour": {"utilization": five, "resetsAt": 4_000_000_000, "status": status},
            "seven_day": {"utilization": 0.12, "resetsAt": 4_000_000_000, "status": "allowed"}}}})


def project() -> int:
    db.init()
    ws = sql("INSERT INTO workspaces (name, created_at) VALUES ('w', ?) RETURNING id", (OLD,))[0][0]
    return sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
               " VALUES (?, 'p', '/p', 'main', ?) RETURNING id", (ws, OLD))[0][0]


def add_task(project_id, title="t") -> int:
    return sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
               " VALUES (?, ?, 'in_progress', 1, ?, ?) RETURNING id", (project_id, title, OLD, OLD))[0][0]


def add_account(config_dir, email=None) -> int:
    return sql("INSERT INTO claude_accounts (config_dir, email, created_at) VALUES (?, ?, ?) RETURNING id",
               (config_dir, email, OLD))[0][0]


def add_run(task_id, account_id=None, status="running", log_path="l", started_at=OLD) -> int:
    return sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at, account_id)"
               " VALUES (?, 's', ?, ?, ?, ?) RETURNING id", (task_id, status, log_path, started_at, account_id))[0][0]


def snapshots() -> list[tuple]:
    return sql("SELECT run_id, account_id, five_hour_utilization, limited FROM usage_snapshots ORDER BY run_id")


def finish(run_id, log):
    runs.finish(transaction, run_id, SimpleNamespace(wait=lambda: 0), log)


@pytest.fixture
def task():
    return add_task(project())


# --- Recording (AC6–AC8) ---------------------------------------------------------------


def test_finish_records_on_runs_account(tmp_path, task):  # AC6
    one, two = add_account("/a/one"), add_account("/a/two")
    run_id = add_run(task, account_id=one)
    sql("UPDATE claude_accounts SET active = (id = ?)", (two,))  # another account made active since
    log = tmp_path / "run.jsonl"
    log.write_text(f"{event(0.2, 'rejected')}\n{event(0.5)}\n")
    finish(run_id, log)
    assert snapshots() == [(run_id, one, 0.5, 1)]
    [(recorded,)] = sql("SELECT recorded_at FROM usage_snapshots")
    assert recorded[:4] == db.now()[:4] and recorded.endswith("Z")
    finish(run_id, log)  # a second finish upserts the same row
    assert len(snapshots()) == 1


@pytest.mark.parametrize("final", ["failed", "stopped"])
def test_finish_records_failed_and_stopped(tmp_path, task, final):  # AC6
    account = add_account("/a/one")
    run_id = add_run(task, account_id=account, status="stopped" if final == "stopped" else "running")
    log = tmp_path / "run.jsonl"
    log.write_text(f"{event()}\n")
    runs.finish(transaction, run_id, SimpleNamespace(wait=lambda: 1), log)
    assert snapshots() == [(run_id, account, 0.34, 0)]


def test_finish_without_event_or_account(tmp_path, task):  # AC7
    account = add_account("/a/one")
    empty, no_account = add_run(task, account_id=account), add_run(task, status="succeeded")
    (tmp_path / "empty.jsonl").write_text('{"type":"result","subtype":"success"}\n{bad\n')
    (tmp_path / "full.jsonl").write_text(f"{event()}\n")
    finish(empty, tmp_path / "empty.jsonl")
    finish(no_account, tmp_path / "full.jsonl")
    assert snapshots() == []
    assert sql("SELECT status FROM runs WHERE id = ?", (empty,)) == [("succeeded",)]


def test_fail_leftovers_records(tmp_path, task):  # AC8
    account = add_account("/a/one")
    log = tmp_path / "run.jsonl"
    log.write_text(f"{event(0.9)}\n")
    run_id = add_run(task, account_id=account, log_path=str(log))
    runs.fail_leftovers(transaction)
    assert sql("SELECT status FROM runs WHERE id = ?", (run_id,)) == [("failed",)]
    assert snapshots() == [(run_id, account, 0.9, 0)]


# --- Labels and accounts (AC12, AC13) --------------------------------------------------


def test_label():  # AC12
    assert label("me@example.com", "/home/x/.claude-work") == "me@example.com"
    assert label(None, "/home/x/.claude-work") == ".claude-work"
    assert label(None, None) == "unknown"


def test_accounts_usage(task):  # AC13
    [(first,)] = sql("SELECT id FROM claude_accounts")
    second = add_account("/a/two", "two@example.com")
    run_id = add_run(task, account_id=second, status="succeeded")
    snap = {"five_hour": {"utilization": 0.85, "resets_at": 2000, "status": "allowed"},
            "seven_day": {"utilization": 0.4, "resets_at": 500, "status": "rejected"},
            "status": "allowed", "overage": True, "limited": True}
    with transaction() as conn:
        UsageRepo(conn).record(run_id, snap)
        found = accounts_usage(ClaudeAccountsRepo(conn), UsageRepo(conn), now=1000)
    [(recorded,)] = sql("SELECT recorded_at FROM usage_snapshots")
    assert found == [
        {"id": first, "label": "claude-config", "active": True, "recorded_at": None, "run_id": None,
         "overage": None, "five_hour": None, "seven_day": None},
        {"id": second, "label": "two@example.com", "active": False, "recorded_at": recorded, "run_id": run_id,
         "overage": True,
         "five_hour": {"utilization": 0.85, "resets_at": 2000, "state": "near_limit", "reset": False},
         "seven_day": {"utilization": 0, "resets_at": 500, "state": "allowed", "reset": True}},
    ]


# --- Stats (AC14–AC18) -------------------------------------------------------------------


def transcript(run_id, task_id, path, tokens, model=None, agent=None, started_at=None):
    sql("INSERT INTO transcripts (run_id, task_id, agent_type, path, model, turns, input_tokens, cache_read_tokens,"
        " output_tokens, started_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
        (run_id, task_id, agent, path, model, *tokens, started_at))


def read(days=7) -> dict:
    with transaction() as conn:
        return stats(UsageRepo(conn), days, today=TODAY)


@pytest.fixture
def fixture(task):
    """Two accounts, one later deleted; runs on 11-12 and 11-13 and one from before the window."""
    p = sql("SELECT project_id FROM tasks WHERE id = ?", (task,))[0][0]
    other = add_task(p, "big")
    one, gone = add_account("/a/one", "one@example.com"), add_account("/a/gone")
    r1 = add_run(task, one, "succeeded", started_at="2026-11-12T10:00:00Z")
    r2 = add_run(other, gone, "succeeded", started_at="2026-11-13T09:00:00Z")
    r3 = add_run(task, None, "succeeded", started_at="2026-11-13T23:59:59Z")  # no transcripts
    old = add_run(task, one, "succeeded", started_at="2026-10-01T00:00:00Z")
    transcript(r1, task, "a", (10, 100, 1), "opus", "orchestrator")  # its own start is NULL → the run's
    transcript(r1, task, "b", (20, 200, 2), "sonnet", "builder", "2026-11-12T11:00:00Z")
    transcript(r2, other, "c", (1000, 0, 5), None, None, "2026-11-13T00:00:00Z")
    transcript(r2, other, "d", (1, 1, 1), "opus", "builder", "2026-11-11T23:00:00Z")  # its own day, not the run's
    transcript(old, task, "e", (9999, 9999, 9999), "opus", "builder", "2026-10-01T00:00:00Z")
    sql("DELETE FROM claude_accounts WHERE id = ?", (gone,))
    return SimpleNamespace(task=task, other=other, project=p)


def test_by_day(fixture):  # AC15, Q8
    found = read()
    assert found["days"] == 7
    assert [d["day"] for d in found["by_day"]] == [f"2026-11-{n:02}" for n in range(7, 14)]
    by = {d["day"]: d for d in found["by_day"]}
    assert by["2026-11-07"] == {"day": "2026-11-07", "input_tokens": 0, "cache_read_tokens": 0,
                                "output_tokens": 0, "runs": 0}
    assert by["2026-11-11"] == {"day": "2026-11-11", "input_tokens": 1, "cache_read_tokens": 1,
                                "output_tokens": 1, "runs": 0}
    assert by["2026-11-12"] == {"day": "2026-11-12", "input_tokens": 30, "cache_read_tokens": 300,
                                "output_tokens": 3, "runs": 1}
    assert by["2026-11-13"] == {"day": "2026-11-13", "input_tokens": 1000, "cache_read_tokens": 0,
                                "output_tokens": 5, "runs": 2}
    assert len(read(30)["by_day"]) == 30 and read(30)["by_day"][0]["day"] == "2026-10-15"


def test_by_account_model_agent(fixture):  # AC16
    found = read()
    assert found["by_account"] == [
        {"key": "unknown", "input_tokens": 1001, "cache_read_tokens": 1, "output_tokens": 6, "runs": 2},
        {"key": "one@example.com", "input_tokens": 30, "cache_read_tokens": 300, "output_tokens": 3, "runs": 1},
    ]
    assert found["by_model"] == [
        {"key": "unknown", "input_tokens": 1000, "cache_read_tokens": 0, "output_tokens": 5, "runs": 1},
        {"key": "sonnet", "input_tokens": 20, "cache_read_tokens": 200, "output_tokens": 2, "runs": 1},
        {"key": "opus", "input_tokens": 11, "cache_read_tokens": 101, "output_tokens": 2, "runs": 2},
    ]
    assert found["by_agent"] == [
        {"key": "agent", "input_tokens": 1000, "cache_read_tokens": 0, "output_tokens": 5, "runs": 1},
        {"key": "builder", "input_tokens": 21, "cache_read_tokens": 201, "output_tokens": 3, "runs": 2},
        {"key": "orchestrator", "input_tokens": 10, "cache_read_tokens": 100, "output_tokens": 1, "runs": 1},
    ]


def test_top_tasks(fixture):  # AC17
    assert read()["top_tasks"] == [
        {"task_id": fixture.other, "title": "big", "project_id": fixture.project, "input_tokens": 1001,
         "cache_read_tokens": 1, "output_tokens": 6},
        {"task_id": fixture.task, "title": "t", "project_id": fixture.project, "input_tokens": 30,
         "cache_read_tokens": 300, "output_tokens": 3},
    ]
    p = fixture.project
    for n in range(12):
        t = add_task(p, f"n{n}")
        transcript(add_run(t, status="succeeded"), t, f"x{n}", (n + 1, 0, 0), started_at="2026-11-13T01:00:00Z")
    top = read()["top_tasks"]
    assert len(top) == 10 and top[0]["task_id"] == fixture.other


def test_empty_stats(task):  # AC30's data: no transcripts
    found = read()
    assert [found[k] for k in ("by_account", "by_model", "by_agent", "top_tasks")] == [[], [], [], []]
    assert all(d["input_tokens"] == d["runs"] == 0 for d in found["by_day"])


def test_days_validated(task):  # AC14
    with transaction() as conn:
        for days in (0, 1, 14, 31):
            with pytest.raises(Invalid):
                usage(ClaudeAccountsRepo(conn), UsageRepo(conn), days)
        assert usage(ClaudeAccountsRepo(conn), UsageRepo(conn), 30)["stats"]["days"] == 30


def test_limited_runs(task):  # AC18, Q6
    account = add_account("/a/one", "one@example.com")
    snap = {"five_hour": {"utilization": 1.0, "resets_at": 1, "status": "rejected"},
            "seven_day": {"utilization": 0.1, "resets_at": 1, "status": "allowed"},
            "status": "rejected", "overage": False}
    made = []
    for n in range(23):
        run_id = add_run(task, account, "failed")
        sql("UPDATE runs SET ended_at = ? WHERE id = ?", (f"2026-11-{n + 1:02}T00:00:00Z", run_id))
        with transaction() as conn:
            UsageRepo(conn).record(run_id, snap | {"limited": n != 22})  # the newest one wasn't limited
        made.append(run_id)
    with transaction() as conn:
        found = usage(ClaudeAccountsRepo(conn), UsageRepo(conn), 7)["limited_runs"]
    assert [r["run_id"] for r in found] == made[21:1:-1]
    assert found[0] == {"run_id": made[21], "task_id": task, "title": "t", "label": "one@example.com",
                        "ended_at": "2026-11-22T00:00:00Z"}
