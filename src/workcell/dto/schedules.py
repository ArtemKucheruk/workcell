"""104: an automation's schedule (docs/data-model-and-api.md §6.1)."""

from pydantic import BaseModel


class NewSchedule(BaseModel):
    """AC8: a missing or null account_id is Auto."""
    factory_id: int
    cron: str
    account_id: int | None = None


class SchedulePatch(BaseModel):
    """AC11: any of the three; one left out stays as it is. `model_fields_set` tells a null account_id (Auto) from a
    missing one."""
    cron: str | None = None
    enabled: bool | None = None
    account_id: int | None = None


class ScheduleRun(BaseModel):
    id: int
    status: str
    started_at: str


class ScheduleOut(BaseModel):
    id: int
    factory_id: int
    automation: str  # the automation's name as it is now
    cron: str
    summary: str  # lib/cron.describe's words (Q6)
    enabled: bool
    account_id: int | None  # null = Auto
    account: str | None  # the account's label, null for Auto
    next_run_at: str | None  # UTC ISO with a Z; null while paused
    last_run: ScheduleRun | None  # the last run it started, with its status now
    last_skip: str | None
    last_skip_at: str | None
