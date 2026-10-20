"""032: GET /api/tasks/{id}/export, POST /api/projects/{id}/import, and the docs."""

import io
import json
import sqlite3
import stat
import zipfile
from contextlib import closing
from pathlib import Path

import pytest
from conftest import git, sql

from claude_factories import config, db
from claude_factories.handlers.transcripts import load
from claude_factories.lib.patch import split_patch
from claude_factories.repositories.reviews import ReviewsRepo
from claude_factories.repositories.rounds import RoundsRepo
from claude_factories.repositories.runs import RunsRepo
from claude_factories.repositories.tasks import TasksRepo
from claude_factories.repositories.transcripts import TranscriptsRepo

H = {"X-Requested-By": "fctl"}
ROOT = Path(__file__).resolve().parents[2]
REVIEWERS = ("security", "ux", "ui", "code")
TABLES = ("tasks", "events", "rounds", "round_files", "verdicts", "decisions", "comments", "runs", "transcripts")
AT = ["2026-10-17T10:00:01Z", "2026-10-17T10:01:03Z", "2026-10-17T10:02:05Z", "2026-10-17T10:03:06Z",
      "2026-10-17T10:04:07Z", "2026-10-17T10:05:09Z", "2026-10-17T10:06:11Z", "2026-10-17T10:07:12Z",
      "2026-10-17T10:08:13Z", "2026-10-17T10:09:15Z"]
SPEC = "# Spec — ü\r\n\n- [ ] AC1\n  trailing  \n"
PATCH = (  # round 1: an added file and a modified one
    "diff --git a/a.py b/a.py\nnew file mode 100644\nindex 0000000..1111111\n--- /dev/null\n+++ b/a.py\n"
    "@@ -0,0 +1 @@\n+x = 1\n"
    "diff --git a/b.py b/b.py\nindex 1111111..2222222 100644\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-y = 1\n+y = 2\n"
)
EVENTS = [("me", None, "backlog", None, AT[0]), ("app", "backlog", "in_progress", None, AT[1]),
          ("orchestrator", "in_progress", "review", "human_review", AT[3]),
          ("app", "review", "in_progress", "rework", AT[6]),
          ("orchestrator", "in_progress", "review", "human_review", AT[9])]
S1 = "6f1c2e0a-1111-2222-3333-444455556666"
S2 = "7a2d3f1b-1111-2222-3333-444455556666"


def even(at: str) -> str:
    """Q4: ZIP's 2-second steps."""
    s = int(at[17:19])
    return f"{at[:17]}{s - s % 2:02d}Z"


def zip_time(at: str) -> tuple:
    return tuple(int(x) for x in (at[:4], at[5:7], at[8:10], at[11:13], at[14:16], even(at)[17:19]))


def rows(query, args=()) -> list[dict]:
    with closing(db.connect()) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(query, args)]


def counts() -> dict:
    return {t: sql(f"SELECT COUNT(*) FROM {t}")[0][0] for t in TABLES}


