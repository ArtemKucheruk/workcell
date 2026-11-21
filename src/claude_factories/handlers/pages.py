"""Page data for the dashboard, workspace, board, task, review, and agents pages (docs/ui.md §8), the sidebar
(041), its login badge, the Settings page's Claude accounts (§8 item 9, 056) and run cap (096), and the fctl reference
(§8 item 7). Each page returns the dict controllers/pages_api.py maps onto its dto/pages.py view-model."""

import re
import shlex
import shutil
import subprocess
import tempfile
import time
from contextlib import suppress
from itertools import groupby
from pathlib import Path
from time import monotonic

from .. import config
from ..adapters.claude import Claude, last_line, read, stripped_env
from ..adapters.git import Git
from ..domain.enums import Reviewer, Status
from ..domain.errors import Conflict, Failed, Invalid, NotFound
from ..lib.account_choice import rank
from ..lib.diff import diff_rows, file_tree
from ..lib.markdown import render_with_headings
from ..lib.run_log import run_agents
from ..repositories.claude_accounts import ClaudeAccountsRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.settings import SettingsRepo
from ..repositories.tasks import TILE_TASKS, TasksRepo
from ..repositories.transcripts import TranscriptsRepo
from ..repositories.usage import UsageRepo
from ..repositories.workspaces import WorkspacesRepo
from .factory import factory_files, factory_hint, factory_state
from .factory_import import sync
from .pull_requests import page_pr
from .reviews import commit_hint
from .rounds import find_round, round_summaries
from .runs import log_lines
from .tasks import list_tasks
from .transcripts import for_task
from .usage import accounts_usage, label

COLUMNS = tuple(Status)
REVIEWERS = tuple(Reviewer)
# Q1: the dashboard's tiles, each the ?show= key of its filtered list
TILES = {
    "backlog": "Backlog", "in_progress": "In progress", "review": "Review", "done": "Done",
    "waiting": "Waiting on me", "escalated": "Escalated", "running": "Running now",
    "done_week": "Done this week", "runs_week": "Runs this week",
}
RECENT = 20  # 053: the Agents page's ended runs
LOGIN: dict = {}  # 014 Q3: {"at": monotonic(), "dir": the active config dir it was filled for (056), "value": …}
# 039: the one `claude auth login` waiting for its code, {"proc", "url", "account_id"}.
# ponytail: no lock (Q9): one user, one pending login, and a new login stops the old one first
PENDING: dict = {}
LOGIN_CODE_TIMEOUT = 60  # 039 Q4: seconds for claude to exchange the code and exit
CODE = re.compile(r"[^\s#]+#[^\s#]+")  # 039 Q1: <code>#<state>, as the sign-in page shows it


def reap(proc: subprocess.Popen) -> None:
    """Wait for `proc` (SIGKILL if it outlives SIGTERM by 5 s) and close its pipes."""
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
    with suppress(BrokenPipeError), proc:  # stdin's close may flush a code claude never read
        pass


def pending() -> dict | None:
    """039: the pending login. Once its process has exited it's dropped, with the auth cache, so a login
    finished in claude's own browser tab (Q6) shows at once (AC14)."""
    if PENDING and PENDING["proc"].poll() is not None:
        reap(PENDING.pop("proc"))
        PENDING.clear()
        LOGIN.clear()
    return PENDING or None


def login_stop(claude: Claude) -> None:
    """039: stop the pending login's process group and forget it: before a new login (AC7), after the code
    timeout (AC13), and on shutdown (AC15)."""
    if PENDING:
        claude.stop(PENDING["proc"].pid)
        reap(PENDING.pop("proc"))
        PENDING.clear()


def env(config_dir: str) -> dict:
    """056: the runs' stripped env (MVP §4.3) with the account's CLAUDE_CONFIG_DIR. Every claude call for an
    account takes it, with the neutral data dir as cwd (014 Q1)."""
    return stripped_env() | {"CLAUDE_CONFIG_DIR": config_dir}


