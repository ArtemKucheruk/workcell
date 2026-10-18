import re
import shlex
from datetime import UTC, datetime, timedelta

import pytest
from conftest import sql
from controllers.test_pages_api import add_round as add_page_round
from controllers.test_pages_api import review_task

H = {"X-Requested-By": "fctl"}
OLD = "2026-01-01T00:00:00Z"
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
WORKTREE = "/code/api/.claude/worktrees/12-x"


@pytest.fixture
def project(client):
    body = {"path": "/code/api", "workspace": "personal", "name": "api", "default_branch": "main"}
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def add_task(project_id, status="in_progress", stage="agent_review", title="t", description="", spec=None,
             worktree=WORKTREE):
    return sql(
        "INSERT INTO tasks (project_id, title, description_md, spec_md, status, stage, position, worktree_path,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?) RETURNING id",
        (project_id, title, description, spec, status, stage, worktree, OLD, OLD),
    )[0][0]


def add_round(task_id, n, build_md=None, files=("app/limits.py",)):
    round_id = sql(
        "INSERT INTO rounds (task_id, n, trigger, base_sha, build_md, created_at)"
        " VALUES (?, ?, 'initial', 'abc1234', ?, ?) RETURNING id",
        (task_id, n, build_md, OLD),
    )[0][0]
    for path in files:
        sql("INSERT INTO round_files (round_id, path, change, additions, deletions, patch)"
            " VALUES (?, ?, 'modified', 1, 0, '')", (round_id, path))
    return round_id


def add_verdict(round_id, reviewer, verdict, body_md=""):
    sql("INSERT INTO verdicts (round_id, reviewer, verdict, body_md, created_at) VALUES (?, ?, ?, ?, ?)",
        (round_id, reviewer, verdict, body_md, OLD))


