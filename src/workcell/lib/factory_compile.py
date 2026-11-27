"""052: a stored factory graph → its Claude Code files (docs/claude-code.md §7.3). Pure: the caller passes the
SKILL.md template's text and the project's values."""

import re

from ..domain.errors import Invalid
from .factory_graph import AGENTS, CONDITIONS

QUESTIONS = {"all_pass": "All reviews PASS?", "any_changes": "Any review CHANGES?", "approved": "Decision APPROVE?"}
LOOP = "\n## The loop\n\n"  # Q2: the compile replaces only the text between these two
AFTER_LOOP = "\n\n## Conditions\n"
END = """{n}. Read the approver's latest decision in `fctl show <id> --round <n>`. APPROVE →
   `fctl stage <id> human_review`. ESCALATE, no decision, or anything else →
   `fctl stage <id> escalated`. Stop and report the decision's summary: the task now waits
   on me in Review."""


def slug(name: str, empty: str = "factory") -> str:
    """Q1, Q10: `Nightly Build!` → `nightly-build`; nothing left → `empty`."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or empty


def fill(text: str, values: dict[str, str]) -> str:
    """Q7: one pass over exactly `{{ key }}` (single spaces) for each key in values. A value is never re-scanned,
    and any other `{{ … }}`, `{% … %}`, or `{# … #}` stays as typed: no text here goes through Jinja."""
    return re.sub(r"\{\{ (\w+) \}\}", lambda m: values.get(m[1], m[0]), text)


def one_line(text: str) -> str:
    """Q7: each line break becomes one space."""
    return re.sub(r"\r\n|[\r\n]", " ", text)


def agent_file(data: dict, values: dict[str, str]) -> str:
    """Q7: 011's frontmatter (no tools line for no tools), then the prompt; values filled over the whole text."""
    head = [f"name: {data['name']}", f"description: {one_line(data['description'])}"]
    if data["tools"]:
        head.append("tools: " + ", ".join(one_line(tool) for tool in data["tools"]))
    head.append(f"model: {data['model']}")
    return fill("---\n" + "\n".join(head) + "\n---\n" + data["prompt"], values)


def title(node: dict) -> str:
    """The node's card title (docs/data-model-and-api.md §6.1)."""
    if node["type"] == "start":
        return "Start"
    if node["type"] == "rounds_below":
        return f"Rounds used < {node['data']['n']}?"
    return QUESTIONS.get(node["type"]) or node["data"]["name"]


