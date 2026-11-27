import sys

from ..client import api


def approve(args):
    """docs/claude-code.md §7.2: my Approve; prints the commands to commit it myself (Q11)."""
    r = api("POST", f"/api/tasks/{args.id}/approve", {"body_md": ""})
    print(f"#{args.id}: {r['status']}\n{r['commit_hint']}")
    if r.get("plane_warning"):  # 109 AC15: the approve stands; Plane wasn't updated
        print(r["plane_warning"], file=sys.stderr)


def rework(args):
    """§7.2: my Request changes with its note."""
    r = api("POST", f"/api/tasks/{args.id}/request-changes", {"body_md": args.note})
    print(f"#{args.id}: {r['status']} · {r['stage']}")
