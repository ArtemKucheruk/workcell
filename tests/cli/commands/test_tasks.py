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
    assert capsys.readouterr().out == f"Added #12 to api → {url}/projects/3\nRun #41 on #12 as b@y → {url}/tasks/12\n"


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
    assert capsys.readouterr().out == f"Added #12 to api → {url}/projects/3\nRun #41 on #12 as b@y → {url}/tasks/12\n"


def test_task_add_help(capsys):  # 060 BE6
    with pytest.raises(SystemExit) as e:
        main(["task", "add", "--help"])
    assert e.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--description TEXT" in out
    assert '"-" reads it from stdin' in out


# --- 094: fctl task add --blocked-by, fctl task block, fctl task unblock ----------------------------------------


def test_task_add_blocked_by(task_server, repo, monkeypatch, capsys):  # 094 AC17
    monkeypatch.chdir(repo)
    main(["task", "add", "T", "--blocked-by", "12,14"])
    assert requests(task_server)[1] == ("POST", "/api/projects/3/tasks", {"title": "T", "blocked_by": [12, 14]})
    assert capsys.readouterr().out == f"Added #12 to api → {os.environ['FCTL_URL']}/projects/3\n"


@pytest.mark.parametrize("value", ["12,x", "x", "0", "12,-1", "12,,14", "1.5", "12, 14", ""])
def test_task_add_blocked_by_usage(server, repo, monkeypatch, capsys, value):  # 094 AC18
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        main(["task", "add", "T", f"--blocked-by={value}"])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: fctl task add") and "argument --blocked-by: task ids must be positive" in err
    assert server.requests == []


DEPS = {"id": 15, "blocked": True, "blocked_by": [{"id": 12, "title": "A", "status": "backlog"},
                                                  {"id": 14, "title": "B", "status": "done"}], "blocks": []}


@pytest.mark.parametrize("words, method", [("block", "PUT"), ("unblock", "DELETE")])
def test_task_block(server, tmp_path, monkeypatch, capsys, words, method):  # 094 AC19
    monkeypatch.chdir(tmp_path)  # task ids are global: no repo needed
    server.replies = [reply(DEPS), reply(DEPS | {"blocked": False, "blocked_by": []})]
    main(["task", words, "15", "--by", "12"])
    main(["task", words, "15", "--by", "12"])
    assert requests(server) == [(method, "/api/tasks/15/blocked-by/12", None)] * 2
    assert capsys.readouterr().out == "#15 blocked by #12 (backlog), #14 (done)\n#15 has no blockers\n"


@pytest.mark.parametrize("argv, status, detail", [
    (["block", "15", "--by", "12"], 422, "cycle: #15 waits on #12, which waits on #15"),
    (["unblock", "15", "--by", "12"], 404, "#15 is not blocked by #12"),
])
def test_task_block_refused(server, monkeypatch, capsys, argv, status, detail):  # 094 AC20
    server.reply = reply({"detail": detail}, status)
    with pytest.raises(SystemExit) as e:
        main(["task", *argv])
    assert e.value.code == 1
    assert capsys.readouterr() == ("", f"fctl: {status} {detail}\n")


# --- 106: fctl task retry ------------------------------------------------------------------------

def task_with(run):
    return reply({"id": 12, "title": "T", "status": "in_progress", "run": run})


RETRIED = RUN | {"run_id": 42}


@pytest.mark.parametrize("status", ["failed", "stopped"])
def test_task_retry(server, tmp_path, monkeypatch, capsys, status):  # 106 AC1, AC2, AC9
    nowhere = tmp_path / "nowhere"  # outside any git repo: no project lookup
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(nowhere)
    server.replies = [task_with({"id": 41, "status": status}), reply(RETRIED, 202)]
    main(["task", "retry", "12"])
    assert requests(server) == [("GET", "/api/tasks/12", None), ("POST", "/api/tasks/12/run", None)]
    assert capsys.readouterr().out == f"Run #42 on #12 as b@y → {os.environ['FCTL_URL']}/tasks/12\n"


def test_task_retry_account_id(server, tmp_path, monkeypatch):  # 106 AC3
    monkeypatch.chdir(tmp_path)
    server.replies = [task_with({"id": 41, "status": "failed"}), reply(RETRIED, 202)]
    main(["task", "retry", "12", "--account", "2"])
    assert requests(server) == [("GET", "/api/tasks/12", None), ("POST", "/api/tasks/12/run", {"account_id": 2})]


