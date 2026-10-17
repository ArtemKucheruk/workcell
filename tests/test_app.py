import os
import shutil
import subprocess
from pathlib import Path

import pytest

import claude_factories

PKG = Path(claude_factories.__file__).parent
REPO = Path(__file__).parent.parent
HOST_ERROR = {"detail": "Host must be 127.0.0.1 or localhost"}
HEADER_ERROR = {"detail": "X-Requested-By: fctl header required"}


# --- Base layout and static files --------------------------------------------


@pytest.mark.parametrize("name, marker", [("htmx.min.js", b'version:"2.0.'),
                                          ("highlight.min.js", b"Highlight.js v11.")])
def test_static_files_are_vendored(client, name, marker):  # AC15
    r = client.get(f"/static/{name}")
    assert r.status_code == 200
    assert r.content == (PKG / "static" / name).read_bytes()
    assert marker in r.content


def test_index_uses_base_layout(client):  # AC16
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.template.name == "index.html"
    assert (PKG / "templates" / "index.html").read_text().startswith('{% extends "base.html" %}')
    html = r.text
    assert '<meta name="color-scheme" content="light dark">' in html
    assert '<script src="/static/htmx.min.js">' in html
    assert '<script src="/static/highlight.min.js">' in html
    assert ('<link rel="stylesheet" href="/static/github.min.css"'
            ' media="(prefers-color-scheme: light)">') in html
    assert ('<link rel="stylesheet" href="/static/github-dark.min.css"'
            ' media="(prefers-color-scheme: dark)">') in html


def test_body_sends_header_on_htmx_requests(client):  # AC17
    assert """<body hx-headers='{"X-Requested-By": "fctl"}'>""" in client.get("/").text


# --- Local-safety middleware -------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1:4545", "localhost:4545", "localhost", "127.0.0.1:5000"])
def test_local_hosts_allowed(client, host):  # AC18
    assert client.get("/", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "localhost.evil.example", "127.0.0.1.evil.example"])
def test_foreign_hosts_rejected(client, host):  # AC19
    r = client.get("/", headers={"Host": host})
    assert r.status_code == 403
    assert r.json() == HOST_ERROR


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_without_header_rejected(client, method):  # AC20
    r = client.request(method, "/anything")
    assert r.status_code == 403
    assert r.json() == HEADER_ERROR


def test_mutating_with_wrong_header_rejected(client):  # AC21
    r = client.post("/anything", headers={"X-Requested-By": "other"})
    assert r.status_code == 403
    assert r.json() == HEADER_ERROR


def test_mutating_with_header_passes(client):  # AC22
    assert client.post("/anything", headers={"X-Requested-By": "fctl"}).status_code == 404


def test_get_needs_no_header(client):  # AC23
    assert client.get("/").status_code == 200


# --- Repo and test harness ---------------------------------------------------


def test_gitignore():  # AC29
    lines = (REPO / ".gitignore").read_text().splitlines()
    for entry in [".venv/", "__pycache__/", ".pytest_cache/", "dist/"]:
        assert entry in lines


def test_harness_isolates(tmp_path):  # AC30
    assert Path(os.environ["FCTL_HOME"]).is_relative_to(tmp_path)
    claude = shutil.which("claude")
    assert claude == str(tmp_path / "bin" / "claude")
    r = subprocess.run([claude], capture_output=True)
    assert (r.returncode, r.stdout, r.stderr) == (0, b"", b"")
