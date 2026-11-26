import ast
import inspect
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import commit, git, sql, write
from controllers.test_runs import (H, LEGACY, LEGACY_HINT, OLD, SKILL, add_task, connect, fake,  # noqa: F401
                                   project)
from controllers.test_transcripts import add_transcript
from fastapi.testclient import TestClient
from test_architecture import PKG, REPO, checked, fastapi_outside, sql_outside, wrong_edges

from claude_factories import config, db
from claude_factories.adapters.git import SubprocessGit
from claude_factories.handlers import factory_import, pages
from claude_factories.server.app import create_app
from claude_factories.server.deps import get_git

PRO = '{"authMethod":"claude.ai","subscriptionType":"pro"}'
PRO_EMAIL = '{"authMethod":"claude.ai","subscriptionType":"pro","email":"artem@example.com"}'
APP_PY = "diff --git a/app.py b/app.py\nnew file mode 100644\n--- /dev/null\n+++ b/app.py\n@@ -0,0 +1 @@\n+x = 1\n"
B_PY = "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1,2 +1,2 @@\n keep\n-x\n+y\n"
TASK_KEYS = {"id", "project_id", "project", "workspace_id", "workspace", "title", "status", "stage", "branch",
             "worktree_path", "description_md", "description_html", "spec_md", "spec_html", "module"}  # 112 AC14
SUMMARY_KEYS = {"n", "trigger", "files", "additions", "deletions", "verdicts"}
CONSOLE = '{"authMethod":"console"}'
UNCOMMITTED = ("factory isn't committed on main: on main, run git add .claude/skills/factory .claude/agents"
               ' && git commit -m "Add factory"')
NONE = "factory isn't committed on main: Create factory in the project's Settings, then commit it on main"
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
    """unready("uncommitted" | "legacy" | "none") → a project on its own repo whose factory is in that state."""
    def make(state):
        path = tmp_path / f"repo-{state}"
        git(tmp_path, "init", "-q", "-b", "main", str(path))
        git(path, "commit", "-q", "--allow-empty", "-m", "init")
        if state == "uncommitted":
            write(path, {SKILL: "# factory\n"})
        if state == "legacy":  # 059: committed on main without `fctl stage`
            commit(path, {SKILL: LEGACY})
        return connect(client, path)
    return make


# --- GET /api/auth -------------------------------------------------------------------


def test_auth_claude_ai(client, fake):  # AC1, 039 AC1
    fake(auth=PRO_EMAIL)
    assert api(client, "/api/auth") == {"auth_method": "claude.ai", "plan": "pro", "runs_enabled": True,
                                        "email": "artem@example.com"}


@pytest.mark.parametrize("auth", ['{"authMethod":"console"}', "not json"])
def test_auth_not_claude_ai(client, fake, auth):  # AC2
    fake(auth=auth)
    assert api(client, "/api/auth") == {"auth_method": None, "plan": None, "runs_enabled": False, "email": None}


def test_auth_email_null(client, fake):  # 039 AC2
    fake(auth=PRO)
    assert api(client, "/api/auth") == {"auth_method": "claude.ai", "plan": "pro", "runs_enabled": True,
                                        "email": None}
    pages.LOGIN.clear()
    fake(auth='{"authMethod":"console","email":"x@y.z"}')
    assert api(client, "/api/auth") == {"auth_method": None, "plan": None, "runs_enabled": False, "email": None}


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


# --- POST /api/auth/login, /api/auth/login/code (039) ---------------------------------

SIGN_IN = "https://claude.ai/oauth/authorize?code=true&client_id=c&state=abc"
# 039 Q1: claude 2.1.304's `auth login`, acted out per the `mode` file. 056: `auth status` prints the `fake-status`
# file in its CLAUDE_CONFIG_DIR, which `login` and `logout` write, so each account's dir answers on its own.
# 055: `auth logout` follows the `logout` file: ok logs out, fail / fail-stderr print an error, silent prints nothing
LOGIN_FAKE = r'''
import json, os, sys, time
d, config_dir = os.environ["FAKE_LOGIN_DIR"], os.environ["CLAUDE_CONFIG_DIR"]
def put(name, text, how="w", where=d):
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, name), how) as f:
        f.write(text)
def record(name):
    put(name, json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ),
                          "pgid": os.getpgrp()}) + "\n", "a")
if sys.argv[1:] == ["auth", "status"]:
    record("statuses")
    status = os.path.join(config_dir, "fake-status")
    print(open(status).read() if os.path.exists(status) else '{"loggedIn":false}')
    sys.exit(0)
if "logout" in sys.argv:
    record("logouts")
    how = open(os.path.join(d, "logout")).read()
    if how == "ok":
        put("fake-status", '{"loggedIn":false}', where=config_dir)
        print("Successfully logged out from your Anthropic account.")
        sys.exit(0)
    if how != "silent":
        print("Logging out…", flush=True)
        print("Error: keychain locked", file=sys.stderr if how == "fail-stderr" else sys.stdout)
    sys.exit(1)
record("starts")
mode = open(os.path.join(d, "mode")).read()
url = "SIGN_IN"
print("Opening browser to sign in…")
if mode.startswith("fail"):
    if mode == "fail-http":
        print("If the browser didn't open, visit: http://localhost:5555/callback")
    print("Error: managed settings forbid this", flush=True)
    sys.exit(1)
osc = "\x1b]8;;" + url + "\x07" + url + "\x1b]8;;\x07"
print("If the browser didn't open, visit: " + (osc if mode == "osc" else url))
print("Paste code here if prompted > ", end="", flush=True)
if mode == "self":  # Q6: claude's own browser tab finished the sign-in
    put("fake-status", 'PRO_EMAIL', where=config_dir)
    sys.exit(0)
while line := sys.stdin.readline():
    put("stdin", line, "a")
    if mode == "hang":
        time.sleep(60)
    if mode == "reject":
        print("Login failed: Invalid code", file=sys.stderr)
        sys.exit(1)
    if line == "good#state\n":
        put("fake-status", 'PRO_EMAIL', where=config_dir)
        print("Login successful.")
        sys.exit(0)
    print("Invalid code", file=sys.stderr)
'''.replace("SIGN_IN", SIGN_IN).replace("PRO_EMAIL", PRO_EMAIL)
NO_LOGIN = {"detail": "no login in progress"}


def put_status(config_dir, status):
    """056: the fake's `auth status` answer for the account in `config_dir`."""
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    (Path(config_dir) / "fake-status").write_text(status)


@pytest.fixture
def fake_login(tmp_path, monkeypatch):
    """039: fake_login(mode, status, logout) sets the fake's behaviour, `status` as account 1's (056), whose dir
    is conftest's CLAUDE_CONFIG_DIR; starts(), statuses(), stdin(), and logouts() read what it saw."""
    d, one = tmp_path / "login", os.environ["CLAUDE_CONFIG_DIR"]
    d.mkdir()
    monkeypatch.setenv("FAKE_LOGIN_DIR", str(d))
    claude = tmp_path / "bin" / "claude"
    claude.write_text(f"#!{sys.executable}{LOGIN_FAKE}")
    claude.chmod(0o755)

    def install(mode="ok", status=CONSOLE, logout="ok"):
        (d / "mode").write_text(mode)
        (d / "logout").write_text(logout)
        put_status(one, status)

    def lines(name):
        return (d / name).read_text().splitlines() if (d / name).exists() else []

    install()
    install.starts = lambda: [json.loads(line) for line in lines("starts")]
    install.statuses = lambda: [json.loads(line) for line in lines("statuses")]
    install.stdin = lambda: lines("stdin")
    install.logouts = lambda: [json.loads(line) for line in lines("logouts")]
    return install


def start(client, status=200, account=1):
    """039's login, for account 1 by default; account=None sends no body, which adds an account (056 Q3)."""
    r = client.post("/api/auth/login", json=None if account is None else {"account_id": account}, headers=H)
    assert r.status_code == status, r.text
    return r.json()


def send(client, code, status=200, account=None):
    r = client.post("/api/auth/login/code", headers=H,
                    json={"code": code} | ({} if account is None else {"account_id": account}))
    assert r.status_code == status, r.text
    return r.json()


