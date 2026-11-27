"""102: POST /api/factories/{id}/run, an automation run on the repo with no task, and how it shows afterwards
(docs/data-model-and-api.md §6.2, §6.4, docs/MVP.md §4.4)."""

import json
import os
import shutil
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from conftest import commit, git, sql, wt_calls
from controllers.test_pages_api import section
from controllers.test_run_accounts import ByDir, rate_limited, snapshot
from controllers.test_run_control import BASE, FIXTURE_ITEMS, FIXTURE_LOG, gone, reaped, stop, until
from controllers.test_runs import (FCTL_ALLOWED, H, OLD, add_running_run, add_task, allowed, cap,  # noqa: F401
                                   fake, project, project_path, run, steps, wait, worktrees)
from fastapi.testclient import TestClient
from handlers.test_transcripts import MAIN

from workcell.adapters.claude import SubprocessClaude
from workcell.lib.transcript import folder_name
from workcell.server.app import create_app
from workcell.server.deps import get_claude

AUTO_SKILL = ".claude/skills/security-audit/SKILL.md"
DISALLOWED = ["Bash(git commit *)", "Bash(git push *)", "Bash(git merge *)", "Bash(git rebase *)",
              "Bash(git reset *)", "Bash(git checkout *)"]
NOT_COMMITTED = ("automation Security audit isn't committed on main: open it, Files → Write to repo, then on main run"
                 ' git add .claude/skills/security-audit .claude/agents && git commit -m "Add factory"')


def add_factory(project_id, name="Security audit", kind="automation") -> int:
    return sql("INSERT INTO factories (project_id, name, kind, graph, created_at, updated_at)"
               " VALUES (?, ?, ?, '{}', ?, ?) RETURNING id", (project_id, name, kind, OLD, OLD))[0][0]


@pytest.fixture
def auto(client, project, repo):
    """The `Security audit` automation of `project`, its compiled skill committed on main."""
    commit(repo, {AUTO_SKILL: "# security-audit\n"})
    return add_factory(project)


def run_now(client, factory_id, body=None):
    kw = {"json": body} if body is not None else {}
    return client.post(f"/api/factories/{factory_id}/run", headers=H, **kw)


def started(client, factory_id, body=None) -> dict:
    r = run_now(client, factory_id, body)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    return r.json()


def runs_count() -> int:
    return sql("SELECT COUNT(*) FROM runs")[0][0]


def row(run_id) -> dict:
    cols = ("task_id", "factory_id", "kind", "trigger", "status", "account_id", "worktree_path", "error")
    return dict(zip(cols, sql(f"SELECT {', '.join(cols)} FROM runs WHERE id = ?", (run_id,))[0]))


def branches(repo) -> list[str]:
    return git(repo, "branch", "--list", "automation/*", "--format=%(refname:short)").split()


def automation_running(factory_id, worktree=None, session="s", account_id=None) -> int:
    return sql("INSERT INTO runs (task_id, factory_id, kind, session_id, status, log_path, started_at, worktree_path,"
               " account_id) VALUES (NULL, ?, 'automation', ?, 'running', 'l', ?, ?, ?) RETURNING id",
               (factory_id, session, OLD, worktree, account_id))[0][0]


# --- Start ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("body", [None, {}, {"account_id": None}])
def test_run_now(client, project, auto, repo, fake, body):  # AC3
    tasks_before, events_before = sql("SELECT * FROM tasks"), sql("SELECT * FROM events")
    r = run_now(client, auto, body)
    assert r.status_code == 202, r.text
    out = r.json()
    s8 = out["session_id"][:8]
    root = project_path(project)
    path = f"{root}/.claude/worktrees/automation-security-audit-{s8}"
    assert out == {"run_id": out["run_id"], "session_id": out["session_id"],
                   "worktree": f".claude/worktrees/automation-security-audit-{s8}", "account_id": 1,
                   "account": "claude-config"}
    wait(out["run_id"])
    assert row(out["run_id"]) | {"status": None} == {
        "task_id": None, "factory_id": auto, "kind": "automation", "trigger": "manual", "status": None,
        "account_id": 1, "worktree_path": path, "error": None}
    switch, copy = wt_calls()
    assert switch["argv"] == ["-C", root, "switch", "--create", f"automation/security-audit-{s8}", "--base", "main",
                              "--no-cd", "--no-hooks", "--format", "json"]
    assert f'worktree-path = "{path}"' in switch["config"].splitlines()
    assert copy["argv"] == ["-C", path, "step", "copy-ignored"]
    seen = fake.recorded("run")
    assert seen["cwd"] == os.path.realpath(path)
    assert seen["argv"][:4] == ["-p", "/security-audit", "--session-id", out["session_id"]]
    assert allowed(seen["argv"]) == FCTL_ALLOWED + ["Bash(pytest *)"]  # Q10: a task run's lists
    assert seen["argv"][seen["argv"].index("--disallowedTools") + 1:] == DISALLOWED
    assert (sql("SELECT * FROM tasks"), sql("SELECT * FROM events")) == (tasks_before, events_before)
    assert path in worktrees(repo)


