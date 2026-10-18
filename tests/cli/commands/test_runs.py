import os
import urllib.parse

import pytest

from claude_factories.cli.main import main

from ..conftest import PROJECT, RUN, reply, requests


def test_run_task(server, capsys):  # 015 AC8
    server.reply = reply(RUN, 202)
    main(["run", "12"])
    assert requests(server) == [("POST", "/api/tasks/12/run", None)]
    assert capsys.readouterr().out == f"Run #41 on #12 → {os.environ['FCTL_URL']}/tasks/12\n"


def test_run_task_outside_repo(server, tmp_path, monkeypatch):  # 015 AC9
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(nowhere)
    server.reply = reply(RUN, 202)
    main(["run", "12"])
    assert requests(server) == [("POST", "/api/tasks/12/run", None)]


def test_run_next(server, repo, monkeypatch, capsys):  # 015 AC10
    server.replies = [reply(PROJECT), reply({"task_id": 14, "run_id": 42}, 202)]
    monkeypatch.chdir(repo)
    main(["run", "next"])
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
        main(["run", "next"])
    assert e.value.code == 1
    assert capsys.readouterr().err == f"fctl: not inside a git repository: {os.getcwd()}\n"
    assert server.requests == []


def test_run_next_empty_backlog(server, repo, monkeypatch, capsys):  # 015 AC12
    server.replies = [reply(PROJECT), reply({"detail": "backlog is empty"}, 404)]
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        main(["run", "next"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: 404 backlog is empty\n"


def test_run_refused(server, capsys):  # 015 AC13
    server.reply = reply({"detail": "run #41 active"}, 409)
    with pytest.raises(SystemExit) as e:
        main(["run", "12"])
    assert e.value.code == 1
    out, err = capsys.readouterr()
    assert (out, err) == ("", "fctl: 409 run #41 active\n")


@pytest.mark.parametrize("argv", [["run"], ["run", "abc"]])
def test_run_usage_errors(server, capsys, argv):  # 015 AC14
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl run")
    assert server.requests == []
