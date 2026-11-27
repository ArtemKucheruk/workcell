import sys

from ..client import api
from ..output import fail, stdin_text

# The app's values, repeated here for argparse `choices`: this module must not import app.py.
REVIEWERS = ("security", "ux", "ui", "code")
STAGES = ("spec", "build", "agent_review", "approval", "rework", "human_review", "escalated")
DECISIONS = ("APPROVE", "ESCALATE")  # the approver's; mine go through `fctl approve` and `fctl rework`


def show(args):
    query = f"?round={args.round}" if args.round is not None else "?feedback=1" if args.feedback else ""
    sys.stdout.write(api("GET", f"/api/tasks/{args.id}/context{query}"))


def spec(args):
    text = stdin_text()
    if not text.strip():  # Q9: a hand-typed `fctl spec 12` can't wipe the spec
        fail("spec is empty; pass it on stdin")
    api("PATCH", f"/api/tasks/{args.id}", {"spec_md": text})
    print(f"Spec saved on #{args.id}")


def stage(args):
    task = api("PATCH", f"/api/tasks/{args.id}", {"stage": args.stage})
    print(f"#{args.id}: {task['status']} · {task['stage']}")


def verdict(args):
    body = {"verdict": args.verdict, "body_md": stdin_text()}
    r = api("PUT", f"/api/tasks/{args.id}/rounds/latest/verdicts/{args.reviewer}", body)
    print(f"Round {r['round']} of #{args.id}: {r['reviewer']}={r['verdict']} ({r['complete']})")


def comment(args):
    body = {"round": "latest", "author": args.reviewer, "path": args.path, "line": args.line, "side": "new",
            "body_md": stdin_text()}
    r = api("POST", f"/api/tasks/{args.id}/comments", body)
    print(f"Comment #{r['id']} on #{args.id} {args.path}:{args.line}")


def decide(args):
    r = api("POST", f"/api/tasks/{args.id}/decision", {"decision": args.decision, "body_md": stdin_text()})
    print(f"Decision #{r['id']} on #{args.id}: {args.decision}")


def round_status(args):
    """docs/claude-code.md §7.2: the latest round's verdicts, for the orchestrator's WAIT FOR ALL."""
    rounds = api("GET", f"/api/tasks/{args.id}")["rounds"]
    if not rounds:
        fail(f"#{args.id} has no rounds")
    last = rounds[-1]
    verdicts = " ".join(f"{who}={last['verdicts'][who]}" for who in REVIEWERS)
    done = sum(last["verdicts"][who] != "pending" for who in REVIEWERS)
    print(f"round {last['n']}: {verdicts} ({done}/{len(REVIEWERS)})")
