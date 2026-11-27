import os
import re
from pathlib import Path

import pytest
from conftest import git, sql

from workcell.lib.markdown import render
from workcell.server.deps import get_git

from .test_tasks import OWNED, add_run, add_task, dump, full_task

H = {"X-Requested-By": "fctl"}
SKILL = ".claude/skills/factory/SKILL.md"
READY = "# factory\n\n1. spec → `fctl stage <id> spec`.\n"  # 059: the app's template calls fctl stage
LEGACY = "# factory\n"  # 059: the file-based bootstrap loop doesn't
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


def commit_skill(repo, text=READY):
    (repo / SKILL).parent.mkdir(parents=True, exist_ok=True)
    (repo / SKILL).write_text(text)
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


def create_factory(client, path, overwrite=False):
    pid = connect(client, path=str(path))["id"]
    r = client.post(f"/api/projects/{pid}/factory", json={"overwrite": overwrite}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_factory_ready(client, repo, tmp_path):  # AC12, 059 BE2
    commit_skill(repo)
    assert factory(client, repo) == "ready"
    templated = tmp_path / "templated"  # the app's own template, committed
    git(tmp_path, "init", "-q", "-b", "main", str(templated))
    create_factory(client, templated)
    git(templated, "add", "-A")
    git(templated, "commit", "-q", "-m", "Add factory")
    assert factory(client, templated) == "ready"


def test_factory_legacy(client, repo):  # 059 BE1
    commit_skill(repo, LEGACY)
    assert factory(client, repo) == "legacy"


@pytest.mark.parametrize("how", ["untracked", "other branch"])
def test_factory_uncommitted(client, repo, how):  # AC13, 059 BE3
    if how == "other branch":
        git(repo, "switch", "-q", "-c", "other")
        commit_skill(repo, LEGACY)
    else:
        (repo / SKILL).parent.mkdir(parents=True)
        (repo / SKILL).write_text(READY)
    assert (repo / SKILL).is_file()
    assert factory(client, repo) == "uncommitted"


@pytest.mark.parametrize("how", ["nothing", "gone", "directory"])
def test_factory_none(client, repo, tmp_path, how):  # AC14, AC15, 059 BE4, Q5
    if how == "directory":  # SKILL.md is a tree on main, not a blob: not committed, and not a file on disk
        (repo / SKILL).mkdir(parents=True)
        (repo / SKILL / "x.md").write_text(READY)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "dir")
    assert factory(client, tmp_path / "gone" if how == "gone" else repo) == "none"


def test_factory_legacy_until_committed(client, repo):  # 059 BE5, Q2
    commit_skill(repo, LEGACY)
    assert SKILL in create_factory(client, repo, overwrite=True)["written"]
    assert "fctl stage" in (repo / SKILL).read_text()
    assert factory(client, repo) == "legacy"


# --- 034: one transaction per handler call, adapters through Depends --------------------


def test_connect_is_one_transaction(client):  # 034 AC13
    raw = '{"path": "/code/api", "workspace": "fresh", "name": "\\ud800", "default_branch": "main"}'
    r = client.post("/api/projects/connect", content=raw, headers=H | {"Content-Type": "application/json"})
    assert (r.status_code, r.json()) == (422, {"detail": "text must not contain lone surrogates"})
    assert sql("SELECT (SELECT COUNT(*) FROM workspaces), (SELECT COUNT(*) FROM projects)") == [(0, 0)]


class CommittedGit:
    """A git adapter whose every committed blob is the app's template (059: factory_state reads SKILL.md)."""

    def blob(self, root, oid):
        return READY.encode(), None


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
    assert (r.status_code, r.json()) == (200, {"id": pid, "workspace_id": work, "name": "api",
                                              "test_cmd": "pytest -q", "github_label": None,
                                              **NO_PLANE})  # 049 BE9: the whole project
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


# --- PATCH name / test_cmd (049) ---------------------------------------------------


def stored(pid):
    """Every column a PATCH could touch, or must not."""
    return sql("SELECT workspace_id, name, path, remote_url, default_branch, test_cmd, context_md, factory_version,"
               " created_at FROM projects WHERE id = ?", (pid,))[0]


def patch(client, pid, body):
    return client.patch(f"/api/projects/{pid}", json=body, headers=H)


def test_rename_project(client):  # 049 BE1
    pid = connect(client)["id"]
    client.put(f"/api/projects/{pid}/context", json={"context_md": "# Stack\n"}, headers=H)
    before = stored(pid)
    r = patch(client, pid, {"name": "  api2  "})
    assert (r.status_code, r.json()) == (200, {"id": pid, "workspace_id": before[0], "name": "api2",
                                              "test_cmd": "pytest -q", "github_label": None, **NO_PLANE})
    assert stored(pid) == (before[0], "api2", *before[2:])


