"""Task status, stage, and reviewer (docs/data-model-and-api.md §5.2)."""

from enum import StrEnum


class Status(StrEnum):  # in board column order
    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class Stage(StrEnum):
    SPEC = "spec"
    BUILD = "build"
    AGENT_REVIEW = "agent_review"
    APPROVAL = "approval"
    REWORK = "rework"
    HUMAN_REVIEW = "human_review"
    ESCALATED = "escalated"


class Reviewer(StrEnum):
    SECURITY = "security"
    UX = "ux"
    UI = "ui"
    CODE = "code"


STAGE_STATUS = {  # §5.2: the status a stage sets
    Stage.SPEC: Status.IN_PROGRESS, Stage.BUILD: Status.IN_PROGRESS, Stage.AGENT_REVIEW: Status.IN_PROGRESS,
    Stage.APPROVAL: Status.IN_PROGRESS, Stage.REWORK: Status.IN_PROGRESS,
    Stage.HUMAN_REVIEW: Status.REVIEW, Stage.ESCALATED: Status.REVIEW,
}
