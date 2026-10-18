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
