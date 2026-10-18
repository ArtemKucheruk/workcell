"""docs/ui.md §8 item 6: the code page."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ...handlers import code as handler
from ...server.deps import GitAdapter, Projects
from . import templates

router = APIRouter()


@router.get("/projects/{project_id}/code", response_class=HTMLResponse)
def code_page(request: Request, project_id: int, projects: Projects, git: GitAdapter, path: str = ""):
    return templates.TemplateResponse(request, "code.html", handler.code(projects, git, project_id, path))
