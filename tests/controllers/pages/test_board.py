import re

import pytest
from conftest import git, sql

H = {"X-Requested-By": "fctl"}
OLD = "2026-01-01T00:00:00Z"
SKILL = ".claude/skills/factory/SKILL.md"
COLUMNS = ["backlog", "in_progress", "review", "done"]


def connect(client, path="/code/api"):
    body = {"path": str(path), "workspace": "personal", "name": "api", "default_branch": "main"}
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture
def project(client):
    return connect(client)


def add_task(project_id, status="backlog", position=1.0, stage=None, title="t"):
    return sql(
        "INSERT INTO tasks (project_id, title, status, stage, position, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (project_id, title, status, stage, position, OLD, OLD),
    )[0][0]


def add_round(task_id, n, files=(), verdicts=None):
    round_id = sql(
        "INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, ?, 'initial', 'abc', ?)"
        " RETURNING id", (task_id, n, OLD),
    )[0][0]
    for i, (additions, deletions) in enumerate(files):
        sql("INSERT INTO round_files (round_id, path, change, additions, deletions, patch)"
            " VALUES (?, ?, 'modified', ?, ?, '')", (round_id, f"f{i}.py", additions, deletions))
    for reviewer, verdict in (verdicts or {}).items():
        sql("INSERT INTO verdicts (round_id, reviewer, verdict, body_md, created_at) VALUES (?, ?, ?, '', ?)",
            (round_id, reviewer, verdict, OLD))


def page(client, project_id):
    r = client.get(f"/projects/{project_id}")
    assert r.status_code == 200
    return r.text


