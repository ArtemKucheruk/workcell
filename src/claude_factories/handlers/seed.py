"""fctl seed: demo data for every page and state in docs/ui.md §8 (038). Two workspaces, three projects
backed by real git repos under FCTL_HOME/demo/ (factory none, uncommitted, and ready, MVP §3.2 step 4), and
tasks in every status and stage, written through the repositories in one transaction. Round diffs are the
§7.4 capture of real worktrees, and every timestamp is an offset back from the moment of seeding (Q5)."""

import base64
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .. import config
from ..adapters.git import Git
from ..domain.enums import STAGE_STATUS, Reviewer
from ..domain.errors import Conflict, Failed
from ..dto.rounds import RoundBody
from ..lib.diff import diff_rows
from ..lib.slug import slug
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from ..repositories.workspaces import WorkspacesRepo
from .factory import create_factory
from .rounds import insert_round
from .runs import exclude_worktrees

TIME = "%Y-%m-%dT%H:%M:%SZ"  # db.now()'s format, so seeded times compare as strings with real ones
URL = "http://127.0.0.1:4545"  # only in the run logs' fctl output
REVIEWERS = tuple(Reviewer)
PNG = base64.b64decode(  # a 1×1 PNG: NUL bytes, so git and the code page both call it binary
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
PASS = {
    "security": "No new input reaches a query, a shell, or an outbound request unchecked. Nothing to fix.",
    "ux": "Status codes and messages say what went wrong and what to do next.",
    "ui": "No page changes; the JSON shapes match the other endpoints.",
    "code": "Small, readable, and covered by tests. `pytest -q` is green.",
}


def write(root: Path, files: dict) -> None:
    """{relative path: str, bytes, or None to delete} under root."""
    for rel, content in files.items():
        target = root / rel
        if content is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())


def seed(tx, git: Git) -> dict:
    """Refuse a home with data (Q12: only a workspace counts) or a leftover demo/ (Q6) before writing
    anything, then build the demo in one transaction: any failure leaves no rows. {workspaces, projects,
    tasks, runs}, for the summary line (Q7)."""
    demo = config.data_dir() / "demo"
    with tx() as conn:
        now = TasksRepo(conn).lock()
        if WorkspacesRepo(conn).all():
            raise Conflict("FCTL_HOME has data; seed an empty one")
        if os.path.lexists(demo):
            raise Conflict(f"{demo} exists; seed an empty FCTL_HOME")
        return Demo(conn, git, now, demo.resolve()).story()


