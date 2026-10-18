import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from claude_factories.domain.errors import Conflict, NotFound, TooLarge
from claude_factories.server.app import create_app

HOST_ERROR = {"detail": "Host must be 127.0.0.1 or localhost"}
HEADER_ERROR = {"detail": "X-Requested-By: fctl header required"}


# --- Local-safety middleware -------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1:4545", "localhost:4545", "localhost", "127.0.0.1:5000"])
def test_local_hosts_allowed(client, host):  # AC18
    assert client.get("/", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "localhost.evil.example", "127.0.0.1.evil.example"])
def test_foreign_hosts_rejected(client, host):  # AC19
    r = client.get("/", headers={"Host": host})
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


def test_get_needs_no_header(client):  # AC23
    assert client.get("/").status_code == 200


# --- 034: create_app, routes, domain errors ------------------------------------------

BASE = "http://127.0.0.1:4545"


def routes(found):
    """Every route, with included routers walked into."""
    for r in found:
        if hasattr(r, "original_router"):
            yield from routes(r.original_router.routes)
        else:
            yield r


def test_moved_routes_served_from_controllers():  # 034 AC7
    modules = {(m, r.path): r.endpoint.__module__
               for r in routes(create_app().routes) for m in getattr(r, "methods", ())}
    for key in [("GET", "/api/workspaces"), ("POST", "/api/projects/connect"), ("GET", "/api/projects"),
                ("POST", "/api/projects/{project_id}/factory")]:
        assert modules[key].startswith("claude_factories.controllers."), key


@pytest.mark.parametrize("error, status, detail", [
    (NotFound("x"), 404, "x"), (NotFound(), 404, "Not Found"), (Conflict("y"), 409, "y"), (TooLarge("z"), 413, "z"),
])
def test_domain_errors_as_json(error, status, detail):  # 034 AC11
    app = create_app()

    @app.get("/api/raises")
    def raises():
        raise error

    with TestClient(app, base_url=BASE) as c:
        r = c.get("/api/raises")
    assert (r.status_code, r.json()) == (status, {"detail": detail})


def test_not_found_page_outside_api():  # 034 AC12
    app = create_app()

    @app.get("/gone")
    def gone():
        raise NotFound("Gone")

    @app.get("/gone-http")
    def gone_http():
        raise HTTPException(404, "Gone")

    with TestClient(app, base_url=BASE) as c:
        r, same = c.get("/gone"), c.get("/gone-http")
    assert r.status_code == 404
    assert r.template.name == "error.html"
    assert "<h1>Gone</h1>" in r.text
    assert (r.status_code, r.text) == (same.status_code, same.text)