def gone(pgid) -> bool:
    """Whether process group `pgid` is empty, waiting up to 5 s."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_login_start(client, fake_login, monkeypatch):  # 039 AC3
    for name in STRIPPED + ("CLAUDE_CODE_USE_VERTEX",):
        monkeypatch.setenv(name, "x")
    assert start(client) == {"url": SIGN_IN, "account_id": 1}
    [seen] = fake_login.starts()
    assert seen["argv"] == ["auth", "login", "--claudeai"]
    assert os.path.realpath(seen["cwd"]) == os.path.realpath(os.environ["FCTL_HOME"])
    leaked = [k for k in seen["env"] if k in STRIPPED or k.startswith("CLAUDE_CODE_USE_")]
    assert leaked == []


def test_login_osc8_url(client, fake_login):  # 039 AC4
    fake_login("osc")
    url = start(client)["url"]
    assert url == SIGN_IN
    assert "\x1b" not in url and "\x07" not in url


def test_login_needs_header(client, fake_login):  # 039 AC5
    r = client.post("/api/auth/login")
    assert r.status_code == 403
    assert fake_login.starts() == []


@pytest.mark.parametrize("mode", ["fail", "fail-http"])
def test_login_no_url(client, fake_login, mode):  # 039 AC6
    fake_login(mode)
    assert start(client, 500) == {
        "detail": "claude auth login printed no sign-in URL: Error: managed settings forbid this"}
    assert send(client, "good#state", 409) == NO_LOGIN


def test_login_restart_stops_first(client, fake_login):  # 039 AC7
    start(client)
    first = fake_login.starts()[0]["pgid"]
    assert start(client) == {"url": SIGN_IN, "account_id": 1}
    assert gone(first)


def test_login_code_success(client, fake_login):  # 039 AC8
    assert api(client, "/api/auth")["runs_enabled"] is False  # primes the 60 s cache
    start(client)
    assert send(client, "good#state") == {"auth_method": "claude.ai", "plan": "pro", "runs_enabled": True,
                                          "email": "artem@example.com"}
    assert fake_login.stdin() == ["good#state"]
    assert api(client, "/api/auth")["runs_enabled"] is True


def test_login_code_after_success(client, fake_login):  # 039 AC9
    start(client)
    send(client, "good#state")
    assert send(client, "good#state", 409) == NO_LOGIN


def test_login_code_without_login(client, fake_login):  # 039 AC10
    assert send(client, "good#state", 409) == NO_LOGIN
    assert fake_login.starts() == []


def test_login_code_refused(client, fake_login):  # 039 AC11
    fake_login("reject")
    start(client)
    assert send(client, "good#state", 422) == {"detail": "Login failed: Invalid code"}
    assert send(client, "good#state", 409) == NO_LOGIN


def test_login_code_shape(client, fake_login):  # 039 AC12
    start(client)
    for bad in ["goodstate", "#state", "good#", "#", "go od#state", "good#st\nate", "a" * 2047 + "#b", ""]:
        r = client.post("/api/auth/login/code", json={"code": bad}, headers=H)
        assert r.status_code == 422, bad
    assert fake_login.stdin() == []
    assert send(client, "  good#state\n")["runs_enabled"] is True
    assert fake_login.stdin() == ["good#state"]


def test_login_code_timeout(client, fake_login, monkeypatch):  # 039 AC13
    fake_login("hang")
    monkeypatch.setattr(pages, "LOGIN_CODE_TIMEOUT", 0.5)
    start(client)
    pgid = fake_login.starts()[0]["pgid"]
    assert send(client, "good#state", 500) == {"detail": "claude auth login didn't finish"}
    assert gone(pgid)


def test_login_finished_by_claude(client, fake_login):  # 039 AC14
    fake_login("self")
    assert api(client, "/api/auth")["runs_enabled"] is False  # primes the 60 s cache
    start(client)
    pages.PENDING["proc"].wait(5)  # claude's own tab finished; nothing has looked yet
    assert api(client, "/api/auth")["runs_enabled"] is True
    assert send(client, "good#state", 409) == NO_LOGIN


def test_login_stopped_on_shutdown(fake_login):  # 039 AC15
    with TestClient(create_app(), base_url="http://127.0.0.1:4545") as c:
        start(c)
        pgid = fake_login.starts()[0]["pgid"]
    assert gone(pgid)


# --- /api/auth/accounts (056) ---------------------------------------------------------

SIGNED_OUT = {"auth_method": None, "plan": None, "runs_enabled": False, "email": None}
TWO = '{"authMethod":"claude.ai","subscriptionType":"max","email":"two@example.com"}'
TWO_AUTH = {"auth_method": "claude.ai", "plan": "max", "runs_enabled": True, "email": "two@example.com"}


@pytest.fixture
def providers(monkeypatch):
    """The API key and provider variables set, so each claude call's env shows them stripped (§4.3)."""
    for name in STRIPPED + ("CLAUDE_CODE_USE_VERTEX",):
        monkeypatch.setenv(name, "x")


def add_account(status=None) -> int:
    """An inactive account in a dir as the app makes them, under FCTL_HOME/claude-accounts/; `status` is its
    fake `auth status` answer."""
    root = config.data_dir() / "claude-accounts"
    root.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=root))
    if status:
        put_status(path, status)
    return sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?) RETURNING id",
               (str(path), OLD))[0][0]


def account_dir(account_id) -> Path:
    return Path(sql("SELECT config_dir FROM claude_accounts WHERE id = ?", (account_id,))[0][0])


def make_active(account_id):
    sql("UPDATE claude_accounts SET active = 0")
    sql("UPDATE claude_accounts SET active = 1 WHERE id = ?", (account_id,))


def active_ids() -> list[int]:
    return [i for (i,) in sql("SELECT id FROM claude_accounts WHERE active = 1")]


def account_count() -> int:
    return sql("SELECT COUNT(*) FROM claude_accounts")[0][0]


def in_account(seen, config_dir):
    """A claude call ran for the account in `config_dir`: its CLAUDE_CONFIG_DIR, the stripped env, and the
    data dir as cwd (§4.3)."""
    assert seen["env"]["CLAUDE_CONFIG_DIR"] == str(config_dir)
    assert [k for k in seen["env"] if k in STRIPPED or k.startswith("CLAUDE_CODE_USE_")] == []
    assert os.path.realpath(seen["cwd"]) == os.path.realpath(os.environ["FCTL_HOME"])


def activate(client, account_id, status=200):
    r = client.post(f"/api/auth/accounts/{account_id}/activate", headers=H)
    assert r.status_code == status, r.text
    return r.json()


def disconnect(client, account_id, status=204):
    """DELETE /api/auth/accounts/{id}: None for the 204, which has no body, else the JSON."""
    r = client.delete(f"/api/auth/accounts/{account_id}", headers=H)
    assert r.status_code == status, r.text
    return None if status == 204 and r.content == b"" else r.json()


def test_accounts(client, fake_login, providers):  # 056 BE4
    fake_login(status=PRO_EMAIL)
    two = add_account()
    one = os.environ["CLAUDE_CONFIG_DIR"]
    assert api(client, "/api/auth/accounts") == [
        {"id": 1, "config_dir": one, "active": True, "signed_in": True, "auth_method": "claude.ai",
         "plan": "pro", "email": "artem@example.com"},
        {"id": two, "config_dir": str(account_dir(two)), "active": False, "signed_in": False,
         "auth_method": None, "plan": None, "email": None},
    ]
    first, second = fake_login.statuses()
    in_account(first, one)
    in_account(second, account_dir(two))
    sql("DELETE FROM claude_accounts")
    assert api(client, "/api/auth/accounts") == []


def test_auth_is_the_active_account(client, fake_login):  # 056 BE5, Q7
    fake_login(status=PRO_EMAIL)  # account 1, in the server's own CLAUDE_CONFIG_DIR
    two = add_account(TWO)
    make_active(two)
    assert api(client, "/api/auth") == TWO_AUTH
    [seen] = fake_login.statuses()
    assert seen["env"]["CLAUDE_CONFIG_DIR"] == str(account_dir(two)) != os.environ["CLAUDE_CONFIG_DIR"]
    sql("UPDATE claude_accounts SET active = 0")
    assert api(client, "/api/auth") == SIGNED_OUT
    assert len(fake_login.statuses()) == 1


def test_add_account(client, fake_login, providers):  # 056 BE6
    body = start(client, account=None)
    [(new, path, active)] = sql("SELECT id, config_dir, active FROM claude_accounts WHERE id != 1")
    assert body == {"url": SIGN_IN, "account_id": new}
    assert Path(path).parent == config.data_dir() / "claude-accounts" and Path(path).is_dir()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o700
    assert (active, active_ids()) == (0, [1])
    [seen] = fake_login.starts()
    in_account(seen, path)
    send(client, "good#state")
    [listed] = [a for a in api(client, "/api/auth/accounts") if a["id"] == new]
    assert (listed["signed_in"], listed["email"]) == (True, "artem@example.com")


def test_add_account_with_none_active(client, fake_login):  # 056 BE7, Q4
    sql("UPDATE claude_accounts SET active = 0")
    new = start(client, account=None)["account_id"]
    assert active_ids() == [new]
    send(client, "good#state")
    assert api(client, "/api/auth")["email"] == "artem@example.com"  # account 1 is CONSOLE, and inactive
    assert fake_login.statuses()[-1]["env"]["CLAUDE_CONFIG_DIR"] == str(account_dir(new))


def test_add_account_no_url(client, fake_login):  # 056 BE8
    fake_login("fail")
    assert start(client, 500, account=None) == {
        "detail": "claude auth login printed no sign-in URL: Error: managed settings forbid this"}
    assert account_count() == 1
    assert list((config.data_dir() / "claude-accounts").iterdir()) == []


def test_login_again(client, fake_login, monkeypatch, tmp_path):  # 056 BE9
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert start(client, 404, account=9) == {"detail": "Claude account #9 not found"}
    assert fake_login.starts() == []
    assert start(client) == {"url": SIGN_IN, "account_id": 1}
    [seen] = fake_login.starts()
    assert seen["env"]["CLAUDE_CONFIG_DIR"] == str(account_dir(1)) == str(tmp_path / "claude-config")
    assert account_count() == 1


@pytest.mark.parametrize("account", [1, None])
def test_login_code_for_another_account(client, fake_login, account):  # 056 BE10, Q5
    start(client)
    assert send(client, "good#state", 409, account=2) == NO_LOGIN
    assert fake_login.stdin() == []
    assert send(client, "good#state", account=account)["runs_enabled"] is True


def test_activate(client, fake_login, monkeypatch):  # 056 BE11
    monkeypatch.setattr(pages, "monotonic", lambda: 1000.0)  # every check well within the 60 s cache
    fake_login(status=PRO_EMAIL)
    two = add_account(TWO)
    assert api(client, "/api/auth")["email"] == "artem@example.com"  # primes the cache
    assert activate(client, two) == TWO_AUTH
    assert active_ids() == [two]
    assert api(client, "/api/auth") == TWO_AUTH
    assert activate(client, two) == TWO_AUTH
    assert active_ids() == [two]
    assert activate(client, 9, 404) == {"detail": "Claude account #9 not found"}


def emails() -> dict:
    return dict(sql("SELECT id, email FROM claude_accounts"))


def test_status_checks_store_email(client, fake_login, monkeypatch):  # 095 AC11
    monkeypatch.setattr(pages, "monotonic", lambda: 1000.0)
    two, three = add_account(TWO), add_account()
    fake_login(status=PRO_EMAIL)
    api(client, "/api/auth")  # the badge's cache fill
    assert emails() == {1: "artem@example.com", two: None, three: None}
    sql("UPDATE claude_accounts SET email = NULL")
    api(client, "/api/auth/accounts")
    assert emails() == {1: "artem@example.com", two: "two@example.com", three: None}
    put_status(account_dir(two), "not json")  # a failed check leaves the stored email
    fake_login(status=CONSOLE)
    api(client, "/api/auth/accounts")
    assert emails() == {1: "artem@example.com", two: "two@example.com", three: None}
    put_status(account_dir(two), TWO.replace("two@", "new@"))
    activate(client, two)
    assert emails()[two] == "new@example.com"
    start(client, account=three)  # the login code, for an inactive account: the fake's sign-in writes PRO_EMAIL
    send(client, "good#state", account=three)
    assert emails()[three] == "artem@example.com"


