import json
import os

import pytest
from conftest import commit, sql, write

from claude_factories import cli

H = {"X-Requested-By": "fctl"}
OLD = "2026-01-01T00:00:00Z"
SHA = "9f2c1e4b7d0a4c1d2aae81f0b3a1b2c3d4e5f607"
FILES = "path, old_path, change, binary, additions, deletions"
AC1_ROWS = [
    ("a.py", None, "modified", 0, 1, 1),
    ("b.py", None, "deleted", 0, 0, 4),
    ("c.py", None, "added", 0, 2, 0),
]
MISSING = object()


@pytest.fixture
def project(client):
    return connect(client, "/code/api")


def connect(client, path):
    body = {"path": path, "workspace": "personal", "name": "api", "default_branch": "main"}
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def add_task(project_id, status="in_progress", stage=None, position=1.0, worktree=None):
    return sql(
        "INSERT INTO tasks (project_id, title, status, stage, position, worktree_path, created_at, updated_at)"
        " VALUES (?, 't', ?, ?, ?, ?, ?, ?) RETURNING id",
        (project_id, status, stage, position, worktree, OLD, OLD),
    )[0][0]


@pytest.fixture
def task(project):
    return add_task(project)


def add_round(task_id, n=1):
    return sql(
        "INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, ?, 'initial', ?, ?) RETURNING id",
        (task_id, n, SHA, OLD),
    )[0][0]


