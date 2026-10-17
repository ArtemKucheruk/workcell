import os

import pytest
from fastapi.testclient import TestClient

from claude_factories.app import app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own FCTL_HOME and a do-nothing fake `claude` first on PATH."""
    monkeypatch.setenv("FCTL_HOME", str(tmp_path / "fctl-home"))
    monkeypatch.delenv("FCTL_URL", raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text("#!/bin/sh\nexit 0\n")
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def client():
    # base_url sets Host: 127.0.0.1:4545, which passes the Host check
    with TestClient(app, base_url="http://127.0.0.1:4545") as c:
        yield c
