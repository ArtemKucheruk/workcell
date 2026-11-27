"""docs/data-model-and-api.md §6.3: submit a round, and a round's diff."""

from fastapi import APIRouter, Request, Response

from ..dto.rounds import RoundBody, RoundSubmitted
from ..handlers import rounds as handler
from ..server.deps import Reviews, Rounds, Tasks

router = APIRouter()
NOSNIFF = {"X-Content-Type-Options": "nosniff"}  # agent-written text, never sniffed as HTML


@router.post("/api/tasks/{task_id}/rounds", status_code=201)
def submit_round(task_id: int, body: RoundBody, request: Request, tasks: Tasks, rounds: Rounds,
                 reviews: Reviews) -> RoundSubmitted:
    return handler.submit_round(tasks, rounds, reviews, task_id, body, str(request.base_url))


@router.get("/api/tasks/{task_id}/rounds/{n}/diff")
def round_diff(task_id: int, n: str, tasks: Tasks, rounds: Rounds) -> Response:
    return Response(handler.diff(tasks, rounds, task_id, n), media_type="text/x-diff", headers=NOSNIFF)
