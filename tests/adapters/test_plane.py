"""109: adapters/plane.Plane against conftest's FakePlane on a local http.server: pagination, the `issues/`
fallback, the X-API-Key header, and each status mapping (AC6, AC7, AC12)."""

import socket

import pytest
from conftest import PLANE_KEY, plane_item

from workcell.adapters import plane as adapter
from workcell.adapters.plane import Plane
from workcell.domain.errors import Conflict, Failed

BASE = "/api/v1/workspaces/acme/projects/p-1/"


def test_items_follow_cursor_pages(plane):  # AC6
    plane.items = [plane_item(n) for n in range(1, 6)]
    got = Plane().items(plane.url, PLANE_KEY, "acme", "p-1")
    assert [i["id"] for i in got] == [f"item-{n}" for n in range(1, 6)]
    assert [r["query"] for r in plane.requests] == [
        {"per_page": ["100"]}, {"per_page": ["100"], "cursor": ["2:1:0"]}, {"per_page": ["100"], "cursor": ["2:2:0"]}]
    assert {r["path"] for r in plane.requests} == {BASE + "work-items/"}
    assert {r["key"] for r in plane.requests} == {PLANE_KEY}


def test_page_cap(plane, monkeypatch):  # Q4
    monkeypatch.setattr(adapter, "PAGES", 2)
    plane.items = [plane_item(n) for n in range(1, 6)]
    assert len(Plane().items(plane.url, PLANE_KEY, "acme", "p-1")) == 4


def test_items_fall_back_to_issues(plane):  # AC7
    plane.old = True
    plane.items = [plane_item(1)]
    assert [i["id"] for i in Plane().items(plane.url, PLANE_KEY, "acme", "p-1")] == ["item-1"]
    assert [r["path"] for r in plane.requests] == [BASE + "work-items/", BASE + "issues/"]


def test_project_and_states(plane):  # AC6
    p = Plane()
    assert p.project(plane.url, PLANE_KEY, "acme", "p-1")["identifier"] == "ENG"
    assert len(p.states(plane.url, PLANE_KEY, "acme", "p-1")) == len(plane.states)
    assert plane.requests[0]["path"] == BASE


def test_set_state_patches(plane):  # AC13
    Plane().set_state(plane.url, PLANE_KEY, "acme", "p-1", "item-7", "s-d")
    assert [(r["method"], r["path"], r["body"], r["key"]) for r in plane.requests] == [
        ("PATCH", BASE + "work-items/item-7/", {"state": "s-d"}, PLANE_KEY)]


def test_set_state_falls_back(plane):  # AC7's fallback for the PATCH
    plane.old = True
    Plane().set_state(plane.url, PLANE_KEY, "acme", "p-1", "item-7", "s-d")
    assert [r["path"] for r in plane.requests] == [BASE + "work-items/item-7/", BASE + "issues/item-7/"]


@pytest.mark.parametrize("status, kind, detail", [
    (401, Conflict, "Plane refused the API key: check it in project Settings"),
    (403, Conflict, "Plane refused the API key: check it in project Settings"),
    (429, Conflict, "Plane's rate limit was hit: try again in a minute"),
    (500, Failed, f"Plane answered 500 to {BASE}"),
    (302, Failed, f"Plane answered 302 to {BASE}"),
    ("html", Failed, f"Plane answered 200 to {BASE}"),
])
def test_status_mapping(plane, status, kind, detail):  # AC12
    plane.fail[""] = status
    with pytest.raises(kind) as e:
        Plane().project(plane.url, PLANE_KEY, "acme", "p-1")
    assert e.value.detail == detail and PLANE_KEY not in e.value.detail


def test_unknown_project(plane):  # AC12
    with pytest.raises(Conflict) as e:
        Plane().project(plane.url, PLANE_KEY, "acme", "nope")
    assert e.value.detail == "Plane has no workspace acme or project nope: check them in project Settings"


def unused_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable():  # AC12
    url = f"http://127.0.0.1:{unused_port()}"
    with pytest.raises(Conflict) as e:
        Plane().project(url, PLANE_KEY, "acme", "p-1")
    assert e.value.detail == f"can't reach {url}: check the API URL in project Settings"


def test_timeout(plane, monkeypatch):  # AC12
    monkeypatch.setattr(adapter, "TIMEOUT", 0.2)
    plane.fail[""] = "slow"
    with pytest.raises(Conflict) as e:
        Plane().project(plane.url, PLANE_KEY, "acme", "p-1")
    assert e.value.detail == f"can't reach {plane.url}: check the API URL in project Settings"
