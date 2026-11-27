import json
import os
import shutil
import socket
import sys
import time
import uuid
from pathlib import Path

import pytest
from conftest import ORIGINAL_PATH, commit, git, sql, write, wt_calls

from claude_factories.adapters import git as git_adapter
from claude_factories.adapters.claude import SubprocessClaude
from claude_factories.adapters.git import WT_MISSING, SubprocessGit
from claude_factories.lib.slug import slug
from claude_factories.server.deps import get_claude, get_git

H = {"X-Requested-By": "fctl"}
OLD = "2026-01-01T00:00:00Z"
SKILL = ".claude/skills/factory/SKILL.md"
READY = "# factory\n\n1. spec → `fctl stage <id> spec`.\n"  # 059: the app's template calls fctl stage
LEGACY = "# factory\n"  # 059: the file-based bootstrap loop doesn't
LEGACY_HINT = "this repo runs the file-based /factory loop: Create factory with Overwrite, then commit it on main"
AUTH_OK = '{"loggedIn":true,"authMethod":"claude.ai","subscriptionType":"pro"}'
SYSTEM = '{"type":"system","subtype":"init"}'
FCTL_ALLOWED = [
    "Bash(fctl show *)", "Bash(fctl diff *)", "Bash(fctl spec *)", "Bash(fctl submit *)",
    "Bash(fctl verdict *)", "Bash(fctl comment *)", "Bash(fctl decide *)", "Bash(fctl stage *)",
    "Bash(fctl round *)", "Bash(git status *)", "Bash(git diff *)",
]
STRIPPED = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOO")

FAKE = """#!{python}
import json, os, sys
def record(name):
    with open(os.path.join(os.environ["FAKE_CLAUDE_RECORDS"], name), "w") as f:
        json.dump({{"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ),
                   "pid": os.getpid(), "pgid": os.getpgrp()}}, f)
if sys.argv[1:] == ["auth", "status"]:
    record("auth")
    if {delete_self!r}:
        os.remove(__file__)
    print({auth!r})
    sys.exit({auth_code!r})
record("run")
if {long!r}:  # 013: one line, a `sleep 60` child in this process group, then 60 s of sleep
    import subprocess, time
    print({system!r}, flush=True)
    child = subprocess.Popen(["sleep", "60"])
    path = os.path.join(os.environ["FAKE_CLAUDE_RECORDS"], "child")
    with open(path + ".tmp", "w") as f:
        f.write(str(child.pid))
    os.replace(path + ".tmp", path)
    time.sleep(60)
lines = {lines!r}
if lines is None:
    sid = sys.argv[sys.argv.index("--session-id") + 1]
    lines = [{system!r}, json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                                      "session_id": sid, "result": "ok"}})]
    print("warn", file=sys.stderr)
for line in lines:
    print(line)
sys.exit({code!r})
"""


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """fake(**behaviour) writes tmp_path/bin/claude; records() reads what it saw (Setup)."""
    records = tmp_path / "records"
    records.mkdir()
    monkeypatch.setenv("FAKE_CLAUDE_RECORDS", str(records))

    def install(auth=AUTH_OK, auth_code=0, lines=None, code=0, delete_self=False, long=False):
        claude = tmp_path / "bin" / "claude"
        claude.write_text(FAKE.format(python=sys.executable, auth=auth, auth_code=auth_code, lines=lines,
                                      code=code, delete_self=delete_self, system=SYSTEM, long=long))
        claude.chmod(0o755)

    def recorded(name):
        path = records / name
        return json.loads(path.read_text()) if path.exists() else None

    def clear():
        for f in records.iterdir():
            f.unlink()

    install()
    install.recorded, install.clear, install.invoked = recorded, clear, lambda: any(records.iterdir())
    return install


@pytest.fixture
def project(client, repo, fake):
    """The repo connected with main, `pytest -q`, and SKILL.md committed on main."""
    commit(repo, {SKILL: READY})
    return connect(client, repo)


@pytest.fixture
def legacy(client, repo, fake):
    """059: as `project`, but the committed SKILL.md is the file-based loop's, without `fctl stage`."""
    commit(repo, {SKILL: LEGACY})
    return connect(client, repo)


def connect(client, repo, test_cmd="pytest -q"):
    body = {"path": str(repo), "workspace": "personal", "name": "repo", "default_branch": "main",
            "test_cmd": test_cmd}
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def add_task(project_id, title="t", status="backlog", stage=None, position=1.0):
    return sql(
        "INSERT INTO tasks (project_id, title, status, stage, position, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (project_id, title, status, stage, position, OLD, OLD),
    )[0][0]


def add_running_run(task_id):
    return sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
               " VALUES (?, 's', 'running', 'l', ?) RETURNING id", (task_id, OLD))[0][0]


def run(client, task_id):
    return client.post(f"/api/tasks/{task_id}/run", headers=H)