def test_patch_test_cmd(client):  # 049 BE2
    pid = connect(client)["id"]
    r = patch(client, pid, {"test_cmd": "  make test "})
    assert (r.status_code, r.json()["test_cmd"]) == (200, "make test")
    assert stored(pid)[5] == "make test"
    r = patch(client, pid, {"test_cmd": "   "})
    assert (r.status_code, r.json()["test_cmd"]) == (200, None)
    assert stored(pid)[5] is None


def test_patch_all_three(client):  # 049 BE3
    pid = connect(client)["id"]
    work = client.post("/api/workspaces", json={"name": "work"}, headers=H).json()["id"]
    r = patch(client, pid, {"workspace_id": work, "name": "x", "test_cmd": "y"})
    assert (r.status_code, r.json()) == (200, {"id": pid, "workspace_id": work, "name": "x", "test_cmd": "y",
                                              "github_label": None, **NO_PLANE})
    assert stored(pid)[:2] == (work, "x")
    assert stored(pid)[5] == "y"


def test_rename_project_blank(client):  # 049 BE4
    pid = connect(client)["id"]
    before = stored(pid)
    r = patch(client, pid, {"name": "   "})
    assert (r.status_code, r.json()) == (422, {"detail": "name must not be blank"})
    assert stored(pid) == before


@pytest.mark.parametrize("body", [{"name": None}, {"test_cmd": None}, {"workspace_id": None}, {"name": 3}])
def test_patch_project_null_or_wrong_type(client, body):  # 049 BE5
    pid = connect(client)["id"]
    before = stored(pid)
    r = patch(client, pid, body)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)
    assert stored(pid) == before


@pytest.mark.parametrize("body", [{}, {"foo": 1}])
def test_patch_project_nothing_sent(client, body):  # 049 BE6
    pid = connect(client)["id"]
    before = stored(pid)
    r = patch(client, pid, body)
    assert (r.status_code, r.json()) == (422, {"detail": "send at least one of: workspace_id, name, test_cmd,"
                                                         " github_label, plane_api_url, plane_workspace,"
                                                         " plane_project_id, plane_api_key,"
                                                         " plane_mark_done"})  # 108 AC4, 109 Q2
    assert stored(pid) == before


def label(pid):
    return sql("SELECT github_label FROM projects WHERE id = ?", (pid,))[0][0]


def test_patch_github_label(client):  # 108 AC2
    pid = connect(client)["id"]
    before = stored(pid)
    r = patch(client, pid, {"github_label": "  bug "})
    assert (r.status_code, r.json()["github_label"]) == (200, "bug")
    assert label(pid) == "bug" and stored(pid) == before


def test_patch_github_label_blank(client):  # 108 AC3
    pid = connect(client)["id"]
    patch(client, pid, {"github_label": "bug"})
    r = patch(client, pid, {"github_label": "  "})
    assert (r.status_code, r.json()["github_label"]) == (200, None)
    assert label(pid) is None


NO_PLANE = {"plane_api_url": None, "plane_workspace": None, "plane_project_id": None, "plane_mark_done": False,
            "plane_key_set": False}  # 109 AC4
SECRET = "plane_api_SECRET_1234567890"


def plane_row(pid):
    return sql("SELECT plane_api_url, plane_workspace, plane_project_id, plane_api_key, plane_mark_done FROM projects"
               " WHERE id = ?", (pid,))[0]


def test_patch_plane_settings(client):  # 109 AC2
    pid = connect(client)["id"]
    before = stored(pid)
    r = patch(client, pid, {"plane_api_url": " https://plane.example.com/// ", "plane_workspace": " acme ",
                            "plane_project_id": " p-1 ", "plane_api_key": f" {SECRET} ", "plane_mark_done": True,
                            "name": "api"})
    assert r.status_code == 200, r.text
    assert plane_row(pid) == ("https://plane.example.com", "acme", "p-1", SECRET, 1)
    assert stored(pid) == before
    assert {k: r.json()[k] for k in NO_PLANE} == {
        "plane_api_url": "https://plane.example.com", "plane_workspace": "acme", "plane_project_id": "p-1",
        "plane_mark_done": True, "plane_key_set": True}
    r = patch(client, pid, {"plane_workspace": "  ", "plane_api_url": "", "plane_mark_done": False})
    assert r.status_code == 200 and plane_row(pid) == (None, None, "p-1", SECRET, 0)  # blank stores NULL


@pytest.mark.parametrize("url", ["ftp://plane.example.com", "plane.example.com", "https://", "https://u:p@x.io",
                                 "https://x.io?a=1", "javascript:alert(1)", "https://x.io:99999"])
def test_patch_plane_url_refused(client, url):  # 109 AC3
    pid = connect(client)["id"]
    r = patch(client, pid, {"plane_api_url": url, "plane_workspace": "acme"})
    assert (r.status_code, r.json()) == (422, {"detail": "plane_api_url must be an http(s) URL like"
                                                         " https://api.plane.so"})
    assert plane_row(pid) == (None, None, None, None, 0)


