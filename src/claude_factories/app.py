"""The FastAPI app behind `fctl serve`."""

import codecs
import json
import os
import re
import shlex
import sqlite3
import subprocess
import threading
import uuid
from contextlib import asynccontextmanager, closing
from datetime import datetime
from itertools import takewhile
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Literal, get_args

import jinja2
from markdown_it import MarkdownIt
from markupsafe import Markup
from pydantic import BaseModel, Field, FiniteFloat, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db

HERE = Path(__file__).parent
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SKILL = ".claude/skills/factory/SKILL.md"
COLUMNS = ("backlog", "in_progress", "review", "done")
Reviewer = Literal["security", "ux", "ui", "code"]
REVIEWERS = get_args(Reviewer)
NOSNIFF = {"X-Content-Type-Options": "nosniff"}  # agent-written text, never sniffed as HTML
MAX_PATCH = 5 * 1024 * 1024  # Q5: UTF-8 bytes of the patch alone
STAGE_STATUS = {  # docs/data-model-and-api.md §5.2
    "spec": "in_progress", "build": "in_progress", "agent_review": "in_progress",
    "approval": "in_progress", "rework": "in_progress",
    "human_review": "review", "escalated": "review",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(title="Claude Factories", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["local_time"] = (
    lambda iso: datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")
)
# Q13: raw HTML off, and markdown-it's link check drops javascript:/vbscript:/file:/data: URLs.
# This filter is the only place agent text becomes Markup.
MD = MarkdownIt("js-default", {"html": False})
templates.env.filters["markdown"] = lambda text: Markup(MD.render(text or ""))


@app.middleware("http")
async def local_safety(request: Request, call_next):
    """docs/MVP.md §4.5: block DNS rebinding (Host) and CSRF (X-Requested-By)."""
    hostname = request.headers.get("host", "").partition(":")[0].lower()
    if hostname not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Host must be 127.0.0.1 or localhost"}, status_code=403)
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-by") != "fctl":
        return JSONResponse({"detail": "X-Requested-By: fctl header required"}, status_code=403)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 without each error's echoed `input`: json.loads lets NaN and Infinity
    in, and echoing them back would fail to encode as JSON and turn the 422 into a 500."""
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)


@app.exception_handler(StarletteHTTPException)
async def page_not_found(request: Request, exc: StarletteHTTPException):
    """A browser GET of a missing page, task, or round gets a page, not JSON. /api and every other
    status keep FastAPI's JSON."""
    if exc.status_code == 404 and request.method == "GET" and not request.url.path.startswith("/api/"):
        return templates.TemplateResponse(request, "error.html", {"detail": exc.detail}, status_code=404)
    return await http_exception_handler(request, exc)


@app.exception_handler(UnicodeEncodeError)
async def unencodable(request: Request, exc: UnicodeEncodeError):
    """A JSON `\\ud800` escape decodes to a lone surrogate, which UTF-8 and SQLite reject: a 422, not
    a 500. Raised inside a transaction, so it rolls back."""
    return JSONResponse({"detail": "text must not contain lone surrogates"}, status_code=422)


# --- Helpers -----------------------------------------------------------------


def query(sql: str, args=()) -> list[sqlite3.Row]:
    with closing(db.connect()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, args).fetchall()


def one_or_404(sql: str, args, detail: str | None = None) -> sqlite3.Row:
    found = query(sql, args)
    if not found:
        raise HTTPException(404, detail)
    return found[0]


def get_or_create_workspace(conn: sqlite3.Connection, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO workspaces (name, created_at) VALUES (?, ?)", (name, db.now()))
    return conn.execute("SELECT id FROM workspaces WHERE name = ?", (name,)).fetchone()[0]


def workspaces() -> list[sqlite3.Row]:
    return query(
        "SELECT w.id, w.name, COUNT(p.id) AS projects FROM workspaces w"
        " LEFT JOIN projects p ON p.workspace_id = w.id GROUP BY w.id ORDER BY w.name"
    )


def factory_state(path: str, default_branch: str) -> str:
    """Q6: ready = SKILL.md committed on the default branch (MVP §3.2), uncommitted = only on disk."""
    try:
        committed = subprocess.run(
            ["git", "-C", path, "cat-file", "-e", f"{default_branch}:{SKILL}"],
            capture_output=True, timeout=10,
        ).returncode == 0
    except (OSError, ValueError, subprocess.TimeoutExpired):  # no git, a NUL in the path, a hung repo
        committed = False
    if committed:
        return "ready"
    return "uncommitted" if os.path.isfile(os.path.join(path, SKILL)) else "none"


async def form_field(request: Request, name: str) -> str:
    """Q10: htmx sends urlencoded forms; parse with the stdlib (no python-multipart)."""
    values = parse_qs((await request.body()).decode(errors="replace")).get(name)
    return values[0].strip() if values else ""


def hx_redirect(url: str) -> Response:
    return Response(status_code=204, headers={"HX-Redirect": url})


def round_summaries(task_id: int) -> list[dict]:
    """A task's rounds by n: file count, +/− sums, and all 4 verdicts ('pending' if missing)."""
    rounds = query(
        "SELECT r.id, r.n, r.trigger, COUNT(f.path) AS files, COALESCE(SUM(f.additions), 0) AS additions,"
        " COALESCE(SUM(f.deletions), 0) AS deletions FROM rounds r"
        " LEFT JOIN round_files f ON f.round_id = r.id WHERE r.task_id = ? GROUP BY r.id ORDER BY r.n",
        (task_id,),
    )
    verdicts = {
        (v["round_id"], v["reviewer"]): v["verdict"]
        for v in query(
            "SELECT v.round_id, v.reviewer, v.verdict FROM verdicts v"
            " JOIN rounds r ON r.id = v.round_id WHERE r.task_id = ?",
            (task_id,),
        )
    }
    return [
        {"n": r["n"], "trigger": r["trigger"], "files": r["files"], "additions": r["additions"],
         "deletions": r["deletions"],
         "verdicts": {who: verdicts.get((r["id"], who), "pending") for who in REVIEWERS}}
        for r in rounds
    ]


def latest_run(task_id: int) -> dict | None:
    """Q9: the task's latest run whatever its status, so a failed one can show as stalled."""
    found = query("SELECT id, status FROM runs WHERE task_id = ? ORDER BY id DESC LIMIT 1", (task_id,))
    return dict(found[0]) if found else None


# --- JSON API (docs/data-model-and-api.md §6.1) -------------------------------


class ConnectBody(BaseModel):
    path: str
    workspace: str
    name: str
    remote_url: str | None = None
    default_branch: str
    test_cmd: str | None = None


@app.get("/api/workspaces")
def list_workspaces():
    return [dict(w) for w in workspaces()]


@app.post("/api/projects/connect")
def connect_project(body: ConnectBody, request: Request):
    workspace, name, branch = body.workspace.strip(), body.name.strip(), body.default_branch
    if not os.path.isabs(body.path):
        raise HTTPException(422, "path must be absolute")
    if not workspace:
        raise HTTPException(422, "workspace must not be blank")
    if not name:
        raise HTTPException(422, "name must not be blank")
    if not branch or branch.startswith("-"):  # it becomes a git argument
        raise HTTPException(422, "default_branch must be non-empty and not start with '-'")
    with closing(db.connect()) as conn, conn:
        ws_id = get_or_create_workspace(conn, workspace)
        row = conn.execute("SELECT id FROM projects WHERE path = ?", (body.path,)).fetchone()
        if row:  # Q4: path is the key; a null test_cmd keeps the stored one
            project_id = row[0]
            conn.execute(
                "UPDATE projects SET workspace_id = ?, name = ?, remote_url = ?, default_branch = ?,"
                " test_cmd = COALESCE(?, test_cmd) WHERE id = ?",
                (ws_id, name, body.remote_url, branch, body.test_cmd, project_id),
            )
        else:
            project_id = conn.execute(
                "INSERT INTO projects (workspace_id, name, path, remote_url, default_branch, test_cmd,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ws_id, name, body.path, body.remote_url, branch, body.test_cmd, db.now()),
            ).lastrowid
    return {"id": project_id, "created": row is None, "url": f"{request.base_url}projects/{project_id}"}


@app.get("/api/projects")
def find_project(path: str):
    found = query("SELECT id, name, path, default_branch FROM projects WHERE path = ?", (path,))
    if not found:
        raise HTTPException(404, f"no project at {path}; in that repo, run fctl connect --workspace <name>")
    p = found[0]
    factory = factory_state(p["path"], p["default_branch"])
    return {"id": p["id"], "name": p["name"], "default_branch": p["default_branch"], "factory": factory}


# --- Create factory (docs/MVP.md §3.2, docs/claude-code.md §7.1, §7.3) ---------

FACTORY_FILES = (SKILL, *(f".claude/agents/{a}.md" for a in (  # Q6: written and listed in this order
    "spec-writer", "builder", "review-security", "review-ux", "review-ui", "review-code", "approver")))
# Q5: markdown, not HTML; values go in verbatim and are never evaluated as template code
FACTORY_TEMPLATES = jinja2.Environment(
    loader=jinja2.FileSystemLoader(HERE / "factory_templates"),
    autoescape=False, keep_trailing_newline=True, undefined=jinja2.StrictUndefined,
)
COMMIT_HINT = 'git add .claude/skills/factory .claude/agents && git commit -m "Add factory"'


class FactoryBody(BaseModel):
    overwrite: bool = False


def create_factory(project_id: int, overwrite: bool) -> dict:
    """Q7, Q8: every check before any write; existing files (lexists) are skipped unless overwrite."""
    p = one_or_404(
        "SELECT p.name, p.path, p.default_branch, p.test_cmd, w.name AS workspace FROM projects p"
        " JOIN workspaces w ON w.id = p.workspace_id WHERE p.id = ?",
        (project_id,),
    )
    if not (p["test_cmd"] or "").strip():
        raise HTTPException(409, "no test command: in the repo, run fctl connect --workspace"
                                 f' {shlex.quote(p["workspace"])} --test-cmd "<your test command>"')
    root = p["path"]
    if not os.path.isdir(root):
        raise HTTPException(409, f"{root} is not a directory")
    real_root = Path(os.path.realpath(root))
    for rel in FACTORY_FILES:
        if not Path(os.path.realpath(os.path.join(root, rel))).is_relative_to(real_root):
            raise HTTPException(409, f"{rel} resolves outside the project")
    values = {"name": p["name"], "default_branch": p["default_branch"], "test_cmd": p["test_cmd"]}
    written, skipped = [], []
    for rel in FACTORY_FILES:
        target = Path(root, rel)
        if os.path.lexists(target) and not overwrite:
            skipped.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(FACTORY_TEMPLATES.get_template(rel.removeprefix(".claude/")).render(values),
                          encoding="utf-8")
        written.append(rel)
    if written:  # Q9
        with closing(db.connect()) as conn, conn:
            conn.execute("UPDATE projects SET factory_version = 1 WHERE id = ?", (project_id,))
    return {"written": written, "skipped": skipped, "commit_hint": COMMIT_HINT}


@app.post("/api/projects/{project_id}/factory")
def create_factory_api(project_id: int, body: FactoryBody):
    return create_factory(project_id, body.overwrite)


# --- Tasks (docs/data-model-and-api.md §6.2) ----------------------------------


class RoundBody(BaseModel):
    """§6.3's rounds body, and §6.2's `submit` (Q4). base_sha may later become a git argument."""
    base_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    patch: str
    build_md: str | None = None


class TaskBody(BaseModel):
    title: str
    description_md: str = ""
    submit: RoundBody | None = None


class TaskPatch(BaseModel):
    spec_md: str | None = None
    stage: (
        Literal["spec", "build", "agent_review", "approval", "rework", "human_review", "escalated"] | None
    ) = None
    status: Literal["backlog", "in_progress", "review", "done"] | None = None
    position: FiniteFloat | None = None


@app.get("/api/projects/{project_id}/tasks")
def list_tasks(project_id: int):
    one_or_404("SELECT 1 FROM projects WHERE id = ?", (project_id,))
    tasks = query("SELECT id, title, status, stage, position FROM tasks WHERE project_id = ?", (project_id,))
    items = []
    # ponytail: 3 queries per task; one grouped query if a board grows past a few hundred tasks
    for t in sorted(tasks, key=lambda t: (COLUMNS.index(t["status"]), t["position"], t["id"])):
        rounds = round_summaries(t["id"])
        last = rounds[-1] if rounds else {}
        items.append({
            "id": t["id"], "title": t["title"], "status": t["status"], "stage": t["stage"],
            "round": last.get("n"), "verdicts": last.get("verdicts"),
            "additions": last.get("additions"), "deletions": last.get("deletions"),
            "run": latest_run(t["id"]),
        })
    return items


@app.post("/api/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: int, body: TaskBody, request: Request):
    """A Backlog task, or with `submit` a standalone task straight in Review with round 1 (Q3)."""
    title = body.title.strip()
    if not title:
        raise HTTPException(422, "title must not be blank")
    status, stage, actor = ("review", "human_review", "app") if body.submit else ("backlog", None, "me")
    with closing(db.connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")  # the bottom position, the inserts, and the round, atomically
        if not conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
            raise HTTPException(404)
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 1.0) FROM tasks WHERE project_id = ? AND status = ?",
            (project_id, status),
        ).fetchone()[0]
        now = db.now()
        task_id = conn.execute(
            "INSERT INTO tasks (project_id, title, description_md, status, stage, position, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, title, body.description_md, status, stage, position, now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO events (task_id, actor, to_status, stage, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, actor, status, stage, now),
        )
        if body.submit:  # a 4xx in here rolls the task back too
            submitted = insert_round(conn, task_id, body.submit)
    if body.submit:
        return {"task_id": task_id} | submitted | {"url": f"{request.base_url}tasks/{task_id}/review"}
    return {"id": task_id, "status": "backlog"}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    task = one_or_404("SELECT id, title, status, stage, branch FROM tasks WHERE id = ?", (task_id,))
    decisions = query(
        "SELECT d.id, r.n AS round, d.actor, d.decision, d.body_md, d.created_at FROM decisions d"
        " JOIN rounds r ON r.id = d.round_id WHERE d.task_id = ? ORDER BY d.id",
        (task_id,),
    )
    return dict(task) | {
        "rounds": round_summaries(task_id),
        "decisions": [dict(d) for d in decisions],
        "run": latest_run(task_id),
    }


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, body: TaskPatch):
    sent = body.model_fields_set
    if sent not in ({"spec_md"}, {"stage"}, {"status", "position"}):
        raise HTTPException(422, "send exactly one of: spec_md, stage, or status with position")
    if any(getattr(body, key) is None for key in sent):
        raise HTTPException(422, f"{', '.join(sorted(sent))} must not be null")
    with closing(db.connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")  # the 409 check, the update, and the event commit together
        conn.row_factory = sqlite3.Row
        task = conn.execute("SELECT status, stage, done_at FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404)
        now = db.now()
        if body.spec_md is not None:
            conn.execute(
                "UPDATE tasks SET spec_md = ?, updated_at = ? WHERE id = ?", (body.spec_md, now, task_id)
            )
            return {"id": task_id, "status": task["status"], "stage": task["stage"]}
        if body.stage is not None:
            status, stage, actor = STAGE_STATUS[body.stage], body.stage, "orchestrator"
        else:  # a manual move (board drag): status and position, stage cleared
            run = conn.execute(
                "SELECT id FROM runs WHERE task_id = ? AND status = 'running'", (task_id,)
            ).fetchone()
            if run:
                raise HTTPException(409, f"run #{run['id']} active")
            status, stage, actor = body.status, None, "me"
        done_at = None
        if status == "done":
            done_at = (task["status"] == "done" and task["done_at"]) or now
        conn.execute(
            "UPDATE tasks SET status = ?, stage = ?, position = COALESCE(?, position), done_at = ?,"
            " updated_at = ? WHERE id = ?",
            (status, stage, body.position, done_at, now, task_id),
        )
        if (status, stage) != (task["status"], task["stage"]):
            conn.execute(
                "INSERT INTO events (task_id, actor, from_status, to_status, stage, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, actor, task["status"], status, stage, now),
            )
    return {"id": task_id, "status": status, "stage": stage}


# --- Runs (docs/data-model-and-api.md §6.2, docs/MVP.md §4.3, §4.4) -----------

PROMPT = "/factory {task_id}"  # MVP §10 OQ1: the one place the prompt lives
ALLOWED_TOOLS = (  # §4.4; the test command's entry is added per project (Q7)
    "Bash(fctl show *)", "Bash(fctl diff *)", "Bash(fctl spec *)", "Bash(fctl submit *)",
    "Bash(fctl verdict *)", "Bash(fctl comment *)", "Bash(fctl decide *)", "Bash(fctl stage *)",
    "Bash(fctl round *)", "Bash(git status *)", "Bash(git diff *)",
)
DISALLOWED_TOOLS = (
    "Bash(git commit *)", "Bash(git push *)", "Bash(git merge *)", "Bash(git rebase *)",
    "Bash(git reset *)", "Bash(git checkout *)",
)
EXCLUDE_LINE = b".claude/worktrees/"


def slug(title: str) -> str:
    """Q3: `Rate-limit login endpoint` → `rate-limit-login`; nothing left → `task`."""
    return "-".join(re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-").split("-")[:3]) or "task"


def refuse_if_running(conn: sqlite3.Connection):
    """§4.4: one run at a time, across all projects."""
    if run := conn.execute("SELECT id FROM runs WHERE status = 'running'").fetchone():
        raise HTTPException(409, f"run #{run[0]} active")


def worktree(task: sqlite3.Row) -> str:
    """Q5: the exclude line, then Q4: the stored worktree, or a new one from the default branch, stored
    right away so an auth refusal leaves it for the next run."""
    path = task["path"]
    exclude = Path(subprocess.run(
        ["git", "-C", path, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
        capture_output=True, text=True, check=True,
    ).stdout.strip())
    exclude.parent.mkdir(parents=True, exist_ok=True)
    old = exclude.read_bytes() if exclude.exists() else b""
    if EXCLUDE_LINE not in old.splitlines():
        with exclude.open("ab") as f:
            f.write((b"\n" if old and not old.endswith(b"\n") else b"") + EXCLUDE_LINE + b"\n")
    if task["worktree_path"]:  # reused as stored, even if the title changed since
        if not os.path.isdir(task["worktree_path"]):
            raise HTTPException(409, f"worktree {task['worktree_path']} is missing")
        return task["worktree_path"]
    name = f"{task['id']}-{slug(task['title'])}"
    branch, wt = f"factory/{name}", os.path.join(path, ".claude", "worktrees", name)
    added = subprocess.run(
        ["git", "-C", path, "worktree", "add", "-b", branch, wt, task["default_branch"]],
        capture_output=True, text=True, errors="replace",
    )
    if added.returncode:
        raise HTTPException(409, f"git worktree add failed: {added.stderr.strip()}")
    with closing(db.connect()) as conn, conn:
        conn.execute("UPDATE tasks SET branch = ?, worktree_path = ? WHERE id = ?", (branch, wt, task["id"]))
    return wt


def run_env(request: Request) -> dict:
    """§4.3: no API key or provider variables, so the run bills to the subscription. Q8: FCTL_URL."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") and not k.startswith("CLAUDE_CODE_USE_")}
    return env | {"FCTL_URL": str(request.base_url).rstrip("/")}


def subscription_auth(cwd: str, env: dict) -> bool:
    """§4.3, Q6: `claude auth status`, run like the run itself, exits 0 and reports claude.ai."""
    try:
        r = subprocess.run(["claude", "auth", "status"], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=30)
        info = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):  # no binary, not JSON, hung
        return False
    return r.returncode == 0 and isinstance(info, dict) and info.get("authMethod") == "claude.ai"


def finish_run(run_id: int, proc: subprocess.Popen, log_path: Path):
    """Q10: on exit, the exit code and the log's last `result` event decide the run row. The task
    is never touched (§3.4 step 8)."""
    code, event = proc.wait(), None
    with log_path.open(errors="replace") as log:
        for line in log:
            try:
                parsed = json.loads(line)
            except ValueError:  # stderr and anything else that isn't JSON
                continue
            if isinstance(parsed, dict) and parsed.get("type") == "result":
                event = parsed
    is_error = bool(event and event.get("is_error"))
    if code == 0 and event and not is_error:
        status, error = "succeeded", None
    else:
        status = "failed"
        error = str(event.get("result")) if is_error else f"exit code {code}" if code else "no result event"
    session = event.get("session_id") if event and isinstance(event.get("session_id"), str) else None
    with closing(db.connect()) as conn, conn:
        conn.execute(
            "UPDATE runs SET status = ?, exit_code = ?, error = ?, session_id = COALESCE(?, session_id),"
            " ended_at = ? WHERE id = ?",
            (status, code, error, session, db.now(), run_id),
        )


@app.post("/api/tasks/{task_id}/run", status_code=202)
def run_task(task_id: int, request: Request):
    """Q2's order: 404, run active, status (Q1), factory (Q12), worktree (Q4), auth; then the run row,
    the move, and the event in one transaction, then the spawn (§4.4)."""
    task = one_or_404(
        "SELECT t.id, t.title, t.status, t.worktree_path, p.path, p.default_branch, p.test_cmd"
        " FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.id = ?",
        (task_id,), f"no task #{task_id}",
    )
    with closing(db.connect()) as conn:
        refuse_if_running(conn)
    if task["status"] in ("review", "done"):
        raise HTTPException(409, f"#{task_id} is {'in review' if task['status'] == 'review' else 'done'}")
    branch = task["default_branch"]
    state = factory_state(task["path"], branch)  # the 409s name the next step (015 ux review, MVP §3.2)
    if state == "uncommitted":
        raise HTTPException(409, f"factory isn't committed on {branch}: on {branch}, run {COMMIT_HINT}")
    if state == "none":
        raise HTTPException(409, f"factory isn't committed on {branch}: "
                                 f"Create factory on the project board, then commit it on {branch}")
    wt, env = worktree(task), run_env(request)
    if not subscription_auth(wt, env):
        raise HTTPException(409, "not on subscription auth")
    session_id = str(uuid.uuid4())
    test_words = list(takewhile(lambda w: not w.startswith("-"), (task["test_cmd"] or "").split()))  # Q7
    allowed = ALLOWED_TOOLS + ((f"Bash({' '.join(test_words)} *)",) if test_words else ())
    cmd = ["claude", "-p", PROMPT.format(task_id=task_id), "--session-id", session_id,
           "--output-format", "stream-json", "--verbose", "--forward-subagent-text",
           "--permission-mode", "acceptEdits", "--permission-prompts", "none",
           "--allowedTools", *allowed, "--disallowedTools", *DISALLOWED_TOOLS]
    runs_dir = db.data_dir() / "runs"
    runs_dir.mkdir(exist_ok=True)
    with closing(db.connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        refuse_if_running(conn)
        now = db.now()
        try:
            run_id = conn.execute(
                "INSERT INTO runs (task_id, session_id, status, log_path, started_at)"
                " VALUES (?, ?, 'running', '', ?) RETURNING id",
                (task_id, session_id, now),
            ).fetchone()[0]
        except sqlite3.IntegrityError:  # one_active_run
            refuse_if_running(conn)
            raise
        log_path = runs_dir / f"{run_id}.jsonl"
        conn.execute("UPDATE runs SET log_path = ? WHERE id = ?", (str(log_path), run_id))
        moved = conn.execute(  # Q9: an in_progress task keeps its status and stage
            "UPDATE tasks SET status = 'in_progress', stage = NULL, updated_at = ? WHERE id = ? AND status = 'backlog'",
            (now, task_id),
        )
        if moved.rowcount:
            conn.execute(
                "INSERT INTO events (task_id, actor, from_status, to_status, created_at)"
                " VALUES (?, 'app', 'backlog', 'in_progress', ?)",
                (task_id, now),
            )
    try:
        with log_path.open("wb") as log:
            proc = subprocess.Popen(cmd, cwd=wt, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:  # Q11: a running row with no process would block every run
        error = f"can't start claude: {e}"
        with closing(db.connect()) as conn, conn:
            conn.execute("UPDATE runs SET status = 'failed', error = ?, ended_at = ? WHERE id = ?",
                         (error, db.now(), run_id))
        raise HTTPException(500, error)
    with closing(db.connect()) as conn, conn:
        conn.execute("UPDATE runs SET pid = ? WHERE id = ?", (proc.pid, run_id))
    threading.Thread(target=finish_run, args=(run_id, proc, log_path), daemon=True).start()
    return {"run_id": run_id, "session_id": session_id, "worktree": os.path.relpath(wt, task["path"])}


@app.post("/api/projects/{project_id}/run-next", status_code=202)
def run_next(project_id: int, request: Request):
    """Q13: the top backlog card, lowest position then lowest id, through all of /run's checks."""
    one_or_404("SELECT 1 FROM projects WHERE id = ?", (project_id,))
    top = query(
        "SELECT id FROM tasks WHERE project_id = ? AND status = 'backlog' ORDER BY position, id LIMIT 1",
        (project_id,),
    )
    if not top:
        raise HTTPException(404, "backlog is empty")
    return {"task_id": top[0]["id"], "run_id": run_task(top[0]["id"], request)["run_id"]}


# --- Rounds (docs/data-model-and-api.md §6.3) ---------------------------------

PATCH_NAMES = {"rename from ": "from", "rename to ": "to", "--- ": "old", "+++ ": "new"}


def unquote(name: str) -> str:
    """Q6: git C-quotes a name holding `"`, `\\`, or control bytes; octal escapes are UTF-8 bytes."""
    if len(name) < 2 or name[0] != '"' or name[-1] != '"':
        return name
    try:
        return codecs.escape_decode(name[1:-1].encode())[0].decode(errors="replace")
    except ValueError:  # a trailing `\` or a bad `\x`: "" makes the caller's 422
        return ""


def safe_path(path: str | None) -> bool:
    """Git never writes an empty, absolute, `..`, or NUL path; refuse them before pages link to it."""
    return bool(path) and not path.startswith("/") and "\0" not in path and ".." not in path.split("/")


def parse_section(section: str) -> dict:
    """Q6: one `diff --git` section → its round_files row."""
    header, *lines = section.split("\n")
    row = {"path": None, "old_path": None, "change": "modified", "binary": 0, "additions": 0,
           "deletions": 0, "patch": section}
    names, in_hunks = {}, False
    for line in lines:
        if in_hunks:
            row["additions"] += line.startswith("+")
            row["deletions"] += line.startswith("-")
        elif line.startswith("@@"):
            in_hunks = True
        elif line.startswith("new file mode "):
            row["change"] = "added"
        elif line.startswith("deleted file mode "):
            row["change"] = "deleted"
        elif line.startswith("Binary files ") and line.endswith(" differ"):
            row["binary"] = 1
        else:
            for prefix, key in PATCH_NAMES.items():
                if line.startswith(prefix):  # git adds a tab after a name with a space
                    names[key] = unquote(line[len(prefix):].removesuffix("\t"))
    new, old = names.get("new", "/dev/null"), names.get("old", "/dev/null")
    if "to" in names:
        row.update(path=names["to"], old_path=names.get("from"), change="renamed")
    elif new != "/dev/null":
        row["path"] = new.removeprefix("b/") if new.startswith("b/") else None
    elif old != "/dev/null":
        row["path"] = old.removeprefix("a/") if old.startswith("a/") else None
    else:  # mode-only, binary, or empty: `diff --git a/X b/X`, split at its midpoint
        pair = header.removeprefix("diff --git ")
        mid = len(pair) // 2
        a, b = unquote(pair[:mid]), unquote(pair[mid + 1:])
        if pair[mid:mid + 1] == " " and a[:2] == "a/" and b[:2] == "b/" and a[2:] == b[2:]:
            row["path"] = a[2:]
    if not safe_path(row["path"]) or (row["change"] == "renamed" and not safe_path(row["old_path"])):
        raise HTTPException(422, f"can't read a safe file path in: {header[:200]}")
    return row


def split_patch(patch: str) -> list[dict]:
    """Q6: one row per file, in patch order. Sections split on \\n only, so joined they give the
    patch back byte for byte."""
    if not patch.startswith("diff --git "):
        raise HTTPException(422, 'patch must start with "diff --git"')
    rows: dict[str, dict] = {}
    for section in re.split(r"(?m)^(?=diff --git )", patch)[1:]:
        row = parse_section(section)
        if seen := rows.get(row["path"]):  # git splits a file <-> symlink typechange in two
            seen.update(change="modified", old_path=None, binary=seen["binary"] | row["binary"],
                        additions=seen["additions"] + row["additions"],
                        deletions=seen["deletions"] + row["deletions"], patch=seen["patch"] + row["patch"])
        else:
            rows[row["path"]] = row
    return list(rows.values())


def insert_round(conn: sqlite3.Connection, task_id: int, body: RoundBody) -> dict:
    """Check the patch (Q4, Q5), number the round and pick its trigger (Q1), and insert it with its
    files, inside the caller's BEGIN IMMEDIATE so any 4xx writes nothing."""
    if len(body.patch.encode()) > MAX_PATCH:
        raise HTTPException(413, "patch over 5 MB")
    if not body.patch.strip():
        raise HTTPException(422, "no changes to submit")
    files = split_patch(body.patch)
    n = conn.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM rounds WHERE task_id = ?", (task_id,)).fetchone()[0]
    changes_requested = conn.execute(
        "SELECT 1 FROM decisions d JOIN rounds r ON r.id = d.round_id WHERE r.task_id = ? AND r.n = ?"
        " AND d.actor = 'me' AND d.decision = 'CHANGES_REQUESTED'",
        (task_id, n - 1),
    ).fetchone()
    trigger = "initial" if n == 1 else "human" if changes_requested else "agent"
    round_id = conn.execute(
        "INSERT INTO rounds (task_id, n, trigger, base_sha, build_md, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, n, trigger, body.base_sha, body.build_md, db.now()),
    ).lastrowid
    conn.executemany(
        "INSERT INTO round_files (round_id, path, old_path, change, binary, additions, deletions, patch)"
        " VALUES (:round_id, :path, :old_path, :change, :binary, :additions, :deletions, :patch)",
        [f | {"round_id": round_id} for f in files],
    )
    return {"round": n, "files_changed": len(files), "additions": sum(f["additions"] for f in files),
            "deletions": sum(f["deletions"] for f in files)}


@app.post("/api/tasks/{task_id}/rounds", status_code=201)
def submit_round(task_id: int, body: RoundBody, request: Request):
    with closing(db.connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")  # n, the round, its files, and the status commit together
        conn.row_factory = sqlite3.Row
        task = conn.execute("SELECT status, stage, worktree_path FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404)
        submitted = insert_round(conn, task_id, body)
        if task["worktree_path"] is None:  # Q2: every round puts a standalone task in Review
            now = db.now()
            conn.execute(
                "UPDATE tasks SET status = 'review', stage = 'human_review', done_at = NULL, updated_at = ?"
                " WHERE id = ?",
                (now, task_id),
            )
            if (task["status"], task["stage"]) != ("review", "human_review"):
                conn.execute(
                    "INSERT INTO events (task_id, actor, from_status, to_status, stage, created_at)"
                    " VALUES (?, 'app', ?, 'review', 'human_review', ?)",
                    (task_id, task["status"], now),
                )
    return submitted | {"url": f"{request.base_url}tasks/{task_id}/review?round={submitted['round']}"}


def round_or_404(task_id: int, n: str) -> sqlite3.Row:
    """005 Q7, 006 Q1: the task's round `n`, or the highest with `latest`; the bare 404 for an unknown
    task first."""
    one_or_404("SELECT 1 FROM tasks WHERE id = ?", (task_id,))
    if n == "latest":
        found = query("SELECT id, n, build_md FROM rounds WHERE task_id = ? ORDER BY n DESC LIMIT 1", (task_id,))
        missing = f"#{task_id} has no rounds"
    else:  # compared as text, so 'abc', '01', or a huge number simply match nothing
        found = query("SELECT id, n, build_md FROM rounds WHERE task_id = ? AND CAST(n AS TEXT) = ?", (task_id, n))
        missing = f"#{task_id} has no round {n}"
    if not found:
        raise HTTPException(404, missing)
    return found[0]


@app.get("/api/tasks/{task_id}/rounds/{n}/diff")
def round_diff(task_id: int, n: str):
    """Q7: the round's files' patches joined in rowid order."""
    patches = query("SELECT patch FROM round_files WHERE round_id = ? ORDER BY rowid",
                    (round_or_404(task_id, n)["id"],))
    return Response("".join(p["patch"] for p in patches), media_type="text/x-diff", headers=NOSNIFF)


# --- Agent API: verdicts, comments, decisions (§6.3), context (§6.2) -----------
# None of these touch the task row or write events (§7.5, Q2).


class VerdictBody(BaseModel):
    verdict: Literal["PASS", "CHANGES"]
    body_md: str = ""


class CommentBody(BaseModel):
    round: int | Literal["latest"] = "latest"
    author: Literal["me"] | Reviewer
    path: str | None = None
    line: int | None = Field(None, ge=1, lt=2**63)  # SQLite INTEGER bounds
    side: Literal["old", "new"] | None = None
    body_md: str


class DecisionBody(BaseModel):
    decision: Literal["APPROVE", "ESCALATE"]  # my APPROVE / CHANGES_REQUESTED go through 009's routes
    body_md: str = ""


@app.put("/api/tasks/{task_id}/rounds/{n}/verdicts/{reviewer}")
def put_verdict(task_id: int, n: str, reviewer: Reviewer, body: VerdictBody):
    """Q2: one row per (round, reviewer); posting again replaces verdict, body, and created_at."""
    found = round_or_404(task_id, n)
    with closing(db.connect()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO verdicts (round_id, reviewer, verdict, body_md, created_at) VALUES (?, ?, ?, ?, ?)",
            (found["id"], reviewer, body.verdict, body.body_md, db.now()),
        )
        done = conn.execute("SELECT COUNT(*) FROM verdicts WHERE round_id = ?", (found["id"],)).fetchone()[0]
    return {"round": found["n"], "reviewer": reviewer, "verdict": body.verdict, "complete": f"{done}/{len(REVIEWERS)}"}


@app.post("/api/tasks/{task_id}/comments", status_code=201)
def post_comment(task_id: int, body: CommentBody):
    """Q3: inline (path and line, side defaulting to new) or conversation (all three NULL)."""
    if (body.path is None) != (body.line is None):
        raise HTTPException(422, "path and line go together")
    if body.side is not None and body.path is None:
        raise HTTPException(422, "side needs a path")
    if not body.body_md.strip():
        raise HTTPException(422, "body_md must not be blank")
    found = round_or_404(task_id, str(body.round))
    if body.path is not None and not query(
        "SELECT 1 FROM round_files WHERE round_id = ? AND path = ?", (found["id"], body.path)
    ):
        raise HTTPException(422, f"{body.path} is not in round {found['n']}")
    side = None if body.path is None else body.side or "new"
    with closing(db.connect()) as conn, conn:
        comment_id = conn.execute(
            "INSERT INTO comments (task_id, round_id, author, path, line, side, body_md, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, found["id"], body.author, body.path, body.line, side, body.body_md, db.now()),
        ).lastrowid
    return {"id": comment_id}


@app.post("/api/tasks/{task_id}/decision", status_code=201)
def post_decision(task_id: int, body: DecisionBody):
    """Q4: the approver's decision on the latest round. Every POST adds a row; readers take the latest."""
    found = round_or_404(task_id, "latest")
    with closing(db.connect()) as conn, conn:
        decision_id = conn.execute(
            "INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at)"
            " VALUES (?, ?, 'approver', ?, ?, ?)",
            (task_id, found["id"], body.decision, body.body_md, db.now()),
        ).lastrowid
    return {"id": decision_id}


# --- My review actions (docs/MVP.md §3.6, §3.7; docs/data-model-and-api.md §6.3) --------


class ApproveBody(BaseModel):
    body_md: str = ""  # Q9: optional; neither the page nor fctl approve sends one


class ChangesBody(BaseModel):
    body_md: str  # Q9: required, and not blank


def commit_hint(task) -> str:
    """Q4, Q5: §3.7's commands for me to run, every value shell-quoted. A standalone task (no branch or
    worktree) gets the commit line alone."""
    commit = f"git add -A && git commit -m {shlex.quote(task['title'])}"
    if not (task["branch"] and task["worktree_path"]):
        return commit
    wt, root = task["worktree_path"], task["path"]
    return "\n".join([
        f"cd {shlex.quote(wt)}",
        commit,
        f"git push -u origin {shlex.quote(task['branch'])}     # then open a PR, or merge locally",
        f"cd {shlex.quote(root)} && git worktree remove {shlex.quote(os.path.relpath(wt, root))}",
    ])


def decide_review(task_id: int, decision: str, body_md: str, status: str, stage: str | None) -> sqlite3.Row:
    """Q2, Q3, Q10: in one transaction, refuse unless in review with a round, then my decision on the
    latest round, the move (position kept, Q8), and the event (actor me, Q7). Returns the task as it was."""
    with closing(db.connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")  # the check and the writes together, so a double click can't act twice
        conn.row_factory = sqlite3.Row
        task = conn.execute(
            "SELECT t.status, t.title, t.branch, t.worktree_path, p.path FROM tasks t"
            " JOIN projects p ON p.id = t.project_id WHERE t.id = ?", (task_id,),
        ).fetchone()
        if not task:
            raise HTTPException(404)
        if task["status"] != "review":
            raise HTTPException(409, f"#{task_id} is not in review")
        latest = conn.execute("SELECT id FROM rounds WHERE task_id = ? ORDER BY n DESC LIMIT 1", (task_id,)).fetchone()
        if not latest:
            raise HTTPException(404, f"#{task_id} has no rounds")
        now = db.now()
        conn.execute(
            "INSERT INTO decisions (task_id, round_id, actor, decision, body_md, created_at)"
            " VALUES (?, ?, 'me', ?, ?, ?)",
            (task_id, latest["id"], decision, body_md, now),
        )
        conn.execute(
            "UPDATE tasks SET status = ?, stage = ?, done_at = ?, updated_at = ? WHERE id = ?",
            (status, stage, now if status == "done" else None, now, task_id),
        )
        conn.execute(
            "INSERT INTO events (task_id, actor, from_status, to_status, stage, created_at)"
            " VALUES (?, 'me', 'review', ?, ?, ?)",
            (task_id, status, stage, now),
        )
    return task


@app.post("/api/tasks/{task_id}/approve")
def approve(task_id: int, body: ApproveBody):
    """§3.7: my APPROVE → done, and the commands I run myself. The app never runs git."""
    task = decide_review(task_id, "APPROVE", body.body_md, "done", None)
    return {"status": "done", "commit_hint": commit_hint(task)}


@app.post("/api/tasks/{task_id}/request-changes", status_code=202)
def request_changes(task_id: int, body: ChangesBody):
    """§3.6: my CHANGES_REQUESTED → in_progress · rework (Q1: standalone too)."""
    if not body.body_md.strip():
        raise HTTPException(422, "body_md must not be blank")
    decide_review(task_id, "CHANGES_REQUESTED", body.body_md, "in_progress", "rework")
    return {"status": "in_progress", "stage": "rework", "run_id": None}  # 013 spawns the rework run


def context_md(task: sqlite3.Row, rounds: list[sqlite3.Row], feedback: sqlite3.Row | None = None) -> str:
    """Q5, Q6: the task as markdown blocks joined by one blank line. A block is a heading, then its
    body with trailing whitespace stripped, unless the body is blank. Agent text passes through as is."""
    blocks = []

    def add(heading: str, body: str | None = None):
        blocks.append(heading + (f"\n{body.rstrip()}" if body and body.strip() else ""))

    def add_comments(round_id: int, only_me: bool):
        found = query(
            "SELECT author, path, line, side, body_md FROM comments"
            " WHERE round_id = ? AND (? = 0 OR author = 'me') ORDER BY id",
            (round_id, only_me),
        )
        if found:
            add("## Comments")
        for c in found:
            where = "" if c["path"] is None else f" on {c['path']}:{c['line']} ({c['side']})"
            add(f"### {c['author']}{where}", c["body_md"])

    status = task["status"] + (f" · {task['stage']}" if task["stage"] else "")
    add(f"# #{task['id']} {task['title']}", f"Status: {status}")
    add("## Description", task["description_md"])
    add("## Spec", "_No spec yet._" if task["spec_md"] is None else task["spec_md"])
    for r in rounds:
        add(f"## Round {r['n']} — build notes", r["build_md"])
        add("## Verdicts")
        verdicts = {v["reviewer"]: v for v in query(
            "SELECT reviewer, verdict, body_md FROM verdicts WHERE round_id = ?", (r["id"],)
        )}
        for who in REVIEWERS:
            v = verdicts.get(who)
            add(f"### {who}: {v['verdict'] if v else 'pending'}", v and v["body_md"])
        add_comments(r["id"], only_me=False)
        decisions = query("SELECT actor, decision, body_md FROM decisions WHERE round_id = ? ORDER BY id", (r["id"],))
        if decisions:
            add("## Decisions")
        for d in decisions:
            add(f"### {d['actor']}: {d['decision']}", d["body_md"])
    if feedback:
        add(f"## Feedback on round {feedback['n']}", feedback["body_md"])
        add_comments(feedback["round_id"], only_me=True)
    return "\n\n".join(blocks) + "\n"


@app.get("/api/tasks/{task_id}/context")
def task_context(task_id: int, n: str | None = Query(None, alias="round"), feedback: bool = False):
    """§6.2: everything (no query), one round (`?round=`), or my latest feedback (`?feedback=1`)."""
    if n is not None and feedback:
        raise HTTPException(422, "give round or feedback, not both")
    task = one_or_404(
        "SELECT id, title, status, stage, description_md, spec_md FROM tasks WHERE id = ?", (task_id,)
    )
    mine = None
    if feedback:  # Q6: my latest CHANGES_REQUESTED
        found = query(
            "SELECT d.round_id, r.n, d.body_md FROM decisions d JOIN rounds r ON r.id = d.round_id"
            " WHERE d.task_id = ? AND d.actor = 'me' AND d.decision = 'CHANGES_REQUESTED' ORDER BY d.id DESC LIMIT 1",
            (task_id,),
        )
        if not found:
            raise HTTPException(404, f"#{task_id} has no feedback")
        mine, rounds = found[0], []
    elif n is not None:
        rounds = [round_or_404(task_id, n)]
    else:
        rounds = query("SELECT id, n, build_md FROM rounds WHERE task_id = ? ORDER BY n", (task_id,))
    return Response(context_md(task, rounds, mine), media_type="text/markdown", headers=NOSNIFF)


# --- Pages and htmx forms (docs/ui.md §8) ------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # ponytail: workspace list until the dashboard (job 017) replaces it
    return templates.TemplateResponse(request, "index.html", {"workspaces": workspaces()})


@app.get("/workspaces/{workspace_id}", response_class=HTMLResponse)
def workspace_page(request: Request, workspace_id: int):
    workspace = one_or_404("SELECT id, name FROM workspaces WHERE id = ?", (workspace_id,))
    rows = query(
        "SELECT p.id, p.name, p.path, p.default_branch,"
        " COUNT(t.id) FILTER (WHERE t.status = 'backlog') AS backlog,"
        " COUNT(t.id) FILTER (WHERE t.status = 'in_progress') AS in_progress,"
        " COUNT(t.id) FILTER (WHERE t.status = 'review') AS review,"
        " COUNT(t.id) FILTER (WHERE t.status = 'done') AS done,"
        " MAX(p.created_at, COALESCE(MAX(t.updated_at), '')) AS last_activity"
        " FROM projects p LEFT JOIN tasks t ON t.project_id = p.id"
        " WHERE p.workspace_id = ? GROUP BY p.id ORDER BY p.name",
        (workspace_id,),
    )
    # ponytail: one git call per row; cache if a workspace grows past a few dozen projects
    projects = [dict(r, factory=factory_state(r["path"], r["default_branch"])) for r in rows]
    return templates.TemplateResponse(
        request, "workspace.html", {"workspace": workspace, "projects": projects}
    )


@app.post("/workspaces")
async def create_workspace(request: Request):
    name = await form_field(request, "name")
    if not name:
        raise HTTPException(422, "name must not be blank")
    with closing(db.connect()) as conn, conn:
        ws_id = get_or_create_workspace(conn, name)
    return hx_redirect(f"/workspaces/{ws_id}")


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_page(request: Request, project_id: int):
    # ponytail: each 3 s poll renders the whole page, one git call included (Q7);
    # add a /projects/{id}/board fragment route if that shows up in profiling
    project = one_or_404(
        "SELECT p.id, p.name, p.path, p.default_branch, p.workspace_id, w.name AS workspace FROM projects p"
        " JOIN workspaces w ON w.id = p.workspace_id WHERE p.id = ?",
        (project_id,),
    )
    tasks = list_tasks(project_id)
    # Q13: the API doesn't return position; read it after list_tasks so every listed task has one
    positions = dict(query("SELECT id, position FROM tasks WHERE project_id = ?", (project_id,)))
    columns = {status: [] for status in COLUMNS}
    for t in tasks:
        columns[t["status"]].append(t | {"position": positions[t["id"]]})
    return templates.TemplateResponse(request, "project.html", {
        "project": project, "workspaces": workspaces(), "columns": columns,
        "factory": factory_state(project["path"], project["default_branch"]),
    })


@app.post("/projects/{project_id}/tasks")
async def add_task_form(request: Request, project_id: int):
    """Q10: the + New task form; create_task validates, places, and logs the event."""
    body = TaskBody(
        title=await form_field(request, "title"),
        description_md=await form_field(request, "description_md"),
    )
    create_task(project_id, body, request)
    return hx_redirect(f"/projects/{project_id}")


@app.post("/projects/{project_id}/workspace")
async def move_project(request: Request, project_id: int):
    try:
        ws_id = int(await form_field(request, "workspace_id"))
    except ValueError:
        raise HTTPException(422, "workspace_id must be an integer")
    with closing(db.connect()) as conn, conn:
        if not conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (ws_id,)).fetchone():
            raise HTTPException(404)
        moved = conn.execute("UPDATE projects SET workspace_id = ? WHERE id = ?", (ws_id, project_id))
        if moved.rowcount == 0:
            raise HTTPException(404)
    return hx_redirect(f"/projects/{project_id}")


@app.post("/projects/{project_id}/factory", response_class=HTMLResponse)
async def create_factory_form(request: Request, project_id: int):
    """Q11: htmx doesn't swap 4xx, so errors come back as a 200 fragment with role="alert"."""
    try:
        result = create_factory(project_id, bool(await form_field(request, "overwrite")))
    except HTTPException as e:
        result = {"error": e.detail}
    return templates.TemplateResponse(request, "factory_result.html", result)


# --- Code page (docs/ui.md §8 item 6) ---

MAX_VIEW = 1024 * 1024  # Q5: over this many bytes, a file isn't shown


def git_stdout(root: str, *args: str) -> tuple[bytes | None, str | None]:
    """MVP §4.1, Q10: (git's stdout, None), or (None, the first line of its stderr) if it fails."""
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return None, "git timed out"
    except (OSError, ValueError) as e:  # no git, a NUL in the path
        return None, str(e)
    if r.returncode:
        return None, next(iter(r.stderr.decode(errors="replace").strip().splitlines()), f"git exited {r.returncode}")
    return r.stdout, None


def read_tracked(root: str, path: str) -> dict:
    """Q3–Q5, Q9: a tracked file's text and line count, or the note shown instead. Nothing outside the
    root and nothing but a regular file is ever opened."""
    real = os.path.realpath(os.path.join(root, path))
    if not Path(real).is_relative_to(os.path.realpath(root)):
        return {"note": "Not shown: points outside the project."}
    if not os.path.isfile(real):  # a directory, a submodule, a FIFO, gone from disk
        return {"note": "Not shown: not a regular file."}
    try:
        if os.stat(real).st_size > MAX_VIEW:
            return {"note": "File over 1 MB not shown."}
        with open(real, "rb") as f:
            data = f.read(MAX_VIEW)
    except OSError as e:
        return {"note": f"Not shown: {e.strerror or e}."}
    if b"\0" in data[:8000]:  # git's binary heuristic
        return {"note": "Binary file not shown."}
    if not data:
        return {"note": "Empty file."}
    text = data.decode(errors="replace")
    # Q9: lines end at \n, \r\n, or a lone \r, as HTML breaks them; a final line ending adds none
    return {"text": text, "lines": len(re.findall(r"\r\n?|\n", text)) + (text[-1] not in "\r\n")}


@app.get("/projects/{project_id}/code", response_class=HTMLResponse)
def code_page(request: Request, project_id: int, path: str = ""):
    """§8 item 6: the main checkout's `git ls-files` tree beside README.md (no `path`) or one file."""
    project = one_or_404("SELECT id, name, path FROM projects WHERE id = ?", (project_id,),
                         f"Project #{project_id} not found")
    root, context = project["path"], {"project": project, "path": path}
    listed, error = git_stdout(root, "ls-files", "-z")
    if error:  # Q10
        return templates.TemplateResponse(request, "code.html", context | {"error": error})
    raw = listed.split(b"\0")[:-1]
    names = [n.decode(errors="replace") for n in raw]
    tracked = {n for n, b in zip(names, raw) if n.encode() == b}  # Q4: a name that didn't decode is listed, not viewable
    if path and path not in tracked:  # Q2: before any filesystem call
        raise HTTPException(404, f"{path} is not a tracked file in {project['name']}")
    shown = path or ("README.md" if "README.md" in tracked else "")  # Q6
    out, _ = git_stdout(root, "branch", "--show-current")
    name = path.rpartition("/")[2]
    return templates.TemplateResponse(request, "code.html", context | {
        "tree": file_tree([{"path": n} for n in names]), "shown": shown,
        "view": read_tracked(root, shown) if shown else {"note": "No README.md in this project."},
        "branch": None if out is None else out.decode(errors="replace").strip() or "detached HEAD",  # Q7
        "lang": name.rpartition(".")[2].lower() if "." in name else None,  # Q9, same rule as review_files
    })


# §5.1, Q8: one row per event, round, verdict, decision, and comment, labelled; ties sort by kind, then id.
TIMELINE = """
SELECT created_at, 0 AS kind, id, IIF(from_status IS NULL, 'created · ', '') || COALESCE(to_status, '')
  || COALESCE(' · ' || stage, '') AS label, NULL AS body_md FROM events WHERE task_id = :task
UNION ALL SELECT created_at, 1, id, 'round ' || n, NULL FROM rounds WHERE task_id = :task
UNION ALL SELECT v.created_at, 2, v.rowid, v.reviewer || ' ' || v.verdict || ' · round ' || r.n, NULL
  FROM verdicts v JOIN rounds r ON r.id = v.round_id WHERE r.task_id = :task
UNION ALL SELECT d.created_at, 3, d.id, d.actor || ' ' || d.decision || ' · round ' || r.n, d.body_md
  FROM decisions d JOIN rounds r ON r.id = d.round_id WHERE d.task_id = :task
UNION ALL SELECT c.created_at, 4, c.id, c.author || COALESCE(' on ' || c.path || ':' || c.line, '')
  || ' · round ' || r.n, c.body_md FROM comments c JOIN rounds r ON r.id = c.round_id WHERE c.task_id = :task
ORDER BY created_at, kind, id
"""


# at most 18 digits: int() refuses a 4300+ digit string, and no file has 10**18 lines (security review)
HUNK = re.compile(r"@@ -(\d{1,18})(?:,\d+)? \+(\d{1,18})(?:,\d+)? @@")


def diff_rows(patch: str) -> list[dict]:
    """008 Q5: one round_files.patch → display rows (hunk, ctx, add, del, note), with old and new
    line numbers and the text without its sign or one trailing \\r. Header lines get no row."""
    rows, old, new, in_hunk = [], 0, 0, False
    lines = patch.split("\n")
    if lines[-1] == "":  # the empty string after the final \n
        lines.pop()
    for line in lines:
        line = line.removesuffix("\r")
        if line.startswith("diff --git "):  # 005's merged typechange sections
            in_hunk = False
        elif m := HUNK.match(line):
            old, new, in_hunk = int(m[1]), int(m[2]), True
            rows.append({"kind": "hunk", "old": None, "new": None, "text": line})
        elif not in_hunk:
            continue
        elif line.startswith("+"):
            rows.append({"kind": "add", "old": None, "new": new, "text": line[1:]})
            new += 1
        elif line.startswith("-"):
            rows.append({"kind": "del", "old": old, "new": None, "text": line[1:]})
            old += 1
        elif line.startswith("\\"):
            rows.append({"kind": "note", "old": None, "new": None, "text": line})
        else:
            rows.append({"kind": "ctx", "old": old, "new": new, "text": line[1:]})
            old, new = old + 1, new + 1
    return rows


def review_files(round_id: int, target: tuple[str, str, str]) -> list[dict]:
    """008: the round's files in rowid order, each with its rows, its inline comments placed under
    their line (Q2), the inline form on the row matching `target` (path, side, line) as strings (Q1),
    and the comments whose line isn't in the diff."""
    comments = query(
        "SELECT id, author, path, line, side, body_md FROM comments WHERE round_id = ? AND path IS NOT NULL"
        " ORDER BY id", (round_id,),
    )
    at: dict[tuple, list] = {}
    for c in comments:
        at.setdefault((c["path"], c["side"], c["line"]), []).append(c)
    files, formed = [], False
    # ponytail: every row of every file renders (up to 5 MB of patch, slow to draw); collapse files
    # over N lines if big rounds get common
    for f in query(
        "SELECT path, old_path, change, binary, additions, deletions, patch FROM round_files WHERE round_id = ?"
        " ORDER BY rowid", (round_id,),
    ):
        rows = diff_rows(f["patch"]) or [{"kind": "note", "old": None, "new": None,
                                          "text": "Binary file not shown." if f["binary"] else "No content changes."}]
        for r in rows:
            sides = [(side, r[side]) for side in ("old", "new") if r[side] is not None]
            r["comments"] = sorted(
                (c for side, num in sides for c in at.pop((f["path"], side, num), [])), key=lambda c: c["id"]
            )
            matches = [(side, str(num)) for side, num in sides if (f["path"], side, str(num)) == target]
            r["form"] = matches[0] if matches and not formed else None  # one form, even if anchors repeat
            formed = formed or bool(matches)
        name = f["path"].rpartition("/")[2]
        files.append(dict(f) | {
            "rows": rows, "lang": name.rpartition(".")[2].lower() if "." in name else None,
            # still in `at` = no row took it: its line isn't in the diff
            "orphans": [c for c in comments if c["path"] == f["path"] and (c["path"], c["side"], c["line"]) in at],
        })
    return files


def file_tree(files: list[dict]) -> dict:
    """008 Q6: {"dir/": {...}, "name": file} in patch order; a directory sits where its first file is."""
    root: dict = {}
    for f in files:
        *dirs, name = f["path"].split("/")
        node = root
        for d in dirs:
            node = node.setdefault(d + "/", {})
        node[name] = f
    return root


PAGE_TASK = (  # the task row both task pages show; `path` is for Review's commit hint
    "SELECT t.id, t.project_id, p.name AS project, t.title, t.description_md, t.spec_md, t.status, t.stage,"
    " t.branch, t.worktree_path, p.path FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.id = ?"
)


def posted_verdicts(task_id: int) -> dict[int, dict]:
    """007 Q5, Q6: round n → {reviewer: verdict row}, for the bodies."""
    posted: dict[int, dict] = {}
    for v in query(
        "SELECT r.n, v.reviewer, v.verdict, v.body_md FROM verdicts v JOIN rounds r ON r.id = v.round_id"
        " WHERE r.task_id = ?", (task_id,),
    ):
        posted.setdefault(v["n"], {})[v["reviewer"]] = v
    return posted


def approver_decision(task_id: int) -> sqlite3.Row | None:
    """007 Q7: only the approver's latest decision, by id."""
    found = query(
        "SELECT d.decision, d.body_md, r.n FROM decisions d JOIN rounds r ON r.id = d.round_id"
        " WHERE d.task_id = ? AND d.actor = 'approver' ORDER BY d.id DESC LIMIT 1", (task_id,),
    )
    return found[0] if found else None


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_page(request: Request, task_id: int):
    """docs/ui.md §8 item 4 without run controls (014): header, description, spec, rounds with build
    notes and verdict popovers, the approver's latest decision, and the status history."""
    task = one_or_404(PAGE_TASK, (task_id,), f"Task #{task_id} not found")
    return templates.TemplateResponse(request, "task.html", {
        "task": task, "rounds": round_summaries(task_id), "posted": posted_verdicts(task_id),
        "build": dict(query("SELECT n, build_md FROM rounds WHERE task_id = ?", (task_id,))),
        "reviewers": REVIEWERS, "approver": approver_decision(task_id),
        "history": [e for e in query(TIMELINE, {"task": task_id}) if e["kind"] == 0],  # Q8: events only
    })


@app.get("/tasks/{task_id}/review", response_class=HTMLResponse)
def review_page(request: Request, task_id: int, n: str = Query("latest", alias="round"), tab: str = "",
                path: str = "", side: str = "", line: str = ""):
    """§8.2's Conversation tab, or with `tab=files` §8.3's Files changed for the picked round (008).
    `path`, `side`, and `line` open the inline comment form under that line (008 Q1)."""
    task = one_or_404(PAGE_TASK, (task_id,), f"Task #{task_id} not found")
    rounds = round_summaries(task_id)
    # AC11: with no rounds, `latest` is a page without a selector, not round_or_404's 404
    found = round_or_404(task_id, n) if rounds or n != "latest" else None
    picked = found["n"] if found else None
    tab = "files" if tab == "files" else "conversation"  # 008 Q4
    files = review_files(found["id"], (path, side, line)) if tab == "files" and found else []
    return templates.TemplateResponse(request, "review.html", {
        "task": task, "rounds": rounds, "selected": next((r for r in rounds if r["n"] == picked), None),
        "posted": posted_verdicts(task_id), "reviewers": REVIEWERS, "approver": approver_decision(task_id),
        "timeline": query(TIMELINE, {"task": task_id}),
        "tab": tab, "files": files, "tree": file_tree(files),
        # Q6: from the task row, so it survives a reload and also follows fctl approve or a drag to Done
        "commit_hint": commit_hint(task) if task["status"] == "done" else None,
    })


@app.post("/tasks/{task_id}/approve")
def approve_form(task_id: int):
    """Q12: the page's Approve sends no summary."""
    approve(task_id, ApproveBody())
    return hx_redirect(f"/tasks/{task_id}/review")


@app.post("/tasks/{task_id}/request-changes")
async def request_changes_form(request: Request, task_id: int):
    request_changes(task_id, ChangesBody(body_md=await form_field(request, "body_md")))
    return hx_redirect(f"/tasks/{task_id}/review")


@app.post("/tasks/{task_id}/comments")
async def add_comment_form(request: Request, task_id: int):
    """007 Q9: a conversation comment from me on the latest round, or 008 Q3: an inline one on the
    sent `round`, `path`, `side`, and `line` (blank = absent). post_comment validates and writes."""
    fields = {k: await form_field(request, k) for k in ("round", "path", "side", "line")}
    try:
        body = CommentBody(author="me", body_md=await form_field(request, "body_md"),
                           **{k: v for k, v in fields.items() if v})
    except ValidationError as e:  # 008 Q11: a 422 with the messages, never the input
        raise HTTPException(422, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()])
    created = post_comment(task_id, body)
    if body.path is None:
        return hx_redirect(f"/tasks/{task_id}/review")
    c = query("SELECT r.n, c.path, c.side, c.line FROM comments c JOIN rounds r ON r.id = c.round_id"
              " WHERE c.id = ?", (created["id"],))[0]
    anchor = quote(f"{c['path']}:{c['side']}:{c['line']}")
    return hx_redirect(f"/tasks/{task_id}/review?{urlencode({'round': c['n'], 'tab': 'files'})}#{anchor}")