@pytest.fixture
def long(client, fake):
    """long(factory_id) starts a long-running automation run and returns once its child is up; every one is
    stopped and reaped at teardown."""
    fake(long=True)
    ids = []

    def start(factory_id):
        fake.clear()
        r = run_now(client, factory_id)
        assert r.status_code == 202, r.text
        ids.append(r.json()["run_id"])
        until(lambda: fake.recorded("child"))
        return SimpleNamespace(run_id=r.json()["run_id"], body=r.json(), pid=fake.recorded("run")["pid"])

    yield start
    for run_id in ids:
        if row(run_id)["status"] == "running":
            stop(client, run_id)
        reaped(run_id)


def test_two_runs_side_by_side(client, auto, repo, long):  # AC4, Q5
    first, second = long(auto), long(auto)
    assert [row(r.run_id)["status"] for r in (first, second)] == ["running", "running"]
    assert first.body["worktree"] != second.body["worktree"]
    assert len(branches(repo)) == 2


@pytest.fixture
def accounts(client, project, tmp_path):
    """As test_run_accounts': account 1 (a@x, active) and 2 (b@y), both logged in."""
    one, two = os.environ["CLAUDE_CONFIG_DIR"], str(tmp_path / "account-2")
    sql("UPDATE claude_accounts SET email = 'a@x' WHERE id = 1")
    sql("INSERT INTO claude_accounts (config_dir, active, email, created_at) VALUES (?, 0, 'b@y', ?)", (two, OLD))
    claude = ByDir({one, two})
    client.app.dependency_overrides[get_claude] = lambda: claude
    return SimpleNamespace(one=one, two=two, claude=claude)


def test_explicit_account(client, auto, repo, accounts, fake):  # AC5
    snapshot(2, limited=True, status="rejected")
    before = runs_count()
    out = started(client, auto, {"account_id": 2})
    assert (out["account_id"], out["account"], row(out["run_id"])["account_id"]) == (2, "b@y", 2)
    assert fake.recorded("run")["env"]["CLAUDE_CONFIG_DIR"] == accounts.two
    r = run_now(client, auto, {"account_id": 99})
    assert (r.status_code, r.json()) == (422, {"detail": "no Claude account #99"})
    accounts.claude.logged_in = {accounts.one}
    r = run_now(client, auto, {"account_id": 2})
    assert (r.status_code, r.json()) == (409, {"detail": "Claude account b@y isn't logged in to claude.ai; log it in"
                                                         " under Settings → Claude accounts, or pick another"})
    assert runs_count() == before + 1
    assert len(branches(repo)) == 1  # AC10: the refused runs' worktrees and branches are gone again


def test_unknown_factory(client, project, fake):  # AC6
    r = run_now(client, 99)
    assert (r.status_code, r.json()) == (404, {"detail": "Factory #99 not found"})
    assert wt_calls() == [] and runs_count() == 0 and not fake.invoked()
    assert client.post(f"/api/factories/{add_factory(project)}/run").status_code == 403  # no X-Requested-By


def test_workflow_refused(client, project, fake):  # AC7
    workflow = add_factory(project, "Review loop", "workflow")
    r = run_now(client, workflow)
    assert (r.status_code, r.json()) == (409, {"detail": "Review loop is a workflow; run it on a task from the board"})
    assert wt_calls() == [] and runs_count() == 0 and not fake.invoked()


def cap_409(*listed, limit) -> dict:
    n = len(listed)
    return {"detail": f"{n} run{'' if n == 1 else 's'} active ({', '.join(listed)}); the limit is {limit}."
                      " Wait, stop one, or raise it in Settings"}


