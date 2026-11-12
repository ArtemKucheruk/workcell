"""093: Create PR, the PR's state, and Merge PR (docs/MVP.md §3.7, docs/data-model-and-api.md §6.3), and the task
pages' `pr` field (§6.4). Agents never commit: git and gh run only on these requests, through the git adapter. AC23:
the task is read in one transaction and the PR and its event are written in another, through `transaction()` as
`rework` does, so no SQLite write lock waits on git or gh. Every refusal is a 409 carrying git's or gh's own line."""

import json
import os
from urllib.parse import urlsplit

from .. import config
from ..adapters.git import Git, Ran
from ..domain.enums import Status
from ..domain.errors import Conflict, DomainError, Failed, NotFound
from ..dto.pull_requests import PrCreated, PrMerged, PrState
from ..lib.pull_request import checks, pr_body, pr_number
from ..lib.remote import web_url
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.tasks import TasksRepo

DOCKER_HINT = " (the backend image has no gh login; create the PR from your host)"  # AC14, Q5


def first_line(text: str) -> str | None:
    return next((line.strip() for line in text.splitlines() if line.strip()), None)


def said(r: Ran, tool: str) -> str:
    """The first line of stderr, else of stdout: what git or gh said when it failed."""
    code, out, err = r
    return first_line(err) or first_line(out) or f"{tool} exited with code {code}"


# --- Reads and checks ------------------------------------------------------------------------


def read_task(tx, task_id: int, body: bool = False) -> dict:
    """The task with its project's path and default branch, in its own transaction. With `body`, also what the PR
    body needs: the round count, the latest round's n and verdicts, and the approver's latest decision."""
    with tx() as conn:
        found = TasksRepo(conn).for_pr(task_id)
        if found is None:
            raise NotFound(f"Task #{task_id} not found")
        task = dict(found)
        if body:
            reviews, rounds = ReviewsRepo(conn), RoundsRepo(conn).all(task_id)
            latest = rounds[-1] if rounds else None
            approver = reviews.approver_latest(task_id)
            task |= {"rounds": len(rounds), "latest": latest and latest["n"],
                     "verdicts": {v["reviewer"]: v["verdict"] for v in reviews.round_verdicts(latest["id"])}
                     if latest else {},
                     "approver": approver and (approver["decision"], approver["body_md"])}
        return task


def check_done(task: dict) -> None:
    """AC7: before any git or gh call."""
    if task["status"] != Status.DONE:
        raise Conflict(f"#{task['id']} is not done; approve it first")


def github_repo(git: Git, root: str) -> str:
    """AC10, AC11, Q6: origin's `owner/repo` on github.com, read raw (no insteadOf) and parsed by lib/remote."""
    code, out, _ = git.origin_url(root)
    url = out.strip()
    if code or not url:
        raise Conflict(f"{root} has no origin remote; add one with git remote add origin …")
    web = web_url(url)
    parts = urlsplit(web) if web else None
    host = parts.hostname if parts else None
    if host != "github.com":
        raise Conflict(f"origin isn't on GitHub ({host or url}); push and open the PR yourself")
    return parts.path.strip("/")


def gh_refusal(detail: str) -> Conflict:
    """AC14: under Docker, the AC12 and AC13 refusals say why."""
    return Conflict(detail + (DOCKER_HINT if config.in_docker() else ""))


def gh_installed(git: Git) -> None:
    if not git.gh_installed():
        raise gh_refusal("gh is not installed: install GitHub CLI, then run gh auth login")


def gh_ready(git: Git) -> None:
    """AC12, AC13: gh is on PATH and logged in to github.com."""
    gh_installed(git)
    r = git.gh_auth()
    if r[0]:
        raise gh_refusal(f"gh is not logged in: run gh auth login. {said(r, 'gh')}")


def gh_json(r: Ran, what: str):
    if r[0]:
        raise Conflict(said(r, "gh"))
    try:
        return json.loads(r[1])
    except ValueError:
        raise Failed(f"{what} printed no JSON: {first_line(r[1]) or 'nothing'}") from None


def viewed(git: Git, repo: str, number: int) -> dict:
    """AC24, AC26: `gh pr view`'s JSON. Q2: polled every 10 s, so gh's login is checked only when the view fails,
    which then gets AC13's refusal if that is why."""
    gh_installed(git)
    r = git.pr_view(repo, number)
    if r[0]:
        gh_ready(git)
        raise Conflict(said(r, "gh"))
    found = gh_json(r, "gh pr view")
    if not isinstance(found, dict) or not isinstance(found.get("state"), str):
        raise Failed("gh pr view printed no PR state")
    return found


