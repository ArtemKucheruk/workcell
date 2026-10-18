import html as htmllib
import os
import re
import shlex
from datetime import datetime

import pytest
from conftest import git, sql, write
from controllers.test_runs import AUTH_OK, SKILL, add_task, connect, fake, project  # noqa: F401

from claude_factories.handlers import pages

STARTED = "2026-10-18T10:02:00Z"
OLD_RUN = "2026-10-18T08:00:00Z"
UNCOMMITTED = ("factory isn't committed on main: on main, run git add .claude/skills/factory .claude/agents"
               ' && git commit -m "Add factory"')
NONE = "factory isn't committed on main: Create factory on the project board, then commit it on main"
CONSOLE = '{"authMethod":"console"}'


def text(html):
    """Tags stripped, entities unescaped, whitespace collapsed."""
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", "", html)).split())


def hhmm(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")


def attrs(tag):
    """A start tag's attributes as {name: value}; a bare attribute's value is ''."""
    return dict(re.findall(r'\s([\w:-]+)(?:="([^"]*)")?', tag))


def buttons(html):
    """[(attrs, text)] of every <button> in html."""
    return [(attrs(a), text(t)) for a, t in re.findall(r"<button([^>]*)>(.*?)</button>", html, re.S)]


def button(html, label):
    [found] = [a for a, t in buttons(html) if t == label]
    return found


def labels(html):
    return {t for _, t in buttons(html)}


def badge(html):
    [(tag, body)] = re.findall(r'<p (id="claude-auth"[^>]*)>(.*?)</p>', html, re.S)
    return attrs(" " + tag), text(body)


def card(html, task_id):
    [body] = [b for tag, b in re.findall(r'(<li class="card[^>]*>)(.*?)</li>', html, re.S)
              if f'data-id="{task_id}"' in tag]
    return body


def header(html):
    return re.search(r"<header>(.*?)</header>", html, re.S)[1]


def run_status(html):
    return text(re.search(r'<span id="run-status">(.*?)</span>', html, re.S)[1])


def live(html):
    """#live's inner html: it starts the page's content and ends at the page's last </main>."""
    return html.split('<div id="live"', 1)[1].rsplit("</main>", 1)[0]


def add_run(task_id, status, error=None, session="s", started=STARTED):
    return sql("INSERT INTO runs (task_id, session_id, status, error, log_path, started_at)"
               " VALUES (?, ?, ?, ?, 'l', ?) RETURNING id", (task_id, session, status, error, started))[0][0]


def get(client, url, status=200):
    r = client.get(url)
    assert r.status_code == status, r.text
    return r.text


def board(client, project_id):
    return get(client, f"/projects/{project_id}")


def task_page(client, task_id):
    return get(client, f"/tasks/{task_id}")


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


# --- Header badge ------------------------------------------------------------------


def test_badge_on_every_page(client, project):  # AC1
    task = add_task(project)
    [[workspace]] = sql("SELECT workspace_id FROM projects WHERE id = ?", (project,))
    pages = ["/", f"/workspaces/{workspace}", f"/projects/{project}", f"/projects/{project}/code",
             f"/tasks/{task}", f"/tasks/{task}/review"]
    for url in pages + ["/tasks/999"]:
        tag, label = badge(get(client, url, 404 if url == "/tasks/999" else 200))
        assert label == "Claude: Pro ✓", url
        assert "off" not in tag.get("class", "").split(), url


@pytest.mark.parametrize("auth, label", [
    ('{"authMethod":"claude.ai","subscriptionType":"max"}', "Claude: Max ✓"),
    ('{"authMethod":"claude.ai"}', "Claude: subscription ✓"),
])
def test_badge_plan(client, fake, auth, label):  # AC2
    fake(auth=auth)
    assert badge(get(client, "/"))[1] == label


@pytest.mark.parametrize("auth, auth_code", [(CONSOLE, 0), ("not json", 0), (AUTH_OK, 1)])
def test_badge_off(client, fake, auth, auth_code):  # AC3
    fake(auth=auth, auth_code=auth_code)
    html = get(client, "/")
    tag, label = badge(html)
    assert label == "API key — runs disabled"
    assert "off" in tag["class"].split()
    assert re.search(r"#claude-auth\.off\s*\{[^}]*color:\s*light-dark\(#cf222e, #f85149\)", html)


def test_badge_check_env_and_cwd(client, fake, monkeypatch):  # AC4
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK"):
        monkeypatch.setenv(name, "x")
    get(client, "/")
    seen = fake.recorded("auth")
    assert seen["argv"] == ["auth", "status"]
    assert not {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK"} & set(seen["env"])
    assert os.path.realpath(seen["cwd"]) == os.path.realpath(os.environ["FCTL_HOME"])


def test_badge_cached_60s(client, tmp_path, monkeypatch):  # AC5
    calls = tmp_path / "auth-calls"
    claude = tmp_path / "bin" / "claude"  # appends a line per call, so every call counts
    claude.write_text(f"#!/bin/sh\necho x >> {shlex.quote(str(calls))}\necho {shlex.quote(AUTH_OK)}\n")
    clock = [1000.0]
    monkeypatch.setattr(pages, "monotonic", lambda: clock[0])
    count = lambda: len(calls.read_text().splitlines()) if calls.exists() else 0  # noqa: E731
    get(client, "/")
    get(client, "/")
    assert count() == 1
    clock[0] += 61
    assert badge(get(client, "/"))[1] == "Claude: Pro ✓"
    assert count() == 2


# --- Board -------------------------------------------------------------------------


def test_backlog_card_run(client, project):  # AC6
    backlog, review, done = add_task(project), add_task(project, status="review", stage="human_review"), \
        add_task(project, status="done")
    for tid, status in ((review, "succeeded"), (done, "failed")):
        add_run(tid, status)
    html = board(client, project)
    run = button(card(html, backlog), "Run")
    assert run["hx-post"] == f"/api/tasks/{backlog}/run" and "disabled" not in run
    for tid in (review, done):
        assert not {"Run", "Retry"} & labels(card(html, tid))


def test_run_next_enabled(client, project):  # AC7
    run_next = button(header(board(client, project)), "Run next ▶")
    assert run_next["hx-post"] == f"/api/projects/{project}/run-next" and "disabled" not in run_next


def test_running_card(client, project):  # AC8
    tid = add_task(project, status="in_progress", stage="build")
    add_run(tid, "succeeded", started=OLD_RUN)
    add_run(tid, "running")
    body = card(board(client, project), tid)
    assert "● running · build" in text(body) and f"started {hhmm(STARTED)}" in text(body)
    assert not {"Run", "Retry"} & labels(body)
    sql("UPDATE tasks SET stage = NULL WHERE id = ?", (tid,))
    shown = text(card(board(client, project), tid))
    assert "● running" in shown and "● running ·" not in shown



@pytest.mark.parametrize("status", ["failed", "stopped", "succeeded"])
def test_stalled_card(client, project, status):  # AC9
    tid, bare = add_task(project, status="in_progress", stage="build"), add_task(project, status="in_progress")
    for t in (tid, bare):
        add_run(t, status)
    html = board(client, project)
    body = card(html, tid)
    assert "stalled · build" in text(body) and "● running" not in text(body)
    assert button(body, "Retry")["hx-post"] == f"/api/tasks/{tid}/run"
    assert "stalled" in text(card(html, bare)) and "stalled ·" not in text(card(html, bare))


def test_in_progress_without_runs(client, project):  # AC10
    tid = add_task(project, status="in_progress", stage="build")
    body = card(board(client, project), tid)
    assert not buttons(body)
    assert text(body) == f"#{tid} t build"


@pytest.mark.parametrize("state, detail", [("uncommitted", UNCOMMITTED), ("none", NONE)])
def test_board_factory_not_ready(client, unready, state, detail):  # AC11
    project_id = unready(state)
    backlog, stalled = add_task(project_id), add_task(project_id, status="in_progress", stage="build")
    add_run(stalled, "failed")
    html = board(client, project_id)
    assert "disabled" in button(header(html), "Run next ▶")
    assert "disabled" in button(card(html, backlog), "Run")
    assert "disabled" in button(card(html, stalled), "Retry")
    assert detail in text(header(html))


def test_board_api_key(client, project, fake):  # AC12
    fake(auth=CONSOLE)
    backlog, stalled = add_task(project), add_task(project, status="in_progress", stage="build")
    add_run(stalled, "stopped")
    html = board(client, project)
    assert "disabled" in button(header(html), "Run next ▶")
    assert "disabled" in button(card(html, backlog), "Run")
    assert "disabled" in button(card(html, stalled), "Retry")


# --- Task page ---------------------------------------------------------------------


def test_task_backlog_run(client, project):  # AC13
    tid = add_task(project)
    html = task_page(client, tid)
    run = button(live(html), "Run")
    assert run["hx-post"] == f"/api/tasks/{tid}/run" and "disabled" not in run
    assert not {"Stop", "Retry"} & labels(html)
    assert "run #" not in text(html) and 'id="run-log"' not in html
    assert "claude --resume" not in text(html) and "Stop the run to take over." not in text(html)


def test_task_running_stop(client, project):  # AC14
    tid = add_task(project, status="in_progress", stage="build")
    rid = add_run(tid, "running")
    inside = live(task_page(client, tid))
    assert button(inside, "Stop")["hx-post"] == f"/api/runs/{rid}/stop"
    assert run_status(inside) == f"run #{rid} running · started {hhmm(STARTED)}"
    assert not {"Run", "Retry"} & labels(inside)


@pytest.mark.parametrize("status, error, shown", [
    ("failed", "exit code 3", ": exit code 3"), ("stopped", None, ""), ("succeeded", None, ""), ("failed", None, ""),
])
def test_task_stalled_retry(client, project, status, error, shown):  # AC15
    tid = add_task(project, status="in_progress", stage="build")
    rid = add_run(tid, status, error)
    inside = live(task_page(client, tid))
    assert button(inside, "Retry")["hx-post"] == f"/api/tasks/{tid}/run"
    assert run_status(inside) == f"run #{rid} {status}{shown}"


def test_task_run_error_escaped(client, project):  # AC16
    tid = add_task(project, status="in_progress", stage="build")
    add_run(tid, "failed", "<script>alert(1)</script>")
    html = task_page(client, tid)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert" not in html


def test_task_review_and_done(client, project):  # AC17
    review, done = add_task(project, status="review", stage="human_review"), add_task(project, status="done")
    for tid in (review, done):
        rid = add_run(tid, "succeeded")
        inside = live(task_page(client, tid))
        assert not {"Run", "Stop", "Retry"} & labels(inside)
        assert run_status(inside) == f"run #{rid} succeeded"
    rid = add_run(review, "running")
    assert button(live(task_page(client, review)), "Stop")["hx-post"] == f"/api/runs/{rid}/stop"


@pytest.mark.parametrize("case", ["uncommitted", "api key"])
def test_task_runs_disabled(client, project, unready, fake, case):  # AC18
    if case == "uncommitted":
        project = unready("uncommitted")
    else:
        fake(auth=CONSOLE)
    backlog, stalled = add_task(project), add_task(project, status="in_progress", stage="build")
    add_run(stalled, "failed")
    assert "disabled" in button(live(task_page(client, backlog)), "Run")
    html = task_page(client, stalled)
    assert "disabled" in button(live(html), "Retry")
    assert (UNCOMMITTED in text(html)) == (case == "uncommitted")
    running = add_run(backlog, "running")
    stop = button(live(task_page(client, backlog)), "Stop")
    assert stop["hx-post"] == f"/api/runs/{running}/stop" and "disabled" not in stop


def test_task_run_log(client, project):  # AC19
    tid, bare = add_task(project, status="in_progress", stage="build"), add_task(project)
    add_run(tid, "failed")
    rid = add_run(tid, "stopped")
    html = task_page(client, tid)
    [tag] = re.findall(r"</main>\s*</div>\s*<details (id=\"run-log\"[^>]*)>", html)
    found = attrs(" " + tag)
    assert found["data-run"] == str(rid) and "open" not in found
    script = html.split('<details id="run-log"', 1)[1]
    assert "/api/runs/" in script and "/log?after=" in script
    assert 'id="run-log"' not in task_page(client, bare)


@pytest.mark.parametrize("worktree", ["/tmp/wt/7-x", "/tmp/my wt/7-x"])
def test_task_takeover(client, project, worktree):  # AC20
    tid = add_task(project, status="in_progress", stage="build")
    sql("UPDATE tasks SET worktree_path = ? WHERE id = ?", (worktree, tid))
    add_run(tid, "failed", session="abc-123")
    command = f"cd {shlex.quote(worktree)} && claude --resume {shlex.quote('abc-123')}"
    shown = text(task_page(client, tid))
    assert command in shown and "Stop the run to take over." not in shown
    if " " in worktree:
        assert f"cd '{worktree}' &&" in shown
    add_run(tid, "running", session="def")
    shown = text(task_page(client, tid))
    assert "claude --resume" not in shown and "Stop the run to take over." in shown


def test_task_no_takeover(client, project):  # AC20
    no_run, no_worktree = add_task(project), add_task(project, status="in_progress", stage="build")
    sql("UPDATE tasks SET worktree_path = '/tmp/wt' WHERE id = ?", (no_run,))
    add_run(no_worktree, "failed")
    for tid in (no_run, no_worktree):
        shown = text(task_page(client, tid))
        assert "claude --resume" not in shown and "Stop the run to take over." not in shown
    sql("UPDATE runs SET status = 'running'")  # running, still no worktree: neither
    assert "Stop the run to take over." not in text(task_page(client, no_worktree))