def test_task_retry_account_email(server, tmp_path, monkeypatch, capsys):  # 106 AC4, Q3
    monkeypatch.chdir(tmp_path)
    accounts = reply([{"id": 1, "email": "a@x"}, {"id": 2, "email": "b@y"}])
    server.replies = [task_with({"id": 41, "status": "failed"}), accounts, reply(RETRIED, 202)]
    main(["task", "retry", "12", "--account", "B@y"])
    assert requests(server) == [("GET", "/api/tasks/12", None), ("GET", "/api/auth/accounts", None),
                                ("POST", "/api/tasks/12/run", {"account_id": 2})]
    capsys.readouterr()
    server.requests.clear()
    server.replies = [task_with({"id": 41, "status": "failed"}), reply([{"id": 1, "email": "a@x"}])]
    with pytest.raises(SystemExit) as e:
        main(["task", "retry", "12", "--account", "b@y"])
    assert e.value.code == 1
    assert capsys.readouterr().err == "fctl: no Claude account b@y\n"
    assert [m for m, _, _ in requests(server)] == ["GET", "GET"]


@pytest.mark.parametrize("run, err", [
    (None, "fctl: #12 never ran; use fctl run 12\n"),  # AC5
    ({"id": 41, "status": "running"}, "fctl: run #41 is running on #12; wait for it or stop it\n"),  # AC6
])
def test_task_retry_nothing_to_retry(server, tmp_path, monkeypatch, capsys, run, err):  # 106 AC5, AC6
    monkeypatch.chdir(tmp_path)
    server.replies = [task_with(run)]
    with pytest.raises(SystemExit) as e:
        main(["task", "retry", "12", "--account", "b@y"])  # Q3: refused before any accounts lookup
    assert e.value.code == 1
    assert capsys.readouterr() == ("", err)
    assert requests(server) == [("GET", "/api/tasks/12", None)]


@pytest.mark.parametrize("detail", [
    "#15 is blocked by #12, #14; finish those first or remove the dependency",
    "#12 is in review",
    "2 runs active (#41 on #12, #42 on #14); the limit is 2. Wait, stop one, or raise it in Settings",
])
def test_task_retry_refused(server, tmp_path, monkeypatch, capsys, detail):  # 106 AC7
    monkeypatch.chdir(tmp_path)
    server.replies = [task_with({"id": 41, "status": "failed"}), reply({"detail": detail}, 409)]
    with pytest.raises(SystemExit) as e:
        main(["task", "retry", "12"])
    assert e.value.code == 1
    assert capsys.readouterr() == ("", f"fctl: 409 {detail}\n")


def test_task_retry_unknown_task(server, tmp_path, monkeypatch, capsys):  # 106 AC8
    monkeypatch.chdir(tmp_path)
    server.replies = [reply({"detail": "Task #99 not found"}, 404)]
    with pytest.raises(SystemExit) as e:
        main(["task", "retry", "99"])
    assert e.value.code == 1
    assert capsys.readouterr() == ("", "fctl: 404 Task #99 not found\n")
    assert requests(server) == [("GET", "/api/tasks/99", None)]


# --- 105: fctl task delete ---------------------------------------------------------------------

CSV = {"id": 14, "title": "Export CSV", "status": "backlog"}
PROMPT = ("Delete #14 Export CSV?\nThis removes its runs, rounds and their files, verdicts, comments, decisions, status"
          " history, and transcript records from the app. Its worktree, branch, run logs, and copied transcript files"
          " stay on disk.\nDelete? [y/N] ")
GONE = (204, "application/json", b"")  # DELETE's empty body, under FastAPI's default content type


def Answer(line):
    """A terminal stdin whose readline (input()'s) answers the prompt with `line`; "" is EOF. read() fails the test."""
    return Terminal(line)


def deleting(server, monkeypatch, capsys, *argv, stdin, code=0):
    """Runs fctl task delete; returns (requests' (method, path), stdout, stderr)."""
    if code:
        with pytest.raises(SystemExit) as e:
            fctl(monkeypatch, "task", "delete", *argv, stdin=stdin)
        assert e.value.code == code
    else:
        fctl(monkeypatch, "task", "delete", *argv, stdin=stdin)
    out, err = capsys.readouterr()
    return [(m, p) for m, p, _, _ in server.requests], out, err


