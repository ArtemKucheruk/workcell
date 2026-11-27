"""104: an automation's schedule, and the scheduler that starts it (docs/data-model-and-api.md §6.1, docs/MVP.md §4.3
The scheduler runs inside the backend).

Like the run handlers, these take `tx`, server/deps.py's transaction(), since the tick runs outside any request."""

import logging
import threading
import time
from datetime import UTC, datetime

from ..adapters.claude import Claude
from ..adapters.git import Git
from ..domain.errors import Conflict, DomainError, Invalid, NotFound
from ..dto.schedules import NewSchedule, ScheduleOut, SchedulePatch, ScheduleRun
from ..lib import cron
from ..repositories.claude_accounts import ClaudeAccountsRepo
from ..repositories.factories import FactoriesRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.runs import RunsRepo
from ..repositories.schedules import SchedulesRepo
from ..repositories.tasks import TasksRepo
from . import runs
from .usage import label

log = logging.getLogger(__name__)
TICK = 60.0  # AC22: seconds between ticks, on the minute
STOP_WAIT = 10.0  # shutdown waits this long for a tick mid-start, then leaves the daemon thread behind


def iso(t: float) -> str:
    """Q2: an epoch time as the DB's UTC ISO with a Z."""
    return datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def out(row) -> ScheduleOut:
    last = (ScheduleRun(id=row["last_run_id"], status=row["last_run_status"], started_at=row["last_run_started_at"])
            if row["last_run_status"] is not None else None)
    account = label(row["account_email"], row["account_config_dir"]) if row["account_id"] is not None else None
    return ScheduleOut(id=row["id"], factory_id=row["factory_id"], automation=row["automation"], cron=row["cron"],
                       summary=cron.describe(row["cron"]), enabled=bool(row["enabled"]), account_id=row["account_id"],
                       account=account, next_run_at=row["next_run_at"], last_run=last, last_skip=row["last_skip"],
                       last_skip_at=row["last_skip_at"])


def need_account(conn, account_id: int | None) -> None:
    """AC9, AC11: an explicit account must exist; None is Auto."""
    if account_id is not None and ClaudeAccountsRepo(conn).get(account_id) is None:
        raise Invalid(f"no Claude account #{account_id}")


def list_schedules(tx, project_id: int) -> list[ScheduleOut]:
    """AC10: the project's schedules, by automation name, then id."""
    with tx() as conn:
        if not ProjectsRepo(conn).exists(project_id):
            raise NotFound(f"Project #{project_id} not found")
        return [out(row) for row in SchedulesRepo(conn).for_project(project_id)]


def create(tx, project_id: int, body: NewSchedule, now: float | None = None) -> ScheduleOut:
    """AC8, AC9's order: the project, the factory (unknown or another project's), a workflow, a second schedule, the
    cron, then the account. Checks and the insert commit together; a refusal writes nothing."""
    now = time.time() if now is None else now
    with tx() as conn:
        TasksRepo(conn).lock()
        if not ProjectsRepo(conn).exists(project_id):
            raise NotFound(f"Project #{project_id} not found")
        factory = FactoriesRepo(conn).get(body.factory_id)
        if factory is None or factory["project_id"] != project_id:
            raise NotFound(f"Factory #{body.factory_id} not found")
        if factory["kind"] != "automation":
            raise Conflict(f"{factory['name']} is a workflow; only automations can be scheduled")
        schedules = SchedulesRepo(conn)
        if schedules.of_factory(body.factory_id) is not None:
            raise Conflict(f"{factory['name']} already has a schedule; edit it instead")
        expr = cron.parse(body.cron).text
        need_account(conn, body.account_id)
        schedule_id = schedules.add(body.factory_id, expr, body.account_id, iso(cron.next_after(expr, now)))
        return out(schedules.get(schedule_id))


def update(tx, schedule_id: int, patch: SchedulePatch, now: float | None = None) -> ScheduleOut:
    """AC11: the fields sent, a null account_id being Auto. Pausing clears next_run_at; resuming, or a new cron while
    enabled, sets it from now. A refusal changes nothing. A null cron or enabled is left as it is."""
    now = time.time() if now is None else now
    sent = patch.model_fields_set
    with tx() as conn:
        TasksRepo(conn).lock()
        schedules = SchedulesRepo(conn)
        row = schedules.get(schedule_id)
        if row is None:
            raise NotFound(f"schedule #{schedule_id} not found")
        fields = {}
        if patch.cron is not None:
            fields["cron"] = cron.parse(patch.cron).text
        if "account_id" in sent:
            need_account(conn, patch.account_id)
            fields["account_id"] = patch.account_id
        if patch.enabled is not None:
            fields["enabled"] = int(patch.enabled)
        enabled = fields.get("enabled", row["enabled"])
        expr = fields.get("cron", row["cron"])
        if not enabled:
            fields["next_run_at"] = None
        elif not row["enabled"] or expr != row["cron"]:
            fields["next_run_at"] = iso(cron.next_after(expr, now))
        if fields:
            schedules.update(schedule_id, fields)
        return out(schedules.get(schedule_id))


