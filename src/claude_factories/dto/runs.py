from pydantic import BaseModel


class RunBody(BaseModel):
    """097 AC9, AC13: POST /api/tasks/{id}/run's optional body; null or missing is Auto."""
    account_id: int | None = None


class RunStarted(BaseModel):
    run_id: int
    session_id: str
    worktree: str
    account_id: int  # 097 AC18: the account it runs in
    account: str  # its label: the stored email, else the config dir's name


class RunNextOut(BaseModel):
    task_id: int
    run_id: int
    account_id: int  # 097 AC19, as RunStarted's
    account: str


class StopOut(BaseModel):
    id: int
    status: str


class LogLine(BaseModel):
    t: str  # text, tool, error, result, or raw (013 Q7)
    text: str


class LogOut(BaseModel):
    next: int
    lines: list[LogLine]