class Demo:
    """The story helpers. `clock` is the time of the current step; each helper moves it forward."""

    def __init__(self, conn, git: Git, now: str, root: Path):
        self.workspaces, self.projects, self.tasks = WorkspacesRepo(conn), ProjectsRepo(conn), TasksRepo(conn)
        self.rounds, self.reviews, self.runs = RoundsRepo(conn), ReviewsRepo(conn), RunsRepo(conn)
        self.git, self.root = git, root
        self.now = self.clock = datetime.strptime(now, TIME).replace(tzinfo=UTC)
        self.run: dict | None = None  # the run being logged
        self.counts = {"workspaces": 0, "projects": 0, "tasks": 0, "runs": 0}

    # --- time ---------------------------------------------------------------------------

    def at(self, days: float) -> str:
        self.clock = self.now - timedelta(days=days)
        return self.clock.strftime(TIME)

    def tick(self, minutes: float = 1) -> str:
        self.clock += timedelta(minutes=minutes)
        return self.clock.strftime(TIME)

    # --- workspaces, projects, tasks -----------------------------------------------------

    def workspace(self, name: str, days: float) -> int:
        self.counts["workspaces"] += 1
        return self.workspaces.get_or_create(name, self.at(days))

    def project(self, workspace_id: int, name: str, test_cmd: str, commits: list, factory: str,
                days: float) -> dict:
        """A repo on main with `commits` [(message, files)], then the factory: none, written
        (uncommitted), or written and committed (ready)."""
        path = str(self.root / name)
        self.git.init(path)
        for message, files in commits:
            write(Path(path), files)
            self.git.commit_all(path, message)
        project_id = self.projects.add(workspace_id, name, path, None, "main", test_cmd, self.at(days))
        if factory != "none":
            create_factory(self.projects, project_id, overwrite=False)
        if factory == "ready":
            self.git.commit_all(path, "Add factory")
        self.counts["projects"] += 1
        return {"id": project_id, "path": path}

    def task(self, project: dict, title: str, description: str, days: float) -> dict:
        """My new Backlog card (§7.5)."""
        now = self.at(days)
        task_id = self.tasks.add(project["id"], title, description, "backlog", None,
                                 self.tasks.bottom_position(project["id"], "backlog"), now)
        self.tasks.add_event(task_id, "me", None, "backlog", None, now)
        self.counts["tasks"] += 1
        return {"id": task_id, "title": title, "project": project, "status": "backlog", "stage": None, "wt": None}

    def standalone(self, project: dict, title: str, description: str, days: float, files: dict) -> dict:
        """§7.4: /factory-submit's task, straight in review with round 1 from the main checkout's changes
        (Q1), which stay uncommitted there."""
        now = self.at(days)
        task_id = self.tasks.add(project["id"], title, description, "review", "human_review",
                                 self.tasks.bottom_position(project["id"], "review"), now)
        self.tasks.add_event(task_id, "app", None, "review", "human_review", now)
        self.counts["tasks"] += 1
        task = {"id": task_id, "title": title, "project": project, "status": "review", "stage": "human_review",
                "wt": None}
        self.round(task, files, None, root=project["path"], minutes=0)
        return task

    def move(self, task: dict, actor: str, status: str, stage: str | None, position: float | None = None) -> None:
        now = self.tick()
        self.tasks.move(task["id"], status, stage, now if status == "done" else None, now, position)
        self.tasks.add_event(task["id"], actor, task["status"], status, stage, now)
        task.update(status=status, stage=stage)

    def stage(self, task: dict, stage: str) -> None:
        """The orchestrator's `fctl stage` (§7.5)."""
        status = STAGE_STATUS[stage]
        self.log("orchestrator", f"fctl stage {task['id']} {stage}", f"#{task['id']}: {status} · {stage}")
        self.move(task, "orchestrator", status, stage)

    def worktree(self, task: dict) -> str:
        """Q3: as handlers/runs.worktree makes it, once per task: the exclude line, then a new branch from main."""
        if not task["wt"]:
            repo = task["project"]["path"]
            exclude_worktrees(self.git, repo)
            name = f"{task['id']}-{slug(task['title'])}"
            branch, wt = f"factory/{name}", os.path.join(repo, ".claude", "worktrees", name)
            if error := self.git.add_worktree(repo, branch, wt, "main"):
                raise Failed(f"git worktree add failed: {error}")
            self.tasks.set_worktree(task["id"], branch, wt)
            task["wt"] = wt
        return task["wt"]

    # --- the factory's records ----------------------------------------------------------

    def spec(self, task: dict, spec_md: str) -> None:
        self.tasks.set_spec(task["id"], spec_md, self.tick(7))
        self.log("spec-writer", f"fctl spec {task['id']} <<'EOF'", f"Spec saved on #{task['id']}")

    def round(self, task: dict, files: dict, build_md: str | None, root: str | None = None,
              minutes: float = 14) -> None:
        """Q3: write the round's changes into the tree, then submit what §7.4's capture sees there. Later
        rounds write on top, so each round's diff is the whole change against HEAD."""
        root = root or self.worktree(task)
        write(Path(root), files)
        base_sha, patch = self.git.capture(root)
        out = insert_round(self.rounds, self.reviews, task["id"], RoundBody(base_sha=base_sha, patch=patch,
                                                                            build_md=build_md), self.tick(minutes))
        n, builder = out["round"], f"builder-{task['id']}"
        self.say(builder, f"Round {n} is ready; tests are green.")
        self.log(builder, f"fctl submit {task['id']} <<'EOF'",
                 f"Round {n} of #{task['id']}: {out['files_changed']} files, +{out['additions']} −{out['deletions']}"
                 f" → {URL}/tasks/{task['id']}/review?round={n}")

    def verdicts(self, task: dict, changes: dict | None = None, who: tuple = REVIEWERS) -> None:
        """Each reviewer in `who` on the latest round: CHANGES with its body in `changes`, else PASS."""
        changes = changes or {}
        latest = self.rounds.latest(task["id"])
        for reviewer in who:
            verdict = "CHANGES" if reviewer in changes else "PASS"
            posted = self.reviews.put_verdict(latest["id"], reviewer, verdict, changes.get(reviewer, PASS[reviewer]),
                                              self.tick(3))
            self.log(f"review-{reviewer}", f"fctl verdict {task['id']} {reviewer} {verdict} <<'EOF'",
                     f"Round {latest['n']} of #{task['id']}: {reviewer}={verdict} ({posted}/4)")

    def comment(self, task: dict, author: str, body: str, path: str | None = None, side: str = "new",
                text: str = "") -> None:
        """A comment on the latest round: inline on the first `side` row of `path`'s diff holding `text`,
        so it never lands outside the diff, or with no path a conversation comment."""
        latest = self.rounds.latest(task["id"])
        line = None
        if path:
            [patch] = [f["patch"] for f in self.rounds.files(latest["id"]) if f["path"] == path]
            line = next(r[side] for r in diff_rows(patch) if r[side] is not None and text in r["text"])
        comment_id = self.reviews.add_comment(task["id"], latest["id"], author, path, line, path and side, body,
                                              self.tick(4))
        if author != "me":  # fctl comment: a reviewer's, always on the new side
            self.log(f"review-{author}", f"fctl comment {task['id']} {author} --path {path} --line {line} <<'EOF'",
                     f"Comment #{comment_id} on #{task['id']} {path}:{line}")

    def decide(self, task: dict, actor: str, decision: str, body: str) -> None:
        latest = self.rounds.latest(task["id"])
        decision_id = self.reviews.add_decision(task["id"], latest["id"], actor, decision, body, self.tick(5))
        if actor == "approver":
            self.log("approver", f"fctl decide {task['id']} {decision} <<'EOF'",
                     f"Decision #{decision_id} on #{task['id']}: {decision}")

    def build_round(self, task: dict, files: dict, build_md: str, changes: dict | None = None) -> None:
        """§3.4 steps 3–4: a builder round, then all four verdicts."""
        self.stage(task, "build")
        self.round(task, files, build_md)
        self.stage(task, "agent_review")
        self.verdicts(task, changes)

    def approver(self, task: dict, decision: str, body: str) -> None:
        """§3.4 steps 6–7: the approver's decision, then review · human_review or escalated."""
        self.stage(task, "approval")
        self.decide(task, "approver", decision, body)
        self.stage(task, "human_review" if decision == "APPROVE" else "escalated")

    def approve(self, task: dict, days: float) -> None:
        """§3.7: my Approve, with no summary as the page sends it."""
        self.at(days)
        self.decide(task, "me", "APPROVE", "")
        self.move(task, "me", "done", None)

    def request_changes(self, task: dict, days: float, body: str, path: str, text: str, comment: str) -> None:
        """§3.6: my inline comment and summary, then in_progress · rework."""
        self.at(days)
        self.comment(task, "me", comment, path, "new", text)
        self.decide(task, "me", "CHANGES_REQUESTED", body)
        self.move(task, "me", "in_progress", "rework")

    # --- runs and their logs ------------------------------------------------------------

    def start(self, task: dict, days: float) -> None:
        """§3.4 step 1: the worktree, the run row (never left running, out of scope), and backlog → in_progress."""
        self.worktree(task)
        session = str(uuid.uuid4())
        run_id = self.runs.add(task["id"], session, self.at(days))
        log_path = config.data_dir() / "runs" / f"{run_id}.jsonl"
        self.runs.set_log_path(run_id, str(log_path))
        self.run = {"id": run_id, "session": session, "path": log_path, "lines": [], "agents": {}}
        self.counts["runs"] += 1
        self.say("orchestrator", f"Running the factory on #{task['id']} from its current stage.")
        if task["status"] == "backlog":
            self.move(task, "app", "in_progress", None)

    def end(self, task: dict, status: str, error: str | None = None) -> None:
        """012 Q10's record of an exit: succeeded (a result event, exit 0), failed (an is_error result whose
        text is the error, exit 1), or stopped (SIGTERM before any result, 013)."""
        run, code = self.run, {"succeeded": 0, "failed": 1, "stopped": -15}[status]
        if status == "succeeded":
            self.say("orchestrator", f"#{task['id']} is now {task['status']} · {task['stage']}. Stopping here.")
        if status != "stopped":
            run["lines"].append({"type": "result", "subtype": "success" if status == "succeeded" else "error",
                                 "is_error": status == "failed", "num_turns": len(run["lines"]),
                                 "result": error or f"#{task['id']}: {task['status']} · {task['stage']}",
                                 "session_id": run["session"]})
        run["path"].parent.mkdir(parents=True, exist_ok=True)
        run["path"].write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in run["lines"]),
                               encoding="utf-8")
        self.runs.set_exit_code(run["id"], code)
        self.runs.finish(run["id"], status, error, None if status == "stopped" else run["session"], self.tick(2))
        self.run = None

    def event(self, kind: str, parent: str | None, block: dict) -> None:
        self.run["lines"].append({"type": kind, "message": {"role": kind, "content": [block]},
                                  "parent_tool_use_id": parent, "session_id": self.run["session"]})

    def agent(self, who: str) -> str | None:
        """The id of the Agent call that spawned `who` in this run, spawning it on first use (013 Q8)."""
        if who == "orchestrator":
            return None
        if who not in self.run["agents"]:
            tool_id = self.run["agents"][who] = f"toolu_{self.run['id']:02}{len(self.run['lines']):04}"
            self.event("assistant", None, {"type": "tool_use", "id": tool_id, "name": "Agent", "input": {
                "name": who, "subagent_type": who.split("-")[0] if who.startswith("builder") else who,
                "description": f"{who} for this task"}})
        return self.run["agents"][who]

    def say(self, who: str, text: str) -> None:
        if self.run:
            self.event("assistant", self.agent(who), {"type": "text", "text": text})

    def log(self, who: str, command: str, output: str) -> None:
        """A Bash call and its result in the current run's log; nothing outside a run."""
        if self.run:
            parent = self.agent(who)
            tool_id = f"toolu_{self.run['id']:02}{len(self.run['lines']):04}"
            self.event("assistant", parent, {"type": "tool_use", "id": tool_id, "name": "Bash",
                                             "input": {"command": command}})
            self.event("user", parent, {"type": "tool_result", "tool_use_id": tool_id, "content": output})


    # --- the story ----------------------------------------------------------------------

    def story(self) -> dict:
        """Q1: the ready project holds every factory task and the context, the none project the standalone
        submit, and the uncommitted one two backlog tasks. Tasks are created oldest first, so ids follow time."""
        personal, work = self.workspace("personal", 28), self.workspace("work", 13)
        api = self.project(personal, "api-server", "pytest -q", API_COMMITS, "ready", 28)
        self.projects.set_context(api["id"], API_CONTEXT)
        notes = self.project(personal, "notes-cli", "pytest -q", NOTES_COMMITS, "none", 20)
        shop = self.project(work, "web-shop", "npm test", SHOP_COMMITS, "uncommitted", 13)

        # done 24 days ago after one round
        t = self.task(api, "Add health check endpoint", HEALTH["description"], 26)
        self.start(t, 25)
        self.stage(t, "spec")
        self.spec(t, HEALTH["spec"])
        self.build_round(t, HEALTH["r1"], HEALTH["build1"])
        self.approver(t, "APPROVE", "All 4 PASS on round 1. Both criteria have a test, and `pytest -q` is green.")
        self.end(t, "succeeded")
        self.approve(t, 24)

        self.task(shop, "Zoom on product images", ZOOM, 12)
        self.task(shop, "Cart badge counts items, not lines", BADGE, 11)
        self.task(api, "Prefix env vars with API_", ENV_VARS, 10)

        # §3.6: done 3 days ago after an agent round and my rework (trigger human), over two runs
        t = self.task(api, "Case-insensitive email login", EMAIL["description"], 9)
        self.start(t, 8)
        self.stage(t, "spec")
        self.spec(t, EMAIL["spec"])
        self.build_round(t, EMAIL["r1"], EMAIL["build1"], {"code": EMAIL["code1"]})
        self.build_round(t, EMAIL["r2"], EMAIL["build2"])
        self.approver(t, "APPROVE", "All 4 PASS on round 2, and AC1 and AC2 have tests.")
        self.end(t, "succeeded")
        self.request_changes(t, 5, EMAIL["feedback"], "app/users.py", "USERS.get(", EMAIL["comment"])
        self.start(t, 5 - 1 / 144)
        self.build_round(t, EMAIL["r3"], EMAIL["build3"])
        self.approver(t, "APPROVE", "All 4 PASS on round 3, and my feedback on round 2 is addressed: one "
                                    "`normalize()` for stored keys and lookups, with AC3's test.")
        self.end(t, "succeeded")
        self.approve(t, 3)

        # Q2: I stopped this run at spec and dragged the card back; the drag cleared the stage
        t = self.task(api, "OpenAPI docs for admins only", DOCS, 6)
        self.start(t, 5.8)
        self.stage(t, "spec")
        self.say("spec-writer", "Reading the users module to see where an admin flag fits.")
        self.end(t, "stopped")
        self.at(5.7)
        self.move(t, "me", "backlog", None, self.tasks.bottom_position(api["id"], "backlog"))

        # §3.4, MVP §10 assumption 2: still CHANGES after 2 rounds, so the approver escalates
        t = self.task(api, "Retry webhooks with backoff", HOOKS["description"], 4)
        self.start(t, 3.9)
        self.stage(t, "spec")
        self.spec(t, HOOKS["spec"])
        self.build_round(t, HOOKS["r1"], HOOKS["build1"], {"security": HOOKS["security1"], "code": HOOKS["code1"]})
        self.build_round(t, HOOKS["r2"], HOOKS["build2"], {"security": HOOKS["security2"]})
        self.comment(t, "security", HOOKS["comment"], "app/webhooks.py", "new", "httpx.post(")
        self.approver(t, "ESCALATE", HOOKS["escalate"])
        self.end(t, "succeeded")

        # §3.6: approved by the agents, then my CHANGES_REQUESTED; no run since (Q2)
        t = self.task(api, "Export the audit log as CSV", AUDIT["description"], 3)
        self.at(2.9)
        self.move(t, "app", "in_progress", None)
        self.stage(t, "spec")
        self.spec(t, AUDIT["spec"])
        self.build_round(t, AUDIT["r1"], AUDIT["build1"])
        self.approver(t, "APPROVE", "All 4 PASS on round 1; both criteria have a test.")
        self.request_changes(t, 1, AUDIT["feedback"], "app/audit.py", '",".join(', AUDIT["comment"])

        # waiting on me: round 2 has every change kind (Q4), and comments from me and a reviewer
        t = self.task(api, "Rate-limit login endpoint", LIMIT["description"], 2)
        self.start(t, 1.9)
        self.stage(t, "spec")
        self.spec(t, LIMIT["spec"])
        self.build_round(t, LIMIT["r1"], LIMIT["build1"], {"security": LIMIT["security1"]})
        self.comment(t, "security", LIMIT["comment"], "app/limits.py", "new", "X-Forwarded-For")
        self.build_round(t, LIMIT["r2"], LIMIT["build2"])
        self.approver(t, "APPROVE", LIMIT["approve"])
        self.end(t, "succeeded")
        self.at(1)
        self.comment(t, "me", LIMIT["mine"], "app/auth.py", "old", "app.throttle")
        self.comment(t, "me", "Trying this behind the staging proxy before I approve.")

        # stalled · build: the run hit the usage limit while building round 2 (§3.4, Q2)
        t = self.task(api, "Structured JSON logging", LOGS["description"], 1.5)
        self.start(t, 1.4)
        self.stage(t, "spec")
        self.spec(t, LOGS["spec"])
        self.build_round(t, LOGS["r1"], LOGS["build1"], {"code": LOGS["code1"]})
        self.stage(t, "build")
        self.say(f"builder-{t['id']}", "Fixing the timestamp: UTC with a Z, and a test for it.")
        self.end(t, "failed", "Claude AI usage limit reached. Your limit will reset at 6pm.")

        # all 4 verdicts in, the approver not yet
        t = self.task(api, "Request ID on every response", REQUEST_ID["description"], 1)
        self.at(0.95)
        self.move(t, "app", "in_progress", None)
        self.stage(t, "spec")
        self.spec(t, REQUEST_ID["spec"])
        self.build_round(t, REQUEST_ID["r1"], REQUEST_ID["build1"])
        self.stage(t, "approval")

        # §3.8, §7.4: /factory-submit, with no factory, no worktree, and no agent review
        self.standalone(notes, "Fix crash on an empty notes file", NOTES_FIX["description"], 0.8, NOTES_FIX["files"])

        # 2 of 4 verdicts posted
        t = self.task(api, "Paginate GET /users", PAGES["description"], 0.5)
        self.at(0.45)
        self.move(t, "app", "in_progress", None)
        self.stage(t, "spec")
        self.spec(t, PAGES["spec"])
        self.stage(t, "build")
        self.round(t, PAGES["r1"], PAGES["build1"])
        self.stage(t, "agent_review")
        self.verdicts(t, {"code": PAGES["code1"]}, ("security", "code"))
        self.comment(t, "code", PAGES["comment"], "app/users.py", "new", "def list_users(")

        # in_progress · spec: no spec yet, no rounds
        t = self.task(api, "Password reset by email", RESET, 0.3)
        self.at(0.28)
        self.move(t, "app", "in_progress", None)
        self.stage(t, "spec")
        return self.counts


