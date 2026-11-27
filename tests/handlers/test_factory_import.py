"""031: POST /api/projects/{id}/import-factory, the docs, the skill, and .gitignore."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from conftest import commit, git, sql, write

from workcell import config, db
from workcell.lib.patch import split_patch
from workcell.lib.transcript import folder_name

from .test_transcripts import assistant, jsonl, line, spawn, user

H = {"X-Requested-By": "fctl"}
ROOT = Path(__file__).resolve().parents[2]
T = ["2026-10-17T10:00:00Z", "2026-10-17T11:00:00Z", "2026-10-17T12:00:00Z", "2026-10-17T13:00:00Z"]
PATCH = (
    "diff --git a/a.py b/a.py\nnew file mode 100644\nindex 0000000..1111111\n--- /dev/null\n+++ b/a.py\n"
    "@@ -0,0 +1 @@\n+x = 1\n"
    "diff --git a/b.py b/b.py\nindex 1111111..2222222 100644\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-y = 1\n+y = 2\n"
)
TABLES = ("tasks", "events", "rounds", "round_files", "verdicts", "decisions", "runs", "transcripts")
S = "aaaaaaaa-1111-2222-3333-444455556666"  # the /factory session
EMPTY = dict.fromkeys(TABLES, 0)


def entry(jid, **extra) -> dict:
    """A board.json job in review · human_review, as SKILL.md's Board section writes it."""
    return {"id": jid, "title": f"Job {jid}", "description": f"Build {jid}", "status": "review",
            "stage": "human_review", "round": 1, "branch": f"factory/feat/{jid}",
            "worktree": f".claude/worktrees/{jid}", "pr": None, "reviews": {"security": "PASS"},
            "history": [{"at": T[0], "status": "in_progress", "stage": "spec"},
                        {"at": T[1], "status": "review", "stage": "human_review"}]} | extra


def board(repo, *jobs):
    write(repo, {"factory/board.json": json.dumps({"jobs": list(jobs)})})


def put(repo, files: dict):
    """{path under factory/jobs/: content}."""
    write(repo, {f"factory/jobs/{k}": v for k, v in files.items()})


def post(client, project, body=None):
    return client.post(f"/api/projects/{project}/import-factory", json={} if body is None else body, headers=H)


def ok(client, project, body=None) -> list[dict]:
    r = post(client, project, body)
    assert r.status_code == 200, r.text
    return r.json()["imported"]


def rows(query, args=()) -> list[dict]:
    with closing(db.connect()) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(query, args)]


def task(jid) -> dict:
    [found] = rows("SELECT * FROM tasks WHERE import_key = ?", (f"factory:{jid}",))
    return found


def counts() -> dict:
    return {t: sql(f"SELECT COUNT(*) FROM {t}")[0][0] for t in TABLES}


