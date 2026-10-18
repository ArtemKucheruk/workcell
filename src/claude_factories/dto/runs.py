from pydantic import BaseModel


class RunStarted(BaseModel):
    run_id: int
    session_id: str
    worktree: str


class RunNextOut(BaseModel):
    task_id: int
    run_id: int


class StopOut(BaseModel):
    id: int
    status: str


class LogLine(BaseModel):
    t: str  # text, tool, error, result, or raw (013 Q7)
    text: str


class LogOut(BaseModel):
    next: int
    lines: list[LogLine]
