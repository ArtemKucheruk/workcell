from pydantic import BaseModel


class WorkspaceOut(BaseModel):
    id: int
    name: str
    projects: int


class WorkspaceBody(BaseModel):
    name: str


class WorkspaceCreated(BaseModel):
    id: int
    name: str