def push_refusal(err: str) -> str:
    """AC18: git's `! [rejected] …` line, else its `error:` or `fatal:` line; never the `To <url>` line."""
    lines = [line.strip() for line in err.splitlines() if line.strip()]
    picked = (next((line for line in lines if line.startswith("! [")), None)
              or next((line for line in lines if line.startswith(("error:", "fatal:"))), None)
              or next((line for line in lines if not line.startswith("To ")), "git push failed"))
    return f"git push was rejected: {picked}"


# --- POST /api/tasks/{id}/pr -----------------------------------------------------------------


def commit_work(git: Git, task: dict) -> None:
    """AC15–AC17: commit the worktree's changes under my identity with the title as the whole message; a clean
    worktree needs commits beyond the default branch instead."""
    wt, default = task["worktree_path"], task["default_branch"]
    r = git.porcelain(wt)
    if r[0]:
        raise Conflict(f"git status failed: {said(r, 'git')}")
    if r[1].strip():
        r = git.commit(wt, task["title"])
        if r[0]:
            raise Conflict(f"git commit failed: {said(r, 'git')}")
        return
    r = git.ahead(wt, default)
    if r[0]:
        raise Conflict(f"git rev-list failed: {said(r, 'git')}")
    if not int(r[1].strip() or 0):
        raise Conflict(f"nothing to commit: #{task['id']}'s branch has no changes beyond {default}")


def create(tx, git: Git, task_id: int, base_url: str) -> PrCreated:
    """AC5–AC23: commit, push, then open the PR, or reuse the branch's open one (AC21). pr_url and a `PR #N opened`
    event are written only when pr_url changes, so asking again adds nothing. Q10 ponytail: no server-side lock;
    the button disables while pending, and the reuse keeps a second request from opening a second PR."""
    task = read_task(tx, task_id, body=True)
    check_done(task)
    if not (task["branch"] and task["worktree_path"]):
        raise Conflict(f"#{task_id} has no branch; commit it yourself")
    if not os.path.isdir(task["worktree_path"]):
        raise Conflict(f"the worktree {task['worktree_path']} is gone")
    repo = github_repo(git, task["path"])
    gh_ready(git)
    commit_work(git, task)
    branch, default = task["branch"], task["default_branch"]
    r = git.push(task["worktree_path"], branch)
    if r[0]:
        raise Conflict(push_refusal(r[2]))
    found = gh_json(git.pr_list(repo, branch), "gh pr list")
    opened = next((p for p in found if isinstance(p, dict) and pr_number(p.get("url")) is not None), None) \
        if isinstance(found, list) else None
    if opened:
        url, reused = opened["url"], True
    else:
        body = pr_body(task["description_md"], task["rounds"], task["latest"], task["verdicts"], task["approver"],
                       f"{base_url}tasks/{task_id}")
        r = git.pr_create(repo, default, branch, task["title"], body)
        if r[0]:
            raise Conflict(said(r, "gh"))
        url, reused = next((line.strip() for line in reversed(r[1].splitlines()) if pr_number(line)), None), False
        if url is None:
            raise Failed(f"gh pr create printed no PR URL: {first_line(r[1]) or 'nothing'}")
    number = pr_number(url)
    with tx() as conn:
        tasks = TasksRepo(conn)
        now = tasks.lock()
        current = tasks.for_pr(task_id)
        if current is not None and current["pr_url"] != url:
            tasks.set_pr_url(task_id, url, now)
            tasks.add_event(task_id, "me", Status.DONE, Status.DONE, None, now, f"PR #{number} opened")
    return PrCreated(number=number, url=url, reused=reused)


# --- GET /api/tasks/{id}/pr ------------------------------------------------------------------


def pr_of(task: dict) -> int | None:
    return pr_number(task["pr_url"])


def state(tx, git: Git, task_id: int) -> PrState:
    """AC24–AC26."""
    task = read_task(tx, task_id)
    number = pr_of(task)
    if number is None:
        raise NotFound(f"#{task_id} has no PR")
    found = viewed(git, github_repo(git, task["path"]), number)
    return PrState(number=number, url=found.get("url") or task["pr_url"], state=found["state"],
                   checks=checks(found.get("statusCheckRollup")))


# --- POST /api/tasks/{id}/pr/merge -----------------------------------------------------------


