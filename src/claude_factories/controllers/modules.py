"""docs/data-model-and-api.md §6.1: a project's modules (112)."""

from fastapi import APIRouter

from ..dto.modules import ModuleList, ModuleOut, ModulePatch, NewModule
from ..handlers import modules as handler
from ..server.deps import Modules, Projects, Tasks

router = APIRouter()


@router.get("/api/projects/{project_id}/modules")
def list_modules(project_id: int, projects: Projects, modules: Modules) -> ModuleList:
    return handler.list_modules(projects, modules, project_id)


@router.post("/api/projects/{project_id}/modules", status_code=201)
def create_module(project_id: int, body: NewModule, projects: Projects, modules: Modules, tasks: Tasks) -> ModuleOut:
    return handler.create_module(projects, modules, tasks, project_id, body)


@router.patch("/api/modules/{module_id}")
def patch_module(module_id: int, body: ModulePatch, modules: Modules, tasks: Tasks) -> ModuleOut:
    return handler.patch_module(modules, tasks, module_id, body)


@router.delete("/api/modules/{module_id}", status_code=204)
def delete_module(module_id: int, modules: Modules) -> None:
    handler.delete_module(modules, module_id)
