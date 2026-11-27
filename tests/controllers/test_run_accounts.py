"""097: which Claude account a run uses: Auto or an explicit pick on start, and the run's own account afterwards
(AC9–AC26)."""

import json
import os
import shlex
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from conftest import sql
from controllers.test_pages_api import add_round, section
from controllers.test_run_control import NOTE
from controllers.test_runs import H, OLD, add_task, fake, project, task_row, wait  # noqa: F401
from handlers.test_transcripts import MAIN, SID

from workcell.adapters.claude import SubprocessClaude
from workcell.handlers import runs as runs_handler
from workcell.handlers.transcripts import collect
from workcell.lib.transcript import folder_name
from workcell.repositories.usage import UsageRepo
from workcell.server.deps import get_claude, transaction


class ByDir(SubprocessClaude):
    """`claude auth status` answers claude.ai only for the config dirs in `logged_in`; `checked` lists each call's
    dir in order. Spawning is the real adapter's, so the fake `claude` binary records the run."""

    def __init__(self, logged_in):
        self.logged_in, self.checked = set(logged_in), []

    def auth_status(self, cwd, env):
        self.checked.append(env["CLAUDE_CONFIG_DIR"])
        return {"authMethod": "claude.ai"} if env["CLAUDE_CONFIG_DIR"] in self.logged_in else None


@pytest.fixture
def accounts(client, project, tmp_path):
    """Account 1 (the server's CLAUDE_CONFIG_DIR, active, a@x) and account 2 (b@y), both logged in."""
    one, two = os.environ["CLAUDE_CONFIG_DIR"], str(tmp_path / "account-2")
    sql("UPDATE claude_accounts SET email = 'a@x' WHERE id = 1")
    sql("INSERT INTO claude_accounts (config_dir, active, email, created_at) VALUES (?, 0, 'b@y', ?)", (two, OLD))
    claude = ByDir({one, two})
    client.app.dependency_overrides[get_claude] = lambda: claude
    return SimpleNamespace(one=one, two=two, claude=claude, project=project)


def snapshot(account_id, five=0.1, seven=0.1, limited=False, status="allowed", five_resets=None):
    """A usage snapshot for the account, on a succeeded run of its own done task; its 5h resets_at."""
    task = add_task(1, "usage", status="done")
    run_id = sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at, account_id)"
                 " VALUES (?, 's', 'succeeded', 'l', ?, ?) RETURNING id", (task, OLD, account_id))[0][0]
    later = int(time.time()) + 3600
    sql("INSERT INTO usage_snapshots (run_id, account_id, five_hour_utilization, five_hour_resets_at,"
        " five_hour_status, seven_day_utilization, seven_day_resets_at, seven_day_status, status, overage, limited,"
        " recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'allowed', NULL, 0, ?, ?)",
        (run_id, account_id, five, five_resets or later, status, seven, later + 86400, int(limited),
         f"2026-10-01T00:00:{run_id:02d}Z"))
    return later


def post(client, task, body=None):
    kw = {"json": body} if body is not None else {}
    return client.post(f"/api/tasks/{task}/run", headers=H, **kw)


def ran_on(client, task, body=None) -> int:
    """A successful start, waited for; the run's account_id."""
    r = post(client, task, body)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    return sql("SELECT account_id FROM runs WHERE id = ?", (r.json()["run_id"],))[0][0]


def task_runs(task):
    return sql("SELECT COUNT(*) FROM runs WHERE task_id = ?", (task,))[0][0]


@pytest.mark.parametrize("body", [None, {}, {"account_id": None}])
def test_auto_by_default(client, accounts, fake, body):  # AC9
    task = add_task(accounts.project)
    assert ran_on(client, task, body) == 1
    assert accounts.claude.checked == [accounts.one]


def test_auto_skips_logged_out(client, accounts, fake):  # AC10
    accounts.claude.logged_in = {accounts.two}
    assert ran_on(client, add_task(accounts.project)) == 2
    assert accounts.claude.checked == [accounts.one, accounts.two]


def test_auto_all_low(client, accounts, fake):  # AC11
    resets = snapshot(1, five=0.92)
    limited = snapshot(2, limited=True)
    task = add_task(accounts.project)
    r = post(client, task)
    hm = datetime.fromtimestamp(resets).strftime("%H:%M")
    hm2 = datetime.fromtimestamp(limited).strftime("%H:%M")
    assert (r.status_code, r.json()) == (409, {"detail": f"all accounts near their limits: a@x 5h 92% (resets {hm}),"
                                                         f" b@y limited (resets {hm2})"})
    assert task_runs(task) == 0 and not fake.recorded("run")
    assert accounts.claude.checked == []  # no non-low candidate to check


def test_auto_without_accounts(client, accounts, fake):  # AC12
    task = add_task(accounts.project)
    accounts.claude.logged_in = set()
    r = post(client, task)
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})
    sql("DELETE FROM claude_accounts WHERE id = 2")
    sql("UPDATE claude_accounts SET active = 0")
    accounts.claude.logged_in = {accounts.one}
    assert ran_on(client, task) == 1  # no active account, but a logged-in one: Auto runs on it
    sql("DELETE FROM claude_accounts")
    r = post(client, add_task(accounts.project))
    assert (r.status_code, r.json()) == (409, {"detail": "not on subscription auth"})


