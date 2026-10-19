import ast
import os
import shlex
from datetime import UTC, datetime, timedelta

import pytest
from conftest import commit, git, sql, write
from controllers.test_runs import H, OLD, SKILL, add_task, connect, fake, project  # noqa: F401
from test_architecture import PKG, checked, fastapi_outside, sql_outside, wrong_edges

from claude_factories import db
from claude_factories.handlers import pages

PRO = '{"authMethod":"claude.ai","subscriptionType":"pro"}'
APP_PY = "diff --git a/app.py b/app.py\nnew file mode 100644\n--- /dev/null\n+++ b/app.py\n@@ -0,0 +1 @@\n+x = 1\n"
B_PY = "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1,2 +1,2 @@\n keep\n-x\n+y\n"
TASK_KEYS = {"id", "project_id", "project", "title", "status", "stage", "branch", "worktree_path",
             "description_md", "description_html", "spec_md", "spec_html"}
SUMMARY_KEYS = {"n", "trigger", "files", "additions", "deletions", "verdicts"}
CONSOLE = '{"authMethod":"console"}'
UNCOMMITTED = ("factory isn't committed on main: on main, run git add .claude/skills/factory .claude/agents"
               ' && git commit -m "Add factory"')
NONE = "factory isn't committed on main: Create factory on the project board, then commit it on main"
STRIPPED = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK")
STARTED = "2026-10-18T10:02:00Z"
WORKTREE = "/code/api/.claude/worktrees/12-x"
SAMPLE = """\
diff --git a/app/auth.py b/app/auth.py
index 1111111..2222222 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -41,3 +41,3 @@ def login():
     user = authenticate(form)
-    if not user:
+    if not user and limiter.hit(client_key(request)):
         return deny()
@@ -60,2 +60,3 @@ def logout():
     session.clear()
+    audit("logout")
     return ok()
diff --git a/app/limits.py b/app/limits.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/app/limits.py
@@ -0,0 +1,2 @@
+def client_key(request):
+    return request.client.host
\\ No newline at end of file
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..4444444
Binary files /dev/null and b/logo.png differ
diff --git a/old_name b/new_name
similarity index 100%
rename from old_name
rename to new_name
diff --git a/tests/test_limits.py b/tests/test_limits.py
deleted file mode 100644
index 5555555..0000000
--- a/tests/test_limits.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def test_old():
-    assert True
"""


# --- Shared DB-row helpers (026 Q3: test_run_control.py, test_reviews.py, and server/test_app.py import them) ---


def review_task(project_id, title="t", status="review", stage="human_review", description="", spec=None,
                branch=None, worktree=WORKTREE):
    return sql(
        "INSERT INTO tasks (project_id, title, description_md, spec_md, status, stage, position, branch,"
        " worktree_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?) RETURNING id",
        (project_id, title, description, spec, status, stage, branch, worktree, OLD, OLD),
    )[0][0]


def add_round(task_id, n, trigger="initial", files=((1, 0),), at=OLD):
    round_id = sql(
        "INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, ?, ?, 'abc1234', ?)"
        " RETURNING id", (task_id, n, trigger, at),
    )[0][0]
    for i, (additions, deletions) in enumerate(files):
        sql("INSERT INTO round_files (round_id, path, change, additions, deletions, patch)"
            " VALUES (?, ?, 'modified', ?, ?, '')", (round_id, f"f{i}.py", additions, deletions))
    return round_id


def add_verdict(round_id, reviewer, verdict, body_md="", at=OLD):
    sql("INSERT INTO verdicts (round_id, reviewer, verdict, body_md, created_at) VALUES (?, ?, ?, ?, ?)",
        (round_id, reviewer, verdict, body_md, at))