def update_main(git: Git, root: str, default: str) -> str:
    """AC31–AC33, Q7: fetch, then fast-forward the main checkout only when that can't fail: it is on the default
    branch, `git status --porcelain` is empty (untracked files count), and HEAD is an ancestor of origin's."""
    target, skip = f"origin/{default}", f"Skipped updating {default}"
    r = git.fetch(root)
    if r[0]:
        return f"{skip}: git fetch failed: {said(r, 'git')}"
    r = git.head_branch(root)
    on = r[1].strip()
    if r[0] or on != default:
        return f"{skip}: the main checkout is on {on or 'a detached HEAD'}."
    r = git.porcelain(root)
    if r[0] or r[1].strip():
        return f"{skip}: the main checkout has uncommitted changes."
    r = git.is_ancestor(root, "HEAD", target)
    if r[0] == 1:
        return f"{skip}: {default} has commits not on {target}."
    if r[0]:
        return f"{skip}: {said(r, 'git')}"
    r = git.ff_merge(root, target)
    if r[0]:
        return f"{skip}: {said(r, 'git')}"
    return f"Fast-forwarded {default} to {target}."


def cleanup(git: Git, root: str, wt: str | None, branch: str | None) -> list[str]:
    """AC34, AC35, Q8, Q9: worktree, local branch, then remote branch, never forced. A failed step is a note with
    git's line, and the rest still run."""
    notes = []
    if wt and os.path.isdir(wt):
        r = git.remove_worktree(root, wt)
        notes.append(f"Removed the worktree {wt}." if not r[0] else f"Kept the worktree: {said(r, 'git')}")
    else:
        notes.append("Worktree already removed.")
    if branch:
        r = git.delete_branch(root, branch)
        notes.append(f"Deleted the local branch {branch}." if not r[0]
                     else f"Kept the local branch {branch}: {said(r, 'git')}")
        r = git.delete_remote_branch(root, branch)
        notes.append(f"Deleted the remote branch {branch}." if not r[0]
                     else "Remote branch already deleted." if "remote ref does not exist" in r[2]
                     else f"Kept the remote branch {branch}: {said(r, 'git')}")
    return notes


def merge(tx, git: Git, task_id: int) -> PrMerged:
    """AC27–AC35: merge an open PR with MERGE_METHOD (an already merged one skips it, a closed one is refused), write
    `PR #N merged`, then update main and clean up. Only refusals up to and during the merge fail the request."""
    task = read_task(tx, task_id)
    check_done(task)
    number = pr_of(task)
    if number is None:
        raise Conflict(f"#{task_id} has no PR; Create PR first")
    repo = github_repo(git, task["path"])
    gh_ready(git)
    found = viewed(git, repo, number)
    if found["state"] == "CLOSED":
        raise Conflict(f"PR #{number} is closed; reopen it on GitHub")
    if found["state"] != "MERGED":
        r = git.pr_merge(repo, number)
        if r[0]:
            raise Conflict(said(r, "gh"))
        with tx() as conn:
            tasks = TasksRepo(conn)
            now = tasks.lock()
            tasks.add_event(task_id, "me", Status.DONE, Status.DONE, None, now, f"PR #{number} merged")
    root = task["path"]
    notes = [update_main(git, root, task["default_branch"]), *cleanup(git, root, task["worktree_path"],
                                                                         task["branch"])]
    return PrMerged(number=number, state="MERGED", notes=notes)


# --- The task pages' `pr` (§6.4) -------------------------------------------------------------


def page_pr(git: Git, task) -> dict | None:
    """AC36: what Create PR shows, from the task row and local git only, never gh. Standalone tasks: None."""
    if not (task["branch"] and task["worktree_path"]):
        return None
    url = task["pr_url"]
    pr = {"url": url, "number": pr_number(url), "can_create": False, "hint": None}
    if url:
        return pr
    if task["status"] != Status.DONE:
        return pr | {"hint": "Approve it first."}
    wt, default = task["worktree_path"], task["default_branch"]
    if not os.path.isdir(wt):
        return pr | {"hint": "The worktree is gone."}
    try:
        changed = git.porcelain(wt)
        ahead = None if changed[0] or changed[1].strip() else git.ahead(wt, default)
    except DomainError as e:  # a timeout: the page still loads
        return pr | {"hint": e.detail}
    if failed := next((r for r in (changed, ahead) if r and r[0]), None):
        return pr | {"hint": said(failed, "git")}
    if changed[1].strip() or int(ahead[1].strip() or 0):
        return pr | {"can_create": True}
    return pr | {"hint": f"Nothing to commit beyond {default}."}
