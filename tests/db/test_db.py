import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_factories import config, db
from claude_factories.server.app import create_app

NOW = "2026-10-17T00:00:00Z"


def start_app():
    with TestClient(create_app(), base_url="http://127.0.0.1:4545"):
        pass


def test_startup_creates_data_dir(tmp_path, monkeypatch):  # AC8
    monkeypatch.setenv("FCTL_HOME", str(tmp_path / "new"))
    assert not (tmp_path / "new").exists()
    start_app()
    assert (tmp_path / "new" / "factory.db").is_file()


def test_data_dir_defaults_to_home(tmp_path, monkeypatch):  # AC9
    monkeypatch.delenv("FCTL_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.data_dir() == tmp_path / ".claude-factories"


def test_schema_has_every_table_and_index():  # AC10
    start_app()
    with closing(db.connect()) as conn:
        rows = set(conn.execute("SELECT type, name FROM sqlite_master"))
    tables = {"workspaces", "projects", "tasks", "runs", "rounds", "round_files", "verdicts", "comments",
              "decisions", "events", "transcripts", "factories", "claude_accounts",
              "context_items", "task_deps", "settings"}  # 030 AC15, 051 BE1, 056, 057 BE1, 094, 096
    assert {("table", t) for t in tables} <= rows
    assert {("index", "one_run_per_task"), ("index", "one_active_account")} <= rows


def test_journal_mode_is_wal():  # AC11
    start_app()
    with closing(sqlite3.connect(Path(os.environ["FCTL_HOME"]) / "factory.db")) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_restart_keeps_data():  # AC12
    start_app()
    with closing(db.connect()) as conn, conn:
        conn.execute("INSERT INTO workspaces (name, created_at) VALUES ('personal', ?)", (NOW,))
    start_app()
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT name FROM workspaces").fetchall() == [("personal",)]


def test_one_run_per_task():  # AC13; 096 AC4
    start_app()
    with closing(db.connect()) as conn:
        conn.execute("INSERT INTO workspaces (id, name, created_at) VALUES (1, 'w', ?)", (NOW,))
        conn.execute(
            "INSERT INTO projects (id, workspace_id, name, path, default_branch, created_at)"
            " VALUES (1, 1, 'p', '/p', 'main', ?)", (NOW,))
        for task in (1, 2):
            conn.execute(
                "INSERT INTO tasks (id, project_id, title, status, position, created_at, updated_at)"
                " VALUES (?, 1, 't', 'in_progress', 1, ?, ?)", (task, NOW, NOW))
        run = ("INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
               " VALUES (?, ?, 'running', '/log', ?)")
        conn.execute(run, (1, "s1", NOW))
        conn.execute(run, (2, "s2", NOW))  # another task's running run is fine
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(run, (1, "s3", NOW))


def settings_value() -> int:
    with closing(db.connect()) as conn:
        return conn.execute("SELECT max_concurrent_runs FROM settings").fetchall()


def test_fresh_db_concurrent_runs():  # 096 AC1
    db.init()
    with closing(db.connect()) as conn:
        indexes = {name: sql for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index'")}
        columns = [c[1] for c in conn.execute("PRAGMA table_info(runs)")]
        fks = {(fk[2], fk[3], fk[4], fk[6]) for fk in conn.execute("PRAGMA foreign_key_list(runs)")}
    assert "one_active_run" not in indexes
    assert "ON runs(task_id) WHERE status = 'running'" in indexes["one_run_per_task"]
    assert "account_id" in columns
    assert ("claude_accounts", "account_id", "id", "SET NULL") in fks
    assert settings_value() == [(2,)]


BEFORE_096 = """
CREATE TABLE tasks (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), title TEXT NOT NULL,
  description_md TEXT NOT NULL DEFAULT '', spec_md TEXT, status TEXT NOT NULL, stage TEXT, position REAL NOT NULL,
  branch TEXT, worktree_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT,
  import_key TEXT UNIQUE, pr_url TEXT);
CREATE TABLE runs (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id), session_id TEXT NOT NULL,
  pid INTEGER, status TEXT NOT NULL, exit_code INTEGER, error TEXT, log_path TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT);
CREATE UNIQUE INDEX one_active_run ON runs(status) WHERE status = 'running';
"""


def test_old_db_gets_concurrent_runs():  # 096 AC2
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033 + BEFORE_096 + f"INSERT INTO tasks (id, project_id, title, status, position, created_at,"
                                        f" updated_at) VALUES (1, 1, 'a', 'backlog', 1, '{NOW}', '{NOW}');"
                                        f"INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
                                        f" VALUES (1, 's', 'succeeded', 'l', '{NOW}');")
    db.init()
    with closing(db.connect()) as conn:
        indexes = {name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert "one_active_run" not in indexes and "one_run_per_task" in indexes
        assert "account_id" in [c[1] for c in conn.execute("PRAGMA table_info(runs)")]
        assert conn.execute("SELECT id, account_id FROM runs").fetchall() == [(1, None)]
    assert settings_value() == [(2,)]
    db.init()  # a second init skips the ALTER
    assert settings_value() == [(2,)]


BEFORE_095 = f"""
CREATE TABLE claude_accounts (id INTEGER PRIMARY KEY, config_dir TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)), created_at TEXT NOT NULL);
INSERT INTO claude_accounts VALUES (1, '/old/claude', 1, '{NOW}');
"""


def test_old_db_gets_usage():  # 095 AC10
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033 + BEFORE_095)
    db.init()
    db.init()  # a second init skips the ALTER
    with closing(db.connect()) as conn:
        assert [c[1] for c in conn.execute("PRAGMA table_info(claude_accounts)")].count("email") == 1
        assert conn.execute("SELECT id, config_dir, email FROM claude_accounts").fetchall() == [(1, "/old/claude", None)]
        columns = [c[1] for c in conn.execute("PRAGMA table_info(usage_snapshots)")]
        assert columns == ["run_id", "account_id", "five_hour_utilization", "five_hour_resets_at", "five_hour_status",
                           "seven_day_utilization", "seven_day_resets_at", "seven_day_status", "status", "overage",
                           "limited", "recorded_at"]
        fks = {(fk[2], fk[3], fk[6]) for fk in conn.execute("PRAGMA foreign_key_list(usage_snapshots)")}
        assert fks == {("runs", "run_id", "CASCADE"), ("claude_accounts", "account_id", "CASCADE")}


def test_init_keeps_setting():  # 096 AC3
    db.init()
    with closing(db.connect()) as conn, conn:
        conn.execute("UPDATE settings SET max_concurrent_runs = 5")
    db.init()
    assert settings_value() == [(5,)]


def test_foreign_keys_on():  # AC14
    start_app()
    with closing(db.connect()) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
                " VALUES (999, 'p', '/p', 'main', ?)", (NOW,))


