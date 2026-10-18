"""docs/MVP.md §3.2: Create factory."""

from fastapi import APIRouter

from ..dto.factory import FactoryBody, FactoryOut
from ..handlers import factory as handler
from ..server.deps import Projects

router = APIRouter()


@router.post("/api/projects/{project_id}/factory")
def create_factory(project_id: int, body: FactoryBody, projects: Projects) -> FactoryOut:
    return handler.create_factory(projects, project_id, body.overwrite)
