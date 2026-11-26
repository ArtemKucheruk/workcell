"""112: a project's modules, its units of work (docs/data-model-and-api.md §5.1, §6.1). A task has at most one; the
task side is in handlers/tasks.py."""

import re

from ..domain.errors import Conflict, Invalid, NotFound
from ..dto.modules import Counts, ModuleList, ModuleOut, ModulePatch, NewModule
from ..repositories.modules import ModulesRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.tasks import TasksRepo

NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")  # Q1: ASCII only, so COLLATE NOCASE's uniqueness is exact
STATUSES = tuple(Counts.model_fields)


def checked_name(name: str) -> str:
    """AC5: trimmed, then 1–40 ASCII letters, digits, `-`, or `_`."""
    name = name.strip()
    if not NAME.fullmatch(name):
        raise Invalid("a module name is 1 to 40 ASCII letters, digits, - or _, e.g. frontend or api_v2")
    return name


def module_out(row) -> ModuleOut:
    return ModuleOut(id=row["id"], name=row["name"], description_md=row["description_md"],
                     counts=Counts(**{s: row[s] for s in STATUSES}))


def list_modules(projects: ProjectsRepo, modules: ModulesRepo, project_id: int) -> ModuleList:
    if not projects.exists(project_id):
        raise NotFound(f"Project #{project_id} not found")
    no_module = modules.no_module(project_id)
    return ModuleList(modules=[module_out(r) for r in modules.for_project(project_id)],
                      no_module=Counts(**{s: no_module[s] for s in STATUSES}))


def create_module(projects: ProjectsRepo, modules: ModulesRepo, tasks: TasksRepo, project_id: int,
                  body: NewModule) -> ModuleOut:
    """AC4–AC7: the 422, then 404, then 409."""
    name = checked_name(body.name)
    tasks.lock()  # the clash check and the insert commit together
    if not projects.exists(project_id):
        raise NotFound(f"Project #{project_id} not found")
    if (found := modules.by_name(project_id, name)) is not None:
        raise Conflict(f"module {modules.get(found)['name']} already exists")
    return module_out(modules.get(modules.add(project_id, name, body.description_md)))


def patch_module(modules: ModulesRepo, tasks: TasksRepo, module_id: int, body: ModulePatch) -> ModuleOut:
    """AC8: name and/or description; a new case of its own name is no clash."""
    fields = {key: getattr(body, key) for key in body.model_fields_set}
    if not fields:
        raise Invalid("send at least one of: name, description_md")
    if "name" in fields:
        fields["name"] = checked_name(fields["name"])
    tasks.lock()
    row = modules.get(module_id)
    if row is None:
        raise NotFound(f"Module #{module_id} not found")
    if "name" in fields:
        found = modules.by_name(row["project_id"], fields["name"])
        if found not in (None, module_id):
            raise Conflict(f"module {modules.get(found)['name']} already exists")
    modules.update(module_id, fields)
    return module_out(modules.get(module_id))


def delete_module(modules: ModulesRepo, module_id: int) -> None:
    """AC9: its tasks stay, with no module."""
    if not modules.delete(module_id):
        raise NotFound(f"Module #{module_id} not found")


def check_module(modules: ModulesRepo, project_id: int, module_id: int) -> None:
    """AC12, AC13: a task's module is one of its own project's."""
    row = modules.get(module_id)
    if row is None:
        raise Invalid(f"no module #{module_id}")
    if row["project_id"] != project_id:
        raise Invalid(f"module #{module_id} is in another project; pick one of this project's modules")
