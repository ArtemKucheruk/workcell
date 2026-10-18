from pydantic import BaseModel


class WorkspaceOut(BaseModel):
    id: int
    name: str
    projects: int
