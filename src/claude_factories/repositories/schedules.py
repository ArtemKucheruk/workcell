"""SQL for the schedules table (104, docs/data-model-and-api.md §5.1)."""

import sqlite3

from .. import db

# a schedule with its automation's name and project, its account's label fields, and its last run as it is now
SELECT = (
    "SELECT s.id, s.factory_id, f.project_id, f.name AS automation, s.cron, s.enabled, s.account_id,"
    " a.email AS account_email, a.config_dir AS account_config_dir, s.next_run_at, s.last_run_id,"
    " r.status AS last_run_status, r.started_at AS last_run_started_at, s.last_skip, s.last_skip_at"
    " FROM schedules s JOIN factories f ON f.id = s.factory_id"
    " LEFT JOIN claude_accounts a ON a.id = s.account_id LEFT JOIN runs r ON r.id = s.last_run_id"
)


class SchedulesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def for_project(self, project_id: int) -> list[sqlite3.Row]:
        """AC10: by automation name, then id."""
        return self.conn.execute(f"{SELECT} WHERE f.project_id = ? ORDER BY f.name, s.id", (project_id,)).fetchall()

    def get(self, schedule_id: int) -> sqlite3.Row | None:
        return self.conn.execute(f"{SELECT} WHERE s.id = ?", (schedule_id,)).fetchone()

    def of_factory(self, factory_id: int) -> int | None:
        found = self.conn.execute("SELECT id FROM schedules WHERE factory_id = ?", (factory_id,)).fetchone()
        return found[0] if found else None

    def add(self, factory_id: int, cron: str, account_id: int | None, next_run_at: str) -> int:
        now = db.now()
        return self.conn.execute(
            "INSERT INTO schedules (factory_id, cron, account_id, next_run_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            (factory_id, cron, account_id, next_run_at, now, now),
        ).fetchone()[0]

    def update(self, schedule_id: int, fields: dict) -> None:
        """Sets `fields`, whose keys are cron, enabled, account_id, and next_run_at, and updated_at."""
        sets = "".join(f"{column} = :{column}, " for column in fields)
        self.conn.execute(f"UPDATE schedules SET {sets}updated_at = :now WHERE id = :id",
                          fields | {"now": db.now(), "id": schedule_id})

    def delete(self, schedule_id: int) -> bool:
        """False if there is no such schedule."""
        return self.conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,)).rowcount > 0

    def due(self, now: str) -> list[sqlite3.Row]:
        """AC14, AC15: the enabled schedules whose next_run_at has come, by next_run_at then id, with the automation's
        name for a skip's reason."""
        return self.conn.execute(
            "SELECT s.id, s.factory_id, f.name AS automation, s.cron FROM schedules s"
            " JOIN factories f ON f.id = s.factory_id"
            " WHERE s.enabled = 1 AND s.next_run_at <= ? ORDER BY s.next_run_at, s.id",
            (now,),
        ).fetchall()

    def claim(self, schedule_id: int, cron: str, now: str, next_run_at: str) -> sqlite3.Row | None:
        """Q8: moves next_run_at on, only while the schedule is still enabled, due, and on the cron that time came from;
        its account_id when claimed, else None (another tick, or a PATCH, got there first)."""
        return self.conn.execute(
            "UPDATE schedules SET next_run_at = ? WHERE id = ? AND enabled = 1 AND next_run_at <= ? AND cron = ?"
            " RETURNING account_id",
            (next_run_at, schedule_id, now, cron),
        ).fetchone()

    def record_run(self, schedule_id: int, run_id: int) -> None:
        """AC14, AC20: a started run, which clears the last skip; nothing else is written."""
        self.conn.execute("UPDATE schedules SET last_run_id = ?, last_skip = NULL, last_skip_at = NULL WHERE id = ?",
                          (run_id, schedule_id))

    def record_skip(self, schedule_id: int, reason: str, at: str) -> None:
        """AC16–AC18, AC20, Q13: only the latest skip is kept; last_run_id stays."""
        self.conn.execute("UPDATE schedules SET last_skip = ?, last_skip_at = ? WHERE id = ?",
                          (reason, at, schedule_id))

    def reschedule_missed(self, now: str) -> list[sqlite3.Row]:
        """AC21: the enabled schedules whose next_run_at has passed, as (id, cron), for skip_missed."""
        return self.conn.execute(
            "SELECT id, cron FROM schedules WHERE enabled = 1 AND next_run_at <= ? ORDER BY id", (now,)
        ).fetchall()

    def set_next(self, schedule_id: int, next_run_at: str) -> None:
        """AC21: a missed time moved on, with no run and no skip recorded."""
        self.conn.execute("UPDATE schedules SET next_run_at = ? WHERE id = ?", (next_run_at, schedule_id))