def add_comment(task_id, round_id, author, body_md, path=None, line=None, side=None):
    sql("INSERT INTO comments (task_id, round_id, author, path, line, side, body_md, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (task_id, round_id, author, path, line, side, body_md, OLD))


def add_decision(task_id, round_id, actor, decision, body_md=""):
    sql("INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, round_id, actor, decision, body_md, OLD))


def count(table):
    return sql(f"SELECT COUNT(*) FROM {table}")[0][0]


@pytest.fixture
def two_rounds(project):
    """(task, round 1's id, round 2's id). Round 1 has app/limits.py and a.py, round 2 app/limits.py."""
    task = add_task(project)
    return task, add_round(task, 1, files=("app/limits.py", "a.py")), add_round(task, 2)


@pytest.fixture
def no_rounds(project):
    return add_task(project)


# --- PUT /api/tasks/{id}/rounds/{n|latest}/verdicts/{reviewer} -----------------


def put(client, task_id, reviewer, body, n="latest", headers=H):
    return client.put(f"/api/tasks/{task_id}/rounds/{n}/verdicts/{reviewer}", json=body, headers=headers)


def verdict_rows():
    return sql("SELECT round_id, reviewer, verdict, body_md, created_at FROM verdicts ORDER BY round_id, reviewer")


def test_verdict_on_latest(client, two_rounds):  # AC1
    task, _, r2 = two_rounds
    body = {"verdict": "CHANGES", "body_md": "1. app/limits.py:31 trusts X-Forwarded-For …"}
    r = put(client, task, "security", body)
    assert r.status_code == 200, r.text
    assert r.json() == {"round": 2, "reviewer": "security", "verdict": "CHANGES", "complete": "1/4"}
    [(round_id, reviewer, verdict, body_md, created_at)] = verdict_rows()  # one row: none on round 1
    assert (round_id, reviewer, verdict, body_md) == (r2, "security", "CHANGES", body["body_md"])
    assert TIMESTAMP.fullmatch(created_at)


def test_verdict_complete_counts(client, two_rounds):  # AC2
    task, _, r2 = two_rounds
    add_verdict(r2, "ux", "PASS")
    add_verdict(r2, "code", "PASS")
    assert put(client, task, "security", {"verdict": "PASS"}).json()["complete"] == "3/4"
    assert put(client, task, "ui", {"verdict": "PASS"}).json()["complete"] == "4/4"


def test_verdict_overwrites(client, two_rounds):  # AC3
    task, _, r2 = two_rounds
    add_verdict(r2, "security", "CHANGES", "Trusts X-Forwarded-For.")
    r = put(client, task, "security", {"verdict": "PASS", "body_md": "Fixed."})
    assert (r.status_code, r.json()["complete"]) == (200, "1/4")
    [(round_id, _, verdict, body_md, created_at)] = verdict_rows()
    assert (round_id, verdict, body_md) == (r2, "PASS", "Fixed.")
    assert created_at != OLD and TIMESTAMP.fullmatch(created_at)


def test_verdict_on_round_number(client, two_rounds):  # AC4
    task, r1, r2 = two_rounds
    add_verdict(r2, "security", "PASS")
    r = put(client, task, "ux", {"verdict": "PASS"}, n=1)
    assert r.json() == {"round": 1, "reviewer": "ux", "verdict": "PASS", "complete": "1/4"}
    assert [row[:3] for row in verdict_rows()] == [(r1, "ux", "PASS"), (r2, "security", "PASS")]


def test_verdict_body_optional(client, two_rounds):  # AC5
    assert put(client, two_rounds[0], "ux", {"verdict": "PASS"}).status_code == 200
    assert verdict_rows()[0][3] == ""


@pytest.mark.parametrize("reviewer, body", [
    ("approver", {"verdict": "PASS"}), ("Security", {"verdict": "PASS"}),
    ("security", {"verdict": "pass"}), ("security", {"verdict": "APPROVE"}), ("security", {"body_md": "x"}),
])
def test_verdict_rejected(client, two_rounds, reviewer, body):  # AC6
    assert put(client, two_rounds[0], reviewer, body).status_code == 422
    assert count("verdicts") == 0


def test_verdict_missing_round(client, two_rounds, no_rounds):  # AC7
    r = put(client, no_rounds, "ux", {"verdict": "PASS"})
    assert (r.status_code, r.json()) == (404, {"detail": f"#{no_rounds} has no rounds"})
    r = put(client, two_rounds[0], "ux", {"verdict": "PASS"}, n=9)
    assert (r.status_code, r.json()) == (404, {"detail": f"#{two_rounds[0]} has no round 9"})
    assert put(client, 999, "ux", {"verdict": "PASS"}).status_code == 404
    assert count("verdicts") == 0


@pytest.mark.parametrize("status, stage, worktree", [("done", None, WORKTREE), ("in_progress", "build", None)])
def test_verdict_any_task(client, project, status, stage, worktree):  # AC8
    task = add_task(project, status, stage, worktree=worktree)
    add_round(task, 1)
    assert put(client, task, "ux", {"verdict": "PASS"}).status_code == 200


# --- POST /api/tasks/{id}/comments ---------------------------------------------

SECURITY_COMMENT = {"round": "latest", "author": "security", "path": "app/limits.py", "line": 31, "side": "new",
                    "body_md": "Use request.client.host unless behind a known proxy."}
COMMENT_COLUMNS = "id, task_id, round_id, author, path, line, side, body_md, created_at"


def post_comment(client, task_id, body, headers=H):
    return client.post(f"/api/tasks/{task_id}/comments", json=body, headers=headers)


def test_comment_inline(client, two_rounds):  # AC9
    task, _, r2 = two_rounds
    r = post_comment(client, task, SECURITY_COMMENT)
    assert r.status_code == 201, r.text
    [row] = sql(f"SELECT {COMMENT_COLUMNS} FROM comments")
    assert r.json() == {"id": row[0]}
    assert row[1:8] == (task, r2, "security", "app/limits.py", 31, "new", SECURITY_COMMENT["body_md"])
    assert TIMESTAMP.fullmatch(row[8])


def test_comment_conversation(client, two_rounds):  # AC10
    task, _, r2 = two_rounds
    assert post_comment(client, task, {"author": "me", "body_md": "Looks close."}).status_code == 201
    assert sql("SELECT round_id, path, line, side, body_md FROM comments") == [
        (r2, None, None, None, "Looks close.")
    ]


def test_comment_on_round_number(client, two_rounds):  # AC11
    task, r1, _ = two_rounds
    body = {"round": 1, "author": "ux", "path": "a.py", "line": 3, "body_md": "x"}
    assert post_comment(client, task, body).status_code == 201
    assert sql("SELECT round_id, side FROM comments") == [(r1, "new")]


BASE_COMMENT = {"author": "security", "path": "app/limits.py", "line": 31, "body_md": "x"}
DROP = object()


@pytest.mark.parametrize("change", [
    {"author": "approver"}, {"author": "bob"}, {"line": DROP}, {"path": DROP},
    {"path": DROP, "line": DROP, "side": "new"}, {"side": "both"}, {"line": 0},
    {"body_md": DROP}, {"body_md": "  "}, {"path": "app/nope.py"},
])
def test_comment_rejected(client, two_rounds, change):  # AC12
    body = {k: v for k, v in (BASE_COMMENT | change).items() if v is not DROP}
    r = post_comment(client, two_rounds[0], body)
    assert r.status_code == 422, r.text
    if change == {"path": "app/nope.py"}:
        assert r.json() == {"detail": "app/nope.py is not in round 2"}
    if change == {"body_md": "  "}:
        assert r.json() == {"detail": "body_md must not be blank"}
    assert count("comments") == 0


def test_comment_missing_round(client, two_rounds, no_rounds):  # AC13
    task = two_rounds[0]
    r = post_comment(client, task, SECURITY_COMMENT | {"round": 9})
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no round 9"})
    r = post_comment(client, no_rounds, SECURITY_COMMENT)
    assert (r.status_code, r.json()) == (404, {"detail": f"#{no_rounds} has no rounds"})
    assert post_comment(client, 999, SECURITY_COMMENT).status_code == 404
    assert count("comments") == 0


# --- POST /api/tasks/{id}/decision ---------------------------------------------

APPROVE = {"decision": "APPROVE", "body_md": "All 4 PASS on round 2; criteria met; tests green."}


def post_decision(client, task_id, body, headers=H):
    return client.post(f"/api/tasks/{task_id}/decision", json=body, headers=headers)


def test_decision_approve(client, two_rounds):  # AC14
    task, _, r2 = two_rounds
    r = post_decision(client, task, APPROVE)
    assert r.status_code == 201, r.text
    [(decision_id, round_id, actor, decision, body_md, created_at)] = sql(
        "SELECT id, round_id, actor, decision, body_md, created_at FROM decisions"
    )
    assert r.json() == {"id": decision_id}
    assert (round_id, actor, decision, body_md) == (r2, "approver", "APPROVE", APPROVE["body_md"])
    assert TIMESTAMP.fullmatch(created_at)
    [listed] = client.get(f"/api/tasks/{task}").json()["decisions"]
    assert (listed["id"], listed["round"], listed["actor"]) == (decision_id, 2, "approver")


def test_decision_body_optional(client, two_rounds):  # AC15
    assert post_decision(client, two_rounds[0], {"decision": "ESCALATE"}).status_code == 201
    assert sql("SELECT decision, body_md FROM decisions") == [("ESCALATE", "")]


def test_decision_appends(client, two_rounds):  # AC16
    first = post_decision(client, two_rounds[0], APPROVE)
    second = post_decision(client, two_rounds[0], {"decision": "ESCALATE"})
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert sql("SELECT id, decision FROM decisions ORDER BY id") == [
        (first.json()["id"], "APPROVE"), (second.json()["id"], "ESCALATE")
    ]


@pytest.mark.parametrize("body", [{"decision": "CHANGES_REQUESTED"}, {"decision": "approve"}, {"body_md": "x"}])
def test_decision_rejected(client, two_rounds, body):  # AC17
    assert post_decision(client, two_rounds[0], body).status_code == 422
    assert count("decisions") == 0


def test_decision_missing_round(client, no_rounds):  # AC18
    r = post_decision(client, no_rounds, APPROVE)
    assert (r.status_code, r.json()) == (404, {"detail": f"#{no_rounds} has no rounds"})
    assert post_decision(client, 999, APPROVE).status_code == 404
    assert count("decisions") == 0


# --- All three write routes -------------------------------------------------------


def snapshot(task_id):
    return (sql("SELECT status, stage, position, updated_at FROM tasks WHERE id = ?", (task_id,)),
            sql("SELECT * FROM events WHERE task_id = ? ORDER BY id", (task_id,)))


def test_writes_leave_task_unchanged(client, two_rounds):  # AC19
    task = two_rounds[0]
    sql("INSERT INTO events (task_id, actor, to_status, stage, created_at)"
        " VALUES (?, 'orchestrator', 'in_progress', 'agent_review', ?)", (task, OLD))
    before = snapshot(task)
    assert put(client, task, "security", {"verdict": "PASS"}).status_code == 200
    assert post_comment(client, task, SECURITY_COMMENT).status_code == 201
    assert post_decision(client, task, APPROVE).status_code == 201
    assert snapshot(task) == before
    assert before[0] == [("in_progress", "agent_review", 1.0, OLD)]


def test_writes_need_fctl_header(client, two_rounds):  # AC20
    task = two_rounds[0]
    assert put(client, task, "security", {"verdict": "PASS"}, headers={}).status_code == 403
    assert post_comment(client, task, SECURITY_COMMENT, headers={}).status_code == 403
    assert post_decision(client, task, APPROVE, headers={}).status_code == 403
    assert [count(t) for t in ("verdicts", "comments", "decisions")] == [0, 0, 0]


# --- GET /api/tasks/{id}/context ---------------------------------------------------


@pytest.fixture
def ctx(project):
    """(task, round 1's id, round 2's id): AC21's fixture."""
    task = add_task(project, title="Rate-limit login endpoint", description="Max 5 failed logins/min per IP.\n",
                    spec="- 6th failed login within 60s → 429\n")
    r1 = add_round(task, 1, build_md="Token bucket in app/limits.py.\n")
    add_verdict(r1, "security", "CHANGES", "Trusts X-Forwarded-For.")
    add_verdict(r1, "ux", "PASS", "")
    add_verdict(r1, "code", "PASS", "Tests cover it.\n")
    add_comment(task, r1, "security", "Use request.client.host.", "app/limits.py", 31, "new")
    return task, r1, add_round(task, 2)


def round_1(task):
    return f"""# #{task} Rate-limit login endpoint
Status: in_progress · agent_review

## Description
Max 5 failed logins/min per IP.

## Spec
- 6th failed login within 60s → 429

## Round 1 — build notes
Token bucket in app/limits.py.

## Verdicts

### security: CHANGES
Trusts X-Forwarded-For.

### ux: PASS

### ui: pending

### code: PASS
Tests cover it.

## Comments

### security on app/limits.py:31 (new)
Use request.client.host.
"""


ROUND_2 = ("\n\n## Round 2 — build notes\n\n## Verdicts\n\n### security: pending\n\n### ux: pending\n\n"
           "### ui: pending\n\n### code: pending\n")


def context(client, task_id, query=""):
    return client.get(f"/api/tasks/{task_id}/context{query}")


def test_context_one_round(client, ctx):  # AC21
    r = context(client, ctx[0], "?round=1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.text == round_1(ctx[0])


def test_context_everything(client, ctx):  # AC22
    assert context(client, ctx[0]).text == round_1(ctx[0]).removesuffix("\n") + ROUND_2


def test_context_latest(client, ctx):  # AC23
    latest = context(client, ctx[0], "?round=latest")
    assert latest.status_code == 200
    assert latest.text == context(client, ctx[0], "?round=2").text


def test_context_decisions(client, ctx):  # AC24
    task, r1, _ = ctx
    add_decision(task, r1, "approver", "ESCALATE", "Round cap reached.")
    assert context(client, task, "?round=1").text.endswith(
        "Use request.client.host.\n\n## Decisions\n\n### approver: ESCALATE\nRound cap reached.\n"
    )


def test_context_fresh_task(client, project):  # AC25
    task = add_task(project, "backlog", None, title="x")
    assert context(client, task).text == f"# #{task} x\nStatus: backlog\n\n## Description\n\n## Spec\n_No spec yet._\n"


def test_context_feedback(client, ctx):  # AC26
    task, r1, r2 = ctx
    sql("UPDATE tasks SET stage = 'rework' WHERE id = ?", (task,))
    add_decision(task, r1, "me", "CHANGES_REQUESTED", "Old note.")
    add_decision(task, r2, "me", "CHANGES_REQUESTED", "Make the limit configurable via settings.")
    add_comment(task, r2, "me", "Keep the old default.", "app/limits.py", 12, "old")
    add_comment(task, r2, "me", "Also log it.")
    add_comment(task, r2, "security", "x")
    text = context(client, task, "?feedback=1").text
    assert text.startswith(f"# #{task} Rate-limit login endpoint\nStatus: in_progress · rework\n\n## Description\n")
    assert text.endswith(
        "## Spec\n- 6th failed login within 60s → 429\n\n## Feedback on round 2\n"
        "Make the limit configurable via settings.\n\n## Comments\n\n### me on app/limits.py:12 (old)\n"
        "Keep the old default.\n\n### me\nAlso log it.\n"
    )
    assert "Old note." not in text and "## Round" not in text


def test_context_no_feedback(client, ctx):  # AC27
    task, r1, _ = ctx
    add_decision(task, r1, "approver", "ESCALATE")
    r = context(client, task, "?feedback=1")
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no feedback"})


def test_context_errors(client, ctx, no_rounds):  # AC28
    task = ctx[0]
    r = context(client, task, "?round=9")
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no round 9"})
    r = context(client, no_rounds, "?round=latest")
    assert (r.status_code, r.json()) == (404, {"detail": f"#{no_rounds} has no rounds"})
    assert context(client, 999).status_code == 404
    r = context(client, task, "?round=1&feedback=1")
    assert (r.status_code, r.json()) == (422, {"detail": "give round or feedback, not both"})


# --- 033: the project context atop the full view -------------------------------------

PROJECT_CONTEXT = "# Stack\n- Python 3.12, uv\n\n## Conventions\n- SQL only in repositories/\n  \n\n"


def set_project_context(client, project_id, text):
    r = client.put(f"/api/projects/{project_id}/context", json={"context_md": text}, headers=H)
    assert r.status_code == 200, r.text


def test_context_starts_with_project_context(client, project, ctx):  # 033 AC13
    task = ctx[0]
    without = context(client, task).text
    set_project_context(client, project, PROJECT_CONTEXT)
    head = f"## Project context\n{PROJECT_CONTEXT.rstrip()}\n\n"
    text = context(client, task).text
    assert text.startswith(head + f"# #{task} Rate-limit login endpoint\n")
    assert text == head + without


@pytest.mark.parametrize("blank", ["", " \n\t\n"])
def test_context_blank_project_context(client, project, ctx, blank):  # 033 AC14
    set_project_context(client, project, blank)
    text = context(client, ctx[0]).text
    assert "## Project context" not in text
    assert text == round_1(ctx[0]).removesuffix("\n") + ROUND_2


def test_context_views_without_project_context(client, project, ctx):  # 033 AC15
    task, _, r2 = ctx
    add_decision(task, r2, "me", "CHANGES_REQUESTED", "Make it configurable.")
    set_project_context(client, project, PROJECT_CONTEXT)
    for query in ("?round=1", "?round=latest", "?feedback=1"):
        r = context(client, task, query)
        assert r.status_code == 200, query
        assert "## Project context" not in r.text and "Python 3.12" not in r.text, query
        assert r.text.startswith(f"# #{task} "), query


def test_context_from_own_project(client, project):  # 033 AC16
    body = {"path": "/code/web", "workspace": "personal", "name": "web", "default_branch": "main"}
    other = client.post("/api/projects/connect", json=body, headers=H).json()["id"]
    set_project_context(client, project, "Stack A\n")
    set_project_context(client, other, "Stack B\n")
    a, b = add_task(project, title="a"), add_task(other, title="b")
    text = context(client, a).text
    assert text.startswith(f"## Project context\nStack A\n\n# #{a} a\n")
    assert "Stack B" not in text
    assert context(client, b).text.startswith(f"## Project context\nStack B\n\n# #{b} b\n")


# --- 009: approve and request changes (026 AC9: from pages/test_review_actions.py) ---

NOTE = "Make the limit configurable via settings."
WT = "/code/api/.claude/worktrees/12-rate-limit-login"
BRANCH = "factory/12-rate-limit-login"
PATCH = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
# 013 Q12: /code/api isn't a repo, so a factory task's rework spawn gets run_task's no-factory 409 (015 wording)
NO_FACTORY = "factory isn't committed on main: Create factory on the project board, then commit it on main"


def task_with_rounds(project_id, n=2, status="review", stage="human_review", **kw):
    """A task with rounds 1..n; (task id, [round ids])."""
    task = review_task(project_id, status=status, stage=stage, **kw)
    return task, [add_page_round(task, i, "initial" if i == 1 else "agent") for i in range(1, n + 1)]


@pytest.fixture
def factory_task(project):
    return task_with_rounds(project, title="Rate-limit login endpoint", branch=BRANCH, worktree=WT)


@pytest.fixture
def standalone(project):
    return task_with_rounds(project, title="Fix open redirect after login", branch=None, worktree=None)


def approve(client, task, body=None, headers=H):
    return client.post(f"/api/tasks/{task}/approve", json={"body_md": ""} if body is None else body, headers=headers)


def rework(client, task, body=None, headers=H):
    return client.post(f"/api/tasks/{task}/request-changes", json={"body_md": NOTE} if body is None else body,
                       headers=headers)


def row(task):
    return sql("SELECT status, stage, position, done_at, updated_at FROM tasks WHERE id = ?", (task,))[0]


def action_snapshot(task):
    """What "nothing written" compares: the decisions and events counts and the task row."""
    return sql("SELECT COUNT(*) FROM decisions")[0][0], sql("SELECT COUNT(*) FROM events")[0][0], row(task)


def decisions(task):
    return sql("SELECT actor, decision, round_id, body_md FROM decisions WHERE task_id = ? ORDER BY id", (task,))


def events(task):
    return sql("SELECT actor, from_status, to_status, stage FROM events WHERE task_id = ? ORDER BY id", (task,))


def current(ts):
    """A YYYY-MM-DDTHH:MM:SSZ timestamp from the last few seconds."""
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", ts), ts
    return datetime.now(UTC) - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) < timedelta(seconds=5)


# --- 009: Approve API -----------------------------------------------------------


def test_approve(client, factory_task):  # 009 AC1, moved by 026
    task, _ = factory_task
    r = approve(client, task)
    assert r.status_code == 200
    assert list(r.json()) == ["status", "commit_hint"] and r.json()["status"] == "done"
    status, stage, position, done_at, updated_at = row(task)
    assert (status, stage, position) == ("done", None, 1.0)
    assert current(done_at) and current(updated_at)


def test_approve_decision(client, project, factory_task):  # 009 AC2, moved by 026
    task, (_, r2) = factory_task
    approve(client, task, {"body_md": "Ship it."})
    assert decisions(task) == [("me", "APPROVE", r2, "Ship it.")]
    other, (_, o2) = task_with_rounds(project)
    assert approve(client, other, {}).status_code == 200
    assert decisions(other) == [("me", "APPROVE", o2, "")]


def test_approve_event(client, factory_task):  # 009 AC3, moved by 026
    task, _ = factory_task
    approve(client, task)
    assert events(task) == [("me", "review", "done", None)]


def test_approve_escalated(client, project):  # 009 AC4, moved by 026
    task, _ = task_with_rounds(project, stage="escalated")
    r = approve(client, task)
    assert (r.status_code, r.json()["status"], row(task)[0]) == (200, "done", "done")


def test_commit_hint_factory(client, factory_task):  # 009 AC5, moved by 026
    task, _ = factory_task
    assert approve(client, task).json()["commit_hint"] == (
        "cd /code/api/.claude/worktrees/12-rate-limit-login\n"
        "git add -A && git commit -m 'Rate-limit login endpoint'\n"
        "git push -u origin factory/12-rate-limit-login     # then open a PR, or merge locally\n"
        "cd /code/api && git worktree remove .claude/worktrees/12-rate-limit-login"
    )


def test_commit_hint_quoted(client, project):  # 009 AC6, moved by 026
    title = """it's $(touch x) "q\""""
    task, _ = task_with_rounds(project, title=title, branch="factory/12-x", worktree="/code/api/.claude/worktrees/12 x")
    lines = approve(client, task).json()["commit_hint"].split("\n")
    assert lines[0] == "cd '/code/api/.claude/worktrees/12 x'"
    assert lines[1] == "git add -A && git commit -m " + shlex.quote(title)
    assert shlex.split(lines[1])[-1] == title
    assert lines[3] == "cd /code/api && git worktree remove '.claude/worktrees/12 x'"


def test_commit_hint_standalone(client, standalone):  # 009 AC7, moved by 026
    task, _ = standalone
    assert approve(client, task).json()["commit_hint"] == "git add -A && git commit -m 'Fix open redirect after login'"


@pytest.mark.parametrize("status, stage", [("backlog", None), ("in_progress", "build"), ("done", None)])
def test_approve_not_in_review(client, project, status, stage):  # 009 AC8, moved by 026
    task, _ = task_with_rounds(project, status=status, stage=stage)
    before = action_snapshot(task)
    r = approve(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": f"#{task} is not in review"})
    assert action_snapshot(task) == before


def test_approve_twice(client, factory_task):  # 009 AC8, moved by 026
    task, _ = factory_task
    assert approve(client, task).status_code == 200
    r = approve(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": f"#{task} is not in review"})
    assert [d[1] for d in decisions(task)] == ["APPROVE"]


def test_approve_missing(client, project):  # 009 AC9, moved by 026
    assert approve(client, 999).status_code == 404
    task, _ = task_with_rounds(project, n=0)
    before = action_snapshot(task)
    r = approve(client, task)
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no rounds"})
    assert action_snapshot(task) == before


# --- 009: Request changes API ---------------------------------------------


def test_request_changes(client, factory_task):  # 009 AC10, moved by 026
    task, _ = factory_task
    r = rework(client, task)
    # 013 Q12: /code/api isn't a repo, so the rework spawn is refused after the move is recorded
    assert (r.status_code, r.json()) == (409, {"detail": NO_FACTORY})
    status, stage, position, done_at, updated_at = row(task)
    assert (status, stage, position, done_at) == ("in_progress", "rework", 1.0, None)
    assert current(updated_at)


def test_request_changes_rows(client, factory_task):  # 009 AC11, moved by 026
    task, (_, r2) = factory_task
    rework(client, task)
    assert decisions(task) == [("me", "CHANGES_REQUESTED", r2, NOTE)]
    assert events(task) == [("me", "review", "in_progress", "rework")]


def test_request_changes_standalone(client, factory_task, standalone):  # 009 AC12, moved by 026
    task, (_, r2) = standalone
    r = rework(client, task)
    assert (r.status_code, r.json()) == (202, {"status": "in_progress", "stage": "rework", "run_id": None})
    assert row(task)[:4] == ("in_progress", "rework", 1.0, None)
    assert decisions(task) == [("me", "CHANGES_REQUESTED", r2, NOTE)]
    assert events(task) == [("me", "review", "in_progress", "rework")]
    r = rework(client, factory_task[0])  # 013: a factory task's spawn is tried, and refused here
    assert (r.status_code, r.json()) == (409, {"detail": NO_FACTORY})
    assert sql("SELECT COUNT(*) FROM runs") == [(0,)]


@pytest.mark.parametrize("body, detail", [({}, None), ({"body_md": ""}, "body_md must not be blank"),
                                          ({"body_md": "  \n"}, "body_md must not be blank")])
def test_request_changes_blank(client, factory_task, body, detail):  # 009 AC13, moved by 026
    task, _ = factory_task
    before = action_snapshot(task)
    r = rework(client, task, body)
    assert r.status_code == 422
    if detail:
        assert r.json() == {"detail": detail}
    assert action_snapshot(task) == before


def test_request_changes_refused(client, project):  # 009 AC14, moved by 026
    for status, stage in (("backlog", None), ("in_progress", "build"), ("done", None)):
        task, _ = task_with_rounds(project, status=status, stage=stage)
        before = action_snapshot(task)
        r = rework(client, task)
        assert (r.status_code, r.json()) == (409, {"detail": f"#{task} is not in review"})
        assert action_snapshot(task) == before
    assert rework(client, 999).status_code == 404
    task, _ = task_with_rounds(project, n=0)
    before = action_snapshot(task)
    r = rework(client, task)
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no rounds"})
    assert action_snapshot(task) == before


def test_request_changes_feedback(client, factory_task):  # 009 AC15, moved by 026
    task, _ = factory_task
    comment = {"round": 2, "author": "me", "path": "f0.py", "line": 1, "body_md": "Keep the old default."}
    assert client.post(f"/api/tasks/{task}/comments", json=comment, headers=H).status_code == 201
    rework(client, task)
    text = client.get(f"/api/tasks/{task}/context?feedback=1").text
    assert f"## Feedback on round 2\n{NOTE}\n\n## Comments\n\n### me on f0.py:1 (new)\nKeep the old default.\n" in text


def test_request_changes_then_submit(client, standalone):  # 009 AC16, moved by 026
    task, _ = standalone
    rework(client, task)
    r = client.post(f"/api/tasks/{task}/rounds", json={"base_sha": "abc1234", "patch": PATCH}, headers=H)
    assert r.status_code == 201 and r.json()["round"] == 3
    assert sql("SELECT trigger FROM rounds WHERE task_id = ? AND n = 3", (task,)) == [("human",)]
    assert row(task)[:2] == ("review", "human_review")


@pytest.mark.parametrize("path", ["/api/tasks/{}/approve", "/api/tasks/{}/request-changes"])
def test_actions_need_fctl_header(client, factory_task, path):  # 009 AC17, moved by 026
    task, _ = factory_task
    before = action_snapshot(task)
    r = client.post(path.format(task), json={"body_md": NOTE}, headers={})
    assert r.status_code == 403
    assert action_snapshot(task) == before
