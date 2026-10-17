import re
import shlex
from datetime import UTC, datetime, timedelta

import pytest
from conftest import sql
from markupsafe import escape
from test_review import H, add_round, add_task, header, page, project, section, timeline  # noqa: F401

FORM = H | {"Content-Type": "application/x-www-form-urlencoded"}
NOTE = "Make the limit configurable via settings."
WT = "/code/api/.claude/worktrees/12-rate-limit-login"
BRANCH = "factory/12-rate-limit-login"
PATCH = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"


def task_with_rounds(project_id, n=2, status="review", stage="human_review", **kw):
    """A task with rounds 1..n; (task id, [round ids])."""
    task = add_task(project_id, status=status, stage=stage, **kw)
    return task, [add_round(task, i, "initial" if i == 1 else "agent") for i in range(1, n + 1)]


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


def snapshot(task):
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


# --- Approve API -----------------------------------------------------------------------


def test_approve(client, factory_task):  # AC1
    task, _ = factory_task
    r = approve(client, task)
    assert r.status_code == 200
    assert list(r.json()) == ["status", "commit_hint"] and r.json()["status"] == "done"
    status, stage, position, done_at, updated_at = row(task)
    assert (status, stage, position) == ("done", None, 1.0)
    assert current(done_at) and current(updated_at)


def test_approve_decision(client, project, factory_task):  # AC2
    task, (_, r2) = factory_task
    approve(client, task, {"body_md": "Ship it."})
    assert decisions(task) == [("me", "APPROVE", r2, "Ship it.")]
    other, (_, o2) = task_with_rounds(project)
    assert approve(client, other, {}).status_code == 200
    assert decisions(other) == [("me", "APPROVE", o2, "")]


def test_approve_event(client, factory_task):  # AC3
    task, _ = factory_task
    approve(client, task)
    assert events(task) == [("me", "review", "done", None)]


def test_approve_escalated(client, project):  # AC4
    task, _ = task_with_rounds(project, stage="escalated")
    r = approve(client, task)
    assert (r.status_code, r.json()["status"], row(task)[0]) == (200, "done", "done")


def test_commit_hint_factory(client, factory_task):  # AC5
    task, _ = factory_task
    assert approve(client, task).json()["commit_hint"] == (
        "cd /code/api/.claude/worktrees/12-rate-limit-login\n"
        "git add -A && git commit -m 'Rate-limit login endpoint'\n"
        "git push -u origin factory/12-rate-limit-login     # then open a PR, or merge locally\n"
        "cd /code/api && git worktree remove .claude/worktrees/12-rate-limit-login"
    )


def test_commit_hint_quoted(client, project):  # AC6
    title = """it's $(touch x) "q\""""
    task, _ = task_with_rounds(project, title=title, branch="factory/12-x", worktree="/code/api/.claude/worktrees/12 x")
    lines = approve(client, task).json()["commit_hint"].split("\n")
    assert lines[0] == "cd '/code/api/.claude/worktrees/12 x'"
    assert lines[1] == "git add -A && git commit -m " + shlex.quote(title)
    assert shlex.split(lines[1])[-1] == title
    assert lines[3] == "cd /code/api && git worktree remove '.claude/worktrees/12 x'"


def test_commit_hint_standalone(client, standalone):  # AC7
    task, _ = standalone
    assert approve(client, task).json()["commit_hint"] == "git add -A && git commit -m 'Fix open redirect after login'"