def connect(client, path) -> int:
    r = client.post("/api/projects/connect", headers=H,
                    json={"path": str(path), "workspace": "w", "name": Path(path).name, "default_branch": "main"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture
def project(client, repo) -> int:
    return connect(client, repo)


@pytest.fixture
def two(repo):
    """001-a in review with a spec and round 1; 002-b in progress with no folder."""
    board(repo, entry("001-a"), entry("002-b", status="in_progress", stage="build",
                                      history=[{"at": T[0], "status": "in_progress", "stage": "spec"}]))
    put(repo, {"001-a/spec.md": "# Spec\n", "001-a/round-1/build.md": "built\n", "001-a/round-1/diff.patch": PATCH})


def rounds_of(jid) -> list[dict]:
    return rows("SELECT * FROM rounds WHERE task_id = ? ORDER BY n", (task(jid)["id"],))


# --- First import ------------------------------------------------------------------


def test_first_import(client, project, two):  # AC3
    imported = ok(client, project)
    a, b = task("001-a"), task("002-b")
    assert imported == [
        {"job": "001-a", "task_id": a["id"], "created": True, "rounds": 1, "transcripts": 0},
        {"job": "002-b", "task_id": b["id"], "created": True, "rounds": 0, "transcripts": 0},
    ]
    assert len(rounds_of("001-a")) == 1 and rounds_of("002-b") == []
    assert (a["project_id"], b["project_id"]) == (project, project)
    assert counts()["transcripts"] == 0


def test_task_fields(client, project, two):  # AC4
    ok(client, project)
    a, b = task("001-a"), task("002-b")
    assert (a["title"], a["status"], a["stage"], a["branch"], a["worktree_path"]) == (
        "Job 001-a", "review", "human_review", "factory/feat/001-a", None)
    assert (b["status"], b["stage"]) == ("in_progress", "build")


def test_description_and_pr(client, repo, project):  # AC5
    url = "https://github.com/me/r/pull/5"
    no_pr = entry("003-c")
    del no_pr["pr"]
    board(repo, entry("001-a", pr=url), entry("002-b"), no_pr)
    ok(client, project)
    assert task("001-a")["description_md"] == f"Build 001-a\n\nPR: {url}"
    assert task("002-b")["description_md"] == "Build 002-b"
    assert task("003-c")["description_md"] == "Build 003-c"


def test_pr_url(client, repo, project):  # 093 AC2
    url = "https://github.com/me/r/pull/5"
    no_pr = entry("003-c")
    del no_pr["pr"]
    board(repo, entry("001-a", pr=url), entry("002-b"), no_pr, entry("004-d", pr="https://github.com/me/r/issues/5"))
    ok(client, project)
    assert task("001-a")["pr_url"] == url
    assert task("001-a")["description_md"] == f"Build 001-a\n\nPR: {url}"
    assert [task(j)["pr_url"] for j in ("002-b", "003-c", "004-d")] == [None, None, None]


def test_dates(client, repo, project):  # AC6
    reopened = [{"at": T[0], "status": "in_progress", "stage": "spec"}, {"at": T[1], "status": "done", "stage": None},
                {"at": T[2], "status": "review", "stage": "escalated"}, {"at": T[3], "status": "done", "stage": None}]
    board(repo, entry("001-a", status="done", stage=None, history=reopened),
          entry("002-b", history=reopened[:3], status="review", stage="escalated"))
    ok(client, project)
    a, b = task("001-a"), task("002-b")
    assert (a["done_at"], a["created_at"], a["updated_at"]) == (T[3], T[0], T[3])
    assert (b["done_at"], b["created_at"], b["updated_at"]) == (None, T[0], T[2])


def test_events(client, repo, project):  # AC7
    history = [{"at": T[0], "status": "in_progress", "stage": "spec"},
               {"at": T[1], "status": "in_progress", "stage": "build"},
               {"at": T[2], "status": "review", "stage": "human_review"},
               {"at": T[3], "status": "done", "stage": None}]
    board(repo, entry("001-a", status="done", stage=None, history=history))
    ok(client, project)
    assert [(e["actor"], e["from_status"], e["to_status"], e["stage"], e["created_at"]) for e in rows(
        "SELECT * FROM events WHERE task_id = ? ORDER BY id", (task("001-a")["id"],))] == [
        ("orchestrator", None, "in_progress", "spec", T[0]),
        ("orchestrator", "in_progress", "in_progress", "build", T[1]),
        ("orchestrator", "in_progress", "review", "human_review", T[2]),
        ("orchestrator", "review", "done", None, T[3]),
    ]


def test_positions(client, repo, project):  # AC8
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
        " VALUES (?, 'mine', 'review', 7, ?, ?)", (project, T[0], T[0]))
    board(repo, entry("001-a"), entry("002-b", status="in_progress", stage="build"), entry("003-c"))
    ok(client, project)
    assert [task(j)["position"] for j in ("001-a", "003-c", "002-b")] == [8, 9, 1]


def test_spec(client, project, repo):  # AC9
    spec = "# Spec — ü\r\n\n- [ ] AC1\n  trailing  \n"
    board(repo, entry("001-a"), entry("002-b"))
    put(repo, {"001-a/spec.md": spec.encode(), "002-b/round-1/build.md": "x"})
    ok(client, project)
    assert task("001-a")["spec_md"] == spec
    assert task("002-b")["spec_md"] is None


def test_rounds_and_triggers(client, repo, project):  # AC10
    board(repo, entry("001-a"), entry("002-b"))
    put(repo, {"001-a/round-1/build.md": "one", "001-a/round-2/diff.patch": "",
               "002-b/round-1/build.md": "one", "002-b/round-2/build.md": "two", "002-b/feedback-2.md": "redo"})
    ok(client, project)
    assert [(r["n"], r["build_md"], r["trigger"]) for r in rounds_of("001-a")] == [
        (1, "one", "initial"), (2, None, "agent")]
    assert [(r["n"], r["trigger"]) for r in rounds_of("002-b")] == [(1, "initial"), (2, "human")]


def test_round_files(client, repo, project):  # AC11
    board(repo, entry("001-a"), entry("002-b"))
    put(repo, {"001-a/round-1/diff.patch": PATCH, "001-a/round-2/diff.patch": "", "002-b/round-1/build.md": "x"})
    ok(client, project)
    r1, r2 = rounds_of("001-a")
    files = rows("SELECT path, old_path, change, binary, additions, deletions, patch FROM round_files"
                 " WHERE round_id = ? ORDER BY rowid", (r1["id"],))
    assert files == split_patch(PATCH)
    r = client.get(f"/api/tasks/{task('001-a')['id']}/rounds/1/diff")
    assert r.status_code == 200 and r.text == PATCH
    assert sql("SELECT COUNT(*) FROM round_files WHERE round_id = ?", (r2["id"],)) == [(0,)]
    [b1] = rounds_of("002-b")
    assert sql("SELECT COUNT(*) FROM round_files WHERE round_id = ?", (b1["id"],)) == [(0,)]


def merge(repo, n, branch) -> str:
    """A gh-style merge of a new branch into main; main's commit before it."""
    parent = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-q", "-c", branch)
    commit(repo, {f"{branch.replace('/', '-')}.txt": branch})
    git(repo, "switch", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", f"Merge pull request #{n} from me/{branch}\n\nTitle", branch)
    return parent


def test_base_sha_from_merge(client, repo, project):  # AC12
    parent = merge(repo, 5, "factory/feat/001-a")
    merge(repo, 50, "factory/feat/050-x")  # "#50 from" isn't "#5 from"
    board(repo, entry("001-a", pr="https://github.com/me/r/pull/5"))
    put(repo, {"001-a/round-1/build.md": "x", "001-a/round-2/build.md": "y"})
    ok(client, project)
    assert [r["base_sha"] for r in rounds_of("001-a")] == [parent, parent]


def test_base_sha_unknown(client, repo, project):  # AC13
    merge(repo, 5, "factory/feat/001-a")
    board(repo, entry("001-a"), entry("002-b", pr="https://github.com/me/r/issues/5"),
          entry("003-c", pr="https://github.com/me/r/pull/6"))
    put(repo, {f"{j}/round-1/build.md": "x" for j in ("001-a", "002-b", "003-c")})
    ok(client, project)
    assert [rounds_of(j)[0]["base_sha"] for j in ("001-a", "002-b", "003-c")] == ["unknown"] * 3


def verdicts(jid, n=1) -> list[tuple]:
    return [(v["reviewer"], v["verdict"], v["body_md"]) for v in rows(
        "SELECT v.* FROM verdicts v JOIN rounds r ON r.id = v.round_id WHERE r.task_id = ? AND r.n = ?"
        " ORDER BY reviewer", (task(jid)["id"], n))]


def test_verdict_pass(client, repo, project):  # AC14
    board(repo, entry("001-a"))
    put(repo, {"001-a/round-1/review-security.md": "VERDICT: PASS\n\nNo findings.\n"})
    ok(client, project)
    assert verdicts("001-a") == [("security", "PASS", "No findings.")]


def test_verdict_changes(client, repo, project):  # AC15
    board(repo, entry("001-a"))
    put(repo, {"001-a/round-1/review-code.md": "VERDICT: CHANGES\nfix a.py:1\n",
               "001-a/round-1/review-ux.md": "PASS\nlooks fine",
               "001-a/round-1/review-other.md": "VERDICT: PASS\n"})
    ok(client, project)
    assert verdicts("001-a") == [("code", "CHANGES", "fix a.py:1"), ("ux", "CHANGES", "looks fine")]


def decisions(jid) -> list[tuple]:
    return [(d["n"], d["actor"], d["decision"], d["body_md"]) for d in rows(
        "SELECT r.n, d.* FROM decisions d JOIN rounds r ON r.id = d.round_id WHERE d.task_id = ? ORDER BY d.id",
        (task(jid)["id"],))]


def test_decision(client, repo, project):  # AC16
    board(repo, entry("001-a"), entry("002-b"), entry("003-c"), entry("004-d"))
    put(repo, {"001-a/round-1/build.md": "x", "001-a/round-2/build.md": "y", "001-a/decision.md": "APPROVE\nAll good.",
               "002-b/round-1/build.md": "x", "002-b/decision.md": "ESCALATE\nTests fail.\n",
               "003-c/round-1/build.md": "x", "003-c/decision.md": "approve\nlower case",
               "004-d/decision.md": "APPROVE\nno rounds"})
    ok(client, project)
    assert decisions("001-a") == [(2, "approver", "APPROVE", "All good.")]
    assert decisions("002-b") == [(1, "approver", "ESCALATE", "Tests fail.")]
    assert decisions("003-c") == [(1, "approver", "ESCALATE", "lower case")]
    assert decisions("004-d") == []


def test_feedback(client, repo, project):  # AC17
    note = "Make the limit configurable.\n\nAnd log it.\n"
    board(repo, entry("001-a"))
    put(repo, {"001-a/round-1/build.md": "x", "001-a/round-2/build.md": "y", "001-a/feedback-2.md": note,
               "001-a/feedback-5.md": "no round 4"})
    ok(client, project)
    assert decisions("001-a") == [(1, "me", "CHANGES_REQUESTED", note)]


def test_file_times(client, repo, project):  # AC18
    board(repo, entry("001-a"))
    put(repo, {"001-a/round-1/build.md": "x", "001-a/round-1/review-ux.md": "VERDICT: PASS\n",
               "001-a/round-2/review-ux.md": "VERDICT: PASS\n", "001-a/decision.md": "APPROVE\n",
               "001-a/feedback-2.md": "redo"})
    jobs = repo / "factory" / "jobs" / "001-a"
    stamps = {"round-1/build.md": 1_700_000_000, "round-1/review-ux.md": 1_700_000_100, "round-2": 1_700_000_200,
              "decision.md": 1_700_000_300, "feedback-2.md": 1_700_000_400, "round-2/review-ux.md": 1_700_000_500}
    for rel, at in stamps.items():
        os.utime(jobs / rel, (at, at))
    ok(client, project)
    utc = {at: f"2023-11-14T{h}Z" for at, h in [
        (1_700_000_000, "22:13:20"), (1_700_000_100, "22:15:00"), (1_700_000_200, "22:16:40"),
        (1_700_000_300, "22:18:20"), (1_700_000_400, "22:20:00"), (1_700_000_500, "22:21:40")]}
    assert [r["created_at"] for r in rounds_of("001-a")] == [utc[1_700_000_000], utc[1_700_000_200]]
    assert [v["created_at"] for v in rows("SELECT v.created_at FROM verdicts v JOIN rounds r ON r.id = v.round_id"
                                          " ORDER BY r.n")] == [utc[1_700_000_100], utc[1_700_000_500]]
    assert [(d["actor"], d["created_at"]) for d in rows("SELECT * FROM decisions ORDER BY id")] == [
        ("me", utc[1_700_000_400]), ("approver", utc[1_700_000_300])]


# --- Rerun -------------------------------------------------------------------------


def test_rerun_same(client, project, two):  # AC19
    first = ok(client, project)
    before = counts()
    again = ok(client, project)
    assert again == [j | {"created": False} for j in first]
    assert counts() == before


def test_rerun_follows_files(client, repo, project, two):  # AC20
    ok(client, project)
    [r1] = rounds_of("001-a")
    done = entry("001-a", title="Renamed", status="done", stage=None)
    done["history"].append({"at": T[3], "status": "done", "stage": None})
    board(repo, done, entry("002-b", status="in_progress", stage="build"))
    put(repo, {"001-a/round-2/diff.patch": PATCH, "001-a/round-2/review-code.md": "VERDICT: PASS\nok"})
    [a, _] = ok(client, project)
    assert (a["created"], a["rounds"]) == (False, 2)
    t = task("001-a")
    assert (t["title"], t["status"], t["stage"], t["done_at"], t["updated_at"]) == ("Renamed", "done", None, T[3], T[3])
    assert [e["to_status"] for e in rows("SELECT * FROM events WHERE task_id = ? ORDER BY id", (t["id"],))] == [
        "in_progress", "review", "done"]
    one, two_ = rounds_of("001-a")
    assert one["id"] == r1["id"] and two_["n"] == 2
    assert sql("SELECT COUNT(*) FROM round_files WHERE round_id = ?", (two_["id"],)) == [(2,)]
    assert verdicts("001-a", 2) == [("code", "PASS", "ok")]


def test_rerun_keeps_comments(client, project, two):  # AC21
    ok(client, project)
    t = task("001-a")
    r = client.post(f"/api/tasks/{t['id']}/comments", json={"round": 1, "author": "me", "body_md": "nice"}, headers=H)
    assert r.status_code == 201, r.text
    [r1] = rounds_of("001-a")
    ok(client, project)
    assert sql("SELECT round_id, body_md FROM comments") == [(r1["id"], "nice")]


def test_rerun_positions(client, repo, project, two):  # AC22
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
        " VALUES (?, 'mine', 'done', 5, ?, ?)", (project, T[0], T[0]))
    ok(client, project)
    b = task("002-b")["position"]
    sql("UPDATE tasks SET position = 0.5 WHERE import_key = 'factory:002-b'")
    board(repo, entry("001-a", status="done", stage=None), entry("002-b", status="in_progress", stage="build"))
    ok(client, project)
    assert task("001-a")["position"] == 6
    assert task("002-b")["position"] == 0.5 != b


# --- One job -----------------------------------------------------------------------


def test_one_job(client, project, two):  # AC23
    [only] = ok(client, project, {"job": "002-b"})
    assert only["job"] == "002-b" and only["created"]
    assert sql("SELECT import_key FROM tasks") == [("factory:002-b",)]


def test_unknown_job(client, project, two):  # AC24
    r = post(client, project, {"job": "nope"})
    assert (r.status_code, r.json()["detail"]) == (404, "no job nope in factory/board.json")
    assert counts() == EMPTY


def test_bad_job_id(client, project, two):  # AC25
    r = post(client, project, {"job": "../x"})
    assert r.status_code == 422 and "../x" in r.json()["detail"]
    assert counts() == EMPTY


# --- Errors and containment ----------------------------------------------------------


def test_unknown_project(client, two):  # AC26
    r = post(client, 99)
    assert (r.status_code, r.json()["detail"]) == (404, "Project #99 not found")


def test_no_board(client, repo, project):  # AC27, 058 Q9
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == (404, f"no factory/board.json or factory/backlog.md in {repo}")
    r = post(client, project, {"job": "001-a"})
    assert (r.status_code, r.json()["detail"]) == (404, f"no factory/board.json in {repo}")


@pytest.mark.parametrize("text, detail", [
    ("{not json", "factory/board.json isn't valid JSON"),
    ('{"tasks": []}', 'factory/board.json has no "jobs" list'),
    ('[]', 'factory/board.json has no "jobs" list'),
    (json.dumps({"jobs": [entry("001-a"), entry("002-b", status="blocked")]}), 'job 002-b has unknown status "blocked"'),
    (json.dumps({"jobs": [entry("001-a"), entry("002-b", stage="deploy")]}), 'job 002-b has unknown stage "deploy"'),
    (json.dumps({"jobs": [entry("001-a"), entry("002-b", history=[{"at": T[0], "status": "x", "stage": None}])]}),
     'job 002-b has unknown status "x"'),
    (json.dumps({"jobs": [entry("001-a"), entry("../b")]}), 'factory/board.json: bad job id "../b"'),
    (json.dumps({"jobs": [entry("001-a"), entry("002-b", title="  ")]}), "job 002-b has no title"),
    (json.dumps({"jobs": [entry("001-a"), {k: v for k, v in entry("002-b").items() if k != "title"}]}),
     "job 002-b has no title"),
])
def test_bad_board(client, repo, project, text, detail):  # AC28
    write(repo, {"factory/board.json": text})
    put(repo, {"001-a/round-1/build.md": "x"})
    r = post(client, project)
    assert r.status_code == 422 and r.json()["detail"].startswith(detail), r.text
    assert counts() == EMPTY


def test_bad_entry_elsewhere_doesnt_block_one_job(client, repo, project):  # AC28, Q7
    board(repo, entry("001-a"), entry("002-b", status="blocked"))
    assert [j["job"] for j in ok(client, project, {"job": "001-a"})] == ["001-a"]


def test_symlinks(client, tmp_path, repo, project):  # AC29, 058 Q9
    outside = tmp_path / "outside"
    write(outside, {"factory/board.json": json.dumps({"jobs": [entry("001-a")]}), "spec.md": "secret",
                    "diff.patch": PATCH})
    (repo / "factory").symlink_to(outside / "factory")
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == (404, f"no factory/board.json or factory/backlog.md in {repo}")
    (repo / "factory").unlink()
    (repo / "factory").mkdir()
    (repo / "factory" / "board.json").symlink_to(outside / "factory" / "board.json")
    assert post(client, project).json()["detail"] == f"no factory/board.json or factory/backlog.md in {repo}"
    (repo / "factory" / "board.json").unlink()
    board(repo, entry("001-a"))
    put(repo, {"001-a/round-1/build.md": "x"})
    (repo / "factory/jobs/001-a/spec.md").symlink_to(outside / "spec.md")
    (repo / "factory/jobs/001-a/round-1/diff.patch").symlink_to(outside / "diff.patch")
    ok(client, project)
    assert task("001-a")["spec_md"] is None
    [r1] = rounds_of("001-a")
    assert sql("SELECT COUNT(*) FROM round_files WHERE round_id = ?", (r1["id"],)) == [(0,)]


def test_patch_too_big(client, repo, project, two):  # AC30
    put(repo, {"001-a/round-1/diff.patch": PATCH + "+" * config.MAX_PATCH})
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == (413, "001-a/round-1/diff.patch over 5 MB")
    assert counts() == EMPTY


def test_patch_not_a_diff(client, repo, project, two):  # AC30
    put(repo, {"001-a/round-1/diff.patch": "hello\n"})
    r = post(client, project)
    assert r.status_code == 422
    assert r.json()["detail"].startswith("job 001-a round 1: ")
    assert counts() == EMPTY


def test_key_in_other_project(client, tmp_path, repo, project, two):  # AC31
    other = tmp_path / "other"
    write(other, {"factory/board.json": json.dumps({"jobs": [entry("001-a")]})})
    other_id = connect(client, other)
    ok(client, other_id)
    before = counts()
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == (409, f"factory:001-a is imported in project #{other_id}")
    assert counts() == before


# --- 058: factory/backlog.md -----------------------------------------------------------

LOG = "# Backlog\n\n## Repo backlog\n\n- [ ] 101-alpha: first\n- [x] 102-beta: second\n- [ ] 103-gamma: third\n"
LOG_IDS = ["101-alpha", "102-beta", "103-gamma"]


def backlog(repo, text=LOG):
    write(repo, {"factory/backlog.md": text})


def events(jid) -> list[tuple]:
    return [(e["actor"], e["from_status"], e["to_status"], e["stage"], e["created_at"]) for e in rows(
        "SELECT * FROM events WHERE task_id = ? ORDER BY id", (task(jid)["id"],))]


def snapshot() -> tuple:
    return rows("SELECT * FROM tasks ORDER BY id"), rows("SELECT * FROM events ORDER BY id")


def aged():
    """Every task and event dated T[0], so a rewrite at the sync time shows."""
    sql("UPDATE tasks SET created_at = ?, updated_at = ?", (T[0], T[0]))
    sql("UPDATE events SET created_at = ?", (T[0],))


def test_backlog_only(client, repo, project):  # BE6
    backlog(repo)
    r = post(client, project)
    assert r.status_code == 200, r.text
    assert r.json() == {"skipped": 0, "imported": [
        {"job": jid, "task_id": task(jid)["id"], "created": True, "rounds": 0, "transcripts": 0} for jid in LOG_IDS]}
    a, b = task("101-alpha"), task("102-beta")
    assert (a["import_key"], a["title"], a["description_md"], a["status"]) == (
        "factory:101-alpha", "Alpha", "## Repo backlog\n\nfirst", "backlog")
    assert (b["title"], b["description_md"], b["status"]) == ("Beta", "## Repo backlog\n\nsecond", "done")
    for t in (a, b, task("103-gamma")):
        assert (t["project_id"], t["stage"], t["branch"], t["spec_md"], t["worktree_path"], t["done_at"]) == (
            project, None, None, None, None, None)
        assert t["created_at"] == t["updated_at"]


def test_backlog_positions(client, repo, project):  # BE7
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
        " VALUES (?, 'mine', 'backlog', 5, ?, ?), (?, 'shipped', 'done', 3, ?, ?)",
        (project, T[0], T[0], project, T[0], T[0]))
    backlog(repo)
    ok(client, project)
    assert [task(j)["position"] for j in LOG_IDS] == [6, 4, 7]


