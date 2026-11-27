"""Workspaces: list them, + Workspace, rename, and delete."""

from ..domain.errors import Conflict, Invalid, NotFound
from ..dto.workspaces import WorkspaceCreated, WorkspaceOut
from ..repositories.tasks import TasksRepo
from ..repositories.workspaces import WorkspacesRepo


def list_workspaces(workspaces: WorkspacesRepo) -> list[WorkspaceOut]:
    return [WorkspaceOut(**w) for w in workspaces.all()]


def create_workspace(workspaces: WorkspacesRepo, name: str) -> int:
    """The workspace named `name`, created if new."""
    return workspaces.get_or_create(name)


def rename_workspace(workspaces: WorkspacesRepo, tasks: TasksRepo, workspace_id: int, name: str) -> WorkspaceCreated:
    """049 Q8: names compare exactly after trimming, as the UNIQUE column does; its own name is a 200."""
    name = name.strip()
    if not name:
        raise Invalid("name must not be blank")
    tasks.lock()  # the clash check and the rename commit together
    if not workspaces.exists(workspace_id):
        raise NotFound(f"Workspace #{workspace_id} not found")
    if workspaces.by_name(name) not in (None, workspace_id):
        raise Conflict(f"workspace {name} already exists")
    workspaces.rename(workspace_id, name)
    return WorkspaceCreated(id=workspace_id, name=name)


def delete_workspace(workspaces: WorkspacesRepo, tasks: TasksRepo, workspace_id: int) -> None:
    """049: only an empty workspace goes; its projects are moved or deleted first."""
    tasks.lock()  # the count and the delete commit together
    found = workspaces.get(workspace_id)
    if found is None:
        raise NotFound(f"Workspace #{workspace_id} not found")
    if count := workspaces.project_count(workspace_id):
        noun = "project" if count == 1 else "projects"
        raise Conflict(f"workspace {found['name']} still holds {count} {noun}; move or delete them first")
    workspaces.delete(workspace_id)