def add_decision(task_id, round_id, actor, decision):
    sql("INSERT INTO decisions (task_id, round_id, actor, decision, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, round_id, actor, decision, OLD))


def captured(repo, monkeypatch) -> str:
    """The patch `fctl submit` would send from repo (§7.4 capture)."""
    monkeypatch.chdir(repo)
    return cli.capture()[1]


@pytest.fixture
def ac1_patch(repo, monkeypatch):
    """a.py: 1 line changed; b.py: 4 lines deleted; c.py: 2 lines added."""
    commit(repo, {"a.py": "x = 1\n", "b.py": "b1\nb2\nb3\nb4\n"})
    write(repo, {"a.py": "x = 2\n", "c.py": "c = 1\nc = 2\n"})
    (repo / "b.py").unlink()
    return captured(repo, monkeypatch)


def post(client, task_id, patch, **body):
    return client.post(f"/api/tasks/{task_id}/rounds", json={"base_sha": SHA, "patch": patch} | body, headers=H)


def files(task_id):
    """The task's latest round's round_files, in insertion order."""
    return sql(
        f"SELECT {FILES} FROM round_files WHERE round_id ="
        " (SELECT id FROM rounds WHERE task_id = ? ORDER BY n DESC LIMIT 1) ORDER BY rowid",
        (task_id,),
    )


def split(client, task_id, patch):
    r = post(client, task_id, patch)
    assert r.status_code == 201, r.text
    return files(task_id)


def rounds(task_id):
    return sql("SELECT n, trigger, base_sha, build_md FROM rounds WHERE task_id = ? ORDER BY n", (task_id,))


def task_row(task_id):
    return sql("SELECT status, stage, position FROM tasks WHERE id = ?", (task_id,))[0]


def events(task_id):
    return sql("SELECT actor, from_status, to_status, stage FROM events WHERE task_id = ? ORDER BY id", (task_id,))


def counts(*tables):
    return [sql(f"SELECT COUNT(*) FROM {t}")[0][0] for t in tables]


def big_patch(size):
    """A well-formed patch of exactly `size` UTF-8 bytes; the ï makes bytes ≠ characters."""
    head = "diff --git a/big.txt b/big.txt\nnew file mode 100644\n--- /dev/null\n+++ b/big.txt\n@@ -0,0 +1 @@\n+naïve "
    patch = head + "x" * (size - len(head.encode()) - 1) + "\n"
    assert len(patch.encode()) == size
    return patch


def hand_patch(new, header="diff --git a/x b/x"):
    """A hand-written one-file patch whose `+++` name is `new` (git never writes these names)."""
    return f"{header}\n--- a/x\n+++ {new}\n@@ -1 +1 @@\n-a\n+b\n"


# --- Patch split into round_files --------------------------------------------


def test_split_modified_deleted_added(client, task, ac1_patch):  # AC1
    assert split(client, task, ac1_patch) == AC1_ROWS
    patches = [p for (p,) in sql("SELECT patch FROM round_files ORDER BY rowid")]
    for (path, *_), patch in zip(AC1_ROWS, patches, strict=True):
        assert patch.startswith(f"diff --git a/{path} b/{path}\n")
    assert "".join(patches) == ac1_patch


def test_split_renames(client, task, repo, monkeypatch):  # AC2
    lines = [f"line {i}\n" for i in range(10)]
    commit(repo, {"old.py": "".join(lines), "x.txt": "same\n"})
    (repo / "old.py").unlink()
    write(repo, {"new.py": "".join(["changed\n"] + lines[1:])})
    (repo / "x.txt").rename(repo / "y.txt")
    assert split(client, task, captured(repo, monkeypatch)) == [
        ("new.py", "old.py", "renamed", 0, 1, 1),
        ("y.txt", "x.txt", "renamed", 0, 0, 0),
    ]


def test_split_binary(client, task, repo, monkeypatch):  # AC3
    write(repo, {"img.bin": b"\x89PNG\0\0\x01\xff"})
    assert split(client, task, captured(repo, monkeypatch)) == [("img.bin", None, "added", 1, 0, 0)]


def test_split_mode_change(client, task, repo, monkeypatch):  # AC4
    commit(repo, {"run.sh": "echo hi\n"})
    (repo / "run.sh").chmod(0o755)
    assert split(client, task, captured(repo, monkeypatch)) == [("run.sh", None, "modified", 0, 0, 0)]


def test_split_space_and_quote_names(client, task, repo, monkeypatch):  # AC5
    write(repo, {"my notes.txt": "a\n", 'say "hi".txt': "b\n"})
    patch = captured(repo, monkeypatch)
    assert "+++ b/my notes.txt\t\n" in patch  # git's trailing tab and C-quoting reach the parser
    assert '+++ "b/say \\"hi\\".txt"' in patch
    assert [row[0] for row in split(client, task, patch)] == ["my notes.txt", 'say "hi".txt']


def test_split_counts_header_like_lines(client, task, repo, monkeypatch):  # AC6
    commit(repo, {"m.txt": "keep\n-- old\n"})
    write(repo, {"m.txt": "keep\n++ new\n"})
    patch = captured(repo, monkeypatch)
    assert "\n--- old\n+++ new\n" in patch
    assert split(client, task, patch) == [("m.txt", None, "modified", 0, 1, 1)]


def test_split_typechange_merges(client, task, repo, monkeypatch):  # AC7
    commit(repo, {"link": "x\n"})
    (repo / "link").unlink()
    os.symlink("target", repo / "link")
    patch = captured(repo, monkeypatch)
    assert split(client, task, patch) == [("link", None, "modified", 0, 1, 1)]
    [(stored,)] = sql("SELECT patch FROM round_files")
    assert stored == patch
    assert stored.count("diff --git a/link b/link\n") == 2


# --- POST /api/tasks/{id}/rounds ---------------------------------------------


def test_round_response(client, task, ac1_patch):  # AC8
    add_round(task, 1)
    r = post(client, task, ac1_patch, build_md="Token bucket …")
    assert r.status_code == 201, r.text
    [(count, additions, deletions)] = sql(
        "SELECT COUNT(*), SUM(additions), SUM(deletions) FROM round_files f JOIN rounds r ON r.id = f.round_id"
        " WHERE r.task_id = ? AND r.n = 2",
        (task,),
    )
    assert r.json() == {"round": 2, "files_changed": count, "additions": additions, "deletions": deletions,
                        "url": f"http://127.0.0.1:4545/tasks/{task}/review?round=2"}
    assert (count, additions, deletions) == (3, 3, 5)
    assert sql("SELECT base_sha, build_md FROM rounds WHERE task_id = ? AND n = 2", (task,)) == [
        (SHA, "Token bucket …")
    ]


def test_round_without_build_md(client, task, ac1_patch):  # AC9
    assert post(client, task, ac1_patch).status_code == 201
    assert rounds(task)[0][3] is None


def test_first_round_is_initial(client, task, ac1_patch):  # AC10
    assert post(client, task, ac1_patch).status_code == 201
    assert rounds(task) == [(1, "initial", SHA, None)]


@pytest.mark.parametrize("decision", [None, ("approver", "ESCALATE")])
def test_round_after_agent_is_agent(client, task, ac1_patch, decision):  # AC11
    round_id = add_round(task, 1)
    if decision:
        add_decision(task, round_id, *decision)
    assert post(client, task, ac1_patch).status_code == 201
    assert rounds(task)[1][:2] == (2, "agent")


def test_round_after_my_changes_requested_is_human(client, task, ac1_patch):  # AC12
    add_decision(task, add_round(task, 1), "me", "CHANGES_REQUESTED")
    assert post(client, task, ac1_patch).status_code == 201
    assert post(client, task, ac1_patch).status_code == 201
    assert [r[:2] for r in rounds(task)] == [(1, "initial"), (2, "human"), (3, "agent")]


def test_standalone_round_moves_to_review(client, project, ac1_patch):  # AC13
    task = add_task(project, "in_progress", "rework", 3.0)
    assert post(client, task, ac1_patch).status_code == 201
    assert task_row(task) == ("review", "human_review", 3.0)
    assert events(task) == [("app", "in_progress", "review", "human_review")]
    assert post(client, task, ac1_patch).status_code == 201  # already in review · human_review
    assert task_row(task) == ("review", "human_review", 3.0)
    assert len(events(task)) == 1


def test_worktree_round_keeps_status(client, project, ac1_patch):  # AC14
    task = add_task(project, "in_progress", "build", worktree="/code/api/.claude/worktrees/12-x")
    assert post(client, task, ac1_patch).status_code == 201
    assert task_row(task)[:2] == ("in_progress", "build")
    assert events(task) == []


def test_round_unknown_task(client, ac1_patch):  # AC15
    assert post(client, 999, ac1_patch).status_code == 404
    assert counts("rounds", "round_files") == [0, 0]


@pytest.mark.parametrize("change", [
    {"base_sha": MISSING}, {"base_sha": "HEAD"}, {"base_sha": "-c"}, {"base_sha": "abc"},
    {"patch": MISSING}, {"patch": "hello\n"}, {"patch": "diff --git nonsense\n"},
    # round 2 (review-security): malformed C-quoting and unsafe paths
    {"patch": hand_patch('"b/x\\"')}, {"patch": hand_patch('"b/\\x"')},
    {"patch": 'diff --git "a/\\x" "b/\\x"\nold mode 100644\nnew mode 100755\n'},
    {"patch": hand_patch("b/../etc/passwd")}, {"patch": hand_patch("b//etc/passwd")},
    {"patch": hand_patch("b/x\0y")},
    {"patch": "diff --git a/x b/y\nsimilarity index 100%\nrename from ../x\nrename to y\n"},
])
def test_round_bad_body(client, task, ac1_patch, change):  # AC16
    body = {k: v for k, v in ({"base_sha": SHA, "patch": ac1_patch} | change).items() if v is not MISSING}
    r = client.post(f"/api/tasks/{task}/rounds", json=body, headers=H)
    assert r.status_code == 422, r.text
    assert counts("rounds", "round_files") == [0, 0]


@pytest.mark.parametrize("patch", ["", "\n"])
def test_round_empty_patch(client, task, patch):  # AC17
    r = post(client, task, patch)
    assert (r.status_code, r.json()) == (422, {"detail": "no changes to submit"})


def test_round_lone_surrogate(client, task, ac1_patch):  # not an AC: a 422 instead of a 500
    body = '{"base_sha": "%s", "build_md": "\\ud800", "patch": %s}' % (SHA, json.dumps(ac1_patch))
    r = client.post(f"/api/tasks/{task}/rounds", content=body, headers=H | {"Content-Type": "application/json"})
    assert (r.status_code, r.json()) == (422, {"detail": "text must not contain lone surrogates"})
    assert counts("rounds", "round_files") == [0, 0]


@pytest.mark.parametrize("size, status", [(5_242_881, 413), (5_242_880, 201)])
def test_round_patch_size(client, task, size, status):  # AC18
    r = post(client, task, big_patch(size))
    assert r.status_code == status, r.text[:200]
    if status == 413:
        assert r.json() == {"detail": "patch over 5 MB"}
        assert counts("rounds", "round_files") == [0, 0]


# --- POST /api/projects/{id}/tasks with submit --------------------------------


def create(client, project_id, patch, title="Fix open redirect after login"):
    body = {"title": title, "description_md": "`next` was …", "submit": {"base_sha": SHA, "patch": patch}}
    return client.post(f"/api/projects/{project_id}/tasks", json=body, headers=H)


def test_submit_new_response(client, project, ac1_patch):  # AC19
    r = create(client, project, ac1_patch)
    assert r.status_code == 201, r.text
    [(task,)] = sql("SELECT id FROM tasks")
    assert r.json() == {"task_id": task, "round": 1, "files_changed": 3, "additions": 3, "deletions": 5,
                        "url": f"http://127.0.0.1:4545/tasks/{task}/review"}


def test_submit_new_task_row(client, project, ac1_patch):  # AC20
    for status, position in (("review", 2.0), ("review", 7.0), ("backlog", 20.0)):
        add_task(project, status, position=position)
    task = create(client, project, ac1_patch).json()["task_id"]
    assert sql("SELECT status, stage, branch, worktree_path, description_md, position FROM tasks WHERE id = ?",
               (task,)) == [("review", "human_review", None, None, "`next` was …", 8.0)]
    empty = connect(client, "/code/web")
    task = create(client, empty, ac1_patch).json()["task_id"]
    assert task_row(task)[2] == 1.0


def test_submit_new_round(client, project, ac1_patch):  # AC21
    task = create(client, project, ac1_patch).json()["task_id"]
    assert rounds(task) == [(1, "initial", SHA, None)]
    assert files(task) == AC1_ROWS


def test_submit_new_event(client, project, ac1_patch):  # AC22
    task = create(client, project, ac1_patch).json()["task_id"]
    assert events(task) == [("app", None, "review", "human_review")]


@pytest.mark.parametrize("patch, title", [("", "Fix it"), (None, "  ")])
def test_submit_new_rejected(client, project, ac1_patch, patch, title):  # AC23
    r = create(client, project, ac1_patch if patch is None else patch, title)
    assert r.status_code == 422, r.text
    assert counts("tasks", "rounds", "round_files", "events") == [0, 0, 0, 0]


def test_submit_new_too_big(client, project):  # AC24
    r = create(client, project, big_patch(5_242_881))
    assert r.status_code == 413
    assert counts("tasks", "rounds", "round_files", "events") == [0, 0, 0, 0]


# --- GET /api/tasks/{id}/rounds/{n|latest}/diff --------------------------------


def test_diff_returns_patch_bytes(client, task, repo, monkeypatch):  # AC25
    commit(repo, {"w.txt": "keep\r\nold\r\n"})
    write(repo, {"w.txt": "keep\r\nnew\r\n", "naïve.txt": "naïve\n"})
    first = captured(repo, monkeypatch)
    write(repo, {"later.py": "x\n"})
    second = captured(repo, monkeypatch)
    assert "-old\r\n" in first and "naïve" in first
    assert post(client, task, first).status_code == 201
    assert post(client, task, second).status_code == 201
    for n, patch in (("1", first), ("latest", second)):
        r = client.get(f"/api/tasks/{task}/rounds/{n}/diff")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/x-diff")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.content == patch.encode()


def test_diff_missing(client, task):  # AC26
    r = client.get(f"/api/tasks/{task}/rounds/latest/diff")
    assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no rounds"})
    for n in ("9", "abc"):
        r = client.get(f"/api/tasks/{task}/rounds/{n}/diff")
        assert (r.status_code, r.json()) == (404, {"detail": f"#{task} has no round {n}"})
    assert client.get("/api/tasks/999/rounds/latest/diff").status_code == 404