def test_accounts_refused_while_running(client, project, fake_login):  # 056 BE12, 055 BE4
    two = add_account(TWO)
    start(client, account=two)
    pgid = fake_login.starts()[0]["pgid"]
    add_run(add_task(project, status="in_progress"), "running")
    assert activate(client, two, 409) == {"detail": "a run is active"}
    assert active_ids() == [1]
    activate(client, 1)  # already active: 200, nothing changes, even during a run (§6.4)
    assert active_ids() == [1]
    assert disconnect(client, two, 409) == {"detail": "a run is active"}
    assert fake_login.logouts() == []
    assert account_dir(two).is_dir() and account_count() == 2
    os.killpg(pgid, 0)  # the login is still alive (ProcessLookupError if not)
    send(client, "good#state", account=two)
    assert fake_login.stdin() == ["good#state"]


def test_disconnect(client, fake_login, providers, monkeypatch):  # 056 BE13, 055 BE2
    calls, real = [], subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append((args, kw)) or real(args, **kw))
    two = add_account(TWO)
    path, one = account_dir(two), sql("SELECT * FROM claude_accounts WHERE id = 1")
    assert disconnect(client, two) is None
    [seen] = fake_login.logouts()
    assert seen["argv"] == ["auth", "logout"]
    in_account(seen, path)
    [(args, kw)] = [c for c in calls if "logout" in c[0]]
    assert args == ["claude", "auth", "logout"] and not kw.get("shell")
    assert not path.exists()
    assert sql("SELECT * FROM claude_accounts") == one


def test_disconnect_keeps_other_dirs(client, fake_login):  # 056 BE14, Q2
    one = Path(os.environ["CLAUDE_CONFIG_DIR"])
    (one / "settings.json").write_text("{}")
    assert disconnect(client, 1) is None
    assert account_count() == 0
    assert (one / "settings.json").read_text() == "{}"


def test_disconnect_active(client, fake_login):  # 056 BE15 (test_runs.py has its run refusal)
    two = add_account(TWO)
    assert disconnect(client, 1) is None
    assert active_ids() == []
    assert api(client, "/api/auth") == SIGNED_OUT
    activate(client, two)
    assert api(client, "/api/auth") == TWO_AUTH


@pytest.mark.parametrize("mode, detail", [
    ("fail", "claude auth logout failed: Error: keychain locked"),
    ("fail-stderr", "claude auth logout failed: Error: keychain locked"),
    ("silent", "claude auth logout exited with code 1"),
])
def test_disconnect_fails(client, fake_login, monkeypatch, mode, detail):  # 056 BE16, 055 BE3
    monkeypatch.setattr(pages, "monotonic", lambda: 1000.0)  # every check well within the 60 s cache
    fake_login(status=PRO_EMAIL, logout=mode)
    two = add_account(TWO)
    assert api(client, "/api/auth")["runs_enabled"] is True  # primes the cache
    assert disconnect(client, two, 500) == {"detail": detail}
    assert account_dir(two).is_dir() and account_count() == 2
    fake_login(status=CONSOLE, logout=mode)
    assert api(client, "/api/auth")["runs_enabled"] is False  # 055 Q4: cleared on failure too
    assert disconnect(client, 9, 404) == {"detail": "Claude account #9 not found"}


def test_disconnect_stops_its_login(client, fake_login):  # 056 BE17, Q12
    two = add_account()
    start(client, account=two)
    pgid = fake_login.starts()[0]["pgid"]
    assert disconnect(client, two) is None
    assert gone(pgid)
    assert send(client, "good#state", 409) == NO_LOGIN


def test_disconnect_leaves_other_login(client, fake_login):  # 056 BE17, Q12
    two = add_account()
    start(client)
    assert disconnect(client, two) is None
    assert send(client, "good#state")["runs_enabled"] is True
    assert fake_login.stdin() == ["good#state"]


def test_accounts_need_header(client, fake_login):  # 056 BE21, Q6
    two = add_account()
    assert client.post("/api/auth/logout", headers=H).status_code == 404
    before = sql("SELECT * FROM claude_accounts")
    for r in (client.post(f"/api/auth/accounts/{two}/activate"), client.delete(f"/api/auth/accounts/{two}"),
              client.post("/api/auth/login")):
        assert r.status_code == 403
    assert sql("SELECT * FROM claude_accounts") == before
    assert fake_login.starts() == fake_login.logouts() == []
    assert account_dir(two).is_dir()


def section(name, heading):
    """docs/<name>'s section from `heading` up to the next heading of the same or a higher level."""
    text = (REPO / "docs" / name).read_text(encoding="utf-8")
    level = heading.split(" ")[0]
    body = text[text.index(f"\n{heading}") + 1:]
    end = re.search(rf"\n#{{1,{len(level)}}} ", body)
    return body[:end.start()] if end else body


def test_login_docs():  # 039 AC16
    api_doc = section("data-model-and-api.md", "### 6.4")
    routes = api_doc[:api_doc.index("```")]
    assert "`/settings`" in routes
    auth_row = api_doc[api_doc.index("GET  /api/auth"):api_doc.index("POST /api/auth/login")]
    assert '"email"' in auth_row
    login_rows = api_doc[api_doc.index("POST /api/auth/login"):api_doc.index("GET  /api/pages/dashboard")]
    assert "POST /api/auth/login/code" in login_rows
    assert '{"url":' in login_rows and '{"code":' in login_rows
    for status in ("409", "422", "500"):
        assert f"# {status} {{\"detail\":" in login_rows
    ui = section("ui.md", "## 8.")
    assert "/settings" in ui[:ui.index("1. **Dashboard**")]
    assert ui.index("8. **Transcript**") < ui.index("9. **Settings** (`/settings`)")
    login_bullet = section("MVP.md", "### 4.6").split("- **Login.**")[1].split("\n- ")[0]
    assert "Settings page" in login_bullet


def test_accounts_docs():  # 056 BE22, after 055 BE7
    tables = section("data-model-and-api.md", "### 5.1")
    table = tables[tables.index("CREATE TABLE claude_accounts"):]
    assert all(column in table[:table.index(";")] for column in ("config_dir", "active", "created_at"))
    assert "CREATE UNIQUE INDEX one_active_account ON claude_accounts(active) WHERE active = 1" in tables
    api_doc = section("data-model-and-api.md", "### 6.4")
    auth = api_doc[api_doc.index("GET  /api/auth"):api_doc.index("GET  /api/pages/dashboard")]
    for row in ("GET  /api/auth/accounts", "POST /api/auth/accounts/{id}/activate",
                "DELETE /api/auth/accounts/{id}", '"account_id"'):
        assert row in auth, row
    assert "POST /api/auth/logout" not in auth
    ui = section("ui.md", "## 8.")
    settings = ui[ui.index("9. **Settings** (`/settings`)"):ui.index("10. **Reviews**")]
    for button in ("**+ Add account**", "**Make preferred**", "**Disconnect**"):  # 097 Q8: was Make active
        assert button in settings, button
    assert "CLAUDE_CONFIG_DIR=<account dir> claude --resume <session-id>" in section("MVP.md", "### 4.4")
    containers = section("MVP.md", "### 4.6")
    bullet = lambda name: containers.split(f"- **{name}.**")[1].split("\n- ")[0]  # noqa: E731
    assert "-e CLAUDE_CONFIG_DIR=" in bullet("Takeover")
    assert "Settings page" in bullet("Login") and "claude auth logout" in bullet("Login")


# --- GET /api/pages/sidebar (041) ----------------------------------------------------


def sidebar(client, query=""):
    return api(client, f"/api/pages/sidebar{query}")


