"""103: GET /api/pages/factories/{id}/runs, an automation's runs page data (docs/data-model-and-api.md §6.4)."""

from types import SimpleNamespace

import pytest
from conftest import sql
from controllers.test_automation_runs import accounts, add_factory, auto  # noqa: F401
from controllers.test_pages_api import section
from controllers.test_run_accounts import snapshot
from controllers.test_runs import H, add_running_run, add_task, cap, fake, project  # noqa: F401
from controllers.test_transcripts import LISTED, add_transcript


def add_run(factory_id, started_at, status="succeeded", error=None, account_id=None, trigger="manual",
            ended_at="2026-10-21T10:05:00Z") -> int:
    return sql("INSERT INTO runs (task_id, factory_id, kind, trigger, session_id, status, log_path, started_at,"
               " ended_at, error, account_id) VALUES (NULL, ?, 'automation', ?, 's', ?, 'l', ?, ?, ?, ?) RETURNING id",
               (factory_id, trigger, status, started_at, None if status == "running" else ended_at, error,
                account_id))[0][0]


def page(client, factory_id):
    return client.get(f"/api/pages/factories/{factory_id}/runs")


@pytest.fixture
def three(client, project, auto, accounts):
    """Three runs of `auto`, a task run, and another automation's run."""
    old = add_run(auto, "2026-10-20T09:00:00Z", account_id=2)
    tie_low = add_run(auto, "2026-10-21T09:00:00Z", status="failed", error="claude exited with code 1",
                      account_id=1, trigger="schedule")
    tie_high = add_run(auto, "2026-10-21T09:00:00Z", status="running")
    add_running_run(add_task(project, status="in_progress"))
    add_run(add_factory(project, "Nightly"), "2026-10-22T09:00:00Z")
    return SimpleNamespace(old=old, tie_low=tie_low, tie_high=tie_high)


def test_page(client, project, auto, three):  # AC1
    r = page(client, auto)
    assert r.status_code == 200, r.text
    body = r.json()
    [(workspace_id, workspace)] = sql("SELECT w.id, w.name FROM projects p JOIN workspaces w ON w.id = p.workspace_id"
                                      " WHERE p.id = ?", (project,))
    assert body["automation"] == {"id": auto, "name": "Security audit", "project_id": project, "project": "repo",
                                  "workspace_id": workspace_id, "workspace": workspace}
    assert [r["id"] for r in body["runs"]] == [three.tie_high, three.tie_low, three.old]
    sql("UPDATE factories SET name = 'Audit' WHERE id = ?", (auto,))
    assert page(client, auto).json()["automation"]["name"] == "Audit"  # the names as they are now


def test_run_fields(client, auto, three):  # AC2
    sql("UPDATE runs SET error = 'leftover' WHERE id = ?", (three.old,))  # not failed: no error shown
    sql("INSERT INTO claude_accounts (config_dir, active, created_at) VALUES ('/tmp/no-email', 0, 'x'),"
        " ('/tmp/gone-account', 0, 'x')")
    unnamed = add_run(auto, "2026-10-19T08:00:00Z", account_id=3)
    gone = add_run(auto, "2026-10-19T09:00:00Z", status="stopped", account_id=4)
    sql("DELETE FROM claude_accounts WHERE id = 4")
    runs = {r["id"]: r for r in page(client, auto).json()["runs"]}
    assert runs[three.tie_low] == {"id": three.tie_low, "status": "failed", "trigger": "schedule",
                                   "started_at": "2026-10-21T09:00:00Z", "ended_at": "2026-10-21T10:05:00Z",
                                   "error": "claude exited with code 1", "account": "a@x",
                                   "transcripts": []}
    assert runs[unnamed]["account"] == "no-email"  # no email: the config dir's last component
    assert (runs[three.old]["error"], runs[three.old]["account"]) == (None, "b@y")
    assert (runs[three.tie_high]["status"], runs[three.tie_high]["ended_at"], runs[three.tie_high]["account"]) == (
        "running", None, None)
    assert runs[gone]["account"] is None


def test_transcripts(client, auto, three):  # AC3
    later = add_transcript(three.old, None, "b", started_at="2026-10-20T09:10:00Z")
    first = add_transcript(three.old, None, "a", started_at="2026-10-20T09:01:00Z")
    tie = add_transcript(three.old, None, "c", started_at="2026-10-20T09:10:00Z")
    other = add_transcript(three.tie_low, None, "d")
    runs = {r["id"]: r for r in page(client, auto).json()["runs"]}
    assert [t["id"] for t in runs[three.old]["transcripts"]] == [first, later, tie]
    assert set(runs[three.old]["transcripts"][0]) == set(LISTED)
    assert runs[three.old]["transcripts"][0]["run_id"] == three.old
    assert [t["id"] for t in runs[three.tie_low]["transcripts"]] == [other]
    assert runs[three.tie_high]["transcripts"] == []


def test_no_runs(client, project, auto):  # AC4
    r = page(client, auto)
    assert (r.status_code, r.json()["runs"]) == (200, [])


def test_run_menu(client, project, auto, accounts):  # AC5
    snapshot(1, five=0.95)
    cap(3)
    add_run(auto, "2026-10-21T09:00:00Z", status="running")
    accounts.claude.checked.clear()
    body = page(client, auto).json()
    board = client.get(f"/api/pages/projects/{project}").json()
    for key in ("runs_enabled", "runs_active", "max_concurrent_runs", "accounts", "auto"):
        assert body[key] == board[key], key
    assert (body["runs_enabled"], body["runs_active"], body["max_concurrent_runs"]) == (True, 1, 3)
    assert body["auto"] == {"account_id": 2, "label": "b@y"}
    for _ in range(3):
        page(client, auto)
    assert len(accounts.claude.checked) <= 1  # claude_login's cache: no claude call per poll


def test_unknown(client, project):  # AC6
    r = page(client, 99)
    assert (r.status_code, r.json()) == (404, {"detail": "Factory #99 not found"})


def test_docs():  # AC28
    ui = section("ui.md", "## 8.")
    for text in ("17. **Automation runs**", "### 8.11 Automation runs", "Runs of <name>", "before **Files**",
                 "Workflows › <automation>", "Agents, Automation runs, Scheduler)", "Workflows › <automation> › <label>",
                 "Started run #44 as b@y."):
        assert text in ui, text
    pages = section("data-model-and-api.md", "### 6.4")
    for text in ("/projects/{id}/factories/{fid}/runs?run=", "GET  /api/pages/factories/7/runs",
                 "default is a workflow; its runs are on its tasks", "Factory #99 not found", '"trigger":"manual"'):
        assert text in pages, text
    runs = section("data-model-and-api.md", "### 6.2")
    assert '"factory_id":null, "factory":null' in runs and '"task_id":null, "factory_id":7' in runs


def test_workflow(client, project):  # AC7
    r = page(client, add_factory(project, "default", "workflow"))
    assert (r.status_code, r.json()) == (404, {"detail": "default is a workflow; its runs are on its tasks"})
