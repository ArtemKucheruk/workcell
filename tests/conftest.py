import os
import subprocess

import pytest
from fastapi.testclient import TestClient

from claude_factories.app import app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own FCTL_HOME, a do-nothing fake `claude` first on PATH, and git
    without the user's config (Q17)."""
    monkeypatch.setenv("FCTL_HOME", str(tmp_path / "fctl-home"))
    monkeypatch.delenv("FCTL_URL", raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text("#!/bin/sh\nexit 0\n")
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "test@example.com")


def git(cwd, *args) -> str:
    """Run git in cwd; its stripped stdout. Raises if git fails."""
    r = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A git repo on `main` with one empty commit and no remote."""
    path = tmp_path / "repo"
    git(tmp_path, "init", "-q", "-b", "main", str(path))
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return path


@pytest.fixture
def client():
    # base_url sets Host: 127.0.0.1:4545, which passes the Host check
    with TestClient(app, base_url="http://127.0.0.1:4545") as c:
        yield c
