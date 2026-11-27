"""109: Plane sync, `POST /api/projects/{id}/plane/sync`, and approve's mark done (docs/data-model-and-api.md §6.1,
docs/MVP.md §4.5). The project's backlog and unstarted work items become Backlog tasks keyed on `tasks.import_key`
`plane:<slug>/<project id>/<item id>`, through #108's upsert. AC11: the project is read in one transaction and the
tasks are written in another, so no SQLite write lock waits on Plane. No detail here names the API key."""

from ..adapters.plane import Plane
from ..domain.enums import Status
from ..domain.errors import Conflict, DomainError, Failed, NotFound
from ..dto.github_issues import IssuesSynced
from ..lib.plane_item import description, key, parse_key
from ..repositories.projects import ProjectsRepo
from ..repositories.tasks import TasksRepo
from .factory_import import upsert

GROUPS = ("backlog", "unstarted")  # AC8, Q8: not triage
NEEDS = "Plane sync needs the API URL, workspace slug, project ID and API key: fill them in project Settings"


def settings(project) -> tuple[str, str, str, str]:
    """AC12: (url, key, slug, project id), else the 409 naming what to fill in."""
    found = (project["plane_api_url"], project["plane_api_key"], project["plane_workspace"],
             project["plane_project_id"])
    if not all(found):
        raise Conflict(NEEDS)
    return found


def item(found) -> dict:
    """One work item, else a 500: {id, name, sequence_id, state, description_stripped}."""
    state = found.get("state") if isinstance(found, dict) else None
    if isinstance(state, dict):  # an `expand=state` answer
        state = state.get("id")
    ok = (isinstance(found, dict) and isinstance(found.get("id"), str) and isinstance(found.get("name"), str)
          and found["name"].strip() and type(found.get("sequence_id")) is int and isinstance(state, str)
          and isinstance(found.get("description_stripped"), str | None))
    if not ok:
        raise Failed("Plane listed a work item without an id, name, sequence_id or state")
    return found | {"state": state}


def groups(states: list) -> dict[str, str]:
    """state id → group."""
    return {s["id"]: s.get("group") for s in states if isinstance(s, dict) and isinstance(s.get("id"), str)}


def sync(tx, plane: Plane, project_id: int) -> IssuesSynced:
    """AC6–AC12: every check, and every Plane call, before the first write."""
    with tx() as conn:
        project = ProjectsRepo(conn).for_plane(project_id)
    if project is None:
        raise NotFound(f"Project #{project_id} not found")
    url, api_key, slug, pid = settings(project)
    identifier = plane.project(url, api_key, slug, pid)["identifier"]
    group = groups(plane.states(url, api_key, slug, pid))
    items = sorted((i for i in map(item, plane.items(url, api_key, slug, pid)) if group.get(i["state"]) in GROUPS),
                   key=lambda i: i["sequence_id"])
    counts = {"new": 0, "updated": 0, "skipped": 0}
    with tx() as conn:
        tasks = TasksRepo(conn)
        now = tasks.lock()
        found = {i["id"]: tasks.by_import_key(key(slug, pid, i["id"])) for i in items}
        for item_id, task in found.items():  # AC11: before any write
            if task and task["project_id"] != project_id:
                raise Conflict(f"{key(slug, pid, item_id)} is imported in project #{task['project_id']}")
        for i in items:
            outcome = upsert(tasks, project_id, found[i["id"]], key(slug, pid, i["id"]), i["name"].strip(),
                             description(i.get("description_stripped"), identifier, i["sequence_id"]),
                             Status.BACKLOG, now)[1]
            counts[outcome] += 1
    return IssuesSynced(**counts)


def completed(states: list) -> str:
    """AC13: the first state in group `completed`, by lowest `sequence`, else list order."""
    done = [(s.get("sequence") if isinstance(s.get("sequence"), int | float) else float("inf"), n, s["id"])
            for n, s in enumerate(states) if isinstance(s, dict) and s.get("group") == "completed"
            and isinstance(s.get("id"), str)]
    if not done:
        raise Conflict("Plane project has no completed state")
    return min(done)[2]


def mark_done(tx, plane: Plane, task) -> str | None:
    """AC13–AC15: after approve commits, outside any transaction, a `plane:` task's item moves to the completed
    state when its project has mark done on. Q3: the key's slug and project, the current URL and key. A failure is
    the warning approve returns, never a refusal."""
    found = parse_key(task["import_key"])
    if found is None:
        return None
    with tx() as conn:
        project = ProjectsRepo(conn).for_plane(task["project_id"])
    if project is None or not project["plane_mark_done"]:
        return None
    slug, pid, item_id = found
    try:
        url, api_key = settings(project)[:2]
        state = completed(plane.states(url, api_key, slug, pid))
        plane.set_state(url, api_key, slug, pid, item_id, state)
    except DomainError as e:
        return f"Approved, but Plane wasn't updated: {e.detail}"
    return None