def test_cap(client, project, auto, fake):  # AC8, Q7
    task = add_task(project, status="in_progress")
    on_task = add_running_run(task)
    cap(1)
    r = run_now(client, auto)
    assert (r.status_code, r.json()) == (409, cap_409(f"#{on_task} on #{task}", limit=1))
    assert wt_calls() == [] and runs_count() == 1 and not fake.invoked()
    on_auto = automation_running(auto)
    gone = automation_running(add_factory(project, "Old"))
    sql("DELETE FROM factories WHERE name = 'Old'")  # ON DELETE SET NULL
    r = run_now(client, auto)
    assert r.json() == cap_409(f"#{on_task} on #{task}", f"#{on_auto} on automation Security audit",
                               f"#{gone} on automation (deleted)", limit=1)
    sql("UPDATE runs SET status = 'failed' WHERE id = ?", (on_task,))
    r = run(client, add_task(project))  # a task run at the cap counts automation runs too
    assert r.json() == cap_409(f"#{on_auto} on automation Security audit", f"#{gone} on automation (deleted)",
                               limit=1)
    assert wt_calls() == [] and not fake.invoked()


class FillsCap(SubprocessClaude):
    """The auth check passes, but meanwhile another start takes the last slot."""

    def __init__(self, factory_id):
        self.factory_id = factory_id

    def auth_status(self, cwd, env):
        automation_running(self.factory_id)
        return {"authMethod": "claude.ai"}


def test_cap_again_under_lock(client, auto, repo, fake):  # AC8: checked again under the write lock
    cap(1)
    client.app.dependency_overrides[get_claude] = lambda: FillsCap(auto)
    r = run_now(client, auto)
    assert r.status_code == 409 and r.json()["detail"].startswith("1 run active (#")
    assert runs_count() == 1 and not fake.invoked()
    assert steps() == ["switch", "step copy-ignored", "remove"] and branches(repo) == []


def test_skill_not_committed(client, project, repo, fake):  # AC9
    auto = add_factory(project)
    r = run_now(client, auto)
    assert (r.status_code, r.json()) == (409, {"detail": NOT_COMMITTED})
    assert wt_calls() == [] and runs_count() == 0 and not fake.invoked()
    commit(repo, {".claude/skills/security-audit/notes.md": "x"})  # a folder without SKILL.md isn't enough
    assert run_now(client, auto).json() == {"detail": NOT_COMMITTED}


def test_check_order(client, project, repo, fake, monkeypatch):  # AC10
    workflow, auto = add_factory(project, "Review loop", "workflow"), add_factory(project)
    task = add_task(project, status="in_progress")
    add_running_run(task)
    cap(1)
    assert run_now(client, workflow).json()["detail"].endswith("is a workflow; run it on a task from the board")
    assert run_now(client, auto).json()["detail"].startswith("1 run active")  # the cap before the skill
    cap(2)
    assert run_now(client, auto).json() == {"detail": NOT_COMMITTED}  # the skill before any wt call
    assert wt_calls() == []
    commit(repo, {AUTO_SKILL: "# security-audit\n"})
    monkeypatch.setenv("FAKE_WT_FAIL", "switch")  # wt refusals as 409s, unchanged
    assert run_now(client, auto).json() == {"detail": "wt switch failed: wt: switch broke"}
    assert steps() == ["switch"]
    monkeypatch.setenv("FAKE_WT_FAIL", "step copy-ignored")  # after the worktree: removed, then the branch
    r = run_now(client, auto)
    assert (r.status_code, r.json()) == (409, {"detail": "wt step copy-ignored failed: wt: step copy-ignored broke"})
    assert steps() == ["switch", "switch", "step copy-ignored", "remove"]
    assert wt_calls()[-1]["argv"][-1].startswith("automation/security-audit-")
    assert branches(repo) == [] and not fake.invoked() and runs_count() == 1


def test_cleanup_failure_ignored(client, auto, repo, fake, monkeypatch):  # AC10, Q6: the refusal stands
    fake(auth='{"authMethod":"console"}')
    monkeypatch.setenv("FAKE_WT_FAIL", "remove")
    r = run_now(client, auto)
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})
    assert steps()[-1] == "remove" and runs_count() == 0
    assert len(branches(repo)) == 1  # `branch -d` refuses a branch still checked out in its worktree


