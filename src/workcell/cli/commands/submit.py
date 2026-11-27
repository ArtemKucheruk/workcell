import sys

from ..client import api
from ..git import capture, main_checkout
from ..output import stdin_text, summary
from .projects import project_at


def submit(args):
    if (args.id is None) != args.new or args.new != (args.title is not None):  # Q11
        args.usage_error("give a task id, or --new with --title")
    main = main_checkout()  # also the "not inside a git repository" check
    base_sha, patch = capture()
    text = stdin_text()
    if args.new:
        project = project_at(main)
        body = {"title": args.title, "description_md": text, "submit": {"base_sha": base_sha, "patch": patch}}
        r = api("POST", f"/api/projects/{project['id']}/tasks", body)
        print(f"Review #{r['task_id']}: {summary(r)}")
    else:
        r = api("POST", f"/api/tasks/{args.id}/rounds", {"base_sha": base_sha, "build_md": text, "patch": patch})
        print(f"Round {r['round']} of #{args.id}: {summary(r)}")


def diff(args):
    n = "latest" if args.round is None else args.round
    sys.stdout.write(api("GET", f"/api/tasks/{args.id}/rounds/{n}/diff"))
