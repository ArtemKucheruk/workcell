"""108: GitHub issues sync, `POST /api/projects/{id}/github-issues/sync` (docs/data-model-and-api.md §6.1). The
repo's open issues (the saved label's alone, if set) become Backlog tasks keyed on `tasks.import_key`
`github:<owner>/<repo>#<n>`, through the user's `gh` login, only when they click Sync now. AC19: the project is read
in one transaction and the tasks are written in another, so no SQLite write lock waits on gh (093 AC23)."""

from urllib.parse import urlsplit

from ..adapters.git import ISSUE_LIMIT, Git
from ..domain.enums import Status
from ..domain.errors import Conflict, Failed, NotFound
from ..dto.github_issues import IssuesSynced
from ..lib.github_issue import description, key
from ..lib.remote import web_url
from ..repositories.projects import ProjectsRepo
from ..repositories.tasks import TasksRepo
from .factory_import import upsert
from .pull_requests import first_line, gh_json, gh_ready, github_repo

FIX = "GitHub issues sync needs a github.com origin"  # Q3
DOCKER_HINT = " (the backend image has no gh login; sync issues from the app on your host)"  # Q3


def page_github(remote_url: str | None) -> dict:
    """AC5, Q2: the Settings page's `github_repo` and `github_hint`, from the stored remote_url alone (no git or gh
    on a poll). The SPA never sees the raw remote, only web_url's host (lib/remote)."""
    if not remote_url:
        return {"github_repo": None,
                "github_hint": "This project has no origin remote: add a github.com origin, then run fctl connect"
                               " in the repo."}
    web = web_url(remote_url)
    parts = urlsplit(web) if web else None
    if parts and parts.hostname == "github.com":
        return {"github_repo": parts.path.strip("/"), "github_hint": None}
    host = f" ({parts.hostname})" if parts else ""
    return {"github_repo": None, "github_hint": f"origin isn't on GitHub{host}; {FIX}."}


def issue(found) -> dict:
    """One entry of gh's JSON, else a 500: {number, title, body, url}."""
    ok = (isinstance(found, dict) and type(found.get("number")) is int and found["number"] > 0
          and isinstance(found.get("title"), str) and found["title"].strip()
          and isinstance(found.get("url"), str) and isinstance(found.get("body"), str | None))
    if not ok:
        raise Failed(f"gh issue list printed an issue without a number, title, or url: {str(found)[:100]}")
    return found


def listed(git: Git, repo: str, label: str | None) -> list[dict]:
    """AC10–AC12: the open issues in ascending number (Q5)."""
    r = git.issue_list(repo, label, ISSUE_LIMIT)
    found = gh_json(r, "gh issue list")
    if not isinstance(found, list):
        raise Failed(f"gh issue list printed no JSON: {first_line(r[1]) or 'nothing'}")
    return sorted((issue(i) for i in found), key=lambda i: i["number"])


def sync(tx, git: Git, project_id: int) -> IssuesSynced:
    """AC6–AC20: every check, and gh, before the first write. Q9: a deleted task's issue comes back as a new task."""
    with tx() as conn:
        project = ProjectsRepo(conn).for_issues(project_id)
    if project is None:
        raise NotFound(f"Project #{project_id} not found")
    repo = github_repo(git, project["path"], FIX)
    gh_ready(git, DOCKER_HINT)
    issues = listed(git, repo, project["github_label"])
    counts = {"new": 0, "updated": 0, "skipped": 0}
    with tx() as conn:
        tasks = TasksRepo(conn)
        now = tasks.lock()
        found = {i["number"]: tasks.by_import_key(key(repo, i["number"])) for i in issues}
        for n, task in found.items():  # AC18: 031 Q11, before any write
            if task and task["project_id"] != project_id:
                raise Conflict(f"{key(repo, n)} is imported in project #{task['project_id']}")
        for i in issues:
            outcome = upsert(tasks, project_id, found[i["number"]], key(repo, i["number"]), i["title"].strip(),
                             description(i["body"], i["url"]), Status.BACKLOG, now)[1]
            counts[outcome] += 1
    return IssuesSynced(**counts)