def account(accounts: ClaudeAccountsRepo, account_id: int):
    found = accounts.get(account_id)
    if found is None:
        raise NotFound(f"Claude account #{account_id} not found")
    return found


def login_start(claude: Claude, accounts: ClaudeAccountsRepo, account_id: int | None) -> dict:
    """039 Q1: `claude auth login --claudeai` and its sign-in URL. Q5: allowed while runs are active.
    056 Q3: for account `account_id`, in its dir; with none, a new account in a fresh dir under
    FCTL_HOME/claude-accounts/ (0700: it will hold OAuth credentials), whose row is added only once the URL
    has arrived, so no write transaction waits on claude. No URL: the fresh dir goes, and no row is added."""
    if account_id is not None:
        config_dir = account(accounts, account_id)["config_dir"]
    else:
        root = config.data_dir() / "claude-accounts"
        root.mkdir(mode=0o700, exist_ok=True)
        config_dir = tempfile.mkdtemp(dir=root)  # mode 0700
    login_stop(claude)
    try:
        try:
            proc, url, out = claude.login(str(config.data_dir()), env(config_dir))
        except OSError as e:
            raise Failed(f"claude auth login didn't start: {e}") from None
        if url is None:
            claude.stop(proc.pid)
            reap(proc)
            line = last_line(out)
            raise Failed("claude auth login printed no sign-in URL" + (f": {line}" if line else ""))
    except Failed:
        if account_id is None:
            shutil.rmtree(config_dir, ignore_errors=True)
        raise
    if account_id is None:
        account_id = accounts.add(config_dir)
    PENDING.update(proc=proc, url=url, account_id=account_id)
    return {"url": url, "account_id": account_id}


def login_code(claude: Claude, accounts: ClaudeAccountsRepo, code: str, account_id: int | None) -> dict:
    """039 Q1: write `<code>#<state>` to the pending login's stdin, kept open, and wait for claude to exit.
    Exit 0 answers /api/auth afresh; otherwise claude's `Login failed: …` line is the 422's detail (Q4).
    056 Q5: an `account_id` other than the pending login's is a 409, and that login stays pending."""
    found = pending()
    if found is None or account_id is not None and account_id != found["account_id"]:
        raise Conflict("no login in progress")
    code = code.strip()
    if len(code) > 2048 or not CODE.fullmatch(code):  # AC12: claude would only re-prompt; the login stays
        raise Invalid("code must be <code>#<state>, as the sign-in page shows it")
    proc, login_account = found["proc"], found["account_id"]  # pending() below clears `found`
    with suppress(BrokenPipeError):  # it exited just now: its exit code still answers
        proc.stdin.write(code + "\n")
        proc.stdin.flush()
    try:
        returncode = proc.wait(LOGIN_CODE_TIMEOUT)
    except subprocess.TimeoutExpired:
        login_stop(claude)
        raise Failed("claude auth login didn't finish") from None
    out = read(proc.stdout, 2) if returncode else ""  # 2 s: a lingering child may hold the pipe open
    pending()  # drops it and the auth cache
    if returncode:
        raise Invalid(last_line(out) or f"claude auth login exited with code {returncode}")
    signed_in = accounts.get(login_account)
    if signed_in and not signed_in["active"]:  # 095 AC11: the active one's email is stored by auth() below
        checked(claude, accounts, signed_in)
    return auth(claude, accounts)


def status(claude: Claude, config_dir: str) -> dict | None:
    """§4.3: `claude auth status`'s parsed claude.ai answer for the account in `config_dir`, or None."""
    return claude.auth_status(str(config.data_dir()), env(config_dir))


def remember(accounts: ClaudeAccountsRepo, account_id: int, info: dict | None) -> None:
    """095 AC11, Q3: a successful check's email, stored as the account's label. A failed check, or one with no
    email, leaves the stored one. Called after claude has answered, so no write transaction waits on it."""
    if info and isinstance(email := info.get("email"), str) and email:
        accounts.set_email(account_id, email)


