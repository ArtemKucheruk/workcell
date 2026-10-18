"""docs/ui.md §8 item 3: the board, + New task, the move to another workspace, and Create factory."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ...domain.errors import DomainError
from ...dto.tasks import TaskBody
from ...handlers import factory as factory_handler
from ...handlers import pages as handler
from ...handlers import projects as projects_handler
from ...handlers import tasks as tasks_handler
from ...server.deps import ClaudeAdapter, GitAdapter, Projects, Reviews, Rounds, Runs, Tasks, Workspaces
from . import form_field, hx_redirect, templates

router = APIRouter()


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_page(request: Request, project_id: int, projects: Projects, tasks: Tasks, rounds: Rounds,
                 reviews: Reviews, runs: Runs, workspaces: Workspaces, git: GitAdapter, claude: ClaudeAdapter):
    return templates.TemplateResponse(request, "project.html", handler.board(
        projects, tasks, rounds, reviews, runs, workspaces, git, claude, project_id))


@router.post("/projects/{project_id}/tasks")
async def add_task_form(request: Request, project_id: int, tasks: Tasks, projects: Projects, rounds: Rounds,
                        reviews: Reviews):
    """Q10: the + New task form; create_task validates, places, and logs the event."""
    body = TaskBody(
        title=await form_field(request, "title"),
        description_md=await form_field(request, "description_md"),
    )
    tasks_handler.create_task(tasks, projects, rounds, reviews, project_id, body, str(request.base_url))
    return hx_redirect(f"/projects/{project_id}")


@router.post("/projects/{project_id}/workspace")
async def move_project(request: Request, project_id: int, workspaces: Workspaces, projects: Projects):
    try:
        ws_id = int(await form_field(request, "workspace_id"))
    except ValueError:
        raise HTTPException(422, "workspace_id must be an integer")
    projects_handler.move_project(workspaces, projects, project_id, ws_id)
    return hx_redirect(f"/projects/{project_id}")


@router.post("/projects/{project_id}/factory", response_class=HTMLResponse)
async def create_factory_form(request: Request, project_id: int, projects: Projects):
    """011 Q11: htmx doesn't swap 4xx, so errors come back as a 200 fragment with role="alert". Every
    refusal comes before any write (011 Q7), so the request's commit after one writes nothing."""
    overwrite = bool(await form_field(request, "overwrite"))
    try:
        result = factory_handler.create_factory(projects, project_id, overwrite).model_dump()
    except DomainError as e:
        result = {"error": e.detail}
    return templates.TemplateResponse(request, "factory_result.html", result)
