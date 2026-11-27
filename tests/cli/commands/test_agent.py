import pytest

from workcell.cli.main import main

from ..conftest import Terminal, fctl, reply, requests


def test_show(server, capsys):  # 006 AC29
    server.reply = (200, "text/markdown; charset=utf-8", "# #12 x\n…".encode())
    main(["show", "12"])
    assert capsys.readouterr().out == "# #12 x\n…"
    main(["show", "12", "--round", "2"])
    main(["show", "12", "--feedback"])
    assert [(m, p) for m, p, _ in requests(server)] == [
        ("GET", "/api/tasks/12/context"),
        ("GET", "/api/tasks/12/context?round=2"),
        ("GET", "/api/tasks/12/context?feedback=1"),
    ]


def test_show_module(server, capsys):  # 112 AC25: the server's Module: line, printed as is
    server.reply = (200, "text/markdown; charset=utf-8", "# #12 x\nStatus: backlog\nModule: frontend\n".encode())
    main(["show", "12"])
    assert capsys.readouterr().out == "# #12 x\nStatus: backlog\nModule: frontend\n"


def test_spec(server, monkeypatch, capsys):  # 006 AC30
    server.reply = reply({"id": 12, "status": "in_progress", "stage": "spec"})
    fctl(monkeypatch, "spec", "12", stdin="## Acceptance criteria\n- x\n")
    assert requests(server) == [("PATCH", "/api/tasks/12", {"spec_md": "## Acceptance criteria\n- x\n"})]
    assert capsys.readouterr().out == "Spec saved on #12\n"


@pytest.mark.parametrize("stdin", ["  \n", Terminal()])
def test_spec_empty(server, monkeypatch, capsys, stdin):  # 006 AC31
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "spec", "12", stdin=stdin)
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: spec is empty; pass it on stdin\n"
    assert server.requests == []


def test_stage(server, capsys):  # 006 AC32
    server.reply = reply({"id": 12, "status": "in_progress", "stage": "agent_review"})
    main(["stage", "12", "agent_review"])
    assert requests(server) == [("PATCH", "/api/tasks/12", {"stage": "agent_review"})]
    assert capsys.readouterr().out == "#12: in_progress · agent_review\n"


def test_verdict(server, monkeypatch, capsys):  # 006 AC33
    server.reply = reply({"round": 1, "reviewer": "security", "verdict": "CHANGES", "complete": "3/4"})
    fctl(monkeypatch, "verdict", "12", "security", "CHANGES", stdin="1. app/limits.py:31 …\n")
    assert requests(server) == [("PUT", "/api/tasks/12/rounds/latest/verdicts/security",
                                 {"verdict": "CHANGES", "body_md": "1. app/limits.py:31 …\n"})]
    assert capsys.readouterr().out == "Round 1 of #12: security=CHANGES (3/4)\n"


def test_comment(server, monkeypatch, capsys):  # 006 AC34
    server.reply = reply({"id": 88}, 201)
    fctl(monkeypatch, "comment", "12", "security", "--path", "app/limits.py", "--line", "31",
         stdin="Use request.client.host.\n")
    assert requests(server) == [("POST", "/api/tasks/12/comments", {
        "round": "latest", "author": "security", "path": "app/limits.py", "line": 31, "side": "new",
        "body_md": "Use request.client.host.\n",
    })]
    assert capsys.readouterr().out == "Comment #88 on #12 app/limits.py:31\n"


def test_decide(server, monkeypatch, capsys):  # 006 AC35
    server.reply = reply({"id": 7}, 201)
    fctl(monkeypatch, "decide", "12", "APPROVE", stdin="All 4 PASS.\n")
    assert requests(server) == [("POST", "/api/tasks/12/decision", {"decision": "APPROVE", "body_md": "All 4 PASS.\n"})]
    assert capsys.readouterr().out == "Decision #7 on #12: APPROVE\n"


def test_agent_commands_skip_terminal_stdin(server, monkeypatch):  # 006 AC36
    server.replies = [reply({"round": 1, "reviewer": "ux", "verdict": "PASS", "complete": "1/4"}),
                      reply({"id": 88}, 201), reply({"id": 7}, 201)]
    fctl(monkeypatch, "verdict", "12", "ux", "PASS", stdin=Terminal())
    fctl(monkeypatch, "comment", "12", "ux", "--path", "a.py", "--line", "1", stdin=Terminal())
    fctl(monkeypatch, "decide", "12", "ESCALATE", stdin=Terminal())
    assert [body["body_md"] for _, _, body in requests(server)] == ["", "", ""]


def task_reply(rounds):
    return reply({"id": 12, "title": "x", "status": "in_progress", "stage": "agent_review", "branch": None,
                  "rounds": rounds, "decisions": [], "run": None})


def test_round(server, capsys):  # 006 AC37
    server.reply = task_reply([
        {"n": 1, "trigger": "initial", "files": 4, "additions": 118, "deletions": 9,
         "verdicts": {"security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS"}},
        {"n": 2, "trigger": "agent", "files": 4, "additions": 126, "deletions": 9,
         "verdicts": {"security": "PASS", "ux": "PASS", "ui": "pending", "code": "PASS"}},
    ])
    main(["round", "12"])
    assert requests(server) == [("GET", "/api/tasks/12", None)]
    assert capsys.readouterr().out == "round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)\n"


def test_round_without_rounds(server, capsys):  # 006 AC38
    server.reply = task_reply([])
    with pytest.raises(SystemExit) as e:
        main(["round", "12"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: #12 has no rounds\n"


@pytest.mark.parametrize("argv", [
    ["show", "12", "--round", "2", "--feedback"], ["show", "abc"],
    ["stage", "12", "deploy"],
    ["verdict", "12", "approver", "PASS"], ["verdict", "12", "security", "pass"], ["verdict", "12", "security"],
    ["comment", "12", "me", "--path", "a.py", "--line", "1"], ["comment", "12", "security", "--path", "a.py"],
    ["comment", "12", "security", "--path", "a.py", "--line", "x"], ["comment", "12", "--path", "a.py", "--line", "1"],
    ["decide", "12", "CHANGES_REQUESTED"], ["decide", "12", "approve"],
    ["round"],
])
def test_agent_usage_errors(server, monkeypatch, capsys, argv):  # 006 AC39
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, *argv, stdin=Terminal())
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith(f"usage: fctl {argv[0]}")
    assert server.requests == []
