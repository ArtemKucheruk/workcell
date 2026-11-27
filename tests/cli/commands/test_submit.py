import json
import os
import urllib.parse

import pytest
from conftest import commit, git, write

from workcell.cli.main import main

from ..conftest import PROJECT, Terminal, fctl, reply

SUBMITTED = {"task_id": 17, "round": 1, "files_changed": 3, "additions": 38, "deletions": 2,
             "url": "http://127.0.0.1:4545/tasks/17/review"}
ROUND = {"round": 2, "files_changed": 4, "additions": 126, "deletions": 9,
         "url": "http://127.0.0.1:4545/tasks/12/review?round=2"}
NO_COMMIT = "fctl: HEAD has no commit yet; commit once before submitting\n"


@pytest.fixture
def new_server(server):
    server.replies = [reply(PROJECT), reply(SUBMITTED, 201)]
    return server


@pytest.fixture
def round_server(server):
    server.reply = reply(ROUND, 201)
    return server


def sent_round(server) -> dict:
    """The one request a `fctl submit <id>` sends: POST /api/tasks/12/rounds; its body."""
    [(method, path, _, body)] = server.requests
    assert (method, path) == ("POST", "/api/tasks/12/rounds")
    return json.loads(body)


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


def test_submit_leaves_out_ignored_files(round_server, repo, monkeypatch):  # 099 AC14
    commit(repo, {".gitignore": ".env\nnode_modules/\n", "a.py": "x = 1\n"})
    write(repo, {"a.py": "x = 2\n", ".env": "API_TOKEN=not-a-real-secret\n", "node_modules/p/i.js": "1;\n"})
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "submit", "12")
    patch = sent_round(round_server)["patch"]
    assert "diff --git a/a.py b/a.py\n" in patch
    assert ".env" not in patch and "not-a-real-secret" not in patch and "node_modules" not in patch


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
    main(["diff", "12"])
    assert [(m, p) for m, p, _, _ in server.requests] == [("GET", "/api/tasks/12/rounds/latest/diff")]
    assert capsys.readouterr().out == DIFF


def test_diff_round_option(server):  # AC41
    server.reply = (200, "text/x-diff; charset=utf-8", DIFF.encode())
    main(["diff", "12", "--round", "2"])
    assert [(m, p) for m, p, _, _ in server.requests] == [("GET", "/api/tasks/12/rounds/2/diff")]
