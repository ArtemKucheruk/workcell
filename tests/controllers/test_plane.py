"""109: POST /api/projects/{id}/plane/sync, approve's mark done in Plane, and the API key's secrecy, against
conftest's FakePlane (a local http.server the real adapter talks to)."""

import io
import logging
import zipfile

import pytest
from conftest import PLANE_KEY, plane_item, sql
from controllers.test_reviews import task_with_rounds

from claude_factories.handlers import plane as handler

H = {"X-Requested-By": "fctl"}
BASE = "/api/v1/workspaces/acme/projects/p-1/"
T = "2026-01-01T00:00:00Z"


def connect(client, path="/code/api"):
    r = client.post("/api/projects/connect", headers=H, json={
        "path": path, "workspace": "w", "name": "api", "default_branch": "main"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def configure(client, pid, plane, **extra):
    r = client.patch(f"/api/projects/{pid}", headers=H, json={
        "plane_api_url": plane.url, "plane_workspace": "acme", "plane_project_id": "p-1",
        "plane_api_key": PLANE_KEY} | extra)
    assert r.status_code == 200, r.text


@pytest.fixture
def project(client, plane):
    pid = connect(client)
    configure(client, pid, plane)
    return pid


def sync(client, pid):
    return client.post(f"/api/projects/{pid}/plane/sync", headers=H, json={})


def synced(client, pid) -> dict:
    r = sync(client, pid)
    assert r.status_code == 200, r.text
    return r.json()


def refused(r, status=409) -> str:
    assert r.status_code == status, r.text
    assert PLANE_KEY not in r.text
    return r.json()["detail"]


def tasks() -> dict[str, tuple]:
    rows = sql("SELECT import_key, title, description_md, status, position,"
               " (SELECT COUNT(*) FROM events WHERE task_id = tasks.id) FROM tasks WHERE import_key IS NOT NULL")
    return {r[0]: r[1:] for r in rows}


def count() -> int:
    return sql("SELECT COUNT(*) FROM tasks")[0][0]


def key(n) -> str:
    return f"plane:acme/p-1/item-{n}"


# --- Sync now (AC6–AC12) ---------------------------------------------------------------------


def test_sync_calls_plane(client, project, plane):  # AC6
    plane.items = [plane_item(n) for n in range(1, 4)]
    assert synced(client, project) == {"new": 3, "updated": 0, "skipped": 0}
    paths = [r["path"] for r in plane.requests]
    assert paths == [BASE, BASE + "states/", BASE + "states/", BASE + "states/", BASE + "work-items/",
                     BASE + "work-items/"]  # 6 states and 3 items, 2 a page
    assert plane.requests[-1]["query"]["cursor"] == ["2:1:0"] and plane.requests[-1]["query"]["per_page"] == ["100"]
    assert {r["key"] for r in plane.requests} == {PLANE_KEY}


def test_sync_old_server(client, project, plane):  # AC7
    plane.old = True
    plane.items = [plane_item(1)]
    assert synced(client, project) == {"new": 1, "updated": 0, "skipped": 0}
    assert BASE + "issues/" in [r["path"] for r in plane.requests]


def test_sync_state_groups(client, project, plane):  # AC8
    plane.items = [plane_item(5, "s-u"), plane_item(2, "s-b"), plane_item(3, "s-s"), plane_item(4, "s-d"),
                   plane_item(6, "s-t"), plane_item(7, "gone")]
    assert synced(client, project) == {"new": 2, "updated": 0, "skipped": 0}
    ids = sql("SELECT import_key FROM tasks ORDER BY position")
    assert [r[0] for r in ids] == [key(2), key(5)]  # ascending sequence_id


def test_sync_new_task(client, project, plane):  # AC9
    plane.items = [plane_item(1, name="  Fix login  ", description="Steps\n\n"), plane_item(2, description="")]
    synced(client, project)
    found = tasks()
    assert found[key(1)] == ("Fix login", "Steps\n\nPlane work item: ENG-1", "backlog", 1.0, 1)
    assert found[key(2)] == ("Item 2", "Plane work item: ENG-2", "backlog", 2.0, 1)
    assert sql("SELECT actor, from_status, to_status FROM events") == [("app", None, "backlog")] * 2


def test_resync(client, project, plane):  # AC10
    plane.items = [plane_item(1), plane_item(2), plane_item(3)]
    synced(client, project)
    assert synced(client, project) == {"new": 0, "updated": 0, "skipped": 3}
    started = sql("SELECT id FROM tasks WHERE import_key = ?", (key(3),))[0][0]
    sql("UPDATE tasks SET status = 'in_progress', stage = 'build' WHERE id = ?", (started,))
    sql("INSERT INTO events (task_id, actor, from_status, to_status, created_at) VALUES (?, 'me', 'backlog',"
        " 'in_progress', ?)", (started, T))
    before = tasks()[key(3)]
    plane.items = [plane_item(1, name="Renamed"), plane_item(2, "s-s"), plane_item(3, name="Renamed too")]
    assert synced(client, project) == {"new": 0, "updated": 1, "skipped": 1}
    assert tasks()[key(1)][0] == "Renamed"
    assert tasks()[key(3)] == before  # started: untouched
    assert tasks()[key(2)][0] == "Item 2"  # no longer listed: left alone


def test_sync_conflict(client, project, plane):  # AC11
    other = connect(client, "/code/other")
    configure(client, other, plane)
    plane.items = [plane_item(2)]
    synced(client, other)
    plane.items = [plane_item(1), plane_item(2)]
    n = count()
    assert refused(sync(client, project)) == f"{key(2)} is imported in project #{other}"
    assert count() == n


def test_sync_holds_no_lock_during_http(client, project, plane, monkeypatch):  # AC11
    seen = []
    real = handler.Plane.items

    def items(self, *args):
        from claude_factories import db
        conn = db.connect()
        conn.execute("PRAGMA busy_timeout = 100")
        conn.execute("BEGIN IMMEDIATE")  # "database is locked" if sync held the write lock now
        conn.rollback()
        conn.close()
        seen.append(True)
        return real(self, *args)

    monkeypatch.setattr(handler.Plane, "items", items)
    plane.items = [plane_item(1)]
    assert synced(client, project)["new"] == 1 and seen


def test_sync_needs_settings(client, plane):  # AC12
    pid = connect(client)
    configure(client, pid, plane, plane_project_id="")
    assert refused(sync(client, pid)) == ("Plane sync needs the API URL, workspace slug, project ID and API key:"
                                          " fill them in project Settings")
    assert plane.requests == []


@pytest.mark.parametrize("where, status, code, detail", [
    ("", 401, 409, "Plane refused the API key: check it in project Settings"),
    ("states/", 403, 409, "Plane refused the API key: check it in project Settings"),
    ("", 404, 409, "Plane has no workspace acme or project p-1: check them in project Settings"),
    ("work-items/", 429, 409, "Plane's rate limit was hit: try again in a minute"),
    ("work-items/", 502, 500, f"Plane answered 502 to {BASE}work-items/"),
    ("states/", "html", 500, f"Plane answered 200 to {BASE}states/"),
])
def test_sync_refusals(client, project, plane, where, status, code, detail):  # AC12
    plane.items = [plane_item(1)]
    plane.fail[where] = status
    assert refused(sync(client, project), code) == detail
    assert count() == 0


def test_sync_unreachable(client, plane):  # AC12
    pid = connect(client)
    configure(client, pid, plane, plane_api_url="http://127.0.0.1:9")
    assert refused(sync(client, pid)) == "can't reach http://127.0.0.1:9: check the API URL in project Settings"


def test_sync_unknown_project(client, plane):  # AC12
    assert refused(sync(client, 99), 404) == "Project #99 not found"


# --- Mark done in Plane (AC13–AC15) -------------------------------------------------------------


def review_task(pid, import_key=key(7)):
    task, _ = task_with_rounds(pid, branch=None, worktree=None)
    sql("UPDATE tasks SET import_key = ? WHERE id = ?", (import_key, task))
    return task


def approve(client, task):
    r = client.post(f"/api/tasks/{task}/approve", headers=H, json={"body_md": ""})
    assert r.status_code == 200, r.text
    return r.json()


def status(task):
    return sql("SELECT status FROM tasks WHERE id = ?", (task,))[0][0]


def test_mark_done(client, project, plane):  # AC13
    configure(client, project, plane, plane_mark_done=True)
    task = review_task(project)
    out = approve(client, task)
    assert (out["status"], out["plane_warning"]) == ("done", None)
    assert [(r["method"], r["path"], r["body"]) for r in plane.requests] == [
        ("GET", BASE + "states/", None), ("GET", BASE + "states/", None), ("GET", BASE + "states/", None),
        ("PATCH", BASE + "work-items/item-7/", {"state": "s-d"})]  # the lowest sequence in `completed`


def test_mark_done_uses_the_key_project(client, project, plane):  # Q3
    configure(client, project, plane, plane_mark_done=True, plane_project_id="p-other")
    task = review_task(project)
    assert approve(client, task)["plane_warning"] is None
    assert plane.requests[-1]["path"] == BASE + "work-items/item-7/"


@pytest.mark.parametrize("setup, detail", [
    (lambda p: p.fail.update({"work-items/item-7/": 401}), "Plane refused the API key: check it in project Settings"),
    (lambda p: p.fail.update({"states/": 429}), "Plane's rate limit was hit: try again in a minute"),
    (lambda p: setattr(p, "states", [s for s in p.states if s["group"] != "completed"]),
     "Plane project has no completed state"),
])
def test_mark_done_failure_keeps_done(client, project, plane, setup, detail):  # AC14
    configure(client, project, plane, plane_mark_done=True)
    setup(plane)
    task = review_task(project)
    out = approve(client, task)
    assert out["status"] == "done" and out["plane_warning"] == f"Approved, but Plane wasn't updated: {detail}"
    assert status(task) == "done"


def test_mark_done_unreachable(client, project, plane):  # AC14
    configure(client, project, plane, plane_mark_done=True, plane_api_url="http://127.0.0.1:9")
    task = review_task(project)
    assert approve(client, task)["plane_warning"] == ("Approved, but Plane wasn't updated: can't reach"
                                                      " http://127.0.0.1:9: check the API URL in project Settings")
    assert status(task) == "done"


def test_no_mark_done(client, project, plane):  # AC15
    off = review_task(project)
    assert approve(client, off)["plane_warning"] is None  # plane_mark_done off
    configure(client, project, plane, plane_mark_done=True)
    for import_key in (None, "github:o/r#1", "factory:job-1"):
        assert approve(client, review_task(project, import_key))["plane_warning"] is None
    assert plane.requests == []


# --- Docs (AC21) ------------------------------------------------------------------------------------


def test_docs():  # AC21
    from pathlib import Path
    root = Path(__file__).parents[2]
    api = (root / "docs/data-model-and-api.md").read_text()
    for text in ("plane_api_url TEXT", "plane_mark_done INTEGER NOT NULL DEFAULT 0", "plane:<slug>/<project id>/",
                 "POST /api/projects/12/plane/sync", "plane_key_set", '"plane_warning":null'):
        assert text in api, text
    ui = (root / "docs/ui.md").read_text()
    assert "**Plane** (109)" in ui and "`plane_warning`" in ui
    mvp = (root / "docs/MVP.md").read_text()
    assert "Plane sync (109) is the one outbound call" in mvp and "- Plane sync (109): project Settings'" in mvp
    assert "Approved, but Plane wasn't updated" in (root / "src/claude_factories/fctl.md").read_text()


# --- The key is a secret (AC16) ------------------------------------------------------------------


def test_key_never_leaks(client, project, plane, caplog):  # AC16
    caplog.set_level(logging.DEBUG)
    configure(client, project, plane, plane_mark_done=True)
    plane.items = [plane_item(1)]
    patched = client.patch(f"/api/projects/{project}", headers=H, json={"plane_workspace": "acme"})
    synced(client, project)
    task = sql("SELECT id FROM tasks WHERE import_key = ?", (key(1),))[0][0]
    bodies = [patched.text, client.get(f"/api/pages/projects/{project}").text,
              client.get(f"/api/pages/tasks/{task}").text]
    plane.fail["work-items/"] = 401
    bodies.append(sync(client, project).text)  # a refusal's detail
    del plane.fail["work-items/"]
    review = review_task(project, key(9))
    plane.fail["work-items/item-9/"] = 500
    bodies.append(str(approve(client, review)))  # a warning
    export = client.get(f"/api/tasks/{task}/export")
    assert export.status_code == 200, export.text
    with zipfile.ZipFile(io.BytesIO(export.content)) as z:
        bodies += [z.read(name).decode(errors="replace") for name in z.namelist()]
    assert all(PLANE_KEY not in b for b in bodies)
    assert PLANE_KEY not in caplog.text and all(PLANE_KEY not in str(r.args) for r in caplog.records)
