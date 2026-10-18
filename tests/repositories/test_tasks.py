"""TasksRepo.lock(): SQLite's write lock, and the writes that take it (035 AC12, AC13)."""

import sqlite3
from contextlib import closing

import pytest

from claude_factories import config, db
from claude_factories.repositories.tasks import TasksRepo

H = {"X-Requested-By": "fctl"}
ROUND = {"base_sha": "abc1234", "patch": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n"}


def test_lock_takes_the_write_lock():  # 035 AC12
    db.init()
    with closing(db.connect()) as first, \
            closing(sqlite3.connect(config.data_dir() / "factory.db", timeout=0)) as second:
        TasksRepo(first).lock()
        with pytest.raises(sqlite3.OperationalError):
            second.execute("BEGIN IMMEDIATE")
        first.commit()
        second.execute("BEGIN IMMEDIATE")
        second.rollback()


@pytest.fixture
def locks(monkeypatch):
    """TasksRepo.lock swapped for a wrapper that counts its calls."""
    calls, lock = [], TasksRepo.lock

    def counted(self):
        calls.append(1)
        return lock(self)

    monkeypatch.setattr(TasksRepo, "lock", counted)
    return calls


def test_writes_that_lock(client, locks):  # 035 AC13
    def locked(method, url, body) -> int:
        before = len(locks)
        r = client.request(method, url, json=body, headers=H)
        assert r.status_code < 300, r.text
        return len(locks) - before

    connect = {"path": "/code/api", "workspace": "personal", "name": "api", "default_branch": "main"}
    project = client.post("/api/projects/connect", json=connect, headers=H).json()["id"]
    before = len(locks)
    r = client.post(f"/api/projects/{project}/tasks", json={"title": "t"}, headers=H)
    assert r.status_code == 201, r.text
    counts = {"create task": len(locks) - before}
    t = f"/api/tasks/{r.json()['id']}"
    for name, method, url, body in [
        ("PATCH", "PATCH", t, {"spec_md": "s"}),
        ("submit round", "POST", f"{t}/rounds", ROUND),  # standalone: now in review · human_review
        ("PUT verdict", "PUT", f"{t}/rounds/latest/verdicts/code", {"verdict": "PASS"}),
        ("POST comment", "POST", f"{t}/comments", {"author": "code", "body_md": "c"}),
        ("POST decision", "POST", f"{t}/decision", {"decision": "APPROVE"}),
        ("request changes", "POST", f"{t}/request-changes", {"body_md": "fix"}),  # standalone: no run
        ("submit again", "POST", f"{t}/rounds", ROUND),
        ("approve", "POST", f"{t}/approve", {}),
    ]:
        counts[name] = locked(method, url, body)
    assert counts == {
        "create task": 1, "PATCH": 1, "submit round": 1, "PUT verdict": 0, "POST comment": 0, "POST decision": 0,
        "request changes": 1, "submit again": 1, "approve": 1,
    }
