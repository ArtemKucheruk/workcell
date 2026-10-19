"""Runs: start, run next, stop, the log, the exit, startup cleanup, and stopping every run on shutdown
(docs/data-model-and-api.md §6.2, docs/MVP.md §4.1, §4.3, §4.4).

036 Q1: a run commits before its spawn and records its exit after the request has ended, so these take
`tx`, server/deps.py's transaction(), and open one transaction per step."""

import os
import sqlite3
import threading
import uuid
from itertools import takewhile
from pathlib import Path

from .. import config
from ..adapters.claude import Claude, stripped_env
from ..adapters.git import Git
from ..domain.errors import Conflict, DomainError, Failed, NotFound
from ..dto.runs import LogOut, RunNextOut, RunStarted, StopOut
from ..lib.run_log import last_result, log_items
from ..lib.slug import slug
from ..repositories.projects import ProjectsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from .factory import factory_hint, factory_state
from .transcripts import collect

PROMPT = "/factory {task_id}"  # MVP §10 OQ1: the one place the prompt lives
ALLOWED_TOOLS = (  # §4.4; the test command's entry is added per project (Q7)
    "Bash(fctl show *)", "Bash(fctl diff *)", "Bash(fctl spec *)", "Bash(fctl submit *)",
    "Bash(fctl verdict *)", "Bash(fctl comment *)", "Bash(fctl decide *)", "Bash(fctl stage *)",
    "Bash(fctl round *)", "Bash(git status *)", "Bash(git diff *)",
)
DISALLOWED_TOOLS = (
    "Bash(git commit *)", "Bash(git push *)", "Bash(git merge *)", "Bash(git rebase *)",
    "Bash(git reset *)", "Bash(git checkout *)",
)
EXCLUDE_LINE = b".claude/worktrees/"


def refuse_if_running(runs: RunsRepo):
    """§4.4: one run at a time, across all projects."""
    if run := runs.any_running():
        raise Conflict(f"run #{run[0]} active")


def worktree(tx, git: Git, task) -> str:
    """Q5: the exclude line, then Q4: the stored worktree, or a new one from the default branch, stored
    right away so an auth refusal leaves it for the next run."""
    path = task["path"]
    exclude = Path(git.exclude_path(path))
    exclude.parent.mkdir(parents=True, exist_ok=True)
    old = exclude.read_bytes() if exclude.exists() else b""
    if EXCLUDE_LINE not in old.splitlines():
        with exclude.open("ab") as f:
            f.write((b"\n" if old and not old.endswith(b"\n") else b"") + EXCLUDE_LINE + b"\n")
    if task["worktree_path"]:  # reused as stored, even if the title changed since
        if not os.path.isdir(task["worktree_path"]):
            raise Conflict(f"worktree {task['worktree_path']} is missing")
        return task["worktree_path"]
    name = f"{task['id']}-{slug(task['title'])}"
    branch, wt = f"factory/{name}", os.path.join(path, ".claude", "worktrees", name)
    if error := git.add_worktree(path, branch, wt, task["default_branch"]):
        raise Conflict(f"git worktree add failed: {error}")
    with tx() as conn:
        TasksRepo(conn).set_worktree(task["id"], branch, wt)
    return wt


def start(tx, git: Git, claude: Claude, task_id: int, base_url: str) -> RunStarted:
    """Q2's order: 404, run active, status (Q1), factory (Q12), worktree (Q4), auth; then the run row,
    the move, and the event in one transaction, then the spawn (§4.4). `base_url` becomes FCTL_URL: the
    controller's loopback URL on the server's own port (028 Q5)."""
    with tx() as conn:
        task = TasksRepo(conn).for_run(task_id)
    if task is None:
        raise NotFound(f"no task #{task_id}")
    with tx() as conn:
        refuse_if_running(RunsRepo(conn))
    if task["status"] in ("review", "done"):
        raise Conflict(f"#{task_id} is {'in review' if task['status'] == 'review' else 'done'}")
    branch = task["default_branch"]
    if hint := factory_hint(factory_state(git, task["path"], branch), branch):
        raise Conflict(hint)
    wt = worktree(tx, git, task)
    env = stripped_env() | {"FCTL_URL": base_url.rstrip("/")}  # §4.3, passed to both exactly as built
    if claude.auth_status(wt, env) is None:  # each run's own check, never cached (§4.3: before every run)
        raise Conflict("not on subscription auth")
    session_id = str(uuid.uuid4())
    test_words = list(takewhile(lambda w: not w.startswith("-"), (task["test_cmd"] or "").split()))  # Q7
    allowed = ALLOWED_TOOLS + ((f"Bash({' '.join(test_words)} *)",) if test_words else ())
    args = ["-p", PROMPT.format(task_id=task_id), "--session-id", session_id,
            "--output-format", "stream-json", "--verbose", "--forward-subagent-text",
            "--permission-mode", "acceptEdits", "--permission-prompts", "none",
            "--allowedTools", *allowed, "--disallowedTools", *DISALLOWED_TOOLS]
    runs_dir = config.data_dir() / "runs"
    runs_dir.mkdir(exist_ok=True)
    with tx() as conn:
        tasks, runs = TasksRepo(conn), RunsRepo(conn)
        now = tasks.lock()
        refuse_if_running(runs)
        try:
            run_id = runs.add(task_id, session_id, now)
        except sqlite3.IntegrityError:  # one_active_run
            refuse_if_running(runs)
            raise
        log_path = runs_dir / f"{run_id}.jsonl"
        runs.set_log_path(run_id, str(log_path))
        if tasks.start(task_id, now):  # Q9: an in_progress task keeps its status and stage
            tasks.add_event(task_id, "app", "backlog", "in_progress", None, now)
    try:
        proc = claude.spawn(args, wt, env, str(log_path))
    except OSError as e:  # Q11: a running row with no process would block every run
        error = f"can't start claude: {e}"
        with tx() as conn:
            RunsRepo(conn).fail(run_id, error)
        raise Failed(error)
    with tx() as conn:
        RunsRepo(conn).set_pid(run_id, proc.pid)
    threading.Thread(target=finish, args=(tx, run_id, proc, log_path), daemon=True).start()
    return RunStarted(run_id=run_id, session_id=session_id, worktree=os.path.relpath(wt, task["path"]))


