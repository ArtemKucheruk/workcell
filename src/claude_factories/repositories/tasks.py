"""SQL for the tasks and events tables."""

import sqlite3

from .. import db
from ..domain.enums import Status


def days_ago(n: int) -> str:
    """SQL for now − n days in db.now()'s format, so stored timestamps compare as strings (Q2)."""
    return f"strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-{n} days')"


# The tasks each dashboard tile counts and lists (Q1), as a WHERE on tasks t. runs_week counts runs instead.
TILE_TASKS = {status: f"t.status = '{status}'" for status in Status} | {
    "waiting": "t.stage = 'human_review'",
    "escalated": "t.stage = 'escalated'",
    # one_active_run allows one running run, so tasks with one = running runs
    "running": "t.id IN (SELECT task_id FROM runs WHERE status = 'running')",
    "done_week": f"t.done_at >= {days_ago(7)}",
}
# §5.1, Q8: one row per event, round, verdict, decision, and comment, labelled; ties sort by kind, then id.
TIMELINE = """
SELECT created_at, 0 AS kind, id, IIF(from_status IS NULL, 'created · ', '') || COALESCE(to_status, '')
  || COALESCE(' · ' || stage, '') AS label, NULL AS body_md FROM events WHERE task_id = :task
UNION ALL SELECT created_at, 1, id, 'round ' || n, NULL FROM rounds WHERE task_id = :task
UNION ALL SELECT v.created_at, 2, v.rowid, v.reviewer || ' ' || v.verdict || ' · round ' || r.n, NULL
  FROM verdicts v JOIN rounds r ON r.id = v.round_id WHERE r.task_id = :task
UNION ALL SELECT d.created_at, 3, d.id, d.actor || ' ' || d.decision || ' · round ' || r.n, d.body_md
  FROM decisions d JOIN rounds r ON r.id = d.round_id WHERE d.task_id = :task
UNION ALL SELECT c.created_at, 4, c.id, c.author || COALESCE(' on ' || c.path || ':' || c.line, '')
  || ' · round ' || r.n, c.body_md FROM comments c JOIN rounds r ON r.id = c.round_id WHERE c.task_id = :task
ORDER BY created_at, kind, id
"""


class TasksRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def lock(self) -> str:
        """035 Q4: BEGIN IMMEDIATE, SQLite's write lock, so a handler's checks and writes commit together.
        Returns db.now(), the timestamp those writes share, since handlers can't import db."""
        self.conn.execute("BEGIN IMMEDIATE")
        return db.now()

    def get(self, task_id: int) -> sqlite3.Row | None:
        """The task row with its project's path and context, for every handler that reads one."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.description_md, t.spec_md, t.status, t.stage, t.branch, t.worktree_path,"
            " t.done_at, p.path, p.context_md FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.id = ?",
            (task_id,),
        ).fetchone()

    def exists(self, task_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is not None

    def for_project(self, project_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, title, status, stage, position, branch FROM tasks WHERE project_id = ?", (project_id,)
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

    def by_import_key(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT id, project_id, status FROM tasks WHERE import_key = ?", (key,)
        ).fetchone()

    def put_imported(self, task_id: int | None, row: dict) -> int:
        """031 Q3: a new imported task (task_id None), or the fields a rerun rewrites. A None position keeps
        the stored one. `row`: project_id, import_key, title, description_md, spec_md, status, stage, position,
        branch, created_at, updated_at, done_at."""
        if task_id is None:
            return self.conn.execute(
                "INSERT INTO tasks (project_id, import_key, title, description_md, spec_md, status, stage, position,"
                " branch, created_at, updated_at, done_at) VALUES (:project_id, :import_key, :title, :description_md,"
                " :spec_md, :status, :stage, :position, :branch, :created_at, :updated_at, :done_at)",
                row,
            ).lastrowid
        self.conn.execute(
            "UPDATE tasks SET title = :title, description_md = :description_md, spec_md = :spec_md, status = :status,"
            " stage = :stage, position = COALESCE(:position, position), branch = :branch, done_at = :done_at,"
            " updated_at = :updated_at WHERE id = :id",
            row | {"id": task_id},
        )
        return task_id

    def for_export(self, task_id: int) -> sqlite3.Row | None:
        """032: what a bundle's task.json and spec.md take from the task."""
        return self.conn.execute(
            "SELECT id, import_key, title, description_md, spec_md, status, stage, created_at FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    def events(self, task_id: int) -> list[sqlite3.Row]:
        """032: the task's events in id order."""
        return self.conn.execute(
            "SELECT actor, from_status, to_status, stage, created_at FROM events WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()

    def replace_events(self, task_id: int, events: list[dict]) -> None:
        """031 Q3: the task's events become `events` (actor, from_status, to_status, stage, created_at)."""
        self.conn.execute("DELETE FROM events WHERE task_id = ?", (task_id,))
        self.conn.executemany(
            "INSERT INTO events (task_id, actor, from_status, to_status, stage, created_at)"
            " VALUES (:task_id, :actor, :from_status, :to_status, :stage, :created_at)",
            [e | {"task_id": task_id} for e in events],
        )

    def for_run(self, task_id: int) -> sqlite3.Row | None:
        """What a run needs: the task, its project's path and default branch, and the test command."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.status, t.worktree_path, p.path, p.default_branch, p.test_cmd"
            " FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.id = ?",
            (task_id,),
        ).fetchone()

    def set_worktree(self, task_id: int, branch: str, worktree_path: str) -> None:
        self.conn.execute("UPDATE tasks SET branch = ?, worktree_path = ? WHERE id = ?",
                          (branch, worktree_path, task_id))

    def start(self, task_id: int, now: str) -> bool:
        """012 Q9: a backlog task → in_progress, stage cleared; False for any other status, which stays."""
        return self.conn.execute(
            "UPDATE tasks SET status = 'in_progress', stage = NULL, updated_at = ? WHERE id = ? AND status = 'backlog'",
            (now, task_id),
        ).rowcount > 0

    def top_backlog(self, project_id: int) -> int | None:
        """012 Q13: the top backlog card's id, lowest position then lowest id."""
        found = self.conn.execute(
            "SELECT id FROM tasks WHERE project_id = ? AND status = 'backlog' ORDER BY position, id LIMIT 1",
            (project_id,),
        ).fetchone()
        return found[0] if found else None

    def for_page(self, task_id: int) -> sqlite3.Row | None:
        """The task row both task pages show; `path` is for Review's commit hint. 047: the workspace is the
        project's now, joined at read time, for the breadcrumb."""
        return self.conn.execute(
            "SELECT t.id, t.project_id, p.name AS project, p.workspace_id, w.name AS workspace, t.title,"
            " t.description_md, t.spec_md, t.status, t.stage, t.branch, t.worktree_path, p.path, p.default_branch"
            " FROM tasks t JOIN projects p ON p.id = t.project_id JOIN workspaces w ON w.id = p.workspace_id"
            " WHERE t.id = ?",
            (task_id,),
        ).fetchone()

    def timeline(self, task_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(TIMELINE, {"task": task_id}).fetchall()

    def tile_counts(self) -> sqlite3.Row:
        """Every dashboard tile's count. Every SQL fragment is a constant."""
        return self.conn.execute(
            "SELECT " + ", ".join(f"COUNT(*) FILTER (WHERE {where}) AS {key}" for key, where in TILE_TASKS.items())
            + f", (SELECT COUNT(*) FROM runs WHERE started_at >= {days_ago(7)}) AS runs_week FROM tasks t"
        ).fetchone()

    def tile(self, key: str) -> list[sqlite3.Row]:
        """The tasks of TILE_TASKS[key], most recently updated first (Q4)."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.status, t.stage, p.id AS project_id, p.name AS project"
            f" FROM tasks t JOIN projects p ON p.id = t.project_id WHERE {TILE_TASKS[key]}"
            " ORDER BY t.updated_at DESC, t.id DESC"
        ).fetchall()

    def open_by_project(self) -> list[sqlite3.Row]:
        """Q5: each project with open tasks, its backlog, in progress, and review counts, by workspace."""
        return self.conn.execute(
            "SELECT w.id AS workspace_id, w.name AS workspace, p.id, p.name,"
            " COUNT(*) FILTER (WHERE t.status = 'backlog') AS backlog,"
            " COUNT(*) FILTER (WHERE t.status = 'in_progress') AS in_progress,"
            " COUNT(*) FILTER (WHERE t.status = 'review') AS review"
            " FROM tasks t JOIN projects p ON p.id = t.project_id JOIN workspaces w ON w.id = p.workspace_id"
            " WHERE t.status != 'done' GROUP BY p.id ORDER BY w.name, p.name, p.id"
        ).fetchall()

    def done_recently(self) -> list[sqlite3.Row]:
        """Q6: tasks done in the last 30 days with their round count; the JOIN drops tasks with no rounds."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.done_at, p.id AS project_id, p.name AS project, COUNT(*) AS rounds"
            " FROM tasks t JOIN rounds r ON r.task_id = t.id JOIN projects p ON p.id = t.project_id"
            f" WHERE t.done_at >= {days_ago(30)} GROUP BY t.id ORDER BY t.done_at DESC, t.id DESC"
        ).fetchall()
