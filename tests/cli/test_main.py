import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI

from claude_factories import config
from claude_factories.cli.main import main

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


def test_serve_has_no_host_option(uvicorn_calls):  # AC6
    with pytest.raises(SystemExit) as e:
        main(["serve", "--host", "0.0.0.0"])
    assert e.value.code == 2
    assert uvicorn_calls == []


def test_serve_prints_banner_before_run(uvicorn_calls):  # AC7
    main(["serve", "--port", "5000"])
    assert uvicorn_calls[0]["stdout"] == (
        f"Claude Factories → http://127.0.0.1:5000 (data: {config.data_dir()})\n"
    )


def test_serve_runs_create_app(uvicorn_calls):  # 034 AC4
    main(["serve"])
    app = uvicorn_calls[0]["app"]
    assert isinstance(app, FastAPI)
    assert "get" in app.openapi()["paths"]["/api/workspaces"]


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
