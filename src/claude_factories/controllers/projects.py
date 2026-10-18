"""docs/data-model-and-api.md §6.1: connect a project, find one by path, and move one to another workspace."""

import os

from fastapi import APIRouter, HTTPException, Request

from ..dto.projects import ConnectBody, ConnectOut, MoveBody, MoveOut, ProjectOut
from ..handlers import projects as handler
from ..server.deps import GitAdapter, Projects, Workspaces

router = APIRouter()


@router.post("/api/projects/connect")
def connect_project(body: ConnectBody, request: Request, workspaces: Workspaces, projects: Projects) -> ConnectOut:
    workspace, name, branch = body.workspace.strip(), body.name.strip(), body.default_branch
    if not os.path.isabs(body.path):
        raise HTTPException(422, "path must be absolute")
    if not workspace:
        raise HTTPException(422, "workspace must not be blank")
    if not name:
        raise HTTPException(422, "name must not be blank")
    if not branch or branch.startswith("-"):  # it becomes a git argument
        raise HTTPException(422, "default_branch must be non-empty and not start with '-'")
    body = body.model_copy(update={"workspace": workspace, "name": name})
    return handler.connect(workspaces, projects, body, str(request.base_url))


@router.get("/api/projects")
def find_project(path: str, projects: Projects, git: GitAdapter) -> ProjectOut:
    return handler.find_project(projects, git, path)


@router.patch("/api/projects/{project_id}")
def move_project(project_id: int, body: MoveBody, workspaces: Workspaces, projects: Projects) -> MoveOut:
    """404 if either id is unknown, before any write."""
    handler.move_project(workspaces, projects, project_id, body.workspace_id)
    return MoveOut(id=project_id, workspace_id=body.workspace_id)