@pytest.mark.parametrize("status, stage", [("backlog", None), ("in_progress", "build"), ("done", None)])
def test_approve_not_in_review(client, project, status, stage):  # AC8
    task, _ = task_with_rounds(project, status=status, stage=stage)
    before = snapshot(task)
    r = approve(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": f"#{task} is not in review"})
    assert snapshot(task) == before


def test_approve_twice(client, factory_task):  # AC8
    task, _ = factory_task
    assert approve(client, task).status_code == 200
    r = approve(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": f"#{task} is not in review"})
    assert [d[1] for d in decisions(task)] == ["APPROVE"]


def test_approve_missing(client, project):  # AC9
    assert approve(client, 999).status_code == 404
    task, _ = task_with_rounds(project, n=0)
    before = snapshot(task)
    r = approve(client, task)
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no rounds"})
    assert snapshot(task) == before


# --- Request changes API ---------------------------------------------------------------


def test_request_changes(client, factory_task):  # AC10
    task, _ = factory_task
    r = rework(client, task)
    # 013 Q12: /code/api isn't a repo, so the rework spawn is refused after the move is recorded
    assert (r.status_code, r.json()) == (409, {"detail": "factory isn't committed on main"})
    status, stage, position, done_at, updated_at = row(task)
    assert (status, stage, position, done_at) == ("in_progress", "rework", 1.0, None)
    assert current(updated_at)


def test_request_changes_rows(client, factory_task):  # AC11
    task, (_, r2) = factory_task
    rework(client, task)
    assert decisions(task) == [("me", "CHANGES_REQUESTED", r2, NOTE)]
    assert events(task) == [("me", "review", "in_progress", "rework")]


def test_request_changes_standalone(client, factory_task, standalone):  # AC12
    task, (_, r2) = standalone
    r = rework(client, task)
    assert (r.status_code, r.json()) == (202, {"status": "in_progress", "stage": "rework", "run_id": None})
    assert row(task)[:4] == ("in_progress", "rework", 1.0, None)
    assert decisions(task) == [("me", "CHANGES_REQUESTED", r2, NOTE)]
    assert events(task) == [("me", "review", "in_progress", "rework")]
    r = rework(client, factory_task[0])  # 013: a factory task's spawn is tried, and refused here
    assert (r.status_code, r.json()) == (409, {"detail": "factory isn't committed on main"})
    assert sql("SELECT COUNT(*) FROM runs") == [(0,)]


@pytest.mark.parametrize("body, detail", [({}, None), ({"body_md": ""}, "body_md must not be blank"),
                                          ({"body_md": "  \n"}, "body_md must not be blank")])
def test_request_changes_blank(client, factory_task, body, detail):  # AC13
    task, _ = factory_task
    before = snapshot(task)
    r = rework(client, task, body)
    assert r.status_code == 422
    if detail:
        assert r.json() == {"detail": detail}
    assert snapshot(task) == before


def test_request_changes_refused(client, project):  # AC14
    for status, stage in (("backlog", None), ("in_progress", "build"), ("done", None)):
        task, _ = task_with_rounds(project, status=status, stage=stage)
        before = snapshot(task)
        r = rework(client, task)
        assert (r.status_code, r.json()) == (409, {"detail": f"#{task} is not in review"})
        assert snapshot(task) == before
    assert rework(client, 999).status_code == 404
    task, _ = task_with_rounds(project, n=0)
    before = snapshot(task)
    r = rework(client, task)
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no rounds"})
    assert snapshot(task) == before


def test_request_changes_feedback(client, factory_task):  # AC15
    task, _ = factory_task
    comment = {"round": 2, "author": "me", "path": "f0.py", "line": 1, "body_md": "Keep the old default."}
    assert client.post(f"/api/tasks/{task}/comments", json=comment, headers=H).status_code == 201
    rework(client, task)
    text = client.get(f"/api/tasks/{task}/context?feedback=1").text
    assert f"## Feedback on round 2\n{NOTE}\n\n## Comments\n\n### me on f0.py:1 (new)\nKeep the old default.\n" in text


def test_request_changes_then_submit(client, standalone):  # AC16
    task, _ = standalone
    rework(client, task)
    r = client.post(f"/api/tasks/{task}/rounds", json={"base_sha": "abc1234", "patch": PATCH}, headers=H)
    assert r.status_code == 201 and r.json()["round"] == 3
    assert sql("SELECT trigger FROM rounds WHERE task_id = ? AND n = 3", (task,)) == [("human",)]
    assert row(task)[:2] == ("review", "human_review")


@pytest.mark.parametrize("path", ["/api/tasks/{}/approve", "/api/tasks/{}/request-changes",
                                  "/tasks/{}/approve", "/tasks/{}/request-changes"])
def test_actions_need_fctl_header(client, factory_task, path):  # AC17
    task, _ = factory_task
    before = snapshot(task)
    r = client.post(path.format(task), json={"body_md": NOTE}, headers={})
    assert r.status_code == 403
    assert snapshot(task) == before


# --- Review page -----------------------------------------------------------------------


def action_forms(html, task):
    """{"request-changes": inner html, "approve": inner html} of the header's two action forms."""
    return dict(re.findall(rf'<form hx-post="/tasks/{task}/(request-changes|approve)"[^>]*>(.*?)</form>',
                           header(html), re.S))


def button(form, label):
    """The attributes of the form's button labelled `label`."""
    return re.search(rf"<button([^>]*)>{label}</button>", form)[1]


@pytest.mark.parametrize("query", ["", "?tab=files"])
def test_action_forms(client, factory_task, query):  # AC18
    task, _ = factory_task
    forms = action_forms(page(client, task, query), task)
    assert list(forms) == ["request-changes", "approve"]
    [textarea] = re.findall(r"<textarea[^>]*>", forms["request-changes"])
    assert 'name="body_md"' in textarea and " required" in textarea and "disabled" not in textarea
    assert "disabled" not in button(forms["request-changes"], "Request changes")
    assert "disabled" not in button(forms["approve"], "Approve")
    assert "<textarea" not in forms["approve"]
    assert all('class="form-error"' in f for f in forms.values())


@pytest.mark.parametrize("status, stage, n", [("backlog", None, 2), ("in_progress", "rework", 2), ("done", None, 2),
                                              ("review", "human_review", 0)])
def test_action_forms_disabled(client, project, status, stage, n):  # AC19
    task, _ = task_with_rounds(project, n=n, status=status, stage=stage)
    forms = action_forms(page(client, task), task)
    assert " disabled" in button(forms["request-changes"], "Request changes")
    assert " disabled" in button(forms["approve"], "Approve")


def test_approve_form(client, factory_task):  # AC20
    task, _ = factory_task
    r = client.post(f"/tasks/{task}/approve", content=b"", headers=FORM)
    assert (r.status_code, r.headers["HX-Redirect"]) == (204, f"/tasks/{task}/review")
    assert row(task)[0] == "done"


def test_request_changes_form(client, project, standalone):  # AC21: standalone, so no spawn (013)
    task, _ = standalone
    r = client.post(f"/tasks/{task}/request-changes", content=b"body_md=Make+it+configurable", headers=FORM)
    assert (r.status_code, r.headers["HX-Redirect"]) == (204, f"/tasks/{task}/review")
    assert [d[3] for d in decisions(task)] == ["Make it configurable"]
    other, _ = task_with_rounds(project)
    before = snapshot(other)
    for body in (b"body_md=", b"body_md=+%0A+"):
        r = client.post(f"/tasks/{other}/request-changes", content=body, headers=FORM)
        assert (r.status_code, r.json()) == (422, {"detail": "body_md must not be blank"})
    assert snapshot(other) == before


def test_commit_section(client, project, factory_task):  # AC22
    task, _ = factory_task
    hint = approve(client, task).json()["commit_hint"]
    for query in ("", "?tab=files"):
        assert f"<pre>{escape(hint)}</pre>" in section(page(client, task, query), "commit")
    bold, _ = task_with_rounds(project, title="Fix <b>login</b>", branch=None, worktree=None)
    approve(client, bold)
    shown = section(page(client, bold), "commit")
    assert f"<pre>{escape('git add -A && git commit -m ' + shlex.quote('Fix <b>login</b>'))}</pre>" in shown
    assert "&lt;b&gt;" in shown and "<b>" not in shown
    for status, stage in (("backlog", None), ("in_progress", "build"), ("review", "human_review")):
        assert 'id="commit"' not in page(client, task_with_rounds(project, status=status, stage=stage)[0])


def test_timeline_after_actions(client, project, factory_task):  # AC23
    task, _ = factory_task
    rework(client, task)
    items = timeline(page(client, task))
    labels = [label for label, _ in items]
    assert f"me CHANGES_REQUESTED · round 2 {NOTE}" in labels and "in_progress · rework" in labels
    assert f"<p>{NOTE}</p>" in dict(items)[f"me CHANGES_REQUESTED · round 2 {NOTE}"]
    other, _ = task_with_rounds(project)
    approve(client, other)
    labels = [label for label, _ in timeline(page(client, other))]
    assert "me APPROVE · round 2" in labels and "done" in labels
