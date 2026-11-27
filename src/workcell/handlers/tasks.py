"""Tasks: list, create, get, patch, delete, and 094's links between them (docs/data-model-and-api.md §5.2, §6.2;
docs/claude-code.md §7.5)."""

from ..domain.enums import STAGE_STATUS, Stage, Status
from ..domain.errors import Conflict, Invalid, NotFound
from ..dto.modules import ModuleRef
from ..dto.tasks import (DecisionOut, Dep, RunOut, TaskBody, TaskCreated, TaskDeps, TaskItem, TaskOut, TaskPatch,
                         TaskPatched, TaskSubmitted)
from ..repositories.modules import ModulesRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from .modules import check_module
from .rounds import insert_round, round_summaries

COLUMNS = tuple(Status)


def module_ref(row) -> ModuleRef | None:
    """112 AC14: a row's module_id and module (its name) as {id, name}, or None."""
    return None if row["module_id"] is None else ModuleRef(id=row["module_id"], name=row["module"])


def latest_run(runs: RunsRepo, task_id: int) -> RunOut | None:
    run = runs.latest(task_id)
    return RunOut(**run) if run else None


def links(tasks: TasksRepo, task_id: int) -> dict:
    """094 AC8: the task's blocked_by and blocks, as TaskDeps takes them."""
    return {"blocked_by": [Dep(**b) for b in tasks.blockers(task_id)],
            "blocks": [d["id"] for d in tasks.dependents(task_id)]}


def list_tasks(projects: ProjectsRepo, tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo,
               project_id: int) -> list[TaskItem]:
    """By column, then position, then id; each with its latest round's verdicts and +/−, its latest run, and its
    links (094, from one query for the project)."""
    if not projects.exists(project_id):
        raise NotFound()
    blocked_by: dict[int, list[Dep]] = {}
    blocks: dict[int, list[int]] = {}
    for link in tasks.project_links(project_id):  # by task_id, then blocker id: both lists come out sorted
        blocked_by.setdefault(link["task_id"], []).append(Dep(**link))
        blocks.setdefault(link["id"], []).append(link["task_id"])
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
            blocked_by=blocked_by.get(t["id"], []), blocks=blocks.get(t["id"], []), module=module_ref(t),
        ))
    return items


def check_blocker(tasks: TasksRepo, project_id: int, blocker_id: int) -> None:
    """094 AC5: a blocker is a task of the same project."""
    blocker = tasks.get(blocker_id)
    if blocker is None:
        raise Invalid(f"no task #{blocker_id}")
    if blocker["project_id"] != project_id:
        raise Invalid(f"#{blocker_id} is in another project; a task waits only on tasks of its own project")


def create_task(tasks: TasksRepo, projects: ProjectsRepo, rounds: RoundsRepo, reviews: ReviewsRepo,
                modules: ModulesRepo, project_id: int, body: TaskBody, base_url: str) -> TaskCreated | TaskSubmitted:
    """A Backlog task, or with `submit` a standalone task straight in Review with round 1 (003 Q3). 094 AC10: with
    its `blocked_by` links, each checked before the task is added, and a repeated id stored once. 112 AC11, AC12:
    with its module, one of the project's, checked before the task is added."""
    title = body.title.strip()
    if not title:
        raise Invalid("title must not be blank")
    status, stage, actor = (Status.REVIEW, Stage.HUMAN_REVIEW, "app") if body.submit else (Status.BACKLOG, None, "me")
    now = tasks.lock()  # the bottom position, the inserts, and the round, atomically
    if not projects.exists(project_id):
        raise NotFound()
    blockers = list(dict.fromkeys(body.blocked_by))
    for blocker_id in blockers:  # a new task has no dependents, so neither a self link nor a cycle can arise
        check_blocker(tasks, project_id, blocker_id)
    if body.module_id is not None:
        check_module(modules, project_id, body.module_id)
    position = tasks.bottom_position(project_id, status)
    task_id = tasks.add(project_id, title, body.description_md, status, stage, position, now, body.module_id)
    tasks.add_event(task_id, actor, None, status, stage, now)
    for blocker_id in blockers:
        tasks.link(task_id, blocker_id)
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
        run=latest_run(runs, task_id), module=module_ref(task), **links(tasks, task_id),
    )


