import json
import os
import subprocess
import sys
import threading
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from claude_factories import db
from claude_factories.handlers import schedules
from claude_factories.handlers.pages import LOGIN
from claude_factories.server.app import create_app

ORIGINAL_PATH = os.environ["PATH"]  # 099 AC10: where the real wt is found, before the fakes go first

# 099: worktrunk as the app calls it. Every call appends {argv, config} to FAKE_WT_LOG. `switch --create` runs
# `git worktree add -b` at the config's worktree-path and prints wt-shaped JSON; `step copy-ignored` exits 0;
# `remove <branch>` runs `git worktree remove` on the branch's worktree. FAKE_WT_FAIL=<step> fails that step,
# FAKE_WT_HANG=<step> sleeps past any timeout, FAKE_WT_PATH replaces the path in switch's JSON, and
# FAKE_WT_COPY=<relative path> makes `step copy-ignored` write that file into the worktree (before any FAIL).
FAKE_WT = '''#!PYTHON
import json, os, subprocess, sys, time, tomllib
args = sys.argv[1:]
config_path = os.environ.get("WORKTRUNK_CONFIG_PATH")
config = open(config_path).read() if config_path else None
with open(os.environ["FAKE_WT_LOG"], "a") as f:
    f.write(json.dumps({"argv": args, "config": config}) + "\\n")
cwd, rest = (args[1], args[2:]) if args[:1] == ["-C"] else (os.getcwd(), args)
step = " ".join(rest[:2]) if rest[:1] == ["step"] else rest[0]
if os.environ.get("FAKE_WT_HANG") == step:
    time.sleep(30)
if step == "step copy-ignored" and os.environ.get("FAKE_WT_COPY"):
    copied = os.path.join(cwd, os.environ["FAKE_WT_COPY"])
    os.makedirs(os.path.dirname(copied), exist_ok=True)
    open(copied, "w").write("SECRET=copied\\n")
if os.environ.get("FAKE_WT_FAIL") == step:
    sys.exit(print("wt: " + step + " broke\\nsecond line", file=sys.stderr) or 1)
def git(*a):
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)
    return r.stdout
if step == "switch":
    branch, base = rest[rest.index("--create") + 1], rest[rest.index("--base") + 1]
    path = os.path.join(cwd, tomllib.loads(config)["worktree-path"])
    git("worktree", "add", "-q", "-b", branch, path, base)
    print(json.dumps({"action": "created", "branch": branch, "path": os.environ.get("FAKE_WT_PATH", path)}))
elif step == "remove":
    blocks = [dict(l.partition(" ")[::2] for l in b.splitlines()) for b in git("worktree", "list", "--porcelain").split("\\n\\n")]
    git("worktree", "remove", next(b["worktree"] for b in blocks if b.get("branch") == "refs/heads/" + rest[-1]))
'''


def wt_calls() -> list[dict]:
    """099: what the fake wt recorded, oldest first: [{argv, config}]."""
    path = os.environ["FAKE_WT_LOG"]
    return [json.loads(line) for line in open(path)] if os.path.exists(path) else []


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own FCTL_HOME, HOME, and CLAUDE_CONFIG_DIR (so nothing touches the real ~/.claude
    or the developer's config dir, 030 AC1), a do-nothing fake `claude` and a recording fake `wt` (099) first
    on PATH, and git without the user's config (Q17). 014: an empty claude_login() cache, since tests swap fakes."""
    LOGIN.clear()
    monkeypatch.setenv("FCTL_HOME", str(tmp_path / "fctl-home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    monkeypatch.delenv("FCTL_URL", raising=False)
    monkeypatch.delenv("FCTL_IN_DOCKER", raising=False)  # 028 AC6: tests run inside the image too
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text("#!/bin/sh\nexit 0\n")
    claude.chmod(0o755)
    wt = bin_dir / "wt"
    wt.write_text(FAKE_WT.replace("PYTHON", sys.executable))
    wt.chmod(0o755)
    monkeypatch.setenv("FAKE_WT_LOG", str(tmp_path / "wt-log"))
    for name in ("FAKE_WT_FAIL", "FAKE_WT_HANG", "FAKE_WT_PATH", "FAKE_WT_COPY", "WORKTRUNK_CONFIG_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    # 104 Q10: no scheduler thread, so a minute boundary never fires a real tick; test_scheduler runs the real loop
    monkeypatch.setattr(schedules, "start_loop", lambda *args, **kwargs: None)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "test@example.com")
    yield
    # 096: a run's exit thread (handlers/runs.finish) still collecting once the test ends would open whatever
    # FCTL_HOME is restored next, so it finishes here, while this test's env is still set
    for thread in threading.enumerate():
        if thread.name.endswith("(finish)"):
            thread.join(15)


def git(cwd, *args) -> str:
    """Run git in cwd; its stripped stdout. Raises if git fails."""
    r = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()


def write(repo, files: dict):
    """Write {relative path: str or bytes} under repo, bytes as given (\\r\\n kept)."""
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())


def commit(repo, files: dict | None = None) -> str:
    """Write files, commit everything, and return the new HEAD."""
    write(repo, files or {})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c")
    return git(repo, "rev-parse", "HEAD")


def sql(query, args=()):
    """Run one statement against the test's database; its rows."""
    with closing(db.connect()) as conn, conn:
        return conn.execute(query, args).fetchall()


@pytest.fixture
def repo(tmp_path):
    """A git repo on `main` with one empty commit and no remote."""
    path = tmp_path / "repo"
    git(tmp_path, "init", "-q", "-b", "main", str(path))
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return path


@pytest.fixture
def client():
    # base_url sets Host: 127.0.0.1:4545, which passes the Host check
    with TestClient(create_app(), base_url="http://127.0.0.1:4545") as c:
        yield c
