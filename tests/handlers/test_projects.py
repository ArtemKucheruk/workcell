"""119: PATCH /api/projects/{id} with a new `path`, calling handlers/projects.patch_project directly (AC1–AC14)."""

import os

import pytest
from conftest import git, sql

from workcell.adapters.git import SubprocessGit
from workcell.domain.errors import Conflict, Invalid
from workcell.dto.projects import ProjectPatch
from workcell.handlers import projects as handler
from workcell.repositories.projects import ProjectsRepo
from workcell.repositories.runs import RunsRepo
from workcell.repositories.tasks import TasksRepo
from workcell.repositories.workspaces import WorkspacesRepo
from workcell.server.deps import transaction

OLD = "2026-01-01T00:00:00Z"


def init(path) -> str:
    """A git repo on main with one commit at `path`; its realpath."""
    path.parent.mkdir(parents=True, exist_ok=True)
    git(path.parent, "init", "-q", "-b", "main", str(path))
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return os.path.realpath(path)


@pytest.fixture
def old(client, tmp_path) -> str:
    return init(tmp_path / "old" / "repo")


@pytest.fixture
def new(tmp_path) -> str:
    return init(tmp_path / "new" / "repo")


def add_project(path, name="api") -> int:
    workspace = sql("INSERT INTO workspaces (name, created_at) VALUES ('personal', ?)"
                    " ON CONFLICT (name) DO UPDATE SET name = name RETURNING id", (OLD,))[0][0]
    return sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
               " VALUES (?, ?, ?, 'main', ?) RETURNING id", (workspace, name, path, OLD))[0][0]


def add_task(project_id, worktree_path=None) -> int:
    return sql("INSERT INTO tasks (project_id, title, status, position, worktree_path, created_at, updated_at)"
               " VALUES (?, 't', 'in_progress', 1, ?, ?, ?) RETURNING id", (project_id, worktree_path, OLD, OLD))[0][0]


def add_factory(project_id, name="Audit") -> int:
    return sql("INSERT INTO factories (project_id, name, kind, graph, created_at, updated_at)"
               " VALUES (?, ?, 'automation', '{}', ?, ?) RETURNING id", (project_id, name, OLD, OLD))[0][0]


def add_run(task_id=None, factory_id=None, worktree_path=None, status="succeeded") -> int:
    kind = "factory" if task_id else "automation"
    return sql("INSERT INTO runs (task_id, factory_id, kind, worktree_path, session_id, status, log_path, started_at)"
               " VALUES (?, ?, ?, ?, 's', ?, 'l', ?) RETURNING id",
               (task_id, factory_id, kind, worktree_path, status, OLD))[0][0]


def add_item(project_id, source_path) -> int:
    return sql("INSERT INTO context_items (project_id, kind, title, source_path, position, created_at, updated_at)"
               " VALUES (?, 'item', 'x', ?, 1, ?, ?) RETURNING id", (project_id, source_path, OLD, OLD))[0][0]


def patch(project_id, **body):
    with transaction() as conn:
        return handler.patch_project(WorkspacesRepo(conn), ProjectsRepo(conn), TasksRepo(conn), RunsRepo(conn),
                                     SubprocessGit(), project_id, ProjectPatch(**body))


def refused(kind, project_id, **body) -> str:
    with pytest.raises(kind) as e:
        patch(project_id, **body)
    return e.value.detail


def project_row(project_id):
    return sql("SELECT name, path FROM projects WHERE id = ?", (project_id,))[0]


def column(table, col, row_id):
    return sql(f"SELECT {col} FROM {table} WHERE id = ?", (row_id,))[0][0]


def test_path_changes_to_realpath(old, new, tmp_path):  # AC1
    pid = add_project(old)
    link = tmp_path / "link"
    link.symlink_to(new)
    out = patch(pid, path=str(link))
    assert out.path == new and project_row(pid) == ("api", new)


def test_path_with_other_fields(old, new):  # AC2
    pid = add_project(old)
    assert refused(Invalid, pid, path=new, name="  ") == "name must not be blank"
    assert refused(Invalid, pid, path="repo", name="api2") == "path must be absolute"
    assert project_row(pid) == ("api", old)
    out = patch(pid, path=new, name="api2")
    assert (out.name, out.path) == ("api2", new) and project_row(pid) == ("api2", new)


def test_rewrites_task_worktrees(old, new):  # AC3
    pid, other = add_project(old), add_project("/elsewhere", "other")
    under, root, none = add_task(pid, f"{old}/.claude/worktrees/7-x"), add_task(pid, old), add_task(pid)
    theirs = add_task(other, f"{old}/.claude/worktrees/8-y")
    patch(pid, path=new)
    assert column("tasks", "worktree_path", under) == f"{new}/.claude/worktrees/7-x"
    assert column("tasks", "worktree_path", root) == new
    assert column("tasks", "worktree_path", none) is None
    assert column("tasks", "worktree_path", theirs) == f"{old}/.claude/worktrees/8-y"


