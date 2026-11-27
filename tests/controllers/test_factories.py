"""051: factory designs (docs/data-model-and-api.md §6.1)."""

import copy
import json
import re
from pathlib import Path

import pytest
from conftest import sql

from workcell.handlers.factories import preset_graph

from .test_projects import H, connect

TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "workcell" / "factory_templates" / "agents"
AGENT_IDS = ["spec-writer", "builder", "review-security", "review-ux", "review-ui", "review-code", "approver"]
OLD = "2000-01-01T00:00:00Z"


@pytest.fixture
def project(client):
    return connect(client)["id"]


def create(client, project_id, name="default", headers=H):
    return client.post(f"/api/projects/{project_id}/factories", json={"name": name}, headers=headers)


def created(client, project_id, name="default") -> dict:
    r = create(client, project_id, name)
    assert r.status_code == 201, r.text
    return r.json()


def put(client, factory_id, body, headers=H):
    return client.put(f"/api/factories/{factory_id}", json=body, headers=headers)


def row(factory_id):
    """The columns a PUT could change, with the graph parsed."""
    [(name, graph, created_at, updated_at)] = sql(
        "SELECT name, graph, created_at, updated_at FROM factories WHERE id = ?", (factory_id,))
    return name, json.loads(graph), created_at, updated_at


def stored_text(factory_id) -> str:
    return sql("SELECT graph FROM factories WHERE id = ?", (factory_id,))[0][0]


def age(factory_id):
    """Set updated_at back, so a write within the same second still shows."""
    sql("UPDATE factories SET updated_at = ? WHERE id = ?", (OLD, factory_id))


def node(graph, node_id) -> dict:
    [found] = [n for n in graph["nodes"] if n["id"] == node_id]
    return found


def edge(graph, edge_id) -> dict:
    [found] = [e for e in graph["edges"] if e["id"] == edge_id]
    return found


def size(graph) -> int:
    return len(json.dumps(graph, ensure_ascii=False, separators=(",", ":")).encode())


# --- POST /api/projects/{id}/factories ----------------------------------------------


def test_create_factory(client, project):  # BE2
    r = create(client, project, "  default ")
    assert r.status_code == 201
    f = r.json()
    [(workspace_id, workspace)] = sql("SELECT w.id, w.name FROM workspaces w JOIN projects p ON p.workspace_id = w.id"
                                      " WHERE p.id = ?", (project,))
    assert set(f) == {"id", "project_id", "project", "workspace_id", "workspace", "name", "kind", "graph",
                      "created_at", "updated_at"}
    assert (f["project_id"], f["project"], f["workspace_id"], f["workspace"], f["name"]) == (
        project, "api", workspace_id, workspace, "default")
    assert TIMESTAMP.fullmatch(f["created_at"])
    assert f["created_at"] == f["updated_at"]
    assert len(f["graph"]["nodes"]) == 10
    assert len(f["graph"]["edges"]) == 14
    assert sql("SELECT id, project_id, name, created_at, updated_at FROM factories") == [
        (f["id"], project, "default", f["created_at"], f["updated_at"])]
    assert row(f["id"])[1] == f["graph"]