def test_patch_plane_key_never_returned(client):  # 109 AC4
    pid = connect(client)["id"]
    r = patch(client, pid, {"plane_api_key": SECRET})
    assert SECRET not in r.text and "plane_api_key" not in r.json() and r.json()["plane_key_set"] is True
    page = client.get(f"/api/pages/projects/{pid}")
    assert page.status_code == 200 and SECRET not in page.text and "plane_api_key" not in page.json()["project"]
    assert page.json()["project"]["plane_key_set"] is True


def test_patch_plane_key_clear_and_keep(client):  # 109 AC5
    pid = connect(client)["id"]
    patch(client, pid, {"plane_api_key": SECRET})
    assert patch(client, pid, {"plane_workspace": "acme"}).json()["plane_key_set"] is True
    assert plane_row(pid)[3] == SECRET
    r = patch(client, pid, {"plane_api_key": ""})
    assert (r.status_code, r.json()["plane_key_set"]) == (200, False)
    assert plane_row(pid)[3] is None


def test_patch_project_unknown(client):  # 049 BE7
    r = patch(client, 999, {"name": "x"})
    assert (r.status_code, r.json()) == (404, {"detail": "Not Found"})
    pid = connect(client)["id"]
    before = stored(pid)
    r = patch(client, pid, {"workspace_id": 999, "name": "x"})
    assert (r.status_code, r.json()) == (404, {"detail": "Not Found"})
    assert stored(pid) == before


def test_patch_project_during_run(client):  # 049 BE8
    pid = connect(client)["id"]
    add_run(add_task(pid, "in_progress", stage="build"), "running")
    assert patch(client, pid, {"name": "api2"}).status_code == 200
    assert patch(client, pid, {"test_cmd": "make test"}).status_code == 200
    assert stored(pid)[1] == "api2"
    assert stored(pid)[5] == "make test"


# --- DELETE /api/projects/{id} (049) -----------------------------------------------


def delete(client, pid, headers=H):
    return client.delete(f"/api/projects/{pid}", headers=headers)


def test_delete_project(client):  # 049 BE14
    pid = connect(client)["id"]
    full_task(pid)
    full_task(pid)
    assert all(dump().values())  # every owned table has a row to remove
    ws = project_workspace(pid)
    r = delete(client, pid)
    assert r.status_code == 204
    assert r.content == b""
    assert sql("SELECT COUNT(*) FROM projects") == [(0,)]
    assert dump() == {table: [] for table in OWNED}
    assert client.get(f"/api/pages/projects/{pid}").status_code == 404
    assert sql("SELECT id FROM workspaces") == [(ws,)]


def test_delete_project_keeps_other_project(client):  # 049 BE15
    other = connect(client, path="/code/other")["id"]
    full_task(other)
    kept = dump()
    pid = connect(client)["id"]
    full_task(pid)
    assert delete(client, pid).status_code == 204
    assert dump() == kept
    assert sql("SELECT id FROM projects") == [(other,)]


def test_delete_project_refused_during_run(client):  # 049 BE16
    pid = connect(client)["id"]
    full_task(pid)
    task_id = full_task(pid)
    run_id = add_run(task_id, "running")
    kept = dump()
    r = delete(client, pid)
    assert (r.status_code, r.json()) == (409, {"detail": f"run #{run_id} active"})
    assert dump() == kept
    assert sql("SELECT id FROM projects") == [(pid,)]
    # Q6: a run in another project doesn't block
    sql("UPDATE runs SET status = 'stopped' WHERE id = ?", (run_id,))
    other = connect(client, path="/code/other")["id"]
    add_run(add_task(other), "running")
    assert delete(client, pid).status_code == 204


def test_delete_project_unknown(client):  # 049 BE17
    r = delete(client, 999)
    assert (r.status_code, r.json()) == (404, {"detail": "Project #999 not found"})


def test_delete_project_leaves_disk(client, repo):  # 049 BE18
    pid = connect(client, path=str(repo))["id"]
    task_id = full_task(pid)
    [(run_id, log, copy)] = sql("SELECT r.id, r.log_path, t.path FROM runs r JOIN transcripts t ON t.run_id = r.id"
                                " WHERE r.task_id = ?", (task_id,))
    home = Path(os.environ["FCTL_HOME"])
    assert Path(log) == home / "runs" / f"{run_id}.log"
    assert (home / "transcripts" / copy).parent == home / "transcripts" / str(run_id)
    assert delete(client, pid).status_code == 204
    assert (repo / ".git").is_dir()
    assert Path(log).is_file()
    assert (home / "transcripts" / copy).is_file()


def test_delete_project_needs_fctl_header(client):  # 049 BE22
    pid = connect(client)["id"]
    full_task(pid)
    kept = dump()
    assert delete(client, pid, headers={}).status_code == 403
    assert dump() == kept
    assert sql("SELECT id FROM projects") == [(pid,)]


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
