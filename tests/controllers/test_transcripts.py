import subprocess
from types import SimpleNamespace

import pytest
from conftest import commit, sql
from controllers.test_runs import READY, SKILL, H, connect, fake, started  # noqa: F401
from controllers.test_runs import add_task as add_backlog_task
from fastapi.testclient import TestClient
from handlers.test_transcripts import (MAIN, SID, add_run, add_task, assistant, copy, jsonl, line, plant, rows,
                                       user)

from workcell.server.app import create_app
from workcell.server.deps import get_claude

LISTED = ("id", "run_id", "round", "agent_type", "name", "model", "turns", "input_tokens", "cache_read_tokens",
          "output_tokens", "started_at", "ended_at")


def add_transcript(run_id, task_id, path, round=None, started_at=None, text=None, **extra) -> int:
    """A transcripts row; `text` also writes its copy."""
    if text is not None:
        copy(path).parent.mkdir(parents=True, exist_ok=True)
        copy(path).write_text(text)
    fields = {"run_id": run_id, "task_id": task_id, "round": round, "path": path, "started_at": started_at,
              "agent_type": "builder", "name": "builder-12", "model": "claude-opus-4-1", "turns": 38,
              "input_tokens": 412, "cache_read_tokens": 1830211, "output_tokens": 20977,
              "ended_at": "2026-10-17T10:21:40Z"} | extra
    return sql(f"INSERT INTO transcripts ({', '.join(fields)}) VALUES ({', '.join(':' + k for k in fields)})"
               " RETURNING id", fields)[0][0]


@pytest.fixture
def ran(client, tmp_path):
    """A succeeded run of a task: .task, .id, .wt."""
    wt = tmp_path / "repo" / ".claude" / "worktrees" / "12-rate-limit"
    wt.mkdir(parents=True)
    task = add_task(wt)
    return type("Ran", (), {"task": task, "id": add_run(task, status="succeeded"), "wt": wt})


@pytest.fixture
def sleeper():
    """A live `sleep 60` in its own session, killed at teardown."""
    proc = subprocess.Popen(["sleep", "60"], start_new_session=True)
    yield proc
    proc.kill()
    proc.wait()


class NoStop:
    """A Claude adapter whose stop() leaves the process running."""
    def __init__(self):
        self.stopped = []

    def stop(self, pid):
        self.stopped.append(pid)


# --- When a copy happens ---------------------------------------------------------------


def test_stop_copies_at_once(client, tmp_path, sleeper):  # AC9
    wt = tmp_path / "wt"
    task = add_task(wt)
    run_id = add_run(task, pid=sleeper.pid)
    source = plant(wt, f"{SID}.jsonl", MAIN)
    adapter = NoStop()
    client.app.dependency_overrides[get_claude] = lambda: adapter
    r = client.post(f"/api/runs/{run_id}/stop", headers=H)
    assert (r.status_code, r.json()) == (200, {"id": run_id, "status": "stopped"})
    assert adapter.stopped == [sleeper.pid] and sleeper.poll() is None
    assert copy(f"{run_id}/{SID}.jsonl").read_bytes() == source.read_bytes()
    assert [(r["run_id"], r["agent_type"]) for r in rows()] == [(run_id, "orchestrator")]


def test_startup_cleanup_copies(tmp_path):  # AC10
    wt = tmp_path / "wt"
    task = add_task(wt)
    run_id = add_run(task)
    source = plant(wt, f"{SID}.jsonl", MAIN)
    with TestClient(create_app(), base_url="http://127.0.0.1:4545"):
        pass
    assert sql("SELECT status, error FROM runs WHERE id = ?", (run_id,)) == [("failed", "app restarted")]
    assert copy(f"{run_id}/{SID}.jsonl").read_bytes() == source.read_bytes()
    assert [(r["run_id"], r["path"]) for r in rows()] == [(run_id, f"{run_id}/{SID}.jsonl")]


