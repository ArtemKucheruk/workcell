"""Runs: start, run next, stop, the log, the exit, startup cleanup, and stopping every run on shutdown
(docs/data-model-and-api.md §6.2, docs/MVP.md §4.1, §4.3, §4.4).

036 Q1: a run commits before its spawn and records its exit after the request has ended, so these take
`tx`, server/deps.py's transaction(), and open one transaction per step."""

import json
import os
import socket
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
from ..lib.rate_limits import latest
from ..lib.run_log import last_result, log_items
from ..lib.slug import slug
from ..repositories.claude_accounts import ClaudeAccountsRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.runs import RunsRepo
from ..repositories.settings import SettingsRepo
from ..repositories.tasks import TasksRepo
from ..repositories.usage import UsageRepo
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
# .fctl/: the text agents write for fctl's stdin, since a run can't approve a Bash command over ~10,000 chars
EXCLUDE_LINES = (b".claude/worktrees/", b".fctl/")
# 096 Q7: parallel starts take turns on the main checkout (info/exclude, .git/index.lock, worktrees/) and on
# the account's .claude.json (its shared .fctl-tmp). ponytail: global, so starts in different repos also wait;
# per-repo locks if that bites. wt_copy_ignored (up to 300 s) stays outside it.
CHECKOUT_LOCK = threading.Lock()


def command_parts(cmd: str) -> list[list[str]]:
    """092: `cmd` split on `&&`, `||`, `;`, `|` outside quotes, each part as its words as written (quotes
    kept, Q4). Empty parts are dropped (AC9). ponytail: `&`, redirections, subshells, and `$( )` aren't
    parsed (spec: out of scope)."""
    parts, words, word, quote, i = [], [], "", None, 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            word += c
            if c == "\\" and quote == '"' and i + 1 < len(cmd):
                word, i = word + cmd[i + 1], i + 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            word, quote = word + c, c
        elif c == "\\" and i + 1 < len(cmd):
            word, i = word + c + cmd[i + 1], i + 1
        elif c.isspace() or c in ";|" or cmd.startswith("&&", i):
            words += [word] if word else []
            word = ""
            if not c.isspace():
                parts += [words] if words else []
                words = []
                i += cmd.startswith(("&&", "||"), i)
        else:
            word += c
        i += 1
    words += [word] if word else []
    return parts + ([words] if words else [])


def test_rules(cmd: str) -> tuple[str, ...]:
    """012 Q7, 092: one `Bash(<words> *)` rule per part of the test command, deduplicated in order
    (Claude Code checks each part of a chain on its own). The words are those before the first flag, but
    when that leaves only the program and the flag is followed by 2+ non-flag words (a value, then a
    subcommand: `npm --prefix frontend ci`), they run through those words, so a rule is never `Bash(npm *)`
    for a subcommand. A `--flag=value` first flag holds its own value, so 1+ word is enough there
    (`npm --prefix=frontend ci` → `Bash(npm --prefix=frontend ci *)`, round 1 security). 092 Q2 ponytail:
    flag arity is unknown, so one word after the flag is taken as its value (`pytest -k "a && b"` stays
    `Bash(pytest *)`, AC6) and `npm -s test` still gets `Bash(npm *)`."""
    rules = {}
    for words in command_parts(cmd):
        prefix = list(takewhile(lambda w: not w.startswith("-"), words))
        if len(prefix) == 1 and len(words) > 1:
            rest = list(takewhile(lambda w: not w.startswith("-"), words[2:]))
            if len(rest) >= (1 if "=" in words[1] else 2):  # `--prefix=frontend` holds its own value
                prefix = words[:2 + len(rest)]
        if prefix:
            rules.setdefault(f"Bash({' '.join(prefix)} *)", None)
    return tuple(rules)


def open_blockers(tasks: TasksRepo, task_id: int) -> str:
    """094: the task's blockers that aren't done, as `#12, #14` by id; "" when it's ready."""
    return ", ".join(f"#{b['id']}" for b in tasks.blockers(task_id) if b["status"] != "done")


def refuse_if_running(runs: RunsRepo, settings: SettingsRepo, task_id: int):
    """096, §4.4: the task's own running run first (Q1), then the global cap, max_concurrent_runs. Each detail
    names the runs in the way and the fix. Start and Request changes share it (Q4)."""
    if run := runs.running(task_id):
        raise Conflict(f"run #{run['id']} is already running on #{task_id}; wait for it or stop it")
    active, cap = runs.running_tasks(), settings.max_concurrent_runs()
    if len(active) >= cap:  # Q3: a lowered cap stops nothing; new starts wait until the count drops under it
        listed = ", ".join(f"#{r['id']} on #{r['task_id']}" for r in active)
        raise Conflict(f"{len(active)} run{'' if len(active) == 1 else 's'} active ({listed}); the limit is {cap}."
                       " Wait, stop one, or raise it in Settings")


