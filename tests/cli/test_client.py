import json
import socket
import urllib.request

import pytest

from claude_factories.cli.client import api


def test_api_sends_header_and_json(server):  # AC24
    api("POST", "/api/x", {"a": 1})
    api("GET", "/api/y")
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
        api("GET", "/api/workspaces")
    assert seen == ["http://127.0.0.1:4545/api/workspaces"]


def test_api_decodes_by_content_type(server):  # AC26
    server.reply = (200, "application/json; charset=utf-8", b'{"id": 3}')
    assert api("GET", "/a") == {"id": 3}
    server.reply = (200, "text/plain; charset=utf-8", b'{"id": 3}')
    assert api("GET", "/b") == '{"id": 3}'


def test_api_error_status(server, capsys):  # AC27
    server.reply = (409, "application/json", json.dumps({"detail": "run #41 active"}).encode())
    with pytest.raises(SystemExit) as e:
        api("POST", "/api/tasks/12/run")
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
        api("GET", "/x")
    assert capsys.readouterr().err == expected + "\n"


def test_api_unreachable(monkeypatch, capsys):  # AC28
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"  # bound then closed: nothing listens there
    monkeypatch.setenv("FCTL_URL", url)
    with pytest.raises(SystemExit) as e:
        api("GET", "/api/workspaces")
    assert e.value.code == 1
    assert capsys.readouterr().err == f'fctl: can\'t reach {url} — is "fctl serve" running?\n'
