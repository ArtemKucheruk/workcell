from typing import Literal

from pydantic import BaseModel, FiniteFloat, computed_field, field_validator

from .modules import ModuleRef
from .rounds import RoundBody, RoundSummary

# 035 Q7: Literals, not the domain enums, so a bad value's 422 keeps type "literal_error"
Stage = Literal["spec", "build", "agent_review", "approval", "rework", "human_review", "escalated"]
Status = Literal["backlog", "in_progress", "review", "done"]


class TaskBody(BaseModel):
    title: str
    description_md: str = ""
    submit: RoundBody | None = None
    blocked_by: list[int] = []  # 094 AC10: the tasks it waits on, each stored once
    module_id: int | None = None  # 112 AC11: one of the project's modules; omitted or null = none


class Dep(BaseModel):
    """094: a task on the other side of a link."""
    id: int
    title: str
    status: str


class TaskDeps(BaseModel):
    """094: PUT and DELETE /api/tasks/{id}/blocked-by/{blocker}'s body, and the link fields of every task."""
    id: int
    blocked_by: list[Dep]  # every link, done blockers too, by id
    blocks: list[int]  # the dependents' ids, ascending

    @computed_field
    def blocked(self) -> bool:
        """Worked out on read, never stored: while any blocker isn't done."""
        return any(d.status != "done" for d in self.blocked_by)


class TaskPatch(BaseModel):
    spec_md: str | None = None
    stage: Stage | None = None
    status: Status | None = None
    position: FiniteFloat | None = None
    title: str | None = None  # 048 Q1: the board's Edit, either or both
    description_md: str | None = None
    module_id: int | None = None  # 112 AC13, Q4: alone; a sent null clears the module

    @field_validator("title", "description_md")
    @classmethod
    def not_null(cls, value: str | None) -> str:
        """048: a sent null gets FastAPI's list detail, as a non-string does; an omitted key stays None."""
        if value is None:
            raise ValueError("must be a string")
        return value


class RunOut(BaseModel):
    id: int
    status: str


class TaskItem(TaskDeps):
    title: str
    status: str
    stage: str | None
    round: int | None
    verdicts: dict[str, str] | None
    additions: int | None
    deletions: int | None
    run: RunOut | None
    module: ModuleRef | None  # 112 AC14


class DecisionOut(BaseModel):
    id: int
    round: int
    actor: str
    decision: str
    body_md: str
    created_at: str


class TaskOut(TaskDeps):
    title: str
    status: str
    stage: str | None
    branch: str | None
    rounds: list[RoundSummary]
    decisions: list[DecisionOut]
    run: RunOut | None
    module: ModuleRef | None  # 112 AC14


class TaskCreated(BaseModel):
    id: int
    status: str


class TaskSubmitted(BaseModel):
    task_id: int
    round: int
    files_changed: int
    additions: int
    deletions: int
    url: str


class TaskPatched(BaseModel):
    id: int
    status: str
    stage: str | None
