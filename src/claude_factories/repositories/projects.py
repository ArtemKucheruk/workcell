"""SQL for the projects table."""

import sqlite3

from .. import db


class ProjectsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def by_path(self, path: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT id, name, path, default_branch FROM projects WHERE path = ?", (path,)
        ).fetchone()

    def add(self, workspace_id: int, name: str, path: str, remote_url: str | None, default_branch: str,
            test_cmd: str | None) -> int:
        return self.conn.execute(
            "INSERT INTO projects (workspace_id, name, path, remote_url, default_branch, test_cmd,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, name, path, remote_url, default_branch, test_cmd, db.now()),
        ).lastrowid

    def update(self, project_id: int, workspace_id: int, name: str, remote_url: str | None,
               default_branch: str, test_cmd: str | None) -> None:
        """A null test_cmd keeps the stored one (002 Q4)."""
        self.conn.execute(
            "UPDATE projects SET workspace_id = ?, name = ?, remote_url = ?, default_branch = ?,"
            " test_cmd = COALESCE(?, test_cmd) WHERE id = ?",
            (workspace_id, name, remote_url, default_branch, test_cmd, project_id),
        )

    def move(self, project_id: int, workspace_id: int) -> bool:
        """False if there is no such project."""
        moved = self.conn.execute("UPDATE projects SET workspace_id = ? WHERE id = ?", (workspace_id, project_id))
        return moved.rowcount > 0

    def for_factory(self, project_id: int) -> sqlite3.Row | None:
        """What Create factory renders and checks, with the workspace's name for its hint."""
        return self.conn.execute(
            "SELECT p.name, p.path, p.default_branch, p.test_cmd, w.name AS workspace FROM projects p"
            " JOIN workspaces w ON w.id = p.workspace_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()

    def set_factory_version(self, project_id: int, version: int) -> None:
        self.conn.execute("UPDATE projects SET factory_version = ? WHERE id = ?", (version, project_id))
