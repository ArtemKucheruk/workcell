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
        conn.executescript(SCHEMA.read_text())
        # 033 Q1: CREATE TABLE IF NOT EXISTS skips a factory.db made before projects.context_md
        if "context_md" not in {row[1] for row in conn.execute("PRAGMA table_info(projects)")}:
            conn.execute("ALTER TABLE projects ADD COLUMN context_md TEXT NOT NULL DEFAULT ''")
