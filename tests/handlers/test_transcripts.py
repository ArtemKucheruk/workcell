import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import sql

from workcell import config, db
from workcell.handlers import runs
from workcell.handlers.transcripts import collect
from workcell.lib.transcript import folder_name
from workcell.server.deps import transaction

SID = "6f1c2e0a-1111-2222-3333-444455556666"
OLD = "2026-01-01T00:00:00Z"
COLUMNS = ("run_id", "task_id", "agent_type", "name", "round", "path", "model", "turns", "input_tokens",
           "cache_read_tokens", "output_tokens", "started_at", "ended_at")


def line(**fields) -> str:
    return json.dumps(fields)


def user(content, ts="2026-10-17T10:04:11.500Z", **extra) -> str:
    return line(type="user", timestamp=ts, message={"role": "user", "content": content}, **extra)


def assistant(msg_id, content, ts="2026-10-17T10:05:00.000Z", model="claude-opus-4-1", **extra) -> str:
    usage = {"input_tokens": 4, "cache_read_input_tokens": 100, "output_tokens": 9}
    return line(type="assistant", timestamp=ts, **extra,
                message={"id": msg_id, "model": model, "usage": usage, "content": content})


def jsonl(*lines: str) -> str:
    return "".join(f"{x}\n" for x in lines)


def spawn(name, subagent_type) -> str:
    """The lead's Agent tool_use that starts a teammate."""
    return assistant(f"spawn-{name}", [{"type": "tool_use", "id": f"toolu_{name}", "name": "Agent",
                                        "input": {"name": name, "subagent_type": subagent_type, "prompt": "go"}}])


def add_task(worktree) -> int:
    """A task whose worktree is `worktree`, in a fresh project."""
    db.init()
    ws = sql("INSERT INTO workspaces (name, created_at) VALUES (?, ?) RETURNING id", (str(worktree), OLD))[0][0]
    project = sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
                  " VALUES (?, 'p', ?, 'main', ?) RETURNING id", (ws, str(worktree), OLD))[0][0]
    return sql("INSERT INTO tasks (project_id, title, status, position, worktree_path, created_at, updated_at)"
               " VALUES (?, 't', 'in_progress', 1, ?, ?, ?) RETURNING id", (project, str(worktree), OLD, OLD))[0][0]


def add_run(task_id, session=SID, status="running", pid=None) -> int:
    return sql("INSERT INTO runs (task_id, session_id, pid, status, log_path, started_at)"
               " VALUES (?, ?, ?, ?, 'l', ?) RETURNING id", (task_id, session, pid, status, OLD))[0][0]


def folder(worktree) -> Path:
    return Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / folder_name(str(worktree))


def plant(worktree, rel: str, text: str) -> Path:
    """Writes `text` at `rel` under the worktree's Claude Code folder."""
    path = folder(worktree) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def copy(rel: str) -> Path:
    return config.data_dir() / "transcripts" / rel


def rows(run_id=None) -> list[dict]:
    where, args = ("WHERE run_id = ?", (run_id,)) if run_id else ("", ())
    return [dict(zip(COLUMNS, r)) for r in sql(f"SELECT {', '.join(COLUMNS)} FROM transcripts {where} ORDER BY id", args)]


@pytest.fixture
def wt(tmp_path) -> Path:
    path = tmp_path / "repo" / ".claude" / "worktrees" / "12-rate_limit"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def ran(wt):
    """A succeeded run of a task in `wt`: (run_id, task_id)."""
    task = add_task(wt)
    return SimpleNamespace(id=add_run(task, status="succeeded"), task=task)


MAIN = jsonl(user("/factory 12"), assistant("m1", [{"type": "text", "text": "hi"}], ts="2026-10-17T10:21:40.123Z"))


# --- Isolation and config ------------------------------------------------------------


def test_claude_config_dir_is_isolated(tmp_path):  # AC1
    assert Path(os.environ["CLAUDE_CONFIG_DIR"]).is_relative_to(tmp_path)
    assert config.claude_config_dir().is_relative_to(tmp_path)


def test_claude_config_dir(tmp_path, monkeypatch):  # AC2
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert config.claude_config_dir() == tmp_path / "cfg"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "")
    assert config.claude_config_dir() == Path.home() / ".claude"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert config.claude_config_dir() == Path.home() / ".claude" == tmp_path / "home" / ".claude"


# --- Collecting --------------------------------------------------------------------


def test_run_exit_copies_main_session(tmp_path, wt):  # AC4
    task = add_task(wt)
    run_id = add_run(task)
    source = plant(wt, f"{SID}.jsonl", MAIN)
    log = tmp_path / "run.jsonl"
    log.write_text(line(type="result", subtype="success", is_error=False, session_id=SID, result="ok") + "\n")
    runs.finish(transaction, run_id, SimpleNamespace(wait=lambda: 0), log)
    assert sql("SELECT status FROM runs WHERE id = ?", (run_id,)) == [("succeeded",)]
    assert copy(f"{run_id}/{SID}.jsonl").read_bytes() == source.read_bytes()
    assert rows() == [{
        "run_id": run_id, "task_id": task, "agent_type": "orchestrator", "name": None, "round": None,
        "path": f"{run_id}/{SID}.jsonl", "model": "claude-opus-4-1", "turns": 1, "input_tokens": 4,
        "cache_read_tokens": 100, "output_tokens": 9,
        "started_at": "2026-10-17T10:04:11Z", "ended_at": "2026-10-17T10:21:40Z",
    }]


