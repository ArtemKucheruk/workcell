from typing import Literal

from pydantic import BaseModel


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