def test_run_without_folder_is_unchanged(client, repo, fake):  # AC12
    commit(repo, {SKILL: READY})
    body = started(client, add_backlog_task(connect(client, repo)))
    assert sql("SELECT status, error, session_id FROM runs WHERE id = ?", (body["run_id"],)) == [
        ("succeeded", None, body["session_id"])]
    assert rows() == []


# --- GET /api/tasks/{id}/transcripts ---------------------------------------------------------


def test_list(client, ran):  # AC16
    later = add_run(ran.task, status="succeeded")
    ids = [
        add_transcript(later, ran.task, "b", started_at="2026-10-17T09:00:00Z"),
        add_transcript(ran.id, ran.task, "c", started_at="2026-10-17T11:00:00Z", round=2),
        add_transcript(ran.id, ran.task, "a", started_at="2026-10-17T10:04:11Z", round=1),
        add_transcript(ran.id, ran.task, "d", started_at="2026-10-17T11:00:00Z", name=None, agent_type=None),
    ]
    r = client.get(f"/api/tasks/{ran.task}/transcripts")
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body] == [ids[2], ids[1], ids[3], ids[0]]
    assert body[0] == {"id": ids[2], "run_id": ran.id, "round": 1, "agent_type": "builder", "name": "builder-12",
                       "model": "claude-opus-4-1", "turns": 38, "input_tokens": 412, "cache_read_tokens": 1830211,
                       "output_tokens": 20977, "started_at": "2026-10-17T10:04:11Z", "ended_at": "2026-10-17T10:21:40Z"}
    assert set(body[0]) == set(LISTED)  # no path (Q8), no task_id


def test_list_empty_and_unknown(client, ran):  # AC16
    assert client.get(f"/api/tasks/{ran.task}/transcripts").json() == []
    r = client.get("/api/tasks/99/transcripts")
    assert (r.status_code, r.json()) == (404, {"detail": "Task #99 not found"})


# --- GET /api/transcripts/{id} ---------------------------------------------------------------


TOOL_INPUT = {"command": "pytest -q", "description": "<b>x</b>"}
DETAIL = jsonl(
    line(type="system", subtype="init", timestamp="2026-10-17T10:04:10Z"),
    user("Task 12, round 1.", ts="2026-10-17T10:04:11.500Z"),
    assistant("A", [{"type": "thinking", "thinking": "plan it", "signature": "sig"}], ts="2026-10-17T10:04:12Z"),
    line(type="attachment", timestamp="2026-10-17T10:04:12.5Z", attachment={"x": 1}),
    assistant("A", [{"type": "text", "text": "<script>x</script> **hi**"}], ts="2026-10-17T10:04:13Z"),
    assistant("A", [{"type": "tool_use", "id": "t1", "name": "Bash", "input": TOOL_INPUT}], ts="2026-10-17T10:04:14Z"),
    user([{"type": "tool_result", "tool_use_id": "t1", "content": "3 passed", "is_error": False}],
         ts="2026-10-17T10:04:20Z"),
    user([{"type": "tool_result", "tool_use_id": "t2", "is_error": True,
           "content": [{"type": "text", "text": "line 1"}, {"type": "image", "source": {}},
                       {"type": "text", "text": "line 2"}]}], ts="2026-10-17T10:04:21Z"),
    assistant("B", [{"type": "redacted_thinking", "data": "x"}, {"type": "text", "text": "done"}],
              ts="2026-10-17T10:05:00Z"),
    assistant("C", [{"type": "redacted_thinking", "data": "x"}], ts="2026-10-17T10:05:01Z"),
    line(type="summary", summary="s"),
)


