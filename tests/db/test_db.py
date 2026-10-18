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
              "verdicts", "comments", "decisions", "events"}
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