BEFORE_033 = f"""
CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  remote_url TEXT,
  default_branch TEXT NOT NULL,
  test_cmd TEXT,
  factory_version INTEGER,
  created_at TEXT NOT NULL);
INSERT INTO workspaces VALUES (1, 'w', '{NOW}');
INSERT INTO projects (id, workspace_id, name, path, default_branch, created_at) VALUES (1, 1, 'p', '/p', 'main', '{NOW}');
"""


def test_startup_adds_context_column():  # 033 AC2
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033)
    start_app()
    with closing(db.connect()) as conn:
        column = [c for c in conn.execute("PRAGMA table_info(projects)") if c[1] == "context_md"]
        assert [(name, kind, notnull, default) for _, name, kind, notnull, default, _ in column] == [
            ("context_md", "TEXT", 1, "''")]
        assert conn.execute("SELECT id, name, context_md FROM projects").fetchall() == [(1, "p", "")]
    start_app()
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT id, context_md FROM projects").fetchall() == [(1, "")]


def test_startup_adds_factory_sync_columns():  # 058 BE27, Q10
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033)
    start_app()
    start_app()  # a second startup finds them there
    with closing(db.connect()) as conn:
        columns = {name: (kind, notnull, default) for _, name, kind, notnull, default, _ in
                   conn.execute("PRAGMA table_info(projects)")}
        assert (columns["factory_mark"], columns["factory_error"]) == (("TEXT", 0, None), ("TEXT", 0, None))
        assert conn.execute("SELECT id, factory_mark, factory_error FROM projects").fetchall() == [(1, None, None)]
    schema = (Path(db.__file__).with_name("schema.sql")).read_text()
    projects = schema[schema.index("CREATE TABLE IF NOT EXISTS projects"):schema.index("CREATE TABLE IF NOT EXISTS tasks")]
    assert "factory_mark TEXT," in projects and "factory_error TEXT)" in projects


