"""Tasks: list, create, get, and patch (docs/data-model-and-api.md §5.2, §6.2; docs/claude-code.md §7.5)."""

from ..domain.enums import STAGE_STATUS, Stage, Status
from ..domain.errors import Conflict, Invalid, NotFound
from ..dto.tasks import (DecisionOut, RunOut, TaskBody, TaskCreated, TaskItem, TaskOut, TaskPatch, TaskPatched,
                         TaskSubmitted)
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from .rounds import insert_round, round_summaries

COLUMNS = tuple(Status)


def latest_run(runs: RunsRepo, task_id: int) -> RunOut | None:
    run = runs.latest(task_id)
    return RunOut(**run) if run else None


def list_tasks(projects: ProjectsRepo, tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo,
               project_id: int) -> list[TaskItem]:
    """By column, then position, then id; each with its latest round's verdicts and +/−, and its latest run."""
    if not projects.exists(project_id):
        raise NotFound()
    items = []
    # ponytail: 3 queries per task; one grouped query if a board grows past a few hundred tasks
    for t in sorted(tasks.for_project(project_id), key=lambda t: (COLUMNS.index(t["status"]), t["position"], t["id"])):
        summaries = round_summaries(rounds, reviews, t["id"])
        last = summaries[-1].model_dump() if summaries else {}
        items.append(TaskItem(
            id=t["id"], title=t["title"], status=t["status"], stage=t["stage"],
            round=last.get("n"), verdicts=last.get("verdicts"),
            additions=last.get("additions"), deletions=last.get("deletions"),
            run=latest_run(runs, t["id"]),
        ))
    return items


def create_task(tasks: TasksRepo, projects: ProjectsRepo, rounds: RoundsRepo, reviews: ReviewsRepo,
                project_id: int, body: TaskBody, base_url: str) -> TaskCreated | TaskSubmitted:
    """A Backlog task, or with `submit` a standalone task straight in Review with round 1 (003 Q3)."""
    title = body.title.strip()
    if not title:
        raise Invalid("title must not be blank")
    status, stage, actor = (Status.REVIEW, Stage.HUMAN_REVIEW, "app") if body.submit else (Status.BACKLOG, None, "me")
    now = tasks.lock()  # the bottom position, the inserts, and the round, atomically
    if not projects.exists(project_id):
        raise NotFound()
    position = tasks.bottom_position(project_id, status)
    task_id = tasks.add(project_id, title, body.description_md, status, stage, position, now)
    tasks.add_event(task_id, actor, None, status, stage, now)
    if not body.submit:
        return TaskCreated(id=task_id, status=Status.BACKLOG)
    submitted = insert_round(rounds, reviews, task_id, body.submit)  # a refusal in here rolls the task back too
    return TaskSubmitted(task_id=task_id, **submitted, url=f"{base_url}tasks/{task_id}/review")


def get_task(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo, task_id: int) -> TaskOut:
    task = tasks.get(task_id)
    if task is None:
        raise NotFound()
    return TaskOut(
        id=task["id"], title=task["title"], status=task["status"], stage=task["stage"], branch=task["branch"],
        rounds=round_summaries(rounds, reviews, task_id),
        decisions=[DecisionOut(**d) for d in reviews.task_decisions(task_id)],
        run=latest_run(runs, task_id),
    )


def patch_task(tasks: TasksRepo, runs: RunsRepo, task_id: int, body: TaskPatch) -> TaskPatched:
    """The spec, a stage (status from §5.2, actor orchestrator), or a manual move (status and position,
    stage cleared, actor me, refused while a run is active). One event per status or stage change."""
    sent = body.model_fields_set
    if sent not in ({"spec_md"}, {"stage"}, {"status", "position"}):
        raise Invalid("send exactly one of: spec_md, stage, or status with position")
    if any(getattr(body, key) is None for key in sent):
        raise Invalid(f"{', '.join(sorted(sent))} must not be null")
    now = tasks.lock()  # the 409 check, the update, and the event commit together
    task = tasks.get(task_id)
    if task is None:
        raise NotFound()
    if body.spec_md is not None:
        tasks.set_spec(task_id, body.spec_md, now)
        return TaskPatched(id=task_id, status=task["status"], stage=task["stage"])
    if body.stage is not None:
        status, stage, actor = STAGE_STATUS[body.stage], body.stage, "orchestrator"
    else:  # a manual move (board drag): status and position, stage cleared
        if run := runs.running(task_id):
            raise Conflict(f"run #{run['id']} active")
        status, stage, actor = body.status, None, "me"
    done_at = None
    if status == Status.DONE:
        done_at = (task["status"] == Status.DONE and task["done_at"]) or now
    tasks.move(task_id, status, stage, done_at, now, body.position)
    if (status, stage) != (task["status"], task["stage"]):
        tasks.add_event(task_id, actor, task["status"], status, stage, now)
    return TaskPatched(id=task_id, status=status, stage=stage)