def cycle(tasks: TasksRepo, project_id: int, task_id: int, blocker_id: int) -> list[int] | None:
    """094 AC6: the shortest chain blocker → … → task along the project's waits-on links, which the new link
    task → blocker would close; None when there is none."""
    waits_on: dict[int, list[int]] = {}
    for link in tasks.project_links(project_id):
        waits_on.setdefault(link["task_id"], []).append(link["id"])
    chains, todo = {blocker_id: [blocker_id]}, [blocker_id]
    while todo:
        at = todo.pop(0)
        if at == task_id:
            return chains[at]
        for nxt in waits_on.get(at, ()):
            if nxt not in chains:
                chains[nxt] = chains[at] + [nxt]
                todo.append(nxt)
    return None


def block(tasks: TasksRepo, task_id: int, blocker_id: int) -> TaskDeps:
    """094: task_id waits on blocker_id from now on. Refused for itself, an unknown task, another project's task,
    or a cycle. Q2: a link that's there already is a 200 with the same body."""
    tasks.lock()  # the cycle walk and the insert commit together
    task = tasks.get(task_id)
    if task is None:
        raise NotFound(f"Task #{task_id} not found")
    if blocker_id == task_id:
        raise Invalid(f"#{task_id} can't wait on itself")
    check_blocker(tasks, task["project_id"], blocker_id)
    if chain := cycle(tasks, task["project_id"], task_id, blocker_id):
        raise Invalid(f"cycle: #{task_id} waits on " + ", which waits on ".join(f"#{n}" for n in chain))
    tasks.link(task_id, blocker_id)
    return TaskDeps(id=task_id, **links(tasks, task_id))


def unblock(tasks: TasksRepo, task_id: int, blocker_id: int) -> TaskDeps:
    """094 Q3: the link goes; one that isn't there is a 404."""
    if not tasks.exists(task_id):
        raise NotFound(f"Task #{task_id} not found")
    if not tasks.unlink(task_id, blocker_id):
        raise NotFound(f"#{task_id} is not blocked by #{blocker_id}")
    return TaskDeps(id=task_id, **links(tasks, task_id))


PATCH_GROUPS = ({"spec_md"}, {"stage"}, {"status", "position"}, {"title"}, {"description_md"},
                {"title", "description_md"}, {"module_id"})
EDIT = {"title", "description_md"}


def patch_task(tasks: TasksRepo, runs: RunsRepo, modules: ModulesRepo, task_id: int, body: TaskPatch) -> TaskPatched:
    """The spec, a stage (status from §5.2, actor orchestrator), a manual move (status and position,
    stage cleared, actor me, refused while a run is active), an edit (title and/or description, any status,
    048 Q1–Q3), or 112's module (null clears it). One event per status or stage change."""
    sent = body.model_fields_set
    if sent not in PATCH_GROUPS:
        raise Invalid("send exactly one of: spec_md, stage, status with position, title and/or description_md,"
                      " or module_id")
    if sent == {"module_id"}:
        return set_module(tasks, modules, task_id, body.module_id)
    if any(getattr(body, key) is None for key in sent):
        raise Invalid(f"{', '.join(sorted(sent))} must not be null")
    title = None if body.title is None else body.title.strip()
    if title == "":
        raise Invalid("title must not be blank")
    now = tasks.lock()  # the 409 check, the update, and the event commit together
    task = tasks.get(task_id)
    if task is None:
        raise NotFound()
    if sent <= EDIT:  # 048 Q2: status and stage stay, so no event
        tasks.edit(task_id, title, body.description_md, now)
        return TaskPatched(id=task_id, status=task["status"], stage=task["stage"])
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


def set_module(tasks: TasksRepo, modules: ModulesRepo, task_id: int, module_id: int | None) -> TaskPatched:
    """112 AC13: the task's module, one of its project's, or none. Q7: status and stage stay, so no event."""
    now = tasks.lock()  # the check and the update commit together
    task = tasks.get(task_id)
    if task is None:
        raise NotFound()
    if module_id is not None:
        check_module(modules, task["project_id"], module_id)
    tasks.set_module(task_id, module_id, now)
    return TaskPatched(id=task_id, status=task["status"], stage=task["stage"])


def delete_task(tasks: TasksRepo, runs: RunsRepo, task_id: int) -> None:
    """048: the task and every row it owns (§5.1), refused while a run is active (§5.2). Nothing on disk."""
    tasks.lock()  # the 409 check and the deletes commit together
    if not tasks.exists(task_id):
        raise NotFound(f"Task #{task_id} not found")
    if run := runs.running(task_id):
        raise Conflict(f"run #{run['id']} active")
    tasks.delete(task_id)