def free_ports() -> tuple[int, int]:
    """096 Q6: two free loopback ports, for FCTL_BACKEND_PORT and FCTL_FRONTEND_PORT. Both sockets stay open
    until both are read, so they differ. ponytail: a port can be taken between the pick and its use; reserve
    ports if that bites."""
    with socket.socket() as a, socket.socket() as b:
        a.bind(("127.0.0.1", 0))
        b.bind(("127.0.0.1", 0))
        return a.getsockname()[1], b.getsockname()[1]


def exclude_worktrees(git: Git, repo: str) -> None:
    """Q5, MVP §10 assumption 4: `.claude/worktrees/` and `.fctl/` in the repo's info/exclude, each added once."""
    exclude = Path(git.exclude_path(repo))
    exclude.parent.mkdir(parents=True, exist_ok=True)
    old = exclude.read_bytes() if exclude.exists() else b""
    if new := [line + b"\n" for line in EXCLUDE_LINES if line not in old.splitlines()]:
        with exclude.open("ab") as f:
            f.write((b"\n" if old and not old.endswith(b"\n") else b"") + b"".join(new))


def trust_project(config_dir: str, repo: str) -> None:
    """A run is headless, so nobody answers Claude Code's trust dialog, and an untrusted repo's
    .claude/settings.json allow rules are ignored. Connecting the repo is the consent, so the run's account
    trusts it. Written only when missing; an unreadable .claude.json is left alone. ponytail: a claude
    process writing the same file between the read and the replace loses its write; a lock if that bites."""
    path = Path(config_dir) / ".claude.json"
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        data = {}
    except ValueError:
        return
    project = data.setdefault("projects", {}).setdefault(repo, {})
    if project.get("hasTrustDialogAccepted") is True:
        return
    project["hasTrustDialogAccepted"] = True
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(".claude.json.fctl-tmp")
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def worktree(tx, git: Git, task) -> str:
    """Q5: the exclude line, then Q4: the stored worktree, or a new one from the default branch made by
    worktrunk (099 AC1), stored right away so a refusal after it leaves it for the next run (099 AC5). Then,
    new or reused, the main checkout's ignored files copied in, minus any the default branch doesn't ignore
    (099 AC2, AC3, round 1 security finding 2). 096 Q7: the exclude write and wt_create hold CHECKOUT_LOCK."""
    path = task["path"]
    with CHECKOUT_LOCK:
        exclude_worktrees(git, path)
    if task["worktree_path"]:  # reused as stored, even if the title changed since
        if not os.path.isdir(task["worktree_path"]):
            raise Conflict(f"worktree {task['worktree_path']} is missing")
        wt = task["worktree_path"]
    else:
        name = f"{task['id']}-{slug(task['title'])}"
        branch = f"factory/{name}"
        with CHECKOUT_LOCK:
            wt = git.wt_create(path, branch, os.path.join(path, ".claude", "worktrees", name),
                               task["default_branch"])
        with tx() as conn:
            TasksRepo(conn).set_worktree(task["id"], branch, wt)
    git.wt_copy_ignored(wt, task["default_branch"])
    return wt


