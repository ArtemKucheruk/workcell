"""093, docs/data-model-and-api.md §6.3: Create PR, the PR's state, and Merge PR. AC23: each handler opens its own
transactions through transaction(), so no write lock is held across git or gh."""

from fastapi import APIRouter, Request

from ..dto.pull_requests import PrCreated, PrMerged, PrState
from ..handlers import pull_requests as handler
from ..server.deps import GitAdapter, transaction

router = APIRouter()


@router.post("/api/tasks/{task_id}/pr")
def create_pr(task_id: int, request: Request, git: GitAdapter) -> PrCreated:
    """Q11: the PR body links the task at the request's base URL, like fctl submit's round URL."""
    return handler.create(transaction, git, task_id, str(request.base_url))


@router.get("/api/tasks/{task_id}/pr")
def pr_state(task_id: int, git: GitAdapter) -> PrState:
    """Q2: polled every 10 s by the task pages while the PR is open."""
    return handler.state(transaction, git, task_id)


@router.post("/api/tasks/{task_id}/pr/merge")
def merge_pr(task_id: int, git: GitAdapter) -> PrMerged:
    return handler.merge(transaction, git, task_id)
