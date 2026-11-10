import json
import os
import sys
import urllib.parse

import pytest
from conftest import git

from claude_factories.cli.main import main

from ..conftest import PROJECT, RUN, Terminal, fctl, reply, requests

ADDED = {"id": 12, "status": "backlog"}


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
    main(["task", "add", "Rate-limit login endpoint"])
    main_path = os.path.realpath(repo)
    assert [(m, p) for m, p, _, _ in task_server.requests] == [
        ("GET", "/api/projects?" + urllib.parse.urlencode({"path": main_path})),
        ("POST", "/api/projects/3/tasks"),
    ]
    assert json.loads(task_server.requests[1][3]) == {"title": "Rate-limit login endpoint"}
    assert capsys.readouterr().out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"


def test_task_add_path_with_space(task_server, tmp_path, monkeypatch):  # AC36
    spaced = tmp_path / "my repo"
    git(tmp_path, "init", "-q", "-b", "main", str(spaced))
    monkeypatch.chdir(spaced)
    main(["task", "add", "x"])
    assert looked_up_path(task_server) == {"path": [os.path.realpath(spaced)]}


def test_task_add_from_worktree(task_server, repo, monkeypatch):  # AC37
    worktree = repo / ".claude" / "worktrees" / "x"
    git(repo, "worktree", "add", "-q", "-b", "factory/x", str(worktree))
    monkeypatch.chdir(worktree)
    main(["task", "add", "x"])
    assert looked_up_path(task_server) == {"path": [os.path.realpath(repo)]}