def test_startup_adds_task_deps():  # 094 AC1
    start_app()
    with closing(db.connect()) as conn, conn:  # a factory.db from before 094: no task_deps, one task
        conn.execute("DROP TABLE task_deps")
        conn.execute("INSERT INTO workspaces (id, name, created_at) VALUES (1, 'w', ?)", (NOW,))
        conn.execute("INSERT INTO projects (id, workspace_id, name, path, default_branch, created_at)"
                     " VALUES (1, 1, 'p', '/p', 'main', ?)", (NOW,))
        conn.execute("INSERT INTO tasks (id, project_id, title, status, position, created_at, updated_at)"
                     " VALUES (1, 1, 't', 'backlog', 1, ?, ?)", (NOW, NOW))
        before = conn.execute("SELECT * FROM tasks").fetchall()
    start_app()
    with closing(db.connect()) as conn:
        columns = [(name, notnull, pk) for _, name, _, notnull, _, pk in conn.execute("PRAGMA table_info(task_deps)")]
        assert columns == [("task_id", 1, 1), ("blocked_by_id", 1, 2)]
        assert conn.execute("SELECT * FROM tasks").fetchall() == before
        assert conn.execute("SELECT COUNT(*) FROM task_deps").fetchone() == (0,)


TRANSCRIPT_COLUMNS = [  # 030 AC15: (name, type, notnull)
    ("id", "INTEGER", 0), ("run_id", "INTEGER", 1), ("task_id", "INTEGER", 0), ("agent_type", "TEXT", 0),  # 102
    ("name", "TEXT", 0), ("round", "INTEGER", 0), ("path", "TEXT", 1), ("model", "TEXT", 0),
    ("turns", "INTEGER", 1), ("input_tokens", "INTEGER", 1), ("cache_read_tokens", "INTEGER", 1),
    ("output_tokens", "INTEGER", 1), ("started_at", "TEXT", 0), ("ended_at", "TEXT", 0),
]


def transcript_columns():
    with closing(db.connect()) as conn:
        return [(name, kind, notnull) for _, name, kind, notnull, _, _ in conn.execute("PRAGMA table_info(transcripts)")]


def test_startup_creates_transcripts_table():  # 030 AC15
    start_app()
    assert transcript_columns() == TRANSCRIPT_COLUMNS
    with closing(db.connect()) as conn:
        [unique] = [i for i in conn.execute("PRAGMA index_list(transcripts)") if i[2]]
        assert [c[2] for c in conn.execute(f"PRAGMA index_info({unique[1]})")] == ["run_id", "path"]


def test_old_db_gets_transcripts_table():  # 030 AC15: a factory.db made before this job
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033)
    start_app()
    assert transcript_columns() == TRANSCRIPT_COLUMNS
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT id, name FROM projects").fetchall() == [(1, "p")]


TASK = ("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at, import_key)"
        " VALUES (1, 't', 'backlog', 1, ?, ?, ?)")


