"""SQL for the claude_accounts table (056)."""

import sqlite3

from .. import db

COLUMNS = "id, config_dir, active"


class ClaudeAccountsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def all(self) -> list[sqlite3.Row]:
        return self.conn.execute(f"SELECT {COLUMNS} FROM claude_accounts ORDER BY id").fetchall()

    def get(self, account_id: int) -> sqlite3.Row | None:
        return self.conn.execute(f"SELECT {COLUMNS} FROM claude_accounts WHERE id = ?", (account_id,)).fetchone()

    def active(self) -> sqlite3.Row | None:
        return self.conn.execute(f"SELECT {COLUMNS} FROM claude_accounts WHERE active = 1").fetchone()

    def add(self, config_dir: str) -> int:
        """Q4: the new row is active only when no row is, decided in the insert itself."""
        return self.conn.execute(
            "INSERT INTO claude_accounts (config_dir, active, created_at)"
            " SELECT ?, NOT EXISTS (SELECT 1 FROM claude_accounts WHERE active = 1), ?",
            (config_dir, db.now()),
        ).lastrowid

    def activate(self, account_id: int) -> None:
        """The old active row is cleared first, so one_active_account holds at every step."""
        self.conn.execute("UPDATE claude_accounts SET active = 0 WHERE active = 1 AND id != ?", (account_id,))
        self.conn.execute("UPDATE claude_accounts SET active = 1 WHERE id = ?", (account_id,))

    def delete(self, account_id: int) -> None:
        self.conn.execute("DELETE FROM claude_accounts WHERE id = ?", (account_id,))
