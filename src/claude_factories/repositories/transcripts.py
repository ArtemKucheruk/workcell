"""SQL for the transcripts table (030)."""

import sqlite3

LISTED = ("id, run_id, round, agent_type, name, model, turns, input_tokens, cache_read_tokens, output_tokens,"
          " started_at, ended_at")
STORED = ("run_id", "task_id", "agent_type", "name", "round", "path", "model", "turns", "input_tokens",
          "cache_read_tokens", "output_tokens", "started_at", "ended_at")


class TranscriptsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def source(self, run_id: int) -> sqlite3.Row | None:
        """What collecting a run needs: its task, its session, the task's worktree, and its own account's
        config_dir (096 Q5: NULL for a run with no account_id, or whose account is gone). 102 AC14: an automation
        run has no task (task_id NULL) and its own worktree_path."""
        return self.conn.execute(
            "SELECT r.task_id, r.session_id, COALESCE(r.worktree_path, t.worktree_path) AS worktree_path,"
            " a.config_dir FROM runs r"
            " LEFT JOIN tasks t ON t.id = r.task_id LEFT JOIN claude_accounts a ON a.id = r.account_id"
            " WHERE r.id = ?",
            (run_id,),
        ).fetchone()

    def upsert(self, row: dict) -> None:
        """Q7: a re-copy of the same (run_id, path) updates its row."""
        self.conn.execute(
            f"INSERT INTO transcripts ({', '.join(STORED)}) VALUES ({', '.join(':' + c for c in STORED)})"
            " ON CONFLICT (run_id, path) DO UPDATE SET "
            + ", ".join(f"{c} = excluded.{c}" for c in STORED if c not in ("run_id", "path")),
            row,
        )

    def for_task(self, task_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            f"SELECT {LISTED} FROM transcripts WHERE task_id = ? ORDER BY run_id, started_at, id", (task_id,)
        ).fetchall()

    def for_export(self, task_id: int) -> list[sqlite3.Row]:
        """032: the task's transcripts with their copy's path and their run's session, in for_task's order."""
        return self.conn.execute(
            "SELECT t.id, t.path, r.session_id, t.agent_type, t.name, t.round, t.started_at FROM transcripts t"
            " JOIN runs r ON r.id = t.run_id WHERE t.task_id = ? ORDER BY t.run_id, t.started_at, t.id", (task_id,),
        ).fetchall()

    def get(self, transcript_id: int) -> sqlite3.Row | None:
        """047 Q3: with its task's project and workspace as they are now, for the breadcrumb."""
        return self.conn.execute(
            f"SELECT x.*, p.id AS project_id, p.name AS project, w.id AS workspace_id, w.name AS workspace"
            f" FROM (SELECT {LISTED}, task_id, path FROM transcripts WHERE id = ?) x JOIN tasks t ON t.id = x.task_id"
            " JOIN projects p ON p.id = t.project_id JOIN workspaces w ON w.id = p.workspace_id",
            (transcript_id,),
        ).fetchone()