def stored() -> dict:
    """Every file under FCTL_HOME/transcripts/ with its bytes."""
    root = config.data_dir() / "transcripts"
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def connect(client, path) -> int:
    r = client.post("/api/projects/connect", headers=H,
                    json={"path": str(path), "workspace": "w", "name": path.name, "default_branch": "main"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture
def ab(client, tmp_path) -> tuple[int, int]:
    """A and B: two connected projects on temp git repos."""
    found = []
    for name in ("a", "b"):
        git(tmp_path, "init", "-q", "-b", "main", str(tmp_path / name))
        found.append(connect(client, tmp_path / name))
    return found[0], found[1]


def build(project: int) -> int:
    """T, the spec's fixture task, written through the repositories so every time is known."""
    path = sql("SELECT path FROM projects WHERE id = ?", (project,))[0][0]
    with closing(db.connect()) as conn, conn:
        conn.row_factory = sqlite3.Row
        tasks, rounds, reviews = TasksRepo(conn), RoundsRepo(conn), ReviewsRepo(conn)
        t = tasks.add(project, "Rate-limit login", "Max 5 failed logins/min per IP.", "review", "human_review", 1.0,
                      AT[0])
        tasks.set_spec(t, SPEC, AT[0])
        tasks.set_worktree(t, f"factory/{t}-rate-limit", f"{path}/.claude/worktrees/{t}-rate-limit")
        rounds.add(t, 1, "initial", "abc123", None, split_patch(PATCH), AT[2])
        r1 = rounds.by_n(t, "1")["id"]
        for who in REVIEWERS:
            reviews.put_verdict(r1, who, "CHANGES" if who == "security" else "PASS", f"{who} findings", AT[3])
        reviews.add_comment(t, r1, "security", "b.py", 1, "new", "Check this line.", AT[4])
        reviews.add_comment(t, r1, "me", None, None, None, "Close.", AT[5])
        reviews.add_decision(t, r1, "me", "CHANGES_REQUESTED", "Make the limit configurable.\n", AT[6])
        rounds.add(t, 2, "human", "abc123", "Round 2 notes.\n", [], AT[7])
        reviews.add_decision(t, rounds.by_n(t, "2")["id"], "approver", "APPROVE", "All good.", AT[8])
        for e in EVENTS:
            tasks.add_event(t, *e)
    return t


@pytest.fixture
def t(ab) -> int:
    return build(ab[0])


def line(**fields) -> str:
    return json.dumps(fields) + "\n"


def transcript(start: str, end: str, model: str) -> str:
    return (line(type="user", timestamp=start, message={"role": "user", "content": "go"})
            + line(type="assistant", timestamp=end, message={
                "id": "m1", "model": model, "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 4, "cache_read_input_tokens": 100, "output_tokens": 9}}))


LISTED = [(f"{S1}.jsonl", transcript("2026-10-17T10:04:11.500Z", "2026-10-17T10:05:00.000Z", "claude-opus-4-1"),
           "orchestrator", None, None),
          (f"{S1}/subagents/agent-a.jsonl", transcript("2026-10-17T10:04:30.000Z", "2026-10-17T10:06:00.000Z",
                                                       "claude-sonnet-4"), "review-code", "rev", 1)]


@pytest.fixture
def with_transcripts(t) -> int:
    """T's 2 transcript rows in S1's run, with copies; S2's row has lost its copy. The run's id."""
    store = config.data_dir() / "transcripts"
    with closing(db.connect()) as conn, conn:
        runs, transcripts = RunsRepo(conn), TranscriptsRepo(conn)
        run, gone = runs.imported(t, S1, AT[1], AT[9]), runs.imported(t, S2, AT[1], AT[9])
        for rid, (rel, text, kind, name, n) in [(run, LISTED[0]), (run, LISTED[1]), (gone, LISTED[0])]:
            path = store / str(rid) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            transcripts.upsert(load(path) | {"agent_type": kind, "name": name, "round": n, "run_id": rid,
                                             "task_id": t, "path": f"{rid}/{rel}"})
    (store / str(gone) / LISTED[0][0]).unlink()
    return run


def export(client, task_id, query=""):
    return client.get(f"/api/tasks/{task_id}/export{query}")


def bundle(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def body_of(client, task_id, query="") -> bytes:
    r = export(client, task_id, query)
    assert r.status_code == 200, r.text
    return r.content


def task_json(content: bytes) -> dict:
    return json.loads(bundle(content).read("task.json"))


def post(client, project, body, headers=H):
    return client.post(f"/api/projects/{project}/import", content=body, headers=headers)


def ok(client, project, body) -> dict:
    r = post(client, project, body)
    assert r.status_code == 200, r.text
    return r.json()


def rezip(content: bytes, add: dict | None = None, drop=(), extra=(), **fields) -> bytes:
    """The bundle with entries dropped, added or replaced (name → text, or None for a folder), raw (ZipInfo,
    bytes) entries appended, and task.json's top-level `fields` replaced."""
    add = add or {}
    src, out = bundle(content), io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for info in src.infolist():
            if info.filename in drop or info.filename in add:
                continue
            if info.is_dir():
                zf.mkdir(info)
                continue
            data = src.read(info)
            if info.filename == "task.json" and fields:
                data = json.dumps(json.loads(data) | fields).encode()
            zf.writestr(info, data)
        for name, data in add.items():
            if data is None or name.endswith("/"):
                zf.mkdir(name)
            else:
                zf.writestr(zipfile.ZipInfo(name, (2026, 10, 17, 10, 0, 0)), data)
        for info, data in extra:
            zf.writestr(info, data)
    return out.getvalue()


def task_row(task_id) -> dict:
    [found] = rows("SELECT * FROM tasks WHERE id = ?", (task_id,))
    return found


def events_of(task_id) -> list[tuple]:
    return [(e["actor"], e["from_status"], e["to_status"], e["stage"], e["created_at"])
            for e in rows("SELECT * FROM events WHERE task_id = ? ORDER BY id", (task_id,))]


# --- Export ------------------------------------------------------------------------------------


def test_export_response(client, t):  # AC1
    r = export(client, t)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == f'attachment; filename="task-{t}.zip"'
    assert r.headers["x-content-type-options"] == "nosniff"


def test_entries(client, t):  # AC2
    infos = bundle(body_of(client, t)).infolist()
    assert sorted(i.filename for i in infos if not i.is_dir()) == sorted([
        "task.json", "spec.md", "round-1/diff.patch", *(f"round-1/review-{r}.md" for r in REVIEWERS),
        "round-2/build.md", "round-2/diff.patch", "feedback-2.md", "decision.md"])
    assert sorted(i.filename for i in infos if i.is_dir()) == ["round-1/", "round-2/"]
    assert all(not i.filename.startswith(("/", "task-")) and ".." not in i.filename for i in infos)


def test_spec_and_build_notes(client, ab, t):  # AC3
    z = bundle(body_of(client, t))
    assert z.read("spec.md") == SPEC.encode()
    assert z.read("round-2/build.md") == b"Round 2 notes.\n"
    assert "round-1/build.md" not in z.namelist()
    bare = client.post(f"/api/projects/{ab[0]}/tasks", json={"title": "No spec"}, headers=H).json()["id"]
    assert "spec.md" not in bundle(body_of(client, bare)).namelist()


def test_diff_patch(client, t):  # AC4
    z = bundle(body_of(client, t))
    for n in (1, 2):
        r = client.get(f"/api/tasks/{t}/rounds/{n}/diff")
        assert z.read(f"round-{n}/diff.patch") == r.content
    assert z.read("round-1/diff.patch") == PATCH.encode()
    assert z.read("round-2/diff.patch") == b""


def test_reviews(client, t):  # AC5
    z = bundle(body_of(client, t))
    assert z.read("round-1/review-security.md") == b"VERDICT: CHANGES\n\nsecurity findings\n"
    assert z.read("round-1/review-ux.md") == b"VERDICT: PASS\n\nux findings\n"
    sql("DELETE FROM verdicts WHERE reviewer = 'ui'")
    assert "round-1/review-ui.md" not in bundle(body_of(client, t)).namelist()


def test_feedback(client, t):  # AC6
    assert bundle(body_of(client, t)).read("feedback-2.md") == b"Make the limit configurable.\n"


def test_decision(client, t):  # AC7
    assert bundle(body_of(client, t)).read("decision.md") == b"APPROVE\n\nAll good.\n"
    with closing(db.connect()) as conn, conn:
        RoundsRepo(conn).add(t, 3, "agent", "abc123", "three", [], AT[9])
    assert "decision.md" not in bundle(body_of(client, t)).namelist()


def test_task_json(client, t):  # AC8
    data = task_json(body_of(client, t))
    assert list(data) == ["import_key", "title", "description_md", "status", "stage", "events", "comments"]
    assert (data["title"], data["description_md"], data["status"], data["stage"]) == (
        "Rate-limit login", "Max 5 failed logins/min per IP.", "review", "human_review")
    assert data["events"] == [dict(zip(("actor", "from_status", "to_status", "stage", "created_at"), e))
                              for e in EVENTS]
    assert data["comments"] == [
        {"round": 1, "author": "security", "path": "b.py", "line": 1, "side": "new", "body_md": "Check this line.",
         "created_at": AT[4]},
        {"round": 1, "author": "me", "path": None, "line": None, "side": None, "body_md": "Close.",
         "created_at": AT[5]}]


def test_no_paths(client, ab, t):  # AC9
    text = bundle(body_of(client, t)).read("task.json").decode()
    project, worktree = sql("SELECT p.path, t.worktree_path FROM tasks t JOIN projects p ON p.id = t.project_id"
                            " WHERE t.id = ?", (t,))[0]
    assert worktree and project not in text and worktree not in text


def test_import_key(client, t):  # AC10
    assert task_json(body_of(client, t))["import_key"] == f"task:{t}@{AT[0]}"
    assert sql("SELECT import_key FROM tasks WHERE id = ?", (t,)) == [(None,)]
    sql("UPDATE tasks SET import_key = 'factory:014-run-ui' WHERE id = ?", (t,))
    assert task_json(body_of(client, t))["import_key"] == "factory:014-run-ui"


def test_entry_times(client, t):  # AC11
    when = {"task.json": AT[0], "spec.md": AT[0], "round-1/": AT[2], "round-1/diff.patch": AT[2],
            "round-2/": AT[7], "round-2/build.md": AT[7], "round-2/diff.patch": AT[7], "feedback-2.md": AT[6],
            "decision.md": AT[8]} | {f"round-1/review-{r}.md": AT[3] for r in REVIEWERS}
    infos = bundle(body_of(client, t)).infolist()
    assert {i.filename: i.date_time for i in infos} == {name: zip_time(at) for name, at in when.items()}
    assert zip_time(AT[0])[5] == 0 and zip_time(AT[3])[5] == 6  # 01 → 00, 06 stays


def test_no_transcripts_by_default(client, t, with_transcripts):  # AC12
    content = body_of(client, t)
    assert not [n for n in bundle(content).namelist() if n.startswith("transcripts/")]
    assert "transcripts" not in task_json(content)


def test_transcripts_on_request(client, t, with_transcripts):  # AC13
    content = body_of(client, t, "?transcripts=1")
    z, run = bundle(content), with_transcripts
    store = config.data_dir() / "transcripts"
    names = [n for n in z.namelist() if n.startswith("transcripts/")]
    assert names == [f"transcripts/{run}/{rel}" for rel, *_ in LISTED]
    for name in names:
        assert z.read(name) == (store / name.removeprefix("transcripts/")).read_bytes()
    assert task_json(content)["transcripts"] == [
        {"path": f"{run}/{rel}", "session_id": S1, "agent_type": kind, "name": name, "round": n}
        for rel, _, kind, name, n in LISTED]


def test_export_unknown_task(client):  # AC14
    r = export(client, 99)
    assert (r.status_code, r.json()["detail"]) == (404, "Task #99 not found")


# --- Import ------------------------------------------------------------------------------------


@pytest.fixture
def copied(client, ab, t) -> dict:
    """T's export imported into B: the response."""
    return ok(client, ab[1], body_of(client, t))


def test_import_response(client, ab, t, copied):  # AC15
    key = f"task:{t}@{AT[0]}"
    assert copied == {"task_id": copied["task_id"], "title": "Rate-limit login", "import_key": key, "created": True,
                      "status": "review", "rounds": 2, "transcripts": 0}
    assert copied["task_id"] != t
    row = task_row(copied["task_id"])
    assert (row["project_id"], row["import_key"]) == (ab[1], key)


def test_import_fields(client, t, copied):  # AC16
    new, old = task_row(copied["task_id"]), task_row(t)
    for k in ("title", "description_md", "spec_md"):
        assert new[k] == old[k], k
    assert (new["branch"], new["worktree_path"]) == (None, None)


def round_rows(task_id) -> list[dict]:
    return rows("SELECT * FROM rounds WHERE task_id = ? ORDER BY n", (task_id,))


def files_of(task_id) -> list[dict]:
    return rows("SELECT r.n, f.path, f.old_path, f.change, f.binary, f.additions, f.deletions, f.patch"
                " FROM round_files f JOIN rounds r ON r.id = f.round_id WHERE r.task_id = ? ORDER BY r.n, f.rowid",
                (task_id,))


def test_import_rounds(client, t, copied):  # AC17
    new, old = round_rows(copied["task_id"]), round_rows(t)
    assert [(r["n"], r["trigger"], r["build_md"], r["base_sha"]) for r in new] == [
        (1, "initial", None, "unknown"), (2, "human", "Round 2 notes.\n", "unknown")]
    assert [r["build_md"] for r in new] == [r["build_md"] for r in old]
    assert files_of(copied["task_id"]) == files_of(t) and len(files_of(t)) == 2


def verdicts_of(task_id) -> list[tuple]:
    return [tuple(v.values()) for v in rows(
        "SELECT r.n, v.reviewer, v.verdict, v.body_md, v.created_at FROM verdicts v JOIN rounds r ON r.id = v.round_id"
        " WHERE r.task_id = ? ORDER BY r.n, v.reviewer", (task_id,))]


def decisions_of(task_id) -> list[tuple]:
    return [tuple(d.values()) for d in rows(
        "SELECT r.n, d.actor, d.decision, d.body_md, d.created_at FROM decisions d JOIN rounds r ON r.id = d.round_id"
        " WHERE d.task_id = ? ORDER BY d.id", (task_id,))]


def comments_of(task_id) -> list[tuple]:
    return [tuple(c.values()) for c in rows(
        "SELECT r.n, c.author, c.path, c.line, c.side, c.body_md, c.created_at FROM comments c"
        " JOIN rounds r ON r.id = c.round_id WHERE c.task_id = ? ORDER BY c.id", (task_id,))]


def test_import_reviews(client, t, copied):  # AC18
    new = copied["task_id"]
    assert [v[:4] for v in verdicts_of(new)] == [v[:4] for v in verdicts_of(t)] and len(verdicts_of(t)) == 4
    assert [d[:4] for d in decisions_of(new)] == [d[:4] for d in decisions_of(t)] == [
        (1, "me", "CHANGES_REQUESTED", "Make the limit configurable.\n"), (2, "approver", "APPROVE", "All good.")]
    assert [c[:6] for c in comments_of(new)] == [c[:6] for c in comments_of(t)] and len(comments_of(t)) == 2


def test_import_times(client, t, copied):  # AC19
    new = copied["task_id"]
    assert [r["created_at"] for r in round_rows(new)] == [even(r["created_at"]) for r in round_rows(t)]
    assert [v[4] for v in verdicts_of(new)] == [even(v[4]) for v in verdicts_of(t)]
    assert [d[4] for d in decisions_of(new)] == [even(d[4]) for d in decisions_of(t)]
    assert even(AT[2]) != AT[2]  # the fixture has odd seconds to round
    assert events_of(new) == events_of(t)
    assert [c[6] for c in comments_of(new)] == [c[6] for c in comments_of(t)] == [AT[4], AT[5]]


def ev(actor, frm, to, stage, at) -> dict:
    return {"actor": actor, "from_status": frm, "to_status": to, "stage": stage, "created_at": at}


def test_land_done_and_escalated(client, ab, t):  # AC20
    content = body_of(client, t)
    events = task_json(content)["events"]
    done = events + [ev("me", "review", "done", None, "2026-10-18T09:00:00Z"),
                     ev("me", "done", "review", None, "2026-10-18T09:30:00Z"),
                     ev("me", "review", "done", None, "2026-10-18T10:00:00Z")]
    got = ok(client, ab[1], rezip(content, import_key="k-done", status="done", stage=None, events=done))
    row = task_row(got["task_id"])
    assert (got["status"], row["status"], row["stage"], row["done_at"]) == ("done", "done", None, "2026-10-18T10:00:00Z")
    assert len(events_of(got["task_id"])) == len(done)
    got = ok(client, ab[1], rezip(content, import_key="k-esc", stage="escalated"))
    row = task_row(got["task_id"])
    assert (row["status"], row["stage"], row["done_at"]) == ("review", "escalated", None)
    assert len(events_of(got["task_id"])) == len(events)


def test_land_backlog(client, ab, t):  # AC21
    content = body_of(client, t)
    events = task_json(content)["events"]
    before = db.now()
    got = ok(client, ab[1], rezip(content, import_key="k-build", status="in_progress", stage="build"))
    after = db.now()
    row = task_row(got["task_id"])
    assert (got["status"], row["status"], row["stage"]) == ("backlog", "backlog", None)
    found = events_of(got["task_id"])
    assert found[:-1] == [tuple(e.values()) for e in events]
    assert found[-1][:4] == ("app", "in_progress", "backlog", None) and before <= found[-1][4] <= after
    got = ok(client, ab[1], rezip(content, import_key="k-backlog", status="backlog", stage=None))
    assert task_row(got["task_id"])["status"] == "backlog"
    assert events_of(got["task_id"]) == [tuple(e.values()) for e in events]


def test_task_times(client, ab, t, copied):  # AC22
    row = task_row(copied["task_id"])
    assert (row["created_at"], row["updated_at"]) == (EVENTS[0][4], EVENTS[-1][4])


def test_positions(client, ab, t):  # AC23
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
        " VALUES (?, 'mine', 'review', 7, ?, ?)", (ab[1], AT[0], AT[0]))
    content = body_of(client, t)
    got = ok(client, ab[1], content)
    assert task_row(got["task_id"])["position"] == 8
    sql("UPDATE tasks SET position = 0.5 WHERE id = ?", (got["task_id"],))
    ok(client, ab[1], content)
    assert task_row(got["task_id"])["position"] == 0.5
    ok(client, ab[1], rezip(content, status="done", stage=None))
    assert task_row(got["task_id"])["position"] == 1


def test_reimport_same(client, ab, t, copied):  # AC24
    before = counts()
    again = ok(client, ab[1], body_of(client, t))
    assert again == copied | {"created": False}
    assert counts() == before


def test_reimport_replaces_comments(client, ab, t, copied):  # AC25
    new = copied["task_id"]
    r = client.post(f"/api/tasks/{new}/comments", json={"round": 1, "author": "me", "body_md": "mine"}, headers=H)
    assert r.status_code == 201, r.text
    ok(client, ab[1], body_of(client, t))
    assert comments_of(new) == comments_of(t)


def refused(client, project, body, status, detail=None, headers=H) -> str:
    """A refusal: no rows written and FCTL_HOME/transcripts/ unchanged. Its detail."""
    before, files = counts(), stored()
    r = post(client, project, body, headers)
    assert r.status_code == status, r.text
    assert counts() == before and stored() == files
    found = r.json()["detail"]
    if detail is not None:
        assert found == detail
    return found


def test_key_in_other_project(client, ab, t, with_transcripts):  # AC26
    content = body_of(client, t, "?transcripts=1")
    ok(client, ab[1], content)
    refused(client, ab[0], content, 409, f"task:{t}@{AT[0]} is imported in project #{ab[1]}")


def test_running_run(client, ab, t, with_transcripts):  # AC27
    content = body_of(client, t, "?transcripts=1")
    new = ok(client, ab[1], content)["task_id"]
    with closing(db.connect()) as conn, conn:
        run = RunsRepo(conn).add(new, "s", AT[9])
    refused(client, ab[1], content, 409, f"run #{run} active")


@pytest.fixture
def with_copies(client, ab, t, with_transcripts) -> dict:
    """T's ?transcripts=1 export imported into B: the response."""
    return ok(client, ab[1], body_of(client, t, "?transcripts=1"))


def test_transcript_runs(client, with_copies):  # AC28
    assert with_copies["transcripts"] == 2
    [run] = rows("SELECT * FROM runs WHERE task_id = ?", (with_copies["task_id"],))
    assert (run["session_id"], run["status"], run["log_path"]) == (S1, "succeeded", "")
    assert (run["started_at"], run["ended_at"]) == ("2026-10-17T10:04:11Z", "2026-10-17T10:06:00Z")


def test_transcript_rows(client, t, with_transcripts, with_copies):  # AC29
    new = with_copies["task_id"]
    [run] = rows("SELECT id FROM runs WHERE task_id = ?", (new,))
    cols = "agent_type, name, round, model, turns, input_tokens, cache_read_tokens, output_tokens"
    copies = rows(f"SELECT path, {cols} FROM transcripts WHERE task_id = ? ORDER BY id", (new,))
    sources = rows(f"SELECT path, {cols} FROM transcripts WHERE task_id = ? AND run_id = ? ORDER BY id",
                   (t, with_transcripts))
    assert [c["path"] for c in copies] == [f"{run['id']}/{rel}" for rel, *_ in LISTED]
    assert [c | {"path": None} for c in copies] == [s | {"path": None} for s in sources]
    assert [(c["agent_type"], c["name"], c["round"], c["model"]) for c in copies] == [
        ("orchestrator", None, None, "claude-opus-4-1"), ("review-code", "rev", 1, "claude-sonnet-4")]
    store = config.data_dir() / "transcripts"
    for rel, text, *_ in LISTED:
        assert (store / str(run["id"]) / rel).read_bytes() == text.encode()
    listed = client.get(f"/api/tasks/{new}/transcripts").json()
    assert sorted(x["agent_type"] for x in listed) == ["orchestrator", "review-code"]


def test_import_unknown_project(client, ab, t):  # AC30
    r = post(client, 99, body_of(client, t))
    assert (r.status_code, r.json()["detail"]) == (404, "Project #99 not found")


# --- Refusals ----------------------------------------------------------------------------------


def test_needs_header(client, ab, t):  # AC31
    refused(client, ab[1], body_of(client, t), 403, "X-Requested-By: fctl header required", headers={})


def test_body_cap(client, ab, t, monkeypatch):  # AC32
    content = body_of(client, t)
    monkeypatch.setattr(config, "MAX_BUNDLE", len(content) - 1)
    refused(client, ab[1], content, 413, "bundle over 50 MB")
    half = len(content) // 2
    refused(client, ab[1], iter([content[:half], content[half:]]), 413, "bundle over 50 MB")  # chunked, no length
    monkeypatch.setattr(config, "MAX_BUNDLE", len(content))
    assert post(client, ab[1], iter([content[:half], content[half:]])).status_code == 200


def test_not_a_zip(client, ab):  # AC33
    for body in (b"hello", b"", b"PK\x03\x04broken"):
        refused(client, ab[1], body, 422, "not a zip file")


@pytest.mark.parametrize("name", ["../x", "round-1/../../x", "/etc/x"])
def test_unsafe_names(client, ab, t, name):  # AC34
    refused(client, ab[1], rezip(body_of(client, t), {name: "x"}), 422, f'bundle entry "{name}" is unsafe')


def test_symlink(client, ab, t):  # AC35
    link = zipfile.ZipInfo("spec.md", (2026, 10, 17, 10, 0, 0))
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    body = rezip(body_of(client, t), drop={"spec.md"}, extra=[(link, b"/etc/passwd")])
    refused(client, ab[1], body, 422, 'bundle entry "spec.md" is a symlink')


@pytest.mark.parametrize("name", ["notes.txt", "round-1/review-other.md", "round-01/build.md", "__MACOSX/x",
                                  "transcripts/1/x.jsonl", "spec.md/", "task-12/task.json"])
def test_unknown_names(client, ab, t, name):  # AC36
    detail = refused(client, ab[1], rezip(body_of(client, t), {name: "x"}), 422)
    assert detail.startswith(f'unknown bundle entry "{name}"')


def test_unpacked_cap(client, ab, t, monkeypatch):  # AC37
    content = body_of(client, t)
    total = sum(i.file_size for i in bundle(content).infolist())
    monkeypatch.setattr(config, "MAX_UNPACKED", total - 1)
    refused(client, ab[1], content, 413, "bundle unpacks to over 500 MB")
    monkeypatch.setattr(config, "MAX_UNPACKED", total)
    assert post(client, ab[1], content).status_code == 200


def one_entry(data: bytes) -> bytearray:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("spec.md", data)
    return bytearray(out.getvalue())


def test_unreadable_entries(client, ab):  # AC38
    bad_crc = one_entry(b"hello world")
    at = bad_crc.index(b"hello world")
    bad_crc[at:at + 5] = b"HELLO"
    assert refused(client, ab[1], bytes(bad_crc), 422).startswith('bundle entry "spec.md" can\'t be read')
    encrypted = one_entry(b"hello world")
    encrypted[encrypted.index(b"PK\x03\x04") + 6] |= 1  # the local header's and the central directory's flags
    encrypted[encrypted.index(b"PK\x01\x02") + 8] |= 1
    assert refused(client, ab[1], bytes(encrypted), 422).startswith('bundle entry "spec.md" can\'t be read')


def comment(**extra) -> dict:
    return {"round": 1, "author": "me", "path": None, "line": None, "side": None, "body_md": "x",
            "created_at": AT[0]} | extra


def bad_cases(run: int) -> list[tuple[dict, dict, str]]:
    """(rezip's add, rezip's task.json fields, a field the detail names)."""
    good = {"path": f"{run}/{LISTED[0][0]}", "session_id": S1, "agent_type": None, "name": None, "round": None}
    return [
        ({"task.json": "{not json"}, {}, "task.json"),
        ({"task.json": "[]"}, {}, "task.json"),
        ({}, {"title": "  "}, "title"),
        ({}, {"title": None}, "title"),
        ({}, {"status": "blocked"}, "status"),
        ({}, {"stage": "deploy"}, "stage"),
        ({}, {"status": "review", "stage": "build"}, "stage"),
        ({}, {"status": "done", "stage": "human_review"}, "stage"),
        ({}, {"import_key": "../x"}, "import_key"),
        ({}, {"import_key": "k" * 201}, "import_key"),
        ({}, {"events": [ev("me", None, "blocked", None, AT[0])]}, "events[0].to_status"),
        ({}, {"events": [ev("me", None, "backlog", None, "2026-10-17 10:00:00")]}, "events[0].created_at"),
        ({}, {"events": [ev("me", None, "backlog", None, "2026-10-17T10:00:00.123Z")]}, "events[0].created_at"),
        ({}, {"comments": [comment(round=3)]}, "comments[0].round"),
        ({}, {"comments": [comment(path="b.py")]}, "comments[0]"),
        ({}, {"comments": [comment(path="b.py", line=1)]}, "comments[0]"),
        ({}, {"transcripts": [good | {"path": "../x.jsonl"}]}, "transcripts[0].path"),
        ({}, {"transcripts": [good | {"path": f"{run}/x.txt"}]}, "transcripts[0].path"),
        ({}, {"transcripts": [good, good | {"path": f"{run}/missing.jsonl"}]}, "transcripts[1].path"),
        ({}, {"transcripts": [good | {"session_id": "../s"}]}, "transcripts[0].session_id"),
    ]


def test_bad_task_json(client, ab, t, with_transcripts):  # AC39
    content = body_of(client, t, "?transcripts=1")
    refused(client, ab[1], rezip(content, drop={"task.json"}), 422, "bundle has no task.json")
    for add, fields, field in bad_cases(with_transcripts):
        detail = refused(client, ab[1], rezip(content, add, **fields), 422)
        assert field in detail, (field, detail)
    assert ok(client, ab[1], content)["transcripts"] == 2  # the base bundle is fine


def test_bad_patch(client, ab, t):  # AC40
    content = body_of(client, t)
    big = "diff --git a/x b/x\n" + "+" * config.MAX_PATCH
    refused(client, ab[1], rezip(content, {"round-1/diff.patch": big}), 413, "round-1/diff.patch over 5 MB")
    detail = refused(client, ab[1], rezip(content, {"round-1/diff.patch": "hello\n"}), 422)
    assert detail.startswith("round 1: ")


# --- Docs --------------------------------------------------------------------------------------


def between(text: str, start: str, end: str) -> str:
    at = text.index(start)
    return text[at:text.index(end, at)]


def test_docs():  # AC50
    data = (ROOT / "docs" / "data-model-and-api.md").read_text()
    api = between(data, "### 6.1", "### 6.2")
    assert "POST /api/projects/3/import " in api and "50 MB" in api and "500 MB" in api
    tasks = between(data, "### 6.2", "### 6.3")
    assert "GET  /api/tasks/12/export[?transcripts=1]" in tasks and "secrets" in tasks
    cc_doc = between((ROOT / "docs" / "claude-code.md").read_text(), "### 7.2", "### 7.3")
    assert "| `fctl export <id> [-o FILE] [--transcripts]` |" in cc_doc
    assert "| `fctl import FILE` |" in cc_doc
    ui = (ROOT / "docs" / "ui.md").read_text()
    # 042: Import moved from the board (item 3) to the project's Settings page (item 12)
    settings = between(ui, "\n12. **Project settings**", "\n### 8.1")
    task = between(ui, "\n4. **Task detail**", "\n5. ")
    assert "**Import**" in settings and "**Export**" in task and "**Include transcripts**" in task
    mvp = (ROOT / "docs" / "MVP.md").read_text()
    safety = between(mvp, "### 4.5", "### 4.6")
    assert "task bundle" in safety and "`MAX_BUNDLE`" in safety and "`MAX_UNPACKED`" in safety
    [config_line] = [x for x in mvp.splitlines() if x.startswith("├── config.py")]
    assert "MAX_BUNDLE" in config_line and "MAX_UNPACKED" in config_line