def test_default_graph(client, project):  # BE3
    graph = created(client, project)["graph"]
    assert [(n["id"], n["type"]) for n in graph["nodes"]] == [
        ("start", "start"), ("spec-writer", "spec_writer"), ("builder", "builder"),
        ("review-security", "reviewer"), ("review-ux", "reviewer"), ("review-ui", "reviewer"),
        ("review-code", "reviewer"), ("all-pass", "all_pass"), ("rounds", "rounds_below"), ("approver", "approver")]
    assert node(graph, "start")["data"] == {}
    assert node(graph, "all-pass")["data"] == {}
    assert node(graph, "rounds")["data"] == {"n": 2}
    assert node(graph, "builder")["data"]["side"] == "both"
    assert [node(graph, f"review-{f}")["data"]["focus"] for f in ("security", "ux", "ui", "code")] == [
        "security", "ux", "ui", "code"]
    reviewers = ["review-security", "review-ux", "review-ui", "review-code"]
    expected = [("start", None, "spec-writer"), ("spec-writer", None, "builder"),
                *(("builder", None, r) for r in reviewers), *((r, None, "all-pass") for r in reviewers),
                ("all-pass", "yes", "approver"), ("all-pass", "no", "rounds"),
                ("rounds", "yes", "builder"), ("rounds", "no", "approver")]
    triples = [(e["source"], e["sourceHandle"], e["target"]) for e in graph["edges"]]
    assert sorted(triples, key=str) == sorted(expected, key=str)
    assert len({e["id"] for e in graph["edges"]}) == 14
    for e in graph["edges"]:
        assert set(e) == {"id", "source", "sourceHandle", "target"}
        assert (e["sourceHandle"] in ("yes", "no")) == (e["source"] in ("all-pass", "rounds"))
    positions = [(n["position"]["x"], n["position"]["y"]) for n in graph["nodes"]]
    assert len(set(positions)) == 10


def template(agent_id) -> tuple[dict, str]:
    """The test's own reading of a 011 template: its frontmatter lines and everything after the closing `---`."""
    lines = (AGENTS_DIR / f"{agent_id}.md").read_text().splitlines(keepends=True)
    assert lines[0] == "---\n"
    end = lines.index("---\n", 1)
    meta = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in lines[1:end])}
    return meta, "".join(lines[end + 1:])


def test_default_agents_from_templates(client, project):  # BE4
    graph = created(client, project)["graph"]
    for agent_id in AGENT_IDS:
        meta, prompt = template(agent_id)
        data = node(graph, agent_id)["data"]
        assert data["name"] == meta["name"] == agent_id
        assert (data["description"], data["model"]) == (meta["description"], meta["model"])
        assert data["tools"] == [t.strip() for t in meta["tools"].split(",")]
        assert data["prompt"] == prompt
        assert prompt.endswith("\n")
    builder = node(graph, "builder")["data"]
    assert builder["tools"] == ["Read", "Edit", "Write", "Grep", "Glob", "Bash"]
    assert "{{ test_cmd }}" in builder["prompt"]


def test_default_graph_round_trips(client, project):  # BE5
    f = created(client, project)
    r = put(client, f["id"], {"graph": f["graph"]})
    assert r.status_code == 200, r.text
    assert r.json()["graph"] == f["graph"]
    assert row(f["id"])[1] == f["graph"]


@pytest.mark.parametrize("body, detail", [
    ({"name": "   "}, "name must not be blank"),
    ({}, None), ({"name": None}, None), ({"name": 3}, None),
])
def test_create_factory_bad_name(client, project, body, detail):  # BE6
    r = client.post(f"/api/projects/{project}/factories", json=body, headers=H)
    assert r.status_code == 422
    if detail:
        assert r.json() == {"detail": detail}
    else:
        assert isinstance(r.json()["detail"], list)
    assert sql("SELECT COUNT(*) FROM factories") == [(0,)]


def test_create_factory_name_taken(client, project):  # BE7
    f = created(client, project)
    r = create(client, project, " default")
    assert (r.status_code, r.json()) == (409, {"detail": "factory default already exists"})
    assert sql("SELECT id FROM factories") == [(f["id"],)]
    other = connect(client, path="/code/other")["id"]
    assert create(client, other).status_code == 201
    assert sql("SELECT COUNT(*) FROM factories") == [(2,)]


def test_create_factory_unknown_project(client):  # BE8
    r = create(client, 999)
    assert (r.status_code, r.json()) == (404, {"detail": "Project #999 not found"})
    assert sql("SELECT COUNT(*) FROM factories") == [(0,)]


# --- 088: templates -------------------------------------------------------------------

TEMPLATE_KEYS = ["standard", "bug-fix", "security-audit", "ml-experiment", "test-coverage"]


