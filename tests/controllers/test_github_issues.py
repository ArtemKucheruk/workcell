"""108: POST /api/projects/{id}/github-issues/sync, the Settings page's `github_repo`/`github_hint`, and the task
page's `issue_url`, against 093's fake `gh` (its `issue list` branch answers from the state's `issues`)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import git, sql

from claude_factories import config

from .test_pull_requests import LOGGED_OUT, between, gh, gh_missing  # noqa: F401 (gh is the fixture)

H = {"X-Requested-By": "fctl"}
URL = "https://github.com/o/r.git"
DOCKER = " (the backend image has no gh login; sync issues from the app on your host)"
T = "2026-01-01T00:00:00Z"
ARGV = ["issue", "list", "--repo", "o/r", "--state", "open", "--json", "number,title,body,url", "--limit", "200"]


def issue(n, title=None, body=None, labels=()):
    return {"number": n, "title": title or f"Issue {n}", "body": f"Body {n}\n" if body is None else body,
            "url": f"https://github.com/o/r/issues/{n}", "labels": list(labels)}


ISSUES = [issue(3), issue(2, labels=["bug"]), issue(1, body="")]  # newest first, as gh lists them


@pytest.fixture
def setup(repo, client, gh):
    """`repo` with origin github.com/o/r, connected as a project, and gh listing ISSUES."""
    git(repo, "remote", "add", "origin", URL)
    r = client.post("/api/projects/connect", headers=H, json={
        "path": str(repo), "workspace": "w", "name": "r", "default_branch": "main", "remote_url": URL})
    assert r.status_code == 200, r.text
    gh.set(issues=ISSUES, probe=str(config.data_dir() / "factory.db"))
    return SimpleNamespace(repo=repo, project=r.json()["id"])


def sync(client, project, headers=H):
    return client.post(f"/api/projects/{project}/github-issues/sync", headers=headers, json={})


def synced(client, project) -> dict:
    r = sync(client, project)
    assert r.status_code == 200, r.text
    return r.json()


def refused(r, status=409) -> str:
    assert r.status_code == status, r.text
    return r.json()["detail"]


def tasks() -> dict[str, dict]:
    """import_key → the task row's fields a sync could touch."""
    rows = sql("SELECT import_key, id, title, description_md, status, position, created_at, updated_at,"
               " (SELECT COUNT(*) FROM events WHERE task_id = tasks.id) FROM tasks WHERE import_key IS NOT NULL")
    keys = ("id", "title", "description_md", "status", "position", "created_at", "updated_at", "events")
    return {r[0]: dict(zip(keys, r[1:])) for r in rows}


def count() -> int:
    return sql("SELECT COUNT(*) FROM tasks")[0][0]


def aged():
    sql("UPDATE tasks SET created_at = ?, updated_at = ?", (T, T))
    sql("UPDATE events SET created_at = ?", (T,))


# --- Refusals (AC6–AC9, AC12, AC18) ----------------------------------------------------------


def test_unknown_project(client, gh):  # AC6
    assert refused(sync(client, 99), 404) == "Project #99 not found"
    assert gh.calls() == []


def test_needs_header(client, setup, gh):  # §4.5
    assert refused(sync(client, setup.project, {}), 403) == "X-Requested-By: fctl header required"
    assert gh.calls() == []


def test_no_origin(client, setup, gh):  # AC7
    git(setup.repo, "remote", "remove", "origin")
    assert refused(sync(client, setup.project)) == (
        f"{setup.repo} has no origin remote; add one with git remote add origin …")
    assert gh.calls() == []


def test_origin_not_github(client, setup, gh):  # AC7, Q3
    git(setup.repo, "remote", "set-url", "origin", "git@gitlab.com:o/r.git")
    assert refused(sync(client, setup.project)) == (
        "origin isn't on GitHub (gitlab.com); GitHub issues sync needs a github.com origin")
    assert gh.calls() == []


def test_gh_missing(client, tmp_path, monkeypatch, setup, gh):  # AC8
    gh_missing(tmp_path, monkeypatch)
    assert refused(sync(client, setup.project)) == "gh is not installed: install GitHub CLI, then run gh auth login"
    monkeypatch.setenv("FCTL_IN_DOCKER", "1")
    assert refused(sync(client, setup.project)) == (
        f"gh is not installed: install GitHub CLI, then run gh auth login{DOCKER}")
    assert count() == 0


def test_gh_logged_out(client, monkeypatch, setup, gh):  # AC9
    gh.set(auth=False)
    assert refused(sync(client, setup.project)) == f"gh is not logged in: run gh auth login. {LOGGED_OUT}"
    assert gh.calls() == [["auth", "status", "--hostname", "github.com"]]
    monkeypatch.setenv("FCTL_IN_DOCKER", "1")
    assert refused(sync(client, setup.project)) == f"gh is not logged in: run gh auth login. {LOGGED_OUT}{DOCKER}"
    assert count() == 0


