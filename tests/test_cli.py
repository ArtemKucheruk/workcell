import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import uvicorn
from conftest import commit, git, write

from claude_factories import cli, db

FCTL = Path(sys.executable).parent / "fctl"


# --- Package and CLI ---------------------------------------------------------


def test_help_names_serve():  # AC1
    r = subprocess.run([FCTL, "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "serve" in r.stdout


def test_no_command_is_usage_error():  # AC2
    r = subprocess.run([FCTL], capture_output=True, text=True)
    assert r.returncode == 2
    assert r.stderr.startswith("usage: fctl")


def test_cli_imports_only_stdlib():  # AC3
    code = (
        "import sys; before = set(sys.modules); import claude_factories.cli; "
        "print('\\n'.join(sorted(set(sys.modules) - before)))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    added = r.stdout.split()
    assert "claude_factories.cli" in added
    bad = [
        m
        for m in added
        if m.split(".")[0] not in sys.stdlib_module_names and m.split(".")[0] != "claude_factories"
    ]
    assert bad == []


# --- fctl serve --------------------------------------------------------------


@pytest.fixture
def uvicorn_calls(monkeypatch, capsys):
    calls = []

    def fake_run(app, **kwargs):
        calls.append({"app": app, "stdout": capsys.readouterr().out, **kwargs})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return calls


def test_serve_defaults_to_localhost_4545(uvicorn_calls):  # AC4
    cli.main(["serve"])
    assert len(uvicorn_calls) == 1
    assert uvicorn_calls[0]["host"] == "127.0.0.1"
    assert uvicorn_calls[0]["port"] == 4545


def test_serve_port_option(uvicorn_calls):  # AC5
    cli.main(["serve", "--port", "5000"])
    assert uvicorn_calls[0]["port"] == 5000
    assert uvicorn_calls[0]["host"] == "127.0.0.1"


def test_serve_has_no_host_option(uvicorn_calls):  # AC6
    with pytest.raises(SystemExit) as e:
        cli.main(["serve", "--host", "0.0.0.0"])
    assert e.value.code == 2
    assert uvicorn_calls == []


def test_serve_prints_banner_before_run(uvicorn_calls):  # AC7
    cli.main(["serve", "--port", "5000"])
    assert uvicorn_calls[0]["stdout"] == (
        f"Claude Factories → http://127.0.0.1:5000 (data: {db.data_dir()})\n"
    )


# --- fctl HTTP client --------------------------------------------------------


@pytest.fixture
def server(monkeypatch):
    """A stdlib HTTP server that records requests. It sends the next of `server.replies`, or
    `server.reply` once those run out."""

    class Handler(BaseHTTPRequestHandler):
        def handle_one(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.server.requests.append((self.command, self.path, self.headers, self.rfile.read(n)))
            replies = self.server.replies
            status, ctype, body = replies.pop(0) if replies else self.server.reply
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_PUT = do_PATCH = handle_one

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    srv.requests = []
    srv.reply = (200, "application/json", b"{}")
    srv.replies = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("FCTL_URL", f"http://127.0.0.1:{srv.server_port}")
    yield srv
    srv.shutdown()
    srv.server_close()


def test_api_sends_header_and_json(server):  # AC24
    cli.api("POST", "/api/x", {"a": 1})
    cli.api("GET", "/api/y")
    assert len(server.requests) == 2
    method, path, headers, body = server.requests[0]
    assert (method, path) == ("POST", "/api/x")
    assert headers["X-Requested-By"] == "fctl"
    assert headers["Content-Type"] == "application/json"
    assert body == b'{"a": 1}'
    method, path, headers, _ = server.requests[1]
    assert (method, path) == ("GET", "/api/y")
    assert headers["X-Requested-By"] == "fctl"


def test_api_default_url(monkeypatch):  # AC25
    seen = []

    class Captured(Exception):
        pass

    def fake_urlopen(req):
        seen.append(req.full_url)
        raise Captured

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(Captured):
        cli.api("GET", "/api/workspaces")
    assert seen == ["http://127.0.0.1:4545/api/workspaces"]


def test_api_decodes_by_content_type(server):  # AC26
    server.reply = (200, "application/json; charset=utf-8", b'{"id": 3}')
    assert cli.api("GET", "/a") == {"id": 3}
    server.reply = (200, "text/plain; charset=utf-8", b'{"id": 3}')
    assert cli.api("GET", "/b") == '{"id": 3}'


def test_api_error_status(server, capsys):  # AC27
    server.reply = (409, "application/json", json.dumps({"detail": "run #41 active"}).encode())
    with pytest.raises(SystemExit) as e:
        cli.api("POST", "/api/tasks/12/run")
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: 409 run #41 active\n"


@pytest.mark.parametrize(
    "ctype, body, expected",
    [
        ("application/json", b'{"detail": [{"loc": "x"}]}', 'fctl: 422 [{"loc": "x"}]'),
        ("text/plain", b"Internal Server Error", "fctl: 422 Internal Server Error"),
    ],
)
def test_api_error_detail_fallbacks(server, capsys, ctype, body, expected):  # Q8
    server.reply = (422, ctype, body)
    with pytest.raises(SystemExit):
        cli.api("GET", "/x")
    assert capsys.readouterr().err == expected + "\n"


def test_api_unreachable(monkeypatch, capsys):  # AC28
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"  # bound then closed: nothing listens there
    monkeypatch.setenv("FCTL_URL", url)
    with pytest.raises(SystemExit) as e:
        cli.api("GET", "/api/workspaces")
    assert e.value.code == 1
    assert capsys.readouterr().err == f'fctl: can\'t reach {url} — is "fctl serve" running?\n'


# --- fctl connect ------------------------------------------------------------

CONNECTED = {"id": 3, "created": True, "url": "http://127.0.0.1:4545/projects/3"}
DETACHED = "fctl: can't tell the default branch: no origin/HEAD and HEAD is detached\n"


@pytest.fixture
def connect_server(server):
    server.reply = (200, "application/json", json.dumps(CONNECTED).encode())
    return server


def sent_body(server):
    assert len(server.requests) == 1
    method, path, _, body = server.requests[0]
    assert (method, path) == ("POST", "/api/projects/connect")
    return json.loads(body)


def test_connect_clone(connect_server, tmp_path, monkeypatch, capsys):  # AC31
    src = tmp_path / "src"
    git(tmp_path, "init", "-q", "-b", "trunk", str(src))
    git(src, "commit", "-q", "--allow-empty", "-m", "init")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(src), str(origin))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    git(clone, "switch", "-q", "-c", "feature")
    monkeypatch.chdir(clone)
    cli.main(["connect", "--workspace", "personal", "--test-cmd", "pytest -q"])
    assert sent_body(connect_server) == {
        "path": os.path.realpath(clone), "workspace": "personal", "name": "clone",
        "remote_url": str(origin), "default_branch": "trunk", "test_cmd": "pytest -q",
    }
    assert capsys.readouterr().out == f"Connected clone (personal) → {CONNECTED['url']}\n"


def test_connect_without_test_cmd(connect_server, repo, monkeypatch):  # AC32
    monkeypatch.chdir(repo)
    cli.main(["connect", "--workspace", "personal"])
    assert sent_body(connect_server)["test_cmd"] is None


def test_connect_no_origin(connect_server, repo, monkeypatch):  # AC33
    git(repo, "switch", "-q", "-c", "dev")
    monkeypatch.chdir(repo)
    cli.main(["connect", "--workspace", "personal"])
    body = sent_body(connect_server)
    assert body["remote_url"] is None
    assert body["default_branch"] == "dev"


def test_connect_from_worktree(connect_server, repo, monkeypatch):  # AC34
    worktree = repo / ".claude" / "worktrees" / "x"
    git(repo, "worktree", "add", "-q", "-b", "factory/x", str(worktree))
    monkeypatch.chdir(worktree)
    cli.main(["connect", "--workspace", "personal"])
    body = sent_body(connect_server)
    assert (body["path"], body["name"]) == (os.path.realpath(repo), "repo")
    assert body["default_branch"] == "main"


def test_connect_from_subdirectory(connect_server, repo, monkeypatch):  # AC35
    sub = repo / "src" / "pkg"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    cli.main(["connect", "--workspace", "personal"])
    assert sent_body(connect_server)["path"] == os.path.realpath(repo)


def test_connect_outside_repo(connect_server, tmp_path, monkeypatch, capsys):  # AC36
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # never find a repo above it
    monkeypatch.chdir(nowhere)
    with pytest.raises(SystemExit) as e:
        cli.main(["connect", "--workspace", "personal"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: not inside a git repository: {os.getcwd()}\n"
    assert connect_server.requests == []


def test_connect_detached_head(connect_server, repo, monkeypatch, capsys):  # AC37
    git(repo, "switch", "-q", "--detach")
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        cli.main(["connect", "--workspace", "personal"])
    assert e.value.code == 1
    assert capsys.readouterr().err == DETACHED
    assert connect_server.requests == []


def test_connect_requires_workspace(connect_server, repo, monkeypatch, capsys):  # AC38
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        cli.main(["connect"])
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl connect")
    assert connect_server.requests == []


# --- fctl task add -----------------------------------------------------------

PROJECT = {"id": 3, "name": "api", "default_branch": "main", "factory": "none"}


@pytest.fixture
def task_server(server):
    server.replies = [
        (200, "application/json", json.dumps(PROJECT).encode()),
        (201, "application/json", json.dumps({"id": 12, "status": "backlog"}).encode()),
    ]
    return server


def looked_up_path(server):
    """The first request (the project lookup GET)'s query, decoded."""
    method, path, _, _ = server.requests[0]
    url = urllib.parse.urlsplit(path)
    assert (method, url.path) == ("GET", "/api/projects")
    return urllib.parse.parse_qs(url.query)


def test_task_add(task_server, repo, monkeypatch, capsys):  # AC35
    monkeypatch.chdir(repo)
    cli.main(["task", "add", "Rate-limit login endpoint"])
    main = os.path.realpath(repo)
    assert [(m, p) for m, p, _, _ in task_server.requests] == [
        ("GET", "/api/projects?" + urllib.parse.urlencode({"path": main})),
        ("POST", "/api/projects/3/tasks"),
    ]
    assert json.loads(task_server.requests[1][3]) == {"title": "Rate-limit login endpoint"}
    assert capsys.readouterr().out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"


def test_task_add_path_with_space(task_server, tmp_path, monkeypatch):  # AC36
    spaced = tmp_path / "my repo"
    git(tmp_path, "init", "-q", "-b", "main", str(spaced))
    monkeypatch.chdir(spaced)
    cli.main(["task", "add", "x"])
    assert looked_up_path(task_server) == {"path": [os.path.realpath(spaced)]}


def test_task_add_from_worktree(task_server, repo, monkeypatch):  # AC37
    worktree = repo / ".claude" / "worktrees" / "x"
    git(repo, "worktree", "add", "-q", "-b", "factory/x", str(worktree))
    monkeypatch.chdir(worktree)
    cli.main(["task", "add", "x"])
    assert looked_up_path(task_server) == {"path": [os.path.realpath(repo)]}


def test_task_add_unconnected(server, repo, monkeypatch, capsys):  # AC38
    main = os.path.realpath(repo)
    server.reply = (404, "application/json", json.dumps({"detail": f"no project at {main}"}).encode())
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        cli.main(["task", "add", "x"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: 404 no project at {main}\n"
    assert [m for m, _, _, _ in server.requests] == ["GET"]


def test_task_add_outside_repo(server, tmp_path, monkeypatch, capsys):  # AC39
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(nowhere)
    with pytest.raises(SystemExit) as e:
        cli.main(["task", "add", "x"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: not inside a git repository: {os.getcwd()}\n"
    assert server.requests == []


@pytest.mark.parametrize(
    "argv, usage", [(["task", "add"], "usage: fctl task add"), (["task"], "usage: fctl task")]
)
def test_task_usage_errors(server, repo, monkeypatch, capsys, argv, usage):  # AC40
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith(usage)
    assert server.requests == []


# --- fctl submit -------------------------------------------------------------

SUBMITTED = {"task_id": 17, "round": 1, "files_changed": 3, "additions": 38, "deletions": 2,
             "url": "http://127.0.0.1:4545/tasks/17/review"}
ROUND = {"round": 2, "files_changed": 4, "additions": 126, "deletions": 9,
         "url": "http://127.0.0.1:4545/tasks/12/review?round=2"}
NO_COMMIT = "fctl: HEAD has no commit yet; commit once before submitting\n"


def reply(obj, status=200):
    return (status, "application/json", json.dumps(obj).encode())


@pytest.fixture
def new_server(server):
    server.replies = [reply(PROJECT), reply(SUBMITTED, 201)]
    return server


@pytest.fixture
def round_server(server):
    server.reply = reply(ROUND, 201)
    return server


class Terminal(io.StringIO):
    """A stdin that is a terminal: reading it fails the test."""

    def isatty(self):
        return True

    def read(self, *args):
        pytest.fail("read stdin from a terminal")


def fctl(monkeypatch, *argv, stdin=""):
    """cli.main with sys.stdin replaced (a str becomes a pipe's contents)."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin) if isinstance(stdin, str) else stdin)
    cli.main(list(argv))


def sent_round(server) -> dict:
    """The one request a `fctl submit <id>` sends: POST /api/tasks/12/rounds; its body."""
    [(method, path, _, body)] = server.requests
    assert (method, path) == ("POST", "/api/tasks/12/rounds")
    return json.loads(body)


@pytest.fixture
def changed(repo):
    """repo with a.py committed then modified."""
    commit(repo, {"a.py": "x = 1\n"})
    write(repo, {"a.py": "x = 2\n"})
    return repo


def test_submit_new_sends_capture(new_server, repo, monkeypatch):  # AC27
    head = commit(repo, {".gitignore": "debug.log\n", "a.py": "x = 1\n"})
    write(repo, {"a.py": "x = 2\n", "c.py": "y = 1\n", "debug.log": "noise\n"})
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "submit", "--new", "--title", "Fix open redirect after login", stdin="Fixed it.\n")
    (get, path, _, _), (post, post_path, _, raw) = new_server.requests
    assert (get, path) == ("GET", "/api/projects?" + urllib.parse.urlencode({"path": os.path.realpath(repo)}))
    assert (post, post_path) == ("POST", "/api/projects/3/tasks")
    body = json.loads(raw)
    patch = body["submit"]["patch"]
    assert body == {"title": "Fix open redirect after login", "description_md": "Fixed it.\n",
                    "submit": {"base_sha": head, "patch": patch}}
    assert "diff --git a/a.py b/a.py\n" in patch
    assert "diff --git a/c.py b/c.py\nnew file mode " in patch
    assert "debug.log" not in patch


def test_submit_leaves_real_index(round_server, repo, monkeypatch):  # AC28
    commit(repo, {"a.py": "x = 1\n"})
    write(repo, {"a.py": "x = 2\n", "c.py": "y = 1\n"})
    git(repo, "add", "a.py")
    before = git(repo, "status", "--porcelain")
    assert before == "M  a.py\n?? c.py"
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "submit", "12")
    assert git(repo, "status", "--porcelain") == before
    patch = sent_round(round_server)["patch"]
    assert "diff --git a/a.py b/a.py\n" in patch and "diff --git a/c.py b/c.py\n" in patch


@pytest.mark.parametrize("files, shown", [(3, "3 files"), (1, "1 file")])
def test_submit_new_prints_review(new_server, changed, monkeypatch, capsys, files, shown):  # AC29
    new_server.replies[1] = reply(SUBMITTED | {"files_changed": files}, 201)
    monkeypatch.chdir(changed)
    fctl(monkeypatch, "submit", "--new", "--title", "T")
    assert capsys.readouterr().out == f"Review #17: {shown}, +38 −2 → http://127.0.0.1:4545/tasks/17/review\n"


def test_submit_round_from_worktree(round_server, changed, monkeypatch):  # AC30
    git(changed, "commit", "-qam", "a.py at x = 2")
    worktree = changed / ".claude" / "worktrees" / "x"
    git(changed, "worktree", "add", "-q", "-b", "factory/x", str(worktree))
    head = commit(worktree, {"b.py": "only in the worktree\n"})
    assert head != git(changed, "rev-parse", "HEAD")
    write(worktree, {"a.py": "x = 3\n"})
    monkeypatch.chdir(worktree)
    fctl(monkeypatch, "submit", "12", stdin="notes\n")
    body = sent_round(round_server)
    assert body == {"base_sha": head, "build_md": "notes\n", "patch": body["patch"]}
    assert "diff --git a/a.py b/a.py\n" in body["patch"] and "+x = 3\n" in body["patch"]


def test_submit_round_prints_round(round_server, changed, monkeypatch, capsys):  # AC31
    monkeypatch.chdir(changed)
    fctl(monkeypatch, "submit", "12")
    assert capsys.readouterr().out == (
        "Round 2 of #12: 4 files, +126 −9 → http://127.0.0.1:4545/tasks/12/review?round=2\n"
    )


def test_submit_from_subdirectory(round_server, repo, monkeypatch):  # AC32
    commit(repo, {"a.py": "x = 1\n", "src/pkg/m.py": "m = 1\n"})
    git(repo, "config", "diff.relative", "true")  # the capture must override it
    write(repo, {"a.py": "x = 2\n"})
    monkeypatch.chdir(repo / "src" / "pkg")
    fctl(monkeypatch, "submit", "12")
    assert "diff --git a/a.py b/a.py\n" in sent_round(round_server)["patch"]


def test_submit_keeps_crlf(round_server, repo, monkeypatch):  # AC33
    commit(repo, {"w.txt": "keep\r\nold\r\n"})
    write(repo, {"w.txt": "keep\r\nnew\r\n"})
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "submit", "12")
    patch = sent_round(round_server)["patch"]
    assert "-old\r\n" in patch and "+new\r\n" in patch


def test_submit_ignores_diff_config(round_server, repo, monkeypatch):  # AC34
    for key in ("diff.noprefix", "diff.mnemonicPrefix"):
        git(repo, "config", key, "true")
    git(repo, "config", "color.diff", "always")
    write(repo, {"naïve.txt": "x\n"})
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "submit", "12")
    patch = sent_round(round_server)["patch"]
    assert "diff --git a/naïve.txt b/naïve.txt\n" in patch and "+++ b/naïve.txt\n" in patch
    assert "\x1b" not in patch


def test_submit_skips_terminal_stdin(new_server, changed, monkeypatch):  # AC35
    monkeypatch.chdir(changed)
    fctl(monkeypatch, "submit", "--new", "--title", "T", stdin=Terminal())
    new_server.reply = reply(ROUND, 201)
    fctl(monkeypatch, "submit", "12", stdin=Terminal())
    assert json.loads(new_server.requests[1][3])["description_md"] == ""
    assert json.loads(new_server.requests[2][3])["build_md"] == ""


@pytest.mark.parametrize("argv", [
    [], ["12", "--new", "--title", "T"], ["--new"], ["12", "--title", "T"], ["abc"],
])
def test_submit_usage_errors(server, changed, monkeypatch, capsys, argv):  # AC36
    monkeypatch.chdir(changed)
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "submit", *argv)
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl submit")
    assert server.requests == []


@pytest.mark.parametrize("argv", [["--new", "--title", "T"], ["12"]])
def test_submit_outside_repo(server, tmp_path, monkeypatch, capsys, argv):  # AC37
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(nowhere)
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "submit", *argv)
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: not inside a git repository: {os.getcwd()}\n"
    assert server.requests == []


def test_submit_without_commit(server, tmp_path, monkeypatch, capsys):  # AC38
    fresh = tmp_path / "fresh"
    git(tmp_path, "init", "-q", "-b", "main", str(fresh))
    write(fresh, {"a.py": "x = 1\n"})
    monkeypatch.chdir(fresh)
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "submit", "12")
    assert e.value.code == 1
    assert capsys.readouterr().err == NO_COMMIT
    assert server.requests == []


def test_submit_new_unconnected(server, changed, monkeypatch, capsys):  # AC39
    main = os.path.realpath(changed)
    server.reply = (404, "application/json", json.dumps({"detail": f"no project at {main}"}).encode())
    monkeypatch.chdir(changed)
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "submit", "--new", "--title", "T")
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: 404 no project at {main}\n"
    assert [m for m, _, _, _ in server.requests] == ["GET"]


# --- fctl diff ---------------------------------------------------------------

DIFF = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\r\n+naïve"  # no final newline


def test_diff_prints_latest(server, capsys):  # AC40
    server.reply = (200, "text/x-diff; charset=utf-8", DIFF.encode())
    cli.main(["diff", "12"])
    assert [(m, p) for m, p, _, _ in server.requests] == [("GET", "/api/tasks/12/rounds/latest/diff")]
    assert capsys.readouterr().out == DIFF


def test_diff_round_option(server):  # AC41
    server.reply = (200, "text/x-diff; charset=utf-8", DIFF.encode())
    cli.main(["diff", "12", "--round", "2"])
    assert [(m, p) for m, p, _, _ in server.requests] == [("GET", "/api/tasks/12/rounds/2/diff")]


# --- Agent commands (006): show, spec, stage, verdict, comment, decide, round ---------


def requests(server):
    """(method, path, parsed JSON body or None) per request."""
    return [(m, p, json.loads(b) if b else None) for m, p, _, b in server.requests]


def test_show(server, capsys):  # 006 AC29
    server.reply = (200, "text/markdown; charset=utf-8", "# #12 x\n…".encode())
    cli.main(["show", "12"])
    assert capsys.readouterr().out == "# #12 x\n…"
    cli.main(["show", "12", "--round", "2"])
    cli.main(["show", "12", "--feedback"])
    assert [(m, p) for m, p, _ in requests(server)] == [
        ("GET", "/api/tasks/12/context"),
        ("GET", "/api/tasks/12/context?round=2"),
        ("GET", "/api/tasks/12/context?feedback=1"),
    ]


def test_spec(server, monkeypatch, capsys):  # 006 AC30
    server.reply = reply({"id": 12, "status": "in_progress", "stage": "spec"})
    fctl(monkeypatch, "spec", "12", stdin="## Acceptance criteria\n- x\n")
    assert requests(server) == [("PATCH", "/api/tasks/12", {"spec_md": "## Acceptance criteria\n- x\n"})]
    assert capsys.readouterr().out == "Spec saved on #12\n"


@pytest.mark.parametrize("stdin", ["  \n", Terminal()])
def test_spec_empty(server, monkeypatch, capsys, stdin):  # 006 AC31
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "spec", "12", stdin=stdin)
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: spec is empty; pass it on stdin\n"
    assert server.requests == []


def test_stage(server, capsys):  # 006 AC32
    server.reply = reply({"id": 12, "status": "in_progress", "stage": "agent_review"})
    cli.main(["stage", "12", "agent_review"])
    assert requests(server) == [("PATCH", "/api/tasks/12", {"stage": "agent_review"})]
    assert capsys.readouterr().out == "#12: in_progress · agent_review\n"


def test_verdict(server, monkeypatch, capsys):  # 006 AC33
    server.reply = reply({"round": 1, "reviewer": "security", "verdict": "CHANGES", "complete": "3/4"})
    fctl(monkeypatch, "verdict", "12", "security", "CHANGES", stdin="1. app/limits.py:31 …\n")
    assert requests(server) == [("PUT", "/api/tasks/12/rounds/latest/verdicts/security",
                                 {"verdict": "CHANGES", "body_md": "1. app/limits.py:31 …\n"})]
    assert capsys.readouterr().out == "Round 1 of #12: security=CHANGES (3/4)\n"


def test_comment(server, monkeypatch, capsys):  # 006 AC34
    server.reply = reply({"id": 88}, 201)
    fctl(monkeypatch, "comment", "12", "security", "--path", "app/limits.py", "--line", "31",
         stdin="Use request.client.host.\n")
    assert requests(server) == [("POST", "/api/tasks/12/comments", {
        "round": "latest", "author": "security", "path": "app/limits.py", "line": 31, "side": "new",
        "body_md": "Use request.client.host.\n",
    })]
    assert capsys.readouterr().out == "Comment #88 on #12 app/limits.py:31\n"


def test_decide(server, monkeypatch, capsys):  # 006 AC35
    server.reply = reply({"id": 7}, 201)
    fctl(monkeypatch, "decide", "12", "APPROVE", stdin="All 4 PASS.\n")
    assert requests(server) == [("POST", "/api/tasks/12/decision", {"decision": "APPROVE", "body_md": "All 4 PASS.\n"})]
    assert capsys.readouterr().out == "Decision #7 on #12: APPROVE\n"


def test_agent_commands_skip_terminal_stdin(server, monkeypatch):  # 006 AC36
    server.replies = [reply({"round": 1, "reviewer": "ux", "verdict": "PASS", "complete": "1/4"}),
                      reply({"id": 88}, 201), reply({"id": 7}, 201)]
    fctl(monkeypatch, "verdict", "12", "ux", "PASS", stdin=Terminal())
    fctl(monkeypatch, "comment", "12", "ux", "--path", "a.py", "--line", "1", stdin=Terminal())
    fctl(monkeypatch, "decide", "12", "ESCALATE", stdin=Terminal())
    assert [body["body_md"] for _, _, body in requests(server)] == ["", "", ""]


def task_reply(rounds):
    return reply({"id": 12, "title": "x", "status": "in_progress", "stage": "agent_review", "branch": None,
                  "rounds": rounds, "decisions": [], "run": None})


def test_round(server, capsys):  # 006 AC37
    server.reply = task_reply([
        {"n": 1, "trigger": "initial", "files": 4, "additions": 118, "deletions": 9,
         "verdicts": {"security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS"}},
        {"n": 2, "trigger": "agent", "files": 4, "additions": 126, "deletions": 9,
         "verdicts": {"security": "PASS", "ux": "PASS", "ui": "pending", "code": "PASS"}},
    ])
    cli.main(["round", "12"])
    assert requests(server) == [("GET", "/api/tasks/12", None)]
    assert capsys.readouterr().out == "round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)\n"


def test_round_without_rounds(server, capsys):  # 006 AC38
    server.reply = task_reply([])
    with pytest.raises(SystemExit) as e:
        cli.main(["round", "12"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: #12 has no rounds\n"


@pytest.mark.parametrize("argv", [
    ["show", "12", "--round", "2", "--feedback"], ["show", "abc"],
    ["stage", "12", "deploy"],
    ["verdict", "12", "approver", "PASS"], ["verdict", "12", "security", "pass"], ["verdict", "12", "security"],
    ["comment", "12", "me", "--path", "a.py", "--line", "1"], ["comment", "12", "security", "--path", "a.py"],
    ["comment", "12", "security", "--path", "a.py", "--line", "x"], ["comment", "12", "--path", "a.py", "--line", "1"],
    ["decide", "12", "CHANGES_REQUESTED"], ["decide", "12", "approve"],
    ["round"],
])
def test_agent_usage_errors(server, monkeypatch, capsys, argv):  # 006 AC39
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, *argv, stdin=Terminal())
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith(f"usage: fctl {argv[0]}")
    assert server.requests == []


# --- My review actions (009): approve, rework ----------------------------------------


def test_approve(server, capsys):  # 009 AC24
    server.reply = reply({"status": "done", "commit_hint": "cd /x\ngit add -A && git commit -m 'T'"})
    cli.main(["approve", "12"])
    assert requests(server) == [("POST", "/api/tasks/12/approve", {"body_md": ""})]
    assert capsys.readouterr().out == "#12: done\ncd /x\ngit add -A && git commit -m 'T'\n"


def test_rework(server, capsys):  # 009 AC25
    server.reply = reply({"status": "in_progress", "stage": "rework", "run_id": None}, 202)
    cli.main(["rework", "12", "Make the limit configurable"])
    assert requests(server) == [("POST", "/api/tasks/12/request-changes", {"body_md": "Make the limit configurable"})]
    assert capsys.readouterr().out == "#12: in_progress · rework\n"


def test_rework_needs_note(server, capsys):  # 009 AC26
    with pytest.raises(SystemExit) as e:
        cli.main(["rework", "12"])
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl rework")
    assert server.requests == []


def test_approve_refused(server, capsys):  # 009 AC26
    server.reply = reply({"detail": "#12 is not in review"}, 409)
    with pytest.raises(SystemExit) as e:
        cli.main(["approve", "12"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: 409 #12 is not in review\n"


# --- fctl setup (015) ----------------------------------------------------------------


def skill(name) -> Path:
    return Path(os.environ["HOME"]) / ".claude" / "skills" / name / "SKILL.md"


def frontmatter(text) -> tuple[str, str]:
    """A SKILL.md's (frontmatter, body); it must start with a `---` block."""
    assert text.startswith("---\n")
    front, body = text[4:].split("\n---\n", 1)
    return front, body


def test_setup_writes_skills(server):  # 015 AC1
    assert not (Path(os.environ["HOME"]) / ".claude").exists()
    cli.main(["setup"])
    assert skill("factory-connect").is_file()
    assert skill("factory-submit").is_file()


def test_setup_output(server, capsys):  # 015 AC2
    cli.main(["setup"])
    assert capsys.readouterr().out == f"Wrote {skill('factory-connect')}\nWrote {skill('factory-submit')}\n"


def test_setup_is_offline(server, monkeypatch):  # 015 AC3
    cli.main(["setup"])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("FCTL_URL", f"http://127.0.0.1:{port}")  # bound then closed: nothing listens
    cli.main(["setup"])  # returns: exit 0
    assert server.requests == []


def test_setup_connect_skill(server):  # 015 AC4
    cli.main(["setup"])
    front, body = frontmatter(skill("factory-connect").read_text())
    assert "name: factory-connect" in front.splitlines()
    assert re.search(r"^description: \S", front, re.M)
    for needle in ("$ARGUMENTS", "fctl connect --workspace", "--test-cmd"):
        assert needle in body


def test_setup_submit_skill(server):  # 015 AC5
    cli.main(["setup"])
    front, body = frontmatter(skill("factory-submit").read_text())
    assert "name: factory-submit" in front.splitlines()
    assert re.search(r"^description: \S", front, re.M)
    assert "fctl submit --new --title" in body
    assert "fctl submit <id> <<'EOF'" in body
    assert re.search(r"fctl submit --new --title .*<<'EOF'\n", body)


def test_setup_overwrites_only_skill_md(server):  # 015 AC6
    cli.main(["setup"])
    first = skill("factory-connect").read_bytes()
    skill("factory-connect").write_text("my edit\n")
    notes = skill("factory-connect").with_name("notes.md")
    notes.write_text("mine\n")
    cli.main(["setup"])
    assert skill("factory-connect").read_bytes() == first
    assert notes.read_text() == "mine\n"


def test_setup_cant_write(server, capsys):  # 015 AC7
    skills = Path(os.environ["HOME"]) / ".claude" / "skills"
    skills.parent.mkdir()
    skills.write_text("not a dir\n")
    with pytest.raises(SystemExit) as e:
        cli.main(["setup"])
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith(f"fctl: can't write {skill('factory-connect')}: ")
    assert "Traceback" not in err


# --- fctl run, task add --run (015) --------------------------------------------------

RUN = {"run_id": 41, "session_id": "s", "worktree": ".claude/worktrees/12-x"}
ADDED = {"id": 12, "status": "backlog"}


def test_run_task(server, capsys):  # 015 AC8
    server.reply = reply(RUN, 202)
    cli.main(["run", "12"])
    assert requests(server) == [("POST", "/api/tasks/12/run", None)]
    assert capsys.readouterr().out == f"Run #41 on #12 → {os.environ['FCTL_URL']}/tasks/12\n"


def test_run_task_outside_repo(server, tmp_path, monkeypatch):  # 015 AC9
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(nowhere)
    server.reply = reply(RUN, 202)
    cli.main(["run", "12"])
    assert requests(server) == [("POST", "/api/tasks/12/run", None)]


def test_run_next(server, repo, monkeypatch, capsys):  # 015 AC10
    server.replies = [reply(PROJECT), reply({"task_id": 14, "run_id": 42}, 202)]
    monkeypatch.chdir(repo)
    cli.main(["run", "next"])
    assert requests(server) == [
        ("GET", "/api/projects?" + urllib.parse.urlencode({"path": os.path.realpath(repo)}), None),
        ("POST", "/api/projects/3/run-next", None),
    ]
    assert capsys.readouterr().out == f"Run #42 on #14 → {os.environ['FCTL_URL']}/tasks/14\n"


def test_run_next_outside_repo(server, tmp_path, monkeypatch, capsys):  # 015 AC11
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(nowhere)
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "next"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: not inside a git repository: {os.getcwd()}\n"
    assert server.requests == []


def test_run_next_empty_backlog(server, repo, monkeypatch, capsys):  # 015 AC12
    server.replies = [reply(PROJECT), reply({"detail": "backlog is empty"}, 404)]
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "next"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: 404 backlog is empty\n"


def test_run_refused(server, capsys):  # 015 AC13
    server.reply = reply({"detail": "run #41 active"}, 409)
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "12"])
    assert e.value.code == 1
    out, err = capsys.readouterr()
    assert (out, err) == ("", "fctl: 409 run #41 active\n")


@pytest.mark.parametrize("argv", [["run"], ["run", "abc"]])
def test_run_usage_errors(server, capsys, argv):  # 015 AC14
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl run")
    assert server.requests == []


def test_task_add_run(server, repo, monkeypatch, capsys):  # 015 AC15
    server.replies = [reply(PROJECT), reply(ADDED, 201), reply(RUN, 202)]
    monkeypatch.chdir(repo)
    cli.main(["task", "add", "T", "--run"])
    assert requests(server) == [
        ("GET", "/api/projects?" + urllib.parse.urlencode({"path": os.path.realpath(repo)}), None),
        ("POST", "/api/projects/3/tasks", {"title": "T"}),
        ("POST", "/api/tasks/12/run", None),
    ]
    url = os.environ["FCTL_URL"]
    assert capsys.readouterr().out == f"Added #12 to api → {url}/projects/3\nRun #41 on #12 → {url}/tasks/12\n"


def test_task_add_run_refused(server, repo, monkeypatch, capsys):  # 015 AC16
    server.replies = [reply(PROJECT), reply(ADDED, 201), reply({"detail": "not on subscription auth"}, 409)]
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        cli.main(["task", "add", "T", "--run"])
    assert e.value.code == 1
    out, err = capsys.readouterr()
    assert out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"
    assert err == "fctl: 409 not on subscription auth\n"


def test_task_add_without_run(server, repo, monkeypatch, capsys):  # 015 AC17
    server.replies = [reply(PROJECT), reply(ADDED, 201), reply(RUN, 202)]
    monkeypatch.chdir(repo)
    cli.main(["task", "add", "T"])
    assert [(m, p) for m, p, _ in requests(server)][1:] == [("POST", "/api/projects/3/tasks")]
    assert capsys.readouterr().out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"
