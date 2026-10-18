"""docs/ui.md §8 items 4 and 5: the task and review pages, and their Approve, Request changes, and
comment forms."""

from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ...domain.errors import DomainError
from ...dto.reviews import ApproveBody, ChangesBody, CommentBody
from ...handlers import pages as handler
from ...handlers import reviews as reviews_handler
from ...server.deps import ClaudeAdapter, GitAdapter, Reviews, Rounds, Runs, Tasks, transaction
from ..runs import agent_url
from . import form_field, hx_redirect, templates

router = APIRouter()


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_page(request: Request, task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews, runs: Runs,
              git: GitAdapter, claude: ClaudeAdapter):
    return templates.TemplateResponse(request, "task.html",
                                      handler.task(tasks, rounds, reviews, runs, git, claude, task_id))


@router.get("/tasks/{task_id}/review", response_class=HTMLResponse)
def review_page(request: Request, task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews,
                n: str = Query("latest", alias="round"), tab: str = "", path: str = "", side: str = "",
                line: str = ""):
    return templates.TemplateResponse(request, "review.html",
                                      handler.review(tasks, rounds, reviews, task_id, n, tab, path, side, line))


@router.post("/tasks/{task_id}/approve")
def approve_form(task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews):
    """Q12: the page's Approve sends no summary."""
    reviews_handler.approve(tasks, rounds, reviews, task_id, ApproveBody())
    return hx_redirect(f"/tasks/{task_id}/review")


@router.post("/tasks/{task_id}/request-changes")
async def request_changes_form(request: Request, task_id: int, git: GitAdapter, claude: ClaudeAdapter,
                               tasks: Tasks, rounds: Rounds, reviews: Reviews):
    """`tasks`, `rounds`, and `reviews` only read the page back after a refusal; the decision and the
    run commit in the handler's own transactions (036 Q10)."""
    body = ChangesBody(body_md=await form_field(request, "body_md"))
    try:
        await run_in_threadpool(reviews_handler.rework, transaction, git, claude, task_id, body,
                                agent_url(request))  # the spawn blocks
    except DomainError as e:
        if not getattr(e, "recorded", False):  # nothing written: the page's alert shows the detail
            raise
        # 013 ux review: htmx doesn't swap a 4xx, so the page would still offer the decision just made.
        # Swap in its header as it is now (round and tab from the page's URL), the refusal in the alert.
        shown = parse_qs(urlsplit(request.headers.get("hx-current-url", "")).query)
        context = handler.review(tasks, rounds, reviews, task_id, shown.get("round", ["latest"])[0],
                                 shown.get("tab", [""])[0])
        return templates.TemplateResponse(request, "review.html", context | {"refused": e.detail}, headers={
            "HX-Retarget": "header", "HX-Reselect": "header", "HX-Reswap": "outerHTML"})
    return hx_redirect(f"/tasks/{task_id}/review")


@router.post("/tasks/{task_id}/comments")
async def add_comment_form(request: Request, task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews):
    """007 Q9: a conversation comment from me on the latest round, or 008 Q3: an inline one on the
    sent `round`, `path`, `side`, and `line` (blank = absent). post_comment validates and writes."""
    fields = {k: await form_field(request, k) for k in ("round", "path", "side", "line")}
    try:
        body = CommentBody(author="me", body_md=await form_field(request, "body_md"),
                           **{k: v for k, v in fields.items() if v})
    except ValidationError as e:  # 008 Q11: a 422 with the messages, never the input
        raise HTTPException(422, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()])
    created = reviews_handler.post_comment(tasks, rounds, reviews, task_id, body)
    if body.path is None:
        return hx_redirect(f"/tasks/{task_id}/review")
    return hx_redirect(handler.comment_url(reviews, task_id, created.id))