def bare(client, workspace, name):
    """A project with no repo behind it, in `workspace` (created if new)."""
    r = client.post("/api/projects/connect", headers=H, json={
        "path": f"/code/{name}", "workspace": workspace, "name": name, "default_branch": "main"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def task_in_work(client):
    """A task in project `w` of `work`, behind a workspace `aaa` that sorts first: (task, project)."""
    bare(client, "aaa", "a")
    p = bare(client, "work", "w")
    return add_task(p), p


def test_sidebar(client):  # 041 BE1
    r = client.post("/api/workspaces", headers=H, json={"name": "aaa"})
    assert r.status_code == 200, r.text
    zeta, alpha = bare(client, "work", "zeta"), bare(client, "work", "alpha")
    zero = {"review": 0, "running": 0, "escalated": 0}
    page = sidebar(client)
    assert page.pop("usage") == api(client, "/api/usage")["accounts"]  # 095 AC19: the only new key
    assert page == {"workspaces": [  # dict equality: exactly these keys at every level
        {"id": r.json()["id"], "name": "aaa", "projects": []},
        {"id": ws_id("work"), "name": "work",
         "projects": [{"id": alpha, "name": "alpha"} | zero, {"id": zeta, "name": "zeta"} | zero]},
    ], "current": None}
    assert list(page["workspaces"][1]["projects"][0]) == ["id", "name", "review", "running", "escalated"]


def test_sidebar_counts(client, project):  # 041 BE2
    for stage in ("human_review", "human_review", "escalated", None):  # None: a manual move to Review
        add_task(project, status="review", stage=stage)
    add_run(add_task(project, status="in_progress", stage="build"), "running")
    add_run(add_task(project, status="in_progress", stage="build"), "failed")
    add_task(project, status="done")
    empty = bare(client, "personal", "zzz")
    projects = sidebar(client)["workspaces"][0]["projects"]
    assert projects == [{"id": project, "name": "repo", "review": 3, "running": 1, "escalated": 1},
                        {"id": empty, "name": "zzz", "review": 0, "running": 0, "escalated": 0}]
    assert all(type(v) is int for p in projects for k, v in p.items() if k != "name")


def test_sidebar_current_task(client):  # 041 BE3
    task, p = task_in_work(client)
    page = sidebar(client, f"?task={task}")
    assert page["current"] == {"workspace_id": ws_id("work"), "project_id": p}
    assert page["workspaces"] == sidebar(client)["workspaces"]


def test_sidebar_current_transcript(client):  # 041 BE4
    task, p = task_in_work(client)
    transcript = add_transcript(add_run(task, "succeeded"), task, "x/agent.jsonl")
    assert sidebar(client, f"?transcript={transcript}")["current"] == {"workspace_id": ws_id("work"),
                                                                       "project_id": p}


@pytest.mark.parametrize("query", ["?task=999", "?transcript=999"])
def test_sidebar_unknown_ids(client, query):  # 041 BE5: 200, never 404
    task_in_work(client)
    assert sidebar(client, query)["current"] is None


@pytest.mark.parametrize("query", ["?task=abc", "?transcript=abc"])
def test_sidebar_bad_id(client, query):  # 041 BE6
    detail = api(client, f"/api/pages/sidebar{query}", 422)["detail"]
    assert detail and all("msg" in e for e in detail)


class Boom:
    """A Git whose every attribute raises."""
    def __getattr__(self, name):
        raise AssertionError(f"git.{name} called")


def test_sidebar_no_git(client):  # 041 BE7
    task, p = task_in_work(client)
    client.app.dependency_overrides[get_git] = Boom
    page = sidebar(client, f"?task={task}")
    assert page["current"] == {"workspace_id": ws_id("work"), "project_id": p}
    assert page["workspaces"] == sidebar(client)["workspaces"]
    assert {"git", "claude"}.isdisjoint(inspect.signature(pages.sidebar).parameters)
    path = PKG / "handlers" / "pages.py"
    assert sql_outside(ast.parse(path.read_text()), path) == []


def test_sidebar_docs():  # 041 BE8
    api_doc = section("data-model-and-api.md", "### 6.4")
    assert "plus the sidebar's" in api_doc[:api_doc.index("```")]
    start = api_doc.index("GET  /api/pages/sidebar")
    assert api_doc.index('← 404 {"detail":"Task #99 not found"}') < start
    rows = api_doc[start:api_doc.index("GET  /api/docs/fctl")]
    for text in ("GET  /api/pages/sidebar?task=", "GET  /api/pages/sidebar?transcript=", '{"workspaces":',
                 '"current":', "# current: the workspace and project of the task", "for an unknown id"):
        assert text in rows, text
    ui = section("ui.md", "## 8.")
    intro = ui[:ui.index("1. **Dashboard**")]
    for text in ("left sidebar", "/api/pages/sidebar", "localStorage", "<dialog>", "/settings"):
        assert text in intro, text
    assert "Linked from the sidebar" in ui[ui.index("7. **fctl reference**"):ui.index("8. **Transcript**")]
    assert ui.index("### 8.3") < ui.index("### 8.4 Sidebar")


def test_project_pages_docs():  # 042 BE6
    ui = section("ui.md", "## 8.")
    intro = ui[:ui.index("1. **Dashboard**")]
    for text in ("Reviews", "Context", "project header"):
        assert text in intro, text
    board = ui[ui.index("3. **Project board**"):ui.index("4. **Task detail**")]
    for text in ("**Code**", "Create factory", "Project context", "Import"):
        assert text not in board, text
    marks = [ui.index(m) for m in ("9. **Settings**", "10. **Reviews**", "11. **Project context**",
                                   "12. **Project settings**", "### 8.1")]
    assert marks == sorted(marks)
    for i, route in enumerate(("/projects/{id}/reviews", "/projects/{id}/context", "/projects/{id}/settings"), 1):
        assert route in ui[marks[i]:marks[i + 1]], route
    assert ui.index("### 8.4 Sidebar") < ui.index("### 8.5 Reviews")
    for text in ("Reviews", "Context", "Settings"):
        assert text in section("ui.md", "### 8.4"), text
    assert "[Code]" not in section("ui.md", "### 8.1")
    api_doc = section("data-model-and-api.md", "### 6.4")
    routes = api_doc[:api_doc.index("```")]
    for route in ("/projects/{id}/reviews?tab=closed", "/projects/{id}/context", "/projects/{id}/settings"):
        assert route in routes, route
    row = api_doc[api_doc.index("GET  /api/pages/projects/{id} "):api_doc.index("GET  /api/pages/tasks/{id}")]
    for text in ("remote_url", "test_cmd", "stage, branch"):
        assert text in row, text
    assert "board editor" not in section("data-model-and-api.md", "### 6.1")
    assert "Project board → **Create factory**" not in section("MVP.md", "### 3.2")
    assert "clear it on the board" not in (REPO / "docs" / "claude-code.md").read_text(encoding="utf-8")
    fctl = (PKG / "fctl.md").read_text(encoding="utf-8")
    assert "on the project board" not in fctl and "board's editor" not in fctl


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
    assert list(page) == ["tiles", "counts", "show", "listed", "waiting", "escalated", "open_tasks", "done"]  # 045 BE6
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
    assert (page["waiting"], page["escalated"]) == ([], [])


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


def needs_you(project_id, stage, at=OLD, rounds=0, title="t", status="review"):
    """045: a task at `status` · `stage` last updated `at`, with rounds 1..rounds."""
    tid = add_task(project_id, title=title, status=status, stage=stage)
    sql("UPDATE tasks SET updated_at = ? WHERE id = ?", (at, tid))
    for n in range(1, rounds + 1):
        add_round(tid, n)
    return tid


def test_dashboard_needs_you(client, project):  # 045 BE1
    waiting = needs_you(project, "human_review", "2026-10-18T09:00:00Z", rounds=2, title="w")
    escalated = needs_you(project, "escalated", "2026-10-17T08:30:00Z", rounds=1, title="e")
    page = api(client, "/api/pages/dashboard")
    assert page["waiting"] == [{"id": waiting, "title": "w", "project_id": project, "project": "repo", "round": 2,
                                "since": "2026-10-18T09:00:00Z"}]
    assert page["escalated"] == [{"id": escalated, "title": "e", "project_id": project, "project": "repo",
                                  "round": 1, "since": "2026-10-17T08:30:00Z"}]


def test_dashboard_needs_you_only_review_stages(client, project):  # 045 BE2
    waiting, escalated = needs_you(project, "human_review"), needs_you(project, "escalated")
    needs_you(project, None, status="backlog")
    for stage in (None, "spec", "build", "agent_review", "approval", "rework"):
        needs_you(project, stage, status="in_progress", rounds=1)
    needs_you(project, None, rounds=1)
    needs_you(project, None, status="done", rounds=1)
    page = api(client, "/api/pages/dashboard")
    assert [t["id"] for t in page["waiting"]] == [waiting]
    assert [t["id"] for t in page["escalated"]] == [escalated]


def test_dashboard_needs_you_order(client, project):  # 045 BE3
    older = needs_you(project, "human_review", "2026-10-18T09:00:00Z")
    newest = needs_you(project, "human_review", "2026-10-19T09:00:00Z")
    tie = needs_you(project, "human_review", "2026-10-18T09:00:00Z")  # same since as `older`, higher id
    assert [t["id"] for t in api(client, "/api/pages/dashboard")["waiting"]] == [newest, tie, older]


def test_dashboard_needs_you_no_rounds(client, project):  # 045 BE4
    tid = needs_you(project, "human_review")
    assert [(t["id"], t["round"]) for t in api(client, "/api/pages/dashboard")["waiting"]] == [(tid, None)]


def test_dashboard_needs_you_ignores_show(client, project):  # 045 BE5
    needs_you(project, "human_review", rounds=2)
    needs_you(project, "escalated", rounds=1)
    add_run(add_task(project, status="in_progress", stage="build"), "succeeded", started=db.now())
    base = api(client, "/api/pages/dashboard")
    assert base["waiting"] and base["escalated"]
    for show in ("runs_week", "waiting", "bogus"):
        page = api(client, f"/api/pages/dashboard?show={show}")
        assert (page["waiting"], page["escalated"]) == (base["waiting"], base["escalated"]), show


def test_dashboard_docs():  # 045 BE7
    ui = section("ui.md", "## 8.")
    item = ui[ui.index("1. **Dashboard** (`/`)"):ui.index("2. **Workspace**")]
    bullets = item.split("\n   - ")[1:]
    assert bullets[0].startswith("First, **Needs you**")
    needs = " ".join(bullets[0].split())
    for part in ("`#id title` linking to `/tasks/{id}/review`", "the project linking to its board", "`round N`",
                 "the age since the task last changed", "red left bar", "`Nothing needs you.`", "ignores `?show=`"):
        assert part in needs, part
    assert needs.index("escalated tasks") < needs.index("waiting on me")  # Q2
    tiles = " ".join(bullets[1].split())
    assert "**Attention**: waiting on me, escalated, and running now." in tiles
    assert "`danger` for escalated and `accent` for the other two" in tiles  # Q6
    assert "**Throughput**: done this week, runs this week, then tasks per status" in tiles  # Q7
    flat = " ".join(item.split())
    assert "scrolls sideways" in flat
    assert "average and max, with one small inline-SVG bar per task beside them, oldest left" in flat  # Q8
    assert "Workspaces" not in item and "No projects yet" not in item  # Q9
    api_doc = section("data-model-and-api.md", "### 6.4")
    row = api_doc[api_doc.index("GET  /api/pages/dashboard"):api_doc.index("GET  /api/pages/workspaces/{id}")]
    assert "the waiting and escalated lists" in row
    assert "round, since}" in row


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


def test_workspace_legacy_row(client, project, unready):  # 059 BE11
    states = ("legacy", "uncommitted", "none")
    ids = {unready(state): state for state in states} | {project: "ready"}
    page = api(client, f"/api/pages/workspaces/{ws_id('personal')}")
    assert {p["id"]: p["factory"] for p in page["projects"]} == ids


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
                               "workspace_id": ws_id("personal"), "workspace": "personal",
                               "remote_url": None, "test_cmd": "pytest -q", "github_label": None,
                               "github_repo": None, "github_hint": page["project"]["github_hint"]}  # 108 AC5
    assert (page["factory"], page["hint"], page["can_run"]) == ("ready", None, True)
    assert page["workspaces"] == [{"id": ws_id("personal"), "name": "personal", "projects": 1}]
    assert list(page["columns"]) == ["backlog", "in_progress", "review", "done"]
    assert [t["id"] for t in page["columns"]["backlog"]] == [b, c, a]
    assert [t["id"] for t in page["columns"]["review"]] == [review]
    assert page["columns"]["in_progress"] == page["columns"]["done"] == []


# --- 096: concurrent runs: the cap on the board, the counts, and /api/settings -----------------


def test_board_run_cap(client, project, tmp_path):  # 096 AC29
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", "-b", "main", str(other))
    add_run(add_task(connect(client, other), status="in_progress"), "running")  # another project counts too
    page = api(client, f"/api/pages/projects/{project}")
    assert (page["runs_active"], page["max_concurrent_runs"], page["can_run"]) == (1, 2, True)
    add_run(add_task(project, status="in_progress"), "running")
    page = api(client, f"/api/pages/projects/{project}")
    assert (page["runs_active"], page["max_concurrent_runs"], page["factory"], page["can_run"]) == (2, 2, "ready", False)


def test_running_counts_two_runs(client, project):  # 096 AC30, AC31
    runs = [add_run(add_task(project, status="in_progress", stage="build"), "running") for _ in range(2)]
    assert sidebar(client)["workspaces"][0]["projects"][0]["running"] == 2
    assert api(client, "/api/pages/dashboard")["counts"]["running"] == 2
    assert sorted(r["id"] for r in api(client, "/api/pages/agents")["running"]) == runs


def put_settings(client, body, headers=H):
    return client.put("/api/settings", json=body, headers=headers)


def test_settings_default(client):  # 096 AC24
    assert api(client, "/api/settings") == {"max_concurrent_runs": 2}


def test_settings_put(client):  # 096 AC25
    r = put_settings(client, {"max_concurrent_runs": 3})
    assert (r.status_code, r.json()) == (200, {"max_concurrent_runs": 3})
    assert api(client, "/api/settings") == {"max_concurrent_runs": 3}


@pytest.mark.parametrize("body", [{"max_concurrent_runs": 0}, {"max_concurrent_runs": 11},
                                  {"max_concurrent_runs": None}, {"max_concurrent_runs": "x"}, {}])
def test_settings_put_invalid(client, body):  # 096 AC26
    r = put_settings(client, body)
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)
    assert api(client, "/api/settings") == {"max_concurrent_runs": 2}