def test_copies_from_active_account(tmp_path, wt):  # 056 BE19, Q8
    task = add_task(wt)
    two = tmp_path / "account-2"
    sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?)", (str(two), OLD))
    sql("UPDATE claude_accounts SET active = 0")
    sql("UPDATE claude_accounts SET active = 1 WHERE config_dir = ?", (str(two),))
    run_id = add_run(task)
    source = two / "projects" / folder_name(str(wt)) / f"{SID}.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(MAIN)
    plant(wt, f"{SID}/subagents/agent-a1.jsonl", MAIN)  # only under the server's own CLAUDE_CONFIG_DIR
    log = tmp_path / "run.jsonl"
    log.write_text(line(type="result", subtype="success", is_error=False, session_id=SID, result="ok") + "\n")
    runs.finish(transaction, run_id, SimpleNamespace(wait=lambda: 0), log)
    assert [r["path"] for r in rows()] == [f"{run_id}/{SID}.jsonl"]
    assert copy(f"{run_id}/{SID}.jsonl").read_bytes() == source.read_bytes()


def test_copies_from_each_runs_account(tmp_path):  # 096 AC22
    """Two runs in two accounts; account 3, holding neither's transcripts, is the active one."""
    made = []
    for n in (1, 2):
        wt = tmp_path / f"wt-{n}"
        wt.mkdir()
        task = add_task(wt)
        config_dir = tmp_path / f"account-{n}"
        account = sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?) RETURNING id",
                      (str(config_dir), OLD))[0][0]
        run_id = add_run(task, status="succeeded")
        sql("UPDATE runs SET account_id = ? WHERE id = ?", (account, run_id))
        source = config_dir / "projects" / folder_name(str(wt)) / f"{SID}.jsonl"
        source.parent.mkdir(parents=True)
        source.write_text(MAIN.replace("hi", f"run {n}"))
        made.append((run_id, source))
    third = tmp_path / "account-3"
    sql("INSERT INTO claude_accounts (config_dir, created_at) VALUES (?, ?)", (str(third), OLD))
    sql("UPDATE claude_accounts SET active = 0")
    sql("UPDATE claude_accounts SET active = 1 WHERE config_dir = ?", (str(third),))
    for run_id, source in made:
        collect(transaction, run_id)
        assert copy(f"{run_id}/{SID}.jsonl").read_bytes() == source.read_bytes()
    assert [r["run_id"] for r in rows()] == [made[0][0], made[1][0]]


def test_run_without_account_uses_active(tmp_path, wt):  # 096 AC23: a run from before 096
    task = add_task(wt)
    run_id = add_run(task, status="succeeded")
    assert sql("SELECT account_id FROM runs WHERE id = ?", (run_id,)) == [(None,)]
    source = plant(wt, f"{SID}.jsonl", MAIN)  # the active account's dir: the server's CLAUDE_CONFIG_DIR
    collect(transaction, run_id)
    assert copy(f"{run_id}/{SID}.jsonl").read_bytes() == source.read_bytes()


def test_subagents(ran, wt):  # AC5
    plant(wt, f"{SID}.jsonl", MAIN)
    sub = f"{SID}/subagents"
    a1 = plant(wt, f"{sub}/agent-a1.jsonl", jsonl(user("Review job 12.")))
    plant(wt, f"{sub}/agent-a1.meta.json", '{"agentType":"review-code","description":"x","toolUseId":"toolu_1"}')
    plant(wt, f"{sub}/agent-a2.jsonl", jsonl(user("no meta")))
    plant(wt, f"{sub}/agent-a3.jsonl", jsonl(user("bad meta")))
    plant(wt, f"{sub}/agent-a3.meta.json", "{not json")
    collect(transaction, ran.id)
    assert copy(f"{ran.id}/{sub}/agent-a1.jsonl").read_bytes() == a1.read_bytes()
    assert copy(f"{ran.id}/{sub}/agent-a2.jsonl").is_file() and copy(f"{ran.id}/{sub}/agent-a3.jsonl").is_file()
    assert not copy(f"{ran.id}/{sub}/agent-a1.meta.json").exists()  # out of scope: meta files aren't copied
    assert [(r["path"], r["agent_type"], r["name"]) for r in rows()] == [
        (f"{ran.id}/{SID}.jsonl", "orchestrator", None),
        (f"{ran.id}/{sub}/agent-a1.jsonl", "review-code", None),
        (f"{ran.id}/{sub}/agent-a2.jsonl", None, None),
        (f"{ran.id}/{sub}/agent-a3.jsonl", None, None),
    ]


