from conftest import sql

from claude_factories import db

from .test_projects import connect, workspace_id


# --- GET /api/workspaces -------------------------------------------------------


def test_workspaces_empty(client):  # AC1
    r = client.get("/api/workspaces")
    assert (r.status_code, r.json()) == (200, [])


def test_workspaces_with_counts_by_name(client):  # AC2
    connect(client, path="/w1", workspace="work")
    connect(client, path="/p1", workspace="personal")
    connect(client, path="/p2", workspace="personal")
    sql("INSERT INTO workspaces (name, created_at) VALUES ('empty', ?)", (db.now(),))
    r = client.get("/api/workspaces")
    assert r.status_code == 200
    assert r.json() == [
        {"id": workspace_id("empty"), "name": "empty", "projects": 0},
        {"id": workspace_id("personal"), "name": "personal", "projects": 2},
        {"id": workspace_id("work"), "name": "work", "projects": 1},
    ]


# --- POST /api/workspaces (020) ------------------------------------------------


def test_create_workspace_strips_and_reuses(client):  # 020 AC28
    r = client.post("/api/workspaces", json={"name": " work "}, headers={"X-Requested-By": "fctl"})
    assert r.status_code == 200, r.text
    created = r.json()
    assert created == {"id": workspace_id("work"), "name": "work"}
    r = client.post("/api/workspaces", json={"name": "work"}, headers={"X-Requested-By": "fctl"})
    assert (r.status_code, r.json()) == (200, created)
    assert sql("SELECT COUNT(*) FROM workspaces") == [(1,)]


def test_create_workspace_refused(client):  # 020 AC29
    r = client.post("/api/workspaces", json={"name": "  "}, headers={"X-Requested-By": "fctl"})
    assert (r.status_code, r.json()) == (422, {"detail": "name must not be blank"})
    r = client.post("/api/workspaces", json={"name": "work"})
    assert r.status_code == 403
    assert sql("SELECT COUNT(*) FROM workspaces") == [(0,)]