def test_auto_refusals(client, auto, accounts, fake):  # AC11
    accounts.claude.logged_in = set()
    r = run_now(client, auto)
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})
    resets, limited = snapshot(1, five=0.92), snapshot(2, limited=True)
    r = run_now(client, auto)
    hm, hm2 = (datetime.fromtimestamp(t).strftime("%H:%M") for t in (resets, limited))
    assert (r.status_code, r.json()) == (409, {"detail": f"all accounts near their limits: a@x 5h 92% (resets {hm}),"
                                                         f" b@y limited (resets {hm2})"})
    assert sql("SELECT COUNT(*) FROM runs WHERE kind = 'automation'") == [(0,)]


def test_spawn_fails(client, auto, fake, tmp_path, monkeypatch):  # AC12
    git_dir = os.path.dirname(os.path.realpath(shutil.which("git")))
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{git_dir}")
    fake(delete_self=True)
    r = run_now(client, auto)
    assert r.status_code == 500 and r.json()["detail"].startswith("can't start claude: ")
    [(status, error)] = sql("SELECT status, error FROM runs WHERE kind = 'automation'")
    assert (status, error) == ("failed", r.json()["detail"])


# --- The run's lifecycle ----------------------------------------------------------------------------------


def test_exit_like_a_task_run(client, auto, accounts, fake):  # AC13
    assert row(started(client, auto)["run_id"])["status"] == "succeeded"
    resets = int(time.time()) + 7200
    fake(lines=[rate_limited(resets), json.dumps({"type": "result", "is_error": True, "result": "limit"})], code=1)
    run_id = started(client, auto, {"account_id": 2})["run_id"]
    assert (row(run_id)["status"], row(run_id)["error"]) == (
        "failed", f"limited on b@y, resets at {datetime.fromtimestamp(resets).strftime('%H:%M')}")
    assert sql("SELECT account_id, limited FROM usage_snapshots WHERE run_id = ?", (run_id,)) == [(2, 1)]


def plant(worktree, session) -> None:
    """The run's main transcript, in its worktree's folder under the account's config dir."""
    path = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "projects", folder_name(worktree), f"{session}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(MAIN)


def test_stop_collects_transcripts(client, auto, long):  # AC14
    s = long(auto)
    plant(row(s.run_id)["worktree_path"], s.body["session_id"])
    r = stop(client, s.run_id)
    assert (r.status_code, r.json()) == (200, {"id": s.run_id, "status": "stopped"})
    assert until(lambda: (got := row(s.run_id))["status"] == "stopped" and got)
    assert sql("SELECT task_id, path FROM transcripts WHERE run_id = ?", (s.run_id,)) == [
        (None, f"{s.run_id}/{s.body['session_id']}.jsonl")]
    assert gone(s.pid)  # SIGTERM to the process group


def test_startup_and_log(client, auto, tmp_path):  # AC15
    worktree, session = str(tmp_path / "wt"), "6f1c2e0a-1111-2222-3333-444455556666"
    run_id = automation_running(auto, worktree, session, account_id=1)
    log = tmp_path / "run.jsonl"
    log.write_text(FIXTURE_LOG)
    sql("UPDATE runs SET log_path = ? WHERE id = ?", (str(log), run_id))
    plant(worktree, session)
    with TestClient(create_app(), base_url=BASE):
        assert (row(run_id)["status"], row(run_id)["error"]) == ("failed", "app restarted")
    assert sql("SELECT task_id FROM transcripts WHERE run_id = ?", (run_id,)) == [(None,)]
    r = client.get(f"/api/runs/{run_id}/log")
    assert r.json() == {"next": 8, "lines": FIXTURE_ITEMS}
    assert client.get(f"/api/runs/{run_id}/log?after=8").json() == {"next": 8, "lines": []}


# --- Pages ------------------------------------------------------------------------------------------------


def test_agents_running(client, project, auto):  # AC16
    task = add_task(project, "Webhooks", status="in_progress", stage="build")
    on_task = add_running_run(task)
    on_auto = automation_running(auto)
    page = client.get("/api/pages/agents").json()
    by_id = {r["id"]: r for r in page["running"]}
    assert by_id[on_auto] == {"id": on_auto, "kind": "automation", "task_id": None, "factory_id": auto,
                              "title": "Security audit", "project_id": project, "project": "repo", "stage": None,
                              "round": None, "started_at": OLD, "agents": by_id[on_auto]["agents"]}
    assert by_id[on_auto]["agents"][0]["name"] == "orchestrator"
    assert (by_id[on_task]["kind"], by_id[on_task]["factory_id"], by_id[on_task]["title"]) == (
        "factory", None, "Webhooks")


