import os
import subprocess
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from claude_factories import db
from claude_factories.app import LOGIN, app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own FCTL_HOME and HOME (so nothing touches the real ~/.claude), a
    do-nothing fake `claude` first on PATH, and git without the user's config (Q17). 014: an empty
    claude_login() cache, since tests swap fakes."""
    LOGIN.clear()
    monkeypatch.setenv("FCTL_HOME", str(tmp_path / "fctl-home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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


def write(repo, files: dict):
    """Write {relative path: str or bytes} under repo, bytes as given (\\r\\n kept)."""
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())


def commit(repo, files: dict | None = None) -> str:
    """Write files, commit everything, and return the new HEAD."""
    write(repo, files or {})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c")
    return git(repo, "rev-parse", "HEAD")


def sql(query, args=()):
    """Run one statement against the test's database; its rows."""
    with closing(db.connect()) as conn, conn:
        return conn.execute(query, args).fetchall()


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