def wait(run_id):
    """Until the run row leaves `running`; the row."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        row = run_row(run_id)
        if row["status"] != "running":
            return row
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} still running")


def started(client, task_id):
    """A successful /run, waited for; its response body."""
    r = run(client, task_id)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    return r.json()


def run_row(run_id):
    cols = ("id", "task_id", "session_id", "pid", "status", "exit_code", "error", "log_path",
            "started_at", "ended_at")
    return dict(zip(cols, sql(f"SELECT {', '.join(cols)} FROM runs WHERE id = ?", (run_id,))[0]))


def task_row(task_id):
    cols = ("status", "stage", "position", "updated_at", "branch", "worktree_path")
    return dict(zip(cols, sql(f"SELECT {', '.join(cols)} FROM tasks WHERE id = ?", (task_id,))[0]))


def events(task_id):
    return sql("SELECT actor, from_status, to_status, stage, note FROM events WHERE task_id = ? ORDER BY id",
               (task_id,))


def worktrees(repo):
    """`git worktree list --porcelain` as {path: {key: value}}."""
    entries = {}
    for block in git(repo, "worktree", "list", "--porcelain").split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in block.splitlines())
        entries[fields["worktree"]] = fields
    return entries


def allowed(argv):
    return argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]


def no_runs():
    return sql("SELECT COUNT(*) FROM runs")[0][0] == 0


# --- POST /api/tasks/{id}/run: a successful spawn -----------------------------


def test_run_response(client, project, fake):  # AC1
    task = add_task(project, "Rate-limit login endpoint")
    r = run(client, task)
    assert r.status_code == 202, r.text
    body = r.json()
    wait(body["run_id"])
    assert body == {"run_id": sql("SELECT id FROM runs WHERE task_id = ?", (task,))[0][0],
                    "session_id": body["session_id"], "worktree": f".claude/worktrees/{task}-rate-limit-login",
                    "account_id": 1, "account": "claude-config"}  # 097 AC18: no email stored, the dir's name
    uuid.UUID(body["session_id"])
    assert fake.recorded("run")["argv"][3] == body["session_id"]


def test_worktree_and_branch(client, project, repo):  # AC2
    task = add_task(project, "Rate-limit login endpoint")
    started(client, task)
    path = f"{repo}/.claude/worktrees/{task}-rate-limit-login"
    entry = worktrees(repo)[path]
    assert entry["branch"] == f"refs/heads/factory/{task}-rate-limit-login"
    assert entry["HEAD"] == git(repo, "rev-parse", "main")
    row = task_row(task)
    assert (row["branch"], row["worktree_path"]) == (f"factory/{task}-rate-limit-login", path)


def test_slug():  # AC3
    assert slug("Rate-limit login endpoint") == "rate-limit-login"
    assert slug("Fix: the  API!!") == "fix-the-api"
    assert slug("Добавить вход") == "task"


def test_exclude_line_once(client, project, repo):  # AC4
    exclude = repo / ".git" / "info" / "exclude"
    exclude.write_text("# mine\n*.log")  # no trailing newline
    started(client, add_task(project, "one"))
    assert exclude.read_text() == "# mine\n*.log\n.claude/worktrees/\n.fctl/\n"
    started(client, add_task(project, "two"))
    assert exclude.read_text() == "# mine\n*.log\n.claude/worktrees/\n.fctl/\n"
    assert git(repo, "status", "--porcelain") == ""


def test_run_trusts_project(client, project, tmp_path):  # a headless run can't answer the trust dialog
    conf = tmp_path / "claude-config" / ".claude.json"
    conf.parent.mkdir()
    conf.write_text('{"keep": 1, "projects": {"/other": {"x": 2}}}')
    started(client, add_task(project, "one"))
    [(path,)] = sql("SELECT path FROM projects WHERE id = ?", (project,))
    assert json.loads(conf.read_text()) == {
        "keep": 1, "projects": {"/other": {"x": 2}, path: {"hasTrustDialogAccepted": True}}}
    assert conf.stat().st_mode & 0o777 == 0o600
    conf.write_text("{not json")  # left alone, and the run still starts
    started(client, add_task(project, "two"))
    assert conf.read_text() == "{not json"


def test_argv(client, project, fake):  # AC5
    task = add_task(project)
    sid = started(client, task)["session_id"]
    assert fake.recorded("run")["argv"] == [
        "-p", f"/factory {task}", "--session-id", sid, "--output-format", "stream-json", "--verbose",
        "--forward-subagent-text", "--permission-mode", "acceptEdits", "--permission-prompts", "none",
        "--allowedTools", *FCTL_ALLOWED, "Bash(pytest *)",
        "--disallowedTools", "Bash(git commit *)", "Bash(git push *)", "Bash(git merge *)",
        "Bash(git rebase *)", "Bash(git reset *)", "Bash(git checkout *)",
    ]


@pytest.mark.parametrize("test_cmd, extra", [
    ("uv run pytest -q", ["Bash(uv run pytest *)"]),  # 092 AC1
    (None, []),  # 092 AC2
    ("pytest -q", ["Bash(pytest *)"]),  # 092 AC2: the connect default
    ("pytest -q tests/", ["Bash(pytest *)"]),  # one word after the flag is its value (092 Q2)
    ("uv run pytest -q && npm --prefix frontend ci && npm --prefix frontend test",  # 092 AC3
     ["Bash(uv run pytest *)", "Bash(npm --prefix frontend ci *)", "Bash(npm --prefix frontend test *)"]),
    ("pytest -q; ruff check .", ["Bash(pytest *)", "Bash(ruff check . *)"]),  # 092 AC4: no flag, all words
    ("pytest -q;ruff check --fix .", ["Bash(pytest *)", "Bash(ruff check *)"]),  # 092 AC4
    ("pytest -q | tee out.txt", ["Bash(pytest *)", "Bash(tee out.txt *)"]),  # 092 AC5
    ("make test || make retry", ["Bash(make test *)", "Bash(make retry *)"]),  # 092 AC5
    ('pytest -k "a && b"', ["Bash(pytest *)"]),  # 092 AC6
    ("pytest -k 'x; y'", ["Bash(pytest *)"]),  # 092 AC6
    ("npm --prefix frontend ci", ["Bash(npm --prefix frontend ci *)"]),  # 092 AC7
    ("npm --prefix frontend ci --silent|pytest",  # 092 AC7, no spaces around the operator
     ["Bash(npm --prefix frontend ci *)", "Bash(pytest *)"]),
    ("npm --prefix=frontend ci --silent && pnpm --dir=frontend test",  # 092 AC7, inline flag value
     ["Bash(npm --prefix=frontend ci *)", "Bash(pnpm --dir=frontend test *)"]),
    ("pytest -q && npm test && pytest -x", ["Bash(pytest *)", "Bash(npm test *)"]),  # 092 AC8
    ("pytest -q; && && ruff check .;", ["Bash(pytest *)", "Bash(ruff check . *)"]),  # 092 AC9
    (" && ; | ", []),  # 092 AC9
])
def test_test_cmd_entry(client, project, fake, test_cmd, extra):  # AC6; 092 AC11
    sql("UPDATE projects SET test_cmd = ?", (test_cmd,))
    started(client, add_task(project))
    argv = fake.recorded("run")["argv"]
    assert allowed(argv) == FCTL_ALLOWED + extra
    assert argv[argv.index("--disallowedTools") + 1:] == [  # 092 AC10
        "Bash(git commit *)", "Bash(git push *)", "Bash(git merge *)", "Bash(git rebase *)",
        "Bash(git reset *)", "Bash(git checkout *)"]


def test_cwd_is_worktree(client, project, repo, fake):  # AC7
    task = add_task(project)
    started(client, task)
    real = os.path.realpath(task_row(task)["worktree_path"])
    assert fake.recorded("auth")["cwd"] == real
    assert fake.recorded("run")["cwd"] == real


def test_env_stripped(client, project, fake, monkeypatch):  # AC8
    for name in STRIPPED:
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("FOO", "bar")
    monkeypatch.setenv("FCTL_URL", "http://elsewhere:1")  # Q8: replaced
    started(client, add_task(project))
    for name in ("auth", "run"):
        env = fake.recorded(name)["env"]
        assert not set(STRIPPED) & set(env)
        assert env["FOO"] == "bar"
        assert env["FCTL_URL"] == "http://127.0.0.1:4545"


def test_env_names_active_account(client, project, fake, monkeypatch, tmp_path):  # 056 BE18
    two = str(tmp_path / "account-2")
    sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?)", (two, OLD))
    sql("UPDATE claude_accounts SET active = 0")
    sql("UPDATE claude_accounts SET active = 1 WHERE config_dir = ?", (two,))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "third"))
    for name in STRIPPED:
        monkeypatch.setenv(name, "x")
    started(client, add_task(project))
    for name in ("auth", "run"):
        env = fake.recorded(name)["env"]
        assert env["CLAUDE_CONFIG_DIR"] == two
        assert not set(STRIPPED) & set(env)
        assert env["FCTL_URL"] == "http://127.0.0.1:4545"


def test_run_keeps_its_account(client, project, fake, tmp_path):  # 096 AC11, Q5
    two = str(tmp_path / "account-2")
    sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?)", (two, OLD))
    sql("UPDATE claude_accounts SET active = 0")
    sql("UPDATE claude_accounts SET active = 1 WHERE config_dir = ?", (two,))
    run_id = started(client, add_task(project))["run_id"]
    [(account_id,)] = sql("SELECT account_id FROM runs WHERE id = ?", (run_id,))
    assert sql("SELECT config_dir FROM claude_accounts WHERE id = ?", (account_id,)) == [(two,)]
    assert fake.recorded("run")["env"]["CLAUDE_CONFIG_DIR"] == two


def test_env_has_free_ports(client, project, fake):  # 096 AC12, Q6
    started(client, add_task(project))
    env = fake.recorded("run")["env"]
    ports = int(env["FCTL_BACKEND_PORT"]), int(env["FCTL_FRONTEND_PORT"])
    assert ports[0] != ports[1]
    for port in ports:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost:4545"])  # frontend/server.js sends the first
@pytest.mark.parametrize("route", ["run", "run-next"])
def test_fctl_url_ignores_host(client, project, fake, route, host):  # 028 AC4
    task = add_task(project)
    url = f"/api/tasks/{task}/run" if route == "run" else f"/api/projects/{project}/run-next"
    r = client.post(url, headers=H | {"Host": host})
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    port = client.base_url.port  # the TestClient server's port, 4545
    assert [fake.recorded(name)["env"]["FCTL_URL"] for name in ("auth", "run")] == [f"http://127.0.0.1:{port}"] * 2


def test_own_process_group(client, project, fake):  # AC9
    run_id = started(client, add_task(project))["run_id"]
    seen = fake.recorded("run")
    assert seen["pgid"] == seen["pid"] != os.getpgrp()
    assert run_row(run_id)["pid"] == seen["pid"]


def test_log_and_row(client, project):  # AC10
    task = add_task(project)
    body = started(client, task)
    row = run_row(body["run_id"])
    log = os.path.join(os.environ["FCTL_HOME"], "runs", f"{body['run_id']}.jsonl")
    assert row["log_path"] == log
    lines = open(log).read().splitlines()
    assert SYSTEM in lines and "warn" in lines
    assert any(json.loads(line).get("type") == "result" for line in lines if line.startswith("{"))
    assert (row["task_id"], row["session_id"]) == (task, body["session_id"])
    assert row["started_at"]


def test_backlog_to_in_progress(client, project):  # AC11
    task = add_task(project, position=3.0)
    before = events(task)
    started(client, task)
    row = task_row(task)
    assert (row["status"], row["stage"], row["position"]) == ("in_progress", None, 3.0)
    assert row["updated_at"] > OLD
    assert events(task) == before + [("app", "backlog", "in_progress", None, None)]


def test_rerun_in_progress(client, project, repo, fake):  # AC12
    task = add_task(project)
    first = started(client, task)
    sql("UPDATE tasks SET stage = 'build' WHERE id = ?", (task,))
    listed, before = worktrees(repo), events(task)
    second = started(client, task)
    assert second["worktree"] == first["worktree"]
    assert worktrees(repo) == listed
    assert fake.recorded("run")["cwd"] == os.path.realpath(task_row(task)["worktree_path"])
    assert (task_row(task)["status"], task_row(task)["stage"]) == ("in_progress", "build")
    assert events(task) == before


# --- On exit ------------------------------------------------------------------

RESULT_S2 = '{"type":"result","subtype":"success","is_error":false,"session_id":"S2","result":"ok"}'
LIMIT = '{"type":"result","subtype":"success","is_error":true,"result":"Claude AI usage limit reached"}'
EXITS = {  # fake behaviour → (status, exit_code, error)
    "success": ({"lines": [SYSTEM, RESULT_S2]}, ("succeeded", 0, None)),
    "error result": ({"lines": [SYSTEM, LIMIT], "code": 1}, ("failed", 1, "Claude AI usage limit reached")),
    "no output": ({"lines": [], "code": 3}, ("failed", 3, "exit code 3")),
    "no result": ({"lines": [SYSTEM]}, ("failed", 0, "no result event")),
}


def exited(client, project, fake, case):
    """Run a task with one of EXITS' fakes; (task id, finished run row)."""
    fake(**EXITS[case][0])
    task = add_task(project)
    r = run(client, task)
    assert r.status_code == 202, r.text
    return task, wait(r.json()["run_id"])