def test_teammates(ran, wt):  # AC6
    plant(wt, f"{SID}.jsonl", jsonl(user("/factory 12"), spawn("builder-12", "builder")))
    team = {"teamName": f"session-{SID[:8]}", "agentName": "builder-12"}
    mate = plant(wt, "b0000000-0000-0000-0000-000000000001.jsonl",
                 jsonl(user("Task 12, round 2.", **team), assistant("x", [{"type": "text", "text": "done"}], **team)))
    plant(wt, "b0000000-0000-0000-0000-000000000001/subagents/agent-s1.jsonl", jsonl(user("hi")))
    plant(wt, "c0000000-0000-0000-0000-000000000002.jsonl",  # another run's teammate
          jsonl(user("Task 12, round 1.", teamName="session-deadbeef", agentName="builder-12")))
    plant(wt, "d0000000-0000-0000-0000-000000000003.jsonl", jsonl(user("a takeover, no team")))
    collect(transaction, ran.id)
    assert copy(f"{ran.id}/{mate.name}").read_bytes() == mate.read_bytes()
    assert [(r["path"], r["agent_type"], r["name"], r["round"]) for r in rows()] == [
        (f"{ran.id}/{SID}.jsonl", "orchestrator", None, None),
        (f"{ran.id}/{mate.name}", "builder", "builder-12", 2),
        (f"{ran.id}/b0000000-0000-0000-0000-000000000001/subagents/agent-s1.jsonl", None, None, None),
    ]
    assert not copy(f"{ran.id}/c0000000-0000-0000-0000-000000000002.jsonl").exists()
    assert not copy(f"{ran.id}/d0000000-0000-0000-0000-000000000003.jsonl").exists()


def test_teammate_without_spawn_has_no_type(ran, wt):  # AC6, Q2: no matching Agent tool_use → NULL
    plant(wt, f"{SID}.jsonl", MAIN)
    plant(wt, "b1.jsonl", jsonl(user("Task 12, round 1.", teamName=f"session-{SID[:8]}", agentName="ux-12")))
    collect(transaction, ran.id)
    assert [(r["agent_type"], r["name"]) for r in rows()] == [("orchestrator", None), (None, "ux-12")]


def test_collect_twice_updates(ran, wt):  # AC11
    source = plant(wt, f"{SID}.jsonl", MAIN)
    collect(transaction, ran.id)
    with source.open("a") as f:
        f.write(jsonl(assistant("m2", [{"type": "text", "text": "more"}], ts="2026-10-17T10:30:00Z")))
    collect(transaction, ran.id)
    found = rows()
    assert len(found) == 1
    assert (found[0]["turns"], found[0]["ended_at"]) == (2, "2026-10-17T10:30:00Z")
    assert copy(f"{ran.id}/{SID}.jsonl").read_bytes() == source.read_bytes()


def test_copy_failure_keeps_run(tmp_path, wt):  # AC13
    task = add_task(wt)
    run_id = add_run(task)
    plant(wt, f"{SID}.jsonl", MAIN)
    (config.data_dir() / "transcripts").write_text("a file, not a directory")
    log = tmp_path / "run.jsonl"
    log.write_text(line(type="result", subtype="success", is_error=False, session_id=SID, result="ok") + "\n")
    runs.finish(transaction, run_id, SimpleNamespace(wait=lambda: 0), log)
    assert sql("SELECT status, error FROM runs WHERE id = ?", (run_id,)) == [("succeeded", None)]
    assert rows() == []


def test_symlinks_skipped(ran, wt, tmp_path):  # AC14
    outside = tmp_path / "outside"
    (outside / "subagents").mkdir(parents=True)
    (outside / "secret.jsonl").write_text(MAIN)
    (outside / "subagents" / "agent-x.jsonl").write_text(MAIN)
    folder(wt).mkdir(parents=True)
    (folder(wt) / f"{SID}.jsonl").symlink_to(outside / "secret.jsonl")
    (folder(wt) / SID).mkdir()
    (folder(wt) / SID / "subagents").symlink_to(outside / "subagents")
    (folder(wt) / "mate.jsonl").symlink_to(outside / "secret.jsonl")
    collect(transaction, ran.id)
    assert rows() == []
    assert not copy(str(ran.id)).exists()


def test_symlinked_subagent_file_skipped(ran, wt, tmp_path):  # AC14
    plant(wt, f"{SID}.jsonl", MAIN)
    (tmp_path / "secret.jsonl").write_text(MAIN)
    plant(wt, f"{SID}/subagents/agent-ok.jsonl", MAIN)
    (folder(wt) / SID / "subagents" / "agent-x.jsonl").symlink_to(tmp_path / "secret.jsonl")
    collect(transaction, ran.id)
    assert [r["path"] for r in rows()] == [f"{ran.id}/{SID}.jsonl", f"{ran.id}/{SID}/subagents/agent-ok.jsonl"]
    assert not copy(f"{ran.id}/{SID}/subagents/agent-x.jsonl").exists()


def test_unsafe_session_id_never_leaves_the_folder(wt):  # §4.5: a session id from the run log is not a path
    task = add_task(wt)
    run_id = add_run(task, session="../../escape")
    plant(wt, "../../escape.jsonl", MAIN)
    collect(transaction, run_id)
    assert rows() == []