def test_settings_put_needs_header(client):  # 096 AC27
    assert put_settings(client, {"max_concurrent_runs": 3}, headers={}).status_code == 403
    assert api(client, "/api/settings") == {"max_concurrent_runs": 2}


def test_lower_cap_below_running(client, project, fake):  # 096 AC28, Q3
    put_settings(client, {"max_concurrent_runs": 3})
    running = [(add_run(t := add_task(project, status="in_progress"), "running"), t) for _ in range(3)]
    r = put_settings(client, {"max_concurrent_runs": 2})
    assert (r.status_code, r.json()) == (200, {"max_concurrent_runs": 2})
    assert sql("SELECT COUNT(*) FROM runs WHERE status = 'running'") == [(3,)]
    r = client.post(f"/api/tasks/{add_task(project)}/run", headers=H)
    listed = ", ".join(f"#{r_} on #{t}" for r_, t in running)
    assert (r.status_code, r.json()) == (409, {"detail": f"3 runs active ({listed}); the limit is 2."
                                                         " Wait, stop one, or raise it in Settings"})


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
        "waiting": False, "escalated": False, "stalled": False, "branch": None, "description_md": "",
        "blocked": False, "blocked_by": [], "blocks": [],  # 094 AC15
        "module": None,  # 112 AC14
    }
    assert [found[bare][k] for k in ("round", "verdicts", "additions", "deletions", "run", "started_at")] == [None] * 6


def test_board_project_facts(client):  # 042 BE1
    r = client.post("/api/projects/connect", headers=H, json={
        "path": "/code/api", "workspace": "personal", "name": "api", "default_branch": "main",
        "remote_url": "git@github.com:me/repo.git", "test_cmd": "pytest -q"})
    assert r.status_code == 200, r.text
    p = r.json()["id"]
    assert api(client, f"/api/pages/projects/{p}")["project"] == {  # dict equality: no extra keys
        "id": p, "name": "api", "path": "/code/api", "default_branch": "main", "workspace_id": ws_id("personal"),
        "workspace": "personal", "remote_url": "git@github.com:me/repo.git", "test_cmd": "pytest -q",
        "github_label": None, "github_repo": "me/repo", "github_hint": None}  # 108 AC5


def test_board_project_facts_unset(client):  # 042 BE2
    project = api(client, f"/api/pages/projects/{bare(client, 'personal', 'api')}")["project"]
    assert project["remote_url"] is None and project["test_cmd"] is None


def test_card_branch(client, project):  # 042 BE3
    branched, plain = review_task(project, branch="factory/12-x"), add_task(project)
    found = cards(client, project)
    assert (found[branched]["branch"], found[plain]["branch"]) == ("factory/12-x", None)


def test_card_description(client, project):  # 048 BE12
    described, plain = review_task(project, description="Columns: *id*"), add_task(project)
    found = cards(client, project)
    assert (found[described]["description_md"], found[plain]["description_md"]) == ("Columns: *id*", "")


def test_task_list_keys(client, project):  # 042 BE4: the card's branch and position stay off §6.2's list
    review_task(project, branch="factory/12-x")
    [item] = api(client, f"/api/projects/{project}/tasks")
    assert set(item) == {"id", "title", "status", "stage", "round", "verdicts", "additions", "deletions", "run",
                         "blocked", "blocked_by", "blocks", "module"}  # 094 AC8, 112 AC14


def link(task_id, *blockers):
    for blocker in blockers:
        sql("INSERT INTO task_deps (task_id, blocked_by_id) VALUES (?, ?)", (task_id, blocker))


def test_card_links(client, project):  # 094 AC15
    done, open_ = add_task(project, "D", status="done"), add_task(project, "O", status="in_progress")
    task = add_task(project, "T")
    link(task, open_, done)
    found = cards(client, project)
    assert {k: found[task][k] for k in ("blocked", "blocked_by", "blocks")} == {
        "blocked": True, "blocks": [],
        "blocked_by": [{"id": done, "title": "D", "status": "done"}, {"id": open_, "title": "O", "status": "in_progress"}]}
    assert (found[done]["blocked"], found[done]["blocks"]) == (False, [task])
    assert (found[open_]["blocked"], found[open_]["blocked_by"], found[open_]["blocks"]) == (False, [], [task])


def test_task_page_links(client, project):  # 094 AC16, Q8
    later, task = add_task(project, "Later", status="done"), add_task(project, "Task")
    first, waiting = add_task(project, "First", status="review", stage="human_review"), add_task(project, "Waiting")
    add_task(connect(client, "/code/other"), "Elsewhere")
    link(task, first, later)
    link(waiting, task)
    page = api(client, f"/api/pages/tasks/{task}")
    assert page["blocked_by"] == [{"id": later, "title": "Later", "status": "done"},
                                  {"id": first, "title": "First", "status": "review"}]
    assert page["blocks"] == [{"id": waiting, "title": "Waiting", "status": "backlog"}]
    assert page["project_tasks"] == [{"id": later, "title": "Later", "status": "done"},
                                     {"id": first, "title": "First", "status": "review"},
                                     {"id": waiting, "title": "Waiting", "status": "backlog"}]
    bare = api(client, f"/api/pages/tasks/{first}")
    assert (bare["blocked_by"], bare["blocks"]) == ([], [{"id": task, "title": "Task", "status": "backlog"}])


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


@pytest.mark.parametrize("state, hint", [("uncommitted", UNCOMMITTED), ("none", NONE), ("legacy", LEGACY_HINT)])
def test_board_factory_not_ready(client, unready, state, hint):  # 026 AC14, 042 BE5, 059 BE9
    page = api(client, f"/api/pages/projects/{unready(state)}")
    assert (page["factory"], page["can_run"], page["hint"]) == (state, False, hint)


def test_board_factory_files(client, unready):  # 059 BE12, Q3
    pid = unready("none")
    page = api(client, f"/api/pages/projects/{pid}")
    assert page["factory_files"] == []
    agents = ".claude/agents/"  # builder-backend.md is the bootstrap's, not one of Create factory's 8
    write(Path(page["project"]["path"]), {f"{agents}review-code.md": "x", f"{agents}builder-backend.md": "x",
                                          f"{agents}spec-writer.md": "x", SKILL: "x"})
    assert api(client, f"/api/pages/projects/{pid}")["factory_files"] == [SKILL, f"{agents}spec-writer.md",
                                                                          f"{agents}review-code.md"]


def test_board_legacy_still_syncs(client, unready):  # 059 BE13, 058
    pid = unready("legacy")
    write(Path(api(client, f"/api/pages/projects/{pid}")["project"]["path"]), {"factory/backlog.md": BACKLOG})
    page = api(client, f"/api/pages/projects/{pid}")
    assert [c["title"] for c in page["columns"]["backlog"]] == ["Alpha", "Beta"]
    assert (page["factory"], page["factory_error"]) == ("legacy", None)


def test_board_console_auth(client, project, fake):  # 026 AC15
    fake(auth=CONSOLE)
    page = api(client, f"/api/pages/projects/{project}")
    assert (page["factory"], page["can_run"], page["hint"]) == ("ready", False, None)


# --- 058: the board's factory/ sync ---------------------------------------------------

BACKLOG = "## Next\n\n- [ ] 101-alpha: first\n- [ ] 102-beta: second\n"


