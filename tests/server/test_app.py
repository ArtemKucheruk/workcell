import re

import pytest
from conftest import sql
from controllers.test_pages_api import add_round
from controllers.test_runs import H, add_task, fake, project  # noqa: F401
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from workcell.domain.errors import Conflict, Failed, Invalid, NotFound, TooLarge
from workcell.server.app import create_app

HOST_ERROR = {"detail": "Host must be 127.0.0.1 or localhost"}
HEADER_ERROR = {"detail": "X-Requested-By: fctl header required"}


# --- Local-safety middleware -------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1:4545", "localhost:4545", "localhost", "127.0.0.1:5000"])
def test_local_hosts_allowed(client, host):  # AC18, 026 AC6
    assert client.get("/api/workspaces", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "localhost.evil.example", "127.0.0.1.evil.example"])
def test_foreign_hosts_rejected(client, host):  # AC19, 026 AC6
    r = client.get("/api/workspaces", headers={"Host": host})
    assert r.status_code == 403
    assert r.json() == HOST_ERROR


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_without_header_rejected(client, method):  # AC20
    r = client.request(method, "/anything")
    assert r.status_code == 403
    assert r.json() == HEADER_ERROR


def test_mutating_with_wrong_header_rejected(client):  # AC21
    r = client.post("/anything", headers={"X-Requested-By": "other"})
    assert r.status_code == 403
    assert r.json() == HEADER_ERROR


def test_mutating_with_header_passes(client):  # AC22
    assert client.post("/anything", headers={"X-Requested-By": "fctl"}).status_code == 404


def test_get_needs_no_header(client):  # AC23, 026 AC6
    assert client.get("/api/workspaces").status_code == 200


# --- 034: create_app, routes, domain errors ------------------------------------------

BASE = "http://127.0.0.1:4545"


def routes(found):
    """Every route, with included routers walked into."""
    for r in found:
        if hasattr(r, "original_router"):
            yield from routes(r.original_router.routes)
        else:
            yield r


MOVED_035 = [  # 035 AC1
    ("GET", "/api/projects/{project_id}/tasks"), ("POST", "/api/projects/{project_id}/tasks"),
    ("GET", "/api/tasks/{task_id}"), ("PATCH", "/api/tasks/{task_id}"), ("GET", "/api/tasks/{task_id}/context"),
    ("POST", "/api/tasks/{task_id}/rounds"), ("GET", "/api/tasks/{task_id}/rounds/{n}/diff"),
    ("PUT", "/api/tasks/{task_id}/rounds/{n}/verdicts/{reviewer}"), ("POST", "/api/tasks/{task_id}/comments"),
    ("POST", "/api/tasks/{task_id}/decision"), ("POST", "/api/tasks/{task_id}/approve"),
]
TEXT_035 = {("GET", "/api/tasks/{task_id}/context"), ("GET", "/api/tasks/{task_id}/rounds/{n}/diff")}
RUN_ROUTES = [  # 036
    ("POST", "/api/tasks/{task_id}/run"), ("POST", "/api/projects/{project_id}/run-next"),
    ("POST", "/api/runs/{run_id}/stop"), ("GET", "/api/runs/{run_id}/log"),
]


def test_moved_routes_served_from_controllers():  # 034 AC7, 035 AC1
    modules = {(m, r.path): r.endpoint.__module__
               for r in routes(create_app().routes) for m in getattr(r, "methods", ())}
    for key in [("GET", "/api/workspaces"), ("POST", "/api/projects/connect"), ("GET", "/api/projects"),
                ("POST", "/api/projects/{project_id}/factory"), *MOVED_035]:
        assert modules[key].startswith("workcell.controllers."), key


