from ..client import api


def approve(args):
    """docs/claude-code.md §7.2: my Approve; prints the commands to commit it myself (Q11)."""
    r = api("POST", f"/api/tasks/{args.id}/approve", {"body_md": ""})
    print(f"#{args.id}: {r['status']}\n{r['commit_hint']}")


def rework(args):
    """§7.2: my Request changes with its note."""
    r = api("POST", f"/api/tasks/{args.id}/request-changes", {"body_md": args.note})
    print(f"#{args.id}: {r['status']} · {r['stage']}")