def test_backlog_events(client, repo, project):  # BE8
    backlog(repo)
    ok(client, project)
    for jid, status in zip(LOG_IDS, ("backlog", "done", "backlog")):
        assert events(jid) == [("app", None, status, None, task(jid)["created_at"])]


def test_board_and_backlog(client, repo, project):  # BE9
    board(repo, entry("101-alpha"))
    backlog(repo, "- [ ] 102-beta: b\n- [x] 101-alpha: a\n")
    assert [j["job"] for j in ok(client, project)] == ["101-alpha", "102-beta"]
    a = task("101-alpha")
    assert (a["title"], a["status"], a["stage"], a["description_md"]) == (
        "Job 101-alpha", "review", "human_review", "Build 101-alpha")
    assert [e[0] for e in events("101-alpha")] == ["orchestrator", "orchestrator"]
    assert counts()["tasks"] == 2


def test_backlog_rerun_same(client, repo, project):  # BE10
    backlog(repo)
    first = ok(client, project)
    aged()
    before = snapshot()
    assert ok(client, project) == [j | {"created": False} for j in first]
    assert snapshot() == before


def test_backlog_rerun_ticked(client, repo, project):  # BE11, Q5
    sql("INSERT INTO tasks (project_id, title, status, position, created_at, updated_at)"
        " VALUES (?, 'shipped', 'done', 9, ?, ?)", (project, T[0], T[0]))
    backlog(repo)
    ok(client, project)
    aged()
    backlog(repo, LOG.replace("- [ ] 101-alpha: first", "- [x] 101-alpha: first, done"))
    [a] = [j for j in ok(client, project) if j["job"] == "101-alpha"]
    assert a["created"] is False
    t = task("101-alpha")
    assert (t["title"], t["description_md"], t["status"], t["position"], t["done_at"]) == (
        "Alpha", "## Repo backlog\n\nfirst, done", "done", 11, None)
    *_, last = events("101-alpha")
    assert events("101-alpha") == [("app", None, "backlog", None, T[0]), ("app", "backlog", "done", None, last[4])]
    assert t["updated_at"] == last[4] != T[0]
    assert task("103-gamma")["updated_at"] == T[0]  # unchanged lines aren't touched


