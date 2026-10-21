from typing import Literal

from pydantic import BaseModel, FiniteFloat, field_validator

from .rounds import RoundBody, RoundSummary

# 035 Q7: Literals, not the domain enums, so a bad value's 422 keeps type "literal_error"
Stage = Literal["spec", "build", "agent_review", "approval", "rework", "human_review", "escalated"]
Status = Literal["backlog", "in_progress", "review", "done"]


class TaskBody(BaseModel):
    title: str
    description_md: str = ""
    submit: RoundBody | None = None


class TaskPatch(BaseModel):
    spec_md: str | None = None
    stage: Stage | None = None
    status: Status | None = None
    position: FiniteFloat | None = None
    title: str | None = None  # 048 Q1: the board's Edit, either or both
    description_md: str | None = None

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


class TaskItem(BaseModel):
    id: int
    title: str
    status: str
    stage: str | None
    round: int | None
    verdicts: dict[str, str] | None
    additions: int | None
    deletions: int | None
    run: RunOut | None


class DecisionOut(BaseModel):
    id: int
    round: int
    actor: str
    decision: str
    body_md: str
    created_at: str


class TaskOut(BaseModel):
    id: int
    title: str
    status: str
    stage: str | None
    branch: str | None
    rounds: list[RoundSummary]
    decisions: list[DecisionOut]
    run: RunOut | None


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
