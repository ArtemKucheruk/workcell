"""052: the compile of a factory graph (docs/claude-code.md §7.3), on the pure functions."""

import pytest

from workcell.domain.errors import Invalid
from workcell.handlers.factories import default_graph
from workcell.handlers.factory import TEMPLATES
from workcell.lib.factory_compile import compile_files

TEMPLATE = (TEMPLATES / "skills" / "factory" / "SKILL.md").read_text(encoding="utf-8")
VALUES = {"name": "api-server", "default_branch": "main", "test_cmd": "make check"}
END = """   `fctl stage <id> human_review`. ESCALATE, no decision, or anything else →
   `fctl stage <id> escalated`. Stop and report the decision's summary: the task now waits
   on me in Review."""
BRANCHING = f"""1. `fctl show <id>`: read the task, then continue from its current stage (table above).
2. spec → `fctl stage <id> spec`. Spawn `spec`: "Task <id>." Wait for it.
   `fctl show <id>` still says `_No spec yet._` → stop and report.
3. build, the next round n → `fctl stage <id> build`.
   - Round 1, or no `coder-<id>` in this session: spawn `coder` named `coder-<id>`:
     "Task <id>, round <n>."
   - Otherwise SendMessage `coder-<id>`: "Round <n>. Round <n-1> verdicts: `fctl show <id> --round <n-1>`."
     SendMessage may be a deferred tool: load it with ToolSearch `select:SendMessage`.

   Wait for it. Done when the builder has run `fctl submit <id>` and `fctl round <id>` shows
   round n. Not there → ask the builder once to submit, then stop and report.
4. agent_review → `fctl stage <id> agent_review`. Spawn these in ONE message, each with "Task <id>.":
   `sec`, `docs`.
   WAIT FOR ALL: go on only when `fctl round <id>` shows a verdict from each. Spawn a reviewer
   that ended without posting its verdict once more. Never message the builder mid-round.
5. Any review CHANGES? yes → step 6, no → step 7.
6. Rounds used < 3? yes → step 3, no → step 7.
7. approval → `fctl stage <id> approval`. Spawn `ship`: "Task <id>, rounds used <x> of 3."
   Rounds exhausted with CHANGES → it must ESCALATE. Wait for it.
8. Decision APPROVE? yes → step 9, no → step 10.
9. Spawn `notify`: "Task <id>." Wait for it.
10. Read the approver's latest decision in `fctl show <id> --round <n>`. APPROVE →
{END}"""


def compiled(graph: dict, values=VALUES, skill="factory") -> dict[str, str]:
    return dict(compile_files(graph, TEMPLATE, values, skill))


def loop_body(skill_md: str) -> str:
    return skill_md.split("\n## The loop\n\n")[1].split("\n\n## Conditions\n")[0]


def agent(id_, type_, **extra) -> dict:
    data = {"name": id_, "description": f"The {id_} agent.", "model": "sonnet", "tools": ["Read"],
            "prompt": "Do it.\n"} | extra
    return {"id": id_, "type": type_, "position": {"x": 0, "y": 0}, "data": data}


def bare(id_, type_, **data) -> dict:
    return {"id": id_, "type": type_, "position": {"x": 0, "y": 0}, "data": data}


def edges(*links) -> list[dict]:
    """"a>b" or "a yes>b" → an edge, in order."""
    out = []
    for i, link in enumerate(links, 1):
        source, target = link.split(">")
        source, _, handle = source.partition(" ")
        out.append({"id": f"e{i}", "source": source, "sourceHandle": handle or None, "target": target})
    return out


def default() -> dict:
    return default_graph().model_dump()


def refusal(graph) -> str:
    with pytest.raises(Invalid) as e:
        compiled(graph)
    return e.value.detail


def test_branching_graph():  # BE5
    graph = {
        "nodes": [bare("start", "start"), agent("spec", "spec_writer"), agent("coder", "builder", side="both"),
                  agent("sec", "reviewer", focus="security"), agent("docs", "reviewer", focus="custom"),
                  bare("changes", "any_changes"), bare("cap", "rounds_below", n=3), agent("ship", "approver"),
                  bare("ok", "approved"), agent("notify", "custom_agent"), agent("stray", "custom_agent")],
        "edges": edges("start>spec", "spec>coder", "coder>sec", "coder>docs", "sec>changes", "docs>changes",
                       "changes no>ship", "changes yes>cap", "cap yes>coder", "cap no>ship", "ship>ok",
                       "ok yes>notify"),
    }
    files = compiled(graph)
    assert list(files) == [".claude/skills/factory/SKILL.md",
                           *(f".claude/agents/{a}.md" for a in ("spec", "coder", "sec", "docs", "ship", "notify",
                                                                 "stray"))]
    assert loop_body(files[".claude/skills/factory/SKILL.md"]) == BRANCHING


def test_agent_file_text():  # BE6
    prompt = "Run {{ test_cmd }}; {{name}} {{ other }} {% if x %}"
    graph = {"nodes": [bare("start", "start"),
                       agent("linter", "custom_agent", model="inherit", tools=[], description="Lints\nthe diff",
                             prompt=prompt)],
             "edges": edges("start>linter")}
    assert compiled(graph)[".claude/agents/linter.md"] == (
        "---\nname: linter\ndescription: Lints the diff\nmodel: inherit\n---\n"
        "Run make check; {{name}} {{ other }} {% if x %}")


def test_condition_among_next_nodes():  # BE7
    graph = default()
    graph["edges"].append({"id": "e99", "source": "builder", "sourceHandle": None, "target": "all-pass"})
    assert refusal(graph) == ("builder leads to review-security, review-ux, review-ui, review-code,"
                              " All reviews PASS?: a condition must be the only node it leads to")


def test_part_of_an_earlier_step():  # BE8
    graph = default()
    [rounds_yes] = [e for e in graph["edges"] if e["source"] == "rounds" and e["sourceHandle"] == "yes"]
    rounds_yes["target"] = "review-security"
    assert refusal(graph) == ("Rounds used < 2? yes leads to review-security: those must be new nodes,"
                              " or exactly the nodes of one earlier step")


@pytest.mark.parametrize("with_be7_edge", [False, True])
def test_blank_description_first(with_be7_edge):  # BE9
    graph = default()
    [spec] = [n for n in graph["nodes"] if n["id"] == "spec-writer"]
    spec["data"]["description"] = "  "
    if with_be7_edge:
        graph["edges"].append({"id": "e99", "source": "builder", "sourceHandle": None, "target": "all-pass"})
    assert refusal(graph) == "agent spec-writer needs a description"
