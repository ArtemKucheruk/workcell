import re

import pytest
from conftest import git, sql

from claude_factories.server.deps import get_git

H = {"X-Requested-By": "fctl"}
SKILL = ".claude/skills/factory/SKILL.md"
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


def body(**overrides):
    return {"path": "/code/api", "workspace": "personal", "name": "api",
            "remote_url": "git@github.com:me/api.git", "default_branch": "main",
            "test_cmd": "pytest -q"} | overrides


def connect(client, **overrides):
    r = client.post("/api/projects/connect", json=body(**overrides), headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def workspace_id(name):
    return sql("SELECT id FROM workspaces WHERE name = ?", (name,))[0][0]


def project_workspace(project_id):
    return sql("SELECT workspace_id FROM projects WHERE id = ?", (project_id,))[0][0]


def commit_skill(repo):
    (repo / SKILL).parent.mkdir(parents=True)
    (repo / SKILL).write_text("# factory\n")
    git(repo, "add", SKILL)
    git(repo, "commit", "-q", "-m", "Add factory")


# --- POST /api/projects/connect --------------------------------------------------


def test_connect_creates_workspace_and_project(client):  # AC3
    r = client.post("/api/projects/connect", json=body(), headers=H)
    assert r.status_code == 200
    pid = r.json()["id"]
    assert r.json() == {"id": pid, "created": True, "url": f"http://127.0.0.1:4545/projects/{pid}"}
    assert [name for (name,) in sql("SELECT name FROM workspaces")] == ["personal"]
    [row] = sql("SELECT id, workspace_id, path, name, remote_url, default_branch, test_cmd,"
                " factory_version, created_at FROM projects")
    assert row[:8] == (pid, workspace_id("personal"), "/code/api", "api",
                       "git@github.com:me/api.git", "main", "pytest -q", None)
    assert TIMESTAMP.fullmatch(row[8])


def test_connect_existing_workspace(client):  # AC4
    a = connect(client, path="/a")
    b = connect(client, path="/b")
    assert sql("SELECT COUNT(*) FROM workspaces") == [(1,)]
    assert project_workspace(a["id"]) == project_workspace(b["id"]) == workspace_id("personal")


def test_connect_rerun_updates(client):  # AC5
    first = connect(client)
    created_at = sql("SELECT created_at FROM projects")[0][0]
    second = connect(client, name="api2", remote_url="git@x:y.git", default_branch="trunk",
                     test_cmd="make test")
    assert second["id"] == first["id"]
    assert second["created"] is False
    assert sql("SELECT name, remote_url, default_branch, test_cmd, created_at FROM projects") == [
        ("api2", "git@x:y.git", "trunk", "make test", created_at)]


def test_connect_null_test_cmd_keeps_stored(client):  # AC6
    connect(client)
    connect(client, test_cmd=None)
    assert sql("SELECT test_cmd FROM projects") == [("pytest -q",)]


def test_connect_rerun_moves_workspace(client):  # AC7
    pid = connect(client)["id"]
    connect(client, workspace="work")
    assert project_workspace(pid) == workspace_id("work")
    connect(client, workspace="personal")
    assert project_workspace(pid) == workspace_id("personal")
    assert sql("SELECT COUNT(*) FROM workspaces") == [(2,)]


def test_connect_strips_workspace(client):  # AC8
    connect(client, path="/a")
    pid = connect(client, path="/b", workspace=" personal ")["id"]
    assert project_workspace(pid) == workspace_id("personal")
    assert sql("SELECT COUNT(*) FROM workspaces") == [(1,)]


@pytest.mark.parametrize("field, value", [
    ("path", "code/api"), ("workspace", "  "), ("name", " "),
    ("default_branch", ""), ("default_branch", "--output=/tmp/x"),
])
def test_connect_invalid_field(client, field, value):  # AC9
    r = client.post("/api/projects/connect", json=body(**{field: value}), headers=H)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert sql("SELECT (SELECT COUNT(*) FROM workspaces), (SELECT COUNT(*) FROM projects)") == [(0, 0)]


# --- GET /api/projects?path= and factory state ----------------------------------


def test_find_project_keys(client):  # AC10
    pid = connect(client)["id"]
    r = client.get("/api/projects", params={"path": "/code/api"})
    assert r.status_code == 200
    assert r.json() == {"id": pid, "name": "api", "default_branch": "main", "factory": "none"}


def test_find_project_unknown(client):  # AC11
    r = client.get("/api/projects", params={"path": "/nope"})
    assert (r.status_code, r.json()) == (404, {"detail": "no project at /nope; in that repo, run fctl connect --workspace <name>"})


def factory(client, path):
    connect(client, path=str(path))
    r = client.get("/api/projects", params={"path": str(path)})
    assert r.status_code == 200
    return r.json()["factory"]


def test_factory_ready(client, repo):  # AC12
    commit_skill(repo)
    assert factory(client, repo) == "ready"


@pytest.mark.parametrize("how", ["untracked", "other branch"])
def test_factory_uncommitted(client, repo, how):  # AC13
    if how == "other branch":
        git(repo, "switch", "-q", "-c", "other")
        commit_skill(repo)
    else:
        (repo / SKILL).parent.mkdir(parents=True)
        (repo / SKILL).write_text("# factory\n")
    assert (repo / SKILL).is_file()
    assert factory(client, repo) == "uncommitted"


def test_factory_none(client, repo):  # AC14
    assert factory(client, repo) == "none"


def test_factory_missing_path(client, tmp_path):  # AC15
    assert factory(client, tmp_path / "gone") == "none"


# --- 034: one transaction per handler call, adapters through Depends --------------------


def test_connect_is_one_transaction(client):  # 034 AC13
    raw = '{"path": "/code/api", "workspace": "fresh", "name": "\\ud800", "default_branch": "main"}'
    r = client.post("/api/projects/connect", content=raw, headers=H | {"Content-Type": "application/json"})
    assert (r.status_code, r.json()) == (422, {"detail": "text must not contain lone surrogates"})
    assert sql("SELECT (SELECT COUNT(*) FROM workspaces), (SELECT COUNT(*) FROM projects)") == [(0, 0)]


class CommittedGit:
    """A git adapter whose committed check always says yes."""

    def committed(self, path, branch, file):
        return True


def test_git_adapter_through_depends(client):  # 034 AC14
    connect(client, path="/nowhere")

    def state():
        return client.get("/api/projects", params={"path": "/nowhere"}).json()["factory"]

    client.app.dependency_overrides[get_git] = CommittedGit
    assert state() == "ready"
    client.app.dependency_overrides.clear()
    assert state() == "none"
