import re
from datetime import datetime
from pathlib import Path

import pytest
from conftest import git, sql

import claude_factories
from claude_factories import db

PKG = Path(claude_factories.__file__).parent
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


def add_task(project_id, status, updated_at="2026-01-01T00:00:00Z"):
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
        " VALUES (?, 't', ?, 1, ?, ?)", (project_id, status, updated_at, updated_at))


def table(html):
    """The page's table as one {header: cell text} dict per body row."""
    rows = [[re.sub(r"<[^>]+>", "", cell).strip()
             for cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", tr, re.S)]
            for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S)]
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def commit_skill(repo):
    (repo / SKILL).parent.mkdir(parents=True)
    (repo / SKILL).write_text("# factory\n")
    git(repo, "add", SKILL)
    git(repo, "commit", "-q", "-m", "Add factory")


def local(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")


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


# --- Workspace page ----------------------------------------------------------------

HEADERS = ["Project", "Path", "Backlog", "In progress", "Review", "Done", "Factory", "Last activity"]


def test_workspace_page(client):  # AC16
    zeta = connect(client, path="/z", name="zeta")["id"]
    alpha = connect(client, path="/a", name="alpha")["id"]
    connect(client, path="/o", name="other", workspace="work")
    r = client.get(f"/workspaces/{workspace_id('personal')}")
    assert r.status_code == 200
    assert r.template.name == "workspace.html"
    assert (PKG / "templates" / "workspace.html").read_text().startswith('{% extends "base.html" %}')
    assert "<h1>personal</h1>" in r.text
    assert '<a href="/">' in r.text
    rows = table(r.text)
    assert [list(row) for row in rows] == [HEADERS, HEADERS]
    assert [(row["Project"], row["Path"]) for row in rows] == [("alpha", "/a"), ("zeta", "/z")]
    assert f'<a href="/projects/{alpha}">alpha</a>' in r.text
    assert f'<a href="/projects/{zeta}">zeta</a>' in r.text


def test_workspace_page_counts(client):  # AC17
    a = connect(client, path="/a", name="a")["id"]
    b = connect(client, path="/b", name="b")["id"]
    for status in ["backlog", "backlog", "review", "done"]:
        add_task(a, status)
    add_task(b, "backlog")
    rows = table(client.get(f"/workspaces/{workspace_id('personal')}").text)
    counts = [{k: row[k] for k in ["Backlog", "In progress", "Review", "Done"]} for row in rows]
    assert counts == [{"Backlog": "2", "In progress": "0", "Review": "1", "Done": "1"},
                      {"Backlog": "1", "In progress": "0", "Review": "0", "Done": "0"}]


def test_workspace_page_factory_state(client, repo):  # AC18
    commit_skill(repo)
    connect(client, path=str(repo), name="a-ready")
    connect(client, path="/nowhere", name="b-none")
    rows = table(client.get(f"/workspaces/{workspace_id('personal')}").text)
    assert [(row["Project"], row["Factory"]) for row in rows] == [("a-ready", "ready"),
                                                                 ("b-none", "none")]


def test_workspace_page_last_activity(client):  # AC19
    tasks_later = connect(client, path="/a", name="a")["id"]
    created_later = connect(client, path="/b", name="b")["id"]
    no_tasks = connect(client, path="/c", name="c")["id"]
    for pid, created in [(tasks_later, "2026-01-01T00:00:00Z"),
                         (created_later, "2026-05-05T08:09:00Z"),
                         (no_tasks, "2026-02-02T10:20:00Z")]:
        sql("UPDATE projects SET created_at = ? WHERE id = ?", (created, pid))
    add_task(tasks_later, "backlog", "2026-03-04T05:06:07Z")
    add_task(tasks_later, "done", "2025-12-31T00:00:00Z")
    add_task(created_later, "done", "2026-01-01T00:00:00Z")
    html = client.get(f"/workspaces/{workspace_id('personal')}").text
    expected = ["2026-03-04T05:06:07Z", "2026-05-05T08:09:00Z", "2026-02-02T10:20:00Z"]
    assert [row["Last activity"] for row in table(html)] == [local(iso) for iso in expected]
    for iso in expected:
        assert f'<time datetime="{iso}">{local(iso)}</time>' in html


def test_workspace_page_empty(client):  # AC20
    sql("INSERT INTO workspaces (name, created_at) VALUES ('empty', ?)", (db.now(),))
    r = client.get(f"/workspaces/{workspace_id('empty')}")
    assert r.status_code == 200
    assert "<table" not in r.text
    assert ("No projects yet. Run <code>fctl connect --workspace empty</code> inside a repo."
            in r.text)


def test_workspace_page_unknown(client):  # AC21
    assert client.get("/workspaces/999").status_code == 404


def test_workspace_page_has_new_workspace_form(client):  # AC22
    connect(client)
    html = client.get(f"/workspaces/{workspace_id('personal')}").text
    [form] = re.findall(r'<form hx-post="/workspaces">(.*?)</form>', html, re.S)
    [field] = re.findall(r"<input\b[^>]*>", form)
    for attr in ['type="text"', 'name="name"', " required "]:
        assert attr in field
    assert "<button>+ Workspace</button>" in form


# --- + Workspace -------------------------------------------------------------------


def test_new_workspace(client):  # AC23
    r = client.post("/workspaces", data={"name": "work"}, headers=H)
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == f"/workspaces/{workspace_id('work')}"


def test_new_workspace_existing_name(client):  # AC24
    connect(client)
    r = client.post("/workspaces", data={"name": "personal"}, headers=H)
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == f"/workspaces/{workspace_id('personal')}"
    assert sql("SELECT COUNT(*) FROM workspaces") == [(1,)]


@pytest.mark.parametrize("name", ["", "   "])
def test_new_workspace_blank(client, name):  # AC25
    r = client.post("/workspaces", data={"name": name}, headers=H)
    assert r.status_code == 422
    assert sql("SELECT COUNT(*) FROM workspaces") == [(0,)]


# --- Project page and moving -----------------------------------------------------


def test_project_page(client):  # AC26
    pid = connect(client)["id"]
    connect(client, path="/other", workspace="work")
    personal, work = workspace_id("personal"), workspace_id("work")
    r = client.get(f"/projects/{pid}")
    assert r.status_code == 200
    assert r.template.name == "project.html"
    assert (PKG / "templates" / "project.html").read_text().startswith('{% extends "base.html" %}')
    html = r.text
    assert f'<h1>api · <a href="/workspaces/{personal}">personal</a></h1>' in html
    assert "/code/api" in html
    [form] = re.findall(rf'<form hx-post="/projects/{pid}/workspace">(.*?)</form>', html, re.S)
    [select] = re.findall(r'<select name="workspace_id">(.*?)</select>', form, re.S)
    assert re.findall(r"<option .*?</option>", select) == [
        f'<option value="{personal}" selected>personal</option>',
        f'<option value="{work}">work</option>',
    ]


def test_project_page_unknown(client):  # AC27
    assert client.get("/projects/999").status_code == 404


def test_move_project(client):  # AC28
    pid = connect(client)["id"]
    connect(client, path="/other", name="other", workspace="work")
    personal, work = workspace_id("personal"), workspace_id("work")
    r = client.post(f"/projects/{pid}/workspace", data={"workspace_id": str(work)}, headers=H)
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == f"/projects/{pid}"
    assert project_workspace(pid) == work
    assert [row["Project"] for row in table(client.get(f"/workspaces/{work}").text)] == ["api", "other"]
    assert "No projects yet." in client.get(f"/workspaces/{personal}").text


@pytest.mark.parametrize("target, value, status", [
    ("unknown project", "work", 404),
    ("unknown workspace", "999", 404),
    ("non-integer", "abc", 422),
])
def test_move_project_invalid(client, target, value, status):  # AC29
    pid = connect(client)["id"]
    connect(client, path="/other", workspace="work")
    personal = workspace_id("personal")
    url = "/projects/999/workspace" if target == "unknown project" else f"/projects/{pid}/workspace"
    ws = str(workspace_id("work")) if value == "work" else value
    r = client.post(url, data={"workspace_id": ws}, headers=H)
    assert r.status_code == status
    assert project_workspace(pid) == personal


# --- Index -------------------------------------------------------------------------


def test_index_lists_workspaces(client):  # AC30
    assert "No projects yet." in client.get("/").text
    connect(client, path="/a")
    connect(client, path="/b")
    connect(client, path="/c", workspace="work")
    html = client.get("/").text
    assert "No projects yet." not in html
    for name, count in [("personal", "2 projects"), ("work", "1 project")]:
        assert re.search(rf'<a href="/workspaces/{workspace_id(name)}">{name}</a>\s*'
                         rf'<span class="muted">{count}</span>', html)
