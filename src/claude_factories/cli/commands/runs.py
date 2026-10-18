from ..client import api
from ..git import main_checkout
from ..output import print_run
from .projects import project_at


def run(args):
    """docs/claude-code.md §7.2: `fctl run <id>` needs no repo; `fctl run next` takes the top of the
    current repo's Backlog (Q10)."""
    if args.target == "next":
        r = api("POST", f"/api/projects/{project_at(main_checkout())['id']}/run-next")
        print_run(r["task_id"], r["run_id"])
    elif args.target.isdecimal():
        task_id = int(args.target)
        print_run(task_id, api("POST", f"/api/tasks/{task_id}/run")["run_id"])
    else:
        args.usage_error(f"target must be a task id or next, not {args.target!r}")
