"""docs/data-model-and-api.md §6.1: workspaces."""

from fastapi import APIRouter, HTTPException

from ..dto.workspaces import WorkspaceBody, WorkspaceCreated, WorkspaceOut
from ..handlers import workspaces as handler
from ..server.deps import Tasks, Workspaces

router = APIRouter()


@router.get("/api/workspaces")
def list_workspaces(workspaces: Workspaces) -> list[WorkspaceOut]:
    return handler.list_workspaces(workspaces)


@router.post("/api/workspaces")
def create_workspace(body: WorkspaceBody, workspaces: Workspaces) -> WorkspaceCreated:
    """+ Workspace: an existing name returns its id (020 Q11: stripped, 200 either way)."""
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name must not be blank")
    return WorkspaceCreated(id=handler.create_workspace(workspaces, name), name=name)


@router.patch("/api/workspaces/{workspace_id}")
def rename_workspace(workspace_id: int, body: WorkspaceBody, workspaces: Workspaces, tasks: Tasks) -> WorkspaceCreated:
    return handler.rename_workspace(workspaces, tasks, workspace_id, body.name)


@router.delete("/api/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: int, workspaces: Workspaces, tasks: Tasks) -> None:
    handler.delete_workspace(workspaces, tasks, workspace_id)