def sync_board(client, project_id) -> dict:
    return api(client, f"/api/pages/projects/{project_id}")


def alpha(page) -> dict:
    return next(c for c in page["columns"]["backlog"] if c["title"] == "Alpha")


@pytest.fixture
def imports(monkeypatch):
    """How many times the board's sync ran 031's import."""
    calls, real = [], factory_import.import_factory
    monkeypatch.setattr(factory_import, "import_factory", lambda *a: calls.append(a) or real(*a))
    return calls


def test_board_syncs_new_backlog(client, project, repo):  # BE20
    add_task(project, position=3.0)
    write(repo, {"factory/backlog.md": BACKLOG})
    page = sync_board(client, project)
    assert [c["title"] for c in page["columns"]["backlog"]] == ["t", "Alpha", "Beta"]
    assert page["factory_error"] is None


def test_board_unchanged_files_dont_sync(client, project, repo, imports):  # BE21
    write(repo, {"factory/backlog.md": BACKLOG})
    sync_board(client, project)
    sql("UPDATE tasks SET description_md = 'edited' WHERE import_key = 'factory:101-alpha'")
    assert alpha(sync_board(client, project))["description_md"] == "edited"
    assert len(imports) == 1


def test_board_resyncs_on_mtime(client, project, repo):  # BE22
    write(repo, {"factory/backlog.md": BACKLOG})
    sync_board(client, project)
    sql("UPDATE tasks SET description_md = 'edited' WHERE import_key = 'factory:101-alpha'")
    path = repo / "factory" / "backlog.md"
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10**9))
    assert alpha(sync_board(client, project))["description_md"] == "## Next\n\nfirst"


def test_board_resyncs_on_size(client, project, repo):  # BE23
    write(repo, {"factory/backlog.md": BACKLOG})
    sync_board(client, project)
    path = repo / "factory" / "backlog.md"
    old = path.stat()
    write(repo, {"factory/backlog.md": BACKLOG.replace("first", "first, longer")})
    os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert alpha(sync_board(client, project))["description_md"] == "## Next\n\nfirst, longer"


def test_board_resyncs_on_board_json(client, project, repo):  # BE24
    write(repo, {"factory/board.json": json.dumps({"jobs": [{"id": "001-a", "title": "Job A", "status": "backlog"}]})})
    sync_board(client, project)
    sql("UPDATE tasks SET title = 'renamed' WHERE import_key = 'factory:001-a'")
    path = repo / "factory" / "board.json"
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10**9))
    assert [c["title"] for c in sync_board(client, project)["columns"]["backlog"]] == ["Job A"]


def test_board_refusal_never_fails(client, project, repo, imports):  # BE25, Q10, Q11
    tid = add_task(project)
    write(repo, {"factory/board.json": "{not json", "factory/backlog.md": BACKLOG})
    page = sync_board(client, project)
    assert [c["id"] for c in page["columns"]["backlog"]] == [tid]
    assert page["factory_error"] == "factory/board.json isn't valid JSON"
    assert sync_board(client, project)["factory_error"] == "factory/board.json isn't valid JSON"
    assert len(imports) == 1
    write(repo, {"factory/board.json": json.dumps({"jobs": []})})
    page = sync_board(client, project)
    assert page["factory_error"] is None
    assert [c["title"] for c in page["columns"]["backlog"]] == ["t", "Alpha", "Beta"]
    assert len(imports) == 2


def test_board_without_factory_files(client, project, imports):  # BE26
    assert sync_board(client, project)["factory_error"] is None
    assert sql("SELECT factory_mark, factory_error FROM projects WHERE id = ?", (project,)) == [(None, None)]
    assert imports == []


def test_board_cross_site_skips_sync(client, project, repo, imports):  # 058 round 2 feedback, MVP §4.5
    write(repo, {"factory/backlog.md": BACKLOG})
    sql("UPDATE projects SET factory_error = 'stored' WHERE id = ?", (project,))
    r = client.get(f"/api/pages/projects/{project}", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200, r.text
    assert (r.json()["columns"]["backlog"], r.json()["factory_error"]) == ([], "stored")
    assert imports == [] and sql("SELECT factory_mark FROM projects WHERE id = ?", (project,)) == [(None,)]
    r = client.get(f"/api/pages/projects/{project}", headers={"Sec-Fetch-Site": "same-origin"})
    assert [c["title"] for c in r.json()["columns"]["backlog"]] == ["Alpha", "Beta"]
    assert r.json()["factory_error"] is None and len(imports) == 1


# --- GET /api/pages/tasks/{id} --------------------------------------------------------


def test_task(client, project):  # AC13
    tid = review_task(project, title="T", description="Max **5**", spec="## Goal", branch="factory/1-t")
    bare = review_task(project, status="backlog", stage=None)
    page = api(client, f"/api/pages/tasks/{tid}")
    assert page["task"] == {
        "id": tid, "project_id": project, "project": "repo", "workspace_id": ws_id("personal"),
        "workspace": "personal", "title": "T", "status": "review",
        "stage": "human_review", "branch": "factory/1-t", "worktree_path": "/code/api/.claude/worktrees/12-x",
        "description_md": "Max **5**", "description_html": "<p>Max <strong>5</strong></p>\n",
        "spec_md": "## Goal", "spec_html": "<h2>Goal</h2>\n", "issue_url": None, "module": None,  # 108 AC22, 112 AC14
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
                           "started_at": STARTED, "account": None}  # 097 AC24: no account_id
    one = shlex.quote(os.environ["CLAUDE_CONFIG_DIR"])  # 056: account 1, active (097 AC22: the NULL fallback)
    assert page["takeover"] == (f"cd {shlex.quote(worktree)} && CLAUDE_CONFIG_DIR={one} claude"
                                f" --resume {shlex.quote(session)}")
    sql("UPDATE runs SET status = 'running' WHERE id = ?", (run,))
    page = api(client, f"/api/pages/tasks/{tid}")
    assert (page["run"]["status"], page["takeover"]) == ("running", None)
    page = api(client, f"/api/pages/tasks/{review_task(project)}")
    assert (page["run"], page["takeover"]) == (None, None)


DOCKER_WT, DOCKER_SESSION = "/code/my api/.claude/worktrees/1-t", "sess'1"


def test_task_takeover_in_docker(client, project, monkeypatch):  # 028 AC1, 056 BE20: no active account
    monkeypatch.setenv("FCTL_IN_DOCKER", "1")
    sql("DELETE FROM claude_accounts")
    tid = review_task(project, worktree=DOCKER_WT)
    run = add_run(tid, "stopped", session=DOCKER_SESSION)
    takeover = api(client, f"/api/pages/tasks/{tid}")["takeover"]
    assert takeover == (f"docker compose exec -w {shlex.quote(DOCKER_WT)} backend claude"
                        f" --resume {shlex.quote(DOCKER_SESSION)}")
    sql("UPDATE runs SET status = 'running' WHERE id = ?", (run,))
    assert api(client, f"/api/pages/tasks/{tid}")["takeover"] is None


@pytest.mark.parametrize("value", [None, "0", ""])
def test_task_takeover_on_host(client, project, monkeypatch, value):  # 028 AC3, 056 BE20: no active account
    if value is not None:
        monkeypatch.setenv("FCTL_IN_DOCKER", value)
    sql("DELETE FROM claude_accounts")
    tid = review_task(project, worktree=DOCKER_WT)
    add_run(tid, "stopped", session=DOCKER_SESSION)
    assert api(client, f"/api/pages/tasks/{tid}")["takeover"] == (
        f"cd {shlex.quote(DOCKER_WT)} && claude --resume {shlex.quote(DOCKER_SESSION)}")


@pytest.mark.parametrize("docker", [False, True])
def test_task_takeover_names_account(client, project, monkeypatch, docker):  # 056 BE20
    if docker:
        monkeypatch.setenv("FCTL_IN_DOCKER", "1")
    two = sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES ('/home/me/it''s 2', ?) RETURNING id",
              (OLD,))[0][0]
    make_active(two)
    tid = review_task(project, worktree=DOCKER_WT)
    add_run(tid, "stopped", session=DOCKER_SESSION)
    wt, session, named = shlex.quote(DOCKER_WT), shlex.quote(DOCKER_SESSION), shlex.quote("/home/me/it's 2")
    assert api(client, f"/api/pages/tasks/{tid}")["takeover"] == (
        f"docker compose exec -w {wt} -e CLAUDE_CONFIG_DIR={named} backend claude --resume {session}" if docker
        else f"cd {wt} && CLAUDE_CONFIG_DIR={named} claude --resume {session}")


def test_isolated_unsets_in_docker():  # 028 AC6: fails under `FCTL_IN_DOCKER=1 uv run pytest` without it
    assert "FCTL_IN_DOCKER" not in os.environ


@pytest.mark.parametrize("case, hint", [("uncommitted", UNCOMMITTED), ("none", NONE), ("legacy", LEGACY_HINT),
                                        ("console", None)])
def test_task_runs_disabled(client, project, unready, fake, case, hint):  # 026 AC16, 042 BE5, 059 BE10
    if case == "console":
        fake(auth=CONSOLE)
    else:
        project = unready(case)
    page = api(client, f"/api/pages/tasks/{add_task(project)}")
    assert (page["can_run"], page["hint"]) == (False, hint)


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
    assert set(page) == {"task", "pr", "rounds", "selected", "approver", "files", "timeline"}  # 093: pr
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


def test_code_landing(client, code_project, repo):  # AC23, 047 BE3: exactly these project keys
    page = api(client, f"/api/pages/projects/{code_project}/code")
    assert page["project"] == {"id": code_project, "name": "repo", "path": str(repo),
                               "workspace_id": ws_id("personal"), "workspace": "personal", "web_url": None}
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
def test_code_git_failure(client, tmp_path, kind):  # 026 AC30, 047 BE4
    """The JSON carries git's own message; the SPA prefixes "Can't list files in <path>: " (CodePage.jsx)."""
    path = tmp_path / kind.replace(" ", "-")
    if kind == "not a repo":
        path.mkdir()
    pid = connect(client, path)
    page = code(client, pid).json()
    assert page["error"].startswith("fatal: ")
    assert page["tree"] == {}
    assert page["project"] == {"id": pid, "name": "repo", "path": str(path),
                               "workspace_id": ws_id("personal"), "workspace": "personal", "web_url": None}


