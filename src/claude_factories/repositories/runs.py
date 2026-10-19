"""SQL for the runs table."""

import sqlite3

from .. import db
from .tasks import days_ago


class RunsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def latest(self, task_id: int) -> sqlite3.Row | None:
        """003 Q9: the task's latest run whatever its status, so a failed one can show as stalled."""
        return self.conn.execute(
            "SELECT id, status FROM runs WHERE task_id = ? ORDER BY id DESC LIMIT 1", (task_id,)
        ).fetchone()

    def running(self, task_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT id FROM runs WHERE task_id = ? AND status = 'running'", (task_id,)
        ).fetchone()

    def any_running(self) -> sqlite3.Row | None:
        """docs/MVP.md §4.4: one run at a time, across all projects."""
        return self.conn.execute("SELECT id FROM runs WHERE status = 'running'").fetchone()

    def running_ids(self) -> list[int]:
        return [i for (i,) in self.conn.execute("SELECT id FROM runs WHERE status = 'running'")]

    def exists(self, run_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is not None

    def add(self, task_id: int, session_id: str, now: str) -> int:
        """A running row with no log path yet. Raises IntegrityError if one_active_run refuses it."""
        return self.conn.execute(
            "INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
            " VALUES (?, ?, 'running', '', ?) RETURNING id",
            (task_id, session_id, now),
        ).fetchone()[0]

    def set_log_path(self, run_id: int, log_path: str) -> None:
        self.conn.execute("UPDATE runs SET log_path = ? WHERE id = ?", (log_path, run_id))

    def set_pid(self, run_id: int, pid: int) -> None:
        self.conn.execute("UPDATE runs SET pid = ? WHERE id = ?", (pid, run_id))

    def set_exit_code(self, run_id: int, code: int) -> None:
        self.conn.execute("UPDATE runs SET exit_code = ? WHERE id = ?", (code, run_id))

    def fail(self, run_id: int, error: str) -> None:
        self.conn.execute("UPDATE runs SET status = 'failed', error = ?, ended_at = ? WHERE id = ?",
                          (error, db.now(), run_id))

    def finish(self, run_id: int, status: str, error: str | None, session_id: str | None,
               now: str | None = None) -> None:
        """012 Q10: the outcome, unless Stop already ended the row (013 Q1)."""
        self.conn.execute(
            "UPDATE runs SET status = ?, error = ?, session_id = COALESCE(?, session_id), ended_at = ?"
            " WHERE id = ? AND status = 'running'",
            (status, error, session_id, now or db.now(), run_id),
        )

    def stop(self, run_id: int) -> sqlite3.Row | None:
        """013 Q1: mark a running row stopped; its (pid, exit_code), or None if it isn't running."""
        return self.conn.execute(
            "UPDATE runs SET status = 'stopped', ended_at = ? WHERE id = ? AND status = 'running'"
            " RETURNING pid, exit_code",
            (db.now(), run_id),
        ).fetchone()

    def fail_running(self, error: str) -> list[int]:
        """013 Q5: every running row failed with `error`; their ids (030: each one's transcripts get copied)."""
        return [i for (i,) in self.conn.execute(
            "UPDATE runs SET status = 'failed', error = ?, ended_at = ? WHERE status = 'running' RETURNING id",
            (error, db.now()),
        ).fetchall()]

    def log_path(self, run_id: int) -> str | None:
        found = self.conn.execute("SELECT log_path FROM runs WHERE id = ?", (run_id,)).fetchone()
        return found[0] if found else None

    def latest_detail(self, task_id: int) -> sqlite3.Row | None:
        """014: the task page's latest run."""
        return self.conn.execute(
            "SELECT id, status, error, session_id, started_at FROM runs WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()

    def started_at(self, project_id: int) -> dict[int, str]:
        """014: run id → started_at for every run of the project's tasks."""
        return dict(self.conn.execute(
            "SELECT r.id, r.started_at FROM runs r JOIN tasks t ON t.id = r.task_id WHERE t.project_id = ?",
            (project_id,),
        ).fetchall())

    def this_week(self) -> list[sqlite3.Row]:
        """The dashboard's Runs this week list (Q3), newest first."""
        return self.conn.execute(
            "SELECT r.id, r.status, r.started_at, t.id AS task_id, t.title, p.id AS project_id, p.name AS project"
            " FROM runs r JOIN tasks t ON t.id = r.task_id JOIN projects p ON p.id = t.project_id"
            f" WHERE r.started_at >= {days_ago(7)} ORDER BY r.started_at DESC, r.id DESC"
        ).fetchall()