def test_issue_list_fails(client, setup, gh):  # AC12
    gh.set(issue_error="HTTP 404: Not Found (https://api.github.com/repos/o/r)\nsecond line")
    assert refused(sync(client, setup.project)) == "HTTP 404: Not Found (https://api.github.com/repos/o/r)"
    assert count() == 0


@pytest.mark.parametrize("output, shown", [("oops\nmore", "oops"), ("", "nothing"), ('{"a": 1}', '{"a": 1}')])
def test_issue_list_no_json(client, setup, gh, output, shown):  # AC12
    gh.set(issue_output=output)
    assert refused(sync(client, setup.project), 500) == f"gh issue list printed no JSON: {shown}"
    assert count() == 0


def test_key_in_other_project(client, tmp_path, setup, gh):  # AC18, 031 Q11
    r = client.post("/api/projects/connect", headers=H, json={
        "path": str(tmp_path / "other"), "workspace": "w", "name": "other", "default_branch": "main"})
    other = r.json()["id"]
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at, import_key)"
        " VALUES (?, 'x', 'backlog', 1, ?, ?, 'github:o/r#2')", (other, T, T))
    assert refused(sync(client, setup.project)) == f"github:o/r#2 is imported in project #{other}"
    assert count() == 1  # issues #1 and #3 weren't written either


# --- The gh call (AC10, AC11, AC19) ----------------------------------------------------------


def test_argv(client, setup, gh):  # AC10
    synced(client, setup.project)
    assert gh.made("issue") == [ARGV]
    assert [c for c in gh.calls() if c[0] == "issue"] == [ARGV]
    prompts = [json.loads(line)["prompt"] for line in gh.log.read_text().splitlines()]
    assert set(prompts) == {"1"}


def test_label(client, setup, gh):  # AC11, Q10
    client.patch(f"/api/projects/{setup.project}", headers=H, json={"github_label": "bug"})
    assert synced(client, setup.project) == {"new": 1, "updated": 0, "skipped": 0}
    assert gh.made("issue") == [ARGV + ["--label", "bug"]]
    assert list(tasks()) == ["github:o/r#2"]


def test_no_write_lock_while_gh_runs(client, setup, gh):  # AC19
    synced(client, setup.project)
    assert gh.state()["probed"] == ["free"]


# --- Tasks (AC13–AC17, AC20) -----------------------------------------------------------------


def test_first_sync(client, setup, gh):  # AC13, AC14, Q5
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
        " VALUES (?, 'mine', 'backlog', 5, ?, ?)", (setup.project, T, T))
    assert synced(client, setup.project) == {"new": 3, "updated": 0, "skipped": 0}
    found = tasks()
    assert list(found) == ["github:o/r#1", "github:o/r#2", "github:o/r#3"]  # ascending number, by id
    assert [t["position"] for t in found.values()] == [6, 7, 8]  # each at the bottom of Backlog
    one, three = found["github:o/r#1"], found["github:o/r#3"]
    assert (three["title"], three["description_md"], three["status"]) == (
        "Issue 3", "Body 3\n\nGitHub issue: https://github.com/o/r/issues/3", "backlog")
    assert one["description_md"] == "GitHub issue: https://github.com/o/r/issues/1"
    for t in found.values():
        events = sql("SELECT actor, from_status, to_status, stage FROM events WHERE task_id = ?", (t["id"],))
        assert events == [("app", None, "backlog", None)]
    assert sql("SELECT project_id, stage, branch, spec_md FROM tasks WHERE import_key = 'github:o/r#2'") == [
        (setup.project, None, None, None)]


def test_resync_idempotent(client, setup, gh):  # AC15, Q4
    synced(client, setup.project)
    aged()
    before = tasks()
    assert synced(client, setup.project) == {"new": 0, "updated": 0, "skipped": 3}
    assert tasks() == before


def test_resync_updates_backlog(client, setup, gh):  # AC16
    synced(client, setup.project)
    aged()
    before = tasks()
    gh.set(issues=[issue(3, title="Issue 3, renamed"), issue(2, body="New body", labels=["bug"]), issue(1, body="")])
    assert synced(client, setup.project) == {"new": 0, "updated": 2, "skipped": 1}
    after = tasks()
    three, two = after["github:o/r#3"], after["github:o/r#2"]
    assert (three["title"], three["description_md"]) == ("Issue 3, renamed", before["github:o/r#3"]["description_md"])
    assert (two["title"], two["description_md"]) == (
        "Issue 2", "New body\n\nGitHub issue: https://github.com/o/r/issues/2")
    for k in ("github:o/r#3", "github:o/r#2"):
        assert (after[k]["position"], after[k]["events"], after[k]["status"]) == (
            before[k]["position"], before[k]["events"], "backlog")
        assert after[k]["updated_at"] != T
    assert after["github:o/r#1"] == before["github:o/r#1"]