def test_task_delete_yes(server, tmp_path, monkeypatch, capsys):  # 105 AC9
    monkeypatch.chdir(tmp_path)  # task ids are global: no repo needed
    server.replies = [reply(CSV), GONE]
    sent, out, err = deleting(server, monkeypatch, capsys, "14", "--yes", stdin=Terminal())
    assert sent == [("GET", "/api/tasks/14"), ("DELETE", "/api/tasks/14")]
    assert server.requests[1][2]["X-Requested-By"] == "fctl"
    assert (out, err) == ("Deleted #14 Export CSV\n", "")
    # off a terminal too, and stdin stays unread
    server.requests.clear()
    server.replies = [reply(CSV), GONE]
    sent, out, _ = deleting(server, monkeypatch, capsys, "14", "--yes", stdin="y\n")
    assert sent == [("GET", "/api/tasks/14"), ("DELETE", "/api/tasks/14")]
    assert sys.stdin.read() == "y\n"


@pytest.mark.parametrize("answer", ["y\n", "yes\n", "  YES  \n", "Y\n", "Yes"])
def test_task_delete_confirmed(server, monkeypatch, capsys, answer):  # 105 AC10
    server.replies = [reply(CSV), GONE]
    sent, out, err = deleting(server, monkeypatch, capsys, "14", stdin=Answer(answer))
    assert sent == [("GET", "/api/tasks/14"), ("DELETE", "/api/tasks/14")]
    assert (out, err) == (PROMPT + "Deleted #14 Export CSV\n", "")


@pytest.mark.parametrize("answer", ["n\n", "no\n", "\n", "", "yep\n", "y es\n"])
def test_task_delete_declined(server, monkeypatch, capsys, answer):  # 105 AC11, Q4: "" is EOF
    server.replies = [reply(CSV)]
    sent, out, err = deleting(server, monkeypatch, capsys, "14", stdin=Answer(answer), code=1)
    assert sent == [("GET", "/api/tasks/14")]
    assert (out, err) == (PROMPT, "fctl: not deleted\n")


def test_task_delete_not_a_terminal(server, monkeypatch, capsys):  # 105 AC12, Q5
    sent, out, err = deleting(server, monkeypatch, capsys, "14", stdin="y\n", code=1)
    assert sent == []
    assert (out, err) == ("", "fctl: not a terminal; pass --yes to delete #14 without asking\n")
    assert sys.stdin.read() == "y\n"


@pytest.mark.parametrize("argv, stdin", [(["99", "--yes"], ""), (["99"], Terminal())])
def test_task_delete_unknown(server, monkeypatch, capsys, argv, stdin):  # 105 AC13, Q3
    server.reply = reply({"detail": "Not Found"}, 404)
    sent, out, err = deleting(server, monkeypatch, capsys, *argv, stdin=stdin, code=1)
    assert sent == [("GET", "/api/tasks/99")]
    assert (out, err) == ("", "fctl: 404 Not Found\n")


@pytest.mark.parametrize("argv, stdin, prompt", [(["14", "--yes"], "", ""), (["14"], Answer("y\n"), PROMPT)])
def test_task_delete_run_active(server, monkeypatch, capsys, argv, stdin, prompt):  # 105 AC14, Q6
    server.replies = [reply(CSV | {"status": "in_progress"}), reply({"detail": "run #41 active"}, 409)]
    sent, out, err = deleting(server, monkeypatch, capsys, *argv, stdin=stdin, code=1)
    assert sent == [("GET", "/api/tasks/14"), ("DELETE", "/api/tasks/14")]
    assert (out, err) == (prompt, "fctl: 409 run #41 active\n")


@pytest.mark.parametrize("value", ["x", "1.5", ""])
def test_task_delete_usage(server, monkeypatch, capsys, value):  # 105 AC15
    with pytest.raises(SystemExit) as e:
        fctl(monkeypatch, "task", "delete", value, "--yes")
    assert e.value.code == 2
    assert capsys.readouterr().err.startswith("usage: fctl task delete")
    assert server.requests == []


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