def test_list_templates(client):  # 088 AC1
    r = client.get("/api/factory-templates")
    assert r.status_code == 200
    assert r.json() == [
        {"key": "standard", "name": "Standard", "description": "Spec, build, then security, UX, UI, and code reviews;"
         " up to 2 rounds; the approver decides.", "kind": "workflow"},
        {"key": "bug-fix", "name": "Bug fix", "description": "Reproduce the bug as a failing test, fix its root cause,"
         " then code and security reviews.", "kind": "workflow"},
        {"key": "security-audit", "name": "Security audit", "description": "Audit dependencies, secrets, and code;"
         " write SECURITY-AUDIT.md and fix what is safe; security review. Built for scheduled runs.",
         "kind": "automation"},
        {"key": "ml-experiment", "name": "ML experiment", "description": "Check the data and baseline, run the"
         " experiment, and gate it on eval metrics against the baseline.", "kind": "workflow"},
        {"key": "test-coverage", "name": "Test coverage", "description": "Find risky untested code and pin its"
         " behavior with tests, leaving production code unchanged.", "kind": "automation"},
    ]
    assert all(t["description"].strip() and "\n" not in t["description"] for t in r.json())


@pytest.mark.parametrize("key", TEMPLATE_KEYS)
def test_create_from_template(client, project, key):  # 088 AC10
    r = client.post(f"/api/projects/{project}/factories", json={"name": "x", "template": key}, headers=H)
    assert r.status_code == 201, r.text
    expected = preset_graph(key).model_dump()
    assert r.json()["graph"] == expected
    assert row(r.json()["id"])[1] == expected


@pytest.mark.parametrize("body", [{"name": "x"}, {"name": "x", "template": None}])
def test_create_without_template(client, project, body):  # 088 AC11
    r = client.post(f"/api/projects/{project}/factories", json=body, headers=H)
    assert r.status_code == 201, r.text
    standard = client.post(f"/api/projects/{project}/factories", json={"name": "y", "template": "standard"},
                           headers=H).json()["graph"]
    assert r.json()["graph"] == standard
    assert len(standard["nodes"]) == 10


def test_create_unknown_template(client, project):  # 088 AC12
    unknown = (422, {"detail": "unknown template nightly: use standard, bug-fix, security-audit, ml-experiment,"
                               " or test-coverage"})
    r = client.post(f"/api/projects/{project}/factories", json={"name": "x", "template": "nightly"}, headers=H)
    assert (r.status_code, r.json()) == unknown
    assert sql("SELECT COUNT(*) FROM factories") == [(0,)]
    r = client.post(f"/api/projects/{project}/factories", json={"name": " ", "template": "nightly"}, headers=H)
    assert (r.status_code, r.json()) == (422, {"detail": "name must not be blank"})
    r = client.post("/api/projects/999/factories", json={"name": "x", "template": "nightly"}, headers=H)
    assert (r.status_code, r.json()) == unknown
    created(client, project, "x")
    r = client.post(f"/api/projects/{project}/factories", json={"name": "x", "template": "nightly"}, headers=H)
    assert (r.status_code, r.json()) == unknown
    assert sql("SELECT COUNT(*) FROM factories") == [(1,)]


def test_create_template_not_a_string(client, project):  # 088 AC13
    r = client.post(f"/api/projects/{project}/factories", json={"name": "x", "template": 5}, headers=H)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)
    assert sql("SELECT COUNT(*) FROM factories") == [(0,)]


# --- GET /api/projects/{id}/factories, GET /api/factories/{id} ---------------------


