"""SQL for the settings table (096 Q2): one row, id 1, seeded by schema.sql."""

import sqlite3


class SettingsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def max_concurrent_runs(self) -> int:
        return self.conn.execute("SELECT max_concurrent_runs FROM settings WHERE id = 1").fetchone()[0]

    def set_max_concurrent_runs(self, n: int) -> None:
        self.conn.execute("UPDATE settings SET max_concurrent_runs = ? WHERE id = 1", (n,))
