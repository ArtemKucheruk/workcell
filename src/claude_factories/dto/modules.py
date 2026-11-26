"""112: a project's modules (docs/data-model-and-api.md §6.1)."""

from pydantic import BaseModel, field_validator


class Counts(BaseModel):
    """AC10: tasks by status."""
    backlog: int
    in_progress: int
    review: int
    done: int


class ModuleOut(BaseModel):
    """AC4: POST's and PATCH's body, and each item of the list."""
    id: int
    name: str
    description_md: str
    counts: Counts


class ModuleList(BaseModel):
    """AC10, Q3."""
    modules: list[ModuleOut]
    no_module: Counts  # the project's tasks with no module


class NewModule(BaseModel):
    name: str
    description_md: str = ""


class ModulePatch(BaseModel):
    """AC8: either or both; the handler refuses neither, and a sent null is refused here."""
    name: str | None = None
    description_md: str | None = None

    @field_validator("name", "description_md")
    @classmethod
    def not_null(cls, value: str | None) -> str:
        """A sent null gets FastAPI's list detail (422), as TaskPatch's does; an omitted key stays None."""
        if value is None:
            raise ValueError("must be a string")
        return value


class ModuleRef(BaseModel):
    """AC14: a task's module, on its responses."""
    id: int
    name: str