def checked(claude: Claude, accounts: ClaudeAccountsRepo, row) -> dict | None:
    """095 AC11: `status` for the account `row`, then `remember`."""
    info = status(claude, row["config_dir"])
    remember(accounts, row["id"], info)
    return info


def auth_status(claude: Claude, accounts: ClaudeAccountsRepo) -> dict | None:
    """MVP §4.3: the active account's status (056), cached 60 s (014 Q3) for the badge and /api/auth alike
    (020 Q3), and only for the dir it was filled for, so a switch never serves the old account. No active
    account: None, without calling claude (056 Q7). A pending login that has exited clears the cache first (039).
    ponytail: no lock, so two cold requests may both run the check."""
    pending()
    found = accounts.active()
    if found is None:
        return None
    now = monotonic()
    if LOGIN.get("dir") != found["config_dir"] or now - LOGIN["at"] >= 60:
        LOGIN.update(at=now, dir=found["config_dir"], value=checked(claude, accounts, found))
    return LOGIN["value"]


def claude_login(claude: Claude, accounts: ClaudeAccountsRepo) -> tuple[str, bool]:
    """docs/ui.md §8: the header's login and whether runs are allowed. 014 Q2: the plan capitalized."""
    info = auth_status(claude, accounts)
    if info is None:
        return "Not signed in — runs disabled", False  # 055 Q1: the sidebar badge's wording
    plan = info.get("subscriptionType")
    return f"Claude: {plan.capitalize() if isinstance(plan, str) and plan else 'subscription'} ✓", True


def described(info: dict | None) -> dict:
    """docs/data-model-and-api.md §6.4's /api/auth body for a status. 020 Q3: a non-claude.ai login's method
    is unknown, so null; `plan` is the raw subscriptionType. 039 Q3: `email` is the claude.ai login's account,
    else null."""
    info = info or {}
    plan, email = info.get("subscriptionType"), info.get("email")
    return {"auth_method": info.get("authMethod"), "plan": plan if isinstance(plan, str) else None,
            "runs_enabled": bool(info), "email": email if isinstance(email, str) else None}


def auth(claude: Claude, accounts: ClaudeAccountsRepo) -> dict:
    """/api/auth: the active account (056)."""
    return described(auth_status(claude, accounts))


def accounts(claude: Claude, accounts: ClaudeAccountsRepo) -> list[dict]:
    """056: every account by id, each checked afresh in its own dir (Q15).
    ponytail: one sequential, uncached `claude auth status` per account per load, since Settings loads the list
    once and never polls; check them in parallel if accounts pile up."""
    found = []
    checks = [(row, status(claude, row["config_dir"])) for row in accounts.all()]
    for row, raw in checks:  # 095 AC11: stored once every check is done, so no write waits on claude
        remember(accounts, row["id"], raw)
        info = described(raw)
        found.append({"id": row["id"], "config_dir": row["config_dir"], "active": bool(row["active"]),
                      "signed_in": info.pop("runs_enabled")} | info)
    return found


def activate(claude: Claude, accounts: ClaudeAccountsRepo, runs: RunsRepo, account_id: int) -> dict:
    """056: make the account the one runs use, and answer /api/auth for it, checked afresh. Q14: a signed-out
    account may be made active. Switching is refused while a run is active (§4.4), changing nothing; the
    already-active account answers 200 even then (§6.4). The check comes before the switch, so no write
    transaction waits on claude, and it refills the auth cache."""
    found = account(accounts, account_id)
    if not found["active"] and runs.any_running():
        raise Conflict("a run is active")
    info = checked(claude, accounts, found)
    if not found["active"]:  # no write when already active, so a stale read can't switch accounts mid-run
        accounts.activate(account_id)
    LOGIN.update(at=monotonic(), dir=found["config_dir"], value=info)
    return described(info)


