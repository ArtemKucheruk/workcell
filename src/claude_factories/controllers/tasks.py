"""docs/data-model-and-api.md §6.2: tasks."""

from fastapi import APIRouter, Request

from ..dto.tasks import TaskBody, TaskCreated, TaskDeps, TaskItem, TaskOut, TaskPatch, TaskPatched, TaskSubmitted
from ..handlers import tasks as handler
from ..server.deps import Projects, Reviews, Rounds, Runs, Tasks

router = APIRouter()


@router.get("/api/projects/{project_id}/tasks")
def list_tasks(project_id: int, projects: Projects, tasks: Tasks, rounds: Rounds, reviews: Reviews,
               runs: Runs) -> list[TaskItem]:
    return handler.list_tasks(projects, tasks, rounds, reviews, runs, project_id)


@router.post("/api/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: int, body: TaskBody, request: Request, tasks: Tasks, projects: Projects,
                rounds: Rounds, reviews: Reviews) -> TaskCreated | TaskSubmitted:
    return handler.create_task(tasks, projects, rounds, reviews, project_id, body, str(request.base_url))


@router.get("/api/tasks/{task_id}")
def get_task(task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews, runs: Runs) -> TaskOut:
    return handler.get_task(tasks, rounds, reviews, runs, task_id)


@router.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, body: TaskPatch, tasks: Tasks, runs: Runs) -> TaskPatched:
    return handler.patch_task(tasks, runs, task_id, body)


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, tasks: Tasks, runs: Runs) -> None:
    handler.delete_task(tasks, runs, task_id)


@router.put("/api/tasks/{task_id}/blocked-by/{blocker_id}")
def block(task_id: int, blocker_id: int, tasks: Tasks) -> TaskDeps:
    """094: the task page's Add, fctl task block."""
    return handler.block(tasks, task_id, blocker_id)


@router.delete("/api/tasks/{task_id}/blocked-by/{blocker_id}")
def unblock(task_id: int, blocker_id: int, tasks: Tasks) -> TaskDeps:
    """094: the task page's Remove, fctl task unblock."""
    return handler.unblock(tasks, task_id, blocker_id)
