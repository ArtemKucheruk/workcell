"""Verdicts, comments, and the approver's decision (docs/data-model-and-api.md §6.3), my approve and
request changes (docs/MVP.md §3.6, §3.7), and the context markdown (§6.2). Only my decisions touch the
task row or write events (docs/claude-code.md §7.5)."""

import os
import shlex

from ..domain.enums import Reviewer, Stage, Status
from ..domain.errors import Conflict, Invalid, NotFound
from ..dto.reviews import (ApproveBody, ApproveOut, ChangesBody, CommentBody, DecisionBody, IdOut, VerdictBody,
                           VerdictOut)
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from .rounds import find_round

REVIEWERS = tuple(Reviewer)


def put_verdict(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int, n: str, reviewer: str,
                body: VerdictBody) -> VerdictOut:
    """006 Q2: one row per (round, reviewer); posting again replaces verdict, body, and created_at."""
    found = find_round(tasks, rounds, task_id, n)
    done = reviews.put_verdict(found["id"], reviewer, body.verdict, body.body_md)
    return VerdictOut(round=found["n"], reviewer=reviewer, verdict=body.verdict, complete=f"{done}/{len(REVIEWERS)}")


def post_comment(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int,
                 body: CommentBody) -> IdOut:
    """006 Q3: inline (path and line, side defaulting to new) or conversation (all three NULL)."""
    if (body.path is None) != (body.line is None):
        raise Invalid("path and line go together")
    if body.side is not None and body.path is None:
        raise Invalid("side needs a path")
    if not body.body_md.strip():
        raise Invalid("body_md must not be blank")
    found = find_round(tasks, rounds, task_id, str(body.round))
    if body.path is not None and not rounds.has_file(found["id"], body.path):
        raise Invalid(f"{body.path} is not in round {found['n']}")
    side = None if body.path is None else body.side or "new"
    return IdOut(id=reviews.add_comment(task_id, found["id"], body.author, body.path, body.line, side, body.body_md))


def post_decision(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int,
                  body: DecisionBody) -> IdOut:
    """006 Q4: the approver's decision on the latest round. Every POST adds a row; readers take the latest."""
    found = find_round(tasks, rounds, task_id, "latest")
    return IdOut(id=reviews.add_decision(task_id, found["id"], "approver", body.decision, body.body_md))


def commit_hint(task) -> str:
    """009 Q4, Q5: §3.7's commands for me to run, every value shell-quoted. A standalone task (no branch or
    worktree) gets the commit line alone. `task` has title, branch, worktree_path, and path."""
    commit = f"git add -A && git commit -m {shlex.quote(task['title'])}"
    if not (task["branch"] and task["worktree_path"]):
        return commit
    wt, root = task["worktree_path"], task["path"]
    return "\n".join([
        f"cd {shlex.quote(wt)}",
        commit,
        f"git push -u origin {shlex.quote(task['branch'])}     # then open a PR, or merge locally",
        f"cd {shlex.quote(root)} && git worktree remove {shlex.quote(os.path.relpath(wt, root))}",
    ])


def locked_task(tasks: TasksRepo, task_id: int):
    """Q4: the write lock first, so the checks and the writes commit together and a double click can't
    act twice. (now, the task row with its project's path)."""
    now = tasks.lock()
    task = tasks.get(task_id)
    if task is None:
        raise NotFound()
    return now, task


def decide(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task, now: str, decision: str, body_md: str,
           status: str, stage: str | None) -> None:
    """009 Q2, Q3, Q10: refuse unless in review with a round, then my decision on the latest round, the
    move (position kept, Q8), and the event (actor me, Q7). Inside locked_task's lock."""
    task_id = task["id"]
    if task["status"] != Status.REVIEW:
        raise Conflict(f"#{task_id} is not in review")
    latest = rounds.latest(task_id)
    if latest is None:
        raise NotFound(f"#{task_id} has no rounds")
    reviews.add_decision(task_id, latest["id"], "me", decision, body_md, now)
    tasks.move(task_id, status, stage, now if status == Status.DONE else None, now)
    tasks.add_event(task_id, "me", Status.REVIEW, status, stage, now)