def text(html):
    """Tags stripped, whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


def columns(html):
    """{status: column inner html}, in page order."""
    return dict(re.findall(r'<section class="column" data-status="(\w+)">(.*?)</section>', html, re.S))


def cards(html):
    """[(the card's <li> start tag, its inner html)], in page order."""
    return re.findall(r'(<li class="card[^>]*>)(.*?)</li>', html, re.S)


def card(html, task_id):
    [found] = [c for c in cards(html) if f'data-id="{task_id}"' in c[0]]
    return found


def ids(html):
    return [int(re.search(r'data-id="(\d+)"', tag)[1]) for tag, _ in cards(html)]


def board(html):
    """The #board start tag's attributes and its inner html (it holds no nested <div>)."""
    return re.search(r'<div id="board"([^>]*)>(.*?)</div>', html, re.S).groups()


def counts():
    return sql("SELECT (SELECT COUNT(*) FROM tasks), (SELECT COUNT(*) FROM events)")[0]


# --- Header ------------------------------------------------------------------------


def test_page_renders(client, project):  # AC1 (002's AC26–AC29 stay in tests/test_projects.py)
    r = client.get(f"/projects/{project}")
    assert r.status_code == 200
    assert r.template.name == "project.html"


def test_code_link(client, project):  # AC2
    assert f'<a href="/projects/{project}/code">Code</a>' in page(client, project)


@pytest.mark.parametrize("state, expected", [
    ("none", "Factory: none"), ("uncommitted", "Factory: uncommitted"), ("ready", "Factory: ready ✓"),
])
def test_factory_state(client, repo, state, expected):  # AC3
    if state != "none":
        (repo / SKILL).parent.mkdir(parents=True)
        (repo / SKILL).write_text("# factory\n")
    if state == "ready":
        git(repo, "add", SKILL)
        git(repo, "commit", "-q", "-m", "Add factory")
    pid = connect(client, repo)
    assert re.findall(r"<span>(Factory: [^<]*)</span>", page(client, pid)) == [expected]


def test_run_next_disabled(client, project):  # AC4
    [attrs] = re.findall(r"<button([^>]*)>Run next ▶</button>", page(client, project))
    assert " disabled" in attrs


# --- Columns -----------------------------------------------------------------------


def test_four_columns_in_order(client, project):  # AC5
    html = page(client, project)
    assert list(columns(html)) == COLUMNS
    assert html.count('class="column"') == 4


def test_column_counts(client, project):  # AC6
    for status, n in (("backlog", 2), ("in_progress", 1), ("done", 3)):
        for _ in range(n):
            add_task(project, status)
    other = connect(client, "/code/other")
    b_task = add_task(other, title="only-in-B")
    html = page(client, project)
    headings = [text(re.search(r"<h2>(.*?)</h2>", col, re.S)[1]) for col in columns(html).values()]
    assert headings == ["Backlog 2", "In progress 1", "Review 0", "Done 3"]
    assert f'data-id="{b_task}"' not in html and "only-in-B" not in html


def test_backlog_order(client, project):  # AC7
    a = add_task(project, position=2.0)
    b = add_task(project, position=1.0)
    c = add_task(project, position=1.0)
    assert ids(columns(page(client, project))["backlog"]) == [b, c, a]
    api = client.get(f"/api/projects/{project}/tasks").json()
    assert [t["id"] for t in api] == [b, c, a]


# --- Cards -------------------------------------------------------------------------


def test_card_drag_attributes(client, project):  # AC8
    by_status = {s: add_task(project, s, position=2.5 if s == "backlog" else 1.0) for s in COLUMNS}
    html = page(client, project)
    for status, col in columns(html).items():
        [(tag, _)] = cards(col)
        assert f'data-id="{by_status[status]}"' in tag
        assert 'draggable="true"' in tag
    assert 'data-position="2.5"' in card(html, by_status["backlog"])[0]
    assert 'data-position="1.0"' in card(html, by_status["done"])[0]


def test_card_id_title_link(client, project):  # AC9
    tid = add_task(project, title="Export CSV")
    _, body = card(page(client, project), tid)
    assert re.search(rf'<a href="/tasks/{tid}"[^>]*>#{tid} Export CSV</a>', body)


def test_title_escaped(client, project):  # AC10
    add_task(project, title="<script>alert(1)</script>")
    html = page(client, project)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)" not in html


def test_stage_text(client, project):  # AC11
    running = add_task(project, "in_progress", stage="agent_review")
    idle = add_task(project)
    html = page(client, project)
    assert "agent_review" in text(card(html, running)[1])
    assert text(card(html, idle)[1]) == f"#{idle} t Run"  # 014 AC21: Backlog cards have [Run]


def test_human_review_card(client, project):  # AC12
    tid = add_task(project, "review", stage="human_review")
    tag, body = card(page(client, project), tid)
    assert "waiting on you" in text(body)
    assert "escalated" not in tag


def test_escalated_card(client, project):  # AC13
    tid = add_task(project, "review", stage="escalated")
    tag, body = card(page(client, project), tid)
    assert re.search(r'class="[^"]*\bescalated\b', tag)
    assert "⚠ NEEDS YOU — escalated" in text(body)


@pytest.fixture
def reviewed(project):
    """An in_progress task: round 1 all CHANGES, round 2 sec/ux PASS, no ui verdict, code CHANGES."""
    tid = add_task(project, "in_progress")
    add_round(tid, 1, files=[(7, 7)], verdicts=dict.fromkeys(["security", "ux", "ui", "code"], "CHANGES"))
    add_round(tid, 2, files=[(100, 5), (26, 4)],
              verdicts={"security": "PASS", "ux": "PASS", "code": "CHANGES"})
    return tid


def test_chips_latest_round(client, project, reviewed):  # AC14
    _, body = card(page(client, project), reviewed)
    [chips] = re.findall(r'<p class="chips">(.*?)</p>', body, re.S)
    assert text(chips) == "r2 sec✓ ux✓ ui· co✗"
    assert re.findall(r'title="([^"]*)"', chips) == [
        "security: PASS", "ux: PASS", "ui: pending", "code: CHANGES"]
    assert "r1" not in text(body)


def test_additions_deletions(client, project, reviewed):  # AC15
    _, body = card(page(client, project), reviewed)
    assert "+126 −9" in text(body)
    assert "+7" not in text(body)


def test_no_rounds_no_chips(client, project):  # AC16
    tids = [add_task(project, status) for status in ("backlog", "in_progress", "review")]
    html = page(client, project)
    for tid in tids:
        _, body = card(html, tid)
        assert 'class="chips"' not in body
        assert text(body) == f"#{tid} t" + (" Run" if tid == tids[0] else "")  # 014 AC21: Backlog's [Run]


def test_done_round_count(client, project):  # AC17
    three, one, none = (add_task(project, "done") for _ in range(3))
    for n in (1, 2, 3):
        add_round(three, n, files=[(1, 1)], verdicts={"code": "PASS"})
    add_round(one, 1, files=[(1, 1)], verdicts={"code": "PASS"})
    html = page(client, project)
    assert text(card(html, three)[1]) == f"#{three} t 3 rounds"
    assert text(card(html, one)[1]) == f"#{one} t 1 round"
    assert text(card(html, none)[1]) == f"#{none} t"


# --- Empty states ------------------------------------------------------------------

EMPTY_BACKLOG = 'No tasks. Add one with + New task, or run fctl task add "title" in the repo.'


def test_empty_board(client, project):  # AC18
    cols = columns(page(client, project))
    assert {s: text(c) for s, c in cols.items()} == {
        "backlog": f"Backlog 0 {EMPTY_BACKLOG}",
        "in_progress": "In progress 0 No tasks",
        "review": "Review 0 No tasks",
        "done": "Done 0 No tasks",
    }


def test_only_done_tasks(client, project):  # AC19
    tid = add_task(project, "done")
    cols = {s: text(c) for s, c in columns(page(client, project)).items()}
    assert cols == {
        "backlog": f"Backlog 0 {EMPTY_BACKLOG}",
        "in_progress": "In progress 0 No tasks",
        "review": "Review 0 No tasks",
        "done": f"Done 1 #{tid} t",
    }


# --- Polling -----------------------------------------------------------------------


def test_board_polls(client, project):  # AC20
    attrs, inner = board(page(client, project))
    assert list(columns(inner)) == COLUMNS
    assert f'hx-get="/projects/{project}"' in attrs
    assert re.search(r'hx-trigger="every 3s[^"]*"', attrs)
    assert 'hx-select="#board"' in attrs
    assert 'hx-swap="outerHTML"' in attrs


def test_board_holds_no_forms(client, project):  # AC21
    html = page(client, project)
    _, inner = board(html)
    assert "<form" not in inner and "board-error" not in inner
    assert f'hx-post="/projects/{project}/tasks"' in html
    assert f'hx-post="/projects/{project}/workspace"' in html
    assert 'id="board-error"' in html


# --- Drag and drop -----------------------------------------------------------------


def test_board_error_element(client, project):  # AC22
    assert re.search(r'<(\w+) id="board-error" role="alert"></\1>', page(client, project))


def test_drag_script(client, project):  # AC23
    [script] = re.findall(r"<script>(.*?)</script>", page(client, project), re.S)
    for needed in ("/api/tasks/", '"PATCH"', "X-Requested-By"):
        assert needed in script
    for banned in ("GET", "POST", "PUT", "DELETE", "XMLHttpRequest", "htmx.ajax", "stage"):
        assert banned not in script
    assert script.count("fetch(") == 1


# --- + New task --------------------------------------------------------------------


def test_new_task_form(client, project):  # AC24
    [details] = re.findall(r"<details>(.*?)</details>", page(client, project), re.S)
    assert details.strip().startswith("<summary>+ New task</summary>")
    [form] = re.findall(rf'<form hx-post="/projects/{project}/tasks">(.*?)</form>', details, re.S)
    [title] = re.findall(r'<input [^>]*name="title"[^>]*>', form)
    assert 'type="text"' in title and " required" in title
    assert '<textarea name="description_md"' in form
    assert re.findall(r"<button[^>]*>(.*?)</button>", form) == ["Add task"]


def post_task(client, project_id, data, headers=H):
    return client.post(f"/projects/{project_id}/tasks", data=data, headers=headers)


def test_new_task_post(client, project):  # AC25
    add_task(project, position=4.0)
    add_task(project, "done", position=10.0)
    add_task(connect(client, "/code/other"), position=50.0)
    r = post_task(client, project, {"title": "Export CSV", "description_md": "**Bold** text"})
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == f"/projects/{project}"
    [(tid, *row)] = sql("SELECT id, project_id, title, description_md, status, stage, position FROM tasks"
                        " WHERE title = 'Export CSV'")
    assert row == [project, "Export CSV", "**Bold** text", "backlog", None, 5.0]
    assert sql("SELECT task_id, actor, from_status, to_status FROM events") == [(tid, "me", None, "backlog")]


def test_new_task_no_description(client, project):  # AC26
    r = post_task(client, project, {"title": "Export CSV"})
    assert r.status_code == 204
    assert sql("SELECT description_md FROM tasks") == [("",)]


@pytest.mark.parametrize("data", [{"title": ""}, {"title": "   "}, {}])
def test_new_task_blank_title(client, project, data):  # AC27
    assert post_task(client, project, data).status_code == 422
    assert counts() == (0, 0)


def test_new_task_unknown_project(client):  # AC28
    assert post_task(client, 999, {"title": "Export CSV"}).status_code == 404
    assert counts() == (0, 0)


def test_new_task_needs_header(client, project):  # AC29
    assert post_task(client, project, {"title": "Export CSV"}, headers={}).status_code == 403
    assert counts() == (0, 0)


def test_new_task_lands_last(client, project):  # AC30
    add_task(project, position=1.0)
    add_task(project, position=3.0)
    post_task(client, project, {"title": "Export CSV"})
    [tid] = sql("SELECT id FROM tasks WHERE title = 'Export CSV'")[0]
    backlog = columns(page(client, project))["backlog"]
    assert ids(backlog)[-1] == tid
    assert text(cards(backlog)[-1][1]) == f"#{tid} Export CSV Run"  # 014 AC21: Backlog cards have [Run]
