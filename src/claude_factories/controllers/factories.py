"""docs/data-model-and-api.md §6.1: a project's factory designs (051)."""

from fastapi import APIRouter

from ..dto.factories import FactoryDesign, FactoryItem, FactoryPatch, NewFactory
from ..handlers import factories as handler
from ..server.deps import Factories, Projects, Tasks

router = APIRouter()


@router.get("/api/projects/{project_id}/factories")
def list_factories(project_id: int, projects: Projects, factories: Factories) -> list[FactoryItem]:
    return handler.list_factories(projects, factories, project_id)


@router.post("/api/projects/{project_id}/factories", status_code=201)
def create_factory(project_id: int, body: NewFactory, projects: Projects, factories: Factories,
                   tasks: Tasks) -> FactoryDesign:
    return handler.create_factory(projects, factories, tasks, project_id, body.name)


@router.get("/api/factories/{factory_id}")
def get_factory(factory_id: int, factories: Factories) -> FactoryDesign:
    return handler.get_factory(factories, factory_id)


@router.put("/api/factories/{factory_id}")
def put_factory(factory_id: int, body: FactoryPatch, factories: Factories, tasks: Tasks) -> FactoryDesign:
    return handler.put_factory(factories, tasks, factory_id, body)


@router.delete("/api/factories/{factory_id}", status_code=204)
def delete_factory(factory_id: int, factories: Factories) -> None:
    handler.delete_factory(factories, factory_id)