def test_agents_recent_and_deleted(client, project, auto):  # AC17, Q9
    ended = automation_running(auto)
    sql("UPDATE runs SET status = 'succeeded', ended_at = ? WHERE id = ?", ("2026-10-21T10:00:00Z", ended))
    sql("INSERT INTO transcripts (run_id, task_id, path, turns, input_tokens, cache_read_tokens, output_tokens)"
        " VALUES (?, NULL, 'x.jsonl', 1, 1, 1, 1)", (ended,))
    [recent] = client.get("/api/pages/agents").json()["recent"]
    assert {k: recent[k] for k in ("id", "kind", "task_id", "factory_id", "title", "project_id", "project",
                                   "transcripts")} == {
        "id": ended, "kind": "automation", "task_id": None, "factory_id": auto, "title": "Security audit",
        "project_id": project, "project": "repo", "transcripts": 1}
    running = automation_running(auto)
    assert client.delete(f"/api/factories/{auto}", headers=H).status_code == 204
    page = client.get("/api/pages/agents").json()
    for item in (page["running"][0], page["recent"][0]):
        assert (item["title"], item["factory_id"], item["project_id"], item["project"]) == (
            "deleted automation", None, None, None)
    assert stop(client, running).json() == {"id": running, "status": "stopped"}  # Q9: still stoppable


def test_other_pages_unchanged(client, project, auto, repo):  # AC18, Q15
    task = add_task(project, "Webhooks", status="in_progress")
    sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at) VALUES (?, 's', 'succeeded', 'l', ?)",
        (task, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    automation_running(auto)
    ended = automation_running(auto)
    sql("UPDATE runs SET status = 'failed', ended_at = started_at WHERE id = ?", (ended,))
    week = client.get("/api/pages/dashboard?show=runs_week")
    assert week.status_code == 200 and [r["task_id"] for r in week.json()["listed"]] == [task]
    for url in ("/api/pages/sidebar", "/api/usage", f"/api/pages/projects/{project}"):
        assert client.get(url).status_code == 200, url
    assert client.delete(f"/api/factories/{auto}", headers=H).status_code == 204
    assert sql("SELECT DISTINCT factory_id FROM runs WHERE kind = 'automation'") == [(None,)]
    other = add_factory(project, "Nightly")
    automation_running(other)
    assert client.delete(f"/api/projects/{project}", headers=H).status_code == 204
    assert sql("SELECT factory_id FROM runs") == [(None,)] * 3


def test_board_run_menu(client, project, accounts):  # AC19, Q12
    snapshot(1, five=0.95)
    page = client.get(f"/api/pages/projects/{project}").json()
    assert page["runs_enabled"] is True
    assert [(a["id"], a["label"], a["active"]) for a in page["accounts"]] == [(1, "a@x", True), (2, "b@y", False)]
    assert page["accounts"][0]["five_hour"]["utilization"] == 0.95
    assert page["auto"] == {"account_id": 2, "label": "b@y"}
    for key in ("project", "columns", "factory", "hint", "can_run", "runs_active", "max_concurrent_runs"):
        assert key in page


def test_docs():  # AC31
    tables = section("data-model-and-api.md", "### 5.1")
    for text in ("kind TEXT NOT NULL DEFAULT 'factory'", "trigger TEXT NOT NULL DEFAULT 'manual'", "worktree_path TEXT",
                 "CHECK ((kind = 'factory') = (task_id IS NOT NULL))", "12-step rebuild", "An automation (a factory"):
        assert text in tables, text
    runs = section("data-model-and-api.md", "### 6.2")
    for text in ("POST /api/factories/7/run", "Review loop is a workflow; run it on a task from the board",
                 "#43 on automation Security audit", "automation/<slug>-<s8>", "isn't committed on main: open it"):
        assert text in runs, text
    pages = section("data-model-and-api.md", "### 6.4")
    for text in ('"factory_id":null', '"kind":"factory","task_id":11', "deleted automation", "runs_enabled"):
        assert text in pages, text
    mvp = section("MVP.md", "### 4.4")
    assert "An automation's run (102)" in mvp and 'claude -p "/security-audit"' in mvp
    # 104 AC32: Scheduled runs moved from Later to MVP, so §9 now lists Run now beside it
    assert "**Run now** on an automation" in section("MVP.md", "## 9.")
    ui = section("ui.md", "## 8.")
    for text in ("Not signed in — runs disabled", "2 of 2 runs active", "Started run #43 as b@y.", "deleted automation",
                 "automation  Security audit"):
        assert text in ui, text
