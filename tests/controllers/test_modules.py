"""112: a project's modules, and a module on each task (docs/data-model-and-api.md §5.1, §6.1, §6.2)."""

import pytest
from conftest import sql

from .test_projects import H, connect

ZERO = {"backlog": 0, "in_progress": 0, "review": 0, "done": 0}


@pytest.fixture
def pid(client):
    return connect(client)["id"]


def add(client, project_id, name, **body):
    return client.post(f"/api/projects/{project_id}/modules", json={"name": name} | body, headers=H)


def made(client, project_id, name):
    r = add(client, project_id, name)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def patch(client, module_id, body):
    return client.patch(f"/api/modules/{module_id}", json=body, headers=H)


def listed(client, project_id):
    return client.get(f"/api/projects/{project_id}/modules")


def new_task(client, project_id, **body):
    return client.post(f"/api/projects/{project_id}/tasks", json={"title": "t"} | body, headers=H)


def task_module(task_id):
    return sql("SELECT module_id FROM tasks WHERE id = ?", (task_id,))[0][0]


def module_rows():
    return sql("SELECT project_id, name, description_md FROM modules ORDER BY id")


# --- Modules API ----------------------------------------------------------------------


def test_create(client, pid):  # AC4
    r = add(client, pid, "  frontend ", description_md="UI")
    assert r.status_code == 201
    assert r.json() == {"id": r.json()["id"], "name": "frontend", "description_md": "UI", "counts": ZERO}
    r = add(client, pid, "backend")
    assert r.status_code == 201 and r.json()["description_md"] == ""
    assert module_rows() == [(pid, "frontend", "UI"), (pid, "backend", "")]


@pytest.mark.parametrize("name", ["", "   ", "x" * 41, "front end", "ui/web", "naïve", "a.b"])
def test_create_bad_name(client, pid, name):  # AC5
    r = add(client, pid, name)
    assert r.status_code == 422
    assert r.json()["detail"] == "a module name is 1 to 40 ASCII letters, digits, - or _, e.g. frontend or api_v2"
    assert module_rows() == []


def test_create_name_limits(client, pid):  # AC5: 40 chars and every allowed kind pass
    assert add(client, pid, "a" * 40).status_code == 201
    assert add(client, pid, "Api_v2-x").status_code == 201


def test_create_duplicate(client, pid):  # AC6
    made(client, pid, "frontend")
    r = add(client, pid, "Frontend")
    assert r.status_code == 409
    assert r.json() == {"detail": "module frontend already exists"}
    other = connect(client, path="/code/other")["id"]
    assert add(client, other, "Frontend").status_code == 201
    assert len(module_rows()) == 2


def test_create_unknown_project(client):  # AC7
    r = add(client, 999, "frontend")
    assert r.status_code == 404
    assert module_rows() == []


def test_patch(client, pid):  # AC8
    mid = made(client, pid, "frontend")
    r = patch(client, mid, {"name": " web ", "description_md": "The SPA"})
    assert r.status_code == 200
    assert r.json() == {"id": mid, "name": "web", "description_md": "The SPA", "counts": ZERO}
    assert patch(client, mid, {"description_md": ""}).json()["name"] == "web"
    assert patch(client, mid, {"name": "WEB"}).json() == {"id": mid, "name": "WEB", "description_md": "", "counts": ZERO}


@pytest.mark.parametrize("body, status", [
    ({"name": "front end"}, 422), ({"name": " "}, 422), ({"name": "x" * 41}, 422), ({"name": "Backend"}, 409),
    ({}, 422), ({"name": None}, 422), ({"description_md": None}, 422), ({"name": "ok", "description_md": None}, 422),
])
def test_patch_refused(client, pid, body, status):  # AC8
    mid = made(client, pid, "frontend")
    made(client, pid, "backend")
    r = patch(client, mid, body)
    assert r.status_code == status
    if status == 409:
        assert r.json() == {"detail": "module backend already exists"}
    assert module_rows()[0] == (pid, "frontend", "")


def test_patch_unknown(client):  # AC8
    assert patch(client, 999, {"name": "x"}).status_code == 404


def test_delete(client, pid):  # AC9
    mid = made(client, pid, "frontend")
    task = new_task(client, pid, module_id=mid).json()["id"]
    r = client.delete(f"/api/modules/{mid}", headers=H)
    assert r.status_code == 204
    assert module_rows() == []
    assert task_module(task) is None
    assert client.delete(f"/api/modules/{mid}", headers=H).status_code == 404