def test_backlog_rerun_keeps_title(client, repo, project):  # 108 AC21, Q6: the shared upsert gets no title
    backlog(repo)
    ok(client, project)
    sql("UPDATE tasks SET title = 'Renamed by me' WHERE import_key = 'factory:101-alpha'")
    backlog(repo, LOG.replace("- [ ] 101-alpha: first", "- [ ] 101-alpha: changed"))
    ok(client, project)
    t = task("101-alpha")
    assert (t["title"], t["description_md"]) == ("Renamed by me", "## Repo backlog\n\nchanged")


def start_run(client, tid):
    sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at) VALUES (?, 's', 'failed', 'l', ?)",
        (tid, T[0]))


def start_round(client, tid):
    sql("INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, 1, 'initial', 'x', ?)", (tid, T[0]))


def start_move(client, tid):
    r = client.patch(f"/api/tasks/{tid}", json={"status": "in_progress", "position": 1}, headers=H)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("start", [start_run, start_round, start_move])
def test_backlog_started_left_alone(client, repo, project, start):  # BE12, Q6
    backlog(repo)
    ok(client, project)
    start(client, task("101-alpha")["id"])
    before = task("101-alpha")
    backlog(repo, LOG.replace("- [ ] 101-alpha: first", "- [x] 101-alpha: rewritten"))
    [a] = [j for j in ok(client, project) if j["job"] == "101-alpha"]
    assert a["created"] is False
    assert task("101-alpha") == before