def finish(tx, run_id: int, proc, log_path: Path):
    """Q10: on exit, the exit code and the log's last `result` event decide the run row. The task
    is never touched (§3.4 step 8). 013 Q1: a row Stop already ended gets only its exit code."""
    code = proc.wait()
    with tx() as conn:  # at once, so Stop never signals a reaped pgid (013 security)
        RunsRepo(conn).set_exit_code(run_id, code)
    with log_path.open(errors="replace") as log:
        event = last_result(log)
    is_error = bool(event and event.get("is_error"))
    if code == 0 and event and not is_error:
        status, error = "succeeded", None
    else:
        status = "failed"
        error = str(event.get("result")) if is_error else f"exit code {code}" if code else "no result event"
    session = event.get("session_id") if event and isinstance(event.get("session_id"), str) else None
    with tx() as conn:
        RunsRepo(conn).finish(run_id, status, error, session)
    collect(tx, run_id)  # 030 Q7: again after Stop's copy, now that the session has ended


def run_next(tx, git: Git, claude: Claude, project_id: int, base_url: str) -> RunNextOut:
    """Q13: the top backlog card, lowest position then lowest id, through all of start's checks."""
    with tx() as conn:
        if not ProjectsRepo(conn).exists(project_id):
            raise NotFound()
        top = TasksRepo(conn).top_backlog(project_id)
    if top is None:
        raise NotFound("backlog is empty")
    return RunNextOut(task_id=top, run_id=start(tx, git, claude, top, base_url).run_id)


def stop(tx, claude: Claude, run_id: int) -> StopOut:
    """013 Q1, Q2: mark the row stopped first, so the exit thread can't record `failed`, then SIGTERM
    the run's process group (§4.4). The pid is only ever one the app stored for its own spawn."""
    with tx() as conn:
        found = RunsRepo(conn).stop(run_id)
    if not found:
        with tx() as conn:
            if not RunsRepo(conn).exists(run_id):
                raise NotFound(f"run #{run_id} not found")
        raise Conflict(f"run #{run_id} is not running")
    pid, exit_code = found
    # ponytail: a Stop in the ms between the runs insert and the pid update marks the row without
    # signalling; the run then finishes unstopped. Store the pid before the insert commits if that bites.
    if pid and exit_code is None:  # an exit code means the leader was reaped: its pgid may be reused
        claude.stop(pid)
    collect(tx, run_id)  # 030 Q7: at once, since a shutdown's exit thread may die before it copies
    return StopOut(id=run_id, status="stopped")


def log(tx, run_id: int, after: int) -> LogOut:
    """013 Q6: `after` and `next` count complete lines; a trailing partial line waits for its newline.
    Q9: no log file yet is an empty page, never an error."""
    with tx() as conn:
        path = RunsRepo(conn).log_path(run_id)
    if path is None:
        raise NotFound(f"run #{run_id} not found")
    try:  # ponytail: the whole file per poll; keep a byte offset per cursor if logs get big
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            lines = f.read().split("\n")[:-1]
    except OSError:
        return LogOut(next=0, lines=[])
    return LogOut(next=len(lines), lines=log_items(lines, after))


def fail_leftovers(tx):
    """013 Q5: at startup, a crash left these running; no signal, since the pid may be reused."""
    with tx() as conn:
        failed = RunsRepo(conn).fail_running("app restarted")
    for run_id in failed:  # 030: the copy their exit thread never made
        collect(tx, run_id)


def stop_all(tx, claude: Claude):
    """013 Q4: stopping serve stops every run."""
    with tx() as conn:
        running = RunsRepo(conn).running_ids()
    for run_id in running:
        try:
            stop(tx, claude, run_id)
        except DomainError:  # it ended in between
            pass