def test_list_factories(client, project):  # BE9
    assert (r := client.get(f"/api/projects/{project}/factories")).status_code == 200
    assert r.json() == []
    other = connect(client, path="/code/other")["id"]
    created(client, other, "aaa")
    nightly = created(client, project, "nightly")
    default = created(client, project, "default")
    beta = created(client, project, "Beta")
    r = client.get(f"/api/projects/{project}/factories")
    assert r.status_code == 200
    assert r.json() == [{"id": f["id"], "name": f["name"], "kind": "workflow", "nodes": 10,
                         "created_at": f["created_at"], "updated_at": f["updated_at"]}
                        for f in (beta, default, nightly)]  # SQLite's BINARY order
    r = client.get("/api/projects/999/factories")
    assert (r.status_code, r.json()) == (404, {"detail": "Project #999 not found"})


def test_get_factory(client, project):  # BE10
    f = created(client, project)
    r = client.get(f"/api/factories/{f['id']}")
    assert (r.status_code, r.json()) == (200, f)
    r = client.get("/api/factories/999")
    assert (r.status_code, r.json()) == (404, {"detail": "Factory #999 not found"})


# --- PUT /api/factories/{id} --------------------------------------------------------


def custom(node_id="custom-1", name="linter", **position) -> dict:
    return {"id": node_id, "type": "custom_agent", "position": {"x": 1200.5, "y": 600.0} | position,
            "data": {"name": name, "description": "Lints.", "model": "haiku", "tools": ["Read", "Bash"],
                     "prompt": "Run the linter.\n"}}


def test_save_graph(client, project):  # BE11
    f = created(client, project)
    graph = copy.deepcopy(f["graph"])
    node(graph, "builder")["position"] = {"x": 640.25, "y": -80.0}
    graph["nodes"].append(custom())
    graph["edges"].append({"id": "e15", "source": "all-pass", "sourceHandle": "no", "target": "custom-1"})
    age(f["id"])
    r = put(client, f["id"], {"graph": graph})
    assert r.status_code == 200, r.text
    assert r.json()["graph"] == graph
    after = client.get(f"/api/factories/{f['id']}").json()
    assert after["graph"] == graph
    assert after["name"] == "default"
    assert after["created_at"] == f["created_at"]
    assert TIMESTAMP.fullmatch(after["updated_at"])
    assert after["updated_at"] > OLD
    assert client.get(f"/api/projects/{project}/factories").json()[0]["nodes"] == 11


def test_save_drops_unknown_keys(client, project):  # BE12
    f = created(client, project)
    sent = copy.deepcopy(f["graph"])
    for n in sent["nodes"]:
        n |= {"selected": True, "measured": {"width": 200, "height": 80}, "dragging": False}
    node(sent, "builder")["data"]["label"] = "Builder"
    for e in sent["edges"]:
        e |= {"type": "deletable", "animated": True, "targetHandle": None}
    del edge(sent, "e1")["sourceHandle"]
    r = put(client, f["id"], {"graph": sent})
    assert r.status_code == 200, r.text
    assert r.json()["graph"] == f["graph"]
    assert edge(r.json()["graph"], "e1")["sourceHandle"] is None
    assert row(f["id"])[1] == f["graph"]
    text = stored_text(f["id"])
    for key in ("selected", "measured", "dragging", "label", "animated", "targetHandle"):
        assert f'"{key}":' not in text
    assert '"type":"deletable"' not in text


def test_rename_factory(client, project):  # BE13
    f = created(client, project)
    sibling = created(client, project, "weekly")
    other = connect(client, path="/code/other")["id"]
    created(client, other, "monthly")
    r = put(client, f["id"], {"name": "  nightly "})
    assert r.status_code == 200
    assert r.json() | {"updated_at": None} == f | {"name": "nightly", "updated_at": None}
    assert row(f["id"])[:2] == ("nightly", f["graph"])
    assert put(client, f["id"], {"name": "nightly"}).status_code == 200
    r = put(client, f["id"], {"name": "weekly"})
    assert (r.status_code, r.json()) == (409, {"detail": "factory weekly already exists"})
    r = put(client, f["id"], {"name": "  "})
    assert (r.status_code, r.json()) == (422, {"detail": "name must not be blank"})
    r = put(client, f["id"], {"name": "monthly"})  # only another project has it
    assert (r.status_code, r.json()["name"]) == (200, "monthly")
    assert row(sibling["id"])[0] == "weekly"