def walk(graph: dict) -> tuple[list[list[dict]], list[list[int | None]]]:
    """Q3, Q6 C1/C2: breadth-first steps from start (each a list of nodes), and each step's next step indexes:
    one, or yes then no for a condition. None is End."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    [start] = [node for node in graph["nodes"] if node["type"] == "start"]
    steps, nexts, step_of = [[start]], [], {start["id"]: 0}
    for members in steps:  # grows as new steps are found
        ids = {node["id"] for node in members}
        if members[0]["type"] in CONDITIONS:
            sets = [(f"{title(members[0])} {handle}", handle) for handle in ("yes", "no")]
        else:
            sets = [(", ".join(title(node) for node in members), None)]
        resolved = []
        for source, handle in sets:
            targets = list(dict.fromkeys(edge["target"] for edge in graph["edges"]
                                         if edge["source"] in ids and edge["sourceHandle"] == handle))
            found = [nodes[target] for target in targets]
            titles = ", ".join(title(node) for node in found)
            known = {step_of.get(target) for target in targets}
            if not targets:
                resolved.append(None)
            elif len(found) > 1 and any(node["type"] in CONDITIONS for node in found):
                raise Invalid(f"{source} leads to {titles}: a condition must be the only node it leads to")
            elif known == {None}:
                step_of |= dict.fromkeys(targets, len(steps))
                resolved.append(len(steps))
                steps.append(found)
            elif len(known) == 1 and None not in known and len(steps[k := known.pop()]) == len(targets):
                resolved.append(k)
            else:
                raise Invalid(f"{source} leads to {titles}: those must be new nodes, or exactly the nodes of one"
                              " earlier step")
        nexts.append(resolved)
    return steps, nexts


def step_text(n: int, members: list[dict], nexts: list[int], cap: int | None) -> str:
    """Q4: step n's text; nexts are step numbers."""
    first, kind = members[0], members[0]["type"]
    name, names = title(first), ", ".join(f"`{title(node)}`" for node in members)  # an agent's title is its name
    if kind in CONDITIONS:
        return f"{n}. {title(first)} yes → step {nexts[0]}, no → step {nexts[1]}."
    if kind == "start":
        text = f"{n}. `fctl show <id>`: read the task, then continue from its current stage (table above)."
    elif all(node["type"] == "reviewer" for node in members):
        text = (f"{n}. agent_review → `fctl stage <id> agent_review`."
                ' Spawn these in ONE message, each with "Task <id>.":\n'
                f"   {names}.\n"
                "   WAIT FOR ALL: go on only when `fctl round <id>` shows a verdict from each. Spawn a reviewer\n"
                "   that ended without posting its verdict once more. Never message the builder mid-round.")
    elif len(members) > 1:
        text = (f'{n}. Spawn these in ONE message, each with "Task <id>.":\n'
                f"   {names}.\n"
                "   WAIT FOR ALL: go on only when every one of them has ended.")
    elif kind == "spec_writer":
        text = (f'{n}. spec → `fctl stage <id> spec`. Spawn `{name}`: "Task <id>." Wait for it.\n'
                "   `fctl show <id>` still says `_No spec yet._` → stop and report.")
    elif kind == "builder":
        text = (f"{n}. build, the next round n → `fctl stage <id> build`.\n"
                f"   - Round 1, or no `{name}-<id>` in this session: spawn `{name}` named `{name}-<id>`:\n"
                '     "Task <id>, round <n>."\n'
                f'   - Otherwise SendMessage `{name}-<id>`: "Round <n>. Round <n-1> verdicts:'
                ' `fctl show <id> --round <n-1>`."\n'
                "     SendMessage may be a deferred tool: load it with ToolSearch `select:SendMessage`.\n"
                "\n"
                "   Wait for it. Done when the builder has run `fctl submit <id>` and `fctl round <id>` shows\n"
                "   round n. Not there → ask the builder once to submit, then stop and report.")
    elif kind == "approver":
        of = "" if cap is None else f" of {cap}"
        text = (f'{n}. approval → `fctl stage <id> approval`. Spawn `{name}`: "Task <id>, rounds used <x>{of}."\n'
                "   Rounds exhausted with CHANGES → it must ESCALATE. Wait for it.")
    else:  # custom_agent
        text = f'{n}. Spawn `{name}`: "Task <id>." Wait for it.'
    return text if nexts[0] == n + 1 else f"{text}\n   Then step {nexts[0]}."


def loop(graph: dict) -> str:
    """Q3–Q5: the body of SKILL.md's `## The loop`, steps joined by one line break, End last."""
    steps, nexts = walk(graph)
    end = len(steps) + 1
    cap = next((step[0]["data"]["n"] for step in steps if step[0]["type"] == "rounds_below"), None)
    texts = [step_text(i, step, [end if k is None else k + 1 for k in following], cap)
             for i, (step, following) in enumerate(zip(steps, nexts), 1)]
    return "\n".join([*texts, END.format(n=end)])


def compile_files(graph: dict, skill_template: str, values: dict[str, str], skill: str) -> list[tuple[str, str]]:
    """(path, content) of SKILL.md, then one file per agent node in node order (Q6: C3 first, then the walk).
    values: the project's name, test_cmd, and default_branch. The template is split before any value goes in,
    so no value can move the loop's boundary (Q2)."""
    agents = [node["data"] for node in graph["nodes"] if node["type"] in AGENTS]
    for data in agents:
        if not data["description"].strip():
            raise Invalid(f"agent {data['name']} needs a description")
    head, rest = skill_template.split(LOOP)
    _, tail = rest.split(AFTER_LOOP)
    named = values | {"skill": skill}
    text = fill(head, named) + LOOP + loop(graph) + AFTER_LOOP + fill(tail, named)
    return [(f".claude/skills/{skill}/SKILL.md", text),
            *((f".claude/agents/{data['name']}.md", agent_file(data, values)) for data in agents)]