def delete_account(claude: Claude, accounts: ClaudeAccountsRepo, runs: RunsRepo, account_id: int) -> None:
    """056 (055's logout, per account): refused while a run is active (§4.4), changing nothing. Q12: stops a
    pending login only if it is this account's. `claude auth logout` in the account's dir; 055 Q4: the auth
    cache is cleared either way, since claude may have logged out partway. Q2: the dir is deleted only if the
    app made it, inside FCTL_HOME/claude-accounts/ and not a symlink; already missing is fine. Then the row
    goes, which leaves none active if it was the active one. On any failure the row stays."""
    found = account(accounts, account_id)
    if runs.any_running():
        raise Conflict("a run is active")
    if PENDING.get("account_id") == account_id:
        login_stop(claude)
    config_dir = found["config_dir"]
    try:
        returncode, out = claude.logout(str(config.data_dir()), env(config_dir))
    except OSError as e:
        raise Failed(f"claude auth logout didn't start: {e}") from None
    except subprocess.TimeoutExpired:
        raise Failed("claude auth logout didn't finish") from None
    finally:
        LOGIN.clear()
    if returncode:
        line = last_line(out)
        raise Failed(f"claude auth logout failed: {line}" if line
                     else f"claude auth logout exited with code {returncode}")
    path = Path(config_dir)
    if not path.is_symlink() and (config.data_dir() / "claude-accounts").resolve() in path.resolve().parents:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            raise Failed(f"can't delete {config_dir}: {e.strerror or e}") from None
    accounts.delete(account_id)


def settings(settings: SettingsRepo) -> dict:
    """096 Q2: GET /api/settings."""
    return {"max_concurrent_runs": settings.max_concurrent_runs()}


def put_settings(settings: SettingsRepo, max_concurrent_runs: int) -> dict:
    """096 Q2, Q3: the DTO checked 1–10. Lowering it below the running count stops nothing."""
    settings.set_max_concurrent_runs(max_concurrent_runs)
    return {"max_concurrent_runs": max_concurrent_runs}


def fctl_doc() -> dict:
    """029: the package's fctl.md rendered with heading ids, and its headings for the Contents nav.
    Read on every request, no cache: the file only changes with the install."""
    html, headings = render_with_headings((Path(__file__).parent.parent / "fctl.md").read_text(encoding="utf-8"))
    return {"body_html": html, "headings": headings}


def dashboard(tasks: TasksRepo, runs: RunsRepo, show: str) -> dict:
    """docs/ui.md §8 item 1. `show` only picks one of the repositories' constant SQL fragments; the Needs you
    lists ignore it (045 Q10)."""
    counts = tasks.tile_counts()
    listed = None
    if show == "runs_week":  # Q3
        listed = runs.this_week()
    elif show in TILE_TASKS:  # Q4
        listed = tasks.tile(show)
    else:  # Q7: an unknown key is ignored
        show = ""
    open_tasks = [(ws, list(projects)) for ws, projects in  # Q5
                  groupby(tasks.open_by_project(), lambda r: (r["workspace_id"], r["workspace"]))]
    return {
        "tiles": TILES, "counts": counts, "show": show, "listed": listed,
        "waiting": tasks.needs_you("waiting"), "escalated": tasks.needs_you("escalated"),
        "open_tasks": open_tasks, "done": tasks.done_recently(),
    }


def agents(runs: RunsRepo) -> dict:
    """053, docs/ui.md §8 item 15: every running run with the agents its log names, then the last RECENT ended
    runs. No git, no claude."""
    # ponytail: each 3 s poll reads the running run's whole log, as handlers/runs.log does; keep a byte
    # offset and the parsed agents per run if logs get big
    return {"running": [named(r) | {"agents": run_agents(log_lines(r["log_path"]))} for r in runs.running_rows()],
            "recent": [named(r) for r in runs.recent(RECENT)]}


def named(row) -> dict:
    """102 AC16, AC17, Q9: an Agents row as a dict, a deleted automation's titled `deleted automation`."""
    return dict(row) | ({"title": "deleted automation"} if row["title"] is None else {})


