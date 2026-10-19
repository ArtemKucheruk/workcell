"""SQL for the workspaces table."""

import sqlite3

from .. import db


class WorkspacesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def all(self) -> list[sqlite3.Row]:
        """Every workspace by name, with its project count."""
        return self.conn.execute(
            "SELECT w.id, w.name, COUNT(p.id) AS projects FROM workspaces w"
            " LEFT JOIN projects p ON p.workspace_id = w.id GROUP BY w.id ORDER BY w.name"
        ).fetchall()

    def get_or_create(self, name: str, now: str | None = None) -> int:
        self.conn.execute("INSERT OR IGNORE INTO workspaces (name, created_at) VALUES (?, ?)", (name, now or db.now()))
        return self.conn.execute("SELECT id FROM workspaces WHERE name = ?", (name,)).fetchone()[0]

    def exists(self, workspace_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone() is not None

    def get(self, workspace_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT id, name FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
