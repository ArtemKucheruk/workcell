from ..client import api, base_url
from ..git import main_checkout
from ..output import print_run
from .projects import project_at


def task_add(args):
    project = project_at(main_checkout())
    task = api("POST", f"/api/projects/{project['id']}/tasks", {"title": args.title})
    # flush: a refused run's stderr line must come after this one, also when stdout is a pipe
    print(f"Added #{task['id']} to {project['name']} → {base_url()}/projects/{project['id']}", flush=True)
    if args.run:  # Q11: a refused run leaves the task in Backlog, its Added line already printed
        print_run(task["id"], api("POST", f"/api/tasks/{task['id']}/run")["run_id"])