def test_detail(client, ran):  # AC17, 047 BE6
    tid = add_transcript(ran.id, ran.task, f"{ran.id}/{SID}.jsonl", round=1, started_at="2026-10-17T10:04:10Z",
                         text=DETAIL)
    r = client.get(f"/api/transcripts/{tid}")
    assert r.status_code == 200
    body = r.json()
    assert {k: body[k] for k in LISTED} == {
        "id": tid, "run_id": ran.id, "round": 1, "agent_type": "builder", "name": "builder-12",
        "model": "claude-opus-4-1", "turns": 38, "input_tokens": 412, "cache_read_tokens": 1830211,
        "output_tokens": 20977, "started_at": "2026-10-17T10:04:10Z", "ended_at": "2026-10-17T10:21:40Z"}
    assert body["task_id"] == ran.task and "path" not in body
    assert (body["factory_id"], body["factory"]) == (None, None)  # 103 AC9
    [(project_id, workspace_id)] = sql("SELECT p.id, p.workspace_id FROM tasks t JOIN projects p ON p.id = t.project_id"
                                       " WHERE t.id = ?", (ran.task,))
    assert {k: body[k] for k in ("project_id", "project", "workspace_id", "workspace")} == {
        "project_id": project_id, "project": "p", "workspace_id": workspace_id, "workspace": str(ran.wt)}
    assert client.get(f"/api/transcripts/{tid}/raw").content == copy(f"{ran.id}/{SID}.jsonl").read_bytes()
    assert body["messages"] == [
        {"role": "user", "at": "2026-10-17T10:04:11.500Z",
         "blocks": [{"type": "text", "text_html": "<p>Task 12, round 1.</p>\n"}]},
        {"role": "assistant", "at": "2026-10-17T10:04:12Z", "blocks": [
            {"type": "thinking", "text": "plan it"},
            {"type": "text", "text_html": "<p>&lt;script&gt;x&lt;/script&gt; <strong>hi</strong></p>\n"},
            {"type": "tool_use", "name": "Bash",
             "input": '{\n  "command": "pytest -q",\n  "description": "<b>x</b>"\n}'},
        ]},
        {"role": "user", "at": "2026-10-17T10:04:20Z",
         "blocks": [{"type": "tool_result", "text": "3 passed", "is_error": False, "truncated": False}]},
        {"role": "user", "at": "2026-10-17T10:04:21Z",
         "blocks": [{"type": "tool_result", "text": "line 1\n[image]\nline 2", "is_error": True, "truncated": False}]},
        {"role": "assistant", "at": "2026-10-17T10:05:00Z",
         "blocks": [{"type": "text", "text_html": "<p>done</p>\n"}]},
    ]


def automation_transcript(ran) -> SimpleNamespace:
    """103: an automation `Security audit` in ran.task's project, a run of it, and a transcript of that run."""
    [(project_id, workspace_id)] = sql("SELECT p.id, p.workspace_id FROM tasks t JOIN projects p ON p.id = t.project_id"
                                       " WHERE t.id = ?", (ran.task,))
    factory = sql("INSERT INTO factories (project_id, name, kind, graph, created_at, updated_at)"
                  " VALUES (?, 'Security audit', 'automation', '{}', 'x', 'x') RETURNING id", (project_id,))[0][0]
    run_id = sql("INSERT INTO runs (task_id, factory_id, kind, session_id, status, log_path, started_at)"
                 " VALUES (NULL, ?, 'automation', 's', 'succeeded', 'l', 'x') RETURNING id", (factory,))[0][0]
    tid = add_transcript(run_id, None, f"{run_id}/{SID}.jsonl", text=DETAIL)
    return SimpleNamespace(id=tid, run_id=run_id, factory=factory, project_id=project_id, workspace_id=workspace_id)


def test_automation_transcript(client, ran):  # 103 AC8
    x = automation_transcript(ran)
    r = client.get(f"/api/transcripts/{x.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {k: body[k] for k in ("run_id", "task_id", "factory_id", "factory", "project_id", "project", "workspace_id",
                                 "workspace")} == {
        "run_id": x.run_id, "task_id": None, "factory_id": x.factory, "factory": "Security audit",
        "project_id": x.project_id, "project": "p", "workspace_id": x.workspace_id, "workspace": str(ran.wt)}
    assert body["messages"]
    assert client.get(f"/api/transcripts/{x.id}/raw").content == copy(f"{x.run_id}/{SID}.jsonl").read_bytes()