def test_rewrites_automation_run_worktrees(old, new):  # AC4, Q2
    pid, other = add_project(old), add_project("/elsewhere", "other")
    mine = add_run(factory_id=add_factory(pid), worktree_path=f"{old}/.claude/worktrees/auto-1")
    theirs = add_run(factory_id=add_factory(other), worktree_path=f"{old}/.claude/worktrees/auto-2")
    orphan = add_run(factory_id=None, worktree_path=f"{old}/.claude/worktrees/auto-3")
    patch(pid, path=new)
    assert column("runs", "worktree_path", mine) == f"{new}/.claude/worktrees/auto-1"
    assert column("runs", "worktree_path", theirs) == f"{old}/.claude/worktrees/auto-2"
    assert column("runs", "worktree_path", orphan) == f"{old}/.claude/worktrees/auto-3"


def test_rewrites_context_source_paths(old, new):  # AC5
    pid = add_project(old)
    inside, outside, none = add_item(pid, f"{old}/docs/MVP.md"), add_item(pid, "/etc/notes.md"), add_item(pid, None)
    patch(pid, path=new)
    assert column("context_items", "source_path", inside) == f"{new}/docs/MVP.md"
    assert column("context_items", "source_path", outside) == "/etc/notes.md"
    assert column("context_items", "source_path", none) is None


def test_sibling_prefix_not_rewritten(old, new):  # AC6
    pid = add_project(old)
    sibling = add_task(pid, f"{old}2/.claude/worktrees/7-x")
    wildcard = add_task(pid, f"{old[:-1]}_/x")  # what `LIKE old_` would match
    item = add_item(pid, f"{old}2/README.md")
    patch(pid, path=new)
    assert column("tasks", "worktree_path", sibling) == f"{old}2/.claude/worktrees/7-x"
    assert column("tasks", "worktree_path", wildcard) == f"{old[:-1]}_/x"
    assert column("context_items", "source_path", item) == f"{old}2/README.md"


def test_relative_path(old):  # AC7
    pid = add_project(old)
    assert refused(Invalid, pid, path="repo") == "path must be absolute"


def test_missing_or_file(old, tmp_path):  # AC8
    pid = add_project(old)
    assert refused(Invalid, pid, path="/x/nowhere") == "no folder at /x/nowhere"
    (tmp_path / "file").write_text("")
    assert refused(Invalid, pid, path=str(tmp_path / "file")) == f"no folder at {tmp_path / 'file'}"


def test_not_a_repo(old, tmp_path):  # AC9
    pid = add_project(old)
    (tmp_path / "plain").mkdir()
    assert refused(Invalid, pid, path=str(tmp_path / "plain")) == f"{tmp_path / 'plain'} is not a git repository"


def test_worktree_or_subdirectory(old, new, tmp_path):  # AC10, Q3
    pid = add_project(old)
    linked = tmp_path / "linked"
    git(new, "worktree", "add", "-q", "-b", "side", str(linked))
    assert refused(Invalid, pid, path=str(linked)) == f"{linked} is not a main checkout; use {new}"
    os.mkdir(f"{new}/src")
    assert refused(Invalid, pid, path=f"{new}/src") == f"{new}/src is not a main checkout; use {new}"
    assert project_row(pid) == ("api", old)


def test_taken_path(old, new):  # AC11
    pid, other = add_project(old), add_project(new, "other")
    assert refused(Conflict, pid, path=new) == f"project #{other} already has path {new}"
    assert project_row(pid) == ("api", old)
    task = add_task(pid, f"{old}/w")
    assert patch(pid, path=old).path == old  # its own path: nothing to rewrite
    assert column("tasks", "worktree_path", task) == f"{old}/w"


def test_active_task_run(old, new):  # AC12
    pid = add_project(old)
    task = add_task(pid, f"{old}/w")
    run = add_run(task_id=task, status="running")
    add_run(task_id=add_task(add_project("/elsewhere", "other")), status="running")  # not this project's
    assert refused(Conflict, pid, path=new) == f"run #{run} active"
    assert project_row(pid) == ("api", old) and column("tasks", "worktree_path", task) == f"{old}/w"
    assert patch(pid, name="api2").name == "api2"  # 049 BE8: other fields still change during a run


def test_active_automation_run(old, new):  # AC13
    pid = add_project(old)
    run = add_run(factory_id=add_factory(pid), worktree_path=f"{old}/a", status="running")
    assert refused(Conflict, pid, path=new) == f"run #{run} active"
    assert project_row(pid) == ("api", old) and column("runs", "worktree_path", run) == f"{old}/a"


def test_other_projects_run_does_not_block(old, new):  # AC12: only this project's runs count
    pid = add_project(old)
    add_run(factory_id=add_factory(add_project("/elsewhere", "other")), status="running")
    assert patch(pid, path=new).path == new


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_path(old, blank):  # AC14
    pid = add_project(old)
    assert refused(Invalid, pid, path=blank) == "path must not be blank"
