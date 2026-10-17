"""Data dir and SQLite helpers. Stdlib only."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def data_dir() -> Path:
    return Path(os.environ.get("FCTL_HOME") or Path.home() / ".claude-factories")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(data_dir() / "factory.db")
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores REFERENCES without it, per connection
    return conn


def init() -> None:
    """Create the data dir and apply schema.sql in WAL mode. Safe to run on every startup."""
    data_dir().mkdir(parents=True, exist_ok=True)
    with closing(connect()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA.read_text())
