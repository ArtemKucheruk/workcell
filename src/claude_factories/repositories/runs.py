"""SQL for the runs table."""

import sqlite3

from .. import db
from .tasks import days_ago

# 102: a run's task or automation, and the project of whichever it has
OWNERS = ("FROM runs r LEFT JOIN tasks t ON t.id = r.task_id LEFT JOIN factories f ON f.id = r.factory_id"
          " LEFT JOIN projects p ON p.id = COALESCE(t.project_id, f.project_id)")
TITLE = "COALESCE(t.title, f.name) AS title"


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
        """Some running run, for 056's account switch and Disconnect, which stay refused while any run is
        active (096: out of scope)."""
        return self.conn.execute("SELECT id FROM runs WHERE status = 'running'").fetchone()

    def running_ids(self) -> list[int]:
        return [i for (i,) in self.conn.execute("SELECT id FROM runs WHERE status = 'running'")]

    def running_tasks(self) -> list[sqlite3.Row]:
        """096: every running run as (id, task_id, kind, name), by id, for the cap and its 409 detail. 102 Q7: name is
        an automation run's automation, NULL for a task run or a deleted automation."""
        return self.conn.execute(
            "SELECT r.id, r.task_id, r.kind, f.name FROM runs r LEFT JOIN factories f ON f.id = r.factory_id"
            " WHERE r.status = 'running' ORDER BY r.id").fetchall()

    def exists(self, run_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is not None

    def add(self, task_id: int | None, session_id: str, now: str, account_id: int | None = None,
            kind: str = "factory", factory_id: int | None = None, worktree_path: str | None = None) -> int:
        """A running row with no log path yet, in account `account_id` (096 Q5). Raises IntegrityError if
        one_run_per_task refuses it (the task already has a running run). 102: an automation run is kind
        `automation` with no task, its automation's `factory_id`, and its own `worktree_path`; trigger stays
        manual (Q17)."""
        return self.conn.execute(
            "INSERT INTO runs (task_id, session_id, status, log_path, started_at, account_id, kind, factory_id,"
            " worktree_path) VALUES (?, ?, 'running', '', ?, ?, ?, ?, ?) RETURNING id",
            (task_id, session_id, now, account_id, kind, factory_id, worktree_path),
        ).fetchone()[0]

    def imported(self, task_id: int, session_id: str, started_at: str, ended_at: str | None) -> int:
        """031 Q8: the task's run for a bootstrap session, added once as succeeded with no log, its times kept
        current on a rerun; its id."""
        found = self.conn.execute(
            "SELECT id FROM runs WHERE task_id = ? AND session_id = ? ORDER BY id LIMIT 1", (task_id, session_id)
        ).fetchone()
        if found:
            self.conn.execute("UPDATE runs SET started_at = ?, ended_at = ? WHERE id = ?",
                              (started_at, ended_at, found[0]))
            return found[0]
        return self.conn.execute(
            "INSERT INTO runs (task_id, session_id, status, log_path, started_at, ended_at)"
            " VALUES (?, ?, 'succeeded', '', ?, ?) RETURNING id",
            (task_id, session_id, started_at, ended_at),
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

    def set_failed_error(self, run_id: int, error: str) -> None:
        """097 AC25: a failed run's error replaced; any other status is left alone."""
        self.conn.execute("UPDATE runs SET error = ? WHERE id = ? AND status = 'failed'", (error, run_id))

    def stop(self, run_id: int) -> sqlite3.Row | None:
        """013 Q1: mark a running row stopped; its (pid, exit_code), or None if it isn't running."""
        return self.conn.execute(
            "UPDATE runs SET status = 'stopped', ended_at = ? WHERE id = ? AND status = 'running'"
            " RETURNING pid, exit_code",
            (db.now(), run_id),
        ).fetchone()

    def fail_running(self, error: str) -> list[tuple[int, str]]:
        """013 Q5: every running row failed with `error`; their (id, log_path) (030: each one's transcripts get
        copied; 095 AC8: its log read for the usage snapshot)."""
        return [(i, path) for i, path in self.conn.execute(
            "UPDATE runs SET status = 'failed', error = ?, ended_at = ? WHERE status = 'running'"
            " RETURNING id, log_path",
            (error, db.now()),
        ).fetchall()]

    def log_path(self, run_id: int) -> str | None:
        found = self.conn.execute("SELECT log_path FROM runs WHERE id = ?", (run_id,)).fetchone()
        return found[0] if found else None

    def latest_detail(self, task_id: int) -> sqlite3.Row | None:
        """014: the task page's latest run; 097 AC22, AC24: with its account's id, config_dir, and email (NULL for
        none or a deleted one)."""
        return self.conn.execute(
            "SELECT r.id, r.status, r.error, r.session_id, r.started_at, a.id AS account_id, a.config_dir, a.email"
            " FROM runs r LEFT JOIN claude_accounts a ON a.id = r.account_id"
            " WHERE r.task_id = ? ORDER BY r.id DESC LIMIT 1",
            (task_id,),
        ).fetchone()

    def latest_log(self, task_id: int) -> sqlite3.Row | None:
        """089: the task's latest run's status and log path."""
        return self.conn.execute(
            "SELECT id, status, log_path FROM runs WHERE task_id = ? ORDER BY id DESC LIMIT 1", (task_id,)
        ).fetchone()

    def for_factory(self, factory_id: int) -> list[sqlite3.Row]:
        """103 AC1, AC2: the automation's runs, started_at newest first then id, each with its account's email and
        config_dir (NULL for none or a deleted one)."""
        return self.conn.execute(
            "SELECT r.id, r.status, r.trigger, r.started_at, r.ended_at, r.error, a.email, a.config_dir"
            " FROM runs r LEFT JOIN claude_accounts a ON a.id = r.account_id"
            " WHERE r.factory_id = ? ORDER BY r.started_at DESC, r.id DESC",
            (factory_id,),
        ).fetchall()

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

    def running_rows(self) -> list[sqlite3.Row]:
        """053: the Agents page's running runs (096: up to the cap, one per task), newest first; round is the task's highest n
        (Q4). 102 AC16: an automation run's title is its automation's name and its project that one's; NULL for a
        deleted automation (the handler words it)."""
        return self.conn.execute(
            f"SELECT r.id, r.kind, r.task_id, r.factory_id, {TITLE}, p.id AS project_id, p.name AS project, t.stage,"
            " (SELECT MAX(n) FROM rounds WHERE task_id = t.id) AS round, r.started_at, r.log_path"
            f" {OWNERS} WHERE r.status = 'running' ORDER BY r.started_at DESC, r.id DESC"
        ).fetchall()

    def recent(self, limit: int) -> list[sqlite3.Row]:
        """053 Q5: ended runs by ended_at newest first (sqlite sorts a null ended_at last on DESC), then id; Q6:
        each one's transcripts rows. 102 AC17: automation runs as in running_rows."""
        return self.conn.execute(
            f"SELECT r.id, r.kind, r.task_id, r.factory_id, {TITLE}, p.id AS project_id, p.name AS project,"
            " r.status, r.error, r.started_at, r.ended_at,"
            " (SELECT COUNT(*) FROM transcripts WHERE run_id = r.id) AS transcripts"
            f" {OWNERS} WHERE r.status != 'running' ORDER BY r.ended_at DESC, r.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
