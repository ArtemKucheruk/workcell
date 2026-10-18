import re
from datetime import UTC, datetime, timedelta

import pytest
from conftest import sql
from test_review import section, text

OLD = "2026-01-01T00:00:00Z"
STATUSES = ("backlog", "in_progress", "review", "done")
TILES = {"backlog": "Backlog", "in_progress": "In progress", "review": "Review", "done": "Done",
         "waiting": "Waiting on me", "escalated": "Escalated", "running": "Running now",
         "done_week": "Done this week", "runs_week": "Runs this week"}


def ago(days):
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def workspace(name):
    return sql("INSERT INTO workspaces (name, created_at) VALUES (?, ?) RETURNING id", (name, OLD))[0][0]


def project(workspace_id, name):
    return sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
               " VALUES (?, ?, ?, 'main', ?) RETURNING id",
               (workspace_id, name, f"/code/{workspace_id}/{name}", OLD))[0][0]


def task(project_id, title="t", status="backlog", stage=None, done_at=None):
    return sql("INSERT INTO tasks (project_id, title, status, stage, position, created_at, updated_at, done_at)"
               " VALUES (?, ?, ?, ?, 1, ?, ?, ?) RETURNING id",
               (project_id, title, status, stage, OLD, OLD, done_at))[0][0]


def run(task_id, status, started_at):
    return sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
               " VALUES (?, 's', ?, 'log', ?) RETURNING id", (task_id, status, started_at))[0][0]


def add_rounds(task_id, count):
    for n in range(1, count + 1):
        sql("INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, ?, 'initial', 'abc', ?)",
            (task_id, n, OLD))


def page(client, query=""):
    r = client.get("/" + query)
    assert r.status_code == 200, r.text
    return r.text


def tile(html, key):
    """The tile's text, and whether it is aria-current."""
    found = re.search(rf'<li><a href="/\?show={key}"( aria-current="page")?>(.*?)</a></li>', html, re.S)
    return text(found[2]), bool(found[1])


def body_rows(html):
    """The raw html of each <tbody> row, in page order."""
    tbodies = "".join(re.findall(r"<tbody>(.*?)</tbody>", html, re.S))
    return re.findall(r"<tr>(.*?)</tr>", tbodies, re.S)


def task_ids(html):
    return [int(i) for i in re.findall(r'<a href="/tasks/(\d+)">', html)]


@pytest.fixture
def two(client):
    """Project api in workspace work, and project web in workspace home."""
    return project(workspace("work"), "api"), project(workspace("home"), "web")


# --- Tiles ---------------------------------------------------------------------------


def test_empty_database(client):  # AC1
    r = client.get("/")
    assert r.status_code == 200
    assert r.template.name == "index.html"
    assert len(re.findall(r'<li><a href="/\?show=', r.text)) == 9
    for key, label in TILES.items():
        assert tile(r.text, key) == (f"{label} 0", False)
    assert "No projects yet." in r.text


def test_status_tiles(client, two):  # AC2
    api, web = two
    task(api), task(web)
    task(api, status="in_progress", stage="build")
    task(web, status="review", stage="human_review")
    task(api, status="done", done_at=OLD)
    html = page(client)
    for key, count in [("backlog", 2), ("in_progress", 1), ("review", 1), ("done", 1)]:
        assert tile(html, key)[0] == f"{TILES[key]} {count}"  # the regex holds the /?show=<key> link


def test_waiting_tile(client, two):  # AC3
    api, web = two
    task(api, status="review", stage="human_review")
    task(web, status="review", stage="human_review")
    task(api, status="review", stage="escalated")
    assert tile(page(client), "waiting")[0] == "Waiting on me 2"


def test_escalated_tile(client, two):  # AC4
    api, web = two
    task(api, status="review", stage="escalated")
    task(web, status="review", stage="human_review")
    assert tile(page(client), "escalated")[0] == "Escalated 1"


def test_running_tile(client, two):  # AC5
    api, web = two
    run(task(api, status="in_progress", stage="build"), "running", ago(0))
    run(task(web), "succeeded", ago(1))
    run(task(web), "failed", ago(1))
    assert tile(page(client), "running")[0] == "Running now 1"


def test_done_this_week_tile(client, two):  # AC6
    api, web = two
    task(api, status="done", done_at=ago(6))
    task(web, status="done", done_at=ago(8))
    assert tile(page(client), "done_week")[0] == "Done this week 1"


def test_runs_this_week_tile(client, two):  # AC7
    api, web = two
    t = task(api, status="in_progress", stage="build")
    run(t, "running", ago(0))
    run(t, "failed", ago(6))
    run(task(web), "succeeded", ago(6))
    run(task(web), "succeeded", ago(8))
    assert tile(page(client), "runs_week")[0] == "Runs this week 3"


# --- Filtered lists ------------------------------------------------------------------


@pytest.mark.parametrize("status", STATUSES)
def test_status_list(client, two, status):  # AC8
    api, web = two
    ids = {s: (task(api, f"{s} a", s), task(web, f"{s} b", s)) for s in STATUSES}
    html = section(page(client, f"?show={status}"), "list")
    a, b = ids[status]
    assert sorted(task_ids(html)) == [a, b]
    for task_id, title, project_id, name in [(a, f"{status} a", api, "api"), (b, f"{status} b", web, "web")]:
        assert re.search(rf'<td><a href="/tasks/{task_id}">#{task_id} {title}</a></td>\s*'
                         rf'<td><a href="/projects/{project_id}">{name}</a></td>', html)


