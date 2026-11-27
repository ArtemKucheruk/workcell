"""Projects: connect, find by path, patch (move, rename, test command, 119's path), delete, and the project context
(docs/data-model-and-api.md §6.1)."""

import os
from urllib.parse import urlsplit

from .. import config
from ..adapters.git import Git
from ..domain.errors import Conflict, Invalid, NotFound, TooLarge
from ..dto.projects import ConnectBody, ConnectOut, ContextOut, ProjectOut, ProjectPatch, ProjectPatched
from ..lib.markdown import render
from ..repositories.projects import ProjectsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
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
        raise NotFound(f"no project at {path}; in that repo, run fctl connect --workspace <name>, or if the"
                       " checkout moved, change the path on the project's Settings page")  # 119 AC15
    return ProjectOut(id=p["id"], name=p["name"], default_branch=p["default_branch"],
                      factory=factory_state(git, p["path"], p["default_branch"]))


def api_url(url: str) -> bool:
    """109 AC3, Q7: http or https with a host, no `user:pass@`, query, or fragment (paths get appended to it)."""
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 (raises on a bad port)
    except ValueError:
        return False
    return (parts.scheme in ("http", "https") and bool(parts.hostname) and "@" not in parts.netloc
            and not parts.query and not parts.fragment and not any(c.isspace() for c in url))


def main_checkout(git: Git, path: str) -> str:
    """119 AC7–AC10: `path`'s realpath (MVP §4.5) when it is a git repo's main checkout; Invalid saying what's wrong
    otherwise. Q3: a linked worktree or a subdirectory is refused, naming the main checkout to use instead."""
    if not path:
        raise Invalid("path must not be blank")
    if not os.path.isabs(path):
        raise Invalid("path must be absolute")
    if not os.path.isdir(path):
        raise Invalid(f"no folder at {path}")
    real = os.path.realpath(path)
    main = git.main_checkout(real)
    if main is None:
        raise Invalid(f"{path} is not a git repository")
    if main != real:
        raise Invalid(f"{path} is not a main checkout; use {main}")
    return real


def patch_project(workspaces: WorkspacesRepo, projects: ProjectsRepo, tasks: TasksRepo, runs: RunsRepo, git: Git,
                  project_id: int, body: ProjectPatch) -> ProjectPatched:
    """049 Q1–Q4: the sent fields together, in any state. Both 404s keep 020's `Not Found`. 119: a new `path` is
    checked before the lock (git runs), then refused if taken or while a run of the project is active, and the
    project's stored paths under the old root move with it, all in this transaction."""
    fields = {key: getattr(body, key) for key in body.model_fields_set}
    if not fields:
        raise Invalid("send at least one of: workspace_id, name, path, test_cmd, github_label, plane_api_url,"
                      " plane_workspace, plane_project_id, plane_api_key, plane_mark_done")
    if "path" in fields:
        fields["path"] = main_checkout(git, fields["path"].strip())
    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if not fields["name"]:
            raise Invalid("name must not be blank")
    if "test_cmd" in fields:
        fields["test_cmd"] = fields["test_cmd"].strip() or None  # Q3: blank stores NULL
    if "github_label" in fields:
        fields["github_label"] = fields["github_label"].strip() or None  # 108 AC2, AC3: the same
    for column in ("plane_api_url", "plane_workspace", "plane_project_id", "plane_api_key"):  # 109 AC2, AC5
        if column in fields:
            fields[column] = fields[column].strip() or None
    if fields.get("plane_api_url"):
        fields["plane_api_url"] = fields["plane_api_url"].rstrip("/")
        if not api_url(fields["plane_api_url"]):
            raise Invalid("plane_api_url must be an http(s) URL like https://api.plane.so")
    tasks.lock()  # so the workspace can't go between its check and the update
    if "workspace_id" in fields and not workspaces.exists(fields["workspace_id"]):
        raise NotFound()
    old = projects.path(project_id)
    if old is None:
        raise NotFound()
    moved = "path" in fields and fields["path"] != old  # AC11: its own path changes nothing
    if moved:
        taken = projects.by_path(fields["path"])
        if taken:
            raise Conflict(f"project #{taken['id']} already has path {fields['path']}")
        if run := runs.running_for_project(project_id):  # AC12, AC13: its worktree is under the old path
            raise Conflict(f"run #{run['id']} active")
    row = projects.patch(project_id, fields)
    if moved:
        projects.move_paths(project_id, old, fields["path"])
    return ProjectPatched(**row)


def delete_project(projects: ProjectsRepo, tasks: TasksRepo, runs: RunsRepo, project_id: int) -> None:
    """049: the project and its tasks, each the 048 way (§5.1), refused while one of them runs (§5.2, Q6).
    Nothing on disk."""
    tasks.lock()  # the 409 check and the deletes commit together
    if not projects.exists(project_id):
        raise NotFound(f"Project #{project_id} not found")
    task_ids = [t["id"] for t in tasks.for_project(project_id)]
    for task_id in task_ids:
        if run := runs.running(task_id):
            raise Conflict(f"run #{run['id']} active")
    for task_id in task_ids:
        tasks.delete(task_id)
    projects.delete(project_id)


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
