"""089: lib/task_flow's state rules over the default graph (AC6, AC8, AC9, AC11, AC13, AC14, AC18, AC20)."""

import json

import pytest

from workcell.handlers.factories import default_graph
from workcell.lib.run_log import run_agents
from workcell.lib.task_flow import current_round, in_round, is_stalled, node_states

GRAPH = default_graph().model_dump()
ALL = {"security": "PASS", "ux": "PASS", "ui": "PASS", "code": "PASS"}


def facts(**kw) -> dict:
    return {"n": 1, "C": 1, "L": 0, "stage": None, "running": False, "stalled": False, "started": True,
            "spec": True, "built": False, "verdicts": {}, "decision": None, "agents": [],
            "transcript_types": set()} | kw


def pick(states, *ids):
    return {i: (states[i]["state"], states[i]["label"]) for i in ids}


def current(states):
    return sorted(i for i, s in states.items() if s["current"])


def test_current_round():  # 089 C
    assert current_round(0, None, None, None) == 1
    assert current_round(0, "spec", None, "2026-01-01T00:00:00Z") == 1
    assert current_round(1, "build", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z") == 2  # rework's build
    assert current_round(1, "build", "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z") == 1  # round 1's own build
    assert current_round(2, "agent_review", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z") == 2


def test_is_stalled():
    assert is_stalled("failed", "in_progress", "agent_review")
    assert not is_stalled("running", "in_progress", "agent_review")
    assert not is_stalled(None, "in_progress", "build")
    assert not is_stalled("succeeded", "review", "human_review")
    assert not is_stalled("failed", "in_progress", "rework")


def test_in_round():  # AC19's attribution
    starts = {1: "2026-01-01T00:00:00Z", 2: "2026-01-02T00:00:00Z"}
    row = lambda r, at: {"round": r, "started_at": at}  # noqa: E731
    assert in_round(row(2, None), 2, starts) and not in_round(row(2, None), 1, starts)
    assert in_round(row(None, "2026-01-01T05:00:00Z"), 1, starts)
    assert not in_round(row(None, "2026-01-02T00:00:00Z"), 1, starts)
    assert in_round(row(None, "2026-01-02T00:00:00Z"), 2, starts)
    assert not in_round(row(None, "2025-12-31T00:00:00Z"), 1, starts)
    assert not in_round(row(None, None), 1, starts)


def test_spec_running():  # AC6
    states = node_states(GRAPH, facts(stage="spec", running=True, spec=False))
    assert pick(states, "spec-writer", "builder") == {"spec-writer": ("running", "running"),
                                                      "builder": ("idle", "not reached")}
    assert current(states) == ["spec-writer"]


def test_mixed_verdicts():  # AC8
    states = node_states(GRAPH, facts(stage="agent_review", running=True, L=1, built=True,
                                      verdicts={"security": "PASS", "code": "CHANGES"}))
    assert pick(states, "review-security", "review-code", "review-ux", "review-ui", "all-pass") == {
        "review-security": ("done", "PASS"), "review-code": ("changes", "CHANGES"),
        "review-ux": ("running", "running"), "review-ui": ("running", "running"), "all-pass": ("idle", "not reached")}
    assert current(states) == ["review-ui", "review-ux"]


def test_round_one_of_a_rework():  # AC9
    states = node_states(GRAPH, facts(stage="build", running=True, n=1, C=2, L=1, built=True,
                                      verdicts=ALL | {"code": "CHANGES"}))
    assert pick(states, "all-pass", "rounds", "approver") == {
        "all-pass": ("done", "no"), "rounds": ("done", "yes"), "approver": ("idle", "not reached")}
    assert states["rounds"]["why"] == "round 1 of 2"
    assert states["all-pass"]["why"] == "code asked for changes"


def test_approval_running():  # AC11
    states = node_states(GRAPH, facts(stage="approval", running=True, L=1, built=True, verdicts=ALL))
    assert (states["all-pass"]["answer"], states["all-pass"]["why"]) == ("yes", "all PASS")
    assert pick(states, "approver", "rounds") == {"approver": ("running", "running"), "rounds": ("idle", "not reached")}
    assert current(states) == ["approver"]


def test_failed_run_in_review():  # AC13
    states = node_states(GRAPH, facts(stage="agent_review", stalled=True, L=1, built=True,
                                      verdicts={"security": "PASS", "code": "PASS"}))
    assert pick(states, "review-ux", "review-ui") == {"review-ux": ("failed", "failed"),
                                                      "review-ui": ("failed", "failed")}
    assert current(states) == ["review-ui", "review-ux"]


def test_escalated():  # AC12's states, Q3
    states = node_states(GRAPH, facts(stage="escalated", n=2, C=2, L=2, built=True,
                                      verdicts=ALL | {"ui": "CHANGES"}, decision="ESCALATE"))
    assert pick(states, "approver") == {"approver": ("escalated", "ESCALATE")}
    assert current(states) == ["approver"]
    no_decision = node_states(GRAPH, facts(stage="escalated", n=2, C=2, L=2, built=True, verdicts=ALL))
    assert pick(no_decision, "approver") == {"approver": ("escalated", "escalated")}
    assert current(no_decision) == ["approver"]


def test_human_review():  # AC14
    states = node_states(GRAPH, facts(stage="human_review", L=1, built=True, verdicts=ALL, decision="APPROVE"))
    assert pick(states, "approver") == {"approver": ("done", "APPROVE")}
    assert current(states) == []


def test_condition_whys():  # AC18
    states = node_states(GRAPH, facts(stage="build", n=1, C=2, L=1, built=True,
                                      verdicts={"security": "CHANGES", "ux": "PASS", "ui": "PASS", "code": "CHANGES"}))
    assert states["all-pass"]["why"] == "security, code asked for changes"
    any_graph = {"nodes": [*GRAPH["nodes"][:7], {"id": "any", "type": "any_changes", "data": {}},
                           {"id": "ok", "type": "approved", "data": {}}],
                 "edges": [*GRAPH["edges"][:6], *({"source": f"review-{w}", "target": "any", "sourceHandle": None}
                                                  for w in ("security", "ux", "ui", "code")),
                           {"source": "approver", "target": "ok", "sourceHandle": None}]}
    any_graph["nodes"].append(GRAPH["nodes"][-1])
    states = node_states(any_graph, facts(stage="human_review", L=1, built=True, verdicts=ALL, decision="APPROVE"))
    assert (states["any"]["answer"], states["any"]["why"]) == ("no", "all PASS")
    assert (states["ok"]["answer"], states["ok"]["why"]) == ("yes", "decision APPROVE")
    idle = node_states(any_graph, facts(stage="agent_review", running=True, L=1, built=True))
    assert (idle["ok"]["state"], idle["ok"]["answer"], idle["ok"]["why"]) == ("idle", None, None)


def spawn(tool_id, kind):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tool_id, "name": "Agent", "input": {"subagent_type": kind, "prompt": "Task 7."}}]}})


def answered(tool_id):
    return json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id}]}})


@pytest.mark.parametrize("lines, running, state", [
    ([spawn("a1", "linter")], True, "running"),
    ([spawn("a1", "linter"), answered("a1")], True, "done"),
    ([spawn("a1", "other")], True, "idle"),
    ([spawn("a1", "linter")], False, "idle"),
])
def test_custom_agent_from_log(lines, running, state):  # AC20
    graph = {"nodes": [{"id": "start", "type": "start", "data": {}},
                       {"id": "lint", "type": "custom_agent", "data": {"name": "linter"}}],
             "edges": [{"source": "start", "target": "lint", "sourceHandle": None}]}
    states = node_states(graph, facts(running=running, agents=run_agents(lines)[1:]))
    assert states["lint"]["state"] == state
    assert states["lint"]["current"] == (state == "running")


def test_custom_agent_from_transcript():  # AC20's done side
    graph = {"nodes": [{"id": "lint", "type": "custom_agent", "data": {"name": "linter"}}], "edges": []}
    assert node_states(graph, facts(transcript_types={"linter"}))["lint"]["state"] == "done"
