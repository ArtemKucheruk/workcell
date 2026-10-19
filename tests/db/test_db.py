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
    tables = {"workspaces", "projects", "tasks", "runs", "rounds", "round_files",
              "verdicts", "comments", "decisions", "events", "transcripts"}  # 030 AC15
    assert {("table", t) for t in tables} <= rows
    assert ("index", "one_active_run") in rows


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
