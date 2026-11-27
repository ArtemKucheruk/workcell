import pytest
from conftest import sql

from workcell import db

from .test_projects import H, connect, workspace_id


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


# --- PATCH /api/workspaces/{id} (049) ------------------------------------------


def rows():
    return {"workspaces": sql("SELECT * FROM workspaces ORDER BY id"),
            "projects": sql("SELECT id, workspace_id FROM projects ORDER BY id")}


def rename(client, ws, body, headers=H):
    return client.patch(f"/api/workspaces/{ws}", json=body, headers=headers)


def remove(client, ws, headers=H):
    return client.delete(f"/api/workspaces/{ws}", headers=headers)


def test_rename_workspace(client):  # 049 BE10
    pid = connect(client, workspace="work")["id"]
    ws = workspace_id("work")
    r = rename(client, ws, {"name": "  work2 "})
    assert (r.status_code, r.json()) == (200, {"id": ws, "name": "work2"})
    assert sql("SELECT id, name FROM workspaces") == [(ws, "work2")]
    assert sql("SELECT id, workspace_id FROM projects") == [(pid, ws)]


def test_rename_workspace_clash(client):  # 049 BE11
    connect(client, path="/a", workspace="work")
    connect(client, path="/b", workspace="personal")
    ws = workspace_id("work")
    r = rename(client, ws, {"name": " work "})
    assert (r.status_code, r.json()) == (200, {"id": ws, "name": "work"})
    before = rows()
    r = rename(client, ws, {"name": "personal"})
    assert (r.status_code, r.json()) == (409, {"detail": "workspace personal already exists"})
    assert rows() == before


@pytest.mark.parametrize("body, detail", [
    ({"name": "  "}, "name must not be blank"), ({}, list), ({"name": None}, list), ({"name": 3}, list)])
def test_rename_workspace_invalid(client, body, detail):  # 049 BE12
    connect(client, workspace="work")
    before = rows()
    r = rename(client, workspace_id("work"), body)
    assert r.status_code == 422
    if detail is list:  # FastAPI's list detail
        assert isinstance(r.json()["detail"], list)
    else:
        assert r.json() == {"detail": detail}
    assert rows() == before


def test_rename_workspace_unknown(client):  # 049 BE13
    r = rename(client, 999, {"name": "x"})
    assert (r.status_code, r.json()) == (404, {"detail": "Workspace #999 not found"})


# --- DELETE /api/workspaces/{id} (049) -----------------------------------------


def test_delete_workspace(client):  # 049 BE19
    connect(client, workspace="personal")
    ws = client.post("/api/workspaces", json={"name": "empty"}, headers=H).json()["id"]
    r = remove(client, ws)
    assert r.status_code == 204
    assert r.content == b""
    assert sql("SELECT name FROM workspaces") == [("personal",)]
    assert client.get(f"/api/pages/workspaces/{ws}").status_code == 404
    listed = [w["id"] for w in client.get("/api/pages/sidebar").json()["workspaces"]]
    assert listed == [workspace_id("personal")]


@pytest.mark.parametrize("count, words", [(2, "2 projects"), (1, "1 project")])
def test_delete_workspace_with_projects(client, count, words):  # 049 BE20
    for i in range(count):
        connect(client, path=f"/p{i}", workspace="personal")
    before = rows()
    r = remove(client, workspace_id("personal"))
    assert (r.status_code, r.json()) == (
        409, {"detail": f"workspace personal still holds {words}; move or delete them first"})
    assert rows() == before


def test_delete_workspace_unknown(client):  # 049 BE21
    r = remove(client, 999)
    assert (r.status_code, r.json()) == (404, {"detail": "Workspace #999 not found"})


def test_workspace_routes_need_fctl_header(client):  # 049 BE22
    connect(client, workspace="work")
    empty = client.post("/api/workspaces", json={"name": "empty"}, headers=H).json()["id"]
    before = rows()
    for r in (rename(client, workspace_id("work"), {"name": "w2"}, headers={}), remove(client, empty, headers={})):
        assert (r.status_code, r.json()) == (403, {"detail": "X-Requested-By: fctl header required"})
    assert rows() == before