def delete(tx, schedule_id: int) -> None:
    """AC12: the schedule only; the automation and its runs stay."""
    with tx() as conn:
        if not SchedulesRepo(conn).delete(schedule_id):
            raise NotFound(f"schedule #{schedule_id} not found")


# --- The scheduler ------------------------------------------------------------------------------------------


def tick(tx, git: Git, claude: Claude, base_url: str, now: float | None = None) -> None:
    """AC14–AC20: every due, enabled schedule, in turn. One schedule's exception is logged and recorded as its skip,
    so the others still go (AC22)."""
    now = time.time() if now is None else now
    with tx() as conn:
        due = SchedulesRepo(conn).due(iso(now))
    for row in due:
        try:
            attempt(tx, git, claude, base_url, row, now)
        except Exception as e:  # noqa: BLE001 — anything at all, so the loop and the other schedules go on
            log.exception("schedule #%s failed", row["id"])
            try:
                with tx() as conn:
                    SchedulesRepo(conn).record_skip(row["id"], f"can't start: {e}", iso(now))
            except Exception:  # noqa: BLE001
                log.exception("schedule #%s: recording its skip failed", row["id"])


def attempt(tx, git: Git, claude: Claude, base_url: str, row, now: float) -> None:
    """Q8: claim first (next_run_at moved on, while still enabled, due, and on the same cron), so two ticks never start
    one time twice; then the automation's own running run (AC16), then start_automation's checks and start. After the
    start only the outcome is written (AC20). Q9: any DomainError, a spawn's 500 included, is a skip with its detail."""
    stamp = iso(now)
    following = iso(cron.next_after(row["cron"], now))
    with tx() as conn:
        claimed = SchedulesRepo(conn).claim(row["id"], row["cron"], stamp, following)
    if claimed is None:
        return
    with tx() as conn:
        running = RunsRepo(conn).running_for_factory(row["factory_id"])
    if running is not None:
        skip(tx, row["id"], f"run #{running['id']} of {row['automation']} is still running", stamp)
        return
    try:
        started = runs.start_automation(tx, git, claude, row["factory_id"], base_url, claimed["account_id"],
                                        trigger="schedule")
    except DomainError as e:
        skip(tx, row["id"], e.detail, stamp)
        return
    with tx() as conn:
        SchedulesRepo(conn).record_run(row["id"], started.run_id)


def skip(tx, schedule_id: int, reason: str, at: str) -> None:
    with tx() as conn:
        SchedulesRepo(conn).record_skip(schedule_id, reason, at)


def skip_missed(tx, now: float | None = None) -> None:
    """AC21: at startup, times missed while the app was down aren't caught up: each enabled schedule whose
    next_run_at has passed gets the next time from now, with no run and no skip."""
    now = time.time() if now is None else now
    with tx() as conn:
        schedules = SchedulesRepo(conn)
        for row in schedules.reschedule_missed(iso(now)):
            schedules.set_next(row["id"], iso(cron.next_after(row["cron"], now)))


def start_loop(tx, git: Git, claude: Claude, base_url: str, interval: float = TICK):
    """AC22, Q4, Q10: a daemon thread calling tick at the start of each `interval` (each minute), until stop_loop.
    Ticks run one after another in this one thread, so a slow start delays the next tick instead of overlapping it.
    Its handle for stop_loop."""
    stop = threading.Event()

    def loop():
        while not stop.wait(interval - time.time() % interval):
            try:
                tick(tx, git, claude, base_url)
            except Exception:  # noqa: BLE001 — a broken tick (the DB, say) must not end the loop
                log.exception("scheduler tick failed")

    thread = threading.Thread(target=loop, name="scheduler", daemon=True)
    thread.start()
    return stop, thread


def stop_loop(handle) -> None:
    """AC22: stops the loop; None (the tests' no-op start_loop) is nothing to stop. ponytail: a tick mid-start (wt's
    copy can take 300 s) is waited on for STOP_WAIT only; its run then belongs to a shutting-down server."""
    if handle is None:
        return
    stop, thread = handle
    stop.set()
    thread.join(STOP_WAIT)
