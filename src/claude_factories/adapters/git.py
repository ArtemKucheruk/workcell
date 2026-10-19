"""git, run as a subprocess with an argument list (docs/MVP.md §4.1)."""

import os
import subprocess
import tempfile
from typing import Protocol

from ..domain.errors import Failed

# cli/git.py capture()'s pinned diff flags (§7.4, 038 Q10): adapters can't import cli/
DIFF_FLAGS = ("-M", "--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "--src-prefix=a/",
              "--dst-prefix=b/")
SEED_IDENTITY = ("-c", "user.name=fctl seed", "-c", "user.email=seed@example.com", "-c", "commit.gpgsign=false")


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


def git_ok(*args: str, env: dict | None = None) -> bytes:
    """038: git's stdout. Failed with the first line of its stderr, or why git didn't start."""
    try:
        r = subprocess.run(["git", *args], capture_output=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:  # no git on PATH, a hung repo
        raise Failed(f"can't run git: {e}")
    if r.returncode:
        first = next(iter(r.stderr.decode(errors="replace").strip().splitlines()), f"exit code {r.returncode}")
        raise Failed(f"git failed: {first}")
    return r.stdout


class Git(Protocol):
    def committed(self, path: str, branch: str, file: str) -> bool: ...
    def exclude_path(self, repo: str) -> str: ...
    def add_worktree(self, repo: str, branch: str, path: str, base: str) -> str | None: ...
    def ls_files(self, root: str) -> tuple[bytes | None, str | None]: ...
    def current_branch(self, root: str) -> tuple[bytes | None, str | None]: ...
    def init(self, path: str) -> None: ...
    def commit_all(self, path: str, message: str) -> None: ...
    def capture(self, path: str) -> tuple[str, str]: ...
    def merge_parent(self, root: str, pr: int) -> str | None: ...


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

    def init(self, path: str) -> None:
        """038: a new repo at `path` (parents created) on `main`."""
        git_ok("init", "-q", "-b", "main", path)

    def commit_all(self, path: str, message: str) -> None:
        """038 Q10: everything in the tree, committed with a fixed identity, unsigned, and no hooks."""
        git_ok("-C", path, "add", "-A")
        git_ok("-C", path, *SEED_IDENTITY, "commit", "-q", "--no-verify", "-m", message)

    def capture(self, path: str) -> tuple[str, str]:
        """§7.4 step 2, as cli/git.py capture() runs it in `path`: (HEAD, the patch of the tracked and
        untracked changes against it), through a temp index so the real one is untouched."""
        base = git_ok("-C", path, "rev-parse", "--verify", "-q", "HEAD^{commit}").decode().strip()
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ | {"GIT_INDEX_FILE": os.path.join(tmp, "index")}
            pinned = ("-C", path, "-c", "core.quotePath=false")
            git_ok(*pinned, "read-tree", base, env=env)
            git_ok(*pinned, "add", "-A", env=env)
            patch = git_ok(*pinned, "diff", "--cached", *DIFF_FLAGS, base, env=env)
        return base, patch.decode(errors="replace")

    def merge_parent(self, root: str, pr: int) -> str | None:
        """031 Q6: the first parent of gh's merge commit for PR #pr, on any ref; None if git fails or none matches."""
        out, _ = git_stdout(root, "log", "--all", "--merges", "-F", "--grep", f"Merge pull request #{pr} from ",
                            "--format=%P", "-n", "1")
        parents = out.split() if out else []
        return parents[0].decode() if parents else None