def sidebar(projects: ProjectsRepo, tasks: TasksRepo, transcripts: TranscriptsRepo, task: int | None,
            transcript: int | None, accounts: ClaudeAccountsRepo, usage: UsageRepo) -> dict:
    """041: every workspace with its projects, and `current`: the workspace and project of `task`, or of
    `transcript`'s task. None without either, or for an unknown id (never a 404). No git, no claude.
    095 AC19: `usage`, GET /api/usage's accounts."""
    rows = projects.for_sidebar()
    workspaces = [{"id": ws_id, "name": name, "projects": [r for r in group if r["id"] is not None]}
                  for (ws_id, name), group in groupby(rows, lambda r: (r["workspace_id"], r["workspace"]))]
    if task is None and transcript is not None:
        found = transcripts.get(transcript)
        task = found["task_id"] if found else None
    found = tasks.for_page(task) if task is not None else None
    project_id = found["project_id"] if found else None
    owner = {r["id"]: r["workspace_id"] for r in rows if r["id"] is not None}
    current = {"workspace_id": owner[project_id], "project_id": project_id} if project_id in owner else None
    return {"workspaces": workspaces, "current": current, "usage": accounts_usage(accounts, usage)}


def workspace(workspaces: WorkspacesRepo, projects: ProjectsRepo, git: Git, workspace_id: int) -> dict:
    found = workspaces.get(workspace_id)
    if found is None:
        raise NotFound()
    # ponytail: one git call per row; cache if a workspace grows past a few dozen projects
    rows = projects.in_workspace(workspace_id)
    return {"workspace": found,
            "projects": [dict(r, factory=factory_state(git, r["path"], r["default_branch"])) for r in rows]}


def board(projects: ProjectsRepo, tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo,
          transcripts: TranscriptsRepo, workspaces: WorkspacesRepo, git: Git, claude: Claude,
          accounts: ClaudeAccountsRepo, settings: SettingsRepo, usage: UsageRepo, project_id: int,
          may_sync: bool = True) -> dict:
    """058: syncs factory/ first when board.json or backlog.md changed, so the columns already hold it. With
    `may_sync` False (a cross-site request, §4.5) it only reads the stored error. 096 AC29: the running runs
    across all projects and the cap; at the cap, `can_run` is false. 102 AC19, Q12: for the Workflows page's
    Run now, `runs_enabled` (the active account's claude.ai login) and the task page's `accounts` and `auto`."""
    # ponytail: each 3 s poll renders the whole page, one git call included (Q7);
    # add a /projects/{id}/board fragment route if that shows up in profiling
    project = projects.for_board(project_id)
    if project is None:
        raise NotFound()
    factory_error = (sync(projects, tasks, rounds, reviews, runs, transcripts, git, project_id) if may_sync
                     else projects.factory_sync(project_id)["factory_error"])
    listed = [t.model_dump() for t in list_tasks(projects, tasks, rounds, reviews, runs, project_id)]  # 035 Q10
    # Q13, 042 BE4, 048 Q5: the API returns neither position, branch, nor description_md; read them after
    # list_tasks so every listed task has a row
    rows = {t["id"]: t for t in tasks.for_project(project_id)}
    # 014: nor the run's start (§6.2 keeps run {id, status}); read after it, so every listed run has one
    started = runs.started_at(project_id)
    columns = {status: [] for status in COLUMNS}
    for t in listed:
        row = rows[t["id"]]
        columns[t["status"]].append(t | {"position": row["position"], "branch": row["branch"],
                                         "description_md": row["description_md"],
                                         "started_at": t["run"] and started[t["run"]["id"]]})
    factory = factory_state(git, project["path"], project["default_branch"])
    active, cap = len(runs.running_ids()), settings.max_concurrent_runs()
    logged_in = claude_login(claude, accounts)[1]
    listed, auto = run_menu(accounts, usage, time.time())
    return {
        "project": project, "workspaces": workspaces.all(), "columns": columns, "factory": factory,
        "hint": factory_hint(factory, project["default_branch"]),
        "runs_active": active, "max_concurrent_runs": cap,
        # Q4: the server's checks still decide
        "can_run": factory == "ready" and active < cap and logged_in,
        "runs_enabled": logged_in, "accounts": listed, "auto": auto,
        "factory_error": factory_error, "factory_files": factory_files(project["path"]),  # 059
    }


