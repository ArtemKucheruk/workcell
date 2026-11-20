"""SQL for the factories table (051)."""

import sqlite3

from .. import db


class FactoriesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def for_project(self, project_id: int) -> list[sqlite3.Row]:
        """The Factories list: by name, then id (Q7), with the node count read from the stored JSON."""
        return self.conn.execute(
            "SELECT id, name, kind, json_array_length(graph, '$.nodes') AS nodes, created_at, updated_at"
            " FROM factories WHERE project_id = ? ORDER BY name, id",
            (project_id,),
        ).fetchall()

    def graphs(self, project_id: int) -> list[sqlite3.Row]:
        """089 Q1: the project's designs with their stored graph JSON, newest updated_at first, then highest id.
        ponytail: 101 Q6: automations are included too, so a task run may pick one; filtering by kind is the
        run/scheduler tasks' job."""
        return self.conn.execute(
            "SELECT id, name, graph FROM factories WHERE project_id = ? ORDER BY updated_at DESC, id DESC",
            (project_id,),
        ).fetchall()

    def get(self, factory_id: int) -> sqlite3.Row | None:
        """<Factory>'s columns, with the project's and workspace's names as they are now."""
        return self.conn.execute(
            "SELECT f.id, f.project_id, p.name AS project, p.workspace_id, w.name AS workspace, f.name, f.kind, f.graph,"
            " f.created_at, f.updated_at FROM factories f JOIN projects p ON p.id = f.project_id"
            " JOIN workspaces w ON w.id = p.workspace_id WHERE f.id = ?",
            (factory_id,),
        ).fetchone()

    def by_name(self, project_id: int, name: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM factories WHERE project_id = ? AND name = ?", (project_id, name)
        ).fetchone()
        return None if row is None else row[0]

    def add(self, project_id: int, name: str, graph: str, kind: str = "workflow") -> int:
        now = db.now()
        return self.conn.execute(
            "INSERT INTO factories (project_id, name, kind, graph, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, name, kind, graph, now, now),
        ).lastrowid

    def update(self, factory_id: int, fields: dict) -> None:
        """Sets `fields`, whose keys are `name` and/or `graph` (the stored JSON), and updated_at."""
        sets = ", ".join(f"{column} = :{column}" for column in fields)
        self.conn.execute(
            f"UPDATE factories SET {sets}, updated_at = :now WHERE id = :id",
            fields | {"now": db.now(), "id": factory_id},
        )

    def delete(self, factory_id: int) -> bool:
        """False if there is no such factory."""
        return self.conn.execute("DELETE FROM factories WHERE id = ?", (factory_id,)).rowcount > 0
