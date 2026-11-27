"""013: a run's stream-json log → display items, its last `result` event, and (053) its agents. No app, no
database."""

import json
from collections.abc import Iterable

from .transcript import ROUND

LOG_NAME_KEYS = ("name", "subagent_type")  # 013 Q8: what an Agent spawn is called
LOG_SUMMARY_KEYS = ("command", "file_path", "pattern", "name", "subagent_type", "description")  # Q7


def first_string(d: dict, keys: tuple) -> str | None:
    return next((v for k in keys if isinstance(v := d.get(k), str) and v), None)


def parse(line: str):
    """A line's JSON value, or None for stderr and anything else that isn't JSON."""
    try:
        return json.loads(line)
    except (ValueError, RecursionError):  # RecursionError: a line nested past the parser's limit
        return None


def blocks(event: dict) -> list[dict]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def first_line(text: str) -> str:
    return (text.splitlines() or [""])[0]


def tool_text(block: dict) -> str:
    """Q7: a tool_use block (with a string `name`) as a tool line, without the `<who> · ` prefix (053 Q2)."""
    inp = block.get("input")
    summary = first_line(first_string(inp, LOG_SUMMARY_KEYS) or "") if isinstance(inp, dict) else ""
    return block["name"] + (f" {summary}" if summary else "")


def last_result(lines: Iterable[str]) -> dict | None:
    """012 Q10: the last `result` event among the lines, skipping any that aren't a JSON object."""
    event = None
    for line in lines:
        parsed = parse(line)
        if isinstance(parsed, dict) and parsed.get("type") == "result":
            event = parsed
    return event


def log_items(lines: list[str], after: int) -> list[dict]:
    """013 Q7, Q8: stream-json lines → display items for lines[after:]. Agent names come from every
    tool_use in `lines`, so a subagent still resolves when its spawn is before `after`."""
    events = [parse(line) for line in lines]
    names = {}
    for e in events:
        if isinstance(e, dict) and e.get("type") == "assistant":
            for b in blocks(e):
                inp = b.get("input")
                if b.get("type") == "tool_use" and isinstance(b.get("id"), str) and isinstance(inp, dict):
                    if name := first_string(inp, LOG_NAME_KEYS):
                        names[b["id"]] = name
    items = []
    for line, e in zip(lines[after:], events[after:]):
        if not isinstance(e, dict):
            if line.strip():
                items.append({"t": "raw", "text": line.removesuffix("\r")})
            continue
        parent = e.get("parent_tool_use_id")
        who = "orchestrator" if parent is None else names.get(parent, "agent") if isinstance(parent, str) else "agent"
        if e.get("type") == "assistant":
            for b in blocks(e):
                if b.get("type") == "text" and isinstance(b.get("text"), str) and b["text"].strip():
                    items.append({"t": "text", "text": f"{who} · {b['text'].strip()}"})
                elif b.get("type") == "tool_use" and isinstance(b.get("name"), str):
                    items.append({"t": "tool", "text": f"{who} · {tool_text(b)}"})
        elif e.get("type") == "user":
            for b in blocks(e):
                if b.get("type") != "tool_result" or b.get("is_error") is not True:
                    continue
                content = b.get("content")
                if isinstance(content, list):
                    content = "\n".join(i["text"] for i in content
                                        if isinstance(i, dict) and isinstance(i.get("text"), str))
                if isinstance(content, str):  # §4.4: how permission denials show up
                    items.append({"t": "error", "text": f"{who} · {first_line(content)}"})
        elif e.get("type") == "result":
            text = e.get("result") if isinstance(e.get("result"), str) else e.get("subtype")
            if isinstance(text, str):
                items.append({"t": "result", "text": text})
    return items


def run_agents(lines: list[str]) -> list[dict]:
    """053: the orchestrator, then one entry per `Agent` tool_use in log order (Q10). An entry runs until a
    tool_result answers its id; its duration is that line's int `tool_use_result.totalDurationMs` (Q1), and its
    last_tool is its latest own tool line, from lines whose parent_tool_use_id is its id (Q2). The orchestrator
    always runs (Q12) and owns the lines with no parent. Skips any line that isn't a JSON object."""
    def entry(name, kind=None, n=None):
        return {"name": name, "type": kind, "round": n, "running": True, "duration_ms": None, "last_tool": None}

    orchestrator, agents = entry("orchestrator"), {}
    for e in map(parse, lines):
        if not isinstance(e, dict):
            continue
        if e.get("type") == "assistant":
            parent = e.get("parent_tool_use_id")
            owner = orchestrator if parent is None else agents.get(parent) if isinstance(parent, str) else None
            for b in blocks(e):
                if b.get("type") != "tool_use" or not isinstance(b.get("name"), str):
                    continue
                if owner:
                    owner["last_tool"] = tool_text(b)
                inp = b.get("input")
                if b["name"] == "Agent" and isinstance(b.get("id"), str) and isinstance(inp, dict):
                    found = ROUND.search(inp["prompt"]) if isinstance(inp.get("prompt"), str) else None
                    agents[b["id"]] = entry(first_string(inp, LOG_NAME_KEYS) or "agent",
                                            first_string(inp, ("subagent_type",)), found and int(found[1]))
        elif e.get("type") == "user":
            result = e.get("tool_use_result")
            ms = result.get("totalDurationMs") if isinstance(result, dict) else None
            for b in blocks(e):
                tool_id = b.get("tool_use_id")
                if b.get("type") == "tool_result" and isinstance(tool_id, str) and tool_id in agents:
                    agents[tool_id] |= {"running": False,
                                        "duration_ms": ms if type(ms) is int else None}  # not a bool
    return [orchestrator, *agents.values()]