def test_import_key_unique():  # 031 AC1
    start_app()
    with closing(db.connect()) as conn:
        conn.executescript("INSERT INTO workspaces VALUES (1, 'w', 'x');"
                           "INSERT INTO projects (id, workspace_id, name, path, default_branch, created_at)"
                           " VALUES (1, 1, 'p', '/p', 'main', 'x');")
        for _ in range(3):
            conn.execute(TASK, (NOW, NOW, None))
        conn.execute(TASK, (NOW, NOW, "factory:001-a"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(TASK, (NOW, NOW, "factory:001-a"))
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 4


def test_old_db_gets_import_key():  # 031 AC2
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033 + f"""
CREATE TABLE tasks (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), title TEXT NOT NULL,
  description_md TEXT NOT NULL DEFAULT '', spec_md TEXT, status TEXT NOT NULL, stage TEXT, position REAL NOT NULL,
  branch TEXT, worktree_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT);
INSERT INTO tasks (id, project_id, title, status, position, created_at, updated_at)
  VALUES (1, 1, 'old', 'backlog', 1, '{NOW}', '{NOW}'), (2, 1, 'old2', 'backlog', 2, '{NOW}', '{NOW}');
""")
    start_app()
    start_app()  # a second startup skips the ALTER
    with closing(db.connect()) as conn:
        assert "import_key" in [c[1] for c in conn.execute("PRAGMA table_info(tasks)")]
        assert conn.execute("SELECT id, import_key FROM tasks").fetchall() == [(1, None), (2, None)]
        conn.execute(TASK, (NOW, NOW, "factory:001-a"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(TASK, (NOW, NOW, "factory:001-a"))


def test_old_db_gets_pr_url():  # 093 AC1
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033 + f"""
CREATE TABLE tasks (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), title TEXT NOT NULL,
  description_md TEXT NOT NULL DEFAULT '', spec_md TEXT, status TEXT NOT NULL, stage TEXT, position REAL NOT NULL,
  branch TEXT, worktree_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT,
  import_key TEXT UNIQUE);
INSERT INTO tasks (id, project_id, title, status, position, created_at, updated_at)
  VALUES (1, 1, 'old', 'done', 1, '{NOW}', '{NOW}'), (2, 1, 'old2', 'backlog', 2, '{NOW}', '{NOW}');
""")
    db.init()
    db.init()  # a second init skips the ALTER
    with closing(db.connect()) as conn:
        assert [c[1] for c in conn.execute("PRAGMA table_info(tasks)")].count("pr_url") == 1
        assert conn.execute("SELECT id, pr_url FROM tasks").fetchall() == [(1, None), (2, None)]


FACTORY_COLUMNS = [("id", "INTEGER", 0), ("project_id", "INTEGER", 1), ("name", "TEXT", 1), ("graph", "TEXT", 1),
                   ("created_at", "TEXT", 1), ("updated_at", "TEXT", 1),
                   ("kind", "TEXT", 1)]  # 051 BE1: (name, type, notnull); 101 AC1: kind


def assert_factories_table():
    with closing(db.connect()) as conn:
        columns = conn.execute("PRAGMA table_info(factories)").fetchall()
        assert [(name, kind, notnull) for _, name, kind, notnull, _, _ in columns] == FACTORY_COLUMNS
        [unique] = [i for i in conn.execute("PRAGMA index_list(factories)") if i[2]]
        assert [c[2] for c in conn.execute(f"PRAGMA index_info({unique[1]})")] == ["project_id", "name"]
        [fk] = conn.execute("PRAGMA foreign_key_list(factories)").fetchall()
        assert (fk[2], fk[3], fk[4], fk[6]) == ("projects", "project_id", "id", "CASCADE")


def test_startup_creates_factories_table():  # 051 BE1
    start_app()
    assert_factories_table()


def test_old_db_gets_factories_table():  # 051 BE1: a factory.db made before this job
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033)
    start_app()
    start_app()
    assert_factories_table()
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT id, name FROM projects").fetchall() == [(1, "p")]
        assert conn.execute("SELECT id FROM workspaces").fetchall() == [(1,)]


FACTORY_ROW = f"INSERT INTO factories (project_id, name, graph, created_at, updated_at) VALUES (1, ?, '{{}}', '{NOW}', '{NOW}')"


def test_fresh_db_factory_kind():  # 101 AC1
    start_app()
    with closing(db.connect()) as conn:
        [kind] = [c for c in conn.execute("PRAGMA table_info(factories)") if c[1] == "kind"]
        assert (kind[2], kind[3], kind[4]) == ("TEXT", 1, "'workflow'")
        assert "CHECK (kind IN ('workflow','automation'))" in conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'factories'").fetchone()[0]
        conn.execute("INSERT INTO workspaces (name, created_at) VALUES ('w', ?)", (NOW,))
        conn.execute("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
                     " VALUES (1, 'p', '/p', 'main', ?)", (NOW,))
        conn.execute(FACTORY_ROW, ("a",))
        assert conn.execute("SELECT kind FROM factories").fetchall() == [("workflow",)]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE factories SET kind = 'nightly'")


def test_old_db_gets_factory_kind():  # 101 AC2
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033 + """
CREATE TABLE factories (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL, graph TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
""")
        conn.execute(FACTORY_ROW, ("old",))
        conn.commit()
    db.init()
    db.init()  # a second init skips the ALTER
    with closing(db.connect()) as conn:
        assert [c[1] for c in conn.execute("PRAGMA table_info(factories)")].count("kind") == 1
        assert conn.execute("SELECT name, kind FROM factories").fetchall() == [("old", "workflow")]
    assert_factories_table()


def accounts() -> list[tuple]:
    with closing(db.connect()) as conn:
        return conn.execute("SELECT config_dir, active FROM claude_accounts ORDER BY id").fetchall()


def test_old_db_gets_first_account(tmp_path, monkeypatch):  # 056 BE1, Q1
    db.init()
    with closing(db.connect()) as conn, conn:
        conn.execute("DROP TABLE claude_accounts")
        conn.execute("INSERT INTO workspaces (name, created_at) VALUES ('personal', ?)", (NOW,))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "old"))
    db.init()
    assert accounts() == [(str(tmp_path / "old"), 1)]
    db.init()
    assert accounts() == [(str(tmp_path / "old"), 1)]
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT name, created_at FROM workspaces").fetchall() == [("personal", NOW)]


