import re

import pytest
from conftest import sql

H = {"X-Requested-By": "fctl"}
OLD = "2026-01-01T00:00:00Z"
REVIEWERS = ("security", "ux", "ui", "code")
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
STAGES = {
    "spec": "in_progress", "build": "in_progress", "agent_review": "in_progress",
    "approval": "in_progress", "rework": "in_progress", "human_review": "review", "escalated": "review",
}


@pytest.fixture
def project(client):
    """A connected project's id."""
    return connect(client, "/code/api")


def connect(client, path):
    body = {"path": path, "workspace": "personal", "name": "api", "default_branch": "main"}
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def create(client, project_id, **body):
    return client.post(f"/api/projects/{project_id}/tasks", json={"title": "x"} | body, headers=H)


def add_task(project_id, status="backlog", position=1.0, stage=None, branch=None):
    return sql(
        "INSERT INTO tasks (project_id, title, status, stage, position, branch, created_at, updated_at)"
        " VALUES (?, 't', ?, ?, ?, ?, ?, ?) RETURNING id",
        (project_id, status, stage, position, branch, OLD, OLD),
    )[0][0]


def add_round(task_id, n, trigger="initial", files=(), verdicts=None):
    round_id = sql(
        "INSERT INTO rounds (task_id, n, trigger, base_sha, created_at)"
        " VALUES (?, ?, ?, 'abc', ?) RETURNING id",
        (task_id, n, trigger, OLD),
    )[0][0]
    for i, (additions, deletions) in enumerate(files):
        sql("INSERT INTO round_files (round_id, path, change, additions, deletions, patch)"
            " VALUES (?, ?, 'modified', ?, ?, '')", (round_id, f"f{i}.py", additions, deletions))
    for reviewer, verdict in (verdicts or {}).items():
        sql("INSERT INTO verdicts (round_id, reviewer, verdict, body_md, created_at) VALUES (?, ?, ?, '', ?)",
            (round_id, reviewer, verdict, OLD))
    return round_id


def add_run(task_id, status):
    return sql(
        "INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
        " VALUES (?, 's', ?, 'l', ?) RETURNING id",
        (task_id, status, OLD),
    )[0][0]


def row(task_id):
    columns = "status, stage, position, updated_at, done_at, spec_md"
    return sql(f"SELECT {columns} FROM tasks WHERE id = ?", (task_id,))[0]


def events(task_id):
    return sql("SELECT actor, from_status, to_status, stage, note FROM events WHERE task_id = ? ORDER BY id",
               (task_id,))


def patch(client, task_id, body):
    return client.patch(f"/api/tasks/{task_id}", json=body, headers=H)


def listed(client, project_id):
    r = client.get(f"/api/projects/{project_id}/tasks")
    assert r.status_code == 200, r.text
    return r.json()


# --- POST /api/projects/{id}/tasks ---------------------------------------------


def test_create(client, project):  # AC1
    r = create(client, project, title="Rate-limit login endpoint",
               description_md="Max 5 failed logins/min per IP.")
    assert r.status_code == 201
    task_id = r.json()["id"]
    assert r.json() == {"id": task_id, "status": "backlog"}
    rows = sql("SELECT project_id, title, description_md, status, stage, spec_md, branch, worktree_path,"
               " done_at, created_at, updated_at FROM tasks")
    assert len(rows) == 1
    *values, created_at, updated_at = rows[0]
    assert values == [project, "Rate-limit login endpoint", "Max 5 failed logins/min per IP.", "backlog",
                      None, None, None, None, None]
    assert created_at == updated_at
    assert TIMESTAMP.fullmatch(created_at)


def test_create_without_description(client, project):  # AC2
    r = client.post(f"/api/projects/{project}/tasks", json={"title": "x"}, headers=H)
    assert r.status_code == 201
    assert sql("SELECT description_md FROM tasks") == [("",)]


def test_create_strips_title(client, project):  # AC3
    assert create(client, project, title="  Export CSV  ").status_code == 201
    assert sql("SELECT title FROM tasks") == [("Export CSV",)]


