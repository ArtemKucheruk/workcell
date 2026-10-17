"""The FastAPI app behind `fctl serve`."""

import os
import sqlite3
import subprocess
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Literal

from pydantic import BaseModel, FiniteFloat

from . import db

HERE = Path(__file__).parent
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SKILL = ".claude/skills/factory/SKILL.md"
COLUMNS = ("backlog", "in_progress", "review", "done")
REVIEWERS = ("security", "ux", "ui", "code")
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


# --- Helpers -----------------------------------------------------------------


def query(sql: str, args=()) -> list[sqlite3.Row]:
    with closing(db.connect()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, args).fetchall()


def one_or_404(sql: str, args) -> sqlite3.Row:
    found = query(sql, args)
    if not found:
        raise HTTPException(404)
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
        raise HTTPException(404, f"no project at {path}")
    p = found[0]
    factory = factory_state(p["path"], p["default_branch"])
    return {"id": p["id"], "name": p["name"], "default_branch": p["default_branch"], "factory": factory}


# --- Tasks (docs/data-model-and-api.md §6.2) ----------------------------------


class TaskBody(BaseModel):
    title: str
    description_md: str = ""


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
def create_task(project_id: int, body: TaskBody):
    title = body.title.strip()
    if not title:
        raise HTTPException(422, "title must not be blank")
    with closing(db.connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")  # the bottom position and the insert, atomically
        if not conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
            raise HTTPException(404)
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 1.0) FROM tasks WHERE project_id = ? AND status = 'backlog'",
            (project_id,),
        ).fetchone()[0]
        now = db.now()
        task_id = conn.execute(
            "INSERT INTO tasks (project_id, title, description_md, status, position, created_at, updated_at)"
            " VALUES (?, ?, ?, 'backlog', ?, ?, ?)",
            (project_id, title, body.description_md, position, now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO events (task_id, actor, to_status, created_at) VALUES (?, 'me', 'backlog', ?)",
            (task_id, now),
        )
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
    create_task(project_id, body)
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
