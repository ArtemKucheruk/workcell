"""docs/data-model-and-api.md §6.1: a project's factory designs (051), and their compiled files (052)."""

from fastapi import APIRouter, Response

from ..dto.factories import FactoryDesign, FactoryFile, FactoryItem, FactoryPatch, FactoryTemplate, NewFactory
from ..dto.factory import FactoryBody, FactoryOut
from ..handlers import factories as handler
from ..server.deps import Factories, Projects, Tasks

router = APIRouter()


@router.get("/api/factory-templates")
def list_templates() -> list[FactoryTemplate]:
    return handler.list_templates()


@router.get("/api/projects/{project_id}/factories")
def list_factories(project_id: int, projects: Projects, factories: Factories) -> list[FactoryItem]:
    return handler.list_factories(projects, factories, project_id)


@router.post("/api/projects/{project_id}/factories", status_code=201)
def create_factory(project_id: int, body: NewFactory, projects: Projects, factories: Factories,
                   tasks: Tasks) -> FactoryDesign:
    return handler.create_factory(projects, factories, tasks, project_id, body.name, body.template)


@router.get("/api/factories/{factory_id}")
def get_factory(factory_id: int, factories: Factories) -> FactoryDesign:
    return handler.get_factory(factories, factory_id)


@router.put("/api/factories/{factory_id}")
def put_factory(factory_id: int, body: FactoryPatch, factories: Factories, tasks: Tasks) -> FactoryDesign:
    return handler.put_factory(factories, tasks, factory_id, body)


@router.delete("/api/factories/{factory_id}", status_code=204)
def delete_factory(factory_id: int, factories: Factories) -> None:
    handler.delete_factory(factories, factory_id)


@router.get("/api/factories/{factory_id}/files")
def factory_files(factory_id: int, factories: Factories, projects: Projects) -> list[FactoryFile]:
    return handler.factory_files(factories, projects, factory_id)


@router.get("/api/factories/{factory_id}/download")
def download_factory(factory_id: int, factories: Factories, projects: Projects) -> Response:
    filename, body = handler.download(factories, projects, factory_id)
    return Response(body, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Content-Type-Options": "nosniff"})


@router.post("/api/factories/{factory_id}/write")
def write_factory(factory_id: int, body: FactoryBody, factories: Factories, projects: Projects) -> FactoryOut:
    return handler.write_factory(factories, projects, factory_id, body.overwrite)