# --- the demo content: three small repos, and what each task writes ---------------------------------

API_README = """# api-server

A small FastAPI service: login, users, and a few admin endpoints. `fctl seed` made it as demo data.

## Run it

```sh
uv run fastapi dev app/main.py
```

## Test it

```sh
uv run pytest -q
```

## Layout

- `app/`: the service, one module per area, each with its own `router`
- `tests/`: one test file per module
"""
API_MAIN = """from fastapi import FastAPI

from app import auth, users

app = FastAPI(title="api-server")
app.include_router(auth.router)
app.include_router(users.router)
"""
API_SETTINGS = """import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///api.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
"""
API_AUTH = """from fastapi import APIRouter, Form, HTTPException, Request

from app.throttle import too_many
from app.users import authenticate
from app.utils import client_ip

router = APIRouter()


@router.post("/login")
def login(request: Request, email: str = Form(), password: str = Form()):
    if too_many(client_ip(request)):
        raise HTTPException(429, "Too many attempts. Wait a second and try again.")
    user = authenticate(email, password)
    if not user:
        raise HTTPException(401, "Wrong email or password.")
    return {"user": user.id}
"""
API_UTILS = """from fastapi import Request


def client_ip(request: Request) -> str:
    # the caller's address, as the socket sees it
    return request.client.host if request.client else "unknown"


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"
"""
API_USERS = """from dataclasses import dataclass

from fastapi import APIRouter

router = APIRouter()


@dataclass
class User:
    id: int
    email: str


USERS = {
    "ada@example.com": (User(1, "ada@example.com"), "correct horse"),
    "alan@example.com": (User(2, "alan@example.com"), "battery staple"),
}


def authenticate(email: str, password: str) -> User | None:
    found = USERS.get(email)
    return found[0] if found and found[1] == password else None


@router.get("/users")
def list_users():
    return [user for user, _ in USERS.values()]
"""
API_COMMITS = [
    ("Initial commit", {
        "README.md": API_README,
        ".gitignore": "__pycache__/\n.venv/\n",
        "pyproject.toml": '[project]\nname = "api-server"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n'
                          'dependencies = ["fastapi", "httpx", "python-multipart"]\n\n'
                          '[dependency-groups]\ndev = ["pytest"]\n',
        "app/__init__.py": "",
        "app/settings.py": API_SETTINGS,
    }),
    ("Add login and users", {
        "app/main.py": API_MAIN,
        "app/auth.py": API_AUTH,
        "app/users.py": API_USERS,
        "app/utils.py": API_UTILS,
        "app/throttle.py": """import time

SEEN: dict[str, float] = {}


def too_many(key: str) -> bool:
    # one attempt per second per key
    last, SEEN[key] = SEEN.get(key, 0.0), time.monotonic()
    return SEEN[key] - last < 1.0
""",
        "tests/test_auth.py": """from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login():
    r = client.post("/login", data={"email": "ada@example.com", "password": "correct horse"})
    assert r.status_code == 200


def test_wrong_password():
    r = client.post("/login", data={"email": "ada@example.com", "password": "nope"})
    assert r.status_code == 401
""",
    }),
]
API_CONTEXT = """## Stack
- Python 3.12 and FastAPI, managed with uv. Tests: `uv run pytest -q`.
- No database yet: users live in `app/users.py`.

## Conventions
- One module per area under `app/`, each with its own `router`, included in `app/main.py`.
- Errors are an `HTTPException` with a sentence the caller can act on.
"""

