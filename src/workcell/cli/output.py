import sys


def fail(message: str):
    print(f"fctl: {message}", file=sys.stderr)
    raise SystemExit(1)


def print_run(task_id: int, started: dict):
    """Q9: the task page, where the run log shows. 097 AC32: and the account the run reply names."""
    from .client import base_url  # ponytail: lazy, since client imports fail() from here; no cycle at import time

    account = f" as {started['account']}" if started.get("account") else ""
    print(f"Run #{started['run_id']} on #{task_id}{account} → {base_url()}/tasks/{task_id}")


def print_automation_run(factory_id: int, started: dict):
    """102 Q18: an automation run has no task page yet, so the Agents page, and the run's own worktree."""
    from .client import base_url  # lazy, as in print_run

    account = f" as {started['account']}" if started.get("account") else ""
    print(f"Run #{started['run_id']} of automation #{factory_id}{account} in {started['worktree']}"
          f" → {base_url()}/agents")


def stdin_text() -> str:
    """Q9: a heredoc or a pipe, sent unchanged; nothing from a terminal, so a hand-typed command
    doesn't wait for Ctrl-D."""
    return "" if sys.stdin.isatty() else sys.stdin.read()


def summary(r: dict) -> str:
    files = f"{r['files_changed']} file" + ("" if r["files_changed"] == 1 else "s")
    return f"{files}, +{r['additions']} −{r['deletions']} → {r['url']}"
