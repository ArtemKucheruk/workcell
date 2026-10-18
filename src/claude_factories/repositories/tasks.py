"""SQL for the tasks and events tables."""

import sqlite3

from .. import db


class TasksRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def lock(self) -> str:
        """035 Q4: BEGIN IMMEDIATE, SQLite's write lock, so a handler's checks and writes commit together.
        Returns db.now(), the timestamp those writes share, since handlers can't import db."""
        self.conn.execute("BEGIN IMMEDIATE")
        return db.now()

    def get(self, task_id: int) -> sqlite3.Row | None:
        """The task row with its project's path, for every handler that reads one."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.description_md, t.spec_md, t.status, t.stage, t.branch, t.worktree_path,"
            " t.done_at, p.path FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.id = ?",
            (task_id,),
        ).fetchone()

    def exists(self, task_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is not None

    def for_project(self, project_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, title, status, stage, position FROM tasks WHERE project_id = ?", (project_id,)
        ).fetchall()

    def bottom_position(self, project_id: int, status: str) -> float:
        """One below the column's last card, or 1.0 in an empty column."""
        return self.conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 1.0) FROM tasks WHERE project_id = ? AND status = ?",
            (project_id, status),
        ).fetchone()[0]

    def add(self, project_id: int, title: str, description_md: str, status: str, stage: str | None,
            position: float, now: str) -> int:
        return self.conn.execute(
            "INSERT INTO tasks (project_id, title, description_md, status, stage, position, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, title, description_md, status, stage, position, now, now),
        ).lastrowid

    def set_spec(self, task_id: int, spec_md: str, now: str) -> None:
        self.conn.execute("UPDATE tasks SET spec_md = ?, updated_at = ? WHERE id = ?", (spec_md, now, task_id))

    def move(self, task_id: int, status: str, stage: str | None, done_at: str | None, now: str,
             position: float | None = None) -> None:
        """A None position keeps the stored one."""
        self.conn.execute(
            "UPDATE tasks SET status = ?, stage = ?, position = COALESCE(?, position), done_at = ?,"
            " updated_at = ? WHERE id = ?",
            (status, stage, position, done_at, now, task_id),
        )

    def add_event(self, task_id: int, actor: str, from_status: str | None, to_status: str, stage: str | None,
                  now: str) -> None:
        self.conn.execute(
            "INSERT INTO events (task_id, actor, from_status, to_status, stage, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, actor, from_status, to_status, stage, now),
        )
