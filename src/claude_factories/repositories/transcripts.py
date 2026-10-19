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
        """What collecting a run needs: its task, its session, and the task's worktree."""
        return self.conn.execute(
            "SELECT r.task_id, r.session_id, t.worktree_path FROM runs r JOIN tasks t ON t.id = r.task_id"
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

    def get(self, transcript_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            f"SELECT {LISTED}, task_id, path FROM transcripts WHERE id = ?", (transcript_id,)
        ).fetchone()