def test_fresh_db_gets_first_account(tmp_path, monkeypatch):  # 056 BE2, Q1
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    db.init()
    assert accounts() == [(str(config.claude_config_dir()), 1)] == [(str(tmp_path / "home" / ".claude"), 1)]
    with closing(db.connect()) as conn, conn:
        conn.execute("DELETE FROM claude_accounts")
    db.init()
    assert accounts() == []


def test_one_active_account():  # 056 BE3
    db.init()
    with closing(db.connect()) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO claude_accounts (config_dir, active, created_at) VALUES ('/b', 1, ?)", (NOW,))
        [(first,)] = conn.execute("SELECT config_dir FROM claude_accounts").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?)", (first, NOW))


CONTEXT_ITEM_COLUMNS = [  # 057 BE1: (name, type, notnull)
    ("id", "INTEGER", 0), ("project_id", "INTEGER", 1), ("parent_id", "INTEGER", 0), ("kind", "TEXT", 1),
    ("title", "TEXT", 1), ("description", "TEXT", 1), ("content_md", "TEXT", 1), ("source_path", "TEXT", 0),
    ("position", "REAL", 1), ("created_at", "TEXT", 1), ("updated_at", "TEXT", 1),
]


def assert_context_items_table():
    with closing(db.connect()) as conn:
        columns = conn.execute("PRAGMA table_info(context_items)").fetchall()
        assert [(name, kind, notnull) for _, name, kind, notnull, _, _ in columns] == CONTEXT_ITEM_COLUMNS
        fks = {(fk[2], fk[3], fk[4], fk[6]) for fk in conn.execute("PRAGMA foreign_key_list(context_items)")}
        assert fks == {("projects", "project_id", "id", "CASCADE"), ("context_items", "parent_id", "id", "CASCADE")}
        conn.execute("INSERT INTO workspaces (id, name, created_at) VALUES (9, 'w9', ?)", (NOW,))
        conn.execute("INSERT INTO projects (id, workspace_id, name, path, default_branch, created_at)"
                     " VALUES (9, 9, 'p9', '/p9', 'main', ?)", (NOW,))
        with pytest.raises(sqlite3.IntegrityError):  # kind CHECK
            conn.execute("INSERT INTO context_items (project_id, kind, title, position, created_at, updated_at)"
                         " VALUES (9, 'folder', 't', 1, ?, ?)", (NOW, NOW))
        conn.rollback()


def test_startup_creates_context_items_table():  # 057 BE1
    start_app()
    assert_context_items_table()


def test_old_db_gets_context_items_table():  # 057 BE1: a factory.db made before this job
    home = Path(os.environ["FCTL_HOME"])
    home.mkdir()
    with closing(sqlite3.connect(home / "factory.db")) as conn:
        conn.executescript(BEFORE_033)
    db.init()
    with closing(db.connect()) as conn, conn:
        conn.execute("INSERT INTO context_items (project_id, kind, title, position, created_at, updated_at)"
                     " VALUES (1, 'item', 'kept', 1, ?, ?)", (NOW, NOW))
    db.init()  # a second init changes nothing
    assert_context_items_table()
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT project_id, title FROM context_items").fetchall() == [(1, "kept")]
        assert conn.execute("SELECT id, name FROM projects").fetchall() == [(1, "p")]


# --- 102: runs without a task (automation runs) --------------------------------------------------------------

RUN_ROW = ("INSERT INTO runs (task_id, session_id, status, log_path, started_at, kind, factory_id)"
           " VALUES (?, 's', 'succeeded', 'l', ?, ?, ?)")


def seed_project(conn):
    conn.execute("INSERT INTO workspaces (id, name, created_at) VALUES (1, 'w', ?)", (NOW,))
    conn.execute("INSERT INTO projects (id, workspace_id, name, path, default_branch, created_at)"
                 " VALUES (1, 1, 'p', '/p', 'main', ?)", (NOW,))
    conn.execute("INSERT INTO tasks (id, project_id, title, status, position, created_at, updated_at)"
                 " VALUES (1, 1, 't', 'in_progress', 1, ?, ?)", (NOW, NOW))
    conn.execute(FACTORY_ROW, ("Security audit",))


