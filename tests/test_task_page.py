import re

import pytest
from conftest import sql
from test_review import (REVIEWERS, add_comment, add_decision, add_event, add_round, add_task, add_verdict, at,  # noqa: F401
                         header, not_found_page, project, section, text)


def page(client, task_id):
    r = client.get(f"/tasks/{task_id}")
    assert r.status_code == 200, r.text
    return r.text


def block(html, n):
    """Round n's block: up to the next round or the end of the rounds section (popovers are <div>s)."""
    return re.search(rf'<div id="round-{n}" class="round">(.*?)(?=<div id="round-|</section>)', html, re.S)[1]


def row(html, n):
    return re.search(r'<p class="round-row">(.*?)</p>', block(html, n), re.S)[1]


def popover(html, n, who):
    return re.search(rf'<div popover id="verdict-{n}-{who}">(.*?)</div>', block(html, n), re.S)[1]


def history(html):
    """[(the label text, the item's html)], in page order."""
    ol = re.search(r"<ol>(.*?)</ol>", section(html, "history"), re.S)[1]
    items = re.findall(r"<li>(.*?)</li>", ol, re.S)
    return [(text(re.sub(r"<time[^>]*>.*?</time>", "", i, flags=re.S)), i) for i in items]


def set_build(round_id, build_md):
    sql("UPDATE rounds SET build_md = ? WHERE id = ?", (build_md, round_id))


# --- Page ----------------------------------------------------------------------------


def test_page_renders(client, project):  # AC1
    task = add_task(project, title="Rate-limit login")
    r = client.get(f"/tasks/{task}")
    assert r.status_code == 200
    assert r.template.name == "task.html"
    assert re.findall(r"<h1>(.*?)</h1>", r.text, re.S) == [f"#{task} Rate-limit login"]


def test_unknown_task_404(client, project):  # AC2
    assert not_found_page(client.get("/tasks/999")) == "Task #999 not found"


def test_project_link(client, project):  # AC3
    assert f'<a href="/projects/{project}">api</a>' in page(client, add_task(project))


def test_review_link(client, project):  # AC4
    no_rounds = add_task(project)
    assert f'<a href="/tasks/{no_rounds}/review">Review</a>' in header(page(client, no_rounds))
    with_round = add_task(project)
    add_round(with_round, 1)
    assert f'<a href="/tasks/{with_round}/review">Review</a>' in header(page(client, with_round))


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
    assert text(re.search(r'<span id="status">(.*?)</span>\s', header(html), re.S)[1]) == expected
    assert bool(re.search(r'class="[^"]*\bescalated\b', html)) == (stage == "escalated")


def test_branch(client, project):  # AC6
    assert "<code>factory/12-x</code>" in header(page(client, add_task(project, branch="factory/12-x")))
    assert "<code>" not in header(page(client, add_task(project, branch=None)))


# --- Description and spec -------------------------------------------------------------


def test_description(client, project):  # AC7
    html = page(client, add_task(project, description="**Max 5** failed logins"))
    assert "<strong>Max 5</strong>" in section(html, "description")
    assert text(section(page(client, add_task(project)), "description")) == "Description No description."


def test_spec_open(client, project):  # AC8
    spec = section(page(client, add_task(project, spec="## Criteria\n- 429")), "spec")
    assert "<h2>Criteria</h2>" in spec and "<li>429</li>" in spec
    assert "<details" not in spec


@pytest.mark.parametrize("spec", [None, "  \n "])
def test_no_spec(client, project, spec):  # AC9
    assert text(section(page(client, add_task(project, spec=spec)), "spec")) == "Spec No spec yet."


# --- Rounds --------------------------------------------------------------------------


def test_round_rows(client, project):  # AC10
    task = add_task(project)
    r1 = add_round(task, 1, files=((100, 5), (18, 4)))
    for who in REVIEWERS:
        add_verdict(r1, who, "CHANGES" if who == "security" else "PASS")
    r2 = add_round(task, 2, "agent", files=((126, 9),))
    for who in REVIEWERS:
        add_verdict(r2, who, "PASS")
    html = page(client, task)
    assert re.findall(r'<div id="(round-\d+)"', section(html, "rounds")) == ["round-1", "round-2"]
    assert text(row(html, 1)) == "Round 1 initial sec ✗ ux ✓ ui ✓ code ✓ +118 −9"
    assert text(row(html, 2)) == "Round 2 agent sec ✓ ux ✓ ui ✓ code ✓ +126 −9"


def test_verdict_popover(client, project):  # AC11
    task = add_task(project)
    add_verdict(add_round(task, 1), "security", "CHANGES", "Trusts **X-Forwarded-For**")
    html = page(client, task)
    assert ('<button type="button" popovertarget="verdict-1-security" title="security: CHANGES">sec ✗</button>'
            in row(html, 1))
    assert block(html, 1).count('<div popover id="verdict-1-security">') == 1
    assert "<div" not in row(html, 1)  # the popover sits after the row's <p>, not in it
    body = popover(html, 1, "security")
    assert text(body).startswith("security · CHANGES")
    assert "<strong>X-Forwarded-For</strong>" in body


def test_plain_chips(client, project):  # AC12
    task = add_task(project)
    add_verdict(add_round(task, 1), "ux", "PASS", "  \n ")
    html = page(client, task)
    assert '<span title="ui: pending">ui ·</span>' in row(html, 1)
    assert '<span title="ux: PASS">ux ✓</span>' in row(html, 1)
    assert "popovertarget" not in html and "popover" not in block(html, 1)