@pytest.mark.parametrize("error, status, detail", [
    (NotFound("x"), 404, "x"), (NotFound(), 404, "Not Found"), (Conflict("y"), 409, "y"), (TooLarge("z"), 413, "z"),
    (Invalid("w"), 422, "w"),  # 035 AC3
    (Failed("x"), 500, "x"),  # 036 AC5
])
def test_domain_errors_as_json(error, status, detail):  # 034 AC11
    app = create_app()

    @app.get("/api/raises")
    def raises():
        raise error

    with TestClient(app, base_url=BASE) as c:
        r = c.get("/api/raises")
    assert (r.status_code, r.json()) == (status, {"detail": detail})


def test_not_found_json_outside_api():  # 034 AC12, 026 AC5
    app = create_app()

    @app.get("/gone")
    def gone():
        raise NotFound("Gone")

    @app.get("/gone-http")
    def gone_http():
        raise HTTPException(404, "Gone")

    with TestClient(app, base_url=BASE) as c:
        r, same = c.get("/gone"), c.get("/gone-http")
    for found in (r, same):
        assert (found.status_code, found.headers["content-type"], found.json()) == (
            404, "application/json", {"detail": "Gone"})


def test_035_response_models_from_dto():  # 035 AC2
    found = {(m, r.path): r for r in routes(create_app().routes) for m in getattr(r, "methods", ())}
    json_routes = [key for key in MOVED_035 if key not in TEXT_035] + [("POST", "/api/tasks/{task_id}/request-changes")]
    json_routes += RUN_ROUTES  # 036 AC4
    assert len(json_routes) == 14
    for key in json_routes:
        model = found[key].response_model
        assert model is not None, key
        classes = re.findall(r"[\w.]+\.[A-Z]\w*", repr(model))  # list[…], unions, and <class '…'> alike
        assert classes, (key, model)
        assert all(c.startswith("workcell.dto.") for c in classes), (key, model)
    for key in TEXT_035:  # Q6: text, no model
        assert found[key].response_model is None, key


# --- 036: every route from controllers/ ------------------------------------------------


def test_every_route_from_controllers():  # 036 AC3, 026 AC2
    found = [r for r in routes(create_app().routes) if isinstance(r, APIRoute)]
    assert found
    for r in found:
        assert r.endpoint.__module__.startswith("workcell.controllers."), (r.path, r.endpoint.__module__)
        assert r.path.startswith("/api/"), r.path
    modules = {(m, r.path): r.endpoint.__module__ for r in found for m in r.methods}
    for key in [*RUN_ROUTES, ("POST", "/api/tasks/{task_id}/request-changes")]:
        assert modules[key].startswith("workcell.controllers."), key


# --- 026: the Jinja pages and their form posts are gone ---------------------------------

OLD_PAGES = ["/", "/workspaces/1", "/projects/1", "/projects/1/code", "/tasks/1", "/tasks/1/review",
             "/static/htmx.min.js"]
OLD_FORMS = ["/workspaces", "/projects/{p}/tasks", "/projects/{p}/workspace", "/projects/{p}/factory",
             "/tasks/{t}/approve", "/tasks/{t}/request-changes", "/tasks/{t}/comments"]
NOT_FOUND = (404, "application/json", {"detail": "Not Found"})


def json_404(r):
    return r.status_code, r.headers["content-type"], r.json()


@pytest.mark.parametrize("url", OLD_PAGES)
def test_old_pages_json_404(client, url):  # 026 AC3
    assert json_404(client.get(url)) == NOT_FOUND


def test_old_form_posts_json_404(client, project, repo):  # 026 AC4
    task = add_task(project, status="review", stage="human_review")
    add_round(task, 1)
    data = {"name": "new", "title": "x", "description_md": "x", "workspace_id": "1", "overwrite": "1",
            "body_md": "x"}

    def state():
        counts = [sql(f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("workspaces", "tasks", "decisions", "comments")]
        return counts, sorted(p for p in (repo / ".claude").rglob("*"))

    before = state()
    for path in OLD_FORMS:
        r = client.post(path.format(p=project, t=task), data=data, headers=H)
        assert r.request.headers["content-type"] == "application/x-www-form-urlencoded"
        assert json_404(r) == NOT_FOUND, path
    assert state() == before
