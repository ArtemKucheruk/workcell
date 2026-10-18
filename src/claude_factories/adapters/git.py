"""git, run as a subprocess with an argument list (docs/MVP.md §4.1)."""

import subprocess
from typing import Protocol


def git_stdout(root: str, *args: str) -> tuple[bytes | None, str | None]:
    """MVP §4.1, 016 Q10: (git's stdout, None), or (None, the first line of its stderr) if it fails."""
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return None, "git timed out"
    except (OSError, ValueError) as e:  # no git, a NUL in the path
        return None, str(e)
    if r.returncode:
        return None, next(iter(r.stderr.decode(errors="replace").strip().splitlines()), f"git exited {r.returncode}")
    return r.stdout, None


class Git(Protocol):
    def committed(self, path: str, branch: str, file: str) -> bool: ...
    def exclude_path(self, repo: str) -> str: ...
    def add_worktree(self, repo: str, branch: str, path: str, base: str) -> str | None: ...
    def ls_files(self, root: str) -> tuple[bytes | None, str | None]: ...
    def current_branch(self, root: str) -> tuple[bytes | None, str | None]: ...


class SubprocessGit:
    def committed(self, path: str, branch: str, file: str) -> bool:
        """`file` is committed on `branch` of the repo at `path`. Any failure is False."""
        try:
            return subprocess.run(
                ["git", "-C", path, "cat-file", "-e", f"{branch}:{file}"], capture_output=True, timeout=10,
            ).returncode == 0
        except (OSError, ValueError, subprocess.TimeoutExpired):  # no git, a NUL in the path, a hung repo
            return False

    def exclude_path(self, repo: str) -> str:
        """012 Q5: the absolute path of the repo's info/exclude. Raises if git fails."""
        return subprocess.run(
            ["git", "-C", repo, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    def add_worktree(self, repo: str, branch: str, path: str, base: str) -> str | None:
        """012 Q4: a new `branch` from `base`, checked out at `path`. git's stripped stderr if it fails."""
        added = subprocess.run(["git", "-C", repo, "worktree", "add", "-b", branch, path, base],
                               capture_output=True, text=True, errors="replace")
        return added.stderr.strip() if added.returncode else None

    def ls_files(self, root: str) -> tuple[bytes | None, str | None]:
        """016: the tracked files, NUL-separated, as git_stdout answers."""
        return git_stdout(root, "ls-files", "-z")

    def current_branch(self, root: str) -> tuple[bytes | None, str | None]:
        return git_stdout(root, "branch", "--show-current")
