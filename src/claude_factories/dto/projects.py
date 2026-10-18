from typing import Literal

from pydantic import BaseModel, Field


class ConnectBody(BaseModel):
    path: str
    workspace: str
    name: str
    remote_url: str | None = None
    default_branch: str
    test_cmd: str | None = None


class ConnectOut(BaseModel):
    id: int
    created: bool
    url: str


class ProjectOut(BaseModel):
    id: int
    name: str
    default_branch: str
    factory: Literal["ready", "uncommitted", "none"]


class MoveBody(BaseModel):
    workspace_id: int = Field(ge=-2**63, lt=2**63)  # SQLite INTEGER bounds: a 404, not an OverflowError's 500


class MoveOut(BaseModel):
    id: int
    workspace_id: int


class ContextBody(BaseModel):
    context_md: str


class ContextOut(BaseModel):
    context_md: str
    context_html: str
    bytes: int
    max_bytes: int
