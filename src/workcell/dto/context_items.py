"""057: context cards and groups (docs/data-model-and-api.md §6.1)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, FiniteFloat, field_validator

Kind = Literal["item", "group"]
ParentId = Annotated[int | None, Field(ge=-2**63, lt=2**63)]  # SQLite INTEGER bounds: a 422, not a 500


class NewContextItem(BaseModel):
    kind: Kind = "item"
    title: str
    description: str = ""
    content_md: str = ""
    parent_id: ParentId = None


class FromPathBody(BaseModel):
    path: str
    parent_id: ParentId = None


class ContextItemPatch(BaseModel):
    """Any non-empty subset, applied together. parent_id null means top level, so only it may be sent as null."""
    title: str | None = None
    description: str | None = None
    content_md: str | None = None
    parent_id: ParentId = None
    position: FiniteFloat | None = None

    @field_validator("title", "description", "content_md", "position")
    @classmethod
    def not_null(cls, value):
        """ProjectPatch.not_null: a sent null gets FastAPI's list detail; an omitted key stays None."""
        if value is None:
            raise ValueError("must not be null")
        return value


class ContextItemOut(BaseModel):
    id: int
    parent_id: int | None
    kind: Kind
    title: str
    description: str
    content_md: str
    content_html: str
    source_path: str | None
    position: float
    created_at: str
    updated_at: str
