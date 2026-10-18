import io
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from conftest import commit, write

from claude_factories.cli.main import main

PROJECT = {"id": 3, "name": "api", "default_branch": "main", "factory": "none"}
RUN = {"run_id": 41, "session_id": "s", "worktree": ".claude/worktrees/12-x"}


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


def reply(obj, status=200):
    return (status, "application/json", json.dumps(obj).encode())


def requests(server):
    """(method, path, parsed JSON body or None) per request."""
    return [(m, p, json.loads(b) if b else None) for m, p, _, b in server.requests]


class Terminal(io.StringIO):
    """A stdin that is a terminal: reading it fails the test."""

    def isatty(self):
        return True

    def read(self, *args):
        pytest.fail("read stdin from a terminal")


def fctl(monkeypatch, *argv, stdin=""):
    """main with sys.stdin replaced (a str becomes a pipe's contents)."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin) if isinstance(stdin, str) else stdin)
    main(list(argv))


@pytest.fixture
def changed(repo):
    """repo with a.py committed then modified."""
    commit(repo, {"a.py": "x = 1\n"})
    write(repo, {"a.py": "x = 2\n"})
    return repo