def outcome(row):
    return row["status"], row["exit_code"], row["error"]


def test_exit_success(client, project, fake):  # AC13
    _, row = exited(client, project, fake, "success")
    assert outcome(row) == EXITS["success"][1]
    assert row["ended_at"] and row["session_id"] == "S2"


def test_exit_error_result(client, project, fake):  # AC14
    _, row = exited(client, project, fake, "error result")
    assert outcome(row) == EXITS["error result"][1]


@pytest.mark.parametrize("case", ["no output", "no result"])
def test_exit_without_result(client, project, fake, case):  # AC15
    _, row = exited(client, project, fake, case)
    assert outcome(row) == EXITS[case][1]
    assert row["ended_at"]


@pytest.mark.parametrize("case", list(EXITS))
def test_exit_leaves_task(client, project, fake, case):  # AC16
    task, _ = exited(client, project, fake, case)
    row = task_row(task)
    assert (row["status"], row["stage"]) == ("in_progress", None)  # as the spawn left it
    assert events(task) == [("app", "backlog", "in_progress", None, None)]  # the spawn's event only


# --- Refusals: none of these writes a runs row --------------------------------


def cap(n):
    """096: max_concurrent_runs = n."""
    sql("UPDATE settings SET max_concurrent_runs = ?", (n,))