def test_backlog_line_removed(client, repo, project):  # BE13
    backlog(repo)
    ok(client, project)
    kept = task("101-alpha")
    backlog(repo, LOG.replace("- [ ] 101-alpha: first\n", ""))
    assert [j["job"] for j in ok(client, project)] == ["102-beta", "103-gamma"]
    assert task("101-alpha") == kept


def test_backlog_skipped(client, repo, project):  # BE14, Q8
    backlog(repo, LOG + "- [ ] ../x: t\n- [ ] just text\n- [~] 104-d: t\n- [ ] 101-alpha: again\n- plain\n")
    r = post(client, project)
    assert r.json()["skipped"] == 4
    board(repo, entry("001-a"))
    r = post(client, project, {"job": "101-alpha"})
    assert (r.status_code, r.json()["detail"]) == (404, "no job 101-alpha in factory/board.json")
    assert post(client, project, {"job": "001-a"}).json()["skipped"] == 0


def test_neither_or_board_alone(client, repo, project):  # BE15, Q9
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == (404, f"no factory/board.json or factory/backlog.md in {repo}")
    board(repo, entry("001-a"))
    r = post(client, project)
    assert r.status_code == 200, r.text
    assert r.json() == {"skipped": 0, "imported": [
        {"job": "001-a", "task_id": task("001-a")["id"], "created": True, "rounds": 0, "transcripts": 0}]}


