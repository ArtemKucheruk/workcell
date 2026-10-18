"""Projects: connect, find by path, move to another workspace, and the project context
(docs/data-model-and-api.md §6.1)."""

from .. import config
from ..adapters.git import Git
from ..domain.errors import NotFound, TooLarge
from ..dto.projects import ConnectBody, ConnectOut, ContextOut, ProjectOut
from ..lib.markdown import render
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


def context_out(context_md: str) -> ContextOut:
    """033 Q3: the cap travels with the context, so the SPA doesn't repeat it."""
    return ContextOut(context_md=context_md, context_html=render(context_md), bytes=len(context_md.encode()),
                      max_bytes=config.MAX_CONTEXT)


def get_context(projects: ProjectsRepo, project_id: int) -> ContextOut:
    context_md = projects.context(project_id)
    if context_md is None:
        raise NotFound(f"Project #{project_id} not found")
    return context_out(context_md)


def put_context(projects: ProjectsRepo, project_id: int, context_md: str) -> ContextOut:
    """033 Q4: the cap counts UTF-8 bytes, as MAX_PATCH does; exactly MAX_CONTEXT passes."""
    if len(context_md.encode()) > config.MAX_CONTEXT:
        raise TooLarge("context over 16 KB")
    if not projects.set_context(project_id, context_md):
        raise NotFound(f"Project #{project_id} not found")
    return context_out(context_md)