def cap_detail(*runs, limit=None):
    """096 AC6's 409 detail for (run id, task id) pairs, by run id."""
    n = len(runs)
    listed = ", ".join(f"#{r} on #{t}" for r, t in runs)
    return (f"{n} run{'' if n == 1 else 's'} active ({listed}); the limit is {limit or n}."
            " Wait, stop one, or raise it in Settings")


def test_refused_while_running(client, project, repo, fake, tmp_path):  # AC17; 096: the cap spans projects
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", "-b", "main", str(other))
    other_task = add_task(connect(client, other))
    running = add_running_run(other_task)
    cap(1)
    task = add_task(project)
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": cap_detail((running, other_task))})
    assert not (repo / ".claude" / "worktrees").exists()
    assert not fake.invoked()
    assert sql("SELECT COUNT(*) FROM runs")[0][0] == 1


@pytest.mark.parametrize("status, stage, detail", [
    ("review", "human_review", "#{} is in review"), ("done", None, "#{} is done"),
])
def test_refused_by_status(client, project, repo, fake, status, stage, detail):  # AC18
    task = add_task(project, status=status, stage=stage)
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": detail.format(task)})
    assert not (repo / ".claude" / "worktrees").exists()
    assert not fake.invoked() and no_runs()


@pytest.mark.parametrize("on_disk", [True, False])
def test_refused_without_factory(client, repo, fake, on_disk):  # AC19
    if on_disk:
        write(repo, {SKILL: "# factory\n"})
    task = add_task(connect(client, repo))
    r = run(client, task)
    fix = ('on main, run git add .claude/skills/factory .claude/agents && git commit -m "Add factory"' if on_disk
           else "Create factory in the project's Settings, then commit it on main")  # 015 ux review, 042 BE5
    assert (r.status_code, r.json()) == (409, {"detail": f"factory isn't committed on main: {fix}"})
    assert not (repo / ".claude" / "worktrees").exists()
    assert not fake.invoked() and no_runs()


def test_refused_legacy_factory(client, legacy, repo, fake):  # 059 BE6
    task = add_task(legacy)
    before = task_row(task), events(task)
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": LEGACY_HINT})
    assert not (repo / ".claude" / "worktrees").exists()
    assert not fake.invoked() and no_runs()
    assert (task_row(task), events(task)) == before and before[0]["status"] == "backlog"


@pytest.mark.parametrize("auth, auth_code", [('{"authMethod":"console"}', 0), ("not json", 0), (AUTH_OK, 1)])
def test_refused_without_subscription(client, project, repo, fake, auth, auth_code):  # AC20
    fake(auth=auth, auth_code=auth_code)
    task = add_task(project, "Rate-limit login endpoint")
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})
    assert fake.recorded("auth") and not fake.recorded("run") and no_runs()
    row = task_row(task)
    path = f"{repo}/.claude/worktrees/{task}-rate-limit-login"
    assert (row["status"], row["branch"], row["worktree_path"]) == (
        "backlog", f"factory/{task}-rate-limit-login", path)
    assert os.path.isdir(path)
    listed = worktrees(repo)
    fake()
    assert started(client, task)["worktree"] == f".claude/worktrees/{task}-rate-limit-login"
    assert worktrees(repo) == listed


def test_refused_without_active_account(client, project, fake):  # 056 BE15, Q7
    sql("DELETE FROM claude_accounts")
    r = run(client, add_task(project))
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})
    assert not fake.recorded("auth") and not fake.recorded("run") and no_runs()


def test_refused_when_worktree_add_fails(client, project, repo, fake):  # AC21
    task = add_task(project, "Rate-limit login endpoint")
    write(repo, {f".claude/worktrees/{task}-rate-limit-login/stray.txt": "x"})
    r = run(client, task)
    assert r.status_code == 409
    assert r.json()["detail"].startswith("wt switch failed: ")  # 099 AC5: wt's stderr, here git's
    row = task_row(task)
    assert (row["status"], row["branch"], row["worktree_path"]) == ("backlog", None, None)
    assert not fake.invoked() and no_runs()


