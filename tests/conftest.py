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


# --- 109: a fake Plane API v1 on a local http.server --------------------------------------------

PLANE_KEY = "plane_api_SECRET_1234567890"


class FakePlane:
    """Workspace `acme`, project `p-1` (identifier ENG), with `states` and `items`, listed `page` at a time with
    Plane's cursor fields. `fail[<suffix>]` answers a status (int), `"html"` (200, not JSON) or `"slow"` for the
    path after the project's (`""`, `"states/"`, `"work-items/"`, `"work-items/<id>/"`). `old` makes `work-items/`
    a 404, as before the rename. Every request lands in `requests` as {method, path, query, key, body}."""

    def __init__(self):
        self.states = [{"id": "s-b", "group": "backlog", "sequence": 1}, {"id": "s-u", "group": "unstarted",
                       "sequence": 2}, {"id": "s-s", "group": "started", "sequence": 3},
                       {"id": "s-d2", "group": "completed", "sequence": 9}, {"id": "s-d", "group": "completed",
                       "sequence": 5}, {"id": "s-t", "group": "triage", "sequence": 0}]
        self.items, self.page, self.fail, self.old, self.requests = [], 2, {}, False, []
        self.url = None

    def answer(self, h, method):
        from urllib.parse import parse_qs, urlsplit
        parts = urlsplit(h.path)
        length = int(h.headers.get("Content-Length") or 0)
        body = json.loads(h.rfile.read(length)) if length else None
        self.requests.append({"method": method, "path": parts.path, "query": parse_qs(parts.query),
                              "key": h.headers.get("X-API-Key"), "body": body})
        base = "/api/v1/workspaces/acme/projects/p-1/"
        if not parts.path.startswith(base):
            return 404, {"detail": "Not found."}
        rest = parts.path[len(base):]
        fail = self.fail.get(rest)
        if fail == "slow":
            import time
            time.sleep(1)
        if fail == "html":
            return 200, "<html>nope</html>"
        if isinstance(fail, int):
            return fail, {"detail": "no"}
        if rest == "":
            return 200, {"id": "p-1", "identifier": "ENG", "name": "Engineering"}
        listing = {"states/": self.states, "issues/": self.items, "work-items/": None if self.old else self.items}
        if rest in listing and listing[rest] is not None and method == "GET":
            cursor = parse_qs(parts.query).get("cursor", ["2:0:0"])[0]
            start = int(cursor.split(":")[1]) * self.page
            more = start + self.page < len(listing[rest])
            return 200, {"results": listing[rest][start:start + self.page], "next_page_results": more,
                         "next_cursor": f"{self.page}:{start // self.page + 1}:0", "prev_page_results": start > 0,
                         "count": len(listing[rest][start:start + self.page])}
        if method == "PATCH" and (rest.startswith("work-items/") and not self.old or rest.startswith("issues/")):
            return 200, {"id": rest.split("/")[1], "state": (body or {}).get("state")}
        return 404, {"detail": "Not found."}


@pytest.fixture
def plane(monkeypatch):
    """A FakePlane serving on 127.0.0.1; its `url` is what project Settings would hold."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    fake = FakePlane()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, method):
            status, data = fake.answer(self, method)
            raw = data.encode() if isinstance(data, str) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.reply("GET")

        def do_PATCH(self):
            self.reply("PATCH")

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fake.url = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield fake
    srv.shutdown()
    srv.server_close()


def plane_item(n, state="s-b", name=None, description=None):
    return {"id": f"item-{n}", "name": name or f"Item {n}", "sequence_id": n, "state": state,
            "description_stripped": f"About {n}\n" if description is None else description}