HEALTH = {
    "description": "The load balancer needs an endpoint that answers without a login.\n\n"
                   '- `GET /health` answers 200 with `{"status": "ok"}`\n- no database check for now\n',
    "spec": """## Goal
`GET /health` tells the load balancer that the app is up.

## Acceptance criteria
- [ ] AC1: `GET /health` → 200 `{"status": "ok"}`.
- [ ] AC2: it needs no login.

## Out of scope
- Checking downstream services.
""",
    "r1": {
        "app/health.py": """from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
""",
        "app/main.py": API_MAIN.replace("auth, users", "auth, health, users") + "app.include_router(health.router)\n",
        "tests/test_health.py": """from fastapi.testclient import TestClient

from app.main import app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
""",
    },
    "build1": """## Changes
- `app/health.py`: the `/health` route.
- `app/main.py`: includes its router.

## Criteria → tests
- AC1, AC2 → `tests/test_health.py::test_health`

## Test output
3 passed in 0.31s
""",
}

EMAIL = {
    "description": "`Ada@Example.com` can't log in, because the lookup is case-sensitive. "
                   "An email should match **whatever its case**.\n",
    "spec": """## Goal
Logging in works whatever the case of the email, and with stray spaces around it.

## Acceptance criteria
- [ ] AC1: `ADA@example.com` with the right password → 200.
- [ ] AC2: ` ada@example.com ` (with spaces) → 200.
- [ ] AC3: a user stored with a mixed-case email can log in.
""",
    "r1": {
        "app/users.py": API_USERS.replace("USERS.get(email)", "USERS.get(email.lower())"),
        "tests/test_users.py": """from app.users import authenticate


def test_any_case():
    assert authenticate("ADA@example.com", "correct horse")
""",
    },
    "build1": "## Changes\n- `app/users.py`: look emails up lower-cased.\n\n## Criteria → tests\n"
              "- AC1 → `tests/test_users.py::test_any_case`\n\n## Test output\n3 passed in 0.29s\n",
    "code1": "AC2 isn't met: `' ada@example.com '` still misses, because only `.lower()` runs. "
             "Strip it as well, and add AC2's test.",
    "r2": {
        "app/users.py": API_USERS.replace("USERS.get(email)", "USERS.get(email.strip().lower())"),
        "tests/test_users.py": """from app.users import authenticate


def test_any_case():
    assert authenticate("ADA@example.com", "correct horse")


def test_spaces():
    assert authenticate(" ada@example.com ", "correct horse")
""",
    },
    "build2": "## Changes\n- `app/users.py`: strip, then lower-case.\n- `tests/test_users.py`: AC2's test.\n\n"
              "## Review findings\n- code · spaces still miss → fixed\n\n## Test output\n4 passed in 0.30s\n",
    "feedback": "AC3 has no test, and it would fail: the keys in `USERS` are stored as typed. "
                "Normalise them when they're added too, with one helper used in both places.",
    "comment": "The same normalisation belongs where `USERS` is filled.",
    "r3": {
        "app/users.py": API_USERS.replace("""USERS = {
    "ada@example.com": (User(1, "ada@example.com"), "correct horse"),
    "alan@example.com": (User(2, "alan@example.com"), "battery staple"),
}""", """def normalize(email: str) -> str:
    return email.strip().lower()


USERS = {normalize(user.email): (user, password) for user, password in [
    (User(1, "ada@example.com"), "correct horse"),
    (User(2, "Alan@Example.com"), "battery staple"),
]}""").replace("USERS.get(email)", "USERS.get(normalize(email))"),
        "tests/test_users.py": """from app.users import authenticate


def test_any_case():
    assert authenticate("ADA@example.com", "correct horse")


def test_spaces():
    assert authenticate(" ada@example.com ", "correct horse")


def test_stored_mixed_case():
    assert authenticate("alan@example.com", "battery staple")
""",
    },
    "build3": "## Changes\n- `app/users.py`: `normalize()` for stored keys and lookups.\n"
              "- `tests/test_users.py`: AC3's test, with `Alan@Example.com` stored.\n\n"
              "## Feedback\n- me · normalise on the way in → done\n\n## Test output\n5 passed in 0.31s\n",
}

