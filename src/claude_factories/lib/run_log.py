"""013: a run's stream-json log → display items, and its last `result` event. No app, no database."""

import json
from collections.abc import Iterable

LOG_NAME_KEYS = ("name", "subagent_type")  # 013 Q8: what an Agent spawn is called
LOG_SUMMARY_KEYS = ("command", "file_path", "pattern", "name", "subagent_type", "description")  # Q7


def first_string(d: dict, keys: tuple) -> str | None:
    return next((v for k in keys if isinstance(v := d.get(k), str) and v), None)


def last_result(lines: Iterable[str]) -> dict | None:
    """012 Q10: the last `result` event among the lines, skipping any that aren't a JSON object."""
    event = None
    for line in lines:
        try:
            parsed = json.loads(line)
        except (ValueError, RecursionError):  # stderr and anything else that isn't JSON
            continue
        if isinstance(parsed, dict) and parsed.get("type") == "result":
            event = parsed
    return event


def log_items(lines: list[str], after: int) -> list[dict]:
    """013 Q7, Q8: stream-json lines → display items for lines[after:]. Agent names come from every
    tool_use in `lines`, so a subagent still resolves when its spawn is before `after`."""
    def blocks(event: dict) -> list[dict]:
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []

    def first_line(text: str) -> str:
        return (text.splitlines() or [""])[0]

    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except (ValueError, RecursionError):  # stderr, or a line nested past the parser's limit
            events.append(None)
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
                    inp = b.get("input")
                    summary = first_line(first_string(inp, LOG_SUMMARY_KEYS) or "") if isinstance(inp, dict) else ""
                    items.append({"t": "tool", "text": f"{who} · {b['name']}" + (f" {summary}" if summary else "")})
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
