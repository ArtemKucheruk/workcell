"""089: the task page's Factory section, GET /api/pages/tasks/{id}/flow (docs/data-model-and-api.md §6.4): the
project's factory graph, each node's state for a round (lib/task_flow), and each node's result."""

import json

from ..domain.errors import NotFound
from ..lib.factory_compile import slug
from ..lib.factory_graph import CONDITIONS
from ..lib.markdown import render
from ..lib.run_log import run_agents
from ..lib.task_flow import current_round, in_round, is_stalled, node_states
from ..repositories.factories import FactoriesRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from ..repositories.transcripts import TranscriptsRepo
from .factories import default_graph
from .runs import log_lines


def pick_graph(factories: FactoriesRepo, project_id: int) -> tuple[dict, dict | None]:
    """Q1: the design whose slug is `factory` (what Write to repo puts in .claude/skills/factory/, which `/factory <id>`
    runs), the latest updated_at then highest id among several; with none, default_graph(), which Create factory
    writes. (graph, source). ponytail: the design as it is now, not as it was when the run started, and the committed
    SKILL.md may differ from it; store the graph on the run if that becomes a problem."""
    for row in factories.graphs(project_id):
        if slug(row["name"]) == "factory":
            return json.loads(row["graph"]), {"factory_id": row["id"], "name": row["name"]}
    return default_graph().model_dump(), None


def md(row, *names: str) -> dict:
    """The row as a dict, each `<name>_md` with its `<name>_html`."""
    out = dict(row)
    for name in names:
        out[f"{name}_html"] = render(out[f"{name}_md"] or "")
    return out


def task_flow(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo,
              transcripts: TranscriptsRepo, factories: FactoriesRepo, task_id: int, n: str) -> dict:
    """`n` is `latest` or a round number as text; a round outside 1..max(L, C) is a 404 naming it."""
    task = tasks.get(task_id)
    if task is None:
        raise NotFound(f"Task #{task_id} not found")
    listed = {r["n"]: r for r in rounds.all(task_id)}
    totals = {r["n"]: r for r in rounds.totals(task_id)}
    last = max(listed, default=0)
    stage = task["stage"]
    current = current_round(last, stage, listed[last]["created_at"] if last else None,
                            stage and tasks.stage_entered(task_id, stage))
    numbers = list(range(1, max(last, current) + 1))
    if n == "latest":
        picked = numbers[-1]
    elif n in {str(i) for i in numbers}:
        picked = int(n)
    else:
        raise NotFound(f"Task #{task_id} has no round {n}")
    if task["worktree_path"] is None and last:  # Q3: a standalone submit; no factory ran
        return {"graph": None, "source": None, "rounds": numbers, "round": picked, "nodes": {}}

    graph, source = pick_graph(factories, task["project_id"])
    run = runs.latest_log(task_id)
    row = listed.get(picked)
    verdicts = [md(v, "body") for v in reviews.round_verdicts(row["id"])] if row else []
    decisions = [md(d, "body") for d in reviews.round_decisions(row["id"])] if row else []
    comments = [md(c, "body") for c in reviews.comments(row["id"], False)] if row else []
    approver = [d for d in decisions if d["actor"] == "approver"]
    starts = {k: r["created_at"] for k, r in listed.items()}
    rows = [dict(t) for t in transcripts.for_task(task_id)]
    of_round = [t for t in rows if in_round(t, picked, starts)]
    customs = any(node["type"] == "custom_agent" or node["type"] == "reviewer" and node["data"]["focus"] == "custom"
                  for node in graph["nodes"])
    facts = {
        "n": picked, "C": current, "L": last, "stage": stage,
        "running": bool(run) and run["status"] == "running",
        "stalled": is_stalled(run and run["status"], task["status"], stage),
        "started": bool(run) or bool(last), "spec": bool((task["spec_md"] or "").strip()), "built": row is not None,
        "verdicts": {v["reviewer"]: v["verdict"] for v in verdicts},
        "decision": approver[-1]["decision"] if approver else None,
        # 053's parse of the latest run's log, read only when a node needs it (custom agents have no verdict rows)
        "agents": run_agents(log_lines(run["log_path"]))[1:] if customs and run else [],
        "transcript_types": {t["agent_type"] for t in of_round},
    }
    states = node_states(graph, facts)

    def result(node: dict) -> dict:
        kind, data = node["type"], node["data"]
        if kind == "start":
            return {}
        if kind in CONDITIONS:
            return {"answer": states[node["id"]]["answer"], "why": states[node["id"]]["why"]}
        name = data["name"]
        out = {"transcripts": [t for t in (rows if kind == "spec_writer" else of_round) if t["agent_type"] == name]}
        if kind == "spec_writer":
            out |= md({"spec_md": task["spec_md"]}, "spec")
        elif kind == "builder" and row:
            total = totals[picked]
            out |= md({"build_md": row["build_md"]}, "build") | {
                "files": total["files"], "additions": total["additions"], "deletions": total["deletions"],
                "diff_url": f"/tasks/{task_id}/review?round={picked}&tab=files"}
        elif kind == "reviewer" and data["focus"] != "custom":
            out["verdict"] = next((v for v in verdicts if v["reviewer"] == data["focus"]), None)
            out["comments"] = [c for c in comments if c["author"] == data["focus"]]
        elif kind == "approver":
            out["decisions"] = decisions
        return out

    return {"graph": graph, "source": source, "rounds": numbers, "round": picked,
            "nodes": {node["id"]: {"state": states[node["id"]]["state"], "label": states[node["id"]]["label"],
                                   "current": states[node["id"]]["current"], "result": result(node)}
                      for node in graph["nodes"]}}
