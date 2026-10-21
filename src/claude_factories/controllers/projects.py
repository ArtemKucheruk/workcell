"""docs/data-model-and-api.md §6.1: connect a project, find one by path, patch (move, rename, test command) or
delete one, and get or put its context."""

import os

from fastapi import APIRouter, HTTPException, Request

from ..dto.projects import ConnectBody, ConnectOut, ContextBody, ContextOut, ProjectOut, ProjectPatch, ProjectPatched
from ..handlers import projects as handler
from ..server.deps import GitAdapter, Projects, Runs, Tasks, Workspaces

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
def patch_project(project_id: int, body: ProjectPatch, workspaces: Workspaces, projects: Projects,
                  tasks: Tasks) -> ProjectPatched:
    return handler.patch_project(workspaces, projects, tasks, project_id, body)


@router.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: int, projects: Projects, tasks: Tasks, runs: Runs) -> None:
    handler.delete_project(projects, tasks, runs, project_id)


@router.get("/api/projects/{project_id}/context")
def get_context(project_id: int, projects: Projects) -> ContextOut:
    return handler.get_context(projects, project_id)


@router.put("/api/projects/{project_id}/context")
def put_context(project_id: int, body: ContextBody, projects: Projects) -> ContextOut:
    return handler.put_context(projects, project_id, body.context_md)
