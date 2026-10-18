"""docs/data-model-and-api.md §6.1: workspaces."""

from fastapi import APIRouter, HTTPException

from ..dto.workspaces import WorkspaceBody, WorkspaceCreated, WorkspaceOut
from ..handlers import workspaces as handler
from ..server.deps import Workspaces

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
