import json
import os
import urllib.parse

import pytest
from conftest import git

from claude_factories.cli.main import main

from ..conftest import PROJECT, Terminal, fctl, reply, requests

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
    main(["connect", "--workspace", "personal", "--test-cmd", "pytest -q"])
    assert sent_body(connect_server) == {
        "path": os.path.realpath(clone), "workspace": "personal", "name": "clone",
        "remote_url": str(origin), "default_branch": "trunk", "test_cmd": "pytest -q",
    }
    assert capsys.readouterr().out == f"Connected clone (personal) → {CONNECTED['url']}\n"


def test_connect_without_test_cmd(connect_server, repo, monkeypatch):  # AC32
    monkeypatch.chdir(repo)
    main(["connect", "--workspace", "personal"])
    assert sent_body(connect_server)["test_cmd"] is None


def test_connect_no_origin(connect_server, repo, monkeypatch):  # AC33
    git(repo, "switch", "-q", "-c", "dev")
    monkeypatch.chdir(repo)
    main(["connect", "--workspace", "personal"])
    body = sent_body(connect_server)
    assert body["remote_url"] is None
    assert body["default_branch"] == "dev"


def test_connect_from_worktree(connect_server, repo, monkeypatch):  # AC34
    worktree = repo / ".claude" / "worktrees" / "x"
    git(repo, "worktree", "add", "-q", "-b", "factory/x", str(worktree))
    monkeypatch.chdir(worktree)
    main(["connect", "--workspace", "personal"])
    body = sent_body(connect_server)
    assert (body["path"], body["name"]) == (os.path.realpath(repo), "repo")
    assert body["default_branch"] == "main"


def test_connect_from_subdirectory(connect_server, repo, monkeypatch):  # AC35
    sub = repo / "src" / "pkg"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    main(["connect", "--workspace", "personal"])
    assert sent_body(connect_server)["path"] == os.path.realpath(repo)


def test_connect_outside_repo(connect_server, tmp_path, monkeypatch, capsys):  # AC36
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # never find a repo above it
    monkeypatch.chdir(nowhere)
    with pytest.raises(SystemExit) as e:
        main(["connect", "--workspace", "personal"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: not inside a git repository: {os.getcwd()}\n"
    assert connect_server.requests == []


def test_connect_detached_head(connect_server, repo, monkeypatch, capsys):  # AC37
    git(repo, "switch", "-q", "--detach")
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        main(["connect", "--workspace", "personal"])
    assert e.value.code == 1
    assert capsys.readouterr().err == DETACHED
    assert connect_server.requests == []


def test_connect_requires_workspace(connect_server, repo, monkeypatch, capsys):  # AC38
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        main(["connect"])
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl connect")
    assert connect_server.requests == []


# --- fctl context, fctl context set (033) --------------------------------------------


def lookup(repo):
    return ("GET", "/api/projects?" + urllib.parse.urlencode({"path": os.path.realpath(repo)}), None)


def saved(text):
    return reply({"context_md": text, "context_html": "", "bytes": len(text.encode()), "max_bytes": 16384})


def test_context_prints_it(server, repo, monkeypatch, capsys):  # 033 AC18
    server.replies = [reply(PROJECT), saved("# Stack\n- Python 3.12")]
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "context")
    assert requests(server) == [lookup(repo), ("GET", "/api/projects/3/context", None)]
    assert capsys.readouterr().out == "# Stack\n- Python 3.12"


def test_context_empty(server, repo, monkeypatch, capsys):  # 033 AC19
    server.replies = [reply(PROJECT), saved("")]
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "context")
    assert capsys.readouterr() == ("", "")


def test_context_set(server, repo, monkeypatch, capsys):  # 033 AC20
    text = "# Stack\n- Python 3.12 — uv\n\n"
    server.replies = [reply(PROJECT), saved(text)]
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "context", "set", stdin=text)
    assert requests(server) == [lookup(repo), ("PUT", "/api/projects/3/context", {"context_md": text})]
    assert server.requests[1][2]["X-Requested-By"] == "fctl"
    assert capsys.readouterr().out == f"Context saved on api ({len(text.encode())} bytes)\n"


@pytest.mark.parametrize("stdin", ["  \n", Terminal()])
def test_context_set_blank(server, repo, monkeypatch, capsys, stdin):  # 033 AC21
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "context", "set", stdin=stdin)
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: context is empty; pass it on stdin\n"
    assert server.requests == []


def test_context_set_too_large(server, repo, monkeypatch, capsys):  # 033 AC22
    server.replies = [reply(PROJECT), reply({"detail": "context over 16 KB"}, 413)]
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "context", "set", stdin="x" * 16385)
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: 413 context over 16 KB\n"