def run_menu(accounts: ClaudeAccountsRepo, usage: UsageRepo, now: float) -> tuple[list[dict], dict | None]:
    """097 AC26, 102 Q12: the Run menu's (accounts with their windows, Auto's first candidate or None), from the DB
    alone (Q9: no claude call on the poll)."""
    rows, listed = accounts.all(), accounts_usage(accounts, usage, now)
    candidates = rank(rows, usage.latest(), now)[0]
    auto = {"account_id": candidates[0]["id"], "label": label(candidates[0]["email"], candidates[0]["config_dir"])
            } if candidates else None
    return [{k: a[k] for k in ("id", "label", "active", "five_hour", "seven_day")} for a in listed], auto


def summaries(rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int) -> list[dict]:
    """035 Q10: the API's round summaries, as dicts for the pages."""
    return [r.model_dump() for r in round_summaries(rounds, reviews, task_id)]


def posted_verdicts(reviews: ReviewsRepo, task_id: int) -> dict[int, dict]:
    """007 Q5, Q6: round n → {reviewer: verdict row}, for the bodies."""
    posted: dict[int, dict] = {}
    for v in reviews.verdict_bodies(task_id):
        posted.setdefault(v["n"], {})[v["reviewer"]] = v
    return posted


def page_task(tasks: TasksRepo, task_id: int):
    task = tasks.for_page(task_id)
    if task is None:
        raise NotFound(f"Task #{task_id} not found")
    return task


def task(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo, transcripts: TranscriptsRepo,
         git: Git, claude: Claude, accounts: ClaudeAccountsRepo, usage: UsageRepo, task_id: int,
         now: float | None = None) -> dict:
    """docs/ui.md §8 item 4: header with the run controls and the latest run (014), description, 094's Blocked by
    and Blocks, spec, rounds with build notes, verdict popovers, and agents (030), the approver's latest decision,
    the status history, the takeover command (Q9), and the run log. 094 Q8: `project_tasks`, the project's other
    tasks by id, are Add's candidates. 093 AC36: `pr`, Create PR's state from local git. 097 AC26: `accounts` for
    the Run menu and `auto`, Auto's pick from the DB alone (Q9: no claude call on the poll); AC24: `run.account`."""
    found = page_task(tasks, task_id)
    run = runs.latest_detail(task_id)
    factory = factory_state(git, found["path"], found["default_branch"])  # ponytail: a git call per 3 s poll, as the board's
    takeover = None  # Q9: only for a run that isn't running, in the task's stored worktree
    if run and found["worktree_path"] and run["status"] != "running":
        wt, session = shlex.quote(found["worktree_path"]), shlex.quote(run["session_id"])
        # 097 AC22: the run's own account's dir; a run with none (pre-096, or deleted) the active one's (056),
        # or nothing with none active (Q7)
        own = run if run["config_dir"] else accounts.active()
        named = f"CLAUDE_CONFIG_DIR={shlex.quote(own['config_dir'])} " if own else ""
        takeover = (f"docker compose exec -w {wt} {named and f'-e {named}'}backend claude --resume {session}"
                    if config.in_docker() else f"cd {wt} && {named}claude --resume {session}")  # 028 Q7
    listed, auto = run_menu(accounts, usage, time.time() if now is None else now)
    run_out = run and {k: run[k] for k in ("id", "status", "error", "session_id", "started_at")} | {
        "account": label(run["email"], run["config_dir"]) if run["config_dir"] else None}
    return {
        "run": run_out, "takeover": takeover, "hint": factory_hint(factory, found["default_branch"]),
        "accounts": listed, "auto": auto,
        "can_run": factory == "ready" and claude_login(claude, accounts)[1],  # Q4
        "task": found, "pr": page_pr(git, found),
        "rounds": summaries(rounds, reviews, task_id), "posted": posted_verdicts(reviews, task_id),
        "build": {r["n"]: r["build_md"] for r in rounds.all(task_id)},
        "reviewers": REVIEWERS, "approver": reviews.approver_latest(task_id),
        "history": [e for e in tasks.timeline(task_id) if e["kind"] == 0],  # Q8: events only
        "transcripts": [t.model_dump() for t in for_task(tasks, transcripts, task_id)],  # 030 Q11
        "blocked_by": tasks.blockers(task_id), "blocks": tasks.dependents(task_id),
        "project_tasks": sorted((t for t in tasks.for_project(found["project_id"]) if t["id"] != task_id),
                                key=lambda t: t["id"]),
    }


