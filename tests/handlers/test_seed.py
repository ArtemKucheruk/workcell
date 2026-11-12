"""038: what `fctl seed` writes, read back through the view-models (docs/data-model-and-api.md §6.4). The
module shares one seeded FCTL_HOME, since seeding runs dozens of git commands."""

import json
import os
import shlex
import sys
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

import pytest
from conftest import FAKE_WT, git, sql

from claude_factories.cli import git as cli_git
from claude_factories.cli.main import main
from claude_factories.lib.slug import slug

REVIEWERS = ("security", "ux", "ui", "code")


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """The seeded FCTL_HOME, made with conftest.isolated's git isolation (that fixture is per test)."""
    tmp = tmp_path_factory.mktemp("seed")
    (tmp / "gitconfig").write_text("")
    (tmp / "bin").mkdir()
    wt = tmp / "bin" / "wt"  # 099 AC8: conftest's fake wt, recording to tmp/wt-log
    wt.write_text(FAKE_WT.replace("PYTHON", sys.executable))
    wt.chmod(0o755)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("PATH", f"{tmp / 'bin'}{os.pathsep}{os.environ['PATH']}")
        mp.setenv("FAKE_WT_LOG", str(tmp / "wt-log"))
        mp.setenv("FCTL_HOME", str(tmp / "fctl-home"))
        mp.setenv("HOME", str(tmp))
        mp.setenv("CLAUDE_CONFIG_DIR", str(tmp / "claude-config"))  # 056: the seed's db.init() makes it account 1
        mp.setenv("GIT_CONFIG_GLOBAL", str(tmp / "gitconfig"))
        mp.setenv("GIT_CONFIG_NOSYSTEM", "1")
        main(["seed"])
    return tmp / "fctl-home"


@pytest.fixture(autouse=True)
def home(seeded, monkeypatch):
    """After conftest.isolated: every test reads the seeded home."""
    monkeypatch.setenv("FCTL_HOME", str(seeded))
    page.cache_clear()


@cache
def page(client, url: str):
    r = client.get(url)
    assert r.status_code == 200, (url, r.text)
    return r.json() if r.headers["content-type"].startswith("application/json") else r.text


def projects(client) -> list[dict]:
    """Every workspace page's project rows, each with its factory state."""
    return [p for w in page(client, "/api/workspaces")
            for p in page(client, f"/api/pages/workspaces/{w['id']}")["projects"]]


def cards(client) -> list[dict]:
    """Every board card, with its project's row as `project`."""
    return [c | {"project": p} for p in projects(client)
            for column in page(client, f"/api/pages/projects/{p['id']}")["columns"].values() for c in column]


def task_page(client, task_id: int) -> dict:
    return page(client, f"/api/pages/tasks/{task_id}")


def review_page(client, task_id: int, n="latest") -> dict:
    return page(client, f"/api/pages/tasks/{task_id}/review?round={n}")


def at(client, status: str, stage: str | None, factory: bool = True) -> list[dict]:
    """The task pages at (status, stage), factory tasks (with a worktree) or not."""
    found = [task_page(client, c["id"]) for c in cards(client) if (c["status"], c["stage"]) == (status, stage)]
    return [t for t in found if (t["task"]["worktree_path"] is not None) == factory]


def one(client, status: str, stage: str | None, factory: bool = True) -> dict:
    [found] = at(client, status, stage, factory)
    return found


def with_rounds(client) -> list[dict]:
    return [t for t in (task_page(client, c["id"]) for c in cards(client)) if t["rounds"]]


def card(client, task_id: int) -> dict:
    [found] = [c for c in cards(client) if c["id"] == task_id]
    return found


def verdicts(r: dict) -> list[str]:
    return [r["verdicts"][who] for who in REVIEWERS]


# --- Projects and repos ----------------------------------------------------------------------


