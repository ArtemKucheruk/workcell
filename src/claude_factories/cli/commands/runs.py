from ..client import api
from ..git import main_checkout
from ..output import fail, print_automation_run, print_run
from .projects import project_at


def account_id(value: str) -> int:
    """097 AC30: an account id as is, else an email matched exactly, ignoring case, against /api/auth/accounts."""
    if value.isdecimal():
        return int(value)
    found = [a["id"] for a in api("GET", "/api/auth/accounts")
             if isinstance(a.get("email"), str) and a["email"].casefold() == value.casefold()]
    if not found:
        fail(f"no Claude account {value}")
    return found[0]


def run(args):
    """docs/claude-code.md §7.2: `fctl run <id>` needs no repo; `fctl run next` takes the top of the
    current repo's Backlog (Q10). 097: `--account` picks the run's account (AC30); without it, Auto and no body
    (AC31). Run next is always Auto."""
    if args.target == "next":
        if args.account is not None:
            args.usage_error("--account can't be used with next; Run next always uses Auto")
        r = api("POST", f"/api/projects/{project_at(main_checkout())['id']}/run-next")
        print_run(r["task_id"], r)
    elif args.target.isdecimal():
        task_id = int(args.target)
        body = {"account_id": account_id(args.account)} if args.account is not None else None
        print_run(task_id, api("POST", f"/api/tasks/{task_id}/run", body))
    else:
        args.usage_error(f"target must be a task id or next, not {args.target!r}")


def automation_run(args):
    """102 AC20, AC21: `fctl automation run <id>` starts an automation by hand; `--account` as `fctl run`'s,
    else Auto with no body."""
    body = {"account_id": account_id(args.account)} if args.account is not None else None
    print_automation_run(args.id, api("POST", f"/api/factories/{args.id}/run", body))