DOCS = """`/docs` and `/openapi.json` are public. Serve them to admins only.

1. Add an `is_admin` flag to `User`.
2. Mount the docs routes behind a dependency that checks it.
"""

HOOKS = {
    "description": "Webhook deliveries fail for good on the first timeout. Retry them:\n\n"
                   "- up to **5 attempts**\n- exponential backoff, starting at 1 s\n",
    "spec": """## Goal
A webhook delivery survives a receiver that is down for a minute.

## Acceptance criteria
- [ ] AC1: a 5xx or a timeout is retried, up to 5 attempts in all.
- [ ] AC2: the waits double from 1 s, with jitter.
- [ ] AC3: a 4xx isn't retried.
- [ ] AC4: deliveries go only to public addresses.
""",
    "r1": {
        "app/webhooks.py": """import time

import httpx

ATTEMPTS = 5


def deliver(url: str, payload: dict) -> bool:
    for attempt in range(ATTEMPTS):
        try:
            r = httpx.post(url, json=payload, timeout=5, follow_redirects=True)
            if r.status_code < 500:
                return r.is_success
        except httpx.TransportError:
            pass
        time.sleep(2**attempt)
    return False
""",
        "tests/test_webhooks.py": """import httpx

from app import webhooks


def test_retries_5xx(monkeypatch):
    replies = iter([httpx.Response(503), httpx.Response(200)])
    monkeypatch.setattr(webhooks.httpx, "post", lambda *a, **k: next(replies))
    monkeypatch.setattr(webhooks.time, "sleep", lambda s: None)
    assert webhooks.deliver("https://example.com/hook", {})
""",
    },
    "build1": "## Changes\n- `app/webhooks.py`: `deliver()` with 5 attempts and doubling waits.\n\n"
              "## Criteria → tests\n- AC1 → `tests/test_webhooks.py::test_retries_5xx`\n\n## Test output\n"
              "3 passed in 0.36s\n",
    "security1": "AC4: `follow_redirects=True` lets a receiver bounce the request to `http://169.254.169.254/` "
                 "or anything else on our network. Don't follow redirects, and refuse private addresses.",
    "code1": "AC2: no jitter, and it sleeps after the last attempt too, which adds 16 s to every failed delivery.",
    "r2": {
        "app/webhooks.py": """import random
import time

import httpx

ATTEMPTS = 5


def deliver(url: str, payload: dict) -> bool:
    for attempt in range(ATTEMPTS):
        try:
            r = httpx.post(url, json=payload, timeout=5)
            if r.status_code < 500:
                return r.is_success
        except httpx.TransportError:
            pass
        if attempt < ATTEMPTS - 1:
            time.sleep(2**attempt + random.uniform(0, 1))
    return False
""",
    },
    "build2": """## Changes
- `app/webhooks.py`: no redirects, jitter on every wait, and no wait after the last attempt.

## Review findings
- security · redirects → fixed. Private addresses → not yet, see the open question.
- code · jitter and the last wait → fixed

## Open questions
- AC4: block private ranges by resolving the host first, or keep an allowlist of receivers? Left as is.

## Test output
3 passed in 0.35s
""",
    "security2": "AC4 still fails: `url` can be `http://localhost:8000/admin` or `http://10.0.0.5/`. Resolve the "
                 "host and refuse private, loopback, and link-local addresses before sending.",
    "comment": "`url` goes out unchecked. Resolve it and refuse private ranges first.",
    "escalate": "Round cap reached (2 rounds), and security is still at CHANGES on round 2: webhook URLs can "
                "reach private addresses (AC4). The builder asks whether to block private ranges or allowlist "
                "receivers, which is a product decision.",
}