def test_workspaces_and_factory_states(client):  # AC8
    workspaces = page(client, "/api/workspaces")
    assert len(workspaces) == 2
    assert sum(w["projects"] for w in workspaces) == 3
    assert sorted(p["factory"] for p in projects(client)) == ["none", "ready", "uncommitted"]


def test_projects_are_demo_repos(client, seeded):  # AC9
    for p in projects(client):
        assert p["path"].startswith(f"{seeded}/demo/")
        assert git(p["path"], "branch", "--show-current") == "main"
        assert int(git(p["path"], "rev-list", "--count", "main")) >= 3
        code = page(client, f"/api/pages/projects/{p['id']}/code")
        assert code["error"] is None
        assert code["branch"] == "main"
        assert code["readme_html"]
        assert any(key.endswith("/") for key in code["tree"])


def test_binary_and_big_files(client):  # AC10
    notes = {}
    for p in projects(client):
        for name in git(p["path"], "ls-files").splitlines():
            r = client.get(f"/api/pages/projects/{p['id']}/code", params={"path": name})
            notes.setdefault(p["id"], []).append(r.json()["view"])
    assert any({"note": "Binary file not shown."} in views and {"note": "File over 1 MB not shown."} in views
               for views in notes.values())


def test_one_project_context(client):  # AC11
    contexts = {p["id"]: page(client, f"/api/projects/{p['id']}/context")["context_md"] for p in projects(client)}
    [with_context] = [project_id for project_id, md in contexts.items() if md]
    task = next(c for c in cards(client) if c["project"]["id"] == with_context)
    assert page(client, f"/api/tasks/{task['id']}/context").startswith("## Project context\n")


