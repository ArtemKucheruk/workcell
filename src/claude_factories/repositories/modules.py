"""SQL for the modules table (112)."""

import sqlite3

from .. import db

# 112 AC10: a module's tasks counted by status, as COUNT FILTERs over tasks t
COUNTS = ", ".join(f"COUNT(t.id) FILTER (WHERE t.status = '{s}') AS {s}"
                   for s in ("backlog", "in_progress", "review", "done"))


class ModulesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def for_project(self, project_id: int) -> list[sqlite3.Row]:
        """AC10: each module with its task counts, by name case-insensitively, then id."""
        return self.conn.execute(
            f"SELECT m.id, m.project_id, m.name, m.description_md, {COUNTS} FROM modules m"
            " LEFT JOIN tasks t ON t.module_id = m.id WHERE m.project_id = ?"
            " GROUP BY m.id ORDER BY m.name COLLATE NOCASE, m.id",
            (project_id,),
        ).fetchall()

    def no_module(self, project_id: int) -> sqlite3.Row:
        """AC10: the counts of the project's tasks with no module."""
        return self.conn.execute(
            f"SELECT {COUNTS} FROM tasks t WHERE t.project_id = ? AND t.module_id IS NULL", (project_id,)
        ).fetchone()

    def get(self, module_id: int) -> sqlite3.Row | None:
        """One module as for_project has it."""
        return self.conn.execute(
            f"SELECT m.id, m.project_id, m.name, m.description_md, {COUNTS} FROM modules m"
            " LEFT JOIN tasks t ON t.module_id = m.id WHERE m.id = ? GROUP BY m.id",
            (module_id,),
        ).fetchone()

    def by_name(self, project_id: int, name: str) -> int | None:
        """The id of the project's module named `name` in any case (AC6), else None."""
        row = self.conn.execute(
            "SELECT id FROM modules WHERE project_id = ? AND name = ? COLLATE NOCASE", (project_id, name)
        ).fetchone()
        return None if row is None else row[0]

    def add(self, project_id: int, name: str, description_md: str) -> int:
        return self.conn.execute(
            "INSERT INTO modules (project_id, name, description_md, created_at) VALUES (?, ?, ?, ?)",
            (project_id, name, description_md, db.now()),
        ).lastrowid

    def update(self, module_id: int, fields: dict) -> None:
        """Sets `fields`, whose keys are `name` and/or `description_md`."""
        sets = ", ".join(f"{column} = :{column}" for column in fields)
        self.conn.execute(f"UPDATE modules SET {sets} WHERE id = :id", fields | {"id": module_id})

    def delete(self, module_id: int) -> bool:
        """AC9: tasks.module_id's ON DELETE SET NULL clears it on the module's tasks. False if there is no such
        module."""
        return self.conn.execute("DELETE FROM modules WHERE id = ?", (module_id,)).rowcount > 0
