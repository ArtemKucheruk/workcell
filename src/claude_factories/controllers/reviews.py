"""docs/data-model-and-api.md §6.3: verdicts, comments, the approver's decision, my approve, and my
request changes with its rework run; §6.2: the context markdown."""

from fastapi import APIRouter, Query, Request, Response

from ..dto.reviews import (ApproveBody, ApproveOut, ChangesBody, ChangesOut, CommentBody, DecisionBody, IdOut, Reviewer,
                           VerdictBody, VerdictOut)
from ..handlers import reviews as handler
from ..server.deps import ClaudeAdapter, GitAdapter, Reviews, Rounds, Tasks, transaction
from .rounds import NOSNIFF
from .runs import agent_url

router = APIRouter()


@router.put("/api/tasks/{task_id}/rounds/{n}/verdicts/{reviewer}")
def put_verdict(task_id: int, n: str, reviewer: Reviewer, body: VerdictBody, tasks: Tasks, rounds: Rounds,
                reviews: Reviews) -> VerdictOut:
    return handler.put_verdict(tasks, rounds, reviews, task_id, n, reviewer, body)


@router.post("/api/tasks/{task_id}/comments", status_code=201)
def post_comment(task_id: int, body: CommentBody, tasks: Tasks, rounds: Rounds, reviews: Reviews) -> IdOut:
    return handler.post_comment(tasks, rounds, reviews, task_id, body)


@router.post("/api/tasks/{task_id}/decision", status_code=201)
def post_decision(task_id: int, body: DecisionBody, tasks: Tasks, rounds: Rounds, reviews: Reviews) -> IdOut:
    return handler.post_decision(tasks, rounds, reviews, task_id, body)


@router.post("/api/tasks/{task_id}/approve")
def approve(task_id: int, body: ApproveBody, tasks: Tasks, rounds: Rounds, reviews: Reviews) -> ApproveOut:
    return handler.approve(tasks, rounds, reviews, task_id, body)


@router.post("/api/tasks/{task_id}/request-changes", status_code=202)
def request_changes(task_id: int, body: ChangesBody, request: Request, git: GitAdapter,
                    claude: ClaudeAdapter) -> ChangesOut:
    """036 Q10: the handler commits my decision before any spawn, so it takes transaction()."""
    return handler.rework(transaction, git, claude, task_id, body, agent_url(request))


@router.get("/api/tasks/{task_id}/context")
def task_context(task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews,
                 n: str | None = Query(None, alias="round"), feedback: bool = False) -> Response:
    return Response(handler.context(tasks, rounds, reviews, task_id, n, feedback), media_type="text/markdown",
                    headers=NOSNIFF)
