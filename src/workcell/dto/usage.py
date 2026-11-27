"""095: GET /api/usage and the sidebar's `usage` (docs/data-model-and-api.md §6.4). No config_dir, tokens, or
credentials (AC13)."""

from pydantic import BaseModel


class UsageWindow(BaseModel):
    utilization: float  # a fraction, 0.34; 0 once reset
    resets_at: int  # epoch seconds
    state: str  # allowed, near_limit, or limited, read at the request's time (AC5)
    reset: bool  # resets_at has passed: the stored value is stale


class UsageAccount(BaseModel):
    id: int
    label: str  # the stored email, else the config dir's name (AC12)
    active: bool
    recorded_at: str | None  # the snapshot's time; this and the rest null with no snapshot yet
    run_id: int | None
    overage: bool | None
    five_hour: UsageWindow | None
    seven_day: UsageWindow | None


class UsageDay(BaseModel):
    day: str  # YYYY-MM-DD, UTC
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    runs: int


class UsageGroup(BaseModel):
    key: str  # an account label, a model, or an agent type
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    runs: int


class UsageTask(BaseModel):
    task_id: int
    title: str
    project_id: int
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int


class UsageStats(BaseModel):
    days: int  # 7 or 30
    by_day: list[UsageDay]  # oldest first, every day of the window
    by_account: list[UsageGroup]  # the largest total first, as are the next two
    by_model: list[UsageGroup]
    by_agent: list[UsageGroup]
    top_tasks: list[UsageTask]  # up to 10


class LimitedRun(BaseModel):
    run_id: int
    task_id: int
    title: str
    label: str
    ended_at: str | None


class UsageOut(BaseModel):
    accounts: list[UsageAccount]  # by id
    stats: UsageStats
    limited_runs: list[LimitedRun]  # up to 20, latest first
