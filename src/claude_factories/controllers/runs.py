"""docs/data-model-and-api.md §6.2: run a task, run next, stop a run, and a run's log; and the runs
lifespan (docs/MVP.md §4.4)."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, Query, Request

from ..dto.runs import LogOut, RunBody, RunNextOut, RunStarted, StopOut
from ..handlers import runs as handler
from ..server.deps import ClaudeAdapter, GitAdapter, get_claude, transaction


@asynccontextmanager
async def lifespan(app):
    """036 Q8: on the router, so server/'s lifespan runs db.init() first (034 Q6)."""
    handler.fail_leftovers(transaction)
    yield
    handler.stop_all(transaction, get_claude())


router = APIRouter(lifespan=lifespan)


def agent_url(request: Request) -> str:
    """028 Q5: an agent's FCTL_URL is loopback plus the port this request arrived on. Agents run next to
    the server, so it reaches it whatever Host a proxy (frontend/server.js) or a port mapping set."""
    return f"http://127.0.0.1:{request.scope['server'][1]}"


@router.post("/api/tasks/{task_id}/run", status_code=202)
def run_task(task_id: int, request: Request, git: GitAdapter, claude: ClaudeAdapter,
             body: RunBody | None = None) -> RunStarted:
    """097 AC9: no body, {}, or a null account_id is Auto."""
    return handler.start(transaction, git, claude, task_id, agent_url(request), body and body.account_id)


@router.post("/api/factories/{factory_id}/run", status_code=202)
def run_automation(factory_id: int, request: Request, git: GitAdapter, claude: ClaudeAdapter,
                   body: RunBody | None = None) -> RunStarted:
    """102: Run now on an automation; the body as a task run's (no body, {}, or a null account_id is Auto)."""
    return handler.start_automation(transaction, git, claude, factory_id, agent_url(request),
                                    body and body.account_id)


@router.post("/api/projects/{project_id}/run-next", status_code=202)
def run_next(project_id: int, request: Request, git: GitAdapter, claude: ClaudeAdapter) -> RunNextOut:
    return handler.run_next(transaction, git, claude, project_id, agent_url(request))


@router.post("/api/runs/{run_id}/stop")
def stop_run(run_id: int, claude: ClaudeAdapter) -> StopOut:
    return handler.stop(transaction, claude, run_id)


@router.get("/api/runs/{run_id}/log")
def run_log(run_id: int, after: int = Query(0, ge=0)) -> LogOut:
    return handler.log(transaction, run_id, after)
