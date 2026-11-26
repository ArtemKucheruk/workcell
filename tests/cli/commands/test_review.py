import pytest

from claude_factories.cli.main import main

from ..conftest import reply, requests


def test_approve(server, capsys):  # 009 AC24
    server.reply = reply({"status": "done", "commit_hint": "cd /x\ngit add -A && git commit -m 'T'"})
    main(["approve", "12"])
    assert requests(server) == [("POST", "/api/tasks/12/approve", {"body_md": ""})]
    assert capsys.readouterr().out == "#12: done\ncd /x\ngit add -A && git commit -m 'T'\n"


def test_rework(server, capsys):  # 009 AC25
    server.reply = reply({"status": "in_progress", "stage": "rework", "run_id": None}, 202)
    main(["rework", "12", "Make the limit configurable"])
    assert requests(server) == [("POST", "/api/tasks/12/request-changes", {"body_md": "Make the limit configurable"})]
    assert capsys.readouterr().out == "#12: in_progress · rework\n"


def test_rework_needs_note(server, capsys):  # 009 AC26
    with pytest.raises(SystemExit) as e:
        main(["rework", "12"])
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl rework")
    assert server.requests == []


def test_approve_refused(server, capsys):  # 009 AC26
    server.reply = reply({"detail": "#12 is not in review"}, 409)
    with pytest.raises(SystemExit) as e:
        main(["approve", "12"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: 409 #12 is not in review\n"


def test_approve_plane_warning(server, capsys):  # 109 AC15
    warning = "Approved, but Plane wasn't updated: Plane project has no completed state"
    server.reply = reply({"status": "done", "commit_hint": "git add -A", "plane_warning": warning})
    main(["approve", "12"])
    out = capsys.readouterr()
    assert (out.out, out.err) == ("#12: done\ngit add -A\n", warning + "\n")
    server.reply = reply({"status": "done", "commit_hint": "git add -A", "plane_warning": None})
    main(["approve", "12"])
    assert capsys.readouterr().err == ""