def test_backlog_containment(client, tmp_path, repo, project):  # BE16
    outside = tmp_path / "outside"
    write(outside, {"factory/backlog.md": LOG})
    (repo / "factory").mkdir()
    (repo / "factory" / "backlog.md").symlink_to(outside / "factory" / "backlog.md")
    missing = (404, f"no factory/board.json or factory/backlog.md in {repo}")
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == missing
    (repo / "factory" / "backlog.md").unlink()
    (repo / "factory").rmdir()
    (repo / "factory").symlink_to(outside / "factory")
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == missing
    (repo / "factory").unlink()
    backlog(repo, LOG + "x" * config.MAX_PATCH)
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == (413, "backlog.md over 5 MB")
    assert counts() == EMPTY


def test_backlog_key_in_other_project(client, tmp_path, repo, project):  # BE17, Q12
    other = tmp_path / "other"
    write(other, {"factory/backlog.md": "- [ ] 103-gamma: theirs\n"})
    other_id = connect(client, other)
    ok(client, other_id)
    before = snapshot()
    backlog(repo)
    r = post(client, project)
    assert (r.status_code, r.json()["detail"]) == (409, f"factory:103-gamma is imported in project #{other_id}")
    assert snapshot() == before


def test_sync_writes_nothing_to_repo(client, repo, project):  # BE18
    board(repo, entry("001-a"))
    backlog(repo)
    put(repo, {"001-a/round-1/build.md": "x"})
    commit(repo, {"factory/backlog.md": LOG})
    factory = repo / "factory"

    def state():
        return git(repo, "status", "--porcelain", "--ignored"), {
            p.relative_to(factory).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(factory.rglob("*")) if p.is_file()}

    before = state()
    ok(client, project)
    ok(client, project)
    assert state() == before