def approve(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int, body: ApproveBody) -> ApproveOut:
    """§3.7: my APPROVE → done, and the commands I run myself. The app never runs git."""
    now, task = locked_task(tasks, task_id)
    decide(tasks, rounds, reviews, task, now, "APPROVE", body.body_md, Status.DONE, None)
    return ApproveOut(status=Status.DONE, commit_hint=commit_hint(task))


def request_changes(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo, task_id: int,
                    body: ChangesBody) -> bool:
    """§3.6: my CHANGES_REQUESTED → in_progress · rework (009 Q1: standalone too). 013 Q12: a factory task
    is refused while any run is active, before any write. Returns whether it is a factory task, whose
    rework run app.py spawns once this commits (035 Q1)."""
    if not body.body_md.strip():
        raise Invalid("body_md must not be blank")
    now, task = locked_task(tasks, task_id)
    factory = bool(task["branch"] and task["worktree_path"])
    if factory and (run := runs.any_running()):
        raise Conflict(f"run #{run['id']} active")
    decide(tasks, rounds, reviews, task, now, "CHANGES_REQUESTED", body.body_md, Status.IN_PROGRESS, Stage.REWORK)
    return factory


def context_md(reviews: ReviewsRepo, task, found: list, feedback=None) -> str:
    """006 Q5, Q6: the task as markdown blocks joined by one blank line. A block is a heading, then its
    body with trailing whitespace stripped, unless the body is blank. Agent text passes through as is."""
    blocks = []

    def add(heading: str, body: str | None = None):
        blocks.append(heading + (f"\n{body.rstrip()}" if body and body.strip() else ""))

    def add_comments(round_id: int, only_me: bool):
        comments = reviews.comments(round_id, only_me)
        if comments:
            add("## Comments")
        for c in comments:
            where = "" if c["path"] is None else f" on {c['path']}:{c['line']} ({c['side']})"
            add(f"### {c['author']}{where}", c["body_md"])

    status = task["status"] + (f" · {task['stage']}" if task["stage"] else "")
    add(f"# #{task['id']} {task['title']}", f"Status: {status}")
    add("## Description", task["description_md"])
    add("## Spec", "_No spec yet._" if task["spec_md"] is None else task["spec_md"])
    for r in found:
        add(f"## Round {r['n']} — build notes", r["build_md"])
        add("## Verdicts")
        verdicts = {v["reviewer"]: v for v in reviews.round_verdicts(r["id"])}
        for who in REVIEWERS:
            v = verdicts.get(who)
            add(f"### {who}: {v['verdict'] if v else 'pending'}", v and v["body_md"])
        add_comments(r["id"], only_me=False)
        decisions = reviews.round_decisions(r["id"])
        if decisions:
            add("## Decisions")
        for d in decisions:
            add(f"### {d['actor']}: {d['decision']}", d["body_md"])
    if feedback:
        add(f"## Feedback on round {feedback['n']}", feedback["body_md"])
        add_comments(feedback["round_id"], only_me=True)
    return "\n\n".join(blocks) + "\n"


def context(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int, n: str | None,
            feedback: bool) -> str:
    """§6.2: everything (no query), one round (`?round=`), or my latest feedback (`?feedback=1`)."""
    if n is not None and feedback:
        raise Invalid("give round or feedback, not both")
    task = tasks.get(task_id)
    if task is None:
        raise NotFound()
    mine = None
    if feedback:  # 006 Q6: my latest CHANGES_REQUESTED
        mine = reviews.latest_feedback(task_id)
        if mine is None:
            raise NotFound(f"#{task_id} has no feedback")
        found = []
    elif n is not None:
        found = [find_round(tasks, rounds, task_id, n)]
    else:
        found = rounds.all(task_id)
    return context_md(reviews, task, found, mine)
