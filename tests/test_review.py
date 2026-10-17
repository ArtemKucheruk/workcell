import re

import pytest
from conftest import sql

H = {"X-Requested-By": "fctl"}
OLD = "2026-01-01T00:00:00Z"
WORKTREE = "/code/api/.claude/worktrees/12-x"
REVIEWERS = ("security", "ux", "ui", "code")


@pytest.fixture
def project(client):
    body = {"path": "/code/api", "workspace": "personal", "name": "api", "default_branch": "main"}
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def add_task(project_id, title="t", status="review", stage="human_review", description="", spec=None,
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


def add_decision(task_id, round_id, actor, decision, body_md="", at=OLD):
    sql("INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, round_id, actor, decision, body_md, at))


def add_event(task_id, from_status, to_status, stage=None, at=OLD, id=None):
    sql("INSERT INTO events (id, task_id, actor, from_status, to_status, stage, created_at)"
        " VALUES (?, ?, 'app', ?, ?, ?, ?)", (id, task_id, from_status, to_status, stage, at))


def page(client, task_id, query=""):
    r = client.get(f"/tasks/{task_id}/review{query}")
    assert r.status_code == 200, r.text
    return r.text


def text(html):
    """Tags stripped, whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


def section(html, name):
    found = re.search(rf'<section id="{name}">(.*?)</section>', html, re.S)
    return found and found[1]


def header(html):
    return re.search(r"<header>(.*?)</header>", html, re.S)[1]


def round_block(html, n):
    return re.search(rf'<div id="round-{n}" class="round">(.*?)</div>', html, re.S)[1]


def round_row(html, n):
    return text(re.search(r'<p class="round-row">(.*?)</p>', round_block(html, n), re.S)[1])


def options(html):
    """[(value, selected)] of the header's round selector."""
    return [(v, bool(s)) for v, s in re.findall(r'<option value="(\d+)"( selected)?>', header(html))]


def timeline(html):
    """[(the label text, the item's html)], in page order."""
    ol = re.search(r"<ol>(.*?)</ol>", section(html, "timeline"), re.S)[1]
    items = re.findall(r"<li>(.*?)</li>", ol, re.S)
    return [(text(re.sub(r"<time[^>]*>.*?</time>", "", i, flags=re.S)), i) for i in items]


@pytest.fixture
def reviewed(project):
    """A factory task: round 1 (initial, sec CHANGES, +118 −9) and round 2 (agent, all PASS, +126 −9)."""
    task = add_task(project, title="Rate-limit login", branch="factory/12-x")
    r1 = add_round(task, 1, files=((118, 9),))
    for who in REVIEWERS:
        add_verdict(r1, who, "CHANGES" if who == "security" else "PASS")
    r2 = add_round(task, 2, "agent", files=((100, 5), (26, 4)))
    for who in REVIEWERS:
        add_verdict(r2, who, "PASS")
    return task


# --- Page ----------------------------------------------------------------------------


def test_page_renders(client, project):  # AC1
    task = add_task(project, title="Rate-limit login")
    r = client.get(f"/tasks/{task}/review")
    assert r.status_code == 200
    assert r.template.name == "review.html"
    assert re.findall(r"<h1>(.*?)</h1>", r.text, re.S) == [f"#{task} Rate-limit login"]


def test_title_escaped(client, project):  # AC2
    html = page(client, add_task(project, title="<script>alert(1)</script>"))
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)" not in html


def not_found_page(r):
    """ui review round 1: a page GET's 404 is an HTML page; its <h1> text."""
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("text/html")
    assert '<a href="/">Claude Factories</a>' in r.text
    return re.search(r"<h1>(.*?)</h1>", r.text)[1]


def test_unknown_task_404(client, project):  # AC3
    assert not_found_page(client.get("/tasks/999/review")) == "Task #999 not found"
    assert not_found_page(client.get("/projects/999")) == "Not Found"
    assert not_found_page(client.get("/no-such-page")) == "Not Found"
    r = client.get("/api/tasks/999")  # the API keeps its JSON 404
    assert (r.status_code, r.json()) == (404, {"detail": "Not Found"})


def test_project_link(client, project):  # AC4
    html = page(client, add_task(project))
    assert f'<a href="/projects/{project}">api</a>' in html


# --- Header --------------------------------------------------------------------------


@pytest.mark.parametrize("status, stage, expected", [
    ("in_progress", "build", "In progress · build"),
    ("review", "human_review", "Review · waiting on you"),
    ("review", "escalated", "Review · ⚠ NEEDS YOU — escalated"),
    ("backlog", None, "Backlog"),
    ("done", None, "Done"),
])
def test_status_stage(client, project, status, stage, expected):  # AC5
    html = page(client, add_task(project, status=status, stage=stage))
    assert text(re.search(r'<span id="status">(.*?)</span>\s', html, re.S)[1]) == expected
    assert bool(re.search(r'class="[^"]*\bescalated\b', html)) == (stage == "escalated")


def test_branch(client, project):  # AC6
    assert "<code>factory/12-x</code>" in header(page(client, add_task(project, branch="factory/12-x")))
    assert "<code>" not in header(page(client, add_task(project, branch=None)))


def test_round_selector(client, project):  # AC7
    task = add_task(project)
    for n in (1, 2, 3):
        add_round(task, n)
    head = header(page(client, task))
    forms = re.findall(r'<form method="get" action="([^"]*)">(.*?)</form>', head, re.S)
    assert [action for action, _ in forms] == [f"/tasks/{task}/review"]
    assert '<select name="round"' in forms[0][1]
    assert options(page(client, task)) == [("1", False), ("2", False), ("3", True)]


def test_round_param(client, project):  # AC8
    task = add_task(project)
    for n in (1, 2, 3):
        add_round(task, n)
    assert options(page(client, task, "?round=2")) == [("1", False), ("2", True), ("3", False)]
    assert page(client, task, "?round=latest") == page(client, task)


def test_files_changed(client, project):  # AC9
    task = add_task(project)
    add_round(task, 1, files=((7, 7),))
    add_round(task, 2, files=((100, 5), (26, 4)))
    assert re.search(r'<span id="files"[^>]*>(.*?)</span>', page(client, task))[1] == "2 files changed +126 −9"
    assert re.search(r'<span id="files"[^>]*>(.*?)</span>', page(client, task, "?round=1"))[1] == (
        "1 file changed +7 −7")


@pytest.mark.parametrize("n", ["99", "abc"])
def test_unknown_round_404(client, project, n):  # AC10
    task = add_task(project)
    add_round(task, 1)
    assert not_found_page(client.get(f"/tasks/{task}/review?round={n}")) == f"#{task} has no round {n}"


def test_no_rounds_header(client, project):  # AC11
    task = add_task(project)
    html = page(client, task)
    assert '<select name="round"' not in html
    assert "files changed" not in html
    assert client.get(f"/tasks/{task}/review?round=1").status_code == 404


# --- Conversation: description and spec ------------------------------------------------


def test_description_markdown(client, project):  # AC12
    html = page(client, add_task(project, description="**Max 5** failed logins"))
    assert "<strong>Max 5</strong>" in section(html, "description")


def test_empty_description(client, project):  # AC13
    assert "No description." in text(section(page(client, add_task(project)), "description"))


def test_spec_details(client, project):  # AC14
    html = page(client, add_task(project, spec="## Criteria\n- 429"))
    [(attrs, inner)] = re.findall(r"<details([^>]*)>(.*?)</details>", html, re.S)
    assert "open" not in attrs
    assert inner.startswith("<summary>Spec</summary>")
    assert "<h2>Criteria</h2>" in inner and "<li>429</li>" in inner
    for spec in (None, "  \n "):
        assert "<summary>Spec</summary>" not in page(client, add_task(project, spec=spec))


def test_raw_html_off(client, project):  # AC15
    html = page(client, add_task(project, description="<script>alert(1)</script>"))
    assert "&lt;script&gt;" in section(html, "description") and "<script>alert" not in html
    html = page(client, add_task(project, description="[x](javascript:alert(1))"))
    assert 'href="javascript:' not in html
    task = add_task(project)
    add_verdict(add_round(task, 1), "security", "CHANGES", "<img src=x onerror=alert(1)>\n\nmore")
    html = page(client, task)
    [(summary, body)] = re.findall(r"<summary>(.*?)</summary>(.*?)</details>", round_block(html, 1), re.S)
    assert "&lt;img" in summary and "&lt;img" in body
    assert "<img" not in html


# --- Conversation: rounds ------------------------------------------------------------


def test_round_rows(client, project, reviewed):  # AC16
    html = page(client, reviewed)
    rounds = section(html, "rounds")
    assert re.findall(r'<div id="(round-\d+)"', rounds) == ["round-1", "round-2"]
    assert round_row(html, 1) == "Round 1 initial sec ✗ ux ✓ ui ✓ code ✓ +118 −9"
    assert round_row(html, 2) == "Round 2 agent sec ✓ ux ✓ ui ✓ code ✓ +126 −9"


def test_chip_titles(client, project):  # AC17
    task = add_task(project)
    r1 = add_round(task, 1)
    add_verdict(r1, "security", "CHANGES")
    add_verdict(r1, "ux", "PASS")
    add_verdict(r1, "code", "PASS")
    chips = re.findall(r'<span title="([^"]*)">(.*?)</span>', round_block(page(client, task), 1))
    assert chips == [("security: CHANGES", "sec ✗"), ("ux: PASS", "ux ✓"), ("ui: pending", "ui ·"),
                     ("code: PASS", "code ✓")]


def test_verdict_bodies(client, project):  # AC18
    task = add_task(project)
    r1 = add_round(task, 1)
    add_verdict(r1, "code", "PASS", "\n  \nLooks **fine**\nsecond line")
    add_verdict(r1, "security", "CHANGES", "app/limits.py:31 trusts X-Forwarded-For")
    add_verdict(r1, "ux", "PASS", "  \n ")  # blank body: no <details>; ui stays pending
    found = re.findall(r"<details([^>]*)><summary>(.*?)</summary>(.*?)</details>", round_block(page(client, task), 1),
                       re.S)
    assert ["open" in attrs for attrs, _, _ in found] == [False, False]
    assert [text(summary) for _, summary, _ in found] == [
        "security · CHANGES app/limits.py:31 trusts X-Forwarded-For", "code · PASS Looks **fine**"]
    assert "<p>app/limits.py:31 trusts X-Forwarded-For</p>" in found[0][2]
    assert "<p>Looks <strong>fine</strong>\nsecond line</p>" in found[1][2]


def test_no_agent_review(client, project):  # AC19
    standalone = add_task(project, worktree=None)
    add_round(standalone, 1)
    block = round_block(page(client, standalone), 1)
    assert "no agent review" in block and "title=" not in block
    factory = add_task(project)
    add_round(factory, 1)
    block = round_block(page(client, factory), 1)
    assert "no agent review" not in block and block.count('title="') == 4 and block.count(": pending") == 4
    add_verdict(add_round(standalone, 2), "security", "PASS")
    block = round_block(page(client, standalone), 2)
    assert "no agent review" not in block and 'title="security: PASS"' in block


def test_no_rounds_section(client, project):  # AC20
    assert text(section(page(client, add_task(project)), "rounds")) == "Rounds No rounds yet."


# --- Conversation: approver decision ----------------------------------------------------


def test_approver_latest(client, project):  # AC21
    task = add_task(project)
    r1, r2 = add_round(task, 1), add_round(task, 2)
    add_decision(task, r1, "approver", "ESCALATE", "stuck")
    add_decision(task, r2, "approver", "APPROVE", "All **4** PASS")
    add_decision(task, r2, "me", "CHANGES_REQUESTED", "nope")
    block = section(page(client, task), "approver")
    assert text(block).startswith("Approver · APPROVE")
    assert "<strong>4</strong>" in block
    assert "ESCALATE" not in block and "CHANGES_REQUESTED" not in block


def test_no_approver(client, project):  # AC22
    task = add_task(project)
    add_decision(task, add_round(task, 1), "me", "CHANGES_REQUESTED")
    assert section(page(client, task), "approver") is None


# --- Timeline ------------------------------------------------------------------------


def at(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def test_timeline_order(client, project):  # AC23
    task = add_task(project, worktree=None)
    add_event(task, None, "backlog", at=at(1))
    add_event(task, "backlog", "in_progress", "spec", at=at(2))
    r1 = add_round(task, 1, at=at(3))
    sql("UPDATE round_files SET path = 'app/limits.py' WHERE round_id = ?", (r1,))
    add_verdict(r1, "security", "CHANGES", at=at(4))
    add_comment(task, r1, "security", "trusts XFF", "app/limits.py", 31, at=at(5))
    add_decision(task, r1, "approver", "ESCALATE", at=at(6))
    add_comment(task, r1, "me", "fix it", at=at(7))
    html = page(client, task)
    labels = [re.sub(r" (trusts XFF|fix it)$", "", label) for label, _ in timeline(html)]
    assert labels == ["created · backlog", "in_progress · spec", "round 1", "security CHANGES · round 1",
                      "security on app/limits.py:31 · round 1", "approver ESCALATE · round 1", "me · round 1"]
    assert [re.search(r'<time datetime="([^"]*)">', item)[1] for _, item in timeline(html)] == [
        at(s) for s in range(1, 8)]


def test_timeline_event_labels(client, project):  # AC24
    task = add_task(project, status="done", stage=None, worktree=None)
    add_event(task, None, "review", "human_review", at=at(1))
    add_event(task, "review", "done", at=at(2))
    assert [label for label, _ in timeline(page(client, task))] == ["created · review · human_review", "done"]


def test_timeline_ties(client, project):  # AC25
    task = add_task(project)
    r1 = add_round(task, 1)  # every row at OLD
    add_comment(task, r1, "me", "second", id=9)
    add_comment(task, r1, "me", "first", id=3)
    add_decision(task, r1, "approver", "APPROVE")
    add_verdict(r1, "ux", "PASS")
    add_event(task, "backlog", "in_progress", "build", id=8)
    add_event(task, None, "backlog", id=2)
    assert [label for label, _ in timeline(page(client, task))] == [
        "created · backlog", "in_progress · build", "round 1", "ux PASS · round 1", "approver APPROVE · round 1",
        "me · round 1 first", "me · round 1 second"]


def test_timeline_bodies(client, project):  # AC26
    task = add_task(project)
    add_event(task, None, "backlog")
    r1 = add_round(task, 1)
    add_verdict(r1, "ux", "PASS", "**ok**")
    add_decision(task, r1, "approver", "APPROVE", "**ok**")
    add_comment(task, r1, "me", "**ok**")
    items = [item for _, item in timeline(page(client, task))]
    assert ["<strong>ok</strong>" in item for item in items] == [False, False, False, True, True]
    assert ["<p>" in item for item in items] == [False, False, False, True, True]


# --- Comment box ---------------------------------------------------------------------


def test_comment_form(client, project, reviewed):  # AC27
    html = page(client, reviewed)
    after = html.split(section(html, "timeline"), 1)[1]
    [form] = re.findall(rf'<form hx-post="/tasks/{reviewed}/comments"[^>]*>(.*?)</form>', after, re.S)
    [textarea] = re.findall(r'<textarea [^>]*name="body_md"[^>]*>', form)
    assert " required" in textarea and 'placeholder="Leave a comment…"' in textarea
    assert re.findall(r"<button[^>]*>(.*?)</button>", form) == ["Comment"]
    html = page(client, add_task(project))
    assert "/comments" not in html and "Comments open once a round is submitted." in html


def post(client, task_id, data, headers=H):
    return client.post(f"/tasks/{task_id}/comments", data=data, headers=headers)


def task_row(task_id):
    return sql("SELECT * FROM tasks WHERE id = ?", (task_id,))


def test_comment_post(client, project, reviewed):  # AC28
    before, events = task_row(reviewed), sql("SELECT COUNT(*) FROM events")
    r = post(client, reviewed, {"body_md": "Looks good"})
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == f"/tasks/{reviewed}/review"
    latest = sql("SELECT id FROM rounds WHERE task_id = ? AND n = 2", (reviewed,))[0][0]
    assert sql("SELECT author, round_id, path, line, side, body_md FROM comments") == [
        ("me", latest, None, None, None, "Looks good")]
    assert sql("SELECT COUNT(*) FROM events") == events
    assert task_row(reviewed) == before


@pytest.mark.parametrize("data", [{"body_md": ""}, {"body_md": "  \n "}, {}])
def test_comment_blank(client, project, reviewed, data):  # AC29
    assert post(client, reviewed, data).status_code == 422
    assert sql("SELECT COUNT(*) FROM comments") == [(0,)]


def test_comment_refused(client, project, reviewed):  # AC30
    assert post(client, reviewed, {"body_md": "x"}, headers={}).status_code == 403
    assert post(client, 999, {"body_md": "x"}).status_code == 404
    assert post(client, add_task(project), {"body_md": "x"}).status_code == 404
    assert sql("SELECT COUNT(*) FROM comments") == [(0,)]


def test_comment_in_timeline(client, project, reviewed):  # AC31
    assert post(client, reviewed, {"body_md": "Looks good"}).status_code == 204
    label, item = timeline(page(client, reviewed))[-1]
    assert label == "me · round 2 Looks good"
    assert "<p>Looks good</p>" in item