def test_refused_when_worktree_missing(client, project, fake, tmp_path):  # AC22
    task = add_task(project, status="in_progress", stage="build")
    gone = str(tmp_path / "gone")
    sql("UPDATE tasks SET branch = 'factory/x', worktree_path = ? WHERE id = ?", (gone, task))
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": f"worktree {gone} is missing"})
    assert not fake.invoked() and no_runs()


def test_spawn_fails(client, project, fake, tmp_path, monkeypatch):  # AC23
    # With the fake gone, PATH lookup must not fall through to a real `claude`
    git_dir = os.path.dirname(os.path.realpath(shutil.which("git")))
    assert not shutil.which("claude", path=git_dir)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{git_dir}")
    fake(delete_self=True)
    task = add_task(project)
    r = run(client, task)
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert detail.startswith("can't start claude: ")
    row = sql("SELECT status, error, ended_at FROM runs WHERE task_id = ?", (task,))
    assert len(row) == 1 and row[0][:2] == ("failed", detail) and row[0][2]
    assert task_row(task)["status"] == "in_progress"
    fake()
    started(client, add_task(project))


def test_unknown_task_and_missing_header(client, project, fake):  # AC24
    r = run(client, 999)
    assert (r.status_code, r.json()) == (404, {"detail": "no task #999"})  # 015 ux review
    assert client.post(f"/api/tasks/{add_task(project)}/run").status_code == 403
    assert not fake.invoked() and no_runs()


# --- POST /api/projects/{id}/run-next -----------------------------------------


@pytest.fixture
def queue(project):
    """Backlog B (1.0), C (1.0, created after B), A (2.0), plus an in_progress task at 0.5."""
    b = add_task(project, "B", position=1.0)
    add_task(project, "C", position=1.0)
    add_task(project, "A", position=2.0)
    add_task(project, "I", status="in_progress", position=0.5)
    return b


def test_run_next_takes_top(client, project, queue, fake):  # AC25
    r = client.post(f"/api/projects/{project}/run-next", headers=H)
    assert r.status_code == 202, r.text
    run_id = sql("SELECT id FROM runs")[0][0]
    assert r.json() == {"task_id": queue, "run_id": run_id, "account_id": 1, "account": "claude-config"}  # 097 AC19
    wait(run_id)
    assert task_row(queue)["status"] == "in_progress"
    assert fake.recorded("run")["argv"][1] == f"/factory {queue}"


def test_run_next_empty_or_unknown(client, project, fake):  # AC26
    add_task(project, status="in_progress")
    r = client.post(f"/api/projects/{project}/run-next", headers=H)
    assert (r.status_code, r.json()) == (404, {"detail": "backlog is empty"})
    assert client.post("/api/projects/999/run-next", headers=H).status_code == 404
    assert no_runs()


def test_run_next_legacy(client, legacy, fake):  # 059 BE7
    top = add_task(legacy, "top", position=1.0)
    add_task(legacy, "next", position=2.0)
    r = client.post(f"/api/projects/{legacy}/run-next", headers=H)
    assert (r.status_code, r.json()) == (409, {"detail": LEGACY_HINT})
    assert no_runs() and not fake.invoked()
    assert task_row(top)["status"] == "backlog"


def test_run_next_while_running(client, project, queue, fake):  # AC27; 096 AC17: at the cap
    other = add_task(project, status="in_progress")
    running = add_running_run(other)
    cap(1)
    r = client.post(f"/api/projects/{project}/run-next", headers=H)
    assert (r.status_code, r.json()) == (409, {"detail": cap_detail((running, other))})
    assert task_row(queue)["status"] == "backlog"
    assert sql("SELECT COUNT(*) FROM runs")[0][0] == 1 and not fake.invoked()


def test_run_next_skips_running_card(client, project, queue, fake):  # 096 AC16, Q10
    running = add_running_run(queue)  # the top backlog card, as a sync or import could leave it
    r = client.post(f"/api/projects/{project}/run-next", headers=H)
    assert r.status_code == 202, r.text
    second = sql("SELECT id FROM tasks WHERE title = 'C'")[0][0]
    assert r.json()["task_id"] == second
    wait(r.json()["run_id"])
    assert run_row(running)["status"] == "running"


# --- 094: blocked tasks don't run -------------------------------------------------------


def waits(task_id, *blockers):
    for blocker in blockers:
        sql("INSERT INTO task_deps (task_id, blocked_by_id) VALUES (?, ?)", (task_id, blocker))


def test_refused_when_blocked(client, project, repo, fake, tmp_path):  # 094 AC12, Q1
    first, done, second = add_task(project), add_task(project, status="done"), add_task(project, status="in_progress")
    task = add_task(project)
    waits(task, second, done, first)
    r = run(client, task)
    detail = f"#{task} is blocked by #{first}, #{second}; finish those first or remove the dependency"
    assert (r.status_code, r.json()) == (409, {"detail": detail})
    assert not (repo / ".claude" / "worktrees").exists()
    assert not fake.invoked() and no_runs()
    assert task_row(task)["status"] == "backlog"
    review = add_task(project, status="review", stage="human_review")
    waits(review, first)
    assert run(client, review).json() == {"detail": f"#{review} is in review"}  # after the review/done 409
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", "-b", "main", str(other))
    blocker = add_task(connect(client, other))
    blocked = add_task(sql("SELECT project_id FROM tasks WHERE id = ?", (blocker,))[0][0])
    waits(blocked, blocker)
    assert run(client, blocked).json() == {  # before the factory check: that repo has no factory
        "detail": f"#{blocked} is blocked by #{blocker}; finish those first or remove the dependency"}
    assert not fake.invoked() and no_runs()