def test_no_agent_review(client, project):  # AC13
    standalone = add_task(project, worktree=None)
    add_round(standalone, 1)
    html = page(client, standalone)
    assert "no agent review" in row(html, 1)
    assert "title=" not in block(html, 1) and "popover" not in block(html, 1)
    factory = add_task(project)
    add_round(factory, 1)
    html = page(client, factory)
    assert "no agent review" not in row(html, 1)
    assert re.findall(r'<span title="([^"]*)">', row(html, 1)) == [f"{who}: pending" for who in REVIEWERS]


def test_build_notes(client, project):  # AC14
    task = add_task(project)
    set_build(add_round(task, 1), "Token **bucket**")
    [(attrs, inner)] = re.findall(r"<details([^>]*)>(.*?)</details>", block(page(client, task), 1), re.S)
    assert "open" not in attrs
    assert inner.startswith("<summary>Build notes</summary>")
    assert "<strong>bucket</strong>" in inner


@pytest.mark.parametrize("build_md", [None, "  \n "])
def test_no_build_notes(client, project, build_md):  # AC15
    task = add_task(project)
    set_build(add_round(task, 1), build_md)
    found = block(page(client, task), 1)
    assert "No build notes." in text(found) and "<details" not in found


def test_no_rounds(client, project):  # AC16
    assert text(section(page(client, add_task(project)), "rounds")) == "Rounds No rounds yet."


# --- Approver decision -----------------------------------------------------------------


def test_approver_latest(client, project):  # AC17
    task = add_task(project)
    r1, r2 = add_round(task, 1), add_round(task, 2)
    add_decision(task, r1, "approver", "ESCALATE", "stuck")
    add_decision(task, r2, "approver", "APPROVE", "All **4** PASS")
    add_decision(task, r2, "me", "CHANGES_REQUESTED", "nope")
    html = page(client, task)
    assert html.count('<section id="approver">') == 1
    found = section(html, "approver")
    assert text(found).startswith("Approver · APPROVE") and "round 2" in text(found)
    assert "<strong>4</strong>" in found
    assert "ESCALATE" not in found and "CHANGES_REQUESTED" not in found


def test_no_approver(client, project):  # AC18
    task = add_task(project)
    add_decision(task, add_round(task, 1), "me", "CHANGES_REQUESTED")
    assert '<section id="approver">' not in page(client, task)


# --- Status history --------------------------------------------------------------------


def test_history_labels(client, project):  # AC19
    task = add_task(project, status="done", stage=None)
    add_event(task, None, "backlog", at=at(1))
    add_event(task, "backlog", "in_progress", at=at(2))
    add_event(task, "in_progress", "in_progress", "spec", at=at(3))
    add_event(task, "in_progress", "review", "human_review", at=at(4))
    add_event(task, "review", "done", at=at(5))
    items = history(page(client, task))
    assert [label for label, _ in items] == [
        "created · backlog", "in_progress", "in_progress · spec", "review · human_review", "done"]
    assert [re.search(r'<time datetime="([^"]*)">', item)[1] for _, item in items] == [at(s) for s in range(1, 6)]


def test_history_events_only(client, project):  # AC20
    task = add_task(project)
    add_event(task, None, "backlog", at=at(1))
    add_event(task, "backlog", "in_progress", "build", at=at(2))
    r1 = add_round(task, 1, at=at(3))
    add_verdict(r1, "ux", "PASS", at=at(4))
    add_decision(task, r1, "approver", "APPROVE", at=at(5))
    add_comment(task, r1, "me", "hi", at=at(6))
    assert [label for label, _ in history(page(client, task))] == ["created · backlog", "in_progress · build"]


def test_history_ties(client, project):  # AC21
    task = add_task(project)
    add_event(task, "backlog", "in_progress", "build", id=8)  # both at OLD
    add_event(task, None, "backlog", id=2)
    assert [label for label, _ in history(page(client, task))] == ["created · backlog", "in_progress · build"]


# --- Safety and polling ------------------------------------------------------------------


def test_raw_html_off(client, project):  # AC22
    script, img = "<script>alert(1)</script>", "<img src=x onerror=alert(1)>"
    task = add_task(project, title=script, spec=img)
    r1 = add_round(task, 1)
    set_build(r1, script)
    add_verdict(r1, "security", "CHANGES", img)
    add_decision(task, r1, "approver", "ESCALATE", script)
    html = page(client, task)
    assert "&lt;script&gt;" in header(html)
    assert "&lt;img" in section(html, "spec")
    assert "&lt;script&gt;" in re.search(r"<details>(.*?)</details>", block(html, 1), re.S)[1]
    assert "&lt;img" in popover(html, 1, "security")
    assert "&lt;script&gt;" in section(html, "approver")
    assert "<script>alert" not in html and "<img" not in html


def test_live_poll(client, project):  # AC23
    task = add_task(project)
    html = page(client, task)
    [(attrs, rest)] = re.findall(r'<div id="live"([^>]*)>(.*)', html, re.S)
    attr = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
    assert (attr["hx-get"], attr["hx-select"], attr["hx-swap"]) == (f"/tasks/{task}", "#live", "outerHTML")
    assert attr["hx-trigger"].startswith("every 3s")
    assert "details[open]" in attr["hx-trigger"] and ":popover-open" in attr["hx-trigger"]
    before = html.split('<div id="live"')[0]
    assert "<header>" not in before and "<section" not in before
    assert rest.startswith("\n<header>") and re.search(r"</main>\s*</div>\s*</body>", rest)
