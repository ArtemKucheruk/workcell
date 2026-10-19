"""docs/MVP.md §3.2: Create factory. 031: import the bootstrap factory's jobs."""

from fastapi import APIRouter

from ..dto.factory import FactoryBody, FactoryOut, ImportBody, ImportOut
from ..handlers import factory as handler
from ..handlers import factory_import
from ..server.deps import GitAdapter, Projects, Reviews, Rounds, Runs, Tasks, Transcripts

router = APIRouter()


@router.post("/api/projects/{project_id}/factory")
def create_factory(project_id: int, body: FactoryBody, projects: Projects) -> FactoryOut:
    return handler.create_factory(projects, project_id, body.overwrite)


@router.post("/api/projects/{project_id}/import-factory")
def import_factory(project_id: int, body: ImportBody, projects: Projects, tasks: Tasks, rounds: Rounds,
                   reviews: Reviews, runs: Runs, transcripts: Transcripts, git: GitAdapter) -> ImportOut:
    return factory_import.import_factory(projects, tasks, rounds, reviews, runs, transcripts, git, project_id, body.job)