def test_context_cards(client, seeded):  # 057 BE22
    by_name = {p["name"]: p for p in projects(client)}
    api = by_name.pop("api-server")
    items = page(client, f"/api/projects/{api['id']}/context/items")
    top = [i for i in items if i["parent_id"] is None]
    assert len([i for i in top if i["kind"] == "item"]) >= 2
    [g] = [i for i in top if i["kind"] == "group"]
    children = [i for i in items if i["parent_id"] == g["id"]]
    assert len(children) >= 2
    [read] = [i for i in items if i["source_path"]]
    assert read["source_path"].startswith(f"{seeded}/demo/api-server/") and read["parent_id"] is None
    assert Path(read["source_path"]).read_text(encoding="utf-8") == read["content_md"]
    task = next(c for c in cards(client) if c["project"]["id"] == api["id"])
    assert f"\n### {g['title']}\n\n#### {children[0]['title']}\n" in page(client, f"/api/tasks/{task['id']}/context")
    for other in by_name.values():
        assert page(client, f"/api/projects/{other['id']}/context/items") == []
    # the summary line counts only these, so it is unchanged: fctl.md's example line
    counts = [sql(f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("workspaces", "projects", "tasks", "runs")]
    assert "{} workspaces, {} projects, {} tasks, {} runs".format(*counts) in (
        Path(__file__).parents[2] / "src" / "claude_factories" / "fctl.md").read_text(encoding="utf-8")


def test_ready_checkout_is_clean(client):  # AC12
    [ready] = [p for p in projects(client) if p["factory"] == "ready"]
    assert git(ready["path"], "status", "--porcelain") == ""
    exclude = git(ready["path"], "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
    assert ".claude/worktrees/" in Path(exclude).read_text().splitlines()
    assert len(git(ready["path"], "worktree", "list").splitlines()) > 1


# --- Tasks -----------------------------------------------------------------------------------


def test_every_status_and_stage(client):  # AC13
    pairs = {(c["status"], c["stage"]) for c in cards(client)}
    assert pairs >= {("backlog", None), ("in_progress", "spec"), ("in_progress", "build"),
                     ("in_progress", "agent_review"), ("in_progress", "approval"), ("in_progress", "rework"),
                     ("review", "human_review"), ("review", "escalated"), ("done", None)}


def test_backlog_descriptions_are_markdown(client):  # AC14
    backlog = [task_page(client, c["id"]) for c in cards(client) if c["status"] == "backlog"]
    assert len(backlog) >= 2
    for t in backlog:
        html = t["task"]["description_html"]
        assert any(tag in html for tag in ("<ul>", "<ol>", "<code>", "<strong>", "<h2>", "<h3>")), t["task"]["id"]


def test_one_stalled_card(client):  # AC15
    [stalled] = [c for c in cards(client) if c["stalled"]]
    assert stalled["stage"] == "build"
    run = task_page(client, stalled["id"])["run"]
    assert run["status"] == "failed"
    assert run["error"]


def test_waiting_factory_task(client):  # AC16
    t = one(client, "review", "human_review")
    r1, r2 = t["rounds"]
    assert "CHANGES" in verdicts(r1)
    assert verdicts(r2) == ["PASS"] * 4 and r2["trigger"] == "agent"
    assert (t["approver"]["decision"], t["approver"]["n"]) == ("APPROVE", 2)
    assert card(client, t["task"]["id"])["waiting"] is True


def test_escalated_task(client):  # AC17
    t = one(client, "review", "escalated")
    latest = t["rounds"][-1]
    assert "CHANGES" in verdicts(latest)
    assert (t["approver"]["decision"], t["approver"]["n"]) == ("ESCALATE", latest["n"])
    assert card(client, t["task"]["id"])["escalated"] is True


def test_rework_task(client):  # AC18
    t = one(client, "in_progress", "rework")
    task_id, latest = t["task"]["id"], t["rounds"][-1]["n"]
    last = page(client, f"/api/tasks/{task_id}")["decisions"][-1]
    assert (last["actor"], last["decision"], last["round"]) == ("me", "CHANGES_REQUESTED", latest)
    assert last["body_md"].strip()
    feedback = page(client, f"/api/tasks/{task_id}/context?feedback=1")
    assert f"## Feedback on round {latest}\n" in feedback
    assert "\n### me on " in feedback


def test_spec_task(client):  # AC19
    t = one(client, "in_progress", "spec", factory=False)
    assert t["task"]["spec_md"] is None
    assert t["rounds"] == []


def test_agent_review_task(client):  # AC20
    latest = verdicts(one(client, "in_progress", "agent_review")["rounds"][-1])
    assert 1 <= sum(v != "pending" for v in latest) <= 3


def test_approval_task(client):  # AC21
    t = one(client, "in_progress", "approval")
    assert "pending" not in verdicts(t["rounds"][-1])
    assert t["approver"] is None


def test_standalone_task(client):  # AC22
    t = one(client, "review", "human_review", factory=False)
    assert t["task"]["branch"] is None and t["task"]["worktree_path"] is None
    [r] = t["rounds"]
    assert r["trigger"] == "initial" and verdicts(r) == ["pending"] * 4
    assert t["run"] is None


def test_done_tasks(client):  # AC23
    now = datetime.now(UTC)
    done = at(client, "done", None)
    ages = [now - datetime.fromisoformat(done_at) for (done_at,) in sql("SELECT done_at FROM tasks WHERE done_at")]
    assert any(age < timedelta(days=7) for age in ages)
    assert any(timedelta(days=7) < age < timedelta(days=30) for age in ages)
    for t in done:
        task_id = t["task"]["id"]
        assert t["rounds"]
        decisions = page(client, f"/api/tasks/{task_id}")["decisions"]
        assert ("me", "APPROVE") in [(d["actor"], d["decision"]) for d in decisions]
        assert review_page(client, task_id)["task"]["commit_hint"]


def test_round_triggers(client):  # AC24
    seen = set()
    for t in with_rounds(client):
        task_id = t["task"]["id"]
        mine = {d["round"] for d in page(client, f"/api/tasks/{task_id}")["decisions"]
                if (d["actor"], d["decision"]) == ("me", "CHANGES_REQUESTED")}
        for r in t["rounds"]:
            assert r["trigger"] == ("initial" if r["n"] == 1 else "human" if r["n"] - 1 in mine else "agent")
            seen.add(r["trigger"])
    assert seen == {"initial", "agent", "human"}


def test_markdown_bodies(client):  # AC25
    for t in with_rounds(client):
        task_id = t["task"]["id"]
        for r in t["rounds"]:
            assert all(v["body_md"].strip() for v in r["posted"].values())
        for d in page(client, f"/api/tasks/{task_id}")["decisions"]:
            assert d["actor"] == "me" or d["body_md"].strip()
        if t["task"]["worktree_path"] is None:  # the standalone
            continue
        assert t["task"]["spec_html"].strip()
        assert all(r["build_html"].strip() for r in t["rounds"])


def test_dashboard(client):  # AC26
    dash = page(client, "/api/pages/dashboard")
    counts = dash["counts"]
    for key in ("backlog", "in_progress", "review", "done", "waiting", "escalated", "done_week", "runs_week"):
        assert counts[key] >= 1, key
    assert counts["running"] == 0
    assert counts["done"] > counts["done_week"]
    assert sql("SELECT COUNT(*) FROM runs")[0][0] > counts["runs_week"]
    assert len(dash["done"]) >= 2 and len({d["rounds"] for d in dash["done"]}) >= 2
    assert len(dash["open_tasks"]) == 2


# --- Diffs and comments ------------------------------------------------------------------------


def test_every_change_kind(client):  # AC27
    files = review_page(client, one(client, "review", "human_review")["task"]["id"])["files"]
    assert {f["change"] for f in files} >= {"added", "modified", "deleted", "renamed"}
    assert all(f["old_path"] for f in files if f["change"] == "renamed")
    assert any(f["binary"] for f in files)


def test_worktrees(client):  # AC28
    standalone = one(client, "review", "human_review", factory=False)["task"]["id"]
    found = [task_page(client, c["id"]) | {"path": c["project"]["path"]} for c in cards(client)
             if (c["run"] or c["round"]) and c["id"] != standalone]
    assert len(found) >= 9
    for t in found:
        name = f"{t['task']['id']}-{slug(t['task']['title'])}"
        assert t["task"]["branch"] == f"factory/{name}"
        assert t["task"]["worktree_path"] == f"{t['path']}/.claude/worktrees/{name}"
        listed = git(t["path"], "worktree", "list", "--porcelain")
        assert f"worktree {t['task']['worktree_path']}\nHEAD " in listed
        assert git(t["task"]["worktree_path"], "branch", "--show-current") == t["task"]["branch"]


def test_worktrees_through_wt_switch(seeded):  # 099 AC8, Q4
    calls = [json.loads(line)["argv"] for line in (seeded.parent / "wt-log").read_text().splitlines()]
    assert calls and all(argv[2:4] == ["switch", "--create"] for argv in calls)  # no copy-ignored step
    assert all(argv[-6:] == ["--base", "main", "--no-cd", "--no-hooks", "--format", "json"] for argv in calls)


def test_diffs_match_the_trees(client, monkeypatch):  # AC29
    for c in cards(client):
        t = task_page(client, c["id"])
        if not t["rounds"]:
            continue
        monkeypatch.chdir(t["task"]["worktree_path"] or c["project"]["path"])  # Q1: the standalone's main checkout
        base_sha, patch = cli_git.capture()
        assert page(client, f"/api/tasks/{c['id']}/rounds/latest/diff") == patch, c["id"]
        [(stored,)] = sql("SELECT base_sha FROM rounds WHERE task_id = ? ORDER BY n DESC LIMIT 1", (c["id"],))
        assert stored == base_sha


def test_inline_comments(client):  # AC30
    comments = []
    for t in with_rounds(client):
        for r in t["rounds"]:
            for f in review_page(client, t["task"]["id"], r["n"])["files"]:
                assert f["orphans"] == [], (t["task"]["id"], r["n"], f["path"])
                comments += [c for row in f["rows"] for c in row["comments"]]
    assert {c["author"] for c in comments} & set(REVIEWERS)
    assert "me" in {c["author"] for c in comments}
    assert {c["side"] for c in comments} == {"old", "new"}


def test_conversation_comment(client):  # AC31
    entries = [e for t in with_rounds(client) for e in review_page(client, t["task"]["id"])["timeline"]]
    assert any(e["kind"] == "comment" and " on " not in e["label"] for e in entries)


# --- Runs ----------------------------------------------------------------------------------------


def runs() -> list[dict]:
    rows = sql("SELECT id, task_id, status, error, session_id, exit_code, log_path FROM runs ORDER BY id")
    return [dict(zip(("id", "task_id", "status", "error", "session_id", "exit_code", "log_path"), r)) for r in rows]


def log_events(run: dict) -> list[dict]:
    return [json.loads(line) for line in Path(run["log_path"]).read_text().splitlines()]


def test_run_statuses_and_takeover(client, seeded):  # AC32
    rows = runs()
    named = shlex.quote(str(seeded.parent / "claude-config"))  # 056: the active account
    assert {r["status"] for r in rows} == {"succeeded", "failed", "stopped"}
    latest = {r["task_id"]: r for r in rows}  # by id, so the last one wins
    for status in ("succeeded", "failed", "stopped"):
        run = next(r for r in latest.values() if r["status"] == status)
        t = task_page(client, run["task_id"])
        assert t["run"]["status"] == status
        wt = t["task"]["worktree_path"]
        assert t["takeover"] == (f"cd {shlex.quote(wt)} && CLAUDE_CONFIG_DIR={named} claude"
                                 f" --resume {shlex.quote(run['session_id'])}")


def test_run_logs(client, seeded):  # AC33
    for run in runs():
        assert run["log_path"] == f"{seeded}/runs/{run['id']}.jsonl"
        assert Path(run["log_path"]).is_file()
        kinds = {line["t"] for line in page(client, f"/api/runs/{run['id']}/log")["lines"]}
        assert {"text", "tool"} <= kinds
        types = [e["type"] for e in log_events(run)]
        if run["status"] == "stopped":
            assert "result" not in types
        else:
            assert types[-1] == "result"


def test_runs_match_their_logs():  # AC34
    for run in runs():
        results = [e for e in log_events(run) if e["type"] == "result"]
        if run["status"] == "stopped":
            assert results == [] and run["error"] is None
            continue
        event = results[-1]
        assert event["session_id"] == run["session_id"]
        if run["status"] == "succeeded":
            assert not event.get("is_error") and run["exit_code"] == 0
        else:
            assert event["is_error"] and run["error"] == event["result"]


# --- History and time ----------------------------------------------------------------------------


def test_history(client):  # AC35
    for c in cards(client):
        t = task_page(client, c["id"])
        labels = [e["label"] for e in t["history"]]
        assert labels[0].startswith("created · ")
        current = t["task"]["status"] + (f" · {t['task']['stage']}" if t["task"]["stage"] else "")
        assert labels[-1].removeprefix("created · ") == current, labels


def test_timestamps():  # AC36
    now = datetime.now(UTC)
    tables = {"workspaces": ("created_at",), "projects": ("created_at",),
              "tasks": ("created_at", "updated_at", "done_at"), "runs": ("started_at", "ended_at"),
              "rounds": ("created_at",), "verdicts": ("created_at",), "comments": ("created_at",),
              "decisions": ("created_at",), "events": ("created_at",)}
    for table, columns in tables.items():
        for column in columns:
            stamps = [s for (s,) in sql(f"SELECT {column} FROM {table}") if s is not None]
            assert stamps, (table, column)
            for s in stamps:
                assert now - timedelta(days=30) < datetime.fromisoformat(s) <= now, (table, column, s)