def test_explicit_pick_even_when_low(client, accounts, fake):  # AC13, Q4
    snapshot(2, limited=True, status="rejected")
    task = add_task(accounts.project)
    assert ran_on(client, task, {"account_id": 2}) == 2
    assert accounts.claude.checked == [accounts.two]


def test_explicit_pick_logged_out(client, accounts, fake):  # AC14
    accounts.claude.logged_in = {accounts.one}
    task = add_task(accounts.project)
    r = post(client, task, {"account_id": 2})
    assert (r.status_code, r.json()) == (409, {"detail": "Claude account b@y isn't logged in to claude.ai; log it in"
                                                         " under Settings → Claude accounts, or pick another"})
    assert task_runs(task) == 0 and not fake.recorded("run")


def test_explicit_pick_unknown(client, accounts, fake):  # AC15, Q5
    task = add_task(accounts.project)
    r = post(client, task, {"account_id": 99})
    assert (r.status_code, r.json()) == (422, {"detail": "no Claude account #99"})
    assert post(client, task, {"account_id": "x"}).status_code == 422
    assert task_runs(task) == 0 and not fake.recorded("run")


def test_account_check_after_earlier_checks(client, accounts, fake):  # AC16
    r = post(client, 999, {"account_id": 99})
    assert (r.status_code, r.json()) == (404, {"detail": "no task #999"})
    review = add_task(accounts.project, status="review", stage="human_review")
    r = post(client, review, {"account_id": 99})
    assert (r.status_code, r.json()) == (409, {"detail": f"#{review} is in review"})
    task = add_task(accounts.project)
    assert post(client, task, {"account_id": 99}).status_code == 422
    assert task_row(task)["worktree_path"]  # the worktree came first, as before the auth check
    assert accounts.claude.checked == []


def test_env_and_trust_in_chosen_account(client, accounts, fake):  # AC17
    task = add_task(accounts.project)
    ran_on(client, task, {"account_id": 2})
    assert fake.recorded("run")["env"]["CLAUDE_CONFIG_DIR"] == accounts.two
    with open(os.path.join(accounts.two, ".claude.json")) as f:
        trusted = json.load(f)
    repo_path = sql("SELECT path FROM projects WHERE id = ?", (accounts.project,))[0][0]
    assert trusted["projects"][repo_path]["hasTrustDialogAccepted"] is True


def test_started_names_account(client, accounts, fake):  # AC18
    r = post(client, add_task(accounts.project), {"account_id": 2})
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    assert (r.json()["account_id"], r.json()["account"]) == (2, "b@y")


def test_run_next_is_auto(client, accounts, fake):  # AC19
    snapshot(1, five=0.95)
    task = add_task(accounts.project, "next")
    r = client.post(f"/api/projects/{accounts.project}/run-next", json={"account_id": 1}, headers=H)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    assert r.json() == {"task_id": task, "run_id": r.json()["run_id"], "account_id": 2, "account": "b@y"}


def test_retry_reruns_auto(client, accounts, fake):  # AC20
    task = add_task(accounts.project)
    assert ran_on(client, task) == 1
    snapshot(1, five=0.9)
    assert ran_on(client, task) == 2


def test_rework_run_is_auto(client, accounts, fake):  # AC21, Q6
    task = add_task(accounts.project)
    assert ran_on(client, task) == 1
    sql("UPDATE tasks SET status = 'review', stage = 'human_review' WHERE id = ?", (task,))
    add_round(task, 1)
    snapshot(1, limited=True)
    r = client.post(f"/api/tasks/{task}/request-changes", json={"body_md": NOTE}, headers=H)
    assert r.status_code == 202, r.text
    wait(r.json()["run_id"])
    assert sql("SELECT account_id FROM runs WHERE id = ?", (r.json()["run_id"],)) == [(2,)]


def page(client, task):
    r = client.get(f"/api/pages/tasks/{task}")
    assert r.status_code == 200, r.text
    return r.json()


def test_takeover_uses_runs_account(client, accounts, fake):  # AC22
    task = add_task(accounts.project)
    ran_on(client, task, {"account_id": 2})
    assert f"CLAUDE_CONFIG_DIR={shlex.quote(accounts.two)} claude --resume" in page(client, task)["takeover"]
    sql("UPDATE runs SET account_id = NULL WHERE task_id = ?", (task,))  # NULL: the active one, as before
    assert f"CLAUDE_CONFIG_DIR={shlex.quote(accounts.one)} claude --resume" in page(client, task)["takeover"]


def test_transcripts_from_runs_account(client, accounts, fake):  # AC23
    task = add_task(accounts.project)
    ran_on(client, task, {"account_id": 2})
    [(run_id,)] = sql("SELECT id FROM runs WHERE task_id = ?", (task,))
    sql("UPDATE runs SET session_id = ? WHERE id = ?", (SID, run_id))
    assert sql("SELECT id FROM claude_accounts WHERE active = 1") == [(1,)]  # not the run's account
    source = os.path.join(accounts.two, "projects", folder_name(task_row(task)["worktree_path"]), f"{SID}.jsonl")
    os.makedirs(os.path.dirname(source))
    with open(source, "w") as f:
        f.write(MAIN)
    collect(transaction, run_id)
    assert sql("SELECT path FROM transcripts WHERE run_id = ?", (run_id,)) == [(f"{run_id}/{SID}.jsonl",)]


