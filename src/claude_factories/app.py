"""The FastAPI app behind `fctl serve`."""

import os
import sqlite3
import subprocess
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import db

HERE = Path(__file__).parent
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SKILL = ".claude/skills/factory/SKILL.md"


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
    # ponytail: stub (Q11); job 004 adds the board
    project = one_or_404(
        "SELECT p.id, p.name, p.path, p.workspace_id, w.name AS workspace FROM projects p"
        " JOIN workspaces w ON w.id = p.workspace_id WHERE p.id = ?",
        (project_id,),
    )
    return templates.TemplateResponse(
        request, "project.html", {"project": project, "workspaces": workspaces()}
    )


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
