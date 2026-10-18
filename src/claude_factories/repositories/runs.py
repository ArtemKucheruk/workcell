"""SQL for the runs table: the reads 035 needs; 036 moves the rest."""

import sqlite3


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
