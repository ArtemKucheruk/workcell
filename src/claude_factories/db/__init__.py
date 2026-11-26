"""SQLite helpers. Stdlib only."""

import re
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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
        if "context_md" not in columns:
            conn.execute("ALTER TABLE projects ADD COLUMN context_md TEXT NOT NULL DEFAULT ''")
        # 058 Q10: the same for the last factory/ sync; 108 AC1: GitHub issues sync's label
        for column in ("factory_mark", "factory_error", "github_label"):
            if column not in columns:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {column} TEXT")
        # 031: the same for tasks.import_key; ALTER can't add UNIQUE, so an index enforces it
        if "import_key" not in {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}:
            conn.execute("ALTER TABLE tasks ADD COLUMN import_key TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS tasks_import_key ON tasks(import_key)")
        if "pr_url" not in {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}:  # 093 AC1: the same
            conn.execute("ALTER TABLE tasks ADD COLUMN pr_url TEXT")
        if "module_id" not in {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}:  # 112 AC2: the same
            conn.execute("ALTER TABLE tasks ADD COLUMN module_id INTEGER REFERENCES modules(id) ON DELETE SET NULL")
        # 096: one run per task replaces the global one-run index; each run remembers its account (Q5)
        conn.execute("DROP INDEX IF EXISTS one_active_run")
        if "account_id" not in {row[1] for row in conn.execute("PRAGMA table_info(runs)")}:
            conn.execute("ALTER TABLE runs ADD COLUMN account_id INTEGER"
                         " REFERENCES claude_accounts(id) ON DELETE SET NULL")
        # 095 AC10: the account's label; usage_snapshots comes from IF NOT EXISTS
        if "email" not in {row[1] for row in conn.execute("PRAGMA table_info(claude_accounts)")}:
            conn.execute("ALTER TABLE claude_accounts ADD COLUMN email TEXT")
        # 101 AC2: the design's kind; the DEFAULT makes every existing row a workflow
        if "kind" not in {row[1] for row in conn.execute("PRAGMA table_info(factories)")}:
            conn.execute("ALTER TABLE factories ADD COLUMN kind TEXT NOT NULL DEFAULT 'workflow'"
                         " CHECK (kind IN ('workflow','automation'))")
        # 102 AC2: an automation run has no task, and ALTER can't drop a NOT NULL or add a table CHECK
        rebuilt = False
        if "kind" not in {row[1] for row in conn.execute("PRAGMA table_info(runs)")}:
            rebuild(conn, "runs")
            rebuilt = True
        if any(row[1] == "task_id" and row[3] for row in conn.execute("PRAGMA table_info(transcripts)")):
            rebuild(conn, "transcripts")
            rebuilt = True
        if rebuilt:  # the dropped table took one_run_per_task with it; the schema's IF NOT EXISTS brings it back
            conn.executescript(SCHEMA.read_text())


def rebuild(conn: sqlite3.Connection, table: str) -> None:
    """102: SQLite's 12-step table rebuild into schema.sql's own CREATE TABLE, every row's id and values kept.
    foreign_keys is OFF meanwhile, so the DROP cascades nothing (usage_snapshots, transcripts) and the rows
    pointing at the table point at the new one. Raises, rolled back, if the copy's own references are broken."""
    found = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \(.*?\);", SCHEMA.read_text(), re.DOTALL)
    create = found[0].replace(f"CREATE TABLE IF NOT EXISTS {table} (", f"CREATE TABLE {table}_new (", 1)
    columns = ", ".join(row[1] for row in conn.execute(f"PRAGMA table_info({table})"))
    conn.execute("PRAGMA foreign_keys = OFF")  # outside a transaction, or SQLite ignores it
    try:
        conn.executescript(
            f"BEGIN; {create} INSERT INTO {table}_new ({columns}) SELECT {columns} FROM {table};"
            f" DROP TABLE {table}; ALTER TABLE {table}_new RENAME TO {table};")
        if conn.execute(f"PRAGMA foreign_key_check({table})").fetchone():
            raise sqlite3.IntegrityError(f"rebuilding {table} broke a foreign key")
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
