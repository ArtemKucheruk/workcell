"""docs/ui.md §8 item 2: a workspace's page, and + Workspace."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ...handlers import pages as handler
from ...handlers import workspaces as workspaces_handler
from ...server.deps import GitAdapter, Projects, Workspaces
from . import form_field, hx_redirect, templates

router = APIRouter()


@router.get("/workspaces/{workspace_id}", response_class=HTMLResponse)
def workspace_page(request: Request, workspace_id: int, workspaces: Workspaces, projects: Projects, git: GitAdapter):
    return templates.TemplateResponse(request, "workspace.html",
                                      handler.workspace(workspaces, projects, git, workspace_id))


@router.post("/workspaces")
async def create_workspace(request: Request, workspaces: Workspaces):
    name = await form_field(request, "name")
    if not name:
        raise HTTPException(422, "name must not be blank")
    return hx_redirect(f"/workspaces/{workspaces_handler.create_workspace(workspaces, name)}")
