"""101: a factory design's fixed kind, workflow or automation (docs/data-model-and-api.md §5.1, §6.1)."""

import pytest
from conftest import sql

from .test_factories import H, created, project, put  # noqa: F401  (project is a fixture)


def post(client, project_id, body):
    return client.post(f"/api/projects/{project_id}/factories", json=body, headers=H)


def test_create_defaults_to_workflow(client, project):  # AC3
    r = post(client, project, {"name": "x"})
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "workflow"
    assert sql("SELECT kind FROM factories WHERE id = ?", (r.json()["id"],)) == [("workflow",)]


@pytest.mark.parametrize("kind", ["workflow", "automation"])
def test_create_with_kind(client, project, kind):  # AC4
    r = post(client, project, {"name": "x", "template": "security-audit", "kind": kind})
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == kind
    assert sql("SELECT kind FROM factories WHERE id = ?", (r.json()["id"],)) == [(kind,)]


@pytest.mark.parametrize("kind", ["nightly", None, 5, "Automation"])
def test_create_bad_kind(client, project, kind):  # AC5
    r = post(client, project, {"name": "x", "kind": kind})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)
    assert sql("SELECT COUNT(*) FROM factories") == [(0,)]


def test_list_has_kind_ordered_by_name(client, project):  # AC6
    b = post(client, project, {"name": "b", "kind": "automation"}).json()
    c = post(client, project, {"name": "c"}).json()
    a = post(client, project, {"name": "a", "kind": "automation"}).json()
    rows = client.get(f"/api/projects/{project}/factories").json()
    assert [(f["id"], f["kind"]) for f in rows] == [(a["id"], "automation"), (b["id"], "automation"),
                                                    (c["id"], "workflow")]


def test_get_has_kind(client, project):  # AC7
    f = post(client, project, {"name": "x", "kind": "automation"}).json()
    r = client.get(f"/api/factories/{f['id']}")
    assert (r.status_code, r.json()["kind"]) == (200, "automation")
    assert r.json() == f


@pytest.mark.parametrize("extra", [{}, {"name": "renamed"}, {"graph": None}])
def test_put_keeps_kind(client, project, extra):  # AC8, Q5
    f = post(client, project, {"name": "x", "kind": "automation"}).json()
    body = {"kind": "workflow"} | (extra if "graph" not in extra else {"graph": f["graph"]})
    if body == {"kind": "workflow"}:
        assert put(client, f["id"], body).status_code == 422  # kind alone is not a field PUT takes
    else:
        r = put(client, f["id"], body)
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "automation"
    assert sql("SELECT kind FROM factories WHERE id = ?", (f["id"],)) == [("automation",)]


def test_templates_have_kind(client):  # AC9, Q1
    r = client.get("/api/factory-templates")
    assert [(t["key"], t["kind"]) for t in r.json()] == [
        ("standard", "workflow"), ("bug-fix", "workflow"), ("security-audit", "automation"),
        ("ml-experiment", "workflow"), ("test-coverage", "automation")]