def start_run(tid):
    sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at) VALUES (?, 's', 'failed', 'l', ?)",
        (tid, T))


def start_round(tid):
    sql("INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, 1, 'initial', 'x', ?)", (tid, T))


def start_move(tid):
    sql("UPDATE tasks SET status = 'in_progress', stage = 'spec' WHERE id = ?", (tid,))


@pytest.mark.parametrize("start", [start_run, start_round, start_move])
def test_started_untouched(client, setup, gh, start):  # AC17
    synced(client, setup.project)
    start(tasks()["github:o/r#3"]["id"])
    aged()
    before = tasks()
    gh.set(issues=[issue(3, title="Changed", body="Changed"), *ISSUES[1:]])
    assert synced(client, setup.project) == {"new": 0, "updated": 0, "skipped": 3}
    assert tasks() == before


def test_closed_issue_left_alone(client, setup, gh):  # AC20
    synced(client, setup.project)
    aged()
    before = tasks()
    gh.set(issues=[issue(4), ISSUES[0], ISSUES[2]])
    assert synced(client, setup.project) == {"new": 1, "updated": 0, "skipped": 2}
    assert tasks()["github:o/r#2"] == before["github:o/r#2"]


def test_deleted_task_comes_back(client, setup, gh):  # Q9
    synced(client, setup.project)
    tid = tasks()["github:o/r#2"]["id"]
    assert client.delete(f"/api/tasks/{tid}", headers=H).status_code in (200, 204)
    assert synced(client, setup.project) == {"new": 1, "updated": 0, "skipped": 2}
    assert tasks()["github:o/r#2"]["id"] != tid


# --- Pages (AC5, AC22) -----------------------------------------------------------------------


@pytest.mark.parametrize("remote, repo, hint", [
    (URL, "o/r", None),
    (None, None, "no origin remote"),
    ("git@gitlab.com:o/r.git", None, "gitlab.com"),
])
def test_board_github(client, gh, remote, repo, hint):  # AC5, Q2
    r = client.post("/api/projects/connect", headers=H, json={
        "path": "/code/api", "workspace": "w", "name": "api", "default_branch": "main", "remote_url": remote})
    project = client.get(f"/api/pages/projects/{r.json()['id']}").json()["project"]
    assert (project["github_label"], project["github_repo"]) == (None, repo)
    assert project["github_hint"] is None if hint is None else hint in project["github_hint"]
    assert gh.calls() == []


def test_board_github_label(client, setup, gh):  # AC5
    client.patch(f"/api/projects/{setup.project}", headers=H, json={"github_label": "bug"})
    assert client.get(f"/api/pages/projects/{setup.project}").json()["project"]["github_label"] == "bug"


def test_task_issue_url(client, setup, gh):  # AC22
    synced(client, setup.project)
    tid = tasks()["github:o/r#2"]["id"]
    assert client.get(f"/api/pages/tasks/{tid}").json()["task"]["issue_url"] == "https://github.com/o/r/issues/2"
    sql("UPDATE tasks SET import_key = 'factory:12-x' WHERE id = ?", (tid,))
    assert client.get(f"/api/pages/tasks/{tid}").json()["task"]["issue_url"] is None


# --- Docs (AC31) -----------------------------------------------------------------------------

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_docs():  # AC31
    mvp = (DOCS / "MVP.md").read_text()
    assert "gh issue list" in between(mvp, "### Non-goals", "\n## ")
    assert "GitHub issues sync" in mvp[mvp.index("## 9."):]
    api = (DOCS / "data-model-and-api.md").read_text()
    schema = between(api, "### 5.1", "### 5.2")
    assert "github_label TEXT" in schema and "github:<owner>/<repo>#<n>" in schema
    endpoints = api[api.index("### 6.1"):]
    for text in ("POST /api/projects/12/github-issues/sync", '"github_label"', "github_repo", "github_hint",
                 "issue_url"):
        assert text in endpoints, text
    ui = (DOCS / "ui.md").read_text()
    settings = between(ui, "12. **Project settings**", "13. **")
    assert "**GitHub issues**" in settings and "**Sync now**" in settings and "Synced GitHub issues:" in settings
    assert "Issue #12" in between(ui, "4. **Task detail**", "5. **Code review**")