AUDIT = {
    "description": "Admins need the audit log as a CSV for the quarterly review: `GET /admin/audit.csv`.\n",
    "spec": """## Goal
Admins download the audit log as CSV.

## Acceptance criteria
- [ ] AC1: `GET /admin/audit.csv` → CSV with the header row `at,user,action`.
- [ ] AC2: one row per event, oldest first.
""",
    "r1": {
        "app/audit.py": r'''from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()
EVENTS: list[dict] = []  # {"at", "user", "action"}, appended by the auth and users routes


@router.get("/admin/audit.csv", response_class=PlainTextResponse)
def export():
    rows = ["at,user,action"] + [",".join([e["at"], e["user"], e["action"]]) for e in EVENTS]
    return "\n".join(rows) + "\n"
''',
        "app/main.py": API_MAIN.replace("auth, users", "audit, auth, users") + "app.include_router(audit.router)\n",
        "tests/test_audit.py": """from fastapi.testclient import TestClient

from app import audit
from app.main import app


def test_header_and_rows():
    audit.EVENTS[:] = [{"at": "2026-10-01T10:00:00Z", "user": "ada@example.com", "action": "login"}]
    r = TestClient(app).get("/admin/audit.csv")
    assert r.text.splitlines() == ["at,user,action", "2026-10-01T10:00:00Z,ada@example.com,login"]
""",
    },
    "build1": "## Changes\n- `app/audit.py`: `GET /admin/audit.csv`.\n- `app/main.py`: includes its router.\n\n"
              "## Criteria → tests\n- AC1, AC2 → `tests/test_audit.py::test_header_and_rows`\n\n"
              "## Test output\n3 passed in 0.33s\n",
    "feedback": "Fields aren't quoted, so an action like `rename, then delete` splits into two columns. Use the "
                "`csv` module, add a test with a comma in a field, and send "
                "`Content-Disposition: attachment; filename=audit.csv` so the browser downloads it.",
    "comment": "A comma in any field breaks the row here. `csv.writer` quotes for you.",
}

