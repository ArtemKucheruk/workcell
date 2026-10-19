"""SQL for the rounds and round_files tables."""

import sqlite3

from .. import db

FILES = ("INSERT INTO round_files (round_id, path, old_path, change, binary, additions, deletions, patch)"
         " VALUES (:round_id, :path, :old_path, :change, :binary, :additions, :deletions, :patch)")


class RoundsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def totals(self, task_id: int) -> list[sqlite3.Row]:
        """A task's rounds by n, each with its file count and +/− sums."""
        return self.conn.execute(
            "SELECT r.id, r.n, r.trigger, COUNT(f.path) AS files, COALESCE(SUM(f.additions), 0) AS additions,"
            " COALESCE(SUM(f.deletions), 0) AS deletions FROM rounds r"
            " LEFT JOIN round_files f ON f.round_id = r.id WHERE r.task_id = ? GROUP BY r.id ORDER BY r.n",
            (task_id,),
        ).fetchall()

    def all(self, task_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, n, build_md FROM rounds WHERE task_id = ? ORDER BY n", (task_id,)
        ).fetchall()

    def latest(self, task_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT id, n, build_md FROM rounds WHERE task_id = ? ORDER BY n DESC LIMIT 1", (task_id,)
        ).fetchone()

    def by_n(self, task_id: int, n: str) -> sqlite3.Row | None:
        """Compared as text, so 'abc', '01', or a huge number simply match nothing."""
        return self.conn.execute(
            "SELECT id, n, build_md FROM rounds WHERE task_id = ? AND CAST(n AS TEXT) = ?", (task_id, n)
        ).fetchone()

    def next_n(self, task_id: int) -> int:
        return self.conn.execute(
            "SELECT COALESCE(MAX(n), 0) + 1 FROM rounds WHERE task_id = ?", (task_id,)
        ).fetchone()[0]

    def add(self, task_id: int, n: int, trigger: str, base_sha: str, build_md: str | None,
            files: list[dict], now: str | None = None) -> None:
        """The round and its round_files rows, in the given order."""
        round_id = self.conn.execute(
            "INSERT INTO rounds (task_id, n, trigger, base_sha, build_md, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, n, trigger, base_sha, build_md, now or db.now()),
        ).lastrowid
        self.conn.executemany(FILES, [f | {"round_id": round_id} for f in files])

    def upsert(self, task_id: int, n: int, trigger: str, base_sha: str, build_md: str | None, created_at: str) -> int:
        """031 Q3: round n of the task, added or rewritten in place, so its id (and my comments) stay; its id."""
        return self.conn.execute(
            "INSERT INTO rounds (task_id, n, trigger, base_sha, build_md, created_at) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (task_id, n) DO UPDATE SET trigger = excluded.trigger, base_sha = excluded.base_sha,"
            " build_md = excluded.build_md, created_at = excluded.created_at RETURNING id",
            (task_id, n, trigger, base_sha, build_md, created_at),
        ).fetchone()[0]

    def replace_files(self, round_id: int, files: list[dict]) -> None:
        self.conn.execute("DELETE FROM round_files WHERE round_id = ?", (round_id,))
        self.conn.executemany(FILES, [f | {"round_id": round_id} for f in files])

    def patches(self, round_id: int) -> list[str]:
        """The round's files' patches in rowid order."""
        return [p for (p,) in self.conn.execute(
            "SELECT patch FROM round_files WHERE round_id = ? ORDER BY rowid", (round_id,)
        )]

    def has_file(self, round_id: int, path: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM round_files WHERE round_id = ? AND path = ?", (round_id, path)
        ).fetchone() is not None

    def files(self, round_id: int) -> list[sqlite3.Row]:
        """The round's files in rowid order, each with its patch."""
        return self.conn.execute(
            "SELECT path, old_path, change, binary, additions, deletions, patch FROM round_files WHERE round_id = ?"
            " ORDER BY rowid", (round_id,),
        ).fetchall()
