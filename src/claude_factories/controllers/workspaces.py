"""docs/data-model-and-api.md §6.1: workspaces."""

from fastapi import APIRouter

from ..dto.workspaces import WorkspaceOut
from ..handlers import workspaces as handler
from ..server.deps import Workspaces

router = APIRouter()


@router.get("/api/workspaces")
def list_workspaces(workspaces: Workspaces) -> list[WorkspaceOut]:
    return handler.list_workspaces(workspaces)