def test_run_next_skips_blocked(client, project, fake):  # 094 AC13
    working = add_task(project, status="in_progress", position=0.5)
    top = add_task(project, "top", position=1.0)
    tie = add_task(project, "tie", position=1.0)
    add_task(project, "later", position=2.0)
    waits(top, working)
    r = client.post(f"/api/projects/{project}/run-next", headers=H)
    assert r.status_code == 202, r.text
    assert r.json() == {"task_id": tie, "run_id": sql("SELECT id FROM runs")[0][0], "account_id": 1,
                        "account": "claude-config"}
    wait(r.json()["run_id"])
    assert (task_row(top)["status"], task_row(tie)["status"]) == ("backlog", "in_progress")


def test_run_next_all_blocked(client, project, fake):  # 094 AC14, Q5
    first, done, second = (add_task(project, status="in_progress"), add_task(project, status="done"),
                           add_task(project, status="review", stage="human_review"))
    top, later = add_task(project, "top", position=1.0), add_task(project, "later", position=2.0)
    waits(top, second, done, first)
    waits(later, first)
    r = client.post(f"/api/projects/{project}/run-next", headers=H)
    assert (r.status_code, r.json()) == (
        409, {"detail": f"all backlog tasks are blocked: #{top} waits on #{first}, #{second}"})
    assert no_runs() and not fake.invoked()
    sql("DELETE FROM tasks WHERE id IN (?, ?)", (top, later))  # deleting a task drops its links (ON DELETE CASCADE)
    r = client.post(f"/api/projects/{project}/run-next", headers=H)
    assert (r.status_code, r.json()) == (404, {"detail": "backlog is empty"})


# --- 113: run next by module -------------------------------------------------------


def add_module(project_id, name):
    return sql("INSERT INTO modules (project_id, name, description_md, created_at) VALUES (?, ?, '', ?) RETURNING id",
               (project_id, name, OLD))[0][0]


def in_module(task_id, module_id):
    sql("UPDATE tasks SET module_id = ? WHERE id = ?", (module_id, task_id))
    return task_id


def run_next_in(client, project_id, body):
    return client.post(f"/api/projects/{project_id}/run-next", json=body, headers=H)


def test_run_next_module_takes_its_top(client, project, fake):  # 113 AC1
    front, back = add_module(project, "frontend"), add_module(project, "backend")
    loose = add_task(project, "loose", position=0.5)
    other = in_module(add_task(project, "other", position=0.6), back)
    later = in_module(add_task(project, "later", position=2.0), front)
    top = in_module(add_task(project, "top", position=1.0), front)
    r = run_next_in(client, project, {"module_id": front})
    assert r.status_code == 202, r.text
    assert r.json() == {"task_id": top, "run_id": sql("SELECT id FROM runs")[0][0], "account_id": 1,
                        "account": "claude-config"}
    wait(r.json()["run_id"])
    assert [task_row(t)["status"] for t in (loose, other, later, top)] == ["backlog"] * 3 + ["in_progress"]


def test_run_next_module_keeps_rules(client, project, fake):  # 113 AC2
    front = add_module(project, "frontend")
    working = add_task(project, status="in_progress", position=0.1)
    blocked = in_module(add_task(project, "blocked", position=1.0), front)
    running = in_module(add_task(project, "running", position=1.5), front)
    ready = in_module(add_task(project, "ready", position=2.0), front)
    waits(blocked, working)
    add_running_run(running)
    r = run_next_in(client, project, {"module_id": front, "account_id": 99})  # account_id ignored: Auto
    assert r.status_code == 202, r.text
    assert (r.json()["task_id"], r.json()["account_id"]) == (ready, 1)
    wait(r.json()["run_id"])


def test_run_next_module_empty(client, project, fake):  # 113 AC3
    front = add_module(project, "frontend")
    add_task(project, "loose")
    in_module(add_task(project, "doing", status="in_progress"), front)
    add_running_run(in_module(add_task(project, "running"), front))
    r = run_next_in(client, project, {"module_id": front})
    assert (r.status_code, r.json()) == (404, {"detail": "module frontend has no backlog tasks"})
    assert sql("SELECT COUNT(*) FROM runs")[0][0] == 1 and not fake.invoked()


def test_run_next_module_all_blocked(client, project, fake):  # 113 AC4
    front = add_module(project, "frontend")
    first, second = add_task(project, status="in_progress"), add_task(project, status="review", stage="human_review")
    add_task(project, "ready elsewhere", position=0.5)
    top = in_module(add_task(project, "top", position=1.0), front)
    later = in_module(add_task(project, "later", position=2.0), front)
    waits(top, second, first)
    waits(later, first)
    r = run_next_in(client, project, {"module_id": front})
    assert (r.status_code, r.json()) == (
        409, {"detail": f"all backlog tasks in frontend are blocked: #{top} waits on #{first}, #{second}"})
    assert no_runs() and not fake.invoked()


def test_run_next_module_refused(client, project, repo, tmp_path, fake):  # 113 AC5
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", "-b", "main", str(other))
    theirs = add_module(connect(client, other), "frontend")
    add_task(project)
    r = run_next_in(client, project, {"module_id": theirs})
    assert (r.status_code, r.json()) == (
        422, {"detail": f"module #{theirs} is in another project; pick one of this project's modules"})
    r = run_next_in(client, project, {"module_id": 99})
    assert (r.status_code, r.json()) == (422, {"detail": "no module #99"})
    assert no_runs() and not fake.invoked()


@pytest.mark.parametrize("body", [None, {}, {"module_id": None}])
def test_run_next_no_module(client, project, fake, body):  # 113 AC6
    front = add_module(project, "frontend")
    in_module(add_task(project, "moduled", position=2.0), front)
    top = add_task(project, "loose", position=1.0)
    r = client.post(f"/api/projects/{project}/run-next", headers=H, **({} if body is None else {"json": body}))
    assert r.status_code == 202, r.text
    assert r.json()["task_id"] == top
    wait(r.json()["run_id"])


