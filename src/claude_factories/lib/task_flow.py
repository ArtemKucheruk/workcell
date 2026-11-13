"""089: where a task's factory run is, per graph node, for one round (docs/data-model-and-api.md §6.4's flow
endpoint). Pure: the handler passes plain dicts of what it read."""

from .factory_graph import CONDITIONS

STANDARD = ("security", "ux", "ui", "code")  # the reviewer focuses with verdict rows
ACTIVE = ("spec", "build", "agent_review", "approval")  # the stages a run that ended leaves stalled
FINISHED = {"done", "changes", "escalated"}  # an agent whose output a condition can read
IDLE = ("idle", "not reached")


def current_round(last: int, stage: str | None, last_created: str | None, stage_event: str | None) -> int:
    """089 C: L+1 while spec, build, or rework has started after round L (or with no round yet), else max(L, 1)."""
    if stage in ("spec", "build", "rework") and (last == 0 or (stage_event is not None and last_created < stage_event)):
        return last + 1
    return max(last, 1)


def is_stalled(run_status: str | None, status: str, stage: str | None) -> bool:
    """089: the latest run has ended while the task still waits on a factory stage."""
    return run_status is not None and run_status != "running" and status == "in_progress" and stage in ACTIVE


def named(value: str | None, name: str) -> bool:
    """A log agent's or transcript's type or name is the node's, or `<name>-…` (a teammate like builder-12)."""
    return isinstance(value, str) and (value == name or value.startswith(f"{name}-"))


def in_round(row: dict, n: int, starts: dict[int, str]) -> bool:
    """089 Q2: a transcript is round n's when its `round` is n, or, with none, it started within
    [round n's created_at, round n+1's)."""
    if row["round"] is not None:
        return row["round"] == n
    start, end = starts.get(n), starts.get(n + 1)
    at = row["started_at"]
    return start is not None and at is not None and at >= start and (end is None or at < end)


def live(state: str, label: str | None = None) -> tuple[str, str]:
    return state, label or {"running": "running", "failed": "failed", "escalated": "escalated", "done": "done"}[state]


def waiting(f: dict, stages: tuple[str, ...]) -> tuple[str, str]:
    """An agent with no output on round n: running or failed while round C is at one of its stages, else idle."""
    if f["n"] == f["C"] and f["stage"] in stages:
        if f["running"]:
            return live("running")
        if f["stalled"]:
            return live("failed")
    return IDLE


def custom(name: str, f: dict) -> tuple[str, str]:
    """A custom agent or custom-focus reviewer: from the latest run's log on round C, else its transcripts."""
    seen = [a for a in f["agents"] if named(a["type"], name) or named(a["name"], name)] if f["n"] == f["C"] else []
    if f["running"] and any(a["running"] for a in seen):
        return live("running")
    if any(not a["running"] for a in seen) or name in f["transcript_types"]:
        return live("done")
    return IDLE


def agent_state(node: dict, f: dict) -> tuple[str, str]:
    kind, data = node["type"], node["data"]
    if kind == "start":
        return live("done") if f["started"] else IDLE
    if kind == "spec_writer":
        return live("done") if f["spec"] else waiting(f | {"n": f["C"]}, ("spec",))  # every round shows the one spec
    if kind == "builder":
        return live("done") if f["built"] else waiting(f, ("build", "rework"))
    if kind == "reviewer" and data["focus"] in STANDARD:
        verdict = f["verdicts"].get(data["focus"])
        if verdict:
            return ("done" if verdict == "PASS" else "changes"), verdict
        return waiting(f, ("agent_review",))
    if kind == "approver":
        decision = f["decision"]
        if decision == "APPROVE":
            return "done", decision
        if decision == "ESCALATE":
            return "escalated", decision
        if f["n"] == f["C"] and f["stage"] == "escalated" and f["n"] == f["L"]:  # Q3: escalated without a decision
            return live("escalated")
        return waiting(f, ("approval",))
    return custom(data["name"], f)


def answer(node: dict, f: dict) -> tuple[bool, str]:
    """A reached condition's answer and why."""
    kind = node["type"]
    if kind in ("all_pass", "any_changes"):
        changed = [who for who in STANDARD if f["verdicts"].get(who) == "CHANGES"]
        why = f"{', '.join(changed)} asked for changes" if changed else "all PASS"
        return (not changed if kind == "all_pass" else bool(changed)), why
    if kind == "rounds_below":
        return f["n"] < node["data"]["n"], f"round {f['n']} of {node['data']['n']}"
    return f["decision"] == "APPROVE", f"decision {f['decision']}" if f["decision"] else "no decision"


def node_states(graph: dict, f: dict) -> dict[str, dict]:
    """089's state rules: {node id: {state, label, current, answer, why}}. `f`: n, C, L, stage, running, stalled,
    started, spec, built, verdicts {focus: verdict} and decision (the approver's latest) on round n, agents (the
    latest run's run_agents), and transcript_types (round n's transcripts' agent types).
    A condition is answered once reached: every non-condition node leading into it has finished (at least one does),
    or a condition leads into it from the handle its answer took. ponytail: an ESCALATE counts as finished, so
    `approved` answers no; the spec only lists done and changes."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    out = {}
    for node in graph["nodes"]:
        if node["type"] not in CONDITIONS:
            state, label = agent_state(node, f)
            out[node["id"]] = {"state": state, "label": label, "answer": None, "why": None}
    answers: dict[str, str] = {}
    pending = [node for node in graph["nodes"] if node["type"] in CONDITIONS]
    while True:  # conditions feed conditions: answer until nothing new is reached
        reached = []
        for node in pending:
            into = [e for e in graph["edges"] if e["target"] == node["id"] and e["source"] in nodes]
            plain = [e for e in into if nodes[e["source"]]["type"] not in CONDITIONS]
            if (plain and all(out[e["source"]]["state"] in FINISHED for e in plain)) or any(
                    e["source"] in answers and answers[e["source"]] == e["sourceHandle"] for e in into):
                reached.append(node)
        if not reached:
            break
        for node in reached:
            yes, why = answer(node, f)
            answers[node["id"]] = "yes" if yes else "no"
            out[node["id"]] = {"state": "done", "label": answers[node["id"]], "answer": answers[node["id"]], "why": why}
            pending.remove(node)
    for node in pending:
        out[node["id"]] = {"state": IDLE[0], "label": IDLE[1], "answer": None, "why": None}
    running = [s for s in out.values() if s["state"] == "running"]
    for s in out.values():
        s["current"] = s["state"] == "running" if running else (
            f["n"] == f["C"] and s["state"] in ("failed", "escalated"))
    return out
