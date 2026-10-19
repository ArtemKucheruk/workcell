"""030: Claude Code transcripts (.jsonl) → their project folder name, a per-file summary, teammate agent types,
and display messages. No app, no database."""

import json
import os
import re

from .markdown import render

ROUND = re.compile(r"(?:Job|Task) \S+, round (\d{1,9})\.")  # Q3
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
CUT = 4096  # Q9: characters of a tool result without ?full=1


def folder_name(worktree: str) -> str:
    """Q1: the folder under `<config>/projects/` holding sessions whose cwd is `worktree`."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(worktree))


def events(data: bytes) -> list[dict]:
    """A .jsonl's lines as dicts, skipping any that aren't a JSON object. Split on \\n only: JSON strings may
    hold U+2028, which str.splitlines() would split on."""
    found = []
    for line in data.decode("utf-8", errors="replace").split("\n"):
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(event, dict):
            found.append(event)
    return found


def message(event: dict) -> dict:
    m = event.get("message")
    return m if isinstance(m, dict) else {}


def blocks(event: dict) -> list[dict]:
    """A line's content blocks; Q10: a string content is one text block."""
    content = message(event).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def first_prompt(evts: list[dict]) -> str:
    """The first user message's text blocks joined with newlines; "" without one."""
    first = next((e for e in evts if e.get("type") == "user"), {})
    return "\n".join(b["text"] for b in blocks(first) if b.get("type") == "text" and isinstance(b.get("text"), str))


def first_round(evts: list[dict]) -> int | None:
    """Q3: n from `Job|Task <id>, round <n>.` anywhere in the first user message, else None."""
    found = ROUND.search(first_prompt(evts))
    return int(found[1]) if found else None


def summary(evts: list[dict]) -> dict:
    """Q5, Q6: round, model, turns, the three token sums, the first and last time, and the first teamName line's
    teamName and agentName (Q2)."""
    usage, model = {}, None
    for e in evts:
        if e.get("type") != "assistant":
            continue
        m = message(e)
        if model is None and isinstance(m.get("model"), str) and m["model"] != "<synthetic>":
            model = m["model"]
        if isinstance(m.get("id"), str):  # one API message spans lines with repeated usage: its last line counts
            usage[m["id"]] = m["usage"] if isinstance(m.get("usage"), dict) else {}

    def total(key: str) -> int:
        return sum(v for u in usage.values() if isinstance(v := u.get(key), int))

    times = [t[:19] + "Z" for e in evts if isinstance(t := e.get("timestamp"), str) and TIME.match(t)]
    team = next((e for e in evts if isinstance(e.get("teamName"), str)), {})
    return {
        "round": first_round(evts), "model": model, "turns": len(usage),
        "input_tokens": total("input_tokens"), "cache_read_tokens": total("cache_read_input_tokens"),
        "output_tokens": total("output_tokens"),
        "started_at": times[0] if times else None, "ended_at": times[-1] if times else None,
        "team_name": team.get("teamName"),
        "agent_name": team["agentName"] if isinstance(team.get("agentName"), str) else None,
    }


def agent_types(evts: list[dict]) -> dict[str, str]:
    """Q2: teammate name → type, from the lead's `Agent` tool_uses (`input.name`, `input.subagent_type`)."""
    types = {}
    for e in evts:
        if e.get("type") != "assistant":
            continue
        for b in blocks(e):
            inp = b.get("input")
            if (b.get("type") == "tool_use" and b.get("name") == "Agent" and isinstance(inp, dict)
                    and isinstance(inp.get("name"), str) and isinstance(inp.get("subagent_type"), str)):
                types.setdefault(inp["name"], inp["subagent_type"])
    return types


def result_text(content) -> str:
    """Q10: a tool_result's content as text: a list's text items joined with newlines, an image as [image]."""
    if isinstance(content, str):
        return content
    parts = []
    for item in content if isinstance(content, list) else []:
        if isinstance(item, dict) and item.get("type") == "image":
            parts.append("[image]")
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def display(block: dict, full: bool) -> dict | None:
    """One content block as shown (docs/MVP.md §4.5: text as markdown with raw HTML off), or None to skip it."""
    kind = block.get("type")
    if kind == "text" and isinstance(block.get("text"), str):
        return {"type": "text", "text_html": render(block["text"])}
    if kind == "thinking" and isinstance(block.get("thinking"), str):
        return {"type": "thinking", "text": block["thinking"]}
    if kind == "tool_use" and isinstance(block.get("name"), str):
        return {"type": "tool_use", "name": block["name"],
                "input": json.dumps(block.get("input"), indent=2, ensure_ascii=False)}
    if kind == "tool_result":
        text = result_text(block.get("content"))
        cut = not full and len(text) > CUT
        return {"type": "tool_result", "text": text[:CUT] if cut else text, "is_error": block.get("is_error") is True,
                "truncated": cut}
    return None


def messages(evts: list[dict], full: bool = False) -> list[dict]:
    """user and assistant lines → [{role, at, blocks}]. Consecutive assistant lines with one `message.id` are one
    message; `at` is its first line's timestamp. Other lines and blocks are skipped, and so is a message left with
    no blocks. Without `full`, each tool result is cut at CUT characters (Q9)."""
    found, last_id = [], None
    for e in evts:
        role = e.get("type")
        if role not in ("user", "assistant"):
            continue
        shown = [d for b in blocks(e) if (d := display(b, full))]
        msg_id = message(e).get("id") if role == "assistant" else None
        if isinstance(msg_id, str) and msg_id == last_id:
            found[-1]["blocks"] += shown
        else:
            at = e.get("timestamp")
            found.append({"role": role, "at": at if isinstance(at, str) else None, "blocks": shown})
        last_id = msg_id
    return [m for m in found if m["blocks"]]
