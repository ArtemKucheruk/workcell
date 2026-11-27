"""SQL for the context_items table (057): a project's context cards and their one level of groups."""

import sqlite3

from .. import db

COLUMNS = ("id, project_id, parent_id, kind, title, description, content_md, source_path, position, created_at,"
           " updated_at")


class ContextItemsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def for_project(self, project_id: int) -> list[sqlite3.Row]:
        """Every card and group, groups' cards included, by position, then id."""
        return self.conn.execute(
            f"SELECT {COLUMNS} FROM context_items WHERE project_id = ? ORDER BY position, id", (project_id,)
        ).fetchall()

    def get(self, item_id: int) -> sqlite3.Row | None:
        return self.conn.execute(f"SELECT {COLUMNS} FROM context_items WHERE id = ?", (item_id,)).fetchone()

    def is_group(self, project_id: int, item_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM context_items WHERE id = ? AND project_id = ? AND kind = 'group'", (item_id, project_id)
        ).fetchone() is not None

    def next_position(self, project_id: int, parent_id: int | None) -> float:
        """Q11: one past the last of the list under parent_id (NULL = top level), or 1.0 in an empty one."""
        return self.conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 1.0) FROM context_items WHERE project_id = ? AND parent_id IS ?",
            (project_id, parent_id),
        ).fetchone()[0]

    def add(self, project_id: int, parent_id: int | None, kind: str, title: str, description: str, content_md: str,
            source_path: str | None, now: str | None = None) -> int:
        """Last in its parent's list."""
        now = now or db.now()
        return self.conn.execute(
            "INSERT INTO context_items (project_id, parent_id, kind, title, description, content_md, source_path,"
            " position, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, parent_id, kind, title, description, content_md, source_path,
             self.next_position(project_id, parent_id), now, now),
        ).lastrowid

    def update(self, item_id: int, fields: dict) -> None:
        """Sets `fields`, whose keys are ContextItemPatch's columns, and updated_at."""
        sets = "".join(f"{column} = :{column}, " for column in fields)
        self.conn.execute(f"UPDATE context_items SET {sets}updated_at = :now WHERE id = :id",
                          fields | {"now": db.now(), "id": item_id})

    def delete(self, item_id: int) -> bool:
        """False if there is no such item. A group's cards go with it (ON DELETE CASCADE)."""
        return self.conn.execute("DELETE FROM context_items WHERE id = ?", (item_id,)).rowcount > 0

    def total_bytes(self, project_id: int) -> int:
        """Q4: the UTF-8 bytes of the project's context_md plus every card's content_md."""
        return self.conn.execute(
            "SELECT length(CAST(context_md AS BLOB)) + (SELECT COALESCE(SUM(length(CAST(content_md AS BLOB))), 0)"
            " FROM context_items WHERE project_id = :id) FROM projects WHERE id = :id",
            {"id": project_id},
        ).fetchone()[0]