def add_comment(task_id, round_id, author, body_md, path=None, line=None, at=OLD, id=None):
    side = None if path is None else "new"
    sql("INSERT INTO comments (id, task_id, round_id, author, path, line, side, body_md, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (id, task_id, round_id, author, path, line, side, body_md, at))


def add_inline(task, round_id, author, path, line, side, body):
    sql("INSERT INTO comments (task_id, round_id, author, path, line, side, body_md, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (task, round_id, author, path, line, side, body, OLD))


def add_decision(task_id, round_id, actor, decision, body_md="", at=OLD):
    sql("INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, round_id, actor, decision, body_md, at))


def add_event(task_id, from_status, to_status, stage=None, at=OLD, id=None):
    sql("INSERT INTO events (id, task_id, actor, from_status, to_status, stage, created_at)"
        " VALUES (?, ?, 'app', ?, ?, ?, ?)", (id, task_id, from_status, to_status, stage, at))


def add_run(task_id, status, error=None, session="s", started=STARTED):
    return sql("INSERT INTO runs (task_id, session_id, status, error, log_path, started_at)"
               " VALUES (?, ?, ?, ?, 'l', ?) RETURNING id", (task_id, session, status, error, started))[0][0]


def submit(client, task, patch):
    """POST the patch as the task's next round; the new round's id."""
    r = client.post(f"/api/tasks/{task}/rounds", json={"base_sha": "abc1234", "patch": patch}, headers=H)
    assert r.status_code == 201, r.text
    return sql("SELECT id FROM rounds WHERE task_id = ? AND n = ?", (task, r.json()["round"]))[0][0]


# --- This file's own helpers ----------------------------------------------------------


def api(client, url, status=200):
    r = client.get(url)
    assert r.status_code == status, r.text
    assert r.headers["content-type"] == "application/json"
    return r.json()


def ws_id(name):
    return sql("SELECT id FROM workspaces WHERE name = ?", (name,))[0][0]


def cards(client, project_id):
    """{id: card} over every column of the board view-model."""
    return {c["id"]: c for column in api(client, f"/api/pages/projects/{project_id}")["columns"].values()
            for c in column}


def flags(card):
    return card["waiting"], card["escalated"], card["stalled"]


def ago(days):
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def done_task(project_id, days, rounds=0):
    """A task done `days` ago, with rounds 1..rounds."""
    tid = add_task(project_id, status="done")
    sql("UPDATE tasks SET done_at = ? WHERE id = ?", (ago(days), tid))
    for n in range(1, rounds + 1):
        add_round(tid, n)
    return tid


@pytest.fixture
def unready(client, tmp_path, fake):
    """unready("uncommitted" | "none") → a project on its own repo whose factory is in that state."""
    def make(state):
        path = tmp_path / f"repo-{state}"
        git(tmp_path, "init", "-q", "-b", "main", str(path))
        git(path, "commit", "-q", "--allow-empty", "-m", "init")
        if state == "uncommitted":
            write(path, {SKILL: "# factory\n"})
        return connect(client, path)
    return make


# --- GET /api/auth -------------------------------------------------------------------


def test_auth_claude_ai(client, fake):  # AC1
    fake(auth=PRO)
    assert api(client, "/api/auth") == {"auth_method": "claude.ai", "plan": "pro", "runs_enabled": True}


@pytest.mark.parametrize("auth", ['{"authMethod":"console"}', "not json"])
def test_auth_not_claude_ai(client, fake, auth):  # AC2
    fake(auth=auth)
    assert api(client, "/api/auth") == {"auth_method": None, "plan": None, "runs_enabled": False}


def test_auth_check_env_and_cwd(client, fake, monkeypatch):  # 026 AC12
    for name in STRIPPED:
        monkeypatch.setenv(name, "x")
    api(client, "/api/auth")
    seen = fake.recorded("auth")
    assert seen["argv"] == ["auth", "status"]
    assert not set(STRIPPED) & set(seen["env"])
    assert os.path.realpath(seen["cwd"]) == os.path.realpath(os.environ["FCTL_HOME"])


def test_auth_cached_60s(client, tmp_path, monkeypatch):  # AC3, 026 AC13
    calls = tmp_path / "auth-calls"
    claude = tmp_path / "bin" / "claude"  # appends a line per call, so every call counts
    claude.write_text(f"#!/bin/sh\necho x >> {shlex.quote(str(calls))}\necho {shlex.quote(PRO)}\n")
    clock = [1000.0]
    monkeypatch.setattr(pages, "monotonic", lambda: clock[0])
    count = lambda: len(calls.read_text().splitlines())  # noqa: E731
    assert api(client, "/api/auth")["plan"] == "pro"
    clock[0] += 59
    assert api(client, "/api/auth")["plan"] == "pro"
    assert count() == 1
    clock[0] += 2  # 61 s after the first
    assert api(client, "/api/auth")["plan"] == "pro"
    assert count() == 2


# --- GET /api/pages/dashboard --------------------------------------------------------


def test_dashboard(client, project):  # AC4
    other = client.post("/api/projects/connect", headers=H, json={
        "path": "/code/other", "workspace": "work", "name": "other", "default_branch": "main"}).json()["id"]
    for status in ("backlog", "in_progress", "review"):
        add_task(project, status=status)
    add_task(other)
    done = add_task(project, title="d", status="done")
    now = db.now()
    sql("UPDATE tasks SET done_at = ? WHERE id = ?", (now, done))
    add_round(done, 1)
    add_round(done, 2)
    page = api(client, "/api/pages/dashboard")
    assert list(page["tiles"].items()) == list(pages.TILES.items())
    assert list(page["counts"]) == list(pages.TILES)
    assert page["counts"]["backlog"] == 2 and page["counts"]["done"] == 1 and page["counts"]["runs_week"] == 0
    assert all(type(v) is int for v in page["counts"].values())
    assert (page["show"], page["listed"]) == ("", None)
    assert page["open_tasks"] == [
        {"id": ws_id("personal"), "name": "personal",
         "projects": [{"id": project, "name": "repo", "backlog": 1, "in_progress": 1, "review": 1}]},
        {"id": ws_id("work"), "name": "work",
         "projects": [{"id": other, "name": "other", "backlog": 1, "in_progress": 0, "review": 0}]},
    ]
    assert page["done"] == [{"id": done, "title": "d", "done_at": now, "project_id": project, "project": "repo",
                             "rounds": 2}]
    assert page["workspaces"] == [{"id": ws_id("personal"), "name": "personal", "projects": 1},
                                  {"id": ws_id("work"), "name": "work", "projects": 1}]


def test_dashboard_waiting(client, project):  # AC5
    add_task(project)
    waiting = add_task(project, title="w", status="review", stage="human_review")
    page = api(client, "/api/pages/dashboard?show=waiting")
    assert page["show"] == "waiting"
    assert page["listed"] == [{"id": waiting, "title": "w", "status": "review", "stage": "human_review",
                               "project_id": project, "project": "repo"}]


def test_dashboard_runs_week_and_bogus(client, project):  # AC6
    tid = add_task(project, title="r", status="in_progress")
    started = db.now()
    run = add_run(tid, "succeeded", started=started)
    page = api(client, "/api/pages/dashboard?show=runs_week")
    assert page["show"] == "runs_week"
    assert page["listed"] == [{"id": run, "status": "succeeded", "started_at": started, "task_id": tid,
                               "title": "r", "project_id": project, "project": "repo"}]
    page = api(client, "/api/pages/dashboard?show=bogus")
    assert (page["show"], page["listed"]) == ("", None)


def test_dashboard_escalated_and_running_counts(client, project):  # 026 AC17
    add_task(project, status="review", stage="escalated")
    add_task(project, status="review", stage="human_review")
    add_run(add_task(project, status="in_progress", stage="build"), "running")
    add_run(add_task(project, status="in_progress", stage="build"), "succeeded")
    add_run(add_task(project), "failed")
    counts = api(client, "/api/pages/dashboard")["counts"]
    assert (counts["escalated"], counts["running"]) == (1, 1)


def test_dashboard_week_windows(client, project):  # 026 AC18
    done_task(project, 6)
    done_task(project, 8)
    tid = add_task(project, status="in_progress", stage="build")
    for days in (0, 6, 8):
        add_run(tid, "succeeded", started=ago(days))
    counts = api(client, "/api/pages/dashboard")["counts"]
    assert (counts["done_week"], counts["runs_week"]) == (1, 2)


def test_dashboard_done_list(client, project):  # 026 AC19
    older, newer = done_task(project, 29, rounds=2), done_task(project, 3, rounds=1)
    done_task(project, 31, rounds=3)
    add_round(add_task(project, status="review", stage="human_review"), 1)
    done_task(project, 1)  # no rounds
    done = api(client, "/api/pages/dashboard")["done"]
    assert [(d["id"], d["rounds"]) for d in done] == [(newer, 1), (older, 2)]


# --- GET /api/pages/workspaces/{id} ---------------------------------------------------


def test_workspace(client, project, repo):  # AC7
    bare = client.post("/api/projects/connect", headers=H, json={
        "path": "/code/zzz", "workspace": "personal", "name": "zzz", "default_branch": "main"}).json()["id"]
    add_task(project, status="review", stage="human_review")
    created = dict(sql("SELECT id, created_at FROM projects"))
    page = api(client, f"/api/pages/workspaces/{ws_id('personal')}")
    assert page == {
        "workspace": {"id": ws_id("personal"), "name": "personal"},
        "projects": [
            {"id": project, "name": "repo", "path": str(repo), "backlog": 0, "in_progress": 0, "review": 1,
             "done": 0, "last_activity": created[project], "factory": "ready"},
            {"id": bare, "name": "zzz", "path": "/code/zzz", "backlog": 0, "in_progress": 0, "review": 0,
             "done": 0, "last_activity": created[bare], "factory": "none"},
        ],
    }


def test_workspace_last_activity(client):  # 026 AC20: 002 AC19's three cases
    ids = {}
    for name, created in (("a", "2026-01-01T00:00:00Z"), ("b", "2026-05-05T08:09:00Z"), ("c", "2026-02-02T10:20:00Z")):
        r = client.post("/api/projects/connect", headers=H, json={
            "path": f"/{name}", "workspace": "personal", "name": name, "default_branch": "main"})
        ids[name] = r.json()["id"]
        sql("UPDATE projects SET created_at = ? WHERE id = ?", (created, ids[name]))
    for name, updated in (("a", "2026-03-04T05:06:07Z"), ("a", "2025-12-31T00:00:00Z"), ("b", "2026-01-01T00:00:00Z")):
        sql("UPDATE tasks SET updated_at = ? WHERE id = ?", (updated, add_task(ids[name])))
    page = api(client, f"/api/pages/workspaces/{ws_id('personal')}")
    assert [(p["name"], p["last_activity"]) for p in page["projects"]] == [
        ("a", "2026-03-04T05:06:07Z"),  # a later task
        ("b", "2026-05-05T08:09:00Z"),  # a later creation
        ("c", "2026-02-02T10:20:00Z"),  # no tasks
    ]


# --- GET /api/pages/projects/{id} -----------------------------------------------------


def test_board(client, project, repo):  # AC8
    a, b, c = add_task(project, position=2.0), add_task(project, position=1.0), add_task(project, position=1.0)
    review = add_task(project, status="review", stage="human_review")
    page = api(client, f"/api/pages/projects/{project}")
    assert page["project"] == {"id": project, "name": "repo", "path": str(repo), "default_branch": "main",
                               "workspace_id": ws_id("personal"), "workspace": "personal"}
    assert (page["factory"], page["hint"], page["can_run"]) == ("ready", None, True)
    assert page["workspaces"] == [{"id": ws_id("personal"), "name": "personal", "projects": 1}]
    assert list(page["columns"]) == ["backlog", "in_progress", "review", "done"]
    assert [t["id"] for t in page["columns"]["backlog"]] == [b, c, a]
    assert [t["id"] for t in page["columns"]["review"]] == [review]
    assert page["columns"]["in_progress"] == page["columns"]["done"] == []


def test_board_card(client, project):  # AC9
    tid, bare = add_task(project, status="in_progress", stage="build"), add_task(project)
    rid = add_round(tid, 1, files=((5, 2),))
    add_verdict(rid, "security", "PASS")
    add_verdict(rid, "ux", "CHANGES")
    run = add_run(tid, "running")
    found = cards(client, project)
    assert found[tid] == {
        "id": tid, "title": "t", "status": "in_progress", "stage": "build", "position": 1.0, "round": 1,
        "verdicts": {"security": "PASS", "ux": "CHANGES", "ui": "pending", "code": "pending"},
        "additions": 5, "deletions": 2, "run": {"id": run, "status": "running"}, "started_at": STARTED,
        "waiting": False, "escalated": False, "stalled": False,
    }
    assert [found[bare][k] for k in ("round", "verdicts", "additions", "deletions", "run", "started_at")] == [None] * 6


def test_card_waiting(client, project):  # AC10
    tid = add_task(project, status="review", stage="human_review")
    assert flags(cards(client, project)[tid]) == (True, False, False)


def test_card_escalated(client, project):  # AC11
    tid = add_task(project, status="review", stage="escalated")
    assert flags(cards(client, project)[tid]) == (False, True, False)


def test_card_stalled(client, project):  # AC12
    failed, running = add_task(project, status="in_progress"), add_task(project, status="in_progress")
    backlog = add_task(project)
    add_run(failed, "failed", error="boom")
    add_run(running, "running")
    found = cards(client, project)
    assert found[failed]["stalled"] is True
    assert found[running]["stalled"] is False
    assert flags(found[backlog]) == (False, False, False)


@pytest.mark.parametrize("state, hint", [("uncommitted", UNCOMMITTED), ("none", NONE)])
def test_board_factory_not_ready(client, unready, state, hint):  # 026 AC14
    page = api(client, f"/api/pages/projects/{unready(state)}")
    assert (page["can_run"], page["hint"]) == (False, hint)


def test_board_console_auth(client, project, fake):  # 026 AC15
    fake(auth=CONSOLE)
    page = api(client, f"/api/pages/projects/{project}")
    assert (page["factory"], page["can_run"], page["hint"]) == ("ready", False, None)


# --- GET /api/pages/tasks/{id} --------------------------------------------------------


def test_task(client, project):  # AC13
    tid = review_task(project, title="T", description="Max **5**", spec="## Goal", branch="factory/1-t")
    bare = review_task(project, status="backlog", stage=None)
    page = api(client, f"/api/pages/tasks/{tid}")
    assert page["task"] == {
        "id": tid, "project_id": project, "project": "repo", "title": "T", "status": "review",
        "stage": "human_review", "branch": "factory/1-t", "worktree_path": "/code/api/.claude/worktrees/12-x",
        "description_md": "Max **5**", "description_html": "<p>Max <strong>5</strong></p>\n",
        "spec_md": "## Goal", "spec_html": "<h2>Goal</h2>\n",
    }
    assert (page["can_run"], page["hint"]) == (True, None)
    task = api(client, f"/api/pages/tasks/{bare}")["task"]
    assert (task["spec_md"], task["spec_html"]) == (None, "")


def test_task_rounds_approver_history(client, project):  # AC14
    tid = review_task(project)
    r1, r2 = add_round(tid, 1), add_round(tid, 2, trigger="agent", files=((3, 1), (2, 0)))
    sql("UPDATE rounds SET build_md = 'built **it**' WHERE id = ?", (r1,))
    add_verdict(r1, "security", "CHANGES", "fix *it*")
    add_verdict(r1, "code", "PASS")
    add_decision(tid, r1, "approver", "ESCALATE", "first")
    add_decision(tid, r2, "approver", "APPROVE", "ok **go**")
    add_decision(tid, r2, "me", "CHANGES_REQUESTED", "mine")
    add_event(tid, None, "backlog", at="2026-01-01T00:00:01Z")
    add_event(tid, "backlog", "in_progress", "build", at="2026-01-01T00:00:02Z")
    page = api(client, f"/api/pages/tasks/{tid}")
    assert page["rounds"] == [
        {"n": 1, "trigger": "initial", "files": 1, "additions": 1, "deletions": 0,
         "verdicts": {"security": "CHANGES", "ux": "pending", "ui": "pending", "code": "PASS"},
         "build_md": "built **it**", "build_html": "<p>built <strong>it</strong></p>\n",
         "posted": {"security": {"verdict": "CHANGES", "body_md": "fix *it*", "body_html": "<p>fix <em>it</em></p>\n"},
                    "code": {"verdict": "PASS", "body_md": "", "body_html": ""}}},
        {"n": 2, "trigger": "agent", "files": 2, "additions": 5, "deletions": 1,
         "verdicts": dict.fromkeys(("security", "ux", "ui", "code"), "pending"),
         "build_md": None, "build_html": "", "posted": {}},
    ]
    assert page["approver"] == {"decision": "APPROVE", "n": 2, "body_md": "ok **go**",
                                "body_html": "<p>ok <strong>go</strong></p>\n"}
    assert page["history"] == [{"created_at": "2026-01-01T00:00:01Z", "label": "created · backlog"},
                               {"created_at": "2026-01-01T00:00:02Z", "label": "in_progress · build"}]
    assert api(client, f"/api/pages/tasks/{review_task(project)}")["approver"] is None


def test_task_run_and_takeover(client, project):  # AC15
    worktree, session = "/code/my api/.claude/worktrees/1-t", "sess'1"
    tid = review_task(project, worktree=worktree)
    run = add_run(tid, "stopped", session=session)
    page = api(client, f"/api/pages/tasks/{tid}")
    assert page["run"] == {"id": run, "status": "stopped", "error": None, "session_id": session,
                           "started_at": STARTED}
    assert page["takeover"] == f"cd {shlex.quote(worktree)} && claude --resume {shlex.quote(session)}"
    sql("UPDATE runs SET status = 'running' WHERE id = ?", (run,))
    page = api(client, f"/api/pages/tasks/{tid}")
    assert (page["run"]["status"], page["takeover"]) == ("running", None)
    page = api(client, f"/api/pages/tasks/{review_task(project)}")
    assert (page["run"], page["takeover"]) == (None, None)


DOCKER_WT, DOCKER_SESSION = "/code/my api/.claude/worktrees/1-t", "sess'1"


def test_task_takeover_in_docker(client, project, monkeypatch):  # 028 AC1
    monkeypatch.setenv("FCTL_IN_DOCKER", "1")
    tid = review_task(project, worktree=DOCKER_WT)
    run = add_run(tid, "stopped", session=DOCKER_SESSION)
    takeover = api(client, f"/api/pages/tasks/{tid}")["takeover"]
    assert takeover == (f"docker compose exec -w {shlex.quote(DOCKER_WT)} backend claude"
                        f" --resume {shlex.quote(DOCKER_SESSION)}")
    sql("UPDATE runs SET status = 'running' WHERE id = ?", (run,))
    assert api(client, f"/api/pages/tasks/{tid}")["takeover"] is None


@pytest.mark.parametrize("value", [None, "0", ""])
def test_task_takeover_on_host(client, project, monkeypatch, value):  # 028 AC3
    if value is not None:
        monkeypatch.setenv("FCTL_IN_DOCKER", value)
    tid = review_task(project, worktree=DOCKER_WT)
    add_run(tid, "stopped", session=DOCKER_SESSION)
    assert api(client, f"/api/pages/tasks/{tid}")["takeover"] == (
        f"cd {shlex.quote(DOCKER_WT)} && claude --resume {shlex.quote(DOCKER_SESSION)}")


def test_isolated_unsets_in_docker():  # 028 AC6: fails under `FCTL_IN_DOCKER=1 uv run pytest` without it
    assert "FCTL_IN_DOCKER" not in os.environ


@pytest.mark.parametrize("case", ["uncommitted", "console"])
def test_task_runs_disabled(client, project, unready, fake, case):  # 026 AC16
    if case == "uncommitted":
        project = unready("uncommitted")
    else:
        fake(auth=CONSOLE)
    page = api(client, f"/api/pages/tasks/{add_task(project)}")
    assert (page["can_run"], page["hint"]) == (False, UNCOMMITTED if case == "uncommitted" else None)


# --- GET /api/pages/tasks/{id}/review -------------------------------------------------


def test_review(client, project):  # AC16
    tid = review_task(project, spec="## Goal")
    add_event(tid, None, "backlog", at="2026-01-01T00:00:01Z")
    r1 = add_round(tid, 1, at="2026-01-01T00:00:02Z")
    add_verdict(r1, "ux", "PASS", "nice", at="2026-01-01T00:00:03Z")
    add_decision(tid, r1, "approver", "APPROVE", "go", at="2026-01-01T00:00:04Z")
    add_comment(tid, r1, "me", "hi *there*", at="2026-01-01T00:00:05Z")
    add_round(tid, 2, trigger="human", files=((2, 1), (1, 1)), at="2026-01-01T00:00:06Z")
    page = api(client, f"/api/pages/tasks/{tid}/review")
    assert set(page) == {"task", "rounds", "selected", "approver", "files", "timeline"}
    assert set(page["task"]) == TASK_KEYS | {"commit_hint"}
    assert page["task"]["spec_html"] == "<h2>Goal</h2>\n"
    assert [set(r) for r in page["rounds"]] == [SUMMARY_KEYS | {"posted"}] * 2
    assert page["rounds"][0]["posted"] == {"ux": {"verdict": "PASS", "body_md": "nice", "body_html": "<p>nice</p>\n"}}
    assert page["selected"] == {"n": 2, "trigger": "human", "files": 2, "additions": 3, "deletions": 2,
                                "verdicts": dict.fromkeys(("security", "ux", "ui", "code"), "pending")}
    assert page["approver"] == {"decision": "APPROVE", "n": 1, "body_md": "go", "body_html": "<p>go</p>\n"}
    assert [f["path"] for f in page["files"]] == ["f0.py", "f1.py"]
    timeline = page["timeline"]
    assert [e["kind"] for e in timeline] == ["event", "round", "verdict", "decision", "comment", "round"]
    assert [e["created_at"] for e in timeline] == sorted(e["created_at"] for e in timeline)
    assert all(set(e) == {"created_at", "kind", "id", "label", "body_md", "body_html"} for e in timeline)
    assert timeline[4] | {"id": 0} == {"created_at": "2026-01-01T00:00:05Z", "kind": "comment", "id": 0,
                                       "label": "me · round 1", "body_md": "hi *there*",
                                       "body_html": "<p>hi <em>there</em></p>\n"}
    assert (timeline[0]["label"], timeline[0]["body_md"], timeline[0]["body_html"]) == ("created · backlog", None, "")


def test_review_round_param(client, project):  # AC17
    tid = review_task(project)
    add_round(tid, 1)
    add_round(tid, 2, files=((1, 0), (1, 0)))
    page = api(client, f"/api/pages/tasks/{tid}/review?round=1")
    assert page["selected"]["n"] == 1
    assert [f["path"] for f in page["files"]] == ["f0.py"]


def test_review_unknown_round_and_no_rounds(client, project):  # AC18
    tid = review_task(project)
    add_round(tid, 1)
    assert api(client, f"/api/pages/tasks/{tid}/review?round=9", 404) == {"detail": f"#{tid} has no round 9"}
    page = api(client, f"/api/pages/tasks/{review_task(project)}/review")
    assert (page["selected"], page["files"], page["rounds"]) == (None, [], [])


def test_review_file_rows(client, project):  # AC19
    tid = review_task(project)
    submit(client, tid, APP_PY)
    [f] = api(client, f"/api/pages/tasks/{tid}/review")["files"]
    assert "patch" not in f
    assert f == {
        "path": "app.py", "old_path": None, "change": "added", "binary": False, "additions": 1, "deletions": 0,
        "lang": "py", "orphans": [],
        "rows": [
            {"kind": "hunk", "old": None, "new": None, "side": None, "anchor": None, "text": "@@ -0,0 +1 @@",
             "comments": []},
            {"kind": "add", "old": None, "new": 1, "side": "new", "anchor": "app.py:new:1", "text": "x = 1",
             "comments": []},
        ],
    }


def test_review_del_and_ctx_rows(client, project):  # AC20
    tid = review_task(project)
    submit(client, tid, B_PY)
    [f] = api(client, f"/api/pages/tasks/{tid}/review")["files"]
    assert [(r["kind"], r["old"], r["new"], r["side"], r["anchor"]) for r in f["rows"]] == [
        ("hunk", None, None, None, None),
        ("ctx", 1, 1, "new", "b.py:new:1"),
        ("del", 2, None, "old", "b.py:old:2"),
        ("add", None, 2, "new", "b.py:new:2"),
    ]


def test_review_inline_comments(client, project):  # AC21
    tid = review_task(project)
    rid = submit(client, tid, APP_PY)
    add_inline(tid, rid, "security", "app.py", 1, "new", "trusts **x**")
    add_inline(tid, rid, "code", "app.py", 99, "new", "gone")
    [f] = api(client, f"/api/pages/tasks/{tid}/review")["files"]
    [here], [orphan] = f["rows"][1]["comments"], f["orphans"]
    ids = dict(sql("SELECT line, id FROM comments"))
    assert here == {"id": ids[1], "author": "security", "path": "app.py", "line": 1, "side": "new",
                    "body_md": "trusts **x**", "body_html": "<p>trusts <strong>x</strong></p>\n"}
    assert orphan == {"id": ids[99], "author": "code", "path": "app.py", "line": 99, "side": "new",
                      "body_md": "gone", "body_html": "<p>gone</p>\n"}
    assert f["rows"][0]["comments"] == []


def test_review_commit_hint(client, project):  # AC22
    tid = review_task(project, branch="factory/1-t")
    submit(client, tid, APP_PY)
    assert api(client, f"/api/pages/tasks/{tid}/review")["task"]["commit_hint"] is None
    r = client.post(f"/api/tasks/{tid}/approve", json={}, headers=H)
    assert r.status_code == 200, r.text
    assert api(client, f"/api/pages/tasks/{tid}/review")["task"]["commit_hint"] == r.json()["commit_hint"]


def note(text):
    """A diff `note` row: no line numbers, no side, no anchor."""
    return {"kind": "note", "old": None, "new": None, "side": None, "anchor": None, "text": text, "comments": []}


def files_at(client, task, query=""):
    """{path: file} of the review view-model's files."""
    return {f["path"]: f for f in api(client, f"/api/pages/tasks/{task}/review{query}")["files"]}


@pytest.fixture
def sample(client, project):
    """A factory task with 008's SAMPLE patch as round 1."""
    task = review_task(project, branch="factory/12-x")
    submit(client, task, SAMPLE)
    return task


def test_review_binary_and_rename_notes(client, sample):  # 026 AC21
    files = files_at(client, sample)
    assert files["logo.png"]["rows"] == [note("Binary file not shown.")]
    assert files["new_name"]["rows"] == [note("No content changes.")]


def test_review_no_newline_note(client, sample):  # 026 AC22
    assert files_at(client, sample)["app/limits.py"]["rows"][-1] == note("\\ No newline at end of file")


def test_review_crlf(client, sample):  # 026 AC23
    submit(client, sample, "diff --git a/win.txt b/win.txt\n--- a/win.txt\n+++ b/win.txt\n@@ -1 +1 @@\n-old\r\n+new\r\n")
    [add] = [r for r in files_at(client, sample, "?round=2")["win.txt"]["rows"] if r["kind"] == "add"]
    assert add["text"] == "new" and "\r" not in add["text"]


def test_review_huge_hunk_number(client, sample):  # 026 AC24: no 500 on a 5000-digit hunk header
    submit(client, sample, f"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -{'9' * 5000} +1 @@\n-x\n+y\n")
    assert files_at(client, sample, "?round=2")["a.py"]["rows"] == [note("No content changes.")]


# --- GET /api/pages/projects/{id}/code ------------------------------------------------


@pytest.fixture
def code_project(client, repo):
    commit(repo, {"README.md": "# Hi\n", "src/a.py": "a = 1\nb = 2\n"})
    return connect(client, repo)


def test_code_landing(client, code_project, repo):  # AC23
    page = api(client, f"/api/pages/projects/{code_project}/code")
    assert page["project"] == {"id": code_project, "name": "repo", "path": str(repo)}
    assert page["branch"] == "main"
    assert page["tree"] == {"README.md": {"path": "README.md"}, "src/": {"a.py": {"path": "src/a.py"}}}
    assert page["shown"] == "README.md"
    assert "<h1>Hi</h1>" in page["readme_html"]
    assert page["error"] is None


def test_code_file(client, code_project, repo):  # AC24
    page = api(client, f"/api/pages/projects/{code_project}/code?path=src/a.py")
    assert (page["shown"], page["view"], page["lang"], page["readme_html"]) == (
        "src/a.py", {"text": "a = 1\nb = 2\n", "lines": 2}, "py", None)
    commit(repo, {"logo.bin": b"\x00\x01\x02"})
    page = api(client, f"/api/pages/projects/{code_project}/code?path=logo.bin")
    assert page["view"] == {"note": "Binary file not shown."}


@pytest.mark.parametrize("path", ["../outside.txt", "untracked.txt"])
def test_code_untracked_404(client, code_project, repo, tmp_path, path):  # AC25
    (tmp_path / "outside.txt").write_text("TOP-SECRET-outside")
    (repo / "untracked.txt").write_text("TOP-SECRET-untracked")
    r = client.get(f"/api/pages/projects/{code_project}/code", params={"path": path})
    assert (r.status_code, r.json()) == (404, {"detail": f"{path} is not a tracked file in repo"})
    assert "TOP-SECRET" not in r.text


SECRET = "TOP-SECRET-7f3a"
APP = 'def main():\n    x = "<b>&</b>"\n    return x\n'
OUTSIDE = {"note": "Not shown: points outside the project."}


@pytest.fixture
def fixture_repo(repo, tmp_path):
    """021's code fixture: 4 tracked files, an untracked notes.txt, an ignored .env, and a secret next to the repo."""
    commit(repo, {"README.md": "# Hello\n", "src/app.py": APP, "docs/guide.md": "Guide\n", ".gitignore": ".env\n"})
    write(repo, {"notes.txt": "untracked notes", ".env": "API=ignored-env"})
    (tmp_path / "secret.txt").write_text(SECRET)
    return repo


def code(client, project_id, path=None, status=200):
    """The code view-model's response, checked for status and JSON."""
    r = client.get(f"/api/pages/projects/{project_id}/code", params=None if path is None else {"path": path})
    assert (r.status_code, r.headers["content-type"]) == (status, "application/json"), r.text
    return r


def test_code_symlink_outside(client, fixture_repo, tmp_path):  # 026 AC25
    os.symlink(tmp_path / "secret.txt", fixture_repo / "leak")
    commit(fixture_repo)
    r = code(client, connect(client, fixture_repo), "leak")
    assert r.json()["view"] == OUTSIDE
    assert SECRET not in r.text


def test_code_readme_symlink_outside(client, repo, tmp_path):  # 026 AC26
    (tmp_path / "secret.txt").write_text(SECRET)
    os.symlink(tmp_path / "secret.txt", repo / "README.md")
    commit(repo)
    r = code(client, connect(client, repo))
    assert (r.json()["view"], r.json()["readme_html"]) == (OUTSIDE, None)
    assert SECRET not in r.text


def test_code_symlink_inside(client, fixture_repo):  # 026 AC27
    os.symlink("src/app.py", fixture_repo / "alias.py")
    commit(fixture_repo)
    assert code(client, connect(client, fixture_repo), "alias.py").json()["view"]["text"] == APP


def test_code_untracked_paths_404(client, fixture_repo, tmp_path):  # 026 AC28
    pid = connect(client, fixture_repo)
    for path in (str(tmp_path / "secret.txt"), ".env", ".git/config", "src"):
        r = code(client, pid, path, 404)
        assert r.json() == {"detail": f"{path} is not a tracked file in repo"}
        assert SECRET not in r.text and "ignored-env" not in r.text and "untracked notes" not in r.text


def test_code_size_limit(client, repo):  # 026 AC29
    commit(repo, {"big.txt": b"x" * (1024 * 1024 + 1), "max.txt": b"y" * (1024 * 1024)})
    pid = connect(client, repo)
    assert code(client, pid, "big.txt").json()["view"] == {"note": "File over 1 MB not shown."}
    assert code(client, pid, "max.txt").json()["view"]["text"] == "y" * (1024 * 1024)


@pytest.mark.parametrize("kind", ["missing", "not a repo"])
def test_code_git_failure(client, tmp_path, kind):  # 026 AC30
    """The JSON carries git's own message; the SPA prefixes "Can't list files in <path>: " (CodePage.jsx)."""
    path = tmp_path / kind.replace(" ", "-")
    if kind == "not a repo":
        path.mkdir()
    page = code(client, connect(client, path)).json()
    assert page["error"].startswith("fatal: ")
    assert page["tree"] == {}


def test_code_branch(client, fixture_repo):  # 026 AC31
    pid = connect(client, fixture_repo)
    git(fixture_repo, "checkout", "-q", "-b", "feature-x")
    assert code(client, pid).json()["branch"] == "feature-x"
    git(fixture_repo, "checkout", "-q", "--detach")
    assert code(client, pid).json()["branch"] == "detached HEAD"


def test_code_no_readme(client, repo):  # 026 AC32
    commit(repo, {"src/app.py": APP})
    page = code(client, connect(client, repo)).json()
    assert (page["view"], page["readme_html"]) == ({"note": "No README.md in this project."}, None)


def test_code_non_utf8_replaced(client, repo):  # 026 AC33
    commit(repo, {"latin.txt": b"caf\xe9\n"})
    assert code(client, connect(client, repo), "latin.txt").json()["view"]["text"] == "caf\ufffd\n"


# --- GET /api/docs/fctl (029) ----------------------------------------------------------


def test_fctl_doc(client):  # 029 AC5: a GET, so no X-Requested-By
    doc = api(client, "/api/docs/fctl")
    assert set(doc) == {"body_html", "headings"}
    assert all(set(h) == {"id", "text", "level"} for h in doc["headings"])
    assert {"id": "fctl-serve", "text": "fctl serve", "level": 2} in doc["headings"]
    assert '<h2 id="fctl-serve">fctl serve</h2>' in doc["body_html"]


def test_fctl_doc_ids_unique(client):  # 029 AC6
    doc = api(client, "/api/docs/fctl")
    ids = [h["id"] for h in doc["headings"]]
    assert all(ids) and len(ids) == len(set(ids))
    for i in ids:
        assert doc["body_html"].count(f'id="{i}"') == 1, i


# --- Shared ---------------------------------------------------------------------------


def test_raw_html_off(client, project):  # AC26
    tid = review_task(project, description="<script>alert(1)</script>")
    rid = add_round(tid, 1)
    add_verdict(rid, "security", "CHANGES", "<img src=x onerror=alert(1)>")
    for url in (f"/api/pages/tasks/{tid}", f"/api/pages/tasks/{tid}/review"):
        page = api(client, url)
        description, body = page["task"]["description_html"], page["rounds"][0]["posted"]["security"]["body_html"]
        assert "&lt;script&gt;" in description and "<script" not in description
        assert "&lt;img" in body and "<img" not in body


@pytest.mark.parametrize("url, detail", [
    ("/api/pages/workspaces/999", "Not Found"),
    ("/api/pages/projects/999", "Not Found"),
    ("/api/pages/tasks/999", "Task #999 not found"),
    ("/api/pages/tasks/999/review", "Task #999 not found"),
    ("/api/pages/projects/999/code", "Project #999 not found"),
])
def test_unknown_ids_json_404(client, url, detail):  # AC27
    assert api(client, url, 404) == {"detail": detail}


# --- Nothing else moves ---------------------------------------------------------------


def test_new_modules_follow_layers():  # AC32
    for rel in ("controllers/pages_api.py", "dto/pages.py"):
        path = PKG / rel
        assert path in checked()
        tree = ast.parse(path.read_text())
        assert wrong_edges(tree, path) + fastapi_outside(tree, path) + sql_outside(tree, path) == []
