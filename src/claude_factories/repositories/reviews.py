"""SQL for the verdicts, comments, and decisions tables."""

import sqlite3

from .. import db


class ReviewsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def task_verdicts(self, task_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT v.round_id, v.reviewer, v.verdict FROM verdicts v"
            " JOIN rounds r ON r.id = v.round_id WHERE r.task_id = ?",
            (task_id,),
        ).fetchall()

    def round_verdicts(self, round_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT reviewer, verdict, body_md FROM verdicts WHERE round_id = ?", (round_id,)
        ).fetchall()

    def put_verdict(self, round_id: int, reviewer: str, verdict: str, body_md: str) -> int:
        """006 Q2: one row per (round, reviewer); returns how many the round now has."""
        self.conn.execute(
            "INSERT OR REPLACE INTO verdicts (round_id, reviewer, verdict, body_md, created_at) VALUES (?, ?, ?, ?, ?)",
            (round_id, reviewer, verdict, body_md, db.now()),
        )
        return self.conn.execute("SELECT COUNT(*) FROM verdicts WHERE round_id = ?", (round_id,)).fetchone()[0]

    def add_comment(self, task_id: int, round_id: int, author: str, path: str | None, line: int | None,
                    side: str | None, body_md: str) -> int:
        return self.conn.execute(
            "INSERT INTO comments (task_id, round_id, author, path, line, side, body_md, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, round_id, author, path, line, side, body_md, db.now()),
        ).lastrowid

    def comments(self, round_id: int, only_me: bool) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT author, path, line, side, body_md FROM comments"
            " WHERE round_id = ? AND (? = 0 OR author = 'me') ORDER BY id",
            (round_id, only_me),
        ).fetchall()

    def add_decision(self, task_id: int, round_id: int, actor: str, decision: str, body_md: str,
                     now: str | None = None) -> int:
        return self.conn.execute(
            "INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, round_id, actor, decision, body_md, now or db.now()),
        ).lastrowid

    def task_decisions(self, task_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT d.id, r.n AS round, d.actor, d.decision, d.body_md, d.created_at FROM decisions d"
            " JOIN rounds r ON r.id = d.round_id WHERE d.task_id = ? ORDER BY d.id",
            (task_id,),
        ).fetchall()

    def round_decisions(self, round_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT actor, decision, body_md FROM decisions WHERE round_id = ? ORDER BY id", (round_id,)
        ).fetchall()

    def changes_requested(self, task_id: int, n: int) -> bool:
        """Whether I requested changes on round n."""
        return self.conn.execute(
            "SELECT 1 FROM decisions d JOIN rounds r ON r.id = d.round_id WHERE r.task_id = ? AND r.n = ?"
            " AND d.actor = 'me' AND d.decision = 'CHANGES_REQUESTED'",
            (task_id, n),
        ).fetchone() is not None

    def latest_feedback(self, task_id: int) -> sqlite3.Row | None:
        """006 Q6: my latest CHANGES_REQUESTED, with its round."""
        return self.conn.execute(
            "SELECT d.round_id, r.n, d.body_md FROM decisions d JOIN rounds r ON r.id = d.round_id"
            " WHERE d.task_id = ? AND d.actor = 'me' AND d.decision = 'CHANGES_REQUESTED' ORDER BY d.id DESC LIMIT 1",
            (task_id,),
        ).fetchone()

    def verdict_bodies(self, task_id: int) -> list[sqlite3.Row]:
        """007 Q5: every verdict of the task's rounds with its round n and body."""
        return self.conn.execute(
            "SELECT r.n, v.reviewer, v.verdict, v.body_md FROM verdicts v JOIN rounds r ON r.id = v.round_id"
            " WHERE r.task_id = ?", (task_id,),
        ).fetchall()

    def approver_latest(self, task_id: int) -> sqlite3.Row | None:
        """007 Q7: only the approver's latest decision, by id."""
        return self.conn.execute(
            "SELECT d.decision, d.body_md, r.n FROM decisions d JOIN rounds r ON r.id = d.round_id"
            " WHERE d.task_id = ? AND d.actor = 'approver' ORDER BY d.id DESC LIMIT 1", (task_id,),
        ).fetchone()

    def inline_comments(self, round_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, author, path, line, side, body_md FROM comments WHERE round_id = ? AND path IS NOT NULL"
            " ORDER BY id", (round_id,),
        ).fetchall()

    def comment_anchor(self, comment_id: int) -> sqlite3.Row:
        """008 Q3: where an inline comment sits: its round n, path, side, and line."""
        return self.conn.execute(
            "SELECT r.n, c.path, c.side, c.line FROM comments c JOIN rounds r ON r.id = c.round_id WHERE c.id = ?",
            (comment_id,),
        ).fetchone()
