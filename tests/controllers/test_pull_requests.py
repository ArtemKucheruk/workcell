"""093: POST/GET /api/tasks/{id}/pr, POST /api/tasks/{id}/pr/merge, and the pages' `pr`, against a bare-repo origin
(reached through `url.<bare>.insteadOf https://github.com/o/r.git`) and a fake `gh` on PATH that logs its argv and
answers from a state file (AC48)."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import commit, git, sql, write, wt_calls

from workcell import config
from workcell.adapters import git as adapter
from workcell.domain.errors import Failed

H = {"X-Requested-By": "fctl"}
URL = "https://github.com/o/r.git"
BRANCH = "factory/12-rate-limit"
TITLE = "Rate-limit login endpoint"
PR = "https://github.com/o/r/pull/71"
OLD = "2026-01-01T00:00:00Z"
DOCKER = " (the backend image has no gh login; create the PR from your host)"
LOGGED_OUT = "You are not logged into any GitHub hosts. To log in, run: gh auth login"

# The fake gh. `pr merge` merges for real into the bare origin with gh's merge-commit message, so main moves on
# GitHub's side; `probe` checks that the app holds no SQLite write lock while gh runs (AC23).
FAKE_GH = r'''#!PYTHON
import json, os, sqlite3, subprocess, sys, tempfile
args = sys.argv[1:]
path = os.environ["FAKE_GH_STATE"]
with open(path) as f:
    state = json.load(f)
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps({"argv": args, "prompt": os.environ.get("GH_PROMPT_DISABLED")}) + "\n")

def opt(name):
    return args[args.index(name) + 1] if name in args else None

def save():
    with open(path, "w") as f:
        json.dump(state, f)

def fail(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)

def probe():
    if state.get("probe"):
        try:
            conn = sqlite3.connect(state["probe"], timeout=0)
            conn.execute("BEGIN IMMEDIATE")
            conn.rollback()
            state.setdefault("probed", []).append("free")
        except sqlite3.OperationalError as e:
            state.setdefault("probed", []).append(str(e))

prs = state.setdefault("prs", [])
if args[:2] == ["auth", "status"]:
    if not state.get("auth", True):
        fail("You are not logged into any GitHub hosts. To log in, run: gh auth login")
elif args[:2] == ["pr", "list"]:
    print(json.dumps([{"number": p["number"], "url": p["url"]} for p in prs
                      if p["head"] == opt("--head") and p["state"] == "OPEN"]))
elif args[:2] == ["pr", "create"]:
    probe()
    save()
    if state.get("create_error"):
        fail(state["create_error"])
    n = state.get("next", 71)
    url = f"https://github.com/{opt('--repo')}/pull/{n}"
    prs.append({"number": n, "url": url, "head": opt("--head"), "base": opt("--base"), "title": opt("--title"),
                "body": opt("--body"), "state": "OPEN", "checks": []})
    state["next"] = n + 1
    save()
    print("Creating pull request for " + opt("--head"))
    print(url)
elif args[:2] == ["pr", "view"]:
    p = next((p for p in prs if p["number"] == int(args[2])), None)
    if p is None:
        fail(f"GraphQL: Could not resolve to a PullRequest with the number of {args[2]}. (repository.pullRequest)")
    print(json.dumps({"number": p["number"], "url": p["url"], "state": p["state"], "statusCheckRollup": p["checks"]}))
elif args[:2] == ["pr", "merge"]:
    probe()
    save()
    if state.get("merge_error"):
        fail(state["merge_error"])
    p = next(p for p in prs if p["number"] == int(args[2]))
    with tempfile.TemporaryDirectory() as tmp:
        def run(*a):
            subprocess.run(["git", "-C", tmp, *a], check=True, capture_output=True)
        subprocess.run(["git", "clone", "-q", state["bare"], tmp], check=True, capture_output=True)
        run("merge", "-q", "--no-ff", "-m", f"Merge pull request #{p['number']} from o/{p['head']}",
            f"origin/{p['head']}")
        run("push", "-q", "origin", p["base"])
        if state.get("delete_head"):  # GitHub's "Automatically delete head branches"
            run("push", "-q", "origin", "--delete", p["head"])
    p["state"] = "MERGED"
    save()
elif args[:2] == ["issue", "list"]:  # 108: `issues` [{number, title, body, url, labels}], newest first as gh lists
    probe()
    save()
    if state.get("issue_error"):
        fail(state["issue_error"])
    if "issue_output" in state:
        sys.stdout.write(state["issue_output"])
        sys.exit(0)
    label = opt("--label")
    print(json.dumps([{k: i.get(k) for k in ("number", "title", "body", "url")} for i in state.get("issues", [])
                      if label is None or label in i.get("labels", [])]))
else:
    fail("unknown command: " + " ".join(args))
'''


class Gh:
    def __init__(self, state: Path, log: Path):
        self.state_path, self.log = state, log

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def set(self, **values):
        self.state_path.write_text(json.dumps(self.state() | values))

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line)["argv"] for line in self.log.read_text().splitlines()]

    def made(self, *prefix) -> list[list[str]]:
        return [c for c in self.calls() if c[:len(prefix)] == list(prefix)]

    def pr(self, **values):
        """A PR for the branch, on GitHub already."""
        found = {"number": 71, "url": PR, "head": BRANCH, "base": "main", "state": "OPEN", "checks": []} | values
        self.set(prs=[*self.state().get("prs", []), found], next=found["number"] + 1)


@pytest.fixture
def gh(tmp_path, monkeypatch) -> Gh:
    script = tmp_path / "bin" / "gh"
    script.write_text(FAKE_GH.replace("PYTHON", sys.executable))
    script.chmod(0o755)
    found = Gh(tmp_path / "gh-state.json", tmp_path / "gh-log")
    found.state_path.write_text("{}")
    monkeypatch.setenv("FAKE_GH_STATE", str(found.state_path))
    monkeypatch.setenv("FAKE_GH_LOG", str(found.log))
    return found


@pytest.fixture
def setup(tmp_path, repo, client, gh):
    """`repo` pushed to a bare origin it reaches as github.com/o/r, a done factory task #N with its worktree on BRANCH
    (clean, nothing beyond main yet), connected as a project."""
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    with open(os.environ["GIT_CONFIG_GLOBAL"], "a") as f:
        f.write(f'[url "{bare}"]\n\tinsteadOf = {URL}\n')
    git(repo, "remote", "add", "origin", URL)
    git(repo, "push", "-q", "-u", "origin", "main")
    with open(repo / ".git" / "info" / "exclude", "a") as f:  # as 012's add_worktree does
        f.write(".claude/worktrees/\n")
    wt = repo / ".claude" / "worktrees" / "12-rate-limit"
    git(repo, "worktree", "add", "-q", "-b", BRANCH, str(wt), "main")
    r = client.post("/api/projects/connect", headers=H,
                    json={"path": str(repo), "workspace": "w", "name": "r", "default_branch": "main"})
    assert r.status_code == 200, r.text
    project = r.json()["id"]
    task = add_task(project, branch=BRANCH, worktree=str(wt))
    gh.set(bare=str(bare), probe=str(config.data_dir() / "factory.db"))
    return SimpleNamespace(repo=repo, bare=bare, wt=wt, project=project, task=task)


def add_task(project, status="done", branch=BRANCH, worktree=None, pr_url=None,
             description="Limit login attempts per IP.\nFive a minute.\n\nDetails follow."):
    return sql("INSERT INTO tasks (project_id, title, description_md, status, position, branch, worktree_path, pr_url,"
               " created_at, updated_at) VALUES (?, ?, ?, ?, 1.0, ?, ?, ?, ?, ?) RETURNING id",
               (project, TITLE, description, status, branch, worktree, pr_url, OLD, OLD))[0][0]


def change(setup, files=None):
    write(setup.wt, files or {"app/limits.py": "LIMIT = 5\n"})


def create(client, task, headers=H):
    return client.post(f"/api/tasks/{task}/pr", headers=headers)


def merge(client, task, headers=H):
    return client.post(f"/api/tasks/{task}/pr/merge", headers=headers)


def pr_url(task):
    return sql("SELECT pr_url FROM tasks WHERE id = ?", (task,))[0][0]


def notes(task) -> list[str]:
    return [r[0] for r in sql("SELECT note FROM events WHERE task_id = ? AND note IS NOT NULL ORDER BY id", (task,))]


def remote_branches(bare) -> list[str]:
    return git(bare, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()


def refused(r, status=409) -> str:
    assert r.status_code == status, r.text
    return r.json()["detail"]


# --- Schema, import, timeline ------------------------------------------------------------------


def test_pr_url_column():  # AC1 (the old-DB half is tests/db/test_db.py::test_old_db_gets_pr_url)
    from workcell import db
    db.init()
    assert "pr_url" in [r[1] for r in sql("PRAGMA table_info(tasks)")]


def test_event_note_in_timeline(client, setup):  # AC37
    sql("INSERT INTO events (task_id, actor, from_status, to_status, note, created_at)"
        " VALUES (?, 'me', 'done', 'done', 'PR #71 opened', ?)", (setup.task, OLD))
    page = client.get(f"/api/pages/tasks/{setup.task}").json()
    assert "done · PR #71 opened" in [e["label"] for e in page["history"]]


# --- The adapter (AC3, AC4) --------------------------------------------------------------------


def test_adapter_timeouts_and_argv(monkeypatch):  # AC3, AC4
    seen = []
    monkeypatch.setattr(adapter, "ran", lambda argv, timeout, env=None: seen.append((argv, timeout, env)) or (0, "", ""))
    monkeypatch.setattr(adapter, "gh", lambda *a: seen.append((["gh", *a], adapter.NETWORK_TIMEOUT, None)) or (0, "", ""))
    g = adapter.SubprocessGit()
    g.origin_url("/r")
    g.porcelain("/w")
    g.ahead("/w", "main")
    g.commit("/w", "T")
    g.head_branch("/r")
    g.is_ancestor("/r", "HEAD", "origin/main")
    g.ff_merge("/r", "origin/main")
    g.delete_branch("/r", "b")
    local = [t for _, t, _ in seen]
    assert set(local) == {60}
    seen.clear()
    g.push("/w", "b")
    g.fetch("/r")
    g.delete_remote_branch("/r", "b")
    g.pr_merge("o/r", 71)
    assert {t for _, t, _ in seen} == {adapter.NETWORK_TIMEOUT} and adapter.NETWORK_TIMEOUT == 120
    argvs = [a for a, _, _ in seen]
    assert argvs[0] == ["git", "-C", "/w", "push", "-u", "origin", "b"]
    assert not any(flag in a for a in argvs for flag in ("--force", "-f"))
    assert adapter.MERGE_METHOD == "--merge"
    assert argvs[-1] == ["gh", "pr", "merge", "71", "--repo", "o/r", "--merge"]


def test_timeout_is_failed():  # AC3
    with pytest.raises(Failed) as e:
        adapter.ran(["sleep", "5"], 0.1)
    assert e.value.detail == "sleep timed out: sleep 5"


def test_gh_prompts_off(client, setup, gh):  # AC3
    change(setup)
    assert create(client, setup.task).status_code == 200
    assert {json.loads(line)["prompt"] for line in gh.log.read_text().splitlines()} == {"1"}


# --- POST /api/tasks/{id}/pr ---------------------------------------------------------------------


def test_create(client, setup, gh):  # AC19, AC23
    change(setup)
    r = create(client, setup.task)
    assert r.status_code == 200, r.text
    assert r.json() == {"number": 71, "url": PR, "reused": False}
    assert pr_url(setup.task) == PR
    [event] = sql("SELECT actor, from_status, to_status, note FROM events WHERE task_id = ?", (setup.task,))
    assert tuple(event) == ("me", "done", "done", "PR #71 opened")
    [call] = gh.made("pr", "create")
    assert call[:10] == ["pr", "create", "--repo", "o/r", "--base", "main", "--head", BRANCH, "--title", TITLE]
    assert BRANCH in remote_branches(setup.bare)
    assert gh.state()["probed"] == ["free"]  # AC23: no write lock held while gh ran


def test_commit_message_and_identity(client, setup, gh):  # AC15
    change(setup, {"app/limits.py": "LIMIT = 5\n", ".gitignore": "secret.env\n", "secret.env": "TOKEN=x\n"})
    assert create(client, setup.task).status_code == 200
    raw = subprocess.run(["git", "-C", str(setup.wt), "cat-file", "commit", "HEAD"], capture_output=True,
                         text=True, check=True).stdout
    assert raw.split("\n\n", 1)[1] == TITLE + "\n"
    assert git(setup.wt, "log", "-1", "--format=%an <%ae>|%cn <%ce>") == "Test <test@example.com>|Test <test@example.com>"
    files = git(setup.wt, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(files) == [".gitignore", "app/limits.py"]


def test_pr_body(client, setup, gh):  # AC20
    rid = sql("INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, 1, 'initial', 'x', ?)"
              " RETURNING id", (setup.task, OLD))[0][0]
    rid2 = sql("INSERT INTO rounds (task_id, n, trigger, base_sha, created_at) VALUES (?, 2, 'agent', 'x', ?)"
               " RETURNING id", (setup.task, OLD))[0][0]
    for who in ("security", "ux", "code"):
        sql("INSERT INTO verdicts (round_id, reviewer, verdict, body_md, created_at) VALUES (?, ?, 'PASS', '', ?)",
            (rid2, who, OLD))
    sql("INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at)"
        " VALUES (?, ?, 'approver', 'APPROVE', 'Ship it.', ?)", (setup.task, rid, OLD))
    change(setup)
    assert create(client, setup.task).status_code == 200
    [found] = gh.state()["prs"]
    assert found["body"] == (
        "Limit login attempts per IP.\nFive a minute.\n\nRounds: 2\n\n"
        "Verdicts (round 2): security PASS · ux PASS · ui pending · code PASS\n\n"
        f"Approver: APPROVE — Ship it.\n\nTask: http://127.0.0.1:4545/tasks/{setup.task}")
    assert "Claude" not in found["body"]


def test_pr_body_closes_issue(client, setup, gh):  # 108 AC24
    sql("UPDATE tasks SET import_key = 'github:o/r#12' WHERE id = ?", (setup.task,))
    change(setup)
    assert create(client, setup.task).status_code == 200
    [found] = gh.state()["prs"]
    assert found["body"].endswith(f"Task: http://127.0.0.1:4545/tasks/{setup.task}\n\nCloses #12")


@pytest.mark.parametrize("key", [None, "factory:12-rate-limit"])
def test_pr_body_no_closes(client, setup, gh, key):  # 108 AC25 (test_pr_body's exact body passes unchanged)
    sql("UPDATE tasks SET import_key = ? WHERE id = ?", (key, setup.task))
    change(setup)
    assert create(client, setup.task).status_code == 200
    [found] = gh.state()["prs"]
    assert "Closes" not in found["body"]


def test_pr_body_closes_other_repo(client, setup, gh):  # 108 AC26, Q7
    sql("UPDATE tasks SET import_key = 'github:old/name#12' WHERE id = ?", (setup.task,))
    change(setup)
    assert create(client, setup.task).status_code == 200
    [found] = gh.state()["prs"]
    assert found["body"].endswith("\n\nCloses old/name#12")


def test_clean_branch_ahead(client, setup, gh):  # AC16
    head = commit(setup.wt, {"a.py": "x = 1\n"})
    r = create(client, setup.task)
    assert r.status_code == 200, r.text
    assert git(setup.wt, "rev-parse", "HEAD") == head  # no commit made
    assert git(setup.bare, "rev-parse", BRANCH) == head
    assert len(gh.made("pr", "create")) == 1


def test_nothing_to_commit(client, setup, gh):  # AC17
    assert refused(create(client, setup.task)) == f"nothing to commit: #{setup.task}'s branch has no changes beyond main"
    assert BRANCH not in remote_branches(setup.bare)
    assert gh.made("pr") == []


def test_push_rejected(client, tmp_path, setup, gh):  # AC18
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", URL, str(other))
    git(other, "checkout", "-q", "-b", BRANCH)
    commit(other, {"theirs.py": "1\n"})
    git(other, "push", "-q", "origin", BRANCH)
    change(setup)
    detail = refused(create(client, setup.task))
    assert detail.startswith(f"git push was rejected: ! [rejected]        {BRANCH} -> {BRANCH}")
    assert pr_url(setup.task) is None
    assert gh.made("pr", "create") == []


def test_reuse(client, setup, gh):  # AC21
    change(setup)
    first, second = create(client, setup.task), create(client, setup.task)
    assert first.json()["reused"] is False
    assert second.status_code == 200 and second.json() == {"number": 71, "url": PR, "reused": True}
    assert len(gh.made("pr", "create")) == 1
    assert notes(setup.task) == ["PR #71 opened"]


def test_reuse_opened_by_hand(client, setup, gh):  # AC21
    gh.pr(number=9, url="https://github.com/o/r/pull/9")
    change(setup)
    r = create(client, setup.task)
    assert r.json() == {"number": 9, "url": "https://github.com/o/r/pull/9", "reused": True}
    assert gh.made("pr", "create") == []
    assert pr_url(setup.task) == "https://github.com/o/r/pull/9"
    assert BRANCH in remote_branches(setup.bare)  # the commit and push still ran
    assert git(setup.wt, "log", "-1", "--format=%s") == TITLE


def test_create_fails(client, setup, gh):  # AC22
    gh.set(create_error="pull request create failed: GraphQL: No commits between main and x (createPullRequest)")
    change(setup)
    assert refused(create(client, setup.task)).startswith("pull request create failed: GraphQL")
    assert git(setup.wt, "log", "-1", "--format=%s") == TITLE
    assert BRANCH in remote_branches(setup.bare)
    assert pr_url(setup.task) is None and notes(setup.task) == []


def test_create_needs_header(client, setup, gh):  # AC5
    assert refused(create(client, setup.task, headers={}), 403) == "X-Requested-By: fctl header required"


def test_create_unknown(client, gh):  # AC6
    assert refused(create(client, 99), 404) == "Task #99 not found"


@pytest.mark.parametrize("status", ["backlog", "in_progress", "review"])
def test_create_not_done(client, setup, gh, status):  # AC7
    sql("UPDATE tasks SET status = ? WHERE id = ?", (status, setup.task))
    change(setup)
    assert refused(create(client, setup.task)) == f"#{setup.task} is not done; approve it first"
    assert gh.calls() == []
    assert git(setup.wt, "status", "--porcelain")  # nothing committed


def test_create_standalone(client, setup, gh):  # AC8
    task = add_task(setup.project, branch=None, worktree=None)
    assert refused(create(client, task)) == f"#{task} has no branch; commit it yourself"


def test_create_worktree_gone(client, setup, gh):  # AC9
    task = add_task(setup.project, worktree="/nowhere/wt")
    assert refused(create(client, task)) == "the worktree /nowhere/wt is gone"


def test_no_origin(client, setup, gh):  # AC10
    git(setup.repo, "remote", "remove", "origin")
    change(setup)
    assert refused(create(client, setup.task)) == (
        f"{setup.repo} has no origin remote; add one with git remote add origin …")
    assert gh.calls() == []


def test_origin_not_github(client, setup, gh):  # AC11
    git(setup.repo, "remote", "set-url", "origin", "git@gitlab.com:o/r.git")
    change(setup)
    assert refused(create(client, setup.task)) == "origin isn't on GitHub (gitlab.com); push and open the PR yourself"


def gh_missing(tmp_path, monkeypatch):
    """PATH with git alone, so neither the fake nor any real gh is found."""
    only = tmp_path / "only-git"
    only.mkdir()
    (only / "git").symlink_to(shutil.which("git"))
    monkeypatch.setenv("PATH", str(only))


def test_gh_missing(client, tmp_path, monkeypatch, setup, gh):  # AC12
    change(setup)
    gh_missing(tmp_path, monkeypatch)
    assert refused(create(client, setup.task)) == "gh is not installed: install GitHub CLI, then run gh auth login"


def test_gh_logged_out(client, setup, gh):  # AC13
    gh.set(auth=False)
    change(setup)
    assert refused(create(client, setup.task)) == f"gh is not logged in: run gh auth login. {LOGGED_OUT}"
    assert gh.calls() == [["auth", "status", "--hostname", "github.com"]]


def test_docker_hint(client, tmp_path, monkeypatch, setup, gh):  # AC14
    monkeypatch.setenv("FCTL_IN_DOCKER", "1")
    gh.set(auth=False)
    change(setup)
    assert refused(create(client, setup.task)) == f"gh is not logged in: run gh auth login. {LOGGED_OUT}{DOCKER}"
    gh_missing(tmp_path, monkeypatch)
    assert refused(create(client, setup.task)).endswith(f"then run gh auth login{DOCKER}")


# --- GET /api/tasks/{id}/pr ----------------------------------------------------------------------


def test_state(client, setup, gh):  # AC24
    checks = [{"conclusion": "SUCCESS"}, {"conclusion": "SKIPPED"}, {"conclusion": "FAILURE"},
              {"conclusion": "", "status": "IN_PROGRESS"}, {"state": "PENDING"}]
    gh.pr(checks=checks)
    sql("UPDATE tasks SET pr_url = ? WHERE id = ?", (PR, setup.task))
    r = client.get(f"/api/tasks/{setup.task}/pr")
    assert r.status_code == 200, r.text
    assert r.json() == {"number": 71, "url": PR, "state": "OPEN", "checks": {"passed": 2, "failed": 1, "pending": 2}}
    assert gh.made("pr", "view") == [["pr", "view", "71", "--repo", "o/r", "--json",
                                      "number,url,state,statusCheckRollup"]]


def test_state_no_checks(client, setup, gh):  # AC24
    gh.pr(state="MERGED")
    sql("UPDATE tasks SET pr_url = ? WHERE id = ?", (PR, setup.task))
    assert client.get(f"/api/tasks/{setup.task}/pr").json()["checks"] == {"passed": 0, "failed": 0, "pending": 0}


def test_state_no_pr(client, setup, gh):  # AC25
    assert refused(client.get(f"/api/tasks/{setup.task}/pr"), 404) == f"#{setup.task} has no PR"


def test_state_gh_fails(client, tmp_path, monkeypatch, setup, gh):  # AC26
    sql("UPDATE tasks SET pr_url = ? WHERE id = ?", (PR, setup.task))
    assert refused(client.get(f"/api/tasks/{setup.task}/pr")).startswith(
        "GraphQL: Could not resolve to a PullRequest with the number of 71.")
    gh.set(auth=False)
    assert refused(client.get(f"/api/tasks/{setup.task}/pr")) == f"gh is not logged in: run gh auth login. {LOGGED_OUT}"
    gh_missing(tmp_path, monkeypatch)
    assert refused(client.get(f"/api/tasks/{setup.task}/pr")).startswith("gh is not installed")


# --- POST /api/tasks/{id}/pr/merge -------------------------------------------------------------


@pytest.fixture
def opened(client, setup, gh):
    change(setup)
    assert create(client, setup.task).status_code == 200
    return setup


def test_merge(client, opened, gh):  # AC28, AC31, AC34
    s = opened
    r = merge(client, s.task)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["number"], body["state"]) == (71, "MERGED")
    assert gh.made("pr", "merge") == [["pr", "merge", "71", "--repo", "o/r", "--merge"]]
    assert notes(s.task) == ["PR #71 opened", "PR #71 merged"]
    [event] = sql("SELECT actor, from_status, to_status FROM events WHERE note = 'PR #71 merged'")
    assert tuple(event) == ("me", "done", "done")
    # AC31: local main fast-forwarded to the merge commit
    assert git(s.repo, "rev-parse", "main") == git(s.bare, "rev-parse", "main")
    assert git(s.repo, "log", "-1", "--format=%s", "main") == f"Merge pull request #71 from o/{BRANCH}"
    # AC34: everything cleaned up
    assert not s.wt.exists()
    assert git(s.repo, "branch", "--list", BRANCH) == ""
    assert BRANCH not in remote_branches(s.bare)
    assert body["notes"] == ["Fast-forwarded main to origin/main.", f"Removed the worktree {s.wt}.",
                             f"Deleted the local branch {BRANCH}.", f"Deleted the remote branch {BRANCH}."]
    assert gh.state()["probed"] == ["free", "free"]  # AC23


def test_merge_blocked(client, opened, gh):  # AC29
    s = opened
    main = git(s.bare, "rev-parse", "main")
    gh.set(merge_error="X Pull request o/r#71 is not mergeable: the base branch policy prohibits the merge.")
    assert refused(merge(client, s.task)) == (
        "X Pull request o/r#71 is not mergeable: the base branch policy prohibits the merge.")
    assert notes(s.task) == ["PR #71 opened"]
    assert s.wt.exists() and BRANCH in remote_branches(s.bare)
    assert git(s.repo, "rev-parse", "origin/main") == main  # nothing fetched


def test_merge_already_merged(client, opened, gh):  # AC30
    s = opened
    gh.set(prs=[p | {"state": "MERGED"} for p in gh.state()["prs"]])
    r = merge(client, s.task)
    assert r.status_code == 200 and r.json()["state"] == "MERGED"
    assert gh.made("pr", "merge") == []
    assert not s.wt.exists() and BRANCH not in remote_branches(s.bare)


def test_merge_closed(client, opened, gh):  # AC30
    gh.set(prs=[p | {"state": "CLOSED"} for p in gh.state()["prs"]])
    assert refused(merge(client, opened.task)) == "PR #71 is closed; reopen it on GitHub"
    assert opened.wt.exists()


def test_skip_other_branch(client, opened, gh):  # AC32
    s = opened
    git(s.repo, "checkout", "-q", "-b", "elsewhere")
    head = git(s.repo, "rev-parse", "HEAD")
    r = merge(client, s.task)
    assert "Skipped updating main: the main checkout is on elsewhere." in r.json()["notes"]
    assert git(s.repo, "rev-parse", "HEAD") == head and git(s.repo, "rev-parse", "main") == head


def test_skip_dirty(client, opened, gh):  # AC33
    s = opened
    write(s.repo, {"scratch.txt": "untracked\n"})
    head = git(s.repo, "rev-parse", "HEAD")
    r = merge(client, s.task)
    assert "Skipped updating main: the main checkout has uncommitted changes." in r.json()["notes"]
    assert git(s.repo, "rev-parse", "HEAD") == head


def test_skip_diverged(client, opened, gh):  # AC33
    s = opened
    head = commit(s.repo, {"local.txt": "mine\n"})
    r = merge(client, s.task)
    assert "Skipped updating main: main has commits not on origin/main." in r.json()["notes"]
    assert git(s.repo, "rev-parse", "HEAD") == head


def test_cleanup_failures(client, opened, gh):  # AC35
    s = opened
    write(s.wt, {"leftover.txt": "x\n"})  # the worktree is dirty, so its branch stays checked out
    gh.set(delete_head=True)
    r = merge(client, s.task)
    assert r.status_code == 200, r.text
    _, wt_note, branch_note, remote_note = r.json()["notes"]
    assert wt_note.startswith("Kept the worktree: fatal:") and s.wt.exists()
    assert branch_note.startswith(f"Kept the local branch {BRANCH}: error:")
    assert remote_note == "Remote branch already deleted."


def test_cleanup_worktree_gone(client, opened, gh):  # AC35
    shutil.rmtree(opened.wt)
    assert merge(client, opened.task).json()["notes"][1] == "Worktree already removed."


def test_cleanup_through_wt(client, opened, gh, tmp_path, monkeypatch):  # 099 Q6
    s = opened
    assert merge(client, s.task).json()["notes"][1] == f"Removed the worktree {s.wt}."
    [remove] = [c["argv"] for c in wt_calls() if "remove" in c["argv"]]
    assert remove == ["-C", str(s.repo), "remove", "--foreground", "--no-delete-branch", "--no-hooks", BRANCH]


def test_cleanup_without_wt(client, opened, gh, tmp_path, monkeypatch):  # 099 Q6: a note, the rest still run
    (tmp_path / "bin" / "wt").unlink()
    only = tmp_path / "git-only"  # gh stays (the fake), git without a real wt beside it
    only.mkdir()
    (only / "git").symlink_to(os.path.realpath(shutil.which("git")))
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{only}")
    notes = merge(client, opened.task).json()["notes"]
    assert notes[1] == "Kept the worktree: wt (worktrunk) isn't installed: brew install worktrunk, then run again"
    assert opened.wt.exists() and notes[3] == f"Deleted the remote branch {BRANCH}."


def test_merge_refusals(client, tmp_path, monkeypatch, setup, gh):  # AC27
    assert refused(merge(client, setup.task, headers={}), 403) == "X-Requested-By: fctl header required"
    assert refused(merge(client, setup.task)) == f"#{setup.task} has no PR; Create PR first"
    sql("UPDATE tasks SET pr_url = ? WHERE id = ?", (PR, setup.task))
    gh.pr()
    gh.set(auth=False)
    assert refused(merge(client, setup.task)) == f"gh is not logged in: run gh auth login. {LOGGED_OUT}"
    gh_missing(tmp_path, monkeypatch)
    assert refused(merge(client, setup.task)).startswith("gh is not installed")
    sql("UPDATE tasks SET status = 'review' WHERE id = ?", (setup.task,))
    assert refused(merge(client, setup.task)) == f"#{setup.task} is not done; approve it first"
    assert gh.made("pr", "merge") == []


# --- Docs (AC46, AC47) -------------------------------------------------------------------------

DOCS = Path(__file__).resolve().parents[2] / "docs"


def between(text: str, start: str, end: str) -> str:
    at = text.index(start)
    return text[at:text.index(end, at + len(start))]


def test_docs():  # AC46
    mvp = (DOCS / "MVP.md").read_text()
    assert "Claude never commits" not in mvp and "The app never runs them" not in mvp
    goals = between(mvp, "### Goals", "### Non-goals")
    assert "Agents never commit" in goals and "Create PR" in goals and "Merge PR" in goals
    flow = between(mvp, "### 3.7 ", "### 3.8 ")
    for text in ("Create PR", "Merge PR", "gh pr create", "gh pr merge <n> --merge", "--ff-only", "wt remove",
                 "git branch -d", "git push origin --delete"):  # 099 Q6: wt remove, was git worktree remove
        assert text in flow, text
    assert "Create PR" in between(mvp, "### 4.3 ", "### 4.4 ")
    assert "no GitHub login" in between(mvp, "### 4.6 ", "### 4.7 ")
    assert "open a GitHub" not in between(mvp, "**Later**", "## 10.")
    assert "Create PR" in between(mvp, "### Assumptions", "### Open questions")
    api = (DOCS / "data-model-and-api.md").read_text()
    assert "pr_url TEXT" in between(api, "### 5.1", "### 5.2")
    endpoints = re.sub(r"\n\s*#\s+", " ", between(api, "### 6.3", "### 6.4"))  # a wrapped # comment as one line
    for text in ("POST /api/tasks/12/pr ", "GET  /api/tasks/12/pr ", "POST /api/tasks/12/pr/merge",
                 "#12 is not done; approve it first", "PR #71 is closed; reopen it on GitHub"):
        assert text in endpoints, text
    assert '"can_create"' in api[api.index("### 6.4"):]
    ui = (DOCS / "ui.md").read_text()
    task_item = between(ui, "4. **Task detail**", "5. **Code review**")
    assert "**Create PR**" in task_item and "**Merge PR**" in task_item and "PR #71 opened" in task_item
    assert "Commit it yourself" in between(ui, "5. **Code review**", "6. **Project code**")
    wireframe = between(ui, "### 8.2", "### 8.3")
    assert "[Create PR]" in wireframe and "[Merge PR]" in wireframe and "checks: 2 passed" in wireframe


def test_fctl_unchanged():  # AC47: no fctl pr; tests/test_fctl_md.py checks fctl.md against the CLI
    fctl_md = (Path(__file__).resolve().parents[2] / "src" / "workcell" / "fctl.md").read_text()
    assert "fctl pr" not in fctl_md and "pr/merge" not in fctl_md


# --- The pages' `pr` (AC36) --------------------------------------------------------------------


def page_pr(client, task):
    a = client.get(f"/api/pages/tasks/{task}").json()["pr"]
    b = client.get(f"/api/pages/tasks/{task}/review").json()["pr"]
    assert a == b
    return a


def test_page_pr(client, setup, gh):  # AC36
    off = {"url": None, "number": None, "can_create": False}
    assert page_pr(client, setup.task) == off | {"hint": "Nothing to commit beyond main."}
    change(setup)
    assert page_pr(client, setup.task) == off | {"can_create": True, "hint": None}
    git(setup.wt, "add", "-A")
    git(setup.wt, "commit", "-q", "-m", "c")
    assert page_pr(client, setup.task)["can_create"] is True  # clean, but ahead of main
    sql("UPDATE tasks SET status = 'review' WHERE id = ?", (setup.task,))
    assert page_pr(client, setup.task) == off | {"hint": "Approve it first."}
    gone = add_task(setup.project, worktree="/nowhere/wt")
    assert page_pr(client, gone) == off | {"hint": "The worktree is gone."}
    with_pr = add_task(setup.project, worktree=str(setup.wt), pr_url=PR, status="review")
    assert page_pr(client, with_pr) == {"url": PR, "number": 71, "can_create": False, "hint": None}
    assert page_pr(client, add_task(setup.project, branch=None)) is None
    assert gh.calls() == []  # local git only