def start(tx, git: Git, claude: Claude, task_id: int, base_url: str) -> RunStarted:
    """Q2's order: 404, the task's own run and the cap (096 Q1), status (Q1), blockers (094), factory (Q12),
    worktree (Q4), auth; then the run row, the move, and the event in one transaction, then the spawn (§4.4).
    `base_url` becomes FCTL_URL: the controller's loopback URL on the server's own port (028 Q5). 056: the auth
    check and the spawn run in the active account's CLAUDE_CONFIG_DIR; with none active, the run is refused
    without calling claude (Q7). 096: the row keeps that account's id (Q5), and the env two free ports (Q6).
    094 Q1, Q4: a blocked task is refused outright, for Run, Retry, Run next, and rework's run alike."""
    with tx() as conn:
        task = TasksRepo(conn).for_run(task_id)
    if task is None:
        raise NotFound(f"no task #{task_id}")
    with tx() as conn:
        refuse_if_running(RunsRepo(conn), SettingsRepo(conn), task_id)
    if task["status"] in ("review", "done"):
        raise Conflict(f"#{task_id} is {'in review' if task['status'] == 'review' else 'done'}")
    with tx() as conn:
        waits_on = open_blockers(TasksRepo(conn), task_id)
    if waits_on:
        raise Conflict(f"#{task_id} is blocked by {waits_on}; finish those first or remove the dependency")
    branch = task["default_branch"]
    if hint := factory_hint(factory_state(git, task["path"], branch), branch):
        raise Conflict(hint)
    wt = worktree(tx, git, task)
    # 096 Q5: the run keeps this account (runs.account_id), whichever is made active later
    with tx() as conn:
        account = ClaudeAccountsRepo(conn).active()
    if account is None:
        raise Conflict("not on subscription auth")
    backend_port, frontend_port = free_ports()
    env = stripped_env() | {"FCTL_URL": base_url.rstrip("/"),  # §4.3, passed to both exactly as built
                            "CLAUDE_CONFIG_DIR": account["config_dir"],
                            "FCTL_BACKEND_PORT": str(backend_port), "FCTL_FRONTEND_PORT": str(frontend_port)}
    if claude.auth_status(wt, env) is None:  # each run's own check, never cached (§4.3: before every run)
        raise Conflict("not on subscription auth")
    with CHECKOUT_LOCK:
        trust_project(account["config_dir"], task["path"])
    session_id = str(uuid.uuid4())
    allowed = ALLOWED_TOOLS + test_rules(task["test_cmd"] or "")
    args = ["-p", PROMPT.format(task_id=task_id), "--session-id", session_id,
            "--output-format", "stream-json", "--verbose", "--forward-subagent-text",
            "--permission-mode", "acceptEdits", "--permission-prompts", "none",
            "--allowedTools", *allowed, "--disallowedTools", *DISALLOWED_TOOLS]
    runs_dir = config.data_dir() / "runs"
    runs_dir.mkdir(exist_ok=True)
    with tx() as conn:
        tasks, runs, settings = TasksRepo(conn), RunsRepo(conn), SettingsRepo(conn)
        now = tasks.lock()
        refuse_if_running(runs, settings, task_id)  # 096 Q1: again under the write lock, so parallel starts count
        try:
            run_id = runs.add(task_id, session_id, now, account["id"])
        except sqlite3.IntegrityError:  # one_run_per_task
            refuse_if_running(runs, settings, task_id)
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
    record_usage(tx, run_id, str(log_path))
    collect(tx, run_id)  # 030 Q7: again after Stop's copy, now that the session has ended


def record_usage(tx, run_id: int, log_path: str) -> None:
    """095 AC6, AC7: the log's latest rate-limit snapshot, on the run's own account; nothing when the log has no
    valid event or the run has no account. Q1 ponytail: read once the run has ended, so a long run's limits only
    show after it; a log tailer if that bites."""
    if snap := latest(log_lines(log_path)):
        with tx() as conn:
            UsageRepo(conn).record(run_id, snap)


def run_next(tx, git: Git, claude: Claude, project_id: int, base_url: str) -> RunNextOut:
    """Q13: the top backlog card, lowest position then lowest id, through all of start's checks. 094: the top
    ready one; with every card blocked, a 409 naming the top card's open blockers (Q5). 096 Q10: a card with a
    running run is skipped; start's checks refuse it at the cap (AC17)."""
    with tx() as conn:
        if not ProjectsRepo(conn).exists(project_id):
            raise NotFound()
        tasks = TasksRepo(conn)
        top = tasks.top_backlog(project_id)
        if top is not None and not top["ready"]:
            raise Conflict(f"all backlog tasks are blocked: #{top['id']} waits on {open_blockers(tasks, top['id'])}")
    if top is None:
        raise NotFound("backlog is empty")
    return RunNextOut(task_id=top["id"], run_id=start(tx, git, claude, top["id"], base_url).run_id)


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


def log_lines(path: str) -> list[str]:
    """013 Q6: the log's complete lines; a trailing partial line waits for its newline. Q9, 053 Q3: no
    readable file is no lines."""
    try:  # ponytail: the whole file per poll; keep a byte offset per cursor if logs get big
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            return f.read().split("\n")[:-1]
    except OSError:
        return []


def log(tx, run_id: int, after: int) -> LogOut:
    """013 Q6: `after` and `next` count complete lines. Q9: no log file yet is an empty page, never an error."""
    with tx() as conn:
        path = RunsRepo(conn).log_path(run_id)
    if path is None:
        raise NotFound(f"run #{run_id} not found")
    lines = log_lines(path)
    return LogOut(next=len(lines), lines=log_items(lines, after))


def fail_leftovers(tx):
    """013 Q5: at startup, a crash left these running; no signal, since the pid may be reused."""
    with tx() as conn:
        failed = RunsRepo(conn).fail_running("app restarted")
    for run_id, path in failed:  # 030: the copy their exit thread never made; 095 AC8: and the usage snapshot
        record_usage(tx, run_id, path)
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
