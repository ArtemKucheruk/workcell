"""SQL for the projects table."""

import sqlite3

from .. import db
from .tasks import TILE_TASKS


class ProjectsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def by_path(self, path: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT id, name, path, default_branch FROM projects WHERE path = ?", (path,)
        ).fetchone()

    def exists(self, project_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is not None

    def add(self, workspace_id: int, name: str, path: str, remote_url: str | None, default_branch: str,
            test_cmd: str | None, now: str | None = None) -> int:
        return self.conn.execute(
            "INSERT INTO projects (workspace_id, name, path, remote_url, default_branch, test_cmd,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, name, path, remote_url, default_branch, test_cmd, now or db.now()),
        ).lastrowid

    def update(self, project_id: int, workspace_id: int, name: str, remote_url: str | None,
               default_branch: str, test_cmd: str | None) -> None:
        """A null test_cmd keeps the stored one (002 Q4)."""
        self.conn.execute(
            "UPDATE projects SET workspace_id = ?, name = ?, remote_url = ?, default_branch = ?,"
            " test_cmd = COALESCE(?, test_cmd) WHERE id = ?",
            (workspace_id, name, remote_url, default_branch, test_cmd, project_id),
        )

    def patch(self, project_id: int, fields: dict) -> sqlite3.Row | None:
        """049: sets `fields`, whose keys are ProjectPatch's columns; the row after, or None if there is no such
        project."""
        sets = ", ".join(f"{column} = :{column}" for column in fields)
        return self.conn.execute(
            f"UPDATE projects SET {sets} WHERE id = :id RETURNING id, workspace_id, name, test_cmd, github_label",
            fields | {"id": project_id},
        ).fetchone()

    def delete(self, project_id: int) -> None:
        """049: the projects row only; its tasks go first, through TasksRepo.delete."""
        self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def for_factory(self, project_id: int) -> sqlite3.Row | None:
        """What Create factory renders and checks, with the workspace's name for its hint."""
        return self.conn.execute(
            "SELECT p.name, p.path, p.default_branch, p.test_cmd, w.name AS workspace FROM projects p"
            " JOIN workspaces w ON w.id = p.workspace_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()

    def set_factory_version(self, project_id: int, version: int) -> None:
        self.conn.execute("UPDATE projects SET factory_version = ? WHERE id = ?", (version, project_id))

    def in_workspace(self, workspace_id: int) -> list[sqlite3.Row]:
        """The workspace page's rows: each project by name with its task counts and last activity."""
        return self.conn.execute(
            "SELECT p.id, p.name, p.path, p.default_branch,"
            " COUNT(t.id) FILTER (WHERE t.status = 'backlog') AS backlog,"
            " COUNT(t.id) FILTER (WHERE t.status = 'in_progress') AS in_progress,"
            " COUNT(t.id) FILTER (WHERE t.status = 'review') AS review,"
            " COUNT(t.id) FILTER (WHERE t.status = 'done') AS done,"
            " MAX(p.created_at, COALESCE(MAX(t.updated_at), '')) AS last_activity"
            " FROM projects p LEFT JOIN tasks t ON t.project_id = p.id"
            " WHERE p.workspace_id = ? GROUP BY p.id ORDER BY p.name",
            (workspace_id,),
        ).fetchall()

    def for_sidebar(self) -> list[sqlite3.Row]:
        """041: every workspace by name, each of its projects by name then id (Q4) with their review, running,
        and escalated counts (Q1). A workspace with no projects is one row whose project columns are NULL."""
        return self.conn.execute(
            "SELECT w.id AS workspace_id, w.name AS workspace, p.id, p.name,"
            f" COUNT(t.id) FILTER (WHERE {TILE_TASKS['waiting']} OR {TILE_TASKS['escalated']}) AS review,"
            f" COUNT(t.id) FILTER (WHERE {TILE_TASKS['running']}) AS running,"
            f" COUNT(t.id) FILTER (WHERE {TILE_TASKS['escalated']}) AS escalated"
            " FROM workspaces w LEFT JOIN projects p ON p.workspace_id = w.id LEFT JOIN tasks t ON t.project_id = p.id"
            " GROUP BY w.id, p.id ORDER BY w.name, p.name, p.id"
        ).fetchall()

    def for_board(self, project_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT p.id, p.name, p.path, p.default_branch, p.workspace_id, w.name AS workspace, p.remote_url,"
            " p.test_cmd, p.github_label FROM projects p JOIN workspaces w ON w.id = p.workspace_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()

    def for_code(self, project_id: int) -> sqlite3.Row | None:
        """047: with the workspace for the code page's breadcrumb; 090: the remote and default branch for its links."""
        return self.conn.execute(
            "SELECT p.id, p.name, p.path, p.workspace_id, w.name AS workspace, p.remote_url, p.default_branch"
            " FROM projects p"
            " JOIN workspaces w ON w.id = p.workspace_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()

    def factory_sync(self, project_id: int) -> sqlite3.Row | None:
        """058 Q10: the path, and the last factory/ sync's file mark and refusal."""
        return self.conn.execute(
            "SELECT path, factory_mark, factory_error FROM projects WHERE id = ?", (project_id,)
        ).fetchone()

    def for_issues(self, project_id: int) -> sqlite3.Row | None:
        """108: what GitHub issues sync needs: the main checkout's path and the saved label."""
        return self.conn.execute("SELECT path, github_label FROM projects WHERE id = ?", (project_id,)).fetchone()

    def set_factory_sync(self, project_id: int, mark: str | None, error: str | None) -> None:
        self.conn.execute("UPDATE projects SET factory_mark = ?, factory_error = ? WHERE id = ?",
                          (mark, error, project_id))

    def context(self, project_id: int) -> str | None:
        """None if there is no such project."""
        row = self.conn.execute("SELECT context_md FROM projects WHERE id = ?", (project_id,)).fetchone()
        return None if row is None else row[0]

    def set_context(self, project_id: int, context_md: str) -> bool:
        """False if there is no such project."""
        return self.conn.execute(
            "UPDATE projects SET context_md = ? WHERE id = ?", (context_md, project_id)
        ).rowcount > 0
