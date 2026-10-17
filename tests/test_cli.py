import json
import socket
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import uvicorn

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
    """A stdlib HTTP server that records requests and sends `server.reply`."""

    class Handler(BaseHTTPRequestHandler):
        def handle_one(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.server.requests.append((self.command, self.path, self.headers, self.rfile.read(n)))
            status, ctype, body = self.server.reply
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = handle_one

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    srv.requests = []
    srv.reply = (200, "application/json", b"{}")
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