def set_remote(project_id, remote):
    sql("UPDATE projects SET remote_url = ? WHERE id = ?", (remote, project_id))


def test_code_web_url(client, code_project):  # 090 AC8
    page = code(client, code_project).json()
    assert page["project"]["web_url"] is None
    set_remote(code_project, "git@github.com:owner/repo.git")
    page = code(client, code_project).json()
    assert page["project"]["web_url"] == "https://github.com/owner/repo"
    assert "remote_url" not in page["project"] and "default_branch" not in page["project"]


def test_code_file_url(client, repo):  # 090 AC9
    commit(repo, {"src/a.py": "a\n", "a b#c.txt": "x\n"})
    pid = connect(client, repo)
    set_remote(pid, "git@github.com:owner/repo.git")
    assert code(client, pid, "src/a.py").json()["file_url"] == "https://github.com/owner/repo/blob/main/src/a.py"
    assert code(client, pid, "a b#c.txt").json()["file_url"] == "https://github.com/owner/repo/blob/main/a%20b%23c.txt"


def test_code_file_url_null(client, code_project, tmp_path):  # 090 AC10
    assert code(client, code_project, "src/a.py").json()["file_url"] is None  # no web_url
    set_remote(code_project, "git@github.com:owner/repo.git")
    assert code(client, code_project).json()["file_url"] is None  # the landing
    set_remote(code_project, "git@gitlab.com:owner/repo.git")
    page = code(client, code_project, "src/a.py").json()
    assert (page["project"]["web_url"], page["file_url"]) == ("https://gitlab.com/owner/repo", None)
    gone = connect(client, tmp_path / "gone")
    set_remote(gone, "git@github.com:owner/repo.git")
    page = code(client, gone, "src/a.py").json()
    assert page["error"] and page["file_url"] is None


def test_code_web_url_on_git_failure(client, tmp_path):  # 090 AC11
    pid = connect(client, tmp_path / "gone")
    set_remote(pid, "https://token@github.com/owner/repo.git")
    page = code(client, pid).json()
    assert page["error"].startswith("fatal: ")
    assert page["project"]["web_url"] == "https://github.com/owner/repo"


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


# --- 054: ?branch= on the code page ----------------------------------------------------


def commit_on(repo, branch, files):
    """Commit `files` on the existing `branch`, then check main out again."""
    git(repo, "checkout", "-q", branch)
    sha = commit(repo, files)
    git(repo, "checkout", "-q", "main")
    return sha


@pytest.fixture
def branched(repo):
    """main (checked out) and feature-x; origin/main, origin/old, origin/HEAD \u2192 origin/main, upstream/z, tag v1."""
    main = commit(repo, {"README.md": "# Main\n", "src/a.py": "a = 1\n"})
    for name in ("feature-x", "tmp"):
        git(repo, "branch", name)
    commit_on(repo, "feature-x", {"README.md": "# Feature\n", "only.py": "x = 1\ny = 2\n"})
    old = commit_on(repo, "tmp", {"README.md": "# Old\n", "old.txt": "old\n"})
    git(repo, "branch", "-q", "-D", "tmp")
    for ref, sha in (("origin/main", main), ("origin/old", old), ("upstream/z", main)):
        git(repo, "update-ref", f"refs/remotes/{ref}", sha)
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(repo, "tag", "v1")
    return repo


def browse(client, project_id, status=200, **params):
    """The code view-model's response for these query params, checked for status and JSON."""
    r = client.get(f"/api/pages/projects/{project_id}/code", params=params)
    assert (r.status_code, r.headers["content-type"]) == (status, "application/json"), r.text
    return r


def test_code_branches_listed(client, branched):  # 054 BE1
    page = browse(client, connect(client, branched)).json()
    assert (page["branches"], page["branch"]) == (["feature-x", "main", "origin/old"], "main")


def test_code_branch_tree(client, branched):  # 054 BE2
    write(branched, {"src/a.py": "edited = 1\n", "untracked.txt": "u"})
    page = browse(client, connect(client, branched), branch="feature-x").json()
    assert page["tree"] == {"README.md": {"path": "README.md"}, "only.py": {"path": "only.py"},
                            "src/": {"a.py": {"path": "src/a.py"}}}
    assert (page["shown"], page["branch"]) == ("README.md", "main")
    assert "<h1>Feature</h1>" in page["readme_html"]


def test_code_branch_file(client, branched):  # 054 BE3
    page = browse(client, connect(client, branched), branch="feature-x", path="only.py").json()
    assert (page["view"], page["lang"], page["readme_html"]) == ({"text": "x = 1\ny = 2\n", "lines": 2}, "py", None)


def test_code_origin_branch(client, branched):  # 054 BE4
    page = browse(client, connect(client, branched), branch="origin/old").json()
    assert page["tree"] == {"README.md": {"path": "README.md"}, "old.txt": {"path": "old.txt"},
                            "src/": {"a.py": {"path": "src/a.py"}}}
    assert page["shown"] == "README.md" and "<h1>Old</h1>" in page["readme_html"]


class SmallBlobsOnly(SubprocessGit):
    """054 Q5: a blob over 1 MB is never read."""
    def blob(self, root, oid):
        data, error = super().blob(root, oid)
        assert data is None or len(data) <= 1024 * 1024, "read a blob over 1 MB"
        return data, error


def test_code_branch_blob_rules(client, branched):  # 054 BE5
    commit_on(branched, "feature-x", {"logo.bin": b"\x00\x01\x02", "big.txt": b"x" * (1024 * 1024 + 1),
                                      "max.txt": b"y" * (1024 * 1024), "empty.txt": b"", "latin.txt": b"caf\xe9\n"})
    pid = connect(client, branched)
    client.app.dependency_overrides[get_git] = SmallBlobsOnly
    views = {p: browse(client, pid, branch="feature-x", path=p).json()["view"]
             for p in ("logo.bin", "big.txt", "max.txt", "empty.txt", "latin.txt")}
    assert views == {"logo.bin": {"note": "Binary file not shown."}, "big.txt": {"note": "File over 1 MB not shown."},
                     "max.txt": {"text": "y" * (1024 * 1024), "lines": 1}, "empty.txt": {"note": "Empty file."},
                     "latin.txt": {"text": "caf\ufffd\n", "lines": 1}}


def test_code_checked_out_branch_is_working_tree(client, branched):  # 054 BE6
    write(branched, {"README.md": "# Edited on disk\n"})
    pid = connect(client, branched)
    for query in ({}, {"path": "README.md"}):
        assert browse(client, pid, branch="main", **query).json() == browse(client, pid, **query).json()
    page = browse(client, pid, branch="main").json()
    assert page["view"]["text"] == "# Edited on disk\n" and "<h1>Edited on disk</h1>" in page["readme_html"]


def test_code_unborn_checked_out_branch(client, tmp_path):  # 054 Q2 (round 2): no commits, so nothing is listed
    git(tmp_path, "init", "-q", "-b", "main", str(tmp_path / "unborn"))
    pid = connect(client, tmp_path / "unborn")
    page = browse(client, pid, branch="main").json()
    assert page == browse(client, pid).json() and (page["branch"], page["branches"]) == ("main", [])


def test_code_unlisted_branch_404(client, branched, tmp_path):  # 054 BE7
    pid = connect(client, branched)
    out = tmp_path / "x"
    for value in ("nope", "HEAD", "main~1", "main^{tree}", git(branched, "rev-parse", "HEAD"), "refs/heads/main",
                  "origin/HEAD", "origin/main", "upstream/z", "v1", "-h", f"--output={out}"):
        assert browse(client, pid, 404, branch=value).json() == {"detail": f"{value} is not a branch in repo"}
    assert not out.exists()


def test_code_branch_not_shadowed_by_tag(client, branched):  # 054 BE8
    git(branched, "tag", "feature-x", "main")
    page = browse(client, connect(client, branched), branch="feature-x").json()
    assert "only.py" in page["tree"] and "<h1>Feature</h1>" in page["readme_html"]


def test_code_branch_untracked_paths_404(client, branched, tmp_path):  # 054 BE9
    commit(branched, {"main_only.txt": "TOP-SECRET-main"})
    (tmp_path / "outside.txt").write_text("TOP-SECRET-outside")
    write(branched, {"untracked.txt": "TOP-SECRET-untracked"})
    pid = connect(client, branched)
    for path in ("main_only.txt", "../outside.txt", "untracked.txt"):
        r = browse(client, pid, 404, branch="feature-x", path=path)
        assert r.json() == {"detail": f"{path} is not a tracked file in repo"}
        assert "TOP-SECRET" not in r.text


def test_code_branch_symlink_is_its_target(client, branched, tmp_path):  # 054 BE10
    (tmp_path / "secret.txt").write_text(SECRET)
    git(branched, "checkout", "-q", "feature-x")
    os.symlink(tmp_path / "secret.txt", branched / "leak")
    commit(branched)
    git(branched, "checkout", "-q", "main")
    r = browse(client, connect(client, branched), branch="feature-x", path="leak")
    assert r.json()["view"] == {"text": str(tmp_path / "secret.txt"), "lines": 1}
    assert SECRET not in r.text


@pytest.mark.parametrize("target", ["commit", "annotated tag"])
def test_code_branch_gitlink_not_shown(client, branched, tmp_path, target):  # 054 Q5, Q6 (rounds 2-3 security)
    """A gitlink naming a local commit, or a tag of a blob over 1 MB: never the object it names, never read."""
    (tmp_path / "big").write_bytes(b"B" * (1024 * 1024 + 1))
    git(branched, "tag", "-a", "-m", "t", "big", git(branched, "hash-object", "-w", str(tmp_path / "big")))
    oid = git(branched, "rev-parse", "main" if target == "commit" else "big")
    git(branched, "checkout", "-q", "feature-x")
    git(branched, "update-index", "--add", "--cacheinfo", f"160000,{oid},sub")
    git(branched, "commit", "-q", "-m", "gitlink")
    git(branched, "checkout", "-q", "main")
    pid = connect(client, branched)
    client.app.dependency_overrides[get_git] = SmallBlobsOnly
    r = browse(client, pid, branch="feature-x", path="sub")
    assert r.json()["view"] == {"note": "Not shown: not a regular file."}
    assert oid not in r.text and "Main" not in r.text and "BBBB" not in r.text


