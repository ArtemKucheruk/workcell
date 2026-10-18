import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent


# --- Repo and test harness ---------------------------------------------------


def test_gitignore():  # AC29
    lines = (REPO / ".gitignore").read_text().splitlines()
    for entry in [".venv/", "__pycache__/", ".pytest_cache/", "dist/"]:
        assert entry in lines


def test_harness_isolates(tmp_path):  # AC30
    assert Path(os.environ["FCTL_HOME"]).is_relative_to(tmp_path)
    claude = shutil.which("claude")
    assert claude == str(tmp_path / "bin" / "claude")
    r = subprocess.run([claude], capture_output=True)
    assert (r.returncode, r.stdout, r.stderr) == (0, b"", b"")