def test_list(client, pid):  # AC10
    web = made(client, pid, "web")
    api = made(client, pid, "API")
    core = made(client, pid, "core")
    other = connect(client, path="/code/other")["id"]
    made(client, other, "elsewhere")
    for module_id, status in ((web, "backlog"), (web, "backlog"), (web, "done"), (api, "review"), (None, "backlog"),
                              (None, "in_progress")):
        task = new_task(client, pid, module_id=module_id).json()["id"]
        sql("UPDATE tasks SET status = ? WHERE id = ?", (status, task))
    new_task(client, other)  # another project's task counts nowhere here
    r = listed(client, pid)
    assert r.status_code == 200
    assert r.json() == {
        "modules": [
            {"id": api, "name": "API", "description_md": "", "counts": ZERO | {"review": 1}},
            {"id": core, "name": "core", "description_md": "", "counts": ZERO},
            {"id": web, "name": "web", "description_md": "", "counts": ZERO | {"backlog": 2, "done": 1}},
        ],
        "no_module": ZERO | {"backlog": 1, "in_progress": 1},
    }
    assert listed(client, 999).status_code == 404


def test_delete_project_with_modules(client, pid):  # AC3
    mid = made(client, pid, "frontend")
    new_task(client, pid, module_id=mid)
    assert client.delete(f"/api/projects/{pid}", headers=H).status_code == 204
    assert module_rows() == []


# --- Tasks with a module ------------------------------------------------------------------


def test_create_task_with_module(client, pid):  # AC11
    mid = made(client, pid, "frontend")
    r = new_task(client, pid, module_id=mid)
    assert r.status_code == 201
    assert task_module(r.json()["id"]) == mid
    assert task_module(new_task(client, pid).json()["id"]) is None
    assert task_module(new_task(client, pid, module_id=None).json()["id"]) is None


def test_create_task_other_module(client, pid):  # AC12
    other = connect(client, path="/code/other")["id"]
    foreign = made(client, other, "frontend")
    for module_id, detail in ((foreign, f"module #{foreign} is in another project; pick one of this project's modules"),
                              (99, "no module #99")):
        r = new_task(client, pid, module_id=module_id)
        assert r.status_code == 422
        assert r.json() == {"detail": detail}
    assert sql("SELECT COUNT(*) FROM tasks") == [(0,)]


def test_patch_task_module(client, pid):  # AC13
    mid = made(client, pid, "frontend")
    task = new_task(client, pid).json()["id"]
    history = sql("SELECT * FROM events WHERE task_id = ?", (task,))
    r = client.patch(f"/api/tasks/{task}", json={"module_id": mid}, headers=H)
    assert r.status_code == 200
    assert r.json() == {"id": task, "status": "backlog", "stage": None}
    assert task_module(task) == mid
    assert client.patch(f"/api/tasks/{task}", json={"module_id": None}, headers=H).status_code == 200
    assert task_module(task) is None
    assert sql("SELECT * FROM events WHERE task_id = ?", (task,)) == history


def test_patch_task_module_refused(client, pid):  # AC13
    mid = made(client, pid, "frontend")
    other = connect(client, path="/code/other")["id"]
    foreign = made(client, other, "frontend")
    task = new_task(client, pid, module_id=mid).json()["id"]
    for module_id in (foreign, 99):
        r = client.patch(f"/api/tasks/{task}", json={"module_id": module_id}, headers=H)
        assert r.status_code == 422
        assert task_module(task) == mid
    # Q4: its own group, not mixed with others
    r = client.patch(f"/api/tasks/{task}", json={"module_id": None, "title": "x"}, headers=H)
    assert r.status_code == 422
    assert client.patch("/api/tasks/999", json={"module_id": None}, headers=H).status_code == 404


def test_task_responses_carry_module(client, pid):  # AC14
    mid = made(client, pid, "frontend")
    with_module = new_task(client, pid, module_id=mid).json()["id"]
    without = new_task(client, pid).json()["id"]
    ref = {"id": mid, "name": "frontend"}
    assert client.get(f"/api/tasks/{with_module}").json()["module"] == ref
    assert client.get(f"/api/tasks/{without}").json()["module"] is None
    items = {t["id"]: t["module"] for t in client.get(f"/api/projects/{pid}/tasks").json()}
    assert items == {with_module: ref, without: None}
    board = client.get(f"/api/pages/projects/{pid}").json()
    assert {c["id"]: c["module"] for c in board["columns"]["backlog"]} == {with_module: ref, without: None}
    assert client.get(f"/api/pages/tasks/{with_module}").json()["task"]["module"] == ref
    assert client.get(f"/api/pages/tasks/{without}").json()["task"]["module"] is None


def test_context_module_line(client, pid):  # AC25
    mid = made(client, pid, "frontend")
    task = new_task(client, pid, title="T", module_id=mid).json()["id"]
    assert client.get(f"/api/tasks/{task}/context").text.startswith(f"# #{task} T\nStatus: backlog\nModule: frontend\n\n")
    plain = new_task(client, pid, title="U").json()["id"]
    text = client.get(f"/api/tasks/{plain}/context").text
    assert text.startswith(f"# #{plain} U\nStatus: backlog\n\n") and "Module:" not in text
