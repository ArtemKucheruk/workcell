"""104: the schedules API (docs/data-model-and-api.md §6.1), with fake git and claude, and the docs it changes."""

import time
from pathlib import Path

import pytest
from conftest import sql
from controllers.test_automation_runs import add_factory, auto, automation_running  # noqa: F401
from controllers.test_runs import H, OLD, fake, project  # noqa: F401

from claude_factories.lib.cron import next_after
from claude_factories.handlers.schedules import iso

REPO = Path(__file__).resolve().parents[2]


def create(client, project_id, body):
    return client.post(f"/api/projects/{project_id}/schedules", json=body, headers=H)


def patch(client, schedule_id, body):
    return client.patch(f"/api/schedules/{schedule_id}", json=body, headers=H)


def next_times(expr, before, after) -> set[str]:
    """next_after from either side of a request, so a minute boundary in between doesn't flake."""
    return {iso(next_after(expr, before)), iso(next_after(expr, after))}


def made(client, project_id, body) -> dict:
    r = create(client, project_id, body)
    assert r.status_code == 201, r.text
    return r.json()


def count() -> int:
    return sql("SELECT COUNT(*) FROM schedules")[0][0]


def add_account(email="b@y", config_dir="/tmp/account-2") -> int:
    return sql("INSERT INTO claude_accounts (config_dir, active, email, created_at) VALUES (?, 0, ?, ?) RETURNING id",
               (config_dir, email, OLD))[0][0]


# --- POST ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("extra", [{}, {"account_id": None}])
def test_create(client, project, auto, extra):  # AC8
    before = time.time()
    out = made(client, project, {"factory_id": auto, "cron": " 0  9 * * 1 "} | extra)
    after = time.time()
    assert out == {"id": out["id"], "factory_id": auto, "automation": "Security audit", "cron": "0 9 * * 1",
                   "summary": "Weekly on Monday at 09:00", "enabled": True, "account_id": None, "account": None,
                   "next_run_at": out["next_run_at"], "last_run": None, "last_skip": None, "last_skip_at": None}
    assert out["next_run_at"] in next_times("0 9 * * 1", before, after)
    assert out["next_run_at"].endswith("Z")
    assert sql("SELECT factory_id, cron, enabled, account_id FROM schedules") == [(auto, "0 9 * * 1", 1, None)]


def test_create_with_account(client, project, auto):  # AC8: account is the label
    two = add_account()
    out = made(client, project, {"factory_id": auto, "cron": "5 * * * *", "account_id": two})
    assert (out["account_id"], out["account"], out["summary"]) == (two, "b@y", "Hourly at :05")
    sql("DELETE FROM schedules")
    out = made(client, project, {"factory_id": auto, "cron": "5 * * * *", "account_id": 1})  # no email: the dir's name
    assert out["account"] == "claude-config"


def test_create_refusals(client, project, auto, tmp_path, repo):  # AC9
    workflow = add_factory(project, "Review loop", "workflow")
    sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at) VALUES (1, 'other', ?, 'main', ?)",
        (str(tmp_path / "other"), OLD))
    other = add_factory(sql("SELECT MAX(id) FROM projects")[0][0], "Elsewhere")
    cases = [
        (99, {"factory_id": auto, "cron": "0 9 * * *"}, 404, "Project #99 not found"),
        (project, {"factory_id": 9, "cron": "0 9 * * *"}, 404, "Factory #9 not found"),
        (project, {"factory_id": other, "cron": "0 9 * * *"}, 404, f"Factory #{other} not found"),
        (project, {"factory_id": workflow, "cron": "0 9 * * *"}, 409,
         "Review loop is a workflow; only automations can be scheduled"),
        (project, {"factory_id": auto, "cron": "0 9 * *"}, 422,
         "cron needs 5 fields (minute hour day month weekday), got 4"),
        (project, {"factory_id": auto, "cron": "0 0 30 2 *"}, 422, "cron 0 0 30 2 * never runs"),
        (project, {"factory_id": auto, "cron": "0 9 * * *", "account_id": 99}, 422, "no Claude account #99"),
    ]
    for project_id, body, status, detail in cases:
        r = create(client, project_id, body)
        assert (r.status_code, r.json()) == (status, {"detail": detail}), body
    assert count() == 0
    assert client.post(f"/api/projects/{project}/schedules", json={"factory_id": auto, "cron": "0 9 * * *"}
                       ).status_code == 403  # no X-Requested-By
    assert count() == 0
    made(client, project, {"factory_id": auto, "cron": "0 9 * * *"})
    r = create(client, project, {"factory_id": auto, "cron": "0 10 * * *"})
    assert (r.status_code, r.json()) == (409, {"detail": "Security audit already has a schedule; edit it instead"})
    assert sql("SELECT cron FROM schedules") == [("0 9 * * *",)]
    assert create(client, project, {"factory_id": auto}).status_code == 422  # FastAPI's list detail