@pytest.mark.parametrize("title", ["", "   "])
def test_create_blank_title(client, project, title):  # AC4
    r = create(client, project, title=title)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert sql("SELECT COUNT(*) FROM tasks") == [(0,)]
    assert sql("SELECT COUNT(*) FROM events") == [(0,)]


def test_create_unknown_project(client, project):  # AC5
    assert create(client, project + 1).status_code == 404
    assert sql("SELECT COUNT(*) FROM tasks") == [(0,)]
    assert sql("SELECT COUNT(*) FROM events") == [(0,)]


def test_first_task_position(client, project):  # AC6
    create(client, project)
    assert sql("SELECT position FROM tasks") == [(1.0,)]


def test_new_task_at_bottom_of_backlog(client, project):  # AC7
    other = connect(client, "/code/other")
    add_task(project, "backlog", 1.0)
    add_task(project, "backlog", 5.0)
    add_task(project, "review", 9.0)
    add_task(other, "backlog", 20.0)
    task_id = create(client, project).json()["id"]
    assert sql("SELECT position FROM tasks WHERE id = ?", (task_id,)) == [(6.0,)]


def test_create_writes_event(client, project):  # AC8
    task_id = create(client, project).json()["id"]
    rows = sql("SELECT actor, from_status, to_status, stage, note, created_at FROM events WHERE task_id = ?",
               (task_id,))
    assert len(rows) == 1
    assert rows[0][:5] == ("me", None, "backlog", None, None)
    assert TIMESTAMP.fullmatch(rows[0][5])


# --- GET /api/projects/{id}/tasks -----------------------------------------------


def test_list_empty(client, project):  # AC9
    assert listed(client, project) == []


def test_list_unknown_project(client):  # AC10
    assert client.get("/api/projects/999/tasks").status_code == 404


def test_list_fresh_task(client, project):  # AC11
    task_id = create(client, project, title="Export CSV").json()["id"]
    assert listed(client, project) == [{
        "id": task_id, "title": "Export CSV", "status": "backlog", "stage": None, "round": None,
        "verdicts": None, "additions": None, "deletions": None, "run": None,
    }]


def test_list_latest_round(client, project):  # AC12
    task_id = add_task(project)
    add_round(task_id, 1, files=[(50, 50)], verdicts=dict.fromkeys(REVIEWERS, "CHANGES"))
    add_round(task_id, 2, "agent", files=[(100, 5), (26, 4)], verdicts=dict.fromkeys(REVIEWERS, "PASS"))
    [item] = listed(client, project)
    assert item["round"] == 2
    assert item["verdicts"] == {"security": "PASS", "ux": "PASS", "ui": "PASS", "code": "PASS"}
    assert (item["additions"], item["deletions"]) == (126, 9)


def test_list_pending_verdicts(client, project):  # AC13
    task_id = add_task(project)
    add_round(task_id, 1, verdicts={"security": "PASS", "code": "CHANGES"})
    [item] = listed(client, project)
    assert item["verdicts"] == {"security": "PASS", "ux": "pending", "ui": "pending", "code": "CHANGES"}


def test_list_latest_run(client, project):  # AC14
    running_task, failed_task = add_task(project, position=1), add_task(project, position=2)
    add_run(running_task, "failed")
    running = add_run(running_task, "running")
    failed = add_run(failed_task, "failed")
    items = listed(client, project)
    assert items[0]["run"] == {"id": running, "status": "running"}
    assert items[1]["run"] == {"id": failed, "status": "failed"}


def test_list_order(client, project):  # AC15
    other = connect(client, "/code/other")
    done = add_task(project, "done", 0.1)
    review = add_task(project, "review", 3.0)
    backlog_late = add_task(project, "backlog", 2.0)
    in_progress = add_task(project, "in_progress", 0.5)
    backlog_tie_a = add_task(project, "backlog", 1.0)
    backlog_tie_b = add_task(project, "backlog", 1.0)
    add_task(other, "backlog", 0.0)
    ids = [item["id"] for item in listed(client, project)]
    assert ids == [backlog_tie_a, backlog_tie_b, backlog_late, in_progress, review, done]