def test_run_next_module_at_cap(client, project, fake):  # 113 AC7
    front = add_module(project, "frontend")
    task = in_module(add_task(project), front)
    other = add_task(project, status="in_progress")
    running = add_running_run(other)
    cap(1)
    r = run_next_in(client, project, {"module_id": front})
    assert (r.status_code, r.json()) == (409, {"detail": cap_detail((running, other))})
    assert task_row(task)["status"] == "backlog" and not fake.invoked()


# --- 036: the adapters come from Depends ------------------------------------------


class NoAuth(SubprocessClaude):
    def auth_status(self, cwd, env):
        return None


class Committed(SubprocessGit):
    def blob(self, root, oid):  # 059: factory_state's one git call; SKILL.md is always the app's template
        return READY.encode(), None


def test_auth_through_adapter(client, project, fake):  # 036 AC9
    client.app.dependency_overrides[get_claude] = NoAuth
    r = run(client, add_task(project))
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})
    assert no_runs() and not fake.invoked()


def test_factory_through_adapter(client, repo, fake):  # 036 AC10
    task = add_task(connect(client, repo), "Rate-limit login endpoint")  # no SKILL.md committed
    r = run(client, task)
    assert r.status_code == 409 and r.json()["detail"].startswith("factory isn't committed on main: ")
    client.app.dependency_overrides[get_git] = Committed
    r = run(client, task)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    assert os.path.isdir(f"{repo}/.claude/worktrees/{task}-rate-limit-login")


# --- 099: worktrunk makes the worktree and copies the ignored files in ------------------------


def steps() -> list[str]:
    """The fake wt's calls by subcommand: `switch`, `step copy-ignored`."""
    return [" ".join(c["argv"][2:4]) if c["argv"][2] == "step" else c["argv"][2] for c in wt_calls()]


def project_path(project_id) -> str:
    return sql("SELECT path FROM projects WHERE id = ?", (project_id,))[0][0]


def test_wt_switch_creates(client, project):  # 099 AC1, AC7
    task = add_task(project, "Rate-limit login endpoint")
    body = started(client, task)
    root, name = project_path(project), f"{task}-rate-limit-login"
    expected = f"{root}/.claude/worktrees/{name}"
    switch = wt_calls()[0]
    assert switch["argv"] == ["-C", root, "switch", "--create", f"factory/{name}", "--base", "main", "--no-cd",
                              "--no-hooks", "--format", "json"]
    assert f'worktree-path = "{expected}"' in switch["config"].splitlines()  # Q1: through WORKTRUNK_CONFIG_PATH
    row = task_row(task)
    assert (row["branch"], row["worktree_path"]) == (f"factory/{name}", expected)
    assert body["worktree"] == f".claude/worktrees/{name}"  # AC7
    assert expected in worktrees(root)


def test_wt_copy_after_switch_before_auth(client, project, fake, monkeypatch):  # 099 AC2, AC5
    task = add_task(project)
    monkeypatch.setenv("FAKE_WT_FAIL", "step copy-ignored")
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": "wt step copy-ignored failed: wt: step copy-ignored broke"})
    assert not fake.invoked() and no_runs()  # the copy comes before the auth check and the spawn
    wt = task_row(task)["worktree_path"]
    assert wt and os.path.isdir(wt)  # AC5: kept for Retry
    switch, copy = wt_calls()
    assert switch["argv"][2] == "switch"
    assert copy["argv"] == ["-C", wt, "step", "copy-ignored"]
    assert ('exclude = [".venv/", ".claude/worktrees/", ".claude/settings.local.json", ".fctl/"]'
            in copy["config"].splitlines())  # Q2
    monkeypatch.delenv("FAKE_WT_FAIL")
    started(client, task)
    assert steps() == ["switch", "step copy-ignored", "step copy-ignored"]


def test_wt_reuse_copies_again(client, project):  # 099 AC3
    task = add_task(project)
    first = started(client, task)
    sql("UPDATE tasks SET stage = 'build' WHERE id = ?", (task,))
    assert started(client, task)["worktree"] == first["worktree"]
    assert steps() == ["switch", "step copy-ignored", "step copy-ignored"]
    wt = task_row(task)["worktree_path"]
    assert [c["argv"] for c in wt_calls()[1:]] == [["-C", wt, "step", "copy-ignored"]] * 2


def test_wt_missing(client, project, repo, fake, tmp_path, monkeypatch):  # 099 AC4
    (tmp_path / "bin" / "wt").unlink()
    git_only = tmp_path / "git-only"  # git without whatever shares its directory (a real wt, say)
    git_only.mkdir()
    (git_only / "git").symlink_to(os.path.realpath(shutil.which("git")))
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{git_only}")
    task = add_task(project)
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": WT_MISSING})
    assert WT_MISSING == "wt (worktrunk) isn't installed: brew install worktrunk, then run again"
    assert task_row(task)["worktree_path"] is None and not (repo / ".claude" / "worktrees").exists()
    assert not fake.invoked() and no_runs()
    old = tmp_path / "old-worktree"  # a reused worktree, made by git before 099
    git(repo, "worktree", "add", "-q", "-b", "factory/old", str(old))
    sql("UPDATE tasks SET branch = 'factory/old', worktree_path = ? WHERE id = ?", (str(old), task))
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": WT_MISSING})
    assert not fake.invoked() and no_runs()


def test_wt_switch_fails(client, project, fake, monkeypatch):  # 099 AC5
    monkeypatch.setenv("FAKE_WT_FAIL", "switch")
    task = add_task(project)
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": "wt switch failed: wt: switch broke"})
    assert task_row(task)["worktree_path"] is None and steps() == ["switch"]
    assert not fake.invoked() and no_runs()


