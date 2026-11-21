"""053: GET /api/pages/agents, the Agents page's view-model."""

import json

import pytest
from conftest import sql
from controllers.test_pages_api import STARTED, add_round, api
from controllers.test_runs import add_task
from controllers.test_transcripts import add_transcript

# BE3: an orchestrator text line, Agent A, A's own Bash, A's answer, Agent B (subagent_type only), B's own Bash
AGENTS_LOG = r"""{"type":"assistant","message":{"content":[{"type":"text","text":"Reading #12"}]},"parent_tool_use_id":null}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_A","name":"Agent","input":{"name":"builder-12","subagent_type":"builder","description":"Build","prompt":"You build. Task 12, round 1. Go."}}]},"parent_tool_use_id":null}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_a1","name":"Bash","input":{"command":"pytest -q"}}]},"parent_tool_use_id":"toolu_A"}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_A","content":"built"}]},"parent_tool_use_id":null,"tool_use_result":{"status":"completed","totalDurationMs":754000}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_B","name":"Agent","input":{"subagent_type":"review-code","prompt":"Job 12, round 2. Review."}}]},"parent_tool_use_id":null}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_b1","name":"Bash","input":{"command":"fctl verdict 12 code PASS\nmore"}}]},"parent_tool_use_id":"toolu_B"}
"""
AGENTS = [  # the API contract's example
    {"name": "orchestrator", "type": None, "round": None, "running": True, "duration_ms": None,
     "last_tool": "Agent review-code"},
    {"name": "builder-12", "type": "builder", "round": 1, "running": False, "duration_ms": 754000,
     "last_tool": "Bash pytest -q"},
    {"name": "review-code", "type": "review-code", "round": 2, "running": True, "duration_ms": None,
     "last_tool": "Bash fctl verdict 12 code PASS"},
]
# BE6: AGENTS_LOG with junk mixed in; the bad Agent calls come before B, so the orchestrator's last tool line stays
# B's spawn (a malformed Agent call is still a tool line, as the run log shows it). The partial line has no newline.
_lines = AGENTS_LOG.split("\n")
MALFORMED_LOG = "\n".join([
    "warn", "[1,2]", _lines[0], '{"type":"assistant","message":null}',
    '{"type":"assistant","message":{"content":"a string"},"parent_tool_use_id":null}',
    _lines[1], '{"type":"user","message":{"content":[null,3]}}', _lines[2], _lines[3],
    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":7,"name":"Agent","input":{"name":"no-id"}}]},'
    '"parent_tool_use_id":null}',
    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_C","name":"Agent","input":"nope"}]},'
    '"parent_tool_use_id":null}',
    _lines[4], "warn", _lines[5], '{"type":"assistant","message":{"content":[{"type":"tool_u',
])
ORCHESTRATOR = {"name": "orchestrator", "type": None, "round": None, "running": True, "duration_ms": None,
                "last_tool": None}
RUNNING_KEYS = {"id", "kind", "task_id", "factory_id", "title", "project_id", "project", "stage", "round",
                "started_at", "agents"}  # 102: factory_id
RECENT_KEYS = {"id", "kind", "task_id", "factory_id", "title", "project_id", "project", "status", "error",
               "started_at", "ended_at", "transcripts"}  # 102: kind, factory_id


def tool(id, name, input, parent=None) -> str:
    """An assistant line holding one tool_use, as a JSON object text."""
    return json.dumps({"type": "assistant", "parent_tool_use_id": parent,
                       "message": {"content": [{"type": "tool_use", "id": id, "name": name, "input": input}]}})


def answer(id, result=None) -> str:
    line = {"type": "user", "parent_tool_use_id": None,
            "message": {"content": [{"type": "tool_result", "tool_use_id": id, "content": "ok"}]}}
    return json.dumps(line | ({} if result is None else {"tool_use_result": result}))


@pytest.fixture
def proj(client):
    """A project named `api` in its own workspace."""
    ws = sql("INSERT INTO workspaces (name, created_at) VALUES ('w', ?) RETURNING id", (STARTED,))[0][0]
    return sql("INSERT INTO projects (workspace_id, name, path, default_branch, created_at)"
               " VALUES (?, 'api', '/code/api', 'main', ?) RETURNING id", (ws, STARTED))[0][0]


def run(task_id, status, log_path="l", error=None, started=STARTED, ended=None):
    return sql("INSERT INTO runs (task_id, session_id, status, error, log_path, started_at, ended_at)"
               " VALUES (?, 's', ?, ?, ?, ?, ?) RETURNING id",
               (task_id, status, error, log_path, started, ended))[0][0]


def agents_for(client, proj, tmp_path, text) -> list[dict]:
    """The agents of a running run whose log holds `text`."""
    path = tmp_path / "run.jsonl"
    path.write_text(text)
    run(add_task(proj, status="in_progress"), "running", str(path))
    page = api(client, "/api/pages/agents")
    assert len(page["running"]) == 1
    return page["running"][0]["agents"]


def test_no_runs(client):  # BE1
    assert api(client, "/api/pages/agents") == {"running": [], "recent": []}


def test_running_row(client, proj):  # BE2
    task = add_task(proj, "Rate-limit login endpoint", status="in_progress", stage="agent_review")
    add_round(task, 1)
    add_round(task, 2)
    run_id = run(task, "running")
    page = api(client, "/api/pages/agents")
    assert page["recent"] == []
    [row] = page["running"]
    assert set(row) == RUNNING_KEYS  # no log_path, session_id, or status
    assert row == {"id": run_id, "kind": "factory", "task_id": task, "factory_id": None,
                   "title": "Rate-limit login endpoint",
                   "project_id": proj, "project": "api", "stage": "agent_review", "round": 2,
                   "started_at": STARTED, "agents": [ORCHESTRATOR]}

    sql("UPDATE runs SET status = 'succeeded', ended_at = ? WHERE id = ?", (STARTED, run_id))
    bare = run(add_task(proj, status="in_progress"), "running")
    [row] = api(client, "/api/pages/agents")["running"]
    assert (row["id"], row["round"], row["stage"]) == (bare, None, None)


