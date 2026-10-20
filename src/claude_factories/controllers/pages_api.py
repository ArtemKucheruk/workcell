"""docs/data-model-and-api.md §6.4: /api/auth and its login (039), /api/docs/fctl, and one view-model per SPA
page. Each route calls its page handler in handlers/pages.py and maps the dict onto dto/pages.py (020 Q2): rows
become objects, markdown gets `*_html`."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, Query

from ..domain.enums import Reviewer
from ..dto import pages as dto
from ..handlers import code as code_handler
from ..handlers import pages as handler
from ..lib.markdown import render
from ..server.deps import (
    ClaudeAdapter,
    GitAdapter,
    Projects,
    Reviews,
    Rounds,
    Runs,
    Tasks,
    Transcripts,
    Workspaces,
    get_claude,
)


@asynccontextmanager
async def lifespan(app):
    """039 AC15: a pending `claude auth login` ends with the server, as controllers/runs.py's runs do."""
    yield
    handler.login_stop(get_claude())


router = APIRouter(lifespan=lifespan)
KINDS = ("event", "round", "verdict", "decision", "comment")  # Q8: the timeline SQL's 0–4 sort key
SIDE = {"add": "new", "ctx": "new", "del": "old"}  # Q5: hunk and note rows have no side


def obj(row, *md: str) -> dict | None:
    """A row (or None) as a dict, each `<name>_md` in `md` with its rendered `<name>_html` (raw HTML off)."""
    if row is None:
        return None
    out = dict(row)
    for name in md:
        out[f"{name}_html"] = render(out[f"{name}_md"])
    return out


def objs(rows, *md: str) -> list[dict]:
    return [obj(r, *md) for r in rows]


def posted(page: dict, n: int) -> dict:
    """Round n's posted verdicts, in reviewer order."""
    found = page["posted"].get(n, {})
    return {who.value: obj(found[who], "body") for who in Reviewer if who in found}


def diff_row(path: str, row: dict) -> dict:
    side = SIDE.get(row["kind"])
    return row | {"side": side, "anchor": side and f"{path}:{side}:{row[side]}",
                  "comments": objs(row["comments"], "body")}


def diff_file(f: dict) -> dict:
    """One review_files entry; the dto drops its `patch` and each row's `form`."""
    return f | {"rows": [diff_row(f["path"], r) for r in f["rows"]], "orphans": objs(f["orphans"], "body")}


@router.get("/api/auth")
def auth(claude: ClaudeAdapter) -> dto.AuthOut:
    return handler.auth(claude)


@router.post("/api/auth/login")
def login(claude: ClaudeAdapter) -> dto.LoginStarted:
    return handler.login_start(claude)


@router.post("/api/auth/login/code")
def login_code(body: dto.LoginCode, claude: ClaudeAdapter) -> dto.AuthOut:
    return handler.login_code(claude, body.code)


@router.get("/api/docs/fctl")
def fctl_doc() -> dto.FctlDoc:
    """029 Q8: docs/ui.md §8 item 7's reference, next to the page view-models."""
    return handler.fctl_doc()


@router.get("/api/pages/sidebar")
def sidebar(projects: Projects, tasks: Tasks, transcripts: Transcripts, task: int | None = None,
            transcript: int | None = None) -> dto.SidebarPage:
    """041: fetched on load and after each navigation, never polled. A non-integer id is FastAPI's 422 (Q3)."""
    page = handler.sidebar(projects, tasks, transcripts, task, transcript)
    return page | {"workspaces": [w | {"projects": objs(w["projects"])} for w in page["workspaces"]]}


@router.get("/api/pages/dashboard")
def dashboard(tasks: Tasks, runs: Runs, workspaces: Workspaces, show: str = "") -> dto.DashboardPage:
    page = handler.dashboard(tasks, runs, workspaces, show)
    return page | {
        "counts": dict(page["counts"]), "listed": page["listed"] and objs(page["listed"]),
        "open_tasks": [{"id": ws_id, "name": name, "projects": objs(projects)}
                       for (ws_id, name), projects in page["open_tasks"]],
        "done": objs(page["done"]), "workspaces": objs(page["workspaces"]),
    }


@router.get("/api/pages/workspaces/{workspace_id}")
def workspace(workspace_id: int, workspaces: Workspaces, projects: Projects, git: GitAdapter) -> dto.WorkspacePage:
    page = handler.workspace(workspaces, projects, git, workspace_id)
    return {"workspace": obj(page["workspace"]), "projects": page["projects"]}


@router.get("/api/pages/projects/{project_id}")
def board(project_id: int, projects: Projects, tasks: Tasks, rounds: Rounds, reviews: Reviews, runs: Runs,
          workspaces: Workspaces, git: GitAdapter, claude: ClaudeAdapter) -> dto.BoardPage:
    page = handler.board(projects, tasks, rounds, reviews, runs, workspaces, git, claude, project_id)
    return page | {"project": obj(page["project"]), "workspaces": objs(page["workspaces"])}


@router.get("/api/pages/tasks/{task_id}")
def task(task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews, runs: Runs, transcripts: Transcripts,
         git: GitAdapter, claude: ClaudeAdapter) -> dto.TaskPage:
    page = handler.task(tasks, rounds, reviews, runs, transcripts, git, claude, task_id)
    return page | {
        "task": obj(page["task"], "description", "spec"), "run": obj(page["run"]),
        "rounds": [r | obj({"build_md": page["build"].get(r["n"])}, "build") | {"posted": posted(page, r["n"])}
                   for r in page["rounds"]],
        "approver": obj(page["approver"], "body"), "history": objs(page["history"]),
    }


@router.get("/api/pages/tasks/{task_id}/review")
def review(task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews,
           n: str = Query("latest", alias="round")) -> dto.ReviewPage:
    """Q6: always with the round's files, whatever tab the SPA shows."""
    page = handler.review(tasks, rounds, reviews, task_id, n, "files")
    return page | {
        "task": obj(page["task"], "description", "spec") | {"commit_hint": page["commit_hint"]},
        "rounds": [r | {"posted": posted(page, r["n"])} for r in page["rounds"]],
        "approver": obj(page["approver"], "body"), "files": [diff_file(f) for f in page["files"]],
        "timeline": [obj(e, "body") | {"kind": KINDS[e["kind"]]} for e in page["timeline"]],
    }


@router.get("/api/pages/projects/{project_id}/code")
def code(project_id: int, projects: Projects, git: GitAdapter, path: str = "") -> dto.CodePage:
    page = code_handler.code(projects, git, project_id, path)
    text = None if path else page.get("view", {}).get("text")  # Q12: the landing page's README
    return page | {"project": obj(page["project"]), "readme_html": None if text is None else render(text)}