def test_task_add_unconnected(server, repo, monkeypatch, capsys):  # AC38
    main_path = os.path.realpath(repo)
    server.reply = (404, "application/json", json.dumps({"detail": f"no project at {main_path}"}).encode())
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        main(["task", "add", "x"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: 404 no project at {main_path}\n"
    assert [m for m, _, _, _ in server.requests] == ["GET"]


def test_task_add_outside_repo(server, tmp_path, monkeypatch, capsys):  # AC39
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(nowhere)
    with pytest.raises(SystemExit) as e:
        main(["task", "add", "x"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: not inside a git repository: {os.getcwd()}\n"
    assert server.requests == []


@pytest.mark.parametrize(
    "argv, usage", [(["task", "add"], "usage: fctl task add"), (["task"], "usage: fctl task")]
)
def test_task_usage_errors(server, repo, monkeypatch, capsys, argv, usage):  # AC40
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith(usage)
    assert server.requests == []


def test_task_add_run(server, repo, monkeypatch, capsys):  # 015 AC15
    server.replies = [reply(PROJECT), reply(ADDED, 201), reply(RUN, 202)]
    monkeypatch.chdir(repo)
    main(["task", "add", "T", "--run"])
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
        main(["task", "add", "T", "--run"])
    assert e.value.code == 1
    out, err = capsys.readouterr()
    assert out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"
    assert err.startswith("fctl: 409 not on subscription auth\nSign in to a Claude account")  # 056: next step


def test_task_add_without_run(server, repo, monkeypatch, capsys):  # 015 AC17
    server.replies = [reply(PROJECT), reply(ADDED, 201), reply(RUN, 202)]
    monkeypatch.chdir(repo)
    main(["task", "add", "T"])
    assert [(m, p) for m, p, _ in requests(server)][1:] == [("POST", "/api/projects/3/tasks")]
    assert capsys.readouterr().out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"


# --- 060: fctl task add --description ----------------------------------------------------------

def test_task_add_description(task_server, repo, monkeypatch, capsys):  # 060 BE1
    monkeypatch.chdir(repo)
    main(["task", "add", "T", "--description", "Max 5 failed logins/min per IP."])
    assert requests(task_server) == [
        ("GET", "/api/projects?" + urllib.parse.urlencode({"path": os.path.realpath(repo)}), None),
        ("POST", "/api/projects/3/tasks", {"title": "T", "description_md": "Max 5 failed logins/min per IP."}),
    ]
    assert capsys.readouterr().out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"


def test_task_add_description_stdin(task_server, repo, monkeypatch):  # 060 BE2
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "task", "add", "T", "--description", "-", stdin="## Why\nMax 5 failed logins.\n")
    assert requests(task_server)[1][2] == {"title": "T", "description_md": "## Why\nMax 5 failed logins.\n"}


@pytest.mark.parametrize("value, stdin", [("", ""), ("  ", ""), ("-", "  \n"), ("-", Terminal())])
def test_task_add_blank_description(server, repo, monkeypatch, capsys, value, stdin):  # 060 BE3, Q1
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "task", "add", "T", "--description", value, stdin=stdin)
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: description is empty; pass it as text, or on stdin with --description -\n"
    assert server.requests == []


def test_task_add_ignores_stdin(task_server, repo, monkeypatch):  # 060 BE4
    monkeypatch.chdir(repo)
    fctl(monkeypatch, "task", "add", "T", stdin="ignored\n")
    assert requests(task_server)[1][2] == {"title": "T"}
    assert sys.stdin.read() == "ignored\n"  # never read


def test_task_add_description_run(server, repo, monkeypatch, capsys):  # 060 BE5
    server.replies = [reply(PROJECT), reply(ADDED, 201), reply(RUN, 202)]
    monkeypatch.chdir(repo)
    main(["task", "add", "T", "--description", "D", "--run"])
    assert requests(server) == [
        ("GET", "/api/projects?" + urllib.parse.urlencode({"path": os.path.realpath(repo)}), None),
        ("POST", "/api/projects/3/tasks", {"title": "T", "description_md": "D"}),
        ("POST", "/api/tasks/12/run", None),
    ]
    url = os.environ["FCTL_URL"]
    assert capsys.readouterr().out == f"Added #12 to api → {url}/projects/3\nRun #41 on #12 → {url}/tasks/12\n"


def test_task_add_help(capsys):  # 060 BE6
    with pytest.raises(SystemExit) as e:
        main(["task", "add", "--help"])
    assert e.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--description TEXT" in out
    assert '"-" reads it from stdin' in out


# --- 032: fctl export, fctl import -------------------------------------------------------------

ZIP = b"PK\x05\x06" + b"\x00" * 18  # an empty zip's bytes
IMPORTED = {"task_id": 12, "title": "Rate-limit login", "import_key": "task:7@2026-10-17T10:03:00Z", "created": True,
            "status": "backlog", "rounds": 2, "transcripts": 0}


def test_export(server, tmp_path, monkeypatch, capsys):  # AC41
    server.reply = (200, "application/zip", ZIP)
    monkeypatch.chdir(tmp_path)
    main(["export", "12"])
    assert [(m, p) for m, p, _, _ in server.requests] == [("GET", "/api/tasks/12/export")]
    assert (tmp_path / "task-12.zip").read_bytes() == ZIP
    assert capsys.readouterr().out == "Exported #12 → task-12.zip\n"


def test_export_output_and_transcripts(server, tmp_path, monkeypatch, capsys):  # AC42
    server.reply = (200, "application/zip", ZIP)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "out.zip").write_bytes(b"old and longer than the new bytes" * 10)
    main(["export", "12", "-o", "out.zip", "--transcripts"])
    assert [(m, p) for m, p, _, _ in server.requests] == [("GET", "/api/tasks/12/export?transcripts=1")]
    assert (tmp_path / "out.zip").read_bytes() == ZIP
    assert capsys.readouterr().out == "Exported #12 → out.zip\n"
    main(["export", "12", "--output", "long.zip"])
    assert (tmp_path / "long.zip").read_bytes() == ZIP


def test_import(server, repo, monkeypatch, capsys):  # AC43
    (repo / "b.zip").write_bytes(ZIP)
    monkeypatch.chdir(repo)
    lines = []
    for got, said in [(IMPORTED, "new, backlog, 2 rounds, 0 transcripts"),
                      (IMPORTED | {"created": False, "status": "review", "rounds": 1, "transcripts": 1},
                       "updated, review, 1 round, 1 transcript")]:
        server.requests.clear()
        server.replies = [reply(PROJECT), reply(got)]
        main(["import", "b.zip"])
        lines.append(f"Imported #12 Rate-limit login ({said})\n")
        (_, lookup, _, _), (method, path, headers, body) = server.requests
        assert lookup == "/api/projects?" + urllib.parse.urlencode({"path": os.path.realpath(repo)})
        assert (method, path, body) == ("POST", "/api/projects/3/import", ZIP)
        assert (headers["Content-Type"], headers["X-Requested-By"]) == ("application/zip", "fctl")
    assert capsys.readouterr().out == "".join(lines)


def test_import_errors(server, repo, monkeypatch, capsys):  # AC44
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        main(["import", "missing.zip"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: can't read missing.zip: {os.strerror(2)}\n"
    assert server.requests == []
    (repo / "b.zip").write_bytes(b"nope")
    server.replies = [reply(PROJECT), reply({"detail": "not a zip file"}, 422)]
    with pytest.raises(SystemExit) as e:
        main(["import", "b.zip"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: 422 not a zip file\n"