# --- GET /api/tasks/{id} ---------------------------------------------------------


def test_get_fresh_task(client, project):  # AC16
    task_id = create(client, project, title="Export CSV").json()["id"]
    r = client.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json() == {"id": task_id, "title": "Export CSV", "status": "backlog", "stage": None,
                        "branch": None, "rounds": [], "decisions": [], "run": None}


def test_get_rounds(client, project):  # AC17
    task_id = add_task(project)
    add_round(task_id, 1, "initial", files=[(100, 5), (10, 2), (5, 1), (3, 1)],
              verdicts={"security": "CHANGES", "ux": "PASS", "code": "PASS"})
    add_round(task_id, 2, "agent")
    assert client.get(f"/api/tasks/{task_id}").json()["rounds"] == [
        {"n": 1, "trigger": "initial", "files": 4, "additions": 118, "deletions": 9,
         "verdicts": {"security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS"}},
        {"n": 2, "trigger": "agent", "files": 0, "additions": 0, "deletions": 0,
         "verdicts": {"security": "pending", "ux": "pending", "ui": "pending", "code": "pending"}},
    ]


def test_get_decisions(client, project):  # AC18
    task_id = add_task(project)
    r1, r2 = add_round(task_id, 1), add_round(task_id, 2, "agent")
    insert = ("INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at)"
              " VALUES (?, ?, ?, ?, ?, ?) RETURNING id")
    d1 = sql(insert, (task_id, r1, "approver", "ESCALATE", "needs a human", "2026-01-02T00:00:00Z"))[0][0]
    d2 = sql(insert, (task_id, r2, "me", "CHANGES_REQUESTED", "use Redis", "2026-01-03T00:00:00Z"))[0][0]
    assert client.get(f"/api/tasks/{task_id}").json()["decisions"] == [
        {"id": d1, "round": 1, "actor": "approver", "decision": "ESCALATE", "body_md": "needs a human",
         "created_at": "2026-01-02T00:00:00Z"},
        {"id": d2, "round": 2, "actor": "me", "decision": "CHANGES_REQUESTED", "body_md": "use Redis",
         "created_at": "2026-01-03T00:00:00Z"},
    ]


def test_get_branch_and_run(client, project):  # AC19
    task_id = add_task(project, "in_progress", stage="build", branch="factory/12-x")
    run_id = add_run(task_id, "running")
    got = client.get(f"/api/tasks/{task_id}").json()
    assert got["branch"] == "factory/12-x"
    assert got["run"] == {"id": run_id, "status": "running"}


def test_get_unknown_task(client):  # AC20
    assert client.get("/api/tasks/999").status_code == 404


# --- PATCH spec_md -----------------------------------------------------------------


def test_patch_spec(client, project):  # AC21
    task_id = add_task(project, "review", stage="human_review")
    r = patch(client, task_id, {"spec_md": "## Acceptance criteria\n- x"})
    assert r.status_code == 200
    assert r.json() == {"id": task_id, "status": "review", "stage": "human_review"}
    status, stage, _, updated_at, _, spec_md = row(task_id)
    assert (status, stage, spec_md) == ("review", "human_review", "## Acceptance criteria\n- x")
    assert updated_at != OLD and TIMESTAMP.fullmatch(updated_at)
    assert events(task_id) == []


# --- PATCH stage -------------------------------------------------------------------


@pytest.mark.parametrize("stage, status", STAGES.items())
def test_patch_stage_maps_status(client, project, stage, status):  # AC22
    task_id = add_task(project)
    r = patch(client, task_id, {"stage": stage})
    assert r.status_code == 200
    assert r.json() == {"id": task_id, "status": status, "stage": stage}
    assert row(task_id)[:2] == (status, stage)


def test_patch_stage_events(client, project):  # AC23
    task_id = add_task(project)
    patch(client, task_id, {"stage": "build"})
    patch(client, task_id, {"stage": "agent_review"})
    assert events(task_id) == [
        ("orchestrator", "backlog", "in_progress", "build", None),
        ("orchestrator", "in_progress", "in_progress", "agent_review", None),
    ]


