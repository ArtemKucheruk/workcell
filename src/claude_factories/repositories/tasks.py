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
    # 096: one_run_per_task allows one running run per task, so tasks with one = running runs
    "running": "t.id IN (SELECT task_id FROM runs WHERE status = 'running')",
    "done_week": f"t.done_at >= {days_ago(7)}",
}
# §5.1, Q8: one row per event (093 AC37: with its note), round, verdict, decision, and comment, labelled; ties sort
# by kind, then id.
TIMELINE = """
SELECT created_at, 0 AS kind, id, IIF(from_status IS NULL, 'created · ', '') || COALESCE(to_status, '')
  || COALESCE(' · ' || stage, '') || COALESCE(' · ' || note, '') AS label, NULL AS body_md FROM events WHERE task_id = :task
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
        """The task row with its project's id, path, and context, for every handler that reads one."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.description_md, t.spec_md, t.status, t.stage, t.branch, t.worktree_path,"
            " t.done_at, t.project_id, p.path, p.context_md FROM tasks t JOIN projects p ON p.id = t.project_id"
            " WHERE t.id = ?",
            (task_id,),
        ).fetchone()

    def exists(self, task_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is not None

    def for_project(self, project_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, title, description_md, status, stage, position, branch FROM tasks WHERE project_id = ?",
            (project_id,),
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

    def edit(self, task_id: int, title: str | None, description_md: str | None, now: str) -> None:
        """048: a None argument keeps the stored value."""
        self.conn.execute(
            "UPDATE tasks SET title = COALESCE(?, title), description_md = COALESCE(?, description_md),"
            " updated_at = ? WHERE id = ?",
            (title, description_md, now, task_id),
        )

    def delete(self, task_id: int) -> None:
        """048: §5.1's cascade, which the schema lacks (foreign_keys is on), children before parents. 094: task_deps
        has its own ON DELETE CASCADE, so the task's links go on both sides."""
        rounds = "SELECT id FROM rounds WHERE task_id = :task"
        for statement in (
            "DELETE FROM transcripts WHERE task_id = :task",
            "DELETE FROM comments WHERE task_id = :task",
            "DELETE FROM decisions WHERE task_id = :task",
            f"DELETE FROM verdicts WHERE round_id IN ({rounds})",
            f"DELETE FROM round_files WHERE round_id IN ({rounds})",
            "DELETE FROM rounds WHERE task_id = :task",
            "DELETE FROM runs WHERE task_id = :task",
            "DELETE FROM events WHERE task_id = :task",
            "DELETE FROM tasks WHERE id = :task",
        ):
            self.conn.execute(statement, {"task": task_id})

    def move(self, task_id: int, status: str, stage: str | None, done_at: str | None, now: str,
             position: float | None = None) -> None:
        """A None position keeps the stored one."""
        self.conn.execute(
            "UPDATE tasks SET status = ?, stage = ?, position = COALESCE(?, position), done_at = ?,"
            " updated_at = ? WHERE id = ?",
            (status, stage, position, done_at, now, task_id),
        )

    def add_event(self, task_id: int, actor: str, from_status: str | None, to_status: str, stage: str | None,
                  now: str, note: str | None = None) -> None:
        """093 AC37: `note`, e.g. `PR #71 opened`, ends the timeline label."""
        self.conn.execute(
            "INSERT INTO events (task_id, actor, from_status, to_status, stage, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, actor, from_status, to_status, stage, note, now),
        )

    def by_import_key(self, key: str) -> sqlite3.Row | None:
        """058 Q6: `started` is any run or round, or a status other than backlog. 108: with the title."""
        return self.conn.execute(
            "SELECT id, project_id, status, title, description_md, status != 'backlog'"
            " OR EXISTS (SELECT 1 FROM runs WHERE task_id = tasks.id)"
            " OR EXISTS (SELECT 1 FROM rounds WHERE task_id = tasks.id) AS started FROM tasks WHERE import_key = ?",
            (key,),
        ).fetchone()

    def put_imported(self, task_id: int | None, row: dict) -> int:
        """031 Q3: a new imported task (task_id None), or the fields a rerun rewrites. A None position keeps
        the stored one. `row`: project_id, import_key, title, description_md, spec_md, status, stage, position,
        branch, created_at, updated_at, done_at, and optionally pr_url (093 AC2), which a rerun only ever sets, so a
        PR opened from the app stays."""
        row = {"pr_url": None} | row
        if task_id is None:
            return self.conn.execute(
                "INSERT INTO tasks (project_id, import_key, title, description_md, spec_md, status, stage, position,"
                " branch, created_at, updated_at, done_at, pr_url) VALUES (:project_id, :import_key, :title,"
                " :description_md, :spec_md, :status, :stage, :position, :branch, :created_at, :updated_at, :done_at,"
                " :pr_url)",
                row,
            ).lastrowid
        self.conn.execute(
            "UPDATE tasks SET title = :title, description_md = :description_md, spec_md = :spec_md, status = :status,"
            " stage = :stage, position = COALESCE(:position, position), branch = :branch, done_at = :done_at,"
            " updated_at = :updated_at, pr_url = COALESCE(:pr_url, pr_url) WHERE id = :id",
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

    def stage_entered(self, task_id: int, stage: str) -> str | None:
        """089: the created_at of the task's newest event with this stage, None with none."""
        found = self.conn.execute(
            "SELECT created_at FROM events WHERE task_id = ? AND stage = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (task_id, stage),
        ).fetchone()
        return found and found[0]

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

    def top_backlog(self, project_id: int) -> sqlite3.Row | None:
        """012 Q13, 094: the top ready backlog card (lowest position, then lowest id) as id and ready 1; with every
        card blocked, the top card with ready 0 (Q5); None for an empty backlog. 096 Q10: a card that already has
        a running run is skipped."""
        return self.conn.execute(
            "SELECT id, NOT EXISTS (SELECT 1 FROM task_deps d JOIN tasks b ON b.id = d.blocked_by_id"
            " WHERE d.task_id = t.id AND b.status != 'done') AS ready FROM tasks t"
            " WHERE project_id = ? AND status = 'backlog'"
            " AND NOT EXISTS (SELECT 1 FROM runs r WHERE r.task_id = t.id AND r.status = 'running')"
            " ORDER BY ready DESC, position, id LIMIT 1",
            (project_id,),
        ).fetchone()

    def blockers(self, task_id: int) -> list[sqlite3.Row]:
        """094: the tasks `task_id` waits on, as id, title, and status, by id."""
        return self.conn.execute(
            "SELECT b.id, b.title, b.status FROM task_deps d JOIN tasks b ON b.id = d.blocked_by_id"
            " WHERE d.task_id = ? ORDER BY b.id",
            (task_id,),
        ).fetchall()

    def dependents(self, task_id: int) -> list[sqlite3.Row]:
        """094: the tasks waiting on `task_id`, as id, title, and status, by id."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.status FROM task_deps d JOIN tasks t ON t.id = d.task_id"
            " WHERE d.blocked_by_id = ? ORDER BY t.id",
            (task_id,),
        ).fetchall()

    def project_links(self, project_id: int) -> list[sqlite3.Row]:
        """094: every link in the project (links never cross projects) as task_id and its blocker's id, title, and
        status, by task_id then blocker id: the board's fields and the cycle walk's edges in one query."""
        return self.conn.execute(
            "SELECT d.task_id, b.id, b.title, b.status FROM task_deps d JOIN tasks b ON b.id = d.blocked_by_id"
            " WHERE b.project_id = ? ORDER BY d.task_id, b.id",
            (project_id,),
        ).fetchall()

    def link(self, task_id: int, blocker_id: int) -> None:
        """094 Q2: a link that's there already stays the one row."""
        self.conn.execute("INSERT OR IGNORE INTO task_deps (task_id, blocked_by_id) VALUES (?, ?)",
                          (task_id, blocker_id))

    def unlink(self, task_id: int, blocker_id: int) -> bool:
        """094: False when there was no such link."""
        return self.conn.execute("DELETE FROM task_deps WHERE task_id = ? AND blocked_by_id = ?",
                                 (task_id, blocker_id)).rowcount > 0

    def for_page(self, task_id: int) -> sqlite3.Row | None:
        """The task row both task pages show; `path` is for Review's commit hint. 047: the workspace is the
        project's now, joined at read time, for the breadcrumb."""
        return self.conn.execute(
            "SELECT t.id, t.project_id, p.name AS project, p.workspace_id, w.name AS workspace, t.title,"
            " t.description_md, t.spec_md, t.status, t.stage, t.branch, t.worktree_path, t.pr_url, t.import_key,"
            " p.path, p.default_branch FROM tasks t JOIN projects p ON p.id = t.project_id"
            " JOIN workspaces w ON w.id = p.workspace_id"
            " WHERE t.id = ?",
            (task_id,),
        ).fetchone()

    def for_pr(self, task_id: int) -> sqlite3.Row | None:
        """093: what Create PR and Merge PR need: the task, its PR, and its project's path and default branch. 108:
        the import_key, for Create PR's `Closes` line."""
        return self.conn.execute(
            "SELECT t.id, t.title, t.description_md, t.status, t.branch, t.worktree_path, t.pr_url, t.import_key,"
            " p.path,"
            " p.default_branch FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.id = ?",
            (task_id,),
        ).fetchone()

    def set_pr_url(self, task_id: int, url: str, now: str) -> None:
        self.conn.execute("UPDATE tasks SET pr_url = ?, updated_at = ? WHERE id = ?", (url, now, task_id))

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

    def needs_you(self, key: str) -> list[sqlite3.Row]:
        """045: the Needs you rows of TILE_TASKS["waiting"] or ["escalated"], each with its highest round n
        (NULL with none) and updated_at as `since` (Q1), in tile()'s order (Q2)."""
        return self.conn.execute(
            "SELECT t.id, t.title, p.id AS project_id, p.name AS project,"
            " (SELECT MAX(n) FROM rounds WHERE task_id = t.id) AS round, t.updated_at AS since"
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
