"""SQL for 095's usage: the usage_snapshots table, and the token and run stats over transcripts and runs."""

import sqlite3

from .. import db

WINDOW_COLUMNS = tuple(f"{w}_{c}" for w in ("five_hour", "seven_day") for c in ("utilization", "resets_at", "status"))
TOKENS = ("SUM(x.input_tokens) AS input_tokens, SUM(x.cache_read_tokens) AS cache_read_tokens,"
          " SUM(x.output_tokens) AS output_tokens")
# Q8: a transcript's time is its own start, else its run's; `since` is a UTC day's start in db.now()'s format
FROM = "FROM transcripts x JOIN runs r ON r.id = x.run_id"
SINCE = " WHERE COALESCE(x.started_at, r.started_at) >= :since"
IN_WINDOW = FROM + SINCE
LARGEST = "ORDER BY SUM(x.input_tokens + x.cache_read_tokens + x.output_tokens) DESC"


class UsageRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(self, run_id: int, snap: dict) -> None:
        """AC6, AC7: the run's snapshot on the run's own account (runs.account_id), recorded now; a re-record of
        the run replaces it. A run with no account_id gets no row."""
        values = {f"{w}_{c}": snap[w][c] for w in ("five_hour", "seven_day")
                  for c in ("utilization", "resets_at", "status")}
        values |= {"run_id": run_id, "status": snap["status"], "overage": int(snap["overage"]),
                   "limited": int(snap["limited"]), "recorded_at": db.now()}
        stored = (*WINDOW_COLUMNS, "status", "overage", "limited", "recorded_at")
        self.conn.execute(
            f"INSERT INTO usage_snapshots (run_id, account_id, {', '.join(stored)})"
            f" SELECT id, account_id, {', '.join(':' + c for c in stored)} FROM runs"
            " WHERE id = :run_id AND account_id IS NOT NULL"
            " ON CONFLICT (run_id) DO UPDATE SET account_id = excluded.account_id, "
            + ", ".join(f"{c} = excluded.{c}" for c in stored),
            values,
        )

    def latest(self) -> dict[int, sqlite3.Row]:
        """AC9: account id → its row with the greatest recorded_at, ties to the highest run_id."""
        rows = self.conn.execute(
            "SELECT * FROM (SELECT s.*, ROW_NUMBER() OVER"
            " (PARTITION BY account_id ORDER BY recorded_at DESC, run_id DESC) AS n FROM usage_snapshots s)"
            " WHERE n = 1"
        ).fetchall()
        return {r["account_id"]: r for r in rows}

    def by_day(self, since: str) -> list[sqlite3.Row]:
        """AC15: tokens per UTC day (YYYY-MM-DD) from `since`; days without transcripts are left out."""
        return self.conn.execute(
            f"SELECT substr(COALESCE(x.started_at, r.started_at), 1, 10) AS day, {TOKENS} {IN_WINDOW}"
            " GROUP BY day", {"since": since}).fetchall()

    def runs_by_day(self, since: str) -> dict[str, int]:
        """AC15: runs started per UTC day from `since`."""
        return dict(self.conn.execute(
            "SELECT substr(started_at, 1, 10) AS day, COUNT(*) FROM runs WHERE started_at >= ? GROUP BY day",
            (since,)).fetchall())

    def by_account(self, since: str) -> list[sqlite3.Row]:
        """AC16: tokens per run account (email and config_dir NULL for none or a deleted one); its runs come from
        runs_by_account, so runs without transcripts count too."""
        return self.conn.execute(
            f"SELECT a.email, a.config_dir, {TOKENS} {FROM}"
            f" LEFT JOIN claude_accounts a ON a.id = r.account_id{SINCE} GROUP BY a.id {LARGEST}",
            {"since": since}).fetchall()

    def runs_by_account(self, since: str) -> list[sqlite3.Row]:
        """AC16: runs started from `since` per account, those without transcripts included."""
        return self.conn.execute(
            "SELECT a.email, a.config_dir, COUNT(*) AS runs FROM runs r"
            " LEFT JOIN claude_accounts a ON a.id = r.account_id WHERE r.started_at >= ? GROUP BY a.id",
            (since,)).fetchall()

    def by_column(self, column: str, missing: str, since: str) -> list[sqlite3.Row]:
        """AC16: tokens and runs per transcripts.`column` (model or agent_type, a constant from the handler),
        NULL read as `missing`, largest first."""
        assert column in ("model", "agent_type")
        return self.conn.execute(
            f"SELECT COALESCE(x.{column}, :missing) AS key, {TOKENS}, COUNT(DISTINCT x.run_id) AS runs {IN_WINDOW}"
            f" GROUP BY key {LARGEST}, key", {"since": since, "missing": missing}).fetchall()

    def top_tasks(self, since: str, limit: int) -> list[sqlite3.Row]:
        """AC17, Q8: the tasks with the most input + cache_read + output tokens from `since`."""
        return self.conn.execute(
            f"SELECT t.id AS task_id, t.title, t.project_id, {TOKENS} {FROM} JOIN tasks t ON t.id = x.task_id{SINCE}"
            f" GROUP BY t.id {LARGEST}, t.id LIMIT :limit", {"since": since, "limit": limit}).fetchall()

    def limited_runs(self, limit: int) -> list[sqlite3.Row]:
        """AC18, Q6: runs whose snapshot was limited, by ended_at newest first (a null one last), then id."""
        return self.conn.execute(
            "SELECT s.run_id, r.task_id, t.title, a.email, a.config_dir, r.ended_at FROM usage_snapshots s"
            " JOIN runs r ON r.id = s.run_id JOIN tasks t ON t.id = r.task_id"
            " JOIN claude_accounts a ON a.id = s.account_id"
            " WHERE s.limited = 1 ORDER BY r.ended_at DESC, s.run_id DESC LIMIT ?", (limit,)).fetchall()
