"""git, run as a subprocess with an argument list (docs/MVP.md §4.1)."""

import subprocess
from typing import Protocol


class Git(Protocol):
    def committed(self, path: str, branch: str, file: str) -> bool: ...


class SubprocessGit:
    def committed(self, path: str, branch: str, file: str) -> bool:
        """`file` is committed on `branch` of the repo at `path`. Any failure is False."""
        try:
            return subprocess.run(
                ["git", "-C", path, "cat-file", "-e", f"{branch}:{file}"], capture_output=True, timeout=10,
            ).returncode == 0
        except (OSError, ValueError, subprocess.TimeoutExpired):  # no git, a NUL in the path, a hung repo
            return False
