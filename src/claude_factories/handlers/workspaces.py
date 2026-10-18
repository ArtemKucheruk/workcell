"""Workspaces: list them, and + Workspace."""

from ..dto.workspaces import WorkspaceOut
from ..repositories.workspaces import WorkspacesRepo


def list_workspaces(workspaces: WorkspacesRepo) -> list[WorkspaceOut]:
    return [WorkspaceOut(**w) for w in workspaces.all()]


def create_workspace(workspaces: WorkspacesRepo, name: str) -> int:
    """The workspace named `name`, created if new."""
    return workspaces.get_or_create(name)
