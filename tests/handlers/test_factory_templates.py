"""088: + New factory's templates (docs/data-model-and-api.md §6.1, docs/claude-code.md §7.3), on the handler."""

import re

import pytest
from controllers.test_factories import template

from claude_factories import config
from claude_factories.handlers.factories import PRESETS, default_graph, preset_graph
from claude_factories.handlers.factory import TEMPLATES
from claude_factories.lib.factory_compile import compile_files
from claude_factories.lib.factory_graph import AGENTS, SLUG, check

KEYS = ["standard", "bug-fix", "security-audit", "ml-experiment", "test-coverage"]
NEW_AGENTS = ["bug-spec-writer", "security-auditor", "data-check", "review-eval", "coverage-planner", "review-tests"]
SKILL = (TEMPLATES / "skills" / "factory" / "SKILL.md").read_text(encoding="utf-8")
VALUES = {"name": "api-server", "default_branch": "main", "test_cmd": "make check"}
TAIL = ["any-changes yes>rounds", "any-changes no>approver", "rounds yes>builder", "rounds no>approver"]
# the spec's Templates section: (id, type, side/focus/n) per node, then "source[ handle]>target" per edge, in order
SHAPES = {
    "bug-fix": (
        [("start", "start", {}), ("bug-spec-writer", "spec_writer", {}), ("builder", "builder", {"side": "both"}),
         ("review-code", "reviewer", {"focus": "code"}), ("review-security", "reviewer", {"focus": "security"}),
         ("any-changes", "any_changes", {}), ("rounds", "rounds_below", {"n": 2}), ("approver", "approver", {})],
        ["start>bug-spec-writer", "bug-spec-writer>builder", "builder>review-code", "builder>review-security",
         "review-code>any-changes", "review-security>any-changes", *TAIL]),
    "security-audit": (
        [("start", "start", {}), ("security-auditor", "spec_writer", {}), ("builder", "builder", {"side": "both"}),
         ("review-security", "reviewer", {"focus": "security"}), ("any-changes", "any_changes", {}),
         ("rounds", "rounds_below", {"n": 2}), ("approver", "approver", {})],
        ["start>security-auditor", "security-auditor>builder", "builder>review-security",
         "review-security>any-changes", *TAIL]),
    "ml-experiment": (
        [("start", "start", {}), ("data-check", "spec_writer", {}), ("builder", "builder", {"side": "both"}),
         ("review-eval", "reviewer", {"focus": "custom"}), ("any-changes", "any_changes", {}),
         ("rounds", "rounds_below", {"n": 3}), ("approver", "approver", {})],
        ["start>data-check", "data-check>builder", "builder>review-eval", "review-eval>any-changes", *TAIL]),
    "test-coverage": (
        [("start", "start", {}), ("coverage-planner", "spec_writer", {}), ("builder", "builder", {"side": "both"}),
         ("review-tests", "reviewer", {"focus": "custom"}), ("any-changes", "any_changes", {}),
         ("rounds", "rounds_below", {"n": 2}), ("approver", "approver", {})],
        ["start>coverage-planner", "coverage-planner>builder", "builder>review-tests", "review-tests>any-changes",
         *TAIL]),
}


def graph(key) -> dict:
    return preset_graph(key).model_dump()


def agents(g) -> list[dict]:
    return [n for n in g["nodes"] if n["type"] in AGENTS]


def test_template_keys():  # AC1's list, on the table
    assert list(PRESETS) == KEYS


@pytest.mark.parametrize("key", KEYS)
def test_template_checks_and_compiles(key):  # AC2
    g = graph(key)
    check(g, config.MAX_GRAPH)
    files = compile_files(g, SKILL, VALUES, "factory")
    assert [path for path, _ in files] == [
        ".claude/skills/factory/SKILL.md", *(f".claude/agents/{n['data']['name']}.md" for n in agents(g))]


@pytest.mark.parametrize("key", KEYS)
def test_template_agent_names(key):  # AC3
    names = [n["data"]["name"] for n in agents(graph(key))]
    assert all(SLUG.fullmatch(name) for name in names)
    assert len(set(names)) == len(names)
    assert all(n["id"] == n["data"]["name"] for n in agents(graph(key)))


@pytest.mark.parametrize("key", SHAPES)
def test_template_shape(key):  # AC4
    nodes, edges = SHAPES[key]
    g = graph(key)
    assert [(n["id"], n["type"], {k: n["data"][k] for k in ("side", "focus", "n") if k in n["data"]})
            for n in g["nodes"]] == nodes
    assert [f"{e['source']}{' ' + e['sourceHandle'] if e['sourceHandle'] else ''}>{e['target']}"
            for e in g["edges"]] == edges
    assert [e["id"] for e in g["edges"]] == [f"e{i}" for i in range(1, len(edges) + 1)]
    positions = [(n["position"]["x"], n["position"]["y"]) for n in g["nodes"]]
    assert len(set(positions)) == len(positions)
    assert [x for x, _ in positions] == sorted(x for x, _ in positions)  # left to right, 300 apart
    assert {x for x, _ in positions} == set(range(0, 1801, 300))


def test_standard_is_default():  # AC5
    assert preset_graph("standard") == default_graph()


@pytest.mark.parametrize("name", NEW_AGENTS)
def test_new_agents_from_files(name):  # AC6
    meta, prompt = template(name)
    [data] = [n["data"] for key in KEYS for n in agents(graph(key)) if n["id"] == name]
    assert data["name"] == meta["name"] == name
    assert (data["description"], data["model"]) == (meta["description"], meta["model"])
    assert data["tools"] == [t.strip() for t in meta["tools"].split(",")] == ["Read", "Grep", "Glob", "Bash"]
    assert data["prompt"] == prompt
    assert prompt.endswith("Do not edit code. Write nothing else.\n")
    assert "## Project context" in prompt
    assert ": " not in meta["description"]  # 011's unquoted frontmatter stays valid YAML


def test_shared_names_have_same_data():  # AC7
    seen = {}
    for key in KEYS:
        for n in agents(graph(key)):
            assert seen.setdefault(n["id"], n["data"]) == n["data"], (key, n["id"])
    assert len(seen) == 7 + len(NEW_AGENTS)


@pytest.mark.parametrize("key", KEYS)
def test_verdict_slots_and_spec(key):  # AC8
    slots = []
    for n in agents(graph(key)):
        if n["type"] == "reviewer":
            [slot] = re.findall(r"fctl verdict <id> (\w+)", n["data"]["prompt"])
            slots.append(slot)
        elif n["type"] == "spec_writer":
            assert "fctl spec <id>" in n["data"]["prompt"]
    assert set(slots) <= {"security", "ux", "ui", "code"}
    assert len(set(slots)) == len(slots)


@pytest.mark.parametrize("key", KEYS)
def test_fewer_reviewers_branch_on_any_changes(key):  # AC9
    types = [n["type"] for n in graph(key)["nodes"]]
    if types.count("reviewer") < 4:
        assert "all_pass" not in types
        assert "any_changes" in types