def test_fresh_db_automation_runs():  # 102 AC1
    db.init()
    with closing(db.connect()) as conn, conn:
        columns = {c[1]: (c[2], c[3], c[4]) for c in conn.execute("PRAGMA table_info(runs)")}
        assert columns["task_id"] == ("INTEGER", 0, None)
        assert columns["factory_id"] == ("INTEGER", 0, None)
        assert columns["kind"] == ("TEXT", 1, "'factory'")
        assert columns["trigger"] == ("TEXT", 1, "'manual'")
        assert columns["worktree_path"] == ("TEXT", 0, None)
        fks = {(fk[2], fk[3], fk[4], fk[6]) for fk in conn.execute("PRAGMA foreign_key_list(runs)")}
        assert ("factories", "factory_id", "id", "SET NULL") in fks
        assert [c for c in conn.execute("PRAGMA table_info(transcripts)") if c[1] == "task_id"][0][3] == 0
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'one_run_per_task'").fetchone()
        seed_project(conn)
        conn.execute(RUN_ROW, (None, NOW, "automation", 1))
        conn.execute(RUN_ROW, (1, NOW, "factory", None))
        assert conn.execute("SELECT kind, trigger FROM runs ORDER BY id").fetchall() == [
            ("automation", "manual"), ("factory", "manual")]
        for bad in ((None, NOW, "factory", None), (1, NOW, "automation", 1), (1, NOW, "nightly", None)):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(RUN_ROW, bad)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE runs SET trigger = 'cron'")


BEFORE_102 = """
CREATE TABLE runs (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id), session_id TEXT NOT NULL,
  pid INTEGER, status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','stopped')), exit_code INTEGER,
  error TEXT, log_path TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
  account_id INTEGER REFERENCES claude_accounts(id) ON DELETE SET NULL);
CREATE UNIQUE INDEX one_run_per_task ON runs(task_id) WHERE status = 'running';
CREATE TABLE transcripts (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
  task_id INTEGER NOT NULL REFERENCES tasks(id), agent_type TEXT, name TEXT, round INTEGER, path TEXT NOT NULL,
  model TEXT, turns INTEGER NOT NULL, input_tokens INTEGER NOT NULL, cache_read_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL, started_at TEXT, ended_at TEXT, UNIQUE (run_id, path));
"""


def test_old_db_rebuilds_runs():  # 102 AC2
    db.init()
    with closing(db.connect()) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript("DROP TABLE runs; DROP TABLE transcripts;" + BEFORE_102)
        with conn:
            seed_project(conn)
            conn.execute("INSERT INTO runs VALUES (5, 1, 's5', 42, 'failed', 1, 'boom', '/l5', ?, ?, 1)", (NOW, NOW))
            conn.execute("INSERT INTO runs VALUES (7, 1, 's7', NULL, 'running', NULL, NULL, '/l7', ?, NULL, NULL)",
                         (NOW,))
            conn.execute("INSERT INTO transcripts VALUES (3, 5, 1, 'orchestrator', NULL, 1, '5/a.jsonl', 'm', 2, 10,"
                         " 20, 30, ?, ?)", (NOW, NOW))
            conn.execute("INSERT INTO usage_snapshots VALUES (5, 1, 0.5, 1, 'allowed', 0.2, 2, 'allowed', NULL, 0,"
                         " 0, ?)", (NOW,))
        runs_before = conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
        transcripts_before = conn.execute("SELECT * FROM transcripts").fetchall()
    db.init()
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT id, task_id, session_id, pid, status, exit_code, error, log_path, started_at,"
                            " ended_at, account_id FROM runs ORDER BY id").fetchall() == runs_before
        assert conn.execute("SELECT kind, trigger, factory_id, worktree_path FROM runs").fetchall() == [
            ("factory", "manual", None, None)] * 2
        assert conn.execute("SELECT * FROM transcripts").fetchall() == transcripts_before
        assert conn.execute("SELECT run_id FROM usage_snapshots").fetchall() == [(5,)]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'one_run_per_task'").fetchone()
        assert [c for c in conn.execute("PRAGMA table_info(transcripts)") if c[1] == "task_id"][0][3] == 0
        with pytest.raises(sqlite3.IntegrityError):  # one_run_per_task is back: task 1 already runs #7
            conn.execute("INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
                         " VALUES (1, 's', 'running', 'l', ?)", (NOW,))
        schema = conn.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    db.init()  # a second init changes nothing
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall() == schema
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone() == (2,)