def test_deleted_automation_transcript(client, ran):  # 103 AC10, Q9
    x = automation_transcript(ran)
    sql("DELETE FROM factories WHERE id = ?", (x.factory,))  # the run's factory_id becomes NULL
    for url in (f"/api/transcripts/{x.id}", f"/api/transcripts/{x.id}/raw"):
        r = client.get(url)
        assert (r.status_code, r.json()) == (404, {"detail": f"Transcript #{x.id} not found"})


def result_line(text: str) -> str:
    return user([{"type": "tool_result", "tool_use_id": "t", "content": text}])


def test_tool_result_cut(client, ran):  # AC18
    long, edge = "x" * 4000 + "y" * 1000, "z" * 4096
    tid = add_transcript(ran.id, ran.task, "t.jsonl", text=jsonl(result_line(long), result_line(edge)))
    cut = [m["blocks"][0] for m in client.get(f"/api/transcripts/{tid}").json()["messages"]]
    assert [(b["text"], b["truncated"]) for b in cut] == [(long[:4096], True), (edge, False)]
    whole = [m["blocks"][0] for m in client.get(f"/api/transcripts/{tid}?full=1").json()["messages"]]
    assert [(b["text"], b["truncated"]) for b in whole] == [(long, False), (edge, False)]


# --- GET /api/transcripts/{id}/raw -----------------------------------------------------------


def test_raw(client, ran):  # AC19
    tid = add_transcript(ran.id, ran.task, f"{ran.id}/{SID}.jsonl", text=DETAIL)
    r = client.get(f"/api/transcripts/{tid}/raw")
    assert r.status_code == 200
    assert r.content == copy(f"{ran.id}/{SID}.jsonl").read_bytes()
    assert r.headers["content-disposition"] == f'attachment; filename="transcript-{tid}.jsonl"'
    assert r.headers["x-content-type-options"] == "nosniff"


def test_not_found(client, ran):  # AC20
    for url in ("/api/transcripts/99", "/api/transcripts/99/raw"):
        r = client.get(url)
        assert (r.status_code, r.json()) == (404, {"detail": "Transcript #99 not found"})
    tid = add_transcript(ran.id, ran.task, "gone.jsonl")
    for url in (f"/api/transcripts/{tid}", f"/api/transcripts/{tid}/raw"):
        r = client.get(url)
        assert (r.status_code, r.json()) == (404, {"detail": f"Transcript #{tid} file missing"})


def test_paths_outside_the_store(client, ran, tmp_path):  # AC21
    (tmp_path / "secret.jsonl").write_text(MAIN)
    copy("").mkdir(parents=True, exist_ok=True)
    copy("link.jsonl").symlink_to(tmp_path / "secret.jsonl")
    for path in ("../factory.db", str(tmp_path / "secret.jsonl"), "link.jsonl", "a/../../factory.db"):
        tid = add_transcript(ran.id, ran.task, path)
        for url in (f"/api/transcripts/{tid}", f"/api/transcripts/{tid}/raw"):
            r = client.get(url)
            assert (r.status_code, r.json()) == (404, {"detail": f"Transcript #{tid} file missing"}), path
            assert b"SQLite" not in r.content and b"assistant" not in r.content


# --- GET /api/pages/tasks/{id} ----------------------------------------------------------------


def test_task_page_transcripts(client, ran):  # AC22
    assert client.get(f"/api/pages/tasks/{ran.task}").json()["transcripts"] == []
    add_transcript(ran.id, ran.task, "b", round=2, started_at="2026-10-17T11:00:00Z")
    add_transcript(ran.id, ran.task, "a", started_at="2026-10-17T10:00:00Z")
    page = client.get(f"/api/pages/tasks/{ran.task}")
    assert page.status_code == 200
    assert page.json()["transcripts"] == client.get(f"/api/tasks/{ran.task}/transcripts").json()
    assert [t["round"] for t in page.json()["transcripts"]] == [None, 2]