@pytest.mark.parametrize("body, detail", [
    ({}, "send at least one of: name, graph"),
    ({"foo": 1}, "send at least one of: name, graph"),
    ({"name": None}, None),
    ({"graph": None}, None),
])
def test_put_nothing_or_null(client, project, body, detail):  # BE14
    f = created(client, project)
    r = put(client, f["id"], body)
    assert r.status_code == 422
    if detail:
        assert r.json() == {"detail": detail}
    else:
        assert isinstance(r.json()["detail"], list)


def drop_prompt(g):
    del node(g, "approver")["data"]["prompt"]


def drop_id(g):
    del node(g, "approver")["id"]


SHAPE_ERRORS = {
    "unknown type": lambda g: node(g, "approver").update(type="judge"),
    "model gpt": lambda g: node(g, "builder")["data"].update(model="gpt"),
    "side all": lambda g: node(g, "builder")["data"].update(side="all"),
    "focus perf": lambda g: node(g, "review-ux")["data"].update(focus="perf"),
    "n 0": lambda g: node(g, "rounds")["data"].update(n=0),
    "n 1.5": lambda g: node(g, "rounds")["data"].update(n=1.5),
    "no prompt": drop_prompt,
    "no id": drop_id,
    "x string": lambda g: node(g, "start")["position"].update(x="5"),
}