def test_agents_from_log(client, proj, tmp_path):  # BE3
    assert agents_for(client, proj, tmp_path, AGENTS_LOG) == AGENTS


def test_agent_fallbacks(client, proj, tmp_path):  # BE4
    log = "\n".join([
        tool("t1", "Agent", {"description": "d", "prompt": "no round phrase here"}),
        tool("t2", "Agent", {"name": "p", "prompt": ["Task 1, round 3."]}),
        tool("t3", "Agent", {"name": "s", "prompt": "Task 1, round 4."}),
        answer("t3", {"totalDurationMs": "754000"}),
        tool("t4", "Agent", {"name": "b"}),
        answer("t4", {"totalDurationMs": True}),
        tool("t5", "Agent", {"name": "m"}),
        answer("t5"),
    ]) + "\n"
    found = agents_for(client, proj, tmp_path, log)
    assert [(a["name"], a["type"], a["round"]) for a in found[1:]] == [
        ("agent", None, None), ("p", None, None), ("s", None, 4), ("b", None, None), ("m", None, None)]
    assert [(a["running"], a["duration_ms"]) for a in found[1:]] == [
        (True, None), (True, None), (False, None), (False, None), (False, None)]
    assert all(a["last_tool"] is None for a in found[1:])  # no tool lines of their own


def test_subagent_lines(client, proj, tmp_path):  # BE5
    log = "\n".join([
        tool("A", "Agent", {"name": "a", "subagent_type": "builder"}),
        tool("T", "Task", {"name": "legacy", "subagent_type": "builder"}),  # Q10: not an Agent
        tool("N", "Bash", {"command": "echo", "name": "n"}),  # a name key alone makes no entry
        tool("a1", "Bash", {"command": "ls"}, parent="A"),
        tool("o1", "Bash", {"command": "git status"}),
        tool("a2", "Read", {"file_path": "x.py"}, parent="A"),  # after the orchestrator's last tool
        tool("g1", "Bash", {"command": "rm -rf x"}, parent="ghost"),  # no Agent call has this id
    ]) + "\n"
    assert agents_for(client, proj, tmp_path, log) == [
        ORCHESTRATOR | {"last_tool": "Bash git status"},
        {"name": "a", "type": "builder", "round": None, "running": True, "duration_ms": None, "last_tool": "Read x.py"},
    ]


def test_malformed_lines_skipped(client, proj, tmp_path):  # BE6
    assert not MALFORMED_LOG.endswith("\n")
    assert agents_for(client, proj, tmp_path, MALFORMED_LOG) == AGENTS


def test_missing_log(client, proj, tmp_path):  # BE7
    run(add_task(proj, status="in_progress"), "running", str(tmp_path / "missing.jsonl"))
    [row] = api(client, "/api/pages/agents")["running"]
    assert row["agents"] == [ORCHESTRATOR]


def test_recent_order(client, proj):  # BE8
    task = add_task(proj, "Webhooks", status="in_progress")
    no_end = run(task, "succeeded")  # 031's imported runs: no ended_at, listed last
    stopped = run(task, "stopped", ended="2026-10-21T09:52:03Z")
    failed = run(task, "failed", error="exit code 1", ended="2026-10-21T09:52:03Z")  # same ended_at: id desc
    succeeded = run(task, "succeeded", ended="2026-10-21T10:00:00Z")
    running = run(task, "running")
    page = api(client, "/api/pages/agents")
    assert [r["id"] for r in page["running"]] == [running]
    recent = page["recent"]
    assert [r["id"] for r in recent] == [succeeded, failed, stopped, no_end]
    assert all(set(r) == RECENT_KEYS for r in recent)
    assert recent[1] == {"id": failed, "kind": "factory", "task_id": task, "factory_id": None, "title": "Webhooks",
                         "project_id": proj, "project": "api",
                         "status": "failed", "error": "exit code 1", "started_at": STARTED,
                         "ended_at": "2026-10-21T09:52:03Z", "transcripts": 0}
    assert (recent[2]["status"], recent[2]["error"]) == ("stopped", None)
    assert recent[3]["ended_at"] is None


def test_recent_limit(client, proj):  # BE9
    task = add_task(proj, status="in_progress")
    minutes = [(i * 5 + 3) % 21 for i in range(21)]  # a shuffle, so id order isn't ended_at order
    ids = [run(task, "succeeded", ended=f"2026-10-21T10:{m:02d}:00Z") for m in minutes]
    recent = api(client, "/api/pages/agents")["recent"]
    first = ids[minutes.index(0)]
    assert first != ids[0]
    assert len(recent) == 20 and first not in [r["id"] for r in recent]


def test_recent_transcripts(client, proj):  # BE10
    task = add_task(proj, status="in_progress")
    two = run(task, "succeeded", ended="2026-10-21T10:00:00Z")
    none = run(task, "failed", error="exit code 1", ended="2026-10-21T09:00:00Z")
    add_transcript(two, task, "a/one.jsonl")
    add_transcript(two, task, "a/two.jsonl")
    recent = api(client, "/api/pages/agents")["recent"]
    assert [(r["id"], r["transcripts"]) for r in recent] == [(two, 2), (none, 0)]