def test_page_run_account(client, accounts, fake):  # AC24
    task = add_task(accounts.project)
    ran_on(client, task, {"account_id": 2})
    assert page(client, task)["run"]["account"] == "b@y"
    sql("DELETE FROM claude_accounts WHERE id = 2")  # ON DELETE SET NULL
    assert page(client, task)["run"]["account"] is None


def rate_limited(resets):
    window = {"utilization": 1.0, "resetsAt": resets, "status": "rejected"}
    return json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": "rejected", "unifiedWindows": {"five_hour": window, "seven_day": window | {"utilization": 0.5}}}})


def test_limited_run_error(client, accounts, fake):  # AC25, Q7
    resets = int(time.time()) + 7200
    result = json.dumps({"type": "result", "is_error": True, "result": "usage limit reached"})
    fake(lines=[rate_limited(resets), result], code=1)
    task = add_task(accounts.project)
    r = post(client, task, {"account_id": 2})
    row = wait(r.json()["run_id"])
    assert (row["status"], row["error"]) == (
        "failed", f"limited on b@y, resets at {datetime.fromtimestamp(resets).strftime('%H:%M')}")
    fake(lines=[result], code=1)  # no snapshot: the result's error stays
    row = wait(post(client, task).json()["run_id"])
    assert row["error"] == "usage limit reached"


def test_limited_error_only_for_failed(client, accounts, fake):  # AC25: a succeeded run keeps no error
    resets = int(time.time()) + 7200
    fake(lines=[rate_limited(resets), json.dumps({"type": "result", "is_error": False, "session_id": SID})])
    row = wait(post(client, add_task(accounts.project)).json()["run_id"])
    assert (row["status"], row["error"]) == ("succeeded", None)
    run_id = sql("INSERT INTO runs (task_id, session_id, status, log_path, started_at, account_id)"
                 " VALUES (?, 's', 'stopped', 'l', ?, 2) RETURNING id", (add_task(accounts.project), OLD))[0][0]
    snap = {"five_hour": {"utilization": 1.0, "resets_at": resets, "status": "rejected"},
            "seven_day": {"utilization": 0.5, "resets_at": resets, "status": "allowed"},
            "status": "rejected", "overage": False, "limited": True}
    with transaction() as conn:
        UsageRepo(conn).record(run_id, snap)
    runs_handler.limited_error(transaction, run_id)
    assert sql("SELECT error FROM runs WHERE id = ?", (run_id,)) == [(None,)]


def test_docs():  # AC34
    mvp = section("MVP.md", "### 4.3")
    for text in ("**Auto**", "`FIVE_HOUR_LOW` (80%)", "`SEVEN_DAY_LOW` (90%)", "fctl run <id> --account",
                 "Everything about a run uses its own account", "takeover command, and the transcript copy"):
        assert text in mvp, text
    assert "chosen at start" in section("data-model-and-api.md", "### 5.1")
    runs = section("data-model-and-api.md", "### 6.2")
    for text in ('{"account_id":2}', '"account_id":2,"account":"b@y"', "all accounts near their limits: a@x 5h 92%",
                 '422 {"detail":"no Claude account #99"}', "isn't logged in to claude.ai", "always Auto, no body read"):
        assert text in runs, text
    pages = section("data-model-and-api.md", "### 6.4")
    for text in ("run.account", "accounts, every account by id as {id, label, active, five_hour",
                 "auto, {account_id, label}"):
        assert text in pages, text
    ui = section("ui.md", "## 8.")
    for text in ("**Choose account**", "`Auto (→ b@y)`", "`Auto (all near limits)`", "`run #41 failed · b@y:",
                 "**Make preferred**", "`preferred` pill"):
        assert text in ui, text


def test_page_accounts_and_auto(client, accounts, fake):  # AC26, Q9
    resets = snapshot(1, five=0.85, seven=0.2)
    data = page(client, add_task(accounts.project))
    assert [{k: a[k] for k in ("id", "label", "active")} for a in data["accounts"]] == [
        {"id": 1, "label": "a@x", "active": True}, {"id": 2, "label": "b@y", "active": False}]
    assert data["accounts"][0]["five_hour"] == {"utilization": 0.85, "resets_at": resets, "state": "near_limit",
                                                "reset": False}
    assert set(data["accounts"][0]) == {"id", "label", "active", "five_hour", "seven_day"}
    assert data["accounts"][1]["five_hour"] is None
    assert data["auto"] == {"account_id": 2, "label": "b@y"}
    assert set(accounts.claude.checked) <= {accounts.one}  # Q9: only can_run's cached badge check, no per-account one
    snapshot(2, limited=True)
    assert page(client, add_task(accounts.project))["auto"] is None