LIMIT_V1 = """import time
from collections import defaultdict, deque

from fastapi import Request

LIMIT = 5  # failed logins per window
WINDOW = 60.0  # seconds
FAILS: dict[str, deque] = defaultdict(deque)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


def blocked(key: str) -> bool:
    now, fails = time.monotonic(), FAILS[key]
    while fails and now - fails[0] > WINDOW:
        fails.popleft()
    return len(fails) >= LIMIT


def fail(key: str) -> None:
    FAILS[key].append(time.monotonic())
"""
LIMIT_TEST = """from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
WRONG = {"email": "ada@example.com", "password": "nope"}


def test_sixth_failure_is_429():
    codes = [client.post("/login", data=WRONG).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
"""
LIMIT = {
    "description": "Allow at most **5 failed logins per minute** per client. Today `app/throttle.py` allows "
                   "one attempt per second, which a script gets around easily.\n",
    "spec": """## Goal
Slow down password guessing: at most 5 failed logins per minute per client.

## Acceptance criteria
- [ ] AC1: the 6th failed login within 60 s from one client → 429.
- [ ] AC2: a successful login doesn't count.
- [ ] AC3: the client is the socket address; `X-Forwarded-For` counts only from `TRUSTED_PROXY`.
- [ ] AC4: `app/throttle.py` is gone.
""",
    "r1": {
        "app/limits.py": LIMIT_V1,
        "app/auth.py": """from fastapi import APIRouter, Form, HTTPException, Request

from app import limits
from app.users import authenticate

router = APIRouter()


@router.post("/login")
def login(request: Request, email: str = Form(), password: str = Form()):
    key = limits.client_key(request)
    if limits.blocked(key):
        raise HTTPException(429, "Too many failed logins. Try again in a minute.")
    user = authenticate(email, password)
    if not user:
        limits.fail(key)
        raise HTTPException(401, "Wrong email or password.")
    return {"user": user.id}
""",
        "tests/test_limits.py": LIMIT_TEST,
    },
    "build1": "## Changes\n- `app/limits.py`: a sliding window of failed logins per client.\n"
              "- `app/auth.py`: checks it before the password, and counts only failures.\n\n"
              "## Criteria → tests\n- AC1 → `tests/test_limits.py::test_sixth_failure_is_429`\n\n"
              "## Test output\n4 passed in 0.40s\n",
    "security1": "AC3 isn't met. `client_key` trusts `X-Forwarded-For` from anyone, so a script sends a new "
                 "value with each guess and is never limited. Use the socket address, and read the header only "
                 "when the request comes from `TRUSTED_PROXY`.",
    "comment": "Anyone can set this header. Trust it only from `settings.TRUSTED_PROXY`.",
    "r2": {
        "app/limits.py": """import time
from collections import defaultdict, deque

from fastapi import Request

from app import settings
from app.net import client_ip

FAILS: dict[str, deque] = defaultdict(deque)


def client_key(request: Request) -> str:
    # X-Forwarded-For only when the request comes from our own proxy
    if settings.TRUSTED_PROXY and client_ip(request) == settings.TRUSTED_PROXY:
        return request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or client_ip(request)
    return client_ip(request)


def blocked(key: str) -> bool:
    now, fails = time.monotonic(), FAILS[key]
    while fails and now - fails[0] > settings.LOGIN_WINDOW:
        fails.popleft()
    return len(fails) >= settings.LOGIN_LIMIT


def fail(key: str) -> None:
    FAILS[key].append(time.monotonic())
""",
        "app/settings.py": API_SETTINGS + 'TRUSTED_PROXY = os.environ.get("TRUSTED_PROXY", "")\n'
                           'LOGIN_LIMIT = int(os.environ.get("LOGIN_LIMIT", "5"))  # failed logins per window\n'
                           "LOGIN_WINDOW = 60.0  # seconds\n",
        "app/throttle.py": None,
        "app/utils.py": None,
        "app/net.py": API_UTILS.replace("# the caller's address, as the socket sees it",
                                        "# the socket's address; limits.client_key decides about proxies"),
        "docs/rate-limit.png": PNG,
        "tests/test_limits.py": LIMIT_TEST + """

def test_forwarded_for_is_ignored():
    for n in range(6):
        r = client.post("/login", data=WRONG, headers={"X-Forwarded-For": f"10.0.0.{n}"})
    assert r.status_code == 429
""",
    },
    "build2": """## Changes
- `app/limits.py`: the client is the socket address; `X-Forwarded-For` counts only from `TRUSTED_PROXY`.
- `app/settings.py`: `TRUSTED_PROXY`, `LOGIN_LIMIT`, and `LOGIN_WINDOW`.
- `app/utils.py` → `app/net.py`: it only holds network helpers.
- `app/throttle.py`: deleted (AC4).
- `docs/rate-limit.png`: the flow, for the README.

## Review findings
- security · `X-Forwarded-For` trusted from anyone → fixed, with a test for a spoofed header

## Test output
5 passed in 0.42s
""",
    "approve": "All 4 PASS on round 2. Security's round-1 finding is fixed and tested with a spoofed header, "
               "and every criterion has a test.",
    "mine": "Good riddance. Nothing else imported `app.throttle`?",
}

LOGS = {
    "description": "Logs should be one JSON object per line, so the log shipper can parse them. Include the "
                   "level, the message, and the time in UTC.\n",
    "spec": """## Goal
The app logs one JSON object per line.

## Acceptance criteria
- [ ] AC1: each log line is a JSON object with `at`, `level`, and `msg`.
- [ ] AC2: `at` is UTC ISO 8601 with a `Z`.
""",
    "r1": {
        "app/log.py": """import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"at": self.formatTime(record), "level": record.levelname, "msg": record.getMessage()})


def setup() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
""",
        "app/main.py": API_MAIN.replace("auth, users", "auth, log, users").replace("app = FastAPI",
                                                                                   "log.setup()\napp = FastAPI"),
        "tests/test_log.py": """import json
import logging

from app.log import JsonFormatter


def test_one_object_per_line():
    record = logging.LogRecord("app", logging.INFO, __file__, 1, "hello", None, None)
    assert json.loads(JsonFormatter().format(record))["msg"] == "hello"
""",
    },
    "build1": "## Changes\n- `app/log.py`: a JSON formatter and `setup()`.\n- `app/main.py`: calls `setup()` first.\n\n"
              "## Criteria → tests\n- AC1 → `tests/test_log.py::test_one_object_per_line`\n\n"
              "## Test output\n3 passed in 0.30s\n",
    "code1": "AC2 isn't met: `formatTime` gives local time like `2026-10-18 14:02:11,123`, with no zone. Format "
             "`record.created` as UTC with a `Z`, and test it.",
}

REQUEST_ID = {
    "description": "Every response should carry an `X-Request-ID`, reusing the caller's if it sent one, so "
                   "support can match a ticket to our logs.\n",
    "spec": """## Goal
Each request has an id that shows in the response and can be matched to logs.

## Acceptance criteria
- [ ] AC1: every response has an `X-Request-ID` header.
- [ ] AC2: a caller's `X-Request-ID` is kept if it is 1–64 characters of `[A-Za-z0-9-]`; otherwise it gets a
  new UUID.
""",
    "r1": {
        "app/request_id.py": """import re
import uuid

from fastapi import Request

VALID = re.compile(r"[A-Za-z0-9-]{1,64}")


async def request_id(request: Request, call_next):
    sent = request.headers.get("X-Request-ID", "")
    rid = sent if VALID.fullmatch(sent) else str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response
""",
        "app/main.py": API_MAIN.replace("from app import auth, users\n",
                                        "from app import auth, users\nfrom app.request_id import request_id\n")
        + 'app.middleware("http")(request_id)\n',
        "tests/test_request_id.py": """from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_new_id():
    assert len(client.get("/users").headers["X-Request-ID"]) == 36


def test_keeps_valid_id():
    assert client.get("/users", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"


def test_replaces_invalid_id():
    assert client.get("/users", headers={"X-Request-ID": "a b"}).headers["X-Request-ID"] != "a b"
""",
    },
    "build1": "## Changes\n- `app/request_id.py`: the middleware.\n- `app/main.py`: installs it.\n\n"
              "## Criteria → tests\n- AC1 → `tests/test_request_id.py::test_new_id`\n"
              "- AC2 → `test_keeps_valid_id`, `test_replaces_invalid_id`\n\n## Test output\n5 passed in 0.34s\n",
}

