from typing import Literal

from pydantic import BaseModel, Field

Reviewer = Literal["security", "ux", "ui", "code"]  # 035 Q7: a Literal, so its 422 stays "literal_error"


class VerdictBody(BaseModel):
    verdict: Literal["PASS", "CHANGES"]
    body_md: str = ""


class VerdictOut(BaseModel):
    round: int
    reviewer: str
    verdict: str
    complete: str


class CommentBody(BaseModel):
    round: int | Literal["latest"] = "latest"
    author: Literal["me"] | Reviewer
    path: str | None = None
    line: int | None = Field(None, ge=1, lt=2**63)  # SQLite INTEGER bounds
    side: Literal["old", "new"] | None = None
    body_md: str


class DecisionBody(BaseModel):
    decision: Literal["APPROVE", "ESCALATE"]  # my APPROVE / CHANGES_REQUESTED go through 009's routes
    body_md: str = ""


class IdOut(BaseModel):
    id: int


class ApproveBody(BaseModel):
    body_md: str = ""  # 009 Q9: optional; neither the page nor fctl approve sends one


class ApproveOut(BaseModel):
    status: str
    commit_hint: str


class ChangesBody(BaseModel):
    body_md: str  # 009 Q9: required, and not blank


class ChangesOut(BaseModel):
    status: str
    stage: str
    run_id: int | None
