"""095: GET /api/usage (AC13, AC14) and the sidebar's `usage` (AC19), over HTTP."""

import inspect
import json

import pytest
from conftest import sql

from workcell.handlers import usage as usage_handler
from workcell.repositories.usage import UsageRepo
from workcell.server.deps import get_claude, get_git, transaction

OLD = "2026-01-01T00:00:00Z"
FAR = 4_000_000_000
SNAP = {"five_hour": {"utilization": 0.34, "resets_at": FAR, "status": "allowed"},
        "seven_day": {"utilization": 0.12, "resets_at": 1, "status": "allowed"},  # long passed: reads as reset
        "status": "allowed", "overage": False, "limited": False}


def get(client, path, status=200):
    r = client.get(path)
    assert r.status_code == status, r.text
    return r.json()


@pytest.fixture
def snapshot(client):
    """Account 1 (conftest's CLAUDE_CONFIG_DIR) has no snapshot; a second, with an email, has one."""
    ws = sql("INSERT INTO workspaces (name, created_at) VALUES ('w', ?) RETURNING id", (OLD,))[0][0]
    p = sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
            " VALUES (?, 'p', '/p', 'main', ?) RETURNING id", (ws, OLD))[0][0]
    task = sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
               " VALUES (?, 't', 'done', 1, ?, ?) RETURNING id", (p, OLD, OLD))[0][0]
    two = sql("INSERT INTO claude_accounts (config_dir, email, created_at) VALUES ('/secret/dir', 'two@x.io', ?)"
              " RETURNING id", (OLD,))[0][0]
    run_id = sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at, account_id)"
                 " VALUES (?, 's', 'succeeded', 'l', ?, ?) RETURNING id", (task, OLD, two))[0][0]
    with transaction() as conn:
        UsageRepo(conn).record(run_id, SNAP)
    return {"account": two, "run": run_id}


def test_usage(client, snapshot):  # AC13
    body = get(client, "/api/usage")
    assert list(body) == ["accounts", "stats", "limited_runs"]
    [(recorded,)] = sql("SELECT recorded_at FROM usage_snapshots")
    assert body["accounts"] == [
        {"id": 1, "label": "claude-config", "active": True, "recorded_at": None, "run_id": None, "overage": None,
         "five_hour": None, "seven_day": None},
        {"id": snapshot["account"], "label": "two@x.io", "active": False, "recorded_at": recorded,
         "run_id": snapshot["run"], "overage": False,
         "five_hour": {"utilization": 0.34, "resets_at": FAR, "state": "allowed", "reset": False},
         "seven_day": {"utilization": 0, "resets_at": 1, "state": "allowed", "reset": True}},
    ]
    text = json.dumps(body)
    assert "/secret/dir" not in text and "config_dir" not in text


@pytest.mark.parametrize("query, days", [("", 7), ("?days=7", 7), ("?days=30", 30)])
def test_usage_days(client, query, days):  # AC14
    stats = get(client, f"/api/usage{query}")["stats"]
    assert stats["days"] == days and len(stats["by_day"]) == days


@pytest.mark.parametrize("query", ["?days=1", "?days=14", "?days=31", "?days=abc", "?days=0"])
def test_usage_bad_days(client, query):  # AC14
    assert get(client, f"/api/usage{query}", 422)["detail"]


class Boom:
    def __getattr__(self, name):
        raise AssertionError(f"{name} called")


def test_sidebar_usage(client, snapshot):  # AC19: the same accounts, no git, no claude
    client.app.dependency_overrides[get_git] = Boom
    client.app.dependency_overrides[get_claude] = Boom
    page = get(client, "/api/pages/sidebar")
    assert set(page) == {"workspaces", "current", "usage"}
    assert page["usage"] == get(client, "/api/usage")["accounts"]
    assert {"git", "claude"}.isdisjoint(inspect.signature(usage_handler.usage).parameters)
