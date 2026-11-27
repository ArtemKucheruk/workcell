"""089: GET /api/pages/tasks/{id}/flow (docs/data-model-and-api.md §6.4): the graph (Q1, Q3), rounds, and each
node's state and result (AC1–AC5, AC7, AC10, AC12, AC15–AC17, AC19, AC20)."""

import json

from conftest import sql
from controllers.test_pages_api import (add_comment, add_decision, add_event, add_round, add_run, add_verdict, api,
                                        review_task)
from controllers.test_runs import H, add_task, fake, project  # noqa: F401
from controllers.test_transcripts import add_transcript

from workcell.handlers.factories import default_graph

LATER = "2026-01-05T00:00:00Z"
DEFAULT = json.loads(default_graph().model_dump_json())


def flow(client, task_id, query="", status=200):
    return api(client, f"/api/pages/tasks/{task_id}/flow{query}", status)


def design(client, project_id, name, template="standard") -> dict:
    r = client.post(f"/api/projects/{project_id}/factories", json={"name": name, "template": template}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def states(page, *ids):
    return {i: (page["nodes"][i]["state"], page["nodes"][i]["label"]) for i in ids}


def current(page):
    return sorted(i for i, node in page["nodes"].items() if node["current"])


def in_progress(project_id, stage, spec="## Spec"):
    return review_task(project_id, status="in_progress", stage=stage, spec=spec)


def test_graph_of_the_factory_design(client, project):  # AC1, Q1
    design(client, project, "Other", "bug-fix")
    found = design(client, project, "Factory", "test-coverage")
    page = flow(client, add_task(project))
    assert page["graph"] == found["graph"]
    assert page["source"] == {"factory_id": found["id"], "name": "Factory"}
    assert set(page["nodes"]) == {n["id"] for n in found["graph"]["nodes"]}


def test_default_graph_without_one(client, project):  # AC2
    design(client, project, "Nightly", "bug-fix")
    page = flow(client, add_task(project))
    assert (page["graph"], page["source"]) == (DEFAULT, None)


def test_standalone_task_has_no_graph(client, project):  # AC3, Q3
    task = review_task(project, worktree=None)
    add_round(task, 1)
    assert flow(client, task) == {"graph": None, "source": None, "rounds": [1], "round": 1, "nodes": {}}


def test_backlog_task_is_all_idle(client, project):  # AC4
    page = flow(client, add_task(project))
    assert (page["rounds"], page["round"]) == ([1], 1)
    assert {node["state"] for node in page["nodes"].values()} == {"idle"}
    assert {node["label"] for node in page["nodes"].values()} == {"not reached"}
    assert current(page) == []


def test_not_found(client, project):  # AC5
    assert flow(client, 99, status=404) == {"detail": "Task #99 not found"}
    task = review_task(project)
    add_round(task, 1)
    assert flow(client, task, "?round=3", 404) == {"detail": f"Task #{task} has no round 3"}
    assert flow(client, task, "?round=x", 404) == {"detail": f"Task #{task} has no round x"}


def test_spec_writer_running(client, project):  # AC6, through the handler
    task = in_progress(project, "spec", spec=None)
    add_run(task, "running")
    page = flow(client, task)
    assert states(page, "spec-writer", "builder") == {"spec-writer": ("running", "running"),
                                                      "builder": ("idle", "not reached")}
    assert current(page) == ["spec-writer"]


def test_builder_running_first_round(client, project):  # AC7
    task = in_progress(project, "build")
    add_event(task, "backlog", "in_progress", "build")
    add_run(task, "running")
    page = flow(client, task)
    assert page["rounds"] == [1]
    assert states(page, "builder", "spec-writer", "start") == {
        "builder": ("running", "running"), "spec-writer": ("done", "done"), "start": ("done", "done")}
    assert current(page) == ["builder"]


def test_round_two_rework(client, project):  # AC10
    task = in_progress(project, "build")
    first = add_round(task, 1)
    for who in ("security", "ux", "ui"):
        add_verdict(first, who, "PASS")
    add_verdict(first, "code", "CHANGES", "fix it")
    add_event(task, "in_progress", "in_progress", "build", at=LATER)
    add_run(task, "running")
    page = flow(client, task)
    assert (page["rounds"], page["round"]) == ([1, 2], 2)
    assert states(page, "builder", "review-code") == {"builder": ("running", "running"),
                                                      "review-code": ("idle", "not reached")}
    one = flow(client, task, "?round=1")
    assert one["round"] == 1
    assert states(one, "builder", "review-security", "review-code", "all-pass", "rounds") == {
        "builder": ("done", "done"), "review-security": ("done", "PASS"), "review-code": ("changes", "CHANGES"),
        "all-pass": ("done", "no"), "rounds": ("done", "yes")}
    assert one["nodes"]["review-code"]["result"]["verdict"]["body_md"] == "fix it"
    assert current(one) == []


def test_escalated_with_decision(client, project):  # AC12
    task = review_task(project, stage="escalated")
    add_round(task, 1)
    second = add_round(task, 2, at=LATER)
    add_decision(task, second, "approver", "ESCALATE", "**Rounds** used up")
    add_run(task, "succeeded")
    page = flow(client, task)
    assert page["round"] == 2
    assert states(page, "approver") == {"approver": ("escalated", "ESCALATE")}
    assert current(page) == ["approver"]
    assert page["nodes"]["approver"]["result"]["decisions"] == [{
        "actor": "approver", "decision": "ESCALATE", "body_md": "**Rounds** used up",
        "body_html": "<p><strong>Rounds</strong> used up</p>\n"}]


def test_builder_result(client, project):  # AC15
    task = in_progress(project, "agent_review")
    round_id = add_round(task, 1, files=((3, 1), (2, 0)))
    sql("UPDATE rounds SET build_md = '# Notes' WHERE id = ?", (round_id,))
    result = flow(client, task)["nodes"]["builder"]["result"]
    assert {k: result[k] for k in ("build_md", "build_html", "files", "additions", "deletions", "diff_url")} == {
        "build_md": "# Notes", "build_html": "<h1>Notes</h1>\n", "files": 2, "additions": 5, "deletions": 1,
        "diff_url": f"/tasks/{task}/review?round=1&tab=files"}


def test_reviewer_result(client, project):  # AC16
    task = in_progress(project, "agent_review")
    round_id = add_round(task, 1)
    add_verdict(round_id, "security", "CHANGES", "Use `hmac`")
    add_comment(task, round_id, "security", "here", path="a.py", line=4)
    add_comment(task, round_id, "security", "overall")
    add_comment(task, round_id, "code", "not mine", path="a.py", line=5)
    result = flow(client, task)["nodes"]["review-security"]["result"]
    assert result["verdict"] == {"verdict": "CHANGES", "body_md": "Use `hmac`",
                                 "body_html": "<p>Use <code>hmac</code></p>\n"}
    assert result["comments"] == [
        {"path": "a.py", "line": 4, "side": "new", "body_md": "here", "body_html": "<p>here</p>\n"},
        {"path": None, "line": None, "side": None, "body_md": "overall", "body_html": "<p>overall</p>\n"}]


def test_approver_result(client, project):  # AC17
    task = review_task(project)
    round_id = add_round(task, 1)
    add_decision(task, round_id, "approver", "APPROVE", "ok")
    add_decision(task, round_id, "me", "CHANGES_REQUESTED", "no")
    decisions = flow(client, task)["nodes"]["approver"]["result"]["decisions"]
    assert [(d["actor"], d["decision"], d["body_html"]) for d in decisions] == [
        ("approver", "APPROVE", "<p>ok</p>\n"), ("me", "CHANGES_REQUESTED", "<p>no</p>\n")]


def test_transcripts_per_round(client, project):  # AC19, Q2
    task = in_progress(project, "agent_review")
    add_round(task, 1, at="2026-01-01T00:00:00Z")
    add_round(task, 2, at="2026-01-03T00:00:00Z")
    run = add_run(task, "succeeded")
    spec = add_transcript(run, task, "s.jsonl", agent_type="spec-writer", started_at="2025-12-31T00:00:00Z")
    built = add_transcript(run, task, "b1.jsonl", round=1, agent_type="builder")
    add_transcript(run, task, "b2.jsonl", round=2, agent_type="builder")
    reviewed = add_transcript(run, task, "r1.jsonl", agent_type="review-ux", started_at="2026-01-02T00:00:00Z")
    add_transcript(run, task, "r2.jsonl", agent_type="review-ux", started_at="2026-01-03T00:00:00Z")
    nodes = flow(client, task, "?round=1")["nodes"]
    ids = {i: [t["id"] for t in nodes[i]["result"]["transcripts"]] for i in ("spec-writer", "builder", "review-ux")}
    assert ids == {"spec-writer": [spec], "builder": [built], "review-ux": [reviewed]}
    row = nodes["builder"]["result"]["transcripts"][0]
    assert {"id", "input_tokens", "output_tokens", "cache_read_tokens", "started_at", "ended_at"} <= set(row)
    assert [t["id"] for t in flow(client, task, "?round=2")["nodes"]["spec-writer"]["result"]["transcripts"]] == [spec]


def test_custom_reviewer_from_the_log(client, project, tmp_path):  # AC20, through the handler
    design(client, project, "factory", "test-coverage")  # review-tests, focus custom
    task = in_progress(project, "agent_review")
    add_round(task, 1)
    run = add_run(task, "running")
    log = tmp_path / "run.jsonl"
    log.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "review-tests"}}]}}) + "\n")
    sql("UPDATE runs SET log_path = ? WHERE id = ?", (str(log), run))
    page = flow(client, task)
    assert states(page, "review-tests") == {"review-tests": ("running", "running")}
    assert current(page) == ["review-tests"]
