"""SQLite helpers. Stdlib only."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .. import config

SCHEMA = Path(__file__).with_name("schema.sql")


def now() -> str:
    """UTC ISO 8601 with seconds and a Z, e.g. 2026-10-17T12:22:23Z."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    # check_same_thread off: a request's connection (server/deps.py) is opened, used, and closed on
    # different threadpool threads, one at a time. No connection is ever shared by two at once.
    conn = sqlite3.connect(config.data_dir() / "factory.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores REFERENCES without it, per connection
    return conn


def init() -> None:
    """Create the data dir and apply schema.sql in WAL mode. Safe to run on every startup."""
    config.data_dir().mkdir(parents=True, exist_ok=True)
    with closing(connect()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        fresh = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'claude_accounts'").fetchone() is None
        conn.executescript(SCHEMA.read_text())
        # 056 Q1: the login runs used so far (CLAUDE_CONFIG_DIR, else ~/.claude) becomes the first, active account,
        # once: when the table is new, so a deleted account never comes back
        if fresh:
            with conn:
                conn.execute("INSERT INTO claude_accounts (config_dir, active, created_at) VALUES (?, 1, ?)",
                             (str(config.claude_config_dir()), now()))
        # 033 Q1: CREATE TABLE IF NOT EXISTS skips a factory.db made before projects.context_md
        if "context_md" not in {row[1] for row in conn.execute("PRAGMA table_info(projects)")}:
            conn.execute("ALTER TABLE projects ADD COLUMN context_md TEXT NOT NULL DEFAULT ''")
        # 031: the same for tasks.import_key; ALTER can't add UNIQUE, so an index enforces it
        if "import_key" not in {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}:
            conn.execute("ALTER TABLE tasks ADD COLUMN import_key TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS tasks_import_key ON tasks(import_key)")
