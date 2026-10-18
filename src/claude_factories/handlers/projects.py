"""Projects: connect, find by path, and move to another workspace (docs/data-model-and-api.md §6.1)."""

from ..adapters.git import Git
from ..domain.errors import NotFound
from ..dto.projects import ConnectBody, ConnectOut, ProjectOut
from ..repositories.projects import ProjectsRepo
from ..repositories.workspaces import WorkspacesRepo
from .factory import factory_state


def connect(workspaces: WorkspacesRepo, projects: ProjectsRepo, body: ConnectBody, base_url: str) -> ConnectOut:
    """`body` already checked and stripped by the controller. 002 Q4: path is the key."""
    workspace_id = workspaces.get_or_create(body.workspace)
    found = projects.by_path(body.path)
    if found:
        project_id = found["id"]
        projects.update(project_id, workspace_id, body.name, body.remote_url, body.default_branch, body.test_cmd)
    else:
        project_id = projects.add(workspace_id, body.name, body.path, body.remote_url, body.default_branch,
                                  body.test_cmd)
    return ConnectOut(id=project_id, created=found is None, url=f"{base_url}projects/{project_id}")


def find_project(projects: ProjectsRepo, git: Git, path: str) -> ProjectOut:
    p = projects.by_path(path)
    if p is None:
        raise NotFound(f"no project at {path}; in that repo, run fctl connect --workspace <name>")
    return ProjectOut(id=p["id"], name=p["name"], default_branch=p["default_branch"],
                      factory=factory_state(git, p["path"], p["default_branch"]))


def move_project(workspaces: WorkspacesRepo, projects: ProjectsRepo, project_id: int, workspace_id: int) -> None:
    if not workspaces.exists(workspace_id) or not projects.move(project_id, workspace_id):
        raise NotFound()
