import json
import os
import urllib.parse

import pytest
from conftest import git

from claude_factories.cli.main import main

from ..conftest import PROJECT, RUN, reply, requests

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
    assert err == "fctl: 409 not on subscription auth\n"


def test_task_add_without_run(server, repo, monkeypatch, capsys):  # 015 AC17
    server.replies = [reply(PROJECT), reply(ADDED, 201), reply(RUN, 202)]
    monkeypatch.chdir(repo)
    main(["task", "add", "T"])
    assert [(m, p) for m, p, _ in requests(server)][1:] == [("POST", "/api/projects/3/tasks")]
    assert capsys.readouterr().out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"
