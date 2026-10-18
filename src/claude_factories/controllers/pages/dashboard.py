"""docs/ui.md §8 item 1: the dashboard."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ...handlers import pages as handler
from ...server.deps import Runs, Tasks, Workspaces
from . import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, tasks: Tasks, runs: Runs, workspaces: Workspaces, show: str = ""):
    return templates.TemplateResponse(request, "index.html", handler.dashboard(tasks, runs, workspaces, show))