def test_patch_same_stage_no_event(client, project):  # AC24
    task_id = add_task(project, "in_progress", stage="build")
    r = patch(client, task_id, {"stage": "build"})
    assert r.status_code == 200
    assert events(task_id) == []


def test_patch_stage_during_run(client, project):  # AC25
    task_id = add_task(project, "in_progress", stage="build")
    add_run(task_id, "running")
    r = patch(client, task_id, {"stage": "agent_review"})
    assert r.status_code == 200
    assert row(task_id)[:2] == ("in_progress", "agent_review")


def test_patch_stage_keeps_position(client, project):  # AC26
    task_id = add_task(project, position=3.5)
    patch(client, task_id, {"stage": "spec"})
    assert row(task_id)[2] == 3.5


# --- PATCH status + position (manual move) -------------------------------------------


def test_move_clears_stage(client, project):  # AC27
    task_id = add_task(project, "review", stage="human_review")
    r = patch(client, task_id, {"status": "backlog", "position": 1.5})
    assert r.status_code == 200
    assert r.json() == {"id": task_id, "status": "backlog", "stage": None}
    assert row(task_id)[:3] == ("backlog", None, 1.5)


def test_move_writes_event(client, project):  # AC28
    task_id = add_task(project, "review", stage="human_review")
    patch(client, task_id, {"status": "backlog", "position": 1.5})
    assert events(task_id) == [("me", "review", "backlog", None, None)]


def test_reorder_no_event(client, project):  # AC29
    task_id = add_task(project, position=3.0)
    assert patch(client, task_id, {"status": "backlog", "position": 0.5}).status_code == 200
    assert row(task_id)[2] == 0.5
    assert events(task_id) == []


def test_move_refused_during_run(client, project):  # AC30
    task_id = add_task(project, "in_progress", position=2.0, stage="build")
    run_id = add_run(task_id, "running")
    before = row(task_id)
    r = patch(client, task_id, {"status": "backlog", "position": 1.0})
    assert r.status_code == 409
    assert r.json() == {"detail": f"run #{run_id} active"}
    assert row(task_id) == before
    assert events(task_id) == []


def test_move_allowed_with_other_or_ended_runs(client, project):  # AC31
    task_id, other = add_task(project), add_task(project, "in_progress", stage="build")
    add_run(other, "running")
    for status in ("failed", "succeeded", "stopped"):
        add_run(task_id, status)
    assert patch(client, task_id, {"status": "review", "position": 1.0}).status_code == 200


def test_done_at(client, project):  # AC32
    task_id = add_task(project, "review", stage="human_review")
    patch(client, task_id, {"status": "done", "position": 1.0})
    assert TIMESTAMP.fullmatch(row(task_id)[4])
    patch(client, task_id, {"status": "backlog", "position": 1.0})
    assert row(task_id)[4] is None
    patch(client, task_id, {"status": "done", "position": 1.0})
    patch(client, task_id, {"stage": "rework"})
    assert row(task_id)[4] is None


# --- PATCH validation ------------------------------------------------------------------


@pytest.mark.parametrize("body", [
    {}, {"status": "backlog"}, {"position": 2}, {"stage": "build", "status": "review", "position": 1},
    {"spec_md": "x", "stage": "build"}, {"stage": None}, {"spec_md": None}, {"stage": "deploy"},
    {"status": "archived", "position": 1}, '{"status":"backlog","position":NaN}',
])
def test_patch_invalid(client, project, body):  # AC33
    task_id = create(client, project).json()["id"]
    before, history = row(task_id), events(task_id)
    if isinstance(body, str):
        r = client.patch(f"/api/tasks/{task_id}", content=body,
                         headers=H | {"Content-Type": "application/json"})
    else:
        r = patch(client, task_id, body)
    assert r.status_code == 422
    assert row(task_id) == before
    assert events(task_id) == history


def test_patch_unknown_task(client):  # AC34
    assert patch(client, 999, {"stage": "build"}).status_code == 404
