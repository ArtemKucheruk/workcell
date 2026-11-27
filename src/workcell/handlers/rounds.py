"""Rounds: submit, the round lookup, the diff, and the summaries (docs/data-model-and-api.md §6.3,
docs/claude-code.md §7.4)."""

from .. import config
from ..domain.enums import Reviewer, Stage, Status
from ..domain.errors import Invalid, NotFound, TooLarge
from ..dto.rounds import RoundBody, RoundSubmitted, RoundSummary
from ..lib.patch import split_patch
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.tasks import TasksRepo

REVIEWERS = tuple(Reviewer)


def trigger(reviews: ReviewsRepo, task_id: int, n: int) -> str:
    """005 Q1: round 1 is initial; a round after my CHANGES_REQUESTED on the one before is human; else agent."""
    if n == 1:
        return "initial"
    return "human" if reviews.changes_requested(task_id, n - 1) else "agent"


def insert_round(rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int, body: RoundBody,
                 now: str | None = None) -> dict:
    """Check the patch (005 Q4, Q5), number the round, and insert it with its files, inside the caller's
    BEGIN IMMEDIATE so any refusal writes nothing. {round, files_changed, additions, deletions}."""
    if len(body.patch.encode()) > config.MAX_PATCH:
        raise TooLarge("patch over 5 MB")
    if not body.patch.strip():
        raise Invalid("no changes to submit")
    files = split_patch(body.patch)
    n = rounds.next_n(task_id)
    rounds.add(task_id, n, trigger(reviews, task_id, n), body.base_sha, body.build_md, files, now)
    return {"round": n, "files_changed": len(files), "additions": sum(f["additions"] for f in files),
            "deletions": sum(f["deletions"] for f in files)}


def submit_round(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int, body: RoundBody,
                 base_url: str) -> RoundSubmitted:
    now = tasks.lock()  # n, the round, its files, and the status commit together
    task = tasks.get(task_id)
    if task is None:
        raise NotFound()
    submitted = insert_round(rounds, reviews, task_id, body)
    if task["worktree_path"] is None:  # 005 Q2: every round puts a standalone task in Review
        tasks.move(task_id, Status.REVIEW, Stage.HUMAN_REVIEW, None, now)
        if (task["status"], task["stage"]) != (Status.REVIEW, Stage.HUMAN_REVIEW):
            tasks.add_event(task_id, "app", task["status"], Status.REVIEW, Stage.HUMAN_REVIEW, now)
    return RoundSubmitted(**submitted, url=f"{base_url}tasks/{task_id}/review?round={submitted['round']}")


def round_summaries(rounds: RoundsRepo, reviews: ReviewsRepo, task_id: int) -> list[RoundSummary]:
    """A task's rounds by n: file count, +/− sums, and all 4 verdicts ('pending' if missing)."""
    verdicts = {(v["round_id"], v["reviewer"]): v["verdict"] for v in reviews.task_verdicts(task_id)}
    return [
        RoundSummary(n=r["n"], trigger=r["trigger"], files=r["files"], additions=r["additions"],
                     deletions=r["deletions"],
                     verdicts={who.value: verdicts.get((r["id"], who), "pending") for who in REVIEWERS})
        for r in rounds.totals(task_id)
    ]


def find_round(tasks: TasksRepo, rounds: RoundsRepo, task_id: int, n: str):
    """005 Q7, 006 Q1: the task's round `n` (id, n, build_md), or its highest with `latest`; the bare
    404 for an unknown task first."""
    if not tasks.exists(task_id):
        raise NotFound()
    if n == "latest":
        found, missing = rounds.latest(task_id), f"#{task_id} has no rounds"
    else:
        found, missing = rounds.by_n(task_id, n), f"#{task_id} has no round {n}"
    if found is None:
        raise NotFound(missing)
    return found


def diff(tasks: TasksRepo, rounds: RoundsRepo, task_id: int, n: str) -> str:
    """005 Q7: the round's files' patches joined in rowid order."""
    return "".join(rounds.patches(find_round(tasks, rounds, task_id, n)["id"]))
