"""git, run as a subprocess with an argument list (docs/MVP.md §4.1)."""

import os
import shlex
import shutil
import subprocess
import tempfile
from typing import Protocol

from ..domain.errors import Failed

# cli/git.py capture()'s pinned diff flags (§7.4, 038 Q10): adapters can't import cli/
DIFF_FLAGS = ("-M", "--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "--src-prefix=a/",
              "--dst-prefix=b/")
SEED_IDENTITY = ("-c", "user.name=fctl seed", "-c", "user.email=seed@example.com", "-c", "commit.gpgsign=false")
LOCAL_TIMEOUT = 60  # 093 AC3: local git, as git_ok
NETWORK_TIMEOUT = 120  # 093 AC3: push, fetch, and every gh call
MERGE_METHOD = "--merge"  # 093 AC4: a merge commit, as this repo's history has
Ran = tuple[int, str, str]  # 093: (exit code, stdout, stderr)


def ran(argv: list[str], timeout: int, env: dict | None = None) -> Ran:
    """093 AC3: argv's (exit code, stdout, stderr), as text. A timeout is Failed("<tool> timed out: <command>"), a
    tool that won't start Failed("can't run <tool>: …"): 500s with a detail, never a stack trace."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, errors="replace", env=env, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Failed(f"{argv[0]} timed out: {shlex.join(argv)}") from None
    except (OSError, ValueError) as e:  # not on PATH, a NUL in an argument
        raise Failed(f"can't run {argv[0]}: {e}") from None
    return r.returncode, r.stdout, r.stderr


def gh(*args: str) -> Ran:
    """093 AC3: gh with prompts off, so a missing login fails instead of waiting on stdin."""
    return ran(["gh", *args], NETWORK_TIMEOUT, os.environ | {"GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1"})


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
    def exclude_path(self, repo: str) -> str: ...
    def add_worktree(self, repo: str, branch: str, path: str, base: str) -> str | None: ...
    def ls_files(self, root: str) -> tuple[bytes | None, str | None]: ...
    def current_branch(self, root: str) -> tuple[bytes | None, str | None]: ...
    def branch_refs(self, root: str) -> tuple[bytes | None, str | None]: ...
    def ls_tree(self, root: str, ref: str) -> tuple[bytes | None, str | None]: ...
    def object_id(self, root: str, ref: str, path: str) -> tuple[bytes | None, str | None]: ...
    def object_type(self, root: str, oid: str) -> tuple[bytes | None, str | None]: ...
    def object_size(self, root: str, oid: str) -> tuple[bytes | None, str | None]: ...
    def blob(self, root: str, oid: str) -> tuple[bytes | None, str | None]: ...
    def init(self, path: str) -> None: ...
    def commit_all(self, path: str, message: str) -> None: ...
    def capture(self, path: str) -> tuple[str, str]: ...
    def merge_parent(self, root: str, pr: int) -> str | None: ...
    # 093: Create PR and Merge PR. Each answers (exit code, stdout, stderr); the handler words the refusal
    def origin_url(self, root: str) -> Ran: ...
    def porcelain(self, path: str) -> Ran: ...
    def ahead(self, path: str, base: str) -> Ran: ...
    def commit(self, path: str, message: str) -> Ran: ...
    def push(self, path: str, branch: str) -> Ran: ...
    def fetch(self, root: str) -> Ran: ...
    def head_branch(self, root: str) -> Ran: ...
    def is_ancestor(self, root: str, ref: str, of: str) -> Ran: ...
    def ff_merge(self, root: str, ref: str) -> Ran: ...
    def remove_worktree(self, root: str, path: str) -> Ran: ...
    def delete_branch(self, root: str, branch: str) -> Ran: ...
    def delete_remote_branch(self, root: str, branch: str) -> Ran: ...
    def gh_installed(self) -> bool: ...
    def gh_auth(self) -> Ran: ...
    def pr_list(self, repo: str, branch: str) -> Ran: ...
    def pr_create(self, repo: str, base: str, branch: str, title: str, body: str) -> Ran: ...
    def pr_view(self, repo: str, number: int) -> Ran: ...
    def pr_merge(self, repo: str, number: int) -> Ran: ...


class SubprocessGit:
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

    def branch_refs(self, root: str) -> tuple[bytes | None, str | None]:
        """054 Q4: the full refnames of the local and origin branches, one per line, in refname order."""
        return git_stdout(root, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin")

    def ls_tree(self, root: str, ref: str) -> tuple[bytes | None, str | None]:
        """054: the files committed on the full refname `ref`, NUL-separated, like ls_files."""
        return git_stdout(root, "ls-tree", "-r", "-z", "--name-only", ref)

    def object_id(self, root: str, ref: str, path: str) -> tuple[bytes | None, str | None]:
        """054: the id of `path`'s object on `ref`, resolved once so a moving ref can't swap it between reads."""
        return git_stdout(root, "rev-parse", "--verify", "-q", f"{ref}:{path}")

    def object_type(self, root: str, oid: str) -> tuple[bytes | None, str | None]:
        """054 Q6: the object's own type (`blob`, `tag`, `commit`, ...), never peeled."""
        return git_stdout(root, "cat-file", "-t", oid)

    def object_size(self, root: str, oid: str) -> tuple[bytes | None, str | None]:
        """054 Q5: the object's size in bytes, without reading it."""
        return git_stdout(root, "cat-file", "-s", oid)

    def blob(self, root: str, oid: str) -> tuple[bytes | None, str | None]:
        """054 Q6: a blob's raw bytes (a symlink's is its target path), with no diff, textconv, or filter. It
        peels an annotated tag to the blob it names, so check object_type first."""
        return git_stdout(root, "cat-file", "blob", oid)

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

    # --- 093: Create PR and Merge PR, run only when I click one (docs/MVP.md §3.7) ---------------

    def origin_url(self, root: str) -> Ran:
        """AC11: origin as configured, without insteadOf rewriting (which `git remote get-url` would apply)."""
        return ran(["git", "-C", root, "config", "--get", "remote.origin.url"], LOCAL_TIMEOUT)

    def porcelain(self, path: str) -> Ran:
        """Q7: untracked files are listed too, so they count as changes; ignored ones aren't."""
        return ran(["git", "-C", path, "status", "--porcelain"], LOCAL_TIMEOUT)

    def ahead(self, path: str, base: str) -> Ran:
        """AC16: how many commits HEAD has that `base` doesn't."""
        return ran(["git", "-C", path, "rev-list", "--count", f"{base}..HEAD", "--"], LOCAL_TIMEOUT)

    def commit(self, path: str, message: str) -> Ran:
        """AC15, Q4: everything not ignored, committed as the configured identity with hooks and signing as set:
        no -c overrides, no --no-verify, and the message exactly `message`. The add's result if it fails."""
        added = ran(["git", "-C", path, "add", "-A"], LOCAL_TIMEOUT)
        return added if added[0] else ran(["git", "-C", path, "commit", "-q", "-m", message], LOCAL_TIMEOUT)

    def push(self, path: str, branch: str) -> Ran:
        """AC18: never forced."""
        return ran(["git", "-C", path, "push", "-u", "origin", branch], NETWORK_TIMEOUT)

    def fetch(self, root: str) -> Ran:
        return ran(["git", "-C", root, "fetch", "origin"], NETWORK_TIMEOUT)

    def head_branch(self, root: str) -> Ran:
        """AC32: the checked-out branch's name; empty on a detached HEAD."""
        return ran(["git", "-C", root, "branch", "--show-current"], LOCAL_TIMEOUT)

    def is_ancestor(self, root: str, ref: str, of: str) -> Ran:
        """AC31: exit 0 when `ref` is an ancestor of `of` (or the same commit), 1 when not."""
        return ran(["git", "-C", root, "merge-base", "--is-ancestor", ref, of], LOCAL_TIMEOUT)

    def ff_merge(self, root: str, ref: str) -> Ran:
        return ran(["git", "-C", root, "merge", "--ff-only", ref], LOCAL_TIMEOUT)

    def remove_worktree(self, root: str, path: str) -> Ran:
        """AC34: no --force, so a dirty worktree stays."""
        return ran(["git", "-C", root, "worktree", "remove", path], LOCAL_TIMEOUT)

    def delete_branch(self, root: str, branch: str) -> Ran:
        """AC34: -d, so an unmerged branch stays."""
        return ran(["git", "-C", root, "branch", "-d", branch], LOCAL_TIMEOUT)

    def delete_remote_branch(self, root: str, branch: str) -> Ran:
        return ran(["git", "-C", root, "push", "origin", "--delete", branch], NETWORK_TIMEOUT)

    def gh_installed(self) -> bool:
        return shutil.which("gh") is not None

    def gh_auth(self) -> Ran:
        return gh("auth", "status", "--hostname", "github.com")

    def pr_list(self, repo: str, branch: str) -> Ran:
        """AC21: the branch's open PRs as JSON [{number, url}]."""
        return gh("pr", "list", "--repo", repo, "--head", branch, "--state", "open", "--json", "number,url")

    def pr_create(self, repo: str, base: str, branch: str, title: str, body: str) -> Ran:
        """AC19: prints the new PR's URL."""
        return gh("pr", "create", "--repo", repo, "--base", base, "--head", branch, "--title", title, "--body", body)

    def pr_view(self, repo: str, number: int) -> Ran:
        return gh("pr", "view", str(number), "--repo", repo, "--json", "number,url,state,statusCheckRollup")

    def pr_merge(self, repo: str, number: int) -> Ran:
        return gh("pr", "merge", str(number), "--repo", repo, MERGE_METHOD)
