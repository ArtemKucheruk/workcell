import argparse
import sys
from pathlib import Path

from ..client import api, base_url
from ..git import main_checkout
from ..output import fail, print_run, stdin_text
from .projects import plural, project_at
from .runs import account_id


def task_ids(text: str) -> list[int]:
    """094 AC18: `12,14` → [12, 14]. A part that isn't a positive integer is argparse's usage error (exit 2)."""
    parts = text.split(",")
    if not all(p.isascii() and p.isdigit() and int(p) > 0 for p in parts):
        raise argparse.ArgumentTypeError(f"task ids must be positive integers separated by commas, not {text!r}")
    return [int(p) for p in parts]


def module_id(project: dict, name: str) -> int:
    """112 AC23, AC24, Q11: the project's module named `name`, trimmed and in any case; an unknown name fails, before
    any task is posted, with the known names in the API's order."""
    modules = api("GET", f"/api/projects/{project['id']}/modules")["modules"]
    wanted = name.strip().casefold()
    for m in modules:
        if m["name"].casefold() == wanted:
            return m["id"]
    known = ", ".join(m["name"] for m in modules) or "none"
    fail(f"no module {name.strip()} in {project['name']}; known: {known}")


def task_add(args):
    body = {"title": args.title}
    if args.description is not None:  # Q2: "-" always means stdin
        text = stdin_text() if args.description == "-" else args.description
        if not text.strip():  # Q1: refused before any request, like fctl spec
            fail("description is empty; pass it as text, or on stdin with --description -")
        body["description_md"] = text
    if args.blocked_by is not None:  # 094 AC17
        body["blocked_by"] = args.blocked_by
    project = project_at(main_checkout())
    if args.module is not None:
        body["module_id"] = module_id(project, args.module)
    task = api("POST", f"/api/projects/{project['id']}/tasks", body)
    # flush: a refused run's stderr line must come after this one, also when stdout is a pipe
    print(f"Added #{task['id']} to {project['name']} → {base_url()}/projects/{project['id']}", flush=True)
    if args.run:  # Q11: a refused run leaves the task in Backlog, its Added line already printed
        print_run(task["id"], api("POST", f"/api/tasks/{task['id']}/run"))


def task_block(args):
    """094 AC19: fctl task block (PUT) and unblock (DELETE), then every link left, with its blocker's status.
    Task ids are global, so no repo is needed."""
    deps = api(args.method, f"/api/tasks/{args.id}/blocked-by/{args.by}")
    blockers = ", ".join(f"#{d['id']} ({d['status']})" for d in deps["blocked_by"])
    print(f"#{deps['id']} blocked by {blockers}" if blockers else f"#{deps['id']} has no blockers")


def task_retry(args):
    """106: the CLI twin of the web Retry (ui.md item 4, §8.1). Refuses before posting when there is nothing to
    retry (AC5, AC6); Q2: anything else posts and the server's answer stands. Q3: the task is checked before an
    email --account is resolved. Task ids are global, so no repo is needed (AC9)."""
    run = api("GET", f"/api/tasks/{args.id}")["run"]
    if run is None:
        fail(f"#{args.id} never ran; use fctl run {args.id}")
    if run["status"] == "running":
        fail(f"run #{run['id']} is running on #{args.id}; wait for it or stop it")
    body = {"account_id": account_id(args.account)} if args.account is not None else None
    print_run(args.id, api("POST", f"/api/tasks/{args.id}/run", body))


# 105 AC10: the board's delete dialog sentence (BoardPage.jsx DeleteTask), word for word
REMOVES = ("This removes its runs, rounds and their files, verdicts, comments, decisions, status history, and transcript"
           " records from the app. Its worktree, branch, run logs, and copied transcript files stay on disk.")


def task_delete(args):
    """105: DELETE /api/tasks/{id} after a confirmation that --yes skips. Q5: off a TTY without --yes it refuses before
    any request. Q3: the GET runs even with --yes, so the output names the title; its 404 shows as given.
    Q6: no early refusal for a running run: the DELETE's 409 shows as given. Q7: the prompt goes to stdout."""
    if not args.yes and not sys.stdin.isatty():
        fail(f"not a terminal; pass --yes to delete #{args.id} without asking")
    task = api("GET", f"/api/tasks/{args.id}")
    name = f"#{task['id']} {task['title']}"
    if not args.yes:
        print(f"Delete {name}?")
        print(REMOVES)
        try:
            answer = input("Delete? [y/N] ")
        except EOFError:  # Q4: EOF counts as no
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            fail("not deleted")
    api("DELETE", f"/api/tasks/{args.id}")
    print(f"Deleted {name}")


def export(args):
    """032 Q9: task ids are global, so no repo is needed; the file is overwritten, like curl -o."""
    data = api("GET", f"/api/tasks/{args.id}/export" + ("?transcripts=1" if args.transcripts else ""))
    out = args.output or f"task-{args.id}.zip"
    try:
        Path(out).write_bytes(data)
    except OSError as e:
        fail(f"can't write {out}: {e.strerror}")
    print(f"Exported #{args.id} → {out}")


def import_bundle(args):
    """032 Q9: into the current repo's project. The file is read first, so a bad path makes no HTTP call."""
    try:
        data = Path(args.file).read_bytes()
    except OSError as e:
        fail(f"can't read {args.file}: {e.strerror}")
    project = project_at(main_checkout())
    got = api("POST", f"/api/projects/{project['id']}/import", data=data, content_type="application/zip")
    print(f"Imported #{got['task_id']} {got['title']} ({'new' if got['created'] else 'updated'}, {got['status']},"
          f" {plural(got['rounds'], 'round')}, {plural(got['transcripts'], 'transcript')})")
