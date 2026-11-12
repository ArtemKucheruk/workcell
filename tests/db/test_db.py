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
              "context_items", "task_deps"}  # 030 AC15, 051 BE1, 056, 057 BE1, 094
    assert {("table", t) for t in tables} <= rows
    assert {("index", "one_active_run"), ("index", "one_active_account")} <= rows


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


def test_one_active_run():  # AC13
    start_app()
    with closing(db.connect()) as conn:
        conn.execute("INSERT INTO workspaces (id, name, created_at) VALUES (1, 'w', ?)", (NOW,))
        conn.execute(
            "INSERT INTO projects (id, workspace_id, name, path, default_branch, created_at)"
            " VALUES (1, 1, 'p', '/p', 'main', ?)", (NOW,))
        conn.execute(
            "INSERT INTO tasks (id, project_id, title, status, position, created_at, updated_at)"
            " VALUES (1, 1, 't', 'in_progress', 1, ?, ?)", (NOW, NOW))
        run = ("INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
               " VALUES (1, ?, 'running', '/log', ?)")
        conn.execute(run, ("s1", NOW))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(run, ("s2", NOW))


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
    ("id", "INTEGER", 0), ("run_id", "INTEGER", 1), ("task_id", "INTEGER", 1), ("agent_type", "TEXT", 0),
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
                   ("created_at", "TEXT", 1), ("updated_at", "TEXT", 1)]  # 051 BE1: (name, type, notnull)


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
