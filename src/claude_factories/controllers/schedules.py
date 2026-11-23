"""docs/data-model-and-api.md §6.1: an automation's schedule (104), and the scheduler's lifespan (docs/MVP.md §4.3)."""

from contextlib import asynccontextmanager

from fastapi import APIRouter

from ..dto.schedules import NewSchedule, ScheduleOut, SchedulePatch
from ..handlers import schedules as handler
from ..server.deps import get_claude, get_git, transaction


@asynccontextmanager
async def lifespan(app):
    """AC21, AC22: included after runs, so this starts after the runs sweep and stops before stop_all. Missed times
    are moved on first, then the loop starts on the server's own port (Q4)."""
    handler.skip_missed(transaction)
    loop = handler.start_loop(transaction, get_git(), get_claude(), f"http://127.0.0.1:{app.state.port}")
    try:
        yield
    finally:
        handler.stop_loop(loop)


router = APIRouter(lifespan=lifespan)


@router.get("/api/projects/{project_id}/schedules")
def list_schedules(project_id: int) -> list[ScheduleOut]:
    return handler.list_schedules(transaction, project_id)


@router.post("/api/projects/{project_id}/schedules", status_code=201)
def create_schedule(project_id: int, body: NewSchedule) -> ScheduleOut:
    return handler.create(transaction, project_id, body)


@router.patch("/api/schedules/{schedule_id}")
def patch_schedule(schedule_id: int, body: SchedulePatch) -> ScheduleOut:
    return handler.update(transaction, schedule_id, body)


@router.delete("/api/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int) -> None:
    handler.delete(transaction, schedule_id)
