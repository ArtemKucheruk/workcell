import re

import pytest
from conftest import git, sql

from claude_factories.lib.markdown import render
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


# --- PATCH /api/projects/{id} (020) -----------------------------------------------


def test_move_project(client):  # 020 AC30
    pid = connect(client)["id"]
    work = client.post("/api/workspaces", json={"name": "work"}, headers=H).json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"workspace_id": work}, headers=H)
    assert (r.status_code, r.json()) == (200, {"id": pid, "workspace_id": work})
    assert project_workspace(pid) == work


@pytest.mark.parametrize("target, body, status", [
    ("unknown project", None, 404), ("unknown workspace", {"workspace_id": 999}, 404),
    ("project", {"workspace_id": 2**63}, 422), ("project", {}, 422), ("project", {"workspace_id": "x"}, 422),
    ("no header", None, 403),
])
def test_move_project_refused(client, target, body, status):  # 020 AC31
    pid = connect(client)["id"]
    work = client.post("/api/workspaces", json={"name": "work"}, headers=H).json()["id"]
    url = f"/api/projects/{999 if target == 'unknown project' else pid}"
    r = client.patch(url, json={"workspace_id": work} if body is None else body,
                     headers={} if target == "no header" else H)
    assert r.status_code == status, r.text
    assert r.headers["content-type"] == "application/json"
    if status == 404:
        assert r.json() == {"detail": "Not Found"}
    assert project_workspace(pid) == workspace_id("personal")


# --- GET and PUT /api/projects/{id}/context (033) ---------------------------------


def put_context(client, pid, body, headers=H):
    return client.put(f"/api/projects/{pid}/context", json=body, headers=headers)


def stored_context(pid):
    return sql("SELECT context_md FROM projects WHERE id = ?", (pid,))[0][0]


def test_context_fresh(client):  # 033 AC1
    pid = connect(client)["id"]
    r = client.get(f"/api/projects/{pid}/context")
    assert (r.status_code, r.json()) == (200, {"context_md": "", "context_html": "", "bytes": 0, "max_bytes": 16384})


def test_context_put_then_get(client):  # 033 AC3
    pid = connect(client)["id"]
    text = "# Stack\n- Python 3.12\n"
    r = put_context(client, pid, {"context_md": text})
    assert r.status_code == 200
    assert r.json() == {"context_md": text, "context_html": render(text), "bytes": len(text.encode()),
                        "max_bytes": 16384}
    assert client.get(f"/api/projects/{pid}/context").json() == r.json()


def test_context_html_escapes_raw_html(client):  # 033 AC4
    pid = connect(client)["id"]
    put_context(client, pid, {"context_md": "<script>alert(1)</script>"})
    html = client.get(f"/api/projects/{pid}/context").json()["context_html"]
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


@pytest.mark.parametrize("text", ["x" * 16384, "é" * 8192])
def test_context_at_cap(client, text):  # 033 AC5
    pid = connect(client)["id"]
    r = put_context(client, pid, {"context_md": text})
    assert (r.status_code, r.json()["bytes"]) == (200, 16384)
    assert stored_context(pid) == text


@pytest.mark.parametrize("text", [
    "x" * 16385,  # 033 AC6
    "é" * 8193,  # 033 AC7: 8193 characters, 16386 bytes
])
def test_context_over_cap(client, text):  # 033 AC6, AC7
    pid = connect(client)["id"]
    put_context(client, pid, {"context_md": "keep"})
    r = put_context(client, pid, {"context_md": text})
    assert (r.status_code, r.json()) == (413, {"detail": "context over 16 KB"})
    assert stored_context(pid) == "keep"


def test_context_cleared(client):  # 033 AC8
    pid = connect(client)["id"]
    put_context(client, pid, {"context_md": "# Stack\n"})
    r = put_context(client, pid, {"context_md": ""})
    assert (r.status_code, r.json()["context_md"]) == (200, "")
    got = client.get(f"/api/projects/{pid}/context").json()
    assert (got["context_md"], got["bytes"]) == ("", 0)


def test_context_unknown_project(client):  # 033 AC9
    for r in (client.get("/api/projects/99/context"), put_context(client, 99, {"context_md": "x"})):
        assert (r.status_code, r.json()) == (404, {"detail": "Project #99 not found"})


def test_context_needs_fctl_header(client):  # 033 AC10
    pid = connect(client)["id"]
    put_context(client, pid, {"context_md": "keep"})
    assert put_context(client, pid, {"context_md": "x"}, headers={}).status_code == 403
    assert stored_context(pid) == "keep"


@pytest.mark.parametrize("body", [{}, {"context_md": 123}, {"context_md": None}, {"context_md": ["x"]}])
def test_context_invalid_body(client, body):  # 033 AC11
    pid = connect(client)["id"]
    put_context(client, pid, {"context_md": "keep"})
    assert put_context(client, pid, body).status_code == 422
    assert stored_context(pid) == "keep"


def test_connect_rerun_keeps_context(client):  # 033 AC12
    pid = connect(client)["id"]
    put_context(client, pid, {"context_md": "# Stack\n"})
    connect(client, name="api2")
    assert stored_context(pid) == "# Stack\n"
