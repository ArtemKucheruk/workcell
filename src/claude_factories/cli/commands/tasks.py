from pathlib import Path

from ..client import api, base_url
from ..git import main_checkout
from ..output import fail, print_run
from .projects import plural, project_at


def task_add(args):
    project = project_at(main_checkout())
    task = api("POST", f"/api/projects/{project['id']}/tasks", {"title": args.title})
    # flush: a refused run's stderr line must come after this one, also when stdout is a pipe
    print(f"Added #{task['id']} to {project['name']} → {base_url()}/projects/{project['id']}", flush=True)
    if args.run:  # Q11: a refused run leaves the task in Backlog, its Added line already printed
        print_run(task["id"], api("POST", f"/api/tasks/{task['id']}/run")["run_id"])


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