# --- GET ----------------------------------------------------------------------------------------------------


def test_list(client, project, auto):  # AC10
    zeta = add_factory(project, "Zeta")
    alpha = add_factory(project, "Alpha")
    ids = [made(client, project, {"factory_id": f, "cron": "0 9 * * *"})["id"] for f in (zeta, auto, alpha)]
    run = automation_running(auto)
    sql("UPDATE runs SET started_at = '2026-11-20T09:00:00Z' WHERE id = ?", (run,))
    sql("UPDATE schedules SET last_run_id = ?, last_skip = 'x', last_skip_at = ? WHERE factory_id = ?", (run, OLD, auto))
    r = client.get(f"/api/projects/{project}/schedules")
    assert r.status_code == 200
    rows = r.json()
    assert [s["automation"] for s in rows] == ["Alpha", "Security audit", "Zeta"]
    assert [s["id"] for s in rows] == [ids[2], ids[1], ids[0]]
    assert rows[1]["last_run"] == {"id": run, "status": "running", "started_at": "2026-11-20T09:00:00Z"}
    assert (rows[1]["last_skip"], rows[1]["last_skip_at"]) == ("x", OLD)
    sql("UPDATE runs SET status = 'succeeded' WHERE id = ?", (run,))  # its current status
    assert client.get(f"/api/projects/{project}/schedules").json()[1]["last_run"]["status"] == "succeeded"
    r = client.get("/api/projects/99/schedules")
    assert (r.status_code, r.json()) == (404, {"detail": "Project #99 not found"})


# --- PATCH --------------------------------------------------------------------------------------------------


def test_patch(client, project, auto):  # AC11
    two = add_account()
    s = made(client, project, {"factory_id": auto, "cron": "0 9 * * *", "account_id": two})
    first = s["next_run_at"]
    out = patch(client, s["id"], {"enabled": False}).json()
    assert (out["enabled"], out["next_run_at"], out["cron"], out["account_id"]) == (False, None, "0 9 * * *", two)
    out = patch(client, s["id"], {"cron": "30 8 * * 1"}).json()  # a new cron while paused stays paused
    assert (out["cron"], out["next_run_at"], out["summary"]) == ("30 8 * * 1", None, "Weekly on Monday at 08:30")
    before = time.time()
    out = patch(client, s["id"], {"enabled": True}).json()
    assert out["enabled"] is True and out["next_run_at"] in next_times("30 8 * * 1", before, time.time())
    before = time.time()
    out = patch(client, s["id"], {"cron": "5 * * * *"}).json()
    assert out["next_run_at"] in next_times("5 * * * *", before, time.time())
    sql("UPDATE schedules SET next_run_at = ?", (first,))
    out = patch(client, s["id"], {"enabled": True, "account_id": 1}).json()  # already enabled: next stays
    assert (out["next_run_at"], out["account_id"], out["account"]) == (first, 1, "claude-config")
    out = patch(client, s["id"], {"account_id": None}).json()
    assert (out["account_id"], out["account"], out["cron"], out["enabled"]) == (None, None, "5 * * * *", True)
    out = patch(client, s["id"], {}).json()
    assert (out["account_id"], out["cron"], out["next_run_at"]) == (None, "5 * * * *", first)


def test_patch_refusals(client, project, auto):  # AC11
    s = made(client, project, {"factory_id": auto, "cron": "0 9 * * *"})
    before = sql("SELECT * FROM schedules")
    for body, detail in [({"cron": "61 * * * *", "enabled": False}, "cron minute 61 is out of range 0–59"),
                         ({"account_id": 99, "enabled": False}, "no Claude account #99")]:
        r = patch(client, s["id"], body)
        assert (r.status_code, r.json()) == (422, {"detail": detail})
    assert sql("SELECT * FROM schedules") == before
    r = patch(client, 9, {"enabled": False})
    assert (r.status_code, r.json()) == (404, {"detail": "schedule #9 not found"})
    assert client.patch(f"/api/schedules/{s['id']}", json={"enabled": False}).status_code == 403
    assert sql("SELECT * FROM schedules") == before


