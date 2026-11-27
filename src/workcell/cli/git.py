import os
import subprocess
import tempfile

from .output import fail


def git(*args: str) -> str | None:
    """Run git; its stripped stdout, or None if it fails."""
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main_checkout() -> str:
    """docs/claude-code.md §7.4 step 1: the main checkout, also from a worktree or a subdirectory."""
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and os.path.basename(common) == ".git":
        root = os.path.dirname(common)
    else:  # a bare repo or a separate git dir
        root = common and git("rev-parse", "--show-toplevel")
    if not root:
        fail(f"not inside a git repository: {os.getcwd()}")
    return os.path.realpath(root)


def default_branch(main: str) -> str:
    """origin/HEAD, else the main checkout's current branch (not the worktree's)."""
    ref = git("-C", main, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    branch = ref.removeprefix("origin/") if ref else git("-C", main, "branch", "--show-current")
    if not branch:
        fail("can't tell the default branch: no origin/HEAD and HEAD is detached")
    return branch


def capture() -> tuple[str, str]:
    """docs/claude-code.md §7.4 step 2: HEAD and the patch of the cwd's tracked and untracked
    changes, via a temp index so the real one is untouched. The diff flags pin the format the
    server parses against user config, and the output is read as bytes: text=True would turn
    \\r\\n into \\n (Q8)."""
    base_sha = git("rev-parse", "--verify", "-q", "HEAD^{commit}")
    if not base_sha:
        fail("HEAD has no commit yet; commit once before submitting")
    # ponytail: read-tree leaves no stat data, so add -A rehashes every file; seed the temp index
    # from a copy of the real one if big repos get slow
    steps = (
        ["read-tree", base_sha],
        ["add", "-A"],  # respects .gitignore
        ["diff", "--cached", "-M", "--no-color", "--no-ext-diff", "--no-textconv", "--no-relative",
         "--src-prefix=a/", "--dst-prefix=b/", base_sha],
    )
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ | {"GIT_INDEX_FILE": os.path.join(tmp, "index")}
        for step in steps:
            r = subprocess.run(["git", "-c", "core.quotePath=false", *step], capture_output=True, env=env)
            if r.returncode:
                fail(f"git {step[0]} failed: {r.stderr.decode(errors='replace').strip()}")
    return base_sha, r.stdout.decode(errors="replace")
