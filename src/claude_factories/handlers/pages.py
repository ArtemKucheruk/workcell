"""Page data for the dashboard, workspace, board, task, and review pages (docs/ui.md §8), and the header's
login badge. Each page returns the dict its template gets, minus `request` (036 Q7)."""

import shlex
from itertools import groupby
from time import monotonic
from urllib.parse import quote, urlencode

from .. import config
from ..adapters.claude import Claude, stripped_env
from ..adapters.git import Git
from ..domain.enums import Reviewer, Status
from ..domain.errors import NotFound
from ..lib.diff import diff_rows, file_tree
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TILE_TASKS, TasksRepo
from ..repositories.workspaces import WorkspacesRepo
from .factory import factory_hint, factory_state
from .reviews import commit_hint
from .rounds import find_round, round_summaries
from .tasks import list_tasks

COLUMNS = tuple(Status)
REVIEWERS = tuple(Reviewer)
# Q1: the dashboard's tiles, each the ?show= key of its filtered list
TILES = {
    "backlog": "Backlog", "in_progress": "In progress", "review": "Review", "done": "Done",
    "waiting": "Waiting on me", "escalated": "Escalated", "running": "Running now",
    "done_week": "Done this week", "runs_week": "Runs this week",
}
LOGIN: dict = {}  # 014 Q3: {"at": monotonic(), "value": claude_login()'s answer}; the pages' only state


def claude_login(claude: Claude) -> tuple[str, bool]:
    """docs/ui.md §8, MVP §4.3: the header's login and whether runs are allowed, checked with the runs'
    stripped env from the neutral data dir (Q1), cached 60 s (Q3). Q2: the plan capitalized.
    ponytail: no lock, so two cold renders may both run the check."""
    now = monotonic()
    if LOGIN and now - LOGIN["at"] < 60:
        return LOGIN["value"]
    info = claude.auth_status(str(config.data_dir()), stripped_env())
    if info is None:
        value = ("API key — runs disabled", False)
    else:
        plan = info.get("subscriptionType")
        value = (f"Claude: {plan.capitalize() if isinstance(plan, str) and plan else 'subscription'} ✓", True)
    LOGIN.update(at=now, value=value)
    return value


def dashboard(tasks: TasksRepo, runs: RunsRepo, workspaces: WorkspacesRepo, show: str) -> dict:
    """docs/ui.md §8 item 1. `show` only picks one of the repositories' constant SQL fragments."""
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
        "open_tasks": open_tasks, "done": tasks.done_recently(), "workspaces": workspaces.all(),
    }


def workspace(workspaces: WorkspacesRepo, projects: ProjectsRepo, git: Git, workspace_id: int) -> dict:
    found = workspaces.get(workspace_id)
    if found is None:
        raise NotFound()
    # ponytail: one git call per row; cache if a workspace grows past a few dozen projects
    rows = projects.in_workspace(workspace_id)
    return {"workspace": found,
            "projects": [dict(r, factory=factory_state(git, r["path"], r["default_branch"])) for r in rows]}


def board(projects: ProjectsRepo, tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo,
          workspaces: WorkspacesRepo, git: Git, claude: Claude, project_id: int) -> dict:
    # ponytail: each 3 s poll renders the whole page, one git call included (Q7);
    # add a /projects/{id}/board fragment route if that shows up in profiling
    project = projects.for_board(project_id)
    if project is None:
        raise NotFound()
    listed = [t.model_dump() for t in list_tasks(projects, tasks, rounds, reviews, runs, project_id)]  # 035 Q10
    # Q13: the API doesn't return position; read it after list_tasks so every listed task has one
    positions = {t["id"]: t["position"] for t in tasks.for_project(project_id)}
    # 014: nor the run's start (§6.2 keeps run {id, status}); read after it, so every listed run has one
    started = runs.started_at(project_id)
    columns = {status: [] for status in COLUMNS}
    for t in listed:
        columns[t["status"]].append(t | {"position": positions[t["id"]],
                                         "started_at": t["run"] and started[t["run"]["id"]]})
    factory = factory_state(git, project["path"], project["default_branch"])
    return {
        "project": project, "workspaces": workspaces.all(), "columns": columns, "factory": factory,
        "hint": factory_hint(factory, project["default_branch"]),
        "can_run": factory == "ready" and claude_login(claude)[1],  # Q4: the server's checks still decide
    }


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


def task(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo, git: Git, claude: Claude,
         task_id: int) -> dict:
    """docs/ui.md §8 item 4: header with the run controls and the latest run (014), description, spec,
    rounds with build notes and verdict popovers, the approver's latest decision, the status history,
    the takeover command (Q9), and the run log."""
    found = page_task(tasks, task_id)
    run = runs.latest_detail(task_id)
    factory = factory_state(git, found["path"], found["default_branch"])  # ponytail: a git call per 3 s poll, as the board's
    takeover = None  # Q9: only for a run that isn't running, in the task's stored worktree
    if run and found["worktree_path"] and run["status"] != "running":
        takeover = f"cd {shlex.quote(found['worktree_path'])} && claude --resume {shlex.quote(run['session_id'])}"
    return {
        "run": run, "takeover": takeover, "hint": factory_hint(factory, found["default_branch"]),
        "can_run": factory == "ready" and claude_login(claude)[1],  # Q4
        "task": found, "rounds": summaries(rounds, reviews, task_id), "posted": posted_verdicts(reviews, task_id),
        "build": {r["n"]: r["build_md"] for r in rounds.all(task_id)},
        "reviewers": REVIEWERS, "approver": reviews.approver_latest(task_id),
        "history": [e for e in tasks.timeline(task_id) if e["kind"] == 0],  # Q8: events only
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


def review(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int, n: str, tab: str,
           path: str = "", side: str = "", line: str = "") -> dict:
    """§8.2's Conversation tab, or with `tab=files` §8.3's Files changed for the picked round (008).
    `path`, `side`, and `line` open the inline comment form under that line (008 Q1)."""
    found_task = page_task(tasks, task_id)
    listed = summaries(rounds, reviews, task_id)
    found = None  # AC11: with no rounds, `latest` is a page without a selector, not find_round's 404
    if listed or n != "latest":
        found = find_round(tasks, rounds, task_id, n)
    picked = found["n"] if found else None
    tab = "files" if tab == "files" else "conversation"  # 008 Q4
    files = review_files(rounds, reviews, found["id"], (path, side, line)) if tab == "files" and found else []
    return {
        "task": found_task, "rounds": listed, "selected": next((r for r in listed if r["n"] == picked), None),
        "posted": posted_verdicts(reviews, task_id), "reviewers": REVIEWERS,
        "approver": reviews.approver_latest(task_id), "timeline": tasks.timeline(task_id),
        "tab": tab, "files": files, "tree": file_tree(files),
        # Q6: from the task row, so it survives a reload and also follows fctl approve or a drag to Done
        "commit_hint": commit_hint(found_task) if found_task["status"] == "done" else None,
    }


def comment_url(reviews: ReviewsRepo, task_id: int, comment_id: int) -> str:
    """008 Q3: the Files changed tab of an inline comment's round, at its line's anchor."""
    c = reviews.comment_anchor(comment_id)
    anchor = quote(f"{c['path']}:{c['side']}:{c['line']}")
    return f"/tasks/{task_id}/review?{urlencode({'round': c['n'], 'tab': 'files'})}#{anchor}"