@pytest.mark.parametrize("mutate", SHAPE_ERRORS.values(), ids=SHAPE_ERRORS.keys())
def test_graph_shape_errors(client, project, mutate):  # BE15
    f = created(client, project)
    graph = copy.deepcopy(f["graph"])
    mutate(graph)
    r = put(client, f["id"], {"graph": graph})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_graph_non_finite_position(client, project, value):  # BE15: a raw body with NaN or Infinity
    f = created(client, project)
    graph = copy.deepcopy(f["graph"])
    node(graph, "start")["position"]["x"] = value
    text = json.dumps({"graph": graph})
    assert ("NaN" if value != value else "Infinity") in text
    r = client.put(f"/api/factories/{f['id']}", content=text, headers=H | {"Content-Type": "application/json"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def add_start(g):
    g["nodes"].append({"id": "start-2", "type": "start", "position": {"x": 0, "y": 600}, "data": {}})


def drop_start(g):
    g["nodes"] = [n for n in g["nodes"] if n["type"] != "start"]


RULES = {
    "0 starts": (drop_start, "graph needs exactly one start node, not 0"),
    "2 starts": (add_start, "graph needs exactly one start node, not 2"),
    "node id": (lambda g: g["nodes"].append(custom("builder", "linter")), "two nodes have id builder"),
    "edge id": (lambda g: g["edges"].append({"id": "e3", "source": "start", "target": "builder"}),
                "two edges have id e3"),
    "slug": (lambda g: node(g, "spec-writer")["data"].update(name="Spec Writer"),
             'agent name "Spec Writer" must be a slug: a-z, 0-9, and single hyphens'),
    "agent name": (lambda g: node(g, "approver")["data"].update(name="builder"), "two agents are named builder"),
    "source": (lambda g: edge(g, "e3").update(source="x9"), "edge e3 starts at no node x9"),
    "target": (lambda g: edge(g, "e3").update(target="x9"), "edge e3 ends at no node x9"),
    "into start": (lambda g: edge(g, "e3").update(target="start"), "edge e3 leads into start, which takes no input"),
    "handle maybe": (lambda g: edge(g, "e11").update(sourceHandle="maybe"),
                     "edge e11 leaves condition all-pass from neither yes nor no"),
    "handle null": (lambda g: edge(g, "e11").update(sourceHandle=None),
                    "edge e11 leaves condition all-pass from neither yes nor no"),
    "agent handle": (lambda g: edge(g, "e3").update(sourceHandle="yes"),
                     "edge e3 leaves builder from handle yes, but only conditions have handles"),
}


@pytest.mark.parametrize("mutate, detail", RULES.values(), ids=RULES.keys())
def test_graph_rules(client, project, mutate, detail):  # BE16
    f = created(client, project)
    graph = copy.deepcopy(f["graph"])
    mutate(graph)
    r = put(client, f["id"], {"graph": graph})
    assert (r.status_code, r.json()) == (422, {"detail": detail})


def test_graph_size_limit(client, project):  # BE17
    f = created(client, project)
    graph = copy.deepcopy(f["graph"])
    node(graph, "approver")["data"]["prompt"] += "x" * (262144 - size(graph))
    assert size(graph) == 262144
    r = put(client, f["id"], {"graph": graph})
    assert r.status_code == 200, r.text
    assert len(stored_text(f["id"]).encode()) == 262144
    node(graph, "approver")["data"]["prompt"] += "x"
    r = put(client, f["id"], {"graph": graph})
    assert (r.status_code, r.json()) == (422, {"detail": "graph over 256 KB"})


def test_refused_put_writes_nothing(client, project):  # BE18
    f = created(client, project)
    created(client, project, "weekly")
    age(f["id"])
    before = row(f["id"])
    bad_rule, bad_shape, too_big = (copy.deepcopy(f["graph"]) for _ in range(3))
    RULES["agent name"][0](bad_rule)
    SHAPE_ERRORS["model gpt"](bad_shape)
    node(too_big, "approver")["data"]["prompt"] += "x" * 262144
    for body, status in [({"name": "weekly"}, 409), ({"name": " "}, 422), ({"graph": bad_rule}, 422),
                         ({"graph": bad_shape}, 422), ({"graph": too_big}, 422),
                         ({"name": "renamed", "graph": bad_rule}, 422),
                         ({"name": "weekly", "graph": f["graph"]}, 409), ({}, 422), ({"name": None}, 422)]:
        assert put(client, f["id"], body).status_code == status, body
        assert row(f["id"]) == before


def test_put_unknown_factory(client, project):  # BE19
    graph = created(client, project)["graph"]
    for body in ({"name": "x"}, {"graph": graph}):
        r = put(client, 999, body)
        assert (r.status_code, r.json()) == (404, {"detail": "Factory #999 not found"})


# --- DELETE --------------------------------------------------------------------------


def test_delete_factory(client, project):  # BE20
    f = created(client, project)
    kept = created(client, project, "weekly")
    r = client.delete(f"/api/factories/{f['id']}", headers=H)
    assert (r.status_code, r.content) == (204, b"")
    assert client.get(f"/api/factories/{f['id']}").status_code == 404
    assert [i["id"] for i in client.get(f"/api/projects/{project}/factories").json()] == [kept["id"]]
    r = client.delete("/api/factories/999", headers=H)
    assert (r.status_code, r.json()) == (404, {"detail": "Factory #999 not found"})


def test_delete_project_removes_factories(client, project):  # BE21
    created(client, project)
    created(client, project, "weekly")
    other = connect(client, path="/code/other")["id"]
    kept = created(client, other)
    assert client.delete(f"/api/projects/{project}", headers=H).status_code == 204
    assert sql("SELECT id, project_id FROM factories") == [(kept["id"], other)]


def test_mutations_need_fctl_header(client, project):  # BE22
    f = created(client, project)
    before = row(f["id"])
    forbidden = (403, {"detail": "X-Requested-By: fctl header required"})
    r = create(client, project, "nightly", headers={})
    assert (r.status_code, r.json()) == forbidden
    r = put(client, f["id"], {"name": "nightly"}, headers={})
    assert (r.status_code, r.json()) == forbidden
    r = client.delete(f"/api/factories/{f['id']}", headers={})
    assert (r.status_code, r.json()) == forbidden
    assert sql("SELECT id FROM factories") == [(f["id"],)]
    assert row(f["id"]) == before