def test_sync_stores_mark(client, repo, project):  # BE19, Q10
    sql("UPDATE projects SET factory_error = 'old refusal' WHERE id = ?", (project,))
    backlog(repo)
    ok(client, project)
    [p] = rows("SELECT factory_mark, factory_error FROM projects WHERE id = ?", (project,))
    assert p["factory_mark"] and p["factory_error"] is None
    sql("UPDATE tasks SET description_md = 'edited' WHERE import_key = 'factory:101-alpha'")
    r = client.get(f"/api/pages/projects/{project}")
    assert r.status_code == 200 and r.json()["factory_error"] is None
    assert task("101-alpha")["description_md"] == "edited"


# --- Transcripts ---------------------------------------------------------------------


def cc(repo) -> Path:
    """The repo's Claude Code folder under conftest's CLAUDE_CONFIG_DIR."""
    return config.claude_config_dir() / "projects" / folder_name(str(repo))


def plant(repo, rel: str, text: str) -> Path:
    path = cc(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


LEAD = jsonl(user("/factory next", ts="2026-10-17T09:00:00.000Z"),
             assistant("m1", [{"type": "text", "text": "go"}], ts="2026-10-17T09:30:00.000Z"))


def subagent(repo, name, prompt, kind=None, session=S) -> Path:
    path = plant(repo, f"{session}/subagents/agent-{name}.jsonl", jsonl(user(prompt, ts="2026-10-17T09:10:00.000Z")))
    if kind:
        plant(repo, f"{session}/subagents/agent-{name}.meta.json", json.dumps({"agentType": kind}))
    return path


@pytest.fixture
def sessions(repo, two):
    """S with agent-a (001-a round 1), agent-b (001-a spec), and agent-c (002-b round 1)."""
    plant(repo, f"{S}.jsonl", LEAD)
    subagent(repo, "a", "Job 001-a, round 1.", "review-code")
    subagent(repo, "b", "Job 001-a.", "spec-writer")
    subagent(repo, "c", "Job 002-b, round 1.", "review-ux")


def transcripts(jid) -> list[tuple]:
    return [(t["agent_type"], t["name"], t["round"], t["path"]) for t in rows(
        "SELECT * FROM transcripts WHERE task_id = ? ORDER BY path", (task(jid)["id"],))]


def test_transcripts(client, repo, project, sessions):  # AC32
    [a] = ok(client, project, {"job": "001-a"})
    [run] = rows("SELECT * FROM runs")
    assert (run["task_id"], run["session_id"], run["status"], run["log_path"], run["pid"], run["exit_code"],
            run["error"]) == (a["task_id"], S, "succeeded", "", None, None, None)
    assert (run["started_at"], run["ended_at"]) == ("2026-10-17T09:00:00Z", "2026-10-17T09:30:00Z")
    rid = run["id"]
    assert transcripts("001-a") == [
        ("orchestrator", None, None, f"{rid}/{S}.jsonl"),
        ("review-code", None, 1, f"{rid}/{S}/subagents/agent-a.jsonl"),
        ("spec-writer", None, None, f"{rid}/{S}/subagents/agent-b.jsonl"),
    ]
    assert a["transcripts"] == 3
    for rel in (f"{S}.jsonl", f"{S}/subagents/agent-a.jsonl", f"{S}/subagents/agent-b.jsonl"):
        assert (config.data_dir() / "transcripts" / str(rid) / rel).read_bytes() == (cc(repo) / rel).read_bytes()
    listed = client.get(f"/api/tasks/{a['task_id']}/transcripts").json()
    assert sorted(t["agent_type"] for t in listed) == ["orchestrator", "review-code", "spec-writer"]


def test_approver_round(client, repo, project, sessions):  # AC33
    subagent(repo, "d", "Job 001-a, round 2, rounds used 2 of 2.", "approver")
    ok(client, project, {"job": "001-a"})
    assert [(k, r) for k, _, r, p in transcripts("001-a") if p.endswith("agent-d.jsonl")] == [("approver", 2)]


def test_teammate(client, repo, project, sessions):  # AC34
    plant(repo, f"{S}.jsonl", LEAD + jsonl(spawn("builder-001-a", "builder")))
    plant(repo, "T.jsonl", jsonl(
        line(type="user", teamName=f"session-{S[:8]}", agentName="builder-001-a", timestamp="2026-10-17T09:20:00.000Z",
             message={"role": "user", "content": "<teammate-message>Job 001-a, round 2.</teammate-message>"})))
    ok(client, project, {"job": "001-a"})
    [run] = rows("SELECT id FROM runs")
    assert ("builder", "builder-001-a", 2, f"{run['id']}/T.jsonl") in transcripts("001-a")


def test_two_jobs_share_a_session(client, repo, project, sessions):  # AC35
    plant(repo, "other-session.jsonl", LEAD)  # ran neither job
    ok(client, project)
    runs = rows("SELECT * FROM runs ORDER BY id")
    assert [(r["task_id"], r["session_id"]) for r in runs] == [(task("001-a")["id"], S), (task("002-b")["id"], S)]
    rid = runs[1]["id"]
    assert transcripts("002-b") == [("orchestrator", None, None, f"{rid}/{S}.jsonl"),
                                    ("review-ux", None, 1, f"{rid}/{S}/subagents/agent-c.jsonl")]


def test_transcripts_rerun(client, project, sessions):  # AC36
    ok(client, project)
    before = counts()
    ok(client, project)
    assert counts() == before and before["runs"] == 2 and before["transcripts"] == 5


def test_no_folder_and_symlinks(client, tmp_path, repo, project, two):  # AC37
    assert [j["transcripts"] for j in ok(client, project)] == [0, 0]
    assert counts()["runs"] == 0
    real = tmp_path / "agent.jsonl"
    real.write_text(jsonl(user("Job 001-a, round 1.")))
    plant(repo, f"{S}.jsonl", LEAD)
    link = cc(repo) / S / "subagents" / "agent-link.jsonl"
    link.parent.mkdir(parents=True)
    link.symlink_to(real)
    assert [j["transcripts"] for j in ok(client, project)] == [0, 0]
    assert counts()["runs"] == 0


# --- Docs, skill, ignore ---------------------------------------------------------------


def test_gitignore():  # AC42; 114 AC9: this repo's own factory/ is gone, so its lines are too
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert "factory/jobs/" not in lines and "factory/board.json" not in lines


def test_docs():  # AC44
    data = (ROOT / "docs" / "data-model-and-api.md").read_text()
    tasks = data[data.index("CREATE TABLE tasks ("):data.index("CREATE TABLE runs")]
    assert "import_key TEXT UNIQUE" in tasks
    api = data[data.index("### 6.1"):data.index("### 6.2")]
    assert "POST /api/projects/3/import-factory" in api
    cc_doc = (ROOT / "docs" / "claude-code.md").read_text()
    assert "| `fctl import-factory [--job ID]` |" in cc_doc[cc_doc.index("### 7.2"):cc_doc.index("### 7.3")]
    mvp = (ROOT / "docs" / "MVP.md").read_text()
    assert "`<project>/factory/`" in mvp[mvp.index("### 4.5"):mvp.index("### 4.6")]


def test_backlog_docs():  # 058 BE32
    data = (ROOT / "docs" / "data-model-and-api.md").read_text()
    projects = data[data.index("CREATE TABLE projects ("):data.index("CREATE TABLE tasks (")]
    assert "factory_mark" in projects and "factory_error" in projects
    api = data[data.index("### 6.1"):data.index("### 6.2")]
    block = api[api.index("POST /api/projects/3/import-factory"):api.index("POST /api/projects/3/import ")]
    assert '"skipped"' in block and "backlog.md" in block
    pages = data[data.index("### 6.4"):]
    assert "factory_error" in pages[pages.index("GET  /api/pages/projects/{id} "):pages.index("GET  /api/pages/tasks/{id}")]
    cc_doc = (ROOT / "docs" / "claude-code.md").read_text()
    section = cc_doc[cc_doc.index("### 7.2"):cc_doc.index("### 7.3")]
    [row] = [line for line in section.splitlines() if line.startswith("| `fctl import-factory")]
    assert "backlog.md" in row
    ui = (ROOT / "docs" / "ui.md").read_text()
    assert "factory/: " in ui[ui.index("3. **Project board**"):ui.index("4. **")]
    assert "Sync factory/" in ui[ui.index("12. **Project settings**"):ui.index("13. **")]
    fctl = (ROOT / "src" / "workcell" / "fctl.md").read_text()
    connect = fctl[fctl.index("## fctl connect\n"):fctl.index("## fctl context\n")]
    assert "Synced factory/: 2 new, 1 updated, 3 skipped" in connect
    imports = fctl[fctl.index("## fctl import-factory\n"):fctl.index("## fctl export\n")]
    for text in ("Skipped 2 lines in factory/backlog.md", "`No jobs in factory/`",
                 "404 no factory/board.json or factory/backlog.md in <path>"):
        assert text in imports, text
