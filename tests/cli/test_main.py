import os
import re
import socket
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from claude_factories import config, db
from claude_factories.cli.main import main
from claude_factories.repositories.workspaces import WorkspacesRepo
from claude_factories.server.app import create_app

FCTL = Path(sys.executable).parent / "fctl"


# --- Package and CLI ---------------------------------------------------------


def test_help_names_serve():  # AC1
    r = subprocess.run([FCTL, "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "serve" in r.stdout


def test_no_command_is_usage_error():  # AC2
    r = subprocess.run([FCTL], capture_output=True, text=True)
    assert r.returncode == 2
    assert r.stderr.startswith("usage: fctl")


# --- fctl serve --------------------------------------------------------------


@pytest.fixture
def uvicorn_calls(monkeypatch, capsys):
    calls = []

    def fake_run(app, **kwargs):
        calls.append({"app": app, "stdout": capsys.readouterr().out, **kwargs})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return calls


def test_serve_defaults_to_localhost_4545(uvicorn_calls):  # AC4
    main(["serve"])
    assert len(uvicorn_calls) == 1
    assert uvicorn_calls[0]["host"] == "127.0.0.1"
    assert uvicorn_calls[0]["port"] == 4545


def test_serve_port_option(uvicorn_calls):  # AC5
    main(["serve", "--port", "5000"])
    assert uvicorn_calls[0]["port"] == 5000
    assert uvicorn_calls[0]["host"] == "127.0.0.1"


def test_serve_prints_banner_before_run(uvicorn_calls):  # AC7
    main(["serve", "--port", "5000"])
    assert uvicorn_calls[0]["stdout"] == (
        f"Claude Factories → http://127.0.0.1:5000 (data: {config.data_dir()})\n"
    )


def test_serve_host_option(uvicorn_calls):  # 027 AC1
    main(["serve", "--host", "0.0.0.0"])
    assert len(uvicorn_calls) == 1
    assert uvicorn_calls[0]["host"] == "0.0.0.0"
    assert uvicorn_calls[0]["port"] == 4545


def test_serve_banner_shows_host(uvicorn_calls):  # 027 AC3
    main(["serve", "--host", "0.0.0.0", "--port", "5000"])
    assert uvicorn_calls[0]["stdout"] == f"Claude Factories → http://0.0.0.0:5000 (data: {config.data_dir()})\n"


def test_serve_help_lists_host():  # 027 AC4
    r = subprocess.run([FCTL, "serve", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    help_text = " ".join(r.stdout.split())  # argparse wraps at the terminal width
    assert re.search(r"--host HOST .*default: 127\.0\.0\.1", help_text)


def test_serve_runs_create_app(uvicorn_calls):  # 034 AC4
    main(["serve"])
    app = uvicorn_calls[0]["app"]
    assert isinstance(app, FastAPI)
    assert "get" in app.openapi()["paths"]["/api/workspaces"]
    assert app.state.port == 4545


def test_serve_passes_port(uvicorn_calls):  # 104 Q4: the scheduler's FCTL_URL port
    main(["serve", "--port", "5000"])
    assert (uvicorn_calls[0]["port"], uvicorn_calls[0]["app"].state.port) == (5000, 5000)


# --- fctl setup (015) ----------------------------------------------------------------


def skill(name) -> Path:
    return Path(os.environ["HOME"]) / ".claude" / "skills" / name / "SKILL.md"


def frontmatter(text) -> tuple[str, str]:
    """A SKILL.md's (frontmatter, body); it must start with a `---` block."""
    assert text.startswith("---\n")
    front, body = text[4:].split("\n---\n", 1)
    return front, body


def test_setup_writes_skills(server):  # 015 AC1
    assert not (Path(os.environ["HOME"]) / ".claude").exists()
    main(["setup"])
    assert skill("factory-connect").is_file()
    assert skill("factory-submit").is_file()


def test_setup_output(server, capsys):  # 015 AC2
    main(["setup"])
    assert capsys.readouterr().out == f"Wrote {skill('factory-connect')}\nWrote {skill('factory-submit')}\n"


def test_setup_is_offline(server, monkeypatch):  # 015 AC3
    main(["setup"])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("FCTL_URL", f"http://127.0.0.1:{port}")  # bound then closed: nothing listens
    main(["setup"])  # returns: exit 0
    assert server.requests == []


def test_setup_connect_skill(server):  # 015 AC4
    main(["setup"])
    front, body = frontmatter(skill("factory-connect").read_text())
    assert "name: factory-connect" in front.splitlines()
    assert re.search(r"^description: \S", front, re.M)
    for needle in ("$ARGUMENTS", "fctl connect --workspace", "--test-cmd"):
        assert needle in body


def test_setup_submit_skill(server):  # 015 AC5
    main(["setup"])
    front, body = frontmatter(skill("factory-submit").read_text())
    assert "name: factory-submit" in front.splitlines()
    assert re.search(r"^description: \S", front, re.M)
    assert "fctl submit --new --title" in body
    assert "fctl submit <id> <<'EOF'" in body
    assert re.search(r"fctl submit --new --title .*<<'EOF'\n", body)


def test_setup_overwrites_only_skill_md(server):  # 015 AC6
    main(["setup"])
    first = skill("factory-connect").read_bytes()
    skill("factory-connect").write_text("my edit\n")
    notes = skill("factory-connect").with_name("notes.md")
    notes.write_text("mine\n")
    main(["setup"])
    assert skill("factory-connect").read_bytes() == first
    assert notes.read_text() == "mine\n"


def test_setup_cant_write(server, capsys):  # 015 AC7
    skills = Path(os.environ["HOME"]) / ".claude" / "skills"
    skills.parent.mkdir()
    skills.write_text("not a dir\n")
    with pytest.raises(SystemExit) as e:
        main(["setup"])
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith(f"fctl: can't write {skill('factory-connect')}: ")
    assert "Traceback" not in err


# --- fctl seed (038) -----------------------------------------------------------------


TABLES = ("workspaces", "projects", "tasks", "runs", "rounds", "round_files", "verdicts", "comments",
          "decisions", "events")


def row_counts() -> dict:
    with closing(db.connect()) as conn:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]  # bound then closed: nothing listens


def refused(capsys) -> str:
    """seed's exit 1 and its stderr."""
    with pytest.raises(SystemExit) as e:
        main(["seed"])
    assert e.value.code == 1
    return capsys.readouterr().err


def test_seed_fresh_home(monkeypatch, capsys):  # AC1
    home = config.data_dir()
    assert not home.exists()
    monkeypatch.setenv("FCTL_URL", f"http://127.0.0.1:{closed_port()}")
    main(["seed"])  # returns: exit 0
    assert (home / "factory.db").is_file() and (home / "demo").is_dir()
    out = capsys.readouterr().out
    assert out.startswith(f"Seeded {home}: ") and out.count("\n") == 1 and out.endswith("\n")


def test_seed_twice(capsys):  # AC2
    main(["seed"])
    before = row_counts()
    capsys.readouterr()
    assert refused(capsys) == "fctl: FCTL_HOME has data; seed an empty one\n"
    assert row_counts() == before


def test_seed_refuses_a_workspace(capsys):  # AC3
    db.init()
    with closing(db.connect()) as conn, conn:
        WorkspacesRepo(conn).get_or_create("personal")
    before = row_counts()
    assert refused(capsys) == "fctl: FCTL_HOME has data; seed an empty one\n"
    assert not (config.data_dir() / "demo").exists()
    assert row_counts() == before


def test_seed_refuses_leftover_demo(capsys):  # AC4
    db.init()
    (config.data_dir() / "demo").mkdir()
    assert refused(capsys) == f"fctl: {config.data_dir()}/demo exists; seed an empty FCTL_HOME\n"
    assert set(row_counts().values()) == {0}
    assert list((config.data_dir() / "demo").iterdir()) == []


def test_seed_without_git(tmp_path, monkeypatch, capsys):  # AC5
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))  # conftest's fake claude only
    err = refused(capsys)
    assert err.startswith("fctl: ") and err.count("\n") == 1
    assert "Traceback" not in err
    assert row_counts()["workspaces"] == 0


def test_seed_ignores_my_git_config(tmp_path, monkeypatch):  # AC6
    (tmp_path / "gitconfig").write_text(  # conftest's GIT_CONFIG_GLOBAL
        "[user]\n\tuseConfigOnly = true\n[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n"
        "[diff]\n\tnoprefix = true\n[color]\n\tui = always\n")
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(name, raising=False)
    main(["seed"])  # returns: exit 0
    with TestClient(create_app(), base_url="http://127.0.0.1:4545") as client:
        with closing(db.connect()) as conn:
            task_ids = [i for (i,) in conn.execute("SELECT DISTINCT task_id FROM rounds")]
        assert len(task_ids) >= 9
        for task_id in task_ids:
            assert client.get(f"/api/tasks/{task_id}/rounds/latest/diff").text.startswith("diff --git a/")