@pytest.fixture
def mixed(two):
    """One task per tile key, plus tasks and runs those tiles must leave out."""
    api, web = two
    ids = {"waiting": task(api, "waiting", "review", "human_review"),
           "escalated": task(web, "escalated", "review", "escalated"),
           "running": task(api, "running", "in_progress", "build"),
           "done_week": task(web, "done recently", "done", done_at=ago(6))}
    run(ids["running"], "running", ago(0))
    task(api, "done long ago", "done", done_at=ago(8))
    run(task(web, "ran", "in_progress", "agent_review"), "succeeded", ago(1))
    run(task(api, "failed"), "failed", ago(1))
    return ids


@pytest.mark.parametrize("key", ["waiting", "escalated", "running", "done_week"])
def test_tile_lists(client, mixed, key):  # AC9
    html = page(client, f"?show={key}")
    assert task_ids(section(html, "list")) == [mixed[key]]
    assert tile(html, key)[0] == f"{TILES[key]} 1"


def test_runs_week_list(client, two):  # AC10
    api, web = two
    first, second = task(api, "first"), task(web, "second")
    new, mid, old = run(first, "running", ago(0)), run(second, "failed", ago(6)), run(first, "succeeded", ago(8))
    html = section(page(client, "?show=runs_week"), "list")
    rows = body_rows(html)
    assert len(rows) == 2
    for row, (run_id, task_id, title, status) in zip(rows, [(new, first, "first", "running"),
                                                            (mid, second, "second", "failed")]):
        assert f"<td>run #{run_id}</td>" in row
        assert f'<a href="/tasks/{task_id}">#{task_id} {title}</a>' in row
        assert f"<td>{status}</td>" in row
    assert f"run #{old}<" not in html


def test_list_heading_and_current_tile(client):  # AC11
    for key, label in TILES.items():
        html = page(client, f"?show={key}")
        assert re.findall(r"<h2>(.*?)</h2>", section(html, "list")) == [label]
        assert [k for k in TILES if tile(html, k)[1]] == [key]
    html = page(client)
    assert section(html, "list") is None
    assert not any(tile(html, k)[1] for k in TILES)


def test_empty_lists(client, two):  # AC12
    for key in TILES:
        html = section(page(client, f"?show={key}"), "list")
        assert ("No runs." if key == "runs_week" else "No tasks.") in html
        assert "<table" not in html


def test_unknown_show(client, two):  # AC13
    task(two[0])
    html = page(client, "?show=bogus")
    assert section(html, "list") is None
    assert not any(tile(html, k)[1] for k in TILES)
    assert tile(html, "backlog")[0] == "Backlog 1"


# --- Open tasks ----------------------------------------------------------------------


def test_open_tasks_table(client):  # AC14
    work = workspace("work")
    api, archive = project(work, "api"), project(work, "archive")
    for status in ["backlog", "backlog", "in_progress", "review", "done", "done"]:
        task(api, status=status)
    task(archive, status="done")
    html = section(page(client), "open-tasks")
    assert [text(r) for r in body_rows(html)] == ["work", "api 2 1 1"]
    assert f'<th colspan="4" scope="rowgroup"><a href="/workspaces/{work}">work</a></th>' in html
    assert f'<td><a href="/projects/{api}">api</a></td>' in html
    assert f"/projects/{archive}" not in html


def test_open_tasks_order(client):  # AC15
    zeta, alpha = workspace("zeta"), workspace("alpha")
    for ws, name in [(zeta, "b"), (zeta, "a"), (alpha, "z"), (alpha, "y")]:
        task(project(ws, name))
    rows = [text(r) for r in body_rows(section(page(client), "open-tasks"))]
    assert rows == ["alpha", "y 1 0 0", "z 1 0 0", "zeta", "a 1 0 0", "b 1 0 0"]


def test_no_open_tasks(client, two):  # AC16
    task(two[0], status="done", done_at=OLD)
    html = section(page(client), "open-tasks")
    assert "No open tasks." in html
    assert "<table" not in html


# --- Rounds per task -----------------------------------------------------------------


def test_rounds_per_task(client, two):  # AC17
    api, web = two
    done = []
    for title, rounds, days, project_id in [("one", 1, 3, api), ("two", 2, 2, web), ("four", 4, 1, api)]:
        t = task(project_id, title, "done", done_at=ago(days))
        add_rounds(t, rounds)
        done.append((t, title, rounds))
    html = section(page(client), "rounds")
    assert re.search(r"Average <strong>2\.3</strong>\s*· Max <strong>4</strong>", html)
    rows = body_rows(html)
    assert len(rows) == 3
    for row, (task_id, title, rounds) in zip(rows, reversed(done)):  # newest done first
        assert f'<a href="/tasks/{task_id}">#{task_id} {title}</a>' in row
        assert f'<td class="num">{rounds}</td>' in row


def test_rounds_leave_out(client, two):  # AC18
    api, _ = two
    counted = task(api, "counted", "done", done_at=ago(29))
    add_rounds(counted, 2)
    add_rounds(task(api, "old", "done", done_at=ago(31)), 3)
    add_rounds(task(api, "open", "review", "human_review"), 5)
    task(api, "no rounds", "done", done_at=ago(1))
    html = section(page(client), "rounds")
    assert task_ids(html) == [counted]
    assert re.search(r"Average <strong>2\.0</strong>\s*· Max <strong>2</strong>", html)


def test_no_rounds(client, two):  # AC19
    add_rounds(task(two[0], "old", "done", done_at=ago(31)), 2)
    html = section(page(client), "rounds")
    assert "No tasks done in the last 30 days." in html
    assert "Average" not in html and "Max" not in html


def test_title_escaped(client, two):  # AC20
    t = task(two[0], "<script>x</script>")
    html = page(client, "?show=backlog")
    assert f"#{t} &lt;script&gt;x&lt;/script&gt;" in section(html, "list")
    assert "<script>x</script>" not in html
