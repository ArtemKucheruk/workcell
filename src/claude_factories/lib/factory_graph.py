"""051: a factory graph's rules (docs/data-model-and-api.md §6.1) and the agent templates' frontmatter. Pure."""

import json
import re

from ..domain.errors import Invalid

AGENTS = {"spec_writer", "builder", "reviewer", "approver", "custom_agent"}
CONDITIONS = {"all_pass", "any_changes", "rounds_below", "approved"}
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def first_repeat(values: list[str]) -> str | None:
    seen = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def check(graph: dict, max_bytes: int) -> str:
    """Rules 1–6 in order on a graph that already has §6.1's shape (Graph.model_dump()); the first that fails
    raises Invalid with its detail. Returns the compact JSON that rule 1 measured, which is what gets stored."""
    text = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode()) > max_bytes:
        raise Invalid(f"graph over {max_bytes // 1024} KB")
    starts = sum(node["type"] == "start" for node in graph["nodes"])
    if starts != 1:
        raise Invalid(f"graph needs exactly one start node, not {starts}")
    for kind, items in (("nodes", graph["nodes"]), ("edges", graph["edges"])):
        if (repeat := first_repeat([item["id"] for item in items])) is not None:
            raise Invalid(f"two {kind} have id {repeat}")
    names = [node["data"]["name"] for node in graph["nodes"] if node["type"] in AGENTS]
    for name in names:
        if not SLUG.fullmatch(name):
            raise Invalid(f'agent name "{name}" must be a slug: a-z, 0-9, and single hyphens')
    if (repeat := first_repeat(names)) is not None:
        raise Invalid(f"two agents are named {repeat}")
    nodes = {node["id"]: node for node in graph["nodes"]}  # unique ids, by rule 3
    for edge in graph["edges"]:
        source, target, handle = nodes.get(edge["source"]), nodes.get(edge["target"]), edge["sourceHandle"]
        if source is None:
            raise Invalid(f"edge {edge['id']} starts at no node {edge['source']}")
        if target is None:
            raise Invalid(f"edge {edge['id']} ends at no node {edge['target']}")
        if target["type"] == "start":
            raise Invalid(f"edge {edge['id']} leads into start, which takes no input")
        if source["type"] in CONDITIONS and handle not in ("yes", "no"):
            raise Invalid(f"edge {edge['id']} leaves condition {source['id']} from neither yes nor no")
        if source["type"] not in CONDITIONS and handle is not None:
            raise Invalid(f"edge {edge['id']} leaves {source['id']} from handle {handle},"
                          " but only conditions have handles")
    return text


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    """An agent template's (`key: value` frontmatter, body): the body is everything after the closing `---` line,
    unchanged. ponytail: flat one-line values only, which is all the 011 templates hold."""
    head, _, body = text.removeprefix("---\n").partition("\n---\n")
    meta = dict(line.split(":", 1) for line in head.splitlines())
    return {key.strip(): value.strip() for key, value in meta.items()}, body
