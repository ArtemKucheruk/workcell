from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


class ProjectPatch(BaseModel):
    """049 Q1: any non-empty subset, applied together."""
    workspace_id: int | None = Field(None, ge=-2**63, lt=2**63)  # SQLite INTEGER bounds: a 404, not a 500
    name: str | None = None
    test_cmd: str | None = None

    @field_validator("workspace_id", "name", "test_cmd")
    @classmethod
    def not_null(cls, value):
        """048's TaskPatch.not_null: a sent null gets FastAPI's list detail; an omitted key stays None."""
        if value is None:
            raise ValueError("must not be null")
        return value


class ProjectPatched(BaseModel):
    id: int
    workspace_id: int
    name: str
    test_cmd: str | None


class ContextBody(BaseModel):
    context_md: str


class ContextOut(BaseModel):
    context_md: str
    context_html: str
    bytes: int
    max_bytes: int