PAGES = {
    "description": "`GET /users` returns everyone at once. Page it with `?limit=` and `?offset=`.\n",
    "spec": """## Goal
`GET /users` returns one page at a time.

## Acceptance criteria
- [ ] AC1: `?limit=` (default 50, at most 200) and `?offset=` (default 0) pick the page.
- [ ] AC2: a limit over 200 → 422.
""",
    "r1": {
        "app/users.py": API_USERS.replace("""def list_users():
    return [user for user, _ in USERS.values()]""", """def list_users(limit: int = 50, offset: int = 0):
    return [user for user, _ in USERS.values()][offset:offset + limit]"""),
        "tests/test_users_paging.py": """from fastapi.testclient import TestClient

from app.main import app


def test_limit_and_offset():
    r = TestClient(app).get("/users", params={"limit": 1, "offset": 1})
    assert [u["id"] for u in r.json()] == [2]
""",
    },
    "build1": "## Changes\n- `app/users.py`: `limit` and `offset` on `GET /users`.\n\n## Criteria → tests\n"
              "- AC1 → `tests/test_users_paging.py::test_limit_and_offset`\n\n## Test output\n3 passed in 0.31s\n",
    "code1": "AC2 isn't met: nothing caps `limit`, so `?limit=1000000` returns every user. Use "
             "`Query(50, ge=1, le=200)`, and add AC2's test.",
    "comment": "Cap this: `limit: int = Query(50, ge=1, le=200)`.",
}

RESET = """Users who forget their password get a one-time link by email.

- valid for **30 minutes**
- works once
"""
ENV_VARS = """Every setting should read an `API_`-prefixed variable, so ours don't clash with other services in one
compose file:

- `DATABASE_URL` → `API_DATABASE_URL`
- `SECRET_KEY` → `API_SECRET_KEY`

Keep reading the old names for one release, with a warning.
"""

NOTES_STORE = """import json
from pathlib import Path

PATH = Path.home() / ".notes.json"


def load(path: Path = PATH) -> list[str]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save(notes: list[str], path: Path = PATH) -> None:
    path.write_text(json.dumps(notes, indent=2))
"""
NOTES_COMMITS = [
    ("Initial commit", {
        "README.md": """# notes-cli

Jot notes from the terminal. `fctl seed` made it as demo data; it has no factory.

```sh
notes add "buy milk"
notes list
```
""",
        "pyproject.toml": '[project]\nname = "notes-cli"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n\n'
                          '[project.scripts]\nnotes = "notes.cli:main"\n',
        "notes/__init__.py": "",
    }),
    ("Add the store", {
        "notes/store.py": NOTES_STORE,
        "tests/test_store.py": """from notes import store


def test_round_trip(tmp_path):
    store.save(["a"], tmp_path / "n.json")
    assert store.load(tmp_path / "n.json") == ["a"]
""",
    }),
    ("Add the CLI", {
        "notes/cli.py": """import sys

from notes import store


def main(argv: list[str] = sys.argv[1:]) -> None:
    notes = store.load()
    if argv[:1] == ["add"]:
        store.save(notes + [" ".join(argv[1:])])
    elif argv[:1] == ["list"]:
        for n, note in enumerate(notes, 1):
            print(f"{n}. {note}")
    else:
        print("usage: notes add TEXT | notes list")
""",
    }),
]
NOTES_FIX = {
    "description": "`notes list` crashed with `JSONDecodeError` when `~/.notes.json` was empty, for example "
                   "after a failed save. `load()` now treats an empty file as no notes. Tests: `pytest -q` "
                   "(2 passed).\n",
    "files": {  # §7.4: a tracked change and an untracked test file
        "notes/store.py": NOTES_STORE.replace("    return json.loads(path.read_text())",
                                              "    text = path.read_text()\n"
                                              "    return json.loads(text) if text.strip() else []"),
        "tests/test_empty_file.py": """from notes import store


def test_empty_file(tmp_path):
    (tmp_path / "n.json").write_text("")
    assert store.load(tmp_path / "n.json") == []
""",
    },
}

ZOOM = """## What
Hovering a product image shows a **2×** zoom that follows the cursor.

## Notes
- On phones, a tap toggles the zoom.
- Use the images in `public/`; no new sizes.
"""
BADGE = """`Cart.badge` returns `this.lines.length`, so three of the same mug show **1**. Return the sum of
`quantity` instead, and add a test.
"""
SHOP_COMMITS = [
    ("Initial commit", {
        "README.md": """# web-shop

The storefront's cart. `fctl seed` made it as demo data. Its factory is written but not committed yet.

## Develop

```sh
npm test
```

`data/products.csv` is the full catalogue export, over 1 MB, and `public/logo.png` is the logo.
""",
        "package.json": '{\n  "name": "web-shop",\n  "private": true,\n  "type": "module",\n'
                        '  "scripts": { "test": "node --test" }\n}\n',
        "src/index.js": 'import { Cart } from "./cart.js";\n\nexport const cart = new Cart();\n',
    }),
    ("Add the cart", {
        "src/cart.js": """export class Cart {
  lines = [];

  add(product, quantity = 1) {
    const line = this.lines.find((l) => l.product.id === product.id);
    if (line) line.quantity += quantity;
    else this.lines.push({ product, quantity });
  }

  get badge() {
    return this.lines.length;
  }
}
""",
    }),
    ("Add the catalogue and logo", {
        "public/logo.png": PNG,
        # Q9: one byte over the code page's limit, in a repo with no worktrees to copy it into
        "data/products.csv": ("id,name,price\n" + "".join(f"{i},Product {i},{i % 50 + 0.99:.2f}\n"
                                                         for i in range(1, 60000)))[:config.MAX_VIEW] + "\n",
    }),
]
