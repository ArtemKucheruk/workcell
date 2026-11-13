"""095 AC9: UsageRepo.latest, an account's latest snapshot."""

from conftest import sql

from claude_factories import db
from claude_factories.repositories.usage import UsageRepo
from claude_factories.server.deps import transaction

OLD = "2026-01-01T00:00:00Z"
SNAP = {"five_hour": {"utilization": 0.1, "resets_at": 1, "status": "allowed"},
        "seven_day": {"utilization": 0.2, "resets_at": 2, "status": "allowed"},
        "status": "allowed", "overage": False, "limited": False}


def test_latest_per_account():  # AC9, Q7
    db.init()
    ws = sql("INSERT INTO workspaces (name, created_at) VALUES ('w', ?) RETURNING id", (OLD,))[0][0]
    p = sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
            " VALUES (?, 'p', '/p', 'main', ?) RETURNING id", (ws, OLD))[0][0]
    task = sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
               " VALUES (?, 't', 'done', 1, ?, ?) RETURNING id", (p, OLD, OLD))[0][0]
    one, two = (sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?) RETURNING id",
                    (d, OLD))[0][0] for d in ("/one", "/two"))
    made = [sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at, account_id)"
                " VALUES (?, 's', 'succeeded', 'l', ?, ?) RETURNING id", (task, OLD, a))[0][0]
            for a in (one, one, one, two, two)]
    with transaction() as conn:
        for run_id in made:
            UsageRepo(conn).record(run_id, SNAP)
    times = ["2026-11-02T00:00:00Z", "2026-11-03T00:00:00Z", "2026-11-01T00:00:00Z",  # account one: the 2nd
             "2026-11-05T00:00:00Z", "2026-11-05T00:00:00Z"]  # account two: a tie → the higher run_id
    for run_id, at in zip(made, times):
        sql("UPDATE usage_snapshots SET recorded_at = ? WHERE run_id = ?", (at, run_id))
    with transaction() as conn:
        latest = UsageRepo(conn).latest()
    assert {a: r["run_id"] for a, r in latest.items()} == {one: made[1], two: made[4]}