def test_wt_elsewhere(client, project, fake, monkeypatch, tmp_path):  # 099 Q1
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv("FAKE_WT_PATH", str(elsewhere))
    task = add_task(project, "Rate-limit login endpoint")
    r = run(client, task)
    expected = f"{project_path(project)}/.claude/worktrees/{task}-rate-limit-login"
    assert (r.status_code, r.json()) == (409, {"detail": f"wt put the worktree at {elsewhere}, expected {expected}"})
    assert task_row(task)["worktree_path"] is None and not fake.invoked() and no_runs()


@pytest.mark.parametrize("step, timeout", [("switch", "WT_SWITCH_TIMEOUT"), ("step copy-ignored", "WT_COPY_TIMEOUT")])
def test_wt_hangs(client, project, fake, monkeypatch, step, timeout):  # 099 AC6
    assert (git_adapter.WT_SWITCH_TIMEOUT, git_adapter.WT_COPY_TIMEOUT) == (60, 300)  # Q3
    monkeypatch.setattr(git_adapter, timeout, 1)
    monkeypatch.setenv("FAKE_WT_HANG", step)
    r = run(client, add_task(project))
    assert (r.status_code, r.json()) == (409, {"detail": f"wt {step} timed out"})
    assert not fake.invoked() and no_runs()


LEAK = ("conf/.env.local is ignored in the main checkout but not on main, so it was left out of the worktree: "
        "commit its .gitignore line on main, then run again")


def test_wt_copy_leak_removed_and_refused(client, project, fake, monkeypatch):  # 099 round 1 security finding 2
    task = add_task(project)
    started(client, task)
    sql("UPDATE tasks SET stage = 'build' WHERE id = ?", (task,))
    wt = task_row(task)["worktree_path"]
    write(Path(wt), {"notes.py": "x = 1\n"})  # the builder's untracked file, there before the copy
    fake.clear()
    monkeypatch.setenv("FAKE_WT_COPY", "conf/.env.local")  # the copy adds a file main's .gitignore doesn't list
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": LEAK})
    assert not os.path.exists(f"{wt}/conf/.env.local") and os.path.exists(f"{wt}/notes.py")
    assert not fake.invoked() and sql("SELECT COUNT(*) FROM runs")[0][0] == 1
    monkeypatch.setenv("FAKE_WT_FAIL", "step copy-ignored")  # a failed copy is cleaned up the same way
    r = run(client, task)
    assert r.json() == {"detail": "wt step copy-ignored failed: wt: step copy-ignored broke"}
    assert not os.path.exists(f"{wt}/conf/.env.local") and not fake.invoked()


def test_wt_copy_ignored_file_stays(client, repo, fake, monkeypatch):  # 099 round 1 security finding 2
    commit(repo, {SKILL: READY, ".gitignore": "*.local\n"})
    task = add_task(connect(client, repo))
    monkeypatch.setenv("FAKE_WT_COPY", "conf/.env.local")
    started(client, task)
    wt = task_row(task)["worktree_path"]
    assert os.path.exists(f"{wt}/conf/.env.local") and git(wt, "status", "--porcelain") == ""


REAL_WT = shutil.which("wt", path=ORIGINAL_PATH)


def real_wt(tmp_path):
    (tmp_path / "bin" / "wt").unlink()
    (tmp_path / "bin" / "wt").symlink_to(REAL_WT)


@pytest.mark.skipif(REAL_WT is None, reason="worktrunk (wt) isn't installed")
def test_real_wt(client, repo, fake, tmp_path):  # 099 AC10, Q6, round 1 security finding 1
    real_wt(tmp_path)
    commit(repo, {SKILL: READY, ".gitignore": ".env\nnode_modules/\n.venv/\n.claude/settings.local.json\n"})
    write(repo, {".env": "API_TOKEN=not-a-real-secret\n", "node_modules/pkg/index.js": "module.exports = 1;\n",
                 ".venv/pyvenv.cfg": "home = /usr/bin\n",
                 ".claude/settings.local.json": '{"permissions": {"allow": ["Bash(curl:*)"]}}\n',
                 ".fctl/build.md": "an old draft\n"})  # .fctl/ is ignored through info/exclude
    project = connect(client, repo)
    task = add_task(project, "Rate-limit login endpoint")
    started(client, task)
    row = task_row(task)
    wt = row["worktree_path"]
    assert wt == f"{project_path(project)}/.claude/worktrees/{task}-rate-limit-login"
    assert open(os.path.join(wt, ".env")).read() == "API_TOKEN=not-a-real-secret\n"
    assert open(os.path.join(wt, "node_modules", "pkg", "index.js")).read() == "module.exports = 1;\n"
    assert not os.path.exists(os.path.join(wt, ".venv"))
    assert not os.path.exists(os.path.join(wt, ".claude", "worktrees"))  # no worktree copied into itself
    assert not os.path.exists(os.path.join(wt, ".claude", "settings.local.json"))  # the run's tools stay as set
    assert not os.path.exists(os.path.join(wt, ".fctl"))
    assert git(wt, "status", "--porcelain") == ""
    # Q6: Merge PR's cleanup removes it through wt and leaves the branch to `git branch -d`
    r = SubprocessGit().wt_remove(project_path(project), row["branch"])
    assert r[0] == 0, r
    assert not os.path.exists(wt)
    assert git(repo, "branch", "--list", row["branch"]) != ""


@pytest.mark.skipif(REAL_WT is None, reason="worktrunk (wt) isn't installed")
def test_real_wt_ignored_only_in_main_checkout(client, repo, fake, tmp_path):  # 099 round 1 security finding 2
    real_wt(tmp_path)
    commit(repo, {SKILL: READY, ".gitignore": ".env\n"})
    write(repo, {".gitignore": ".env\nconf/.env.local\n", ".env": "A=1\n", "conf/.env.local": "B=2\n"})  # uncommitted
    task = add_task(connect(client, repo))
    r = run(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": LEAK})
    wt = task_row(task)["worktree_path"]
    assert not os.path.exists(f"{wt}/conf/.env.local") and os.path.exists(f"{wt}/.env")
    assert git(wt, "status", "--porcelain") == "" and not fake.invoked() and no_runs()