def review_files(rounds: RoundsRepo, reviews: ReviewsRepo, round_id: int, target: tuple[str, str, str]) -> list[dict]:
    """008: the round's files in rowid order, each with its rows, its inline comments placed under
    their line (Q2), the inline form on the row matching `target` (path, side, line) as strings (Q1),
    and the comments whose line isn't in the diff."""
    comments = reviews.inline_comments(round_id)
    at: dict[tuple, list] = {}
    for c in comments:
        at.setdefault((c["path"], c["side"], c["line"]), []).append(c)
    files, formed = [], False
    # ponytail: every row of every file renders (up to 5 MB of patch, slow to draw); collapse files
    # over N lines if big rounds get common
    for f in rounds.files(round_id):
        rows = diff_rows(f["patch"]) or [{"kind": "note", "old": None, "new": None,
                                          "text": "Binary file not shown." if f["binary"] else "No content changes."}]
        for r in rows:
            sides = [(side, r[side]) for side in ("old", "new") if r[side] is not None]
            r["comments"] = sorted(
                (c for side, num in sides for c in at.pop((f["path"], side, num), [])), key=lambda c: c["id"]
            )
            matches = [(side, str(num)) for side, num in sides if (f["path"], side, str(num)) == target]
            r["form"] = matches[0] if matches and not formed else None  # one form, even if anchors repeat
            formed = formed or bool(matches)
        name = f["path"].rpartition("/")[2]
        files.append(dict(f) | {
            "rows": rows, "lang": name.rpartition(".")[2].lower() if "." in name else None,
            # still in `at` = no row took it: its line isn't in the diff
            "orphans": [c for c in comments if c["path"] == f["path"] and (c["path"], c["side"], c["line"]) in at],
        })
    return files


def review(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, git: Git, task_id: int, n: str, tab: str,
           path: str = "", side: str = "", line: str = "") -> dict:
    """§8.2's Conversation tab, or with `tab=files` §8.3's Files changed for the picked round (008).
    `path`, `side`, and `line` open the inline comment form under that line (008 Q1). 093 AC36: `pr`."""
    found_task = page_task(tasks, task_id)
    listed = summaries(rounds, reviews, task_id)
    found = None  # AC11: with no rounds, `latest` is a page without a selector, not find_round's 404
    if listed or n != "latest":
        found = find_round(tasks, rounds, task_id, n)
    picked = found["n"] if found else None
    tab = "files" if tab == "files" else "conversation"  # 008 Q4
    files = review_files(rounds, reviews, found["id"], (path, side, line)) if tab == "files" and found else []
    return {
        "task": found_task, "pr": page_pr(git, found_task), "rounds": listed, "selected": next((r for r in listed if r["n"] == picked), None),
        "posted": posted_verdicts(reviews, task_id), "reviewers": REVIEWERS,
        "approver": reviews.approver_latest(task_id), "timeline": tasks.timeline(task_id),
        "tab": tab, "files": files, "tree": file_tree(files),
        # Q6: from the task row, so it survives a reload and also follows fctl approve or a drag to Done
        "commit_hint": commit_hint(found_task) if found_task["status"] == "done" else None,
    }