@pytest.mark.parametrize("kind", ["missing", "not a repo"])
@pytest.mark.parametrize("params", [{}, {"branch": "x"}])
def test_code_branch_git_failure(client, tmp_path, kind, params):  # 054 BE11
    path = tmp_path / kind.replace(" ", "-")
    if kind == "not a repo":
        path.mkdir()
    page = browse(client, connect(client, path), **params).json()
    assert page["error"].startswith("fatal: ")
    assert (page["branch"], page["branches"], page["tree"]) == (None, [], {})


def test_context_library_docs():  # 057 BE23
    tables = section("data-model-and-api.md", "### 5.1")
    table = tables[tables.index("CREATE TABLE context_items"):]
    table = table[:table.index(";")]
    for column in ("project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE",
                   "parent_id INTEGER REFERENCES context_items(id) ON DELETE CASCADE", "CHECK (kind IN ('item','group'))",
                   "title", "description", "content_md", "source_path", "position REAL", "created_at", "updated_at"):
        assert column in table, column
    relations = " ".join(tables[tables.index("Relations:"):].split())
    assert "0–n context items, removed with it" in relations
    projects = section("data-model-and-api.md", "### 6.1")
    rows = {
        "GET  /api/projects/3/context/items ": ['"detail":"Project #99 not found"'],
        "POST /api/projects/3/context/items ": [
            "title must not be blank", "description over 160 characters", "a group has no content",
            "groups are one level deep", "parent_id 7 is not a group of this project", "card over 16 KB",
            "project context over 64 KB", "every 4xx writes nothing"],
        "POST /api/projects/3/context/items/upload?name=": ["only .md, .markdown, and .txt files", "not UTF-8"],
        "POST /api/projects/3/context/items/from-path ": [
            "path must be absolute", "no file or folder at", "no .md, .markdown, or .txt files",
            "51 files; the limit is 50", "Permission denied"],
        "PATCH /api/context/items/5 ": ["send at least one of: title, description, content_md, parent_id, position",
                                        "Context item #99 not found"],
        "DELETE /api/context/items/5 ": ["ON DELETE CASCADE"],
        "POST /api/context/items/5/reload ": ["only a card read from a path can be reloaded", "no file at"],
    }
    starts = [projects.index(row) for row in rows]
    assert starts == sorted(starts)
    for (row, texts), start, end in zip(rows.items(), starts, [*starts[1:], projects.index("```", starts[-1])]):
        for text in texts:
            assert text in projects[start:end], (row, text)
    assert "<ContextItem> = {" in projects and "**Derived titles and descriptions.**" in projects
    context_row = section("data-model-and-api.md", "### 6.2")
    context_row = context_row[context_row.index("GET  /api/tasks/12/context"):context_row.index("PATCH /api/tasks/12")]
    assert "the pinned context_md, then the context cards" in " ".join(context_row.split())
    [show] = [line for line in section("claude-code.md", "### 7.2").splitlines() if line.startswith("| `fctl show")]
    assert "the pinned context, then the project's context cards" in show
    routes = section("data-model-and-api.md", "### 6.4")
    assert "`/projects/{id}/context` loads" in routes and "/context/items` for the rest" in routes
    ui = section("ui.md", "## 8.")
    item = ui[ui.index("11. **Project context**"):ui.index("12. **Project settings**")]
    for text in ("Stack and conventions", "<dialog>", "Upload files", "Add from path", "Reload from path"):
        assert text in item, text
    assert ui.index("### 8.8 Agents") < ui.index("### 8.9 Context")
    wireframe = section("ui.md", "### 8.9")
    grid = wireframe[wireframe.index("[+ New card] [+ New group]"):wireframe.index("⋯ → a native popover menu")]
    for text in ("api-server · personal", "Upload files", "Path [", "[Add from path]", "2 cards", "README.md"):
        assert text in wireframe[:wireframe.index("⋯ → ")], text
    assert grid.index("Stack and conventions") < grid.index("API conventions") < grid.index("Runbooks")
    menu, modal, dialog = (wireframe.index(m) for m in ("\n⋯ → ", "\nRunbooks → the group modal",
                                                         "\nAPI conventions → the card dialog"))
    for text in ("Edit", "Reload from path", "Move to group", "Move out of group", "Delete"):
        assert text in wireframe[menu:modal], text
    assert "[Close]" in wireframe[modal:dialog] and "Deploy" in wireframe[modal:dialog]
    assert "16384 bytes" in wireframe[dialog:] and "Preview" in wireframe[dialog:]
    safety = " ".join(section("MVP.md", "### 4.5").split())
    for text in ("context card over 16 KB", "over 64 KB in all", "`.md`, `.markdown`, and `.txt` regular files",
                 "never subfolders", "at most 50 per folder", "writes nothing to disk"):
        assert text in safety, text
    assert "MAX_CONTEXT_TOTAL, MAX_CONTEXT_FILES" in section("MVP.md", "### 4.7")


def test_code_branch_docs():  # 054 BE12
    ui = section("ui.md", "## 8.")
    item = ui[ui.index("6. **Project code**"):ui.index("7. **fctl reference**")]
    for text in ("?branch=", "git ls-tree", "\u00a78.6", "`+/\u2212`"):
        assert text in item, text
    wireframe = section("ui.md", "### 8.6")
    assert "Branch [main \u25be]" in wireframe and "\nBranch main\n" not in wireframe
    api_doc = section("data-model-and-api.md", "### 6.4")
    assert "/projects/{id}/code?path=&branch=" in api_doc and "branches" in api_doc
    assert "?branch=" in section("MVP.md", "### 4.5")
    later = section("MVP.md", "## 9.").split("**Later**")[1]
    assert "Worktree browsing on the code page." in later and "Branch and worktree browsing" not in later


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


# --- 047: the breadcrumb's workspace ---------------------------------------------------


def test_task_workspace(client):  # 047 BE1
    task, _ = task_in_work(client)
    found = api(client, f"/api/pages/tasks/{task}")["task"]
    assert set(found) == TASK_KEYS | {"issue_url"}  # 108 AC22
    assert (found["workspace_id"], found["workspace"]) == (ws_id("work"), "work")


def test_review_workspace(client):  # 047 BE2
    task, _ = task_in_work(client)
    found = api(client, f"/api/pages/tasks/{task}/review")["task"]
    assert set(found) == TASK_KEYS | {"commit_hint"}
    assert (found["workspace_id"], found["workspace"]) == (ws_id("work"), "work")


def test_moved_project_workspace(client):  # 047 BE5: joined at read time, never a stored copy
    task, p = task_in_work(client)
    transcript = add_transcript(add_run(task, "succeeded"), task, "x/agent.jsonl", text="")

    def reported():
        return {(got["workspace_id"], got["workspace"]) for got in (
            api(client, f"/api/pages/tasks/{task}")["task"], api(client, f"/api/pages/tasks/{task}/review")["task"],
            code(client, p).json()["project"], api(client, f"/api/transcripts/{transcript}"))}

    assert reported() == {(ws_id("work"), "work")}
    r = client.patch(f"/api/projects/{p}", json={"workspace_id": ws_id("aaa")}, headers=H)
    assert r.status_code == 200, r.text
    assert reported() == {(ws_id("aaa"), "aaa")}


def test_breadcrumb_docs():  # 047 BE7
    ui = section("ui.md", "## 8.")
    intro = ui[:ui.index("1. **Dashboard**")]
    for text in ("The task, review, code, and transcript pages", "breadcrumb", "›", "`/workspaces/{id}`"):
        assert text in intro, text
    task_item = ui[ui.index("4. **Task detail**"):ui.index("5. **Code review**")]
    for text in ("title row", "**Export** opens a native popover", "**Include transcripts**"):
        assert text in task_item, text
    review_item = ui[ui.index("5. **Code review**"):ui.index("6. **Project code**")]
    for text in ("**Review changes**", "**Submit review**", "**Copy**", "`navigator.clipboard`"):
        assert text in review_item, text
    wireframe = section("ui.md", "### 8.2")
    assert "personal › api-server › #12 › Review" in wireframe and "[Review changes" in wireframe
    assert "[Approve]" not in wireframe and "[Request changes]" not in wireframe
    transcript_item = ui[ui.index("8. **Transcript**"):ui.index("9. **Settings**")]
    assert "a link to its task" not in transcript_item and "breadcrumb" in transcript_item


def test_breadcrumb_api_docs():  # 047 BE8
    tasks_doc = section("data-model-and-api.md", "### 6.2")
    row = tasks_doc[tasks_doc.index("GET  /api/transcripts/5[?full=1]"):tasks_doc.index("GET  /api/transcripts/5/raw")]
    assert '"workspace_id"' in row and '"project_id"' in row
    api_doc = section("data-model-and-api.md", "### 6.4")
    task_row = api_doc[api_doc.index("GET  /api/pages/tasks/{id} "):api_doc.index("GET  /api/pages/tasks/{id}/review")]
    code_row = api_doc[api_doc.index("GET  /api/pages/projects/{id}/code?path="):api_doc.index("← 404", api_doc.index(
        "GET  /api/pages/projects/{id}/code?path="))]
    assert "workspace" in task_row and "workspace" in code_row


# --- Nothing else moves ---------------------------------------------------------------


def test_new_modules_follow_layers():  # AC32
    for rel in ("controllers/pages_api.py", "dto/pages.py"):
        path = PKG / rel
        assert path in checked()
        tree = ast.parse(path.read_text())
        assert wrong_edges(tree, path) + fastapi_outside(tree, path) + sql_outside(tree, path) == []