# --- DELETE -------------------------------------------------------------------------------------------------


def test_delete(client, project, auto):  # AC12
    s = made(client, project, {"factory_id": auto, "cron": "0 9 * * *"})
    run = automation_running(auto)
    sql("UPDATE schedules SET last_run_id = ?", (run,))
    assert client.delete(f"/api/schedules/{s['id']}").status_code == 403
    r = client.delete(f"/api/schedules/{s['id']}", headers=H)
    assert (r.status_code, r.content) == (204, b"")
    assert count() == 0
    assert sql("SELECT id FROM factories WHERE id = ?", (auto,)) == [(auto,)]
    assert sql("SELECT id FROM runs") == [(run,)]
    r = client.delete("/api/schedules/9", headers=H)
    assert (r.status_code, r.json()) == (404, {"detail": "schedule #9 not found"})


def test_removed_with_automation_or_project(client, project, auto):  # AC13
    other = add_factory(project, "Test coverage")
    made(client, project, {"factory_id": auto, "cron": "0 9 * * *"})
    made(client, project, {"factory_id": other, "cron": "0 9 * * *"})
    assert client.delete(f"/api/factories/{auto}", headers=H).status_code == 204
    assert sql("SELECT factory_id FROM schedules") == [(other,)]
    assert client.delete(f"/api/projects/{project}", headers=H).status_code == 204
    assert count() == 0


# --- Docs (AC32) --------------------------------------------------------------------------------------------


def doc(name: str) -> str:
    return " ".join((REPO / "docs" / name).read_text().split())


def between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def test_docs():  # AC32
    mvp = doc("MVP.md")
    flows = between(mvp, "### 3.2 Create a factory", "### 3.3 ")
    assert "no scheduler" not in flows and "cron recipe" not in flows and "comes later" not in flows
    assert "Scheduler page" in flows
    decisions = between(mvp, "### 4.3 Decisions", "### 4.4 ")
    paragraph = between(decisions, "**The scheduler runs inside the backend.**", "**Agents call")
    for phrase in ("each minute", "still running", "last_skip", "not caught up", "local time", "TZ",
                   "doesn't exist", "first"):
        assert phrase in paragraph, phrase
    assert "trigger = 'schedule'" in between(mvp, "### 4.4 How a run is spawned", "### 4.5 ")
    mvp_scope, later = between(mvp, "**MVP**", "**Later**"), between(mvp, "**Later**", "## 10.")
    assert "Scheduled runs" in mvp_scope and "Scheduled runs" not in later
    claude = doc("claude-code.md")
    assert "crontab" not in claude and "fctl task add \"Security audit\" --run" not in claude
    assert "**Scheduling an automation.**" in claude and "Scheduler page" in claude
    ui = doc("ui.md")
    assert "**Workflows** (`/projects/{id}/factories`, item 14), **Scheduler** (`/projects/{id}/scheduler`" in ui
    sidebar = between(ui, "### 8.4 Sidebar", "### 8.5 ")
    assert sidebar.index("Workflows") < sidebar.index("Scheduler") < sidebar.index("Settings")
    assert "scheduling is a later page" not in ui
    assert "17. **Scheduler** (`/projects/{id}/scheduler`" in ui and "### 8.11 Scheduler" in ui
    assert "(Board, Task detail, Reviews, Agents, Scheduler)" in ui
    assert "`in 5m`" in ui and "`tomorrow`" in ui
    api = doc("data-model-and-api.md")
    assert "CREATE TABLE schedules (" in api
    assert "schedule for the scheduler's runs" in api
    assert "An automation has 0–1 schedules" in api
    for endpoint in ("GET /api/projects/3/schedules", "POST /api/projects/3/schedules", "PATCH /api/schedules/4",
                     "DELETE /api/schedules/4", "<Schedule> ="):
        assert endpoint in between(api, "### 6.1 ", "### 6.2 "), endpoint
    assert "`/projects/{id}/scheduler`" in between(api, "### 6.4 ", "```")
