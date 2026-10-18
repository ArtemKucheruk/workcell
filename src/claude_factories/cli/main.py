import argparse
from pathlib import Path

from .commands.agent import DECISIONS, REVIEWERS, STAGES, comment, decide, round_status, show, spec, stage, verdict
from .commands.projects import connect
from .commands.review import approve, rework
from .commands.runs import run
from .commands.submit import diff, submit
from .commands.tasks import task_add
from .output import fail

SKILLS = ("factory-connect", "factory-submit")  # docs/claude-code.md §7.1, shipped in global_skills/


def setup(args):
    """docs/claude-code.md §7.1: install the global skills. fctl owns SKILL.md and overwrites it;
    other files in those folders stay (Q2). No HTTP. Stops at the first failed write (Q4)."""
    for name in SKILLS:
        content = (Path(__file__).parent.parent / "global_skills" / name / "SKILL.md").read_bytes()
        dest = Path.home() / ".claude" / "skills" / name / "SKILL.md"  # Q1: CLAUDE_CONFIG_DIR ignored
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        except OSError as e:
            fail(f"can't write {dest}: {e.strerror}")
        print(f"Wrote {dest}")


def serve(args):
    import uvicorn  # heavy imports stay out of every other command

    from ..config import data_dir
    from ..server.app import create_app

    print(f"Claude Factories → http://127.0.0.1:{args.port} (data: {data_dir()})", flush=True)
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fctl", description="Claude Factories CLI.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("serve", help="start the app on 127.0.0.1")
    p.add_argument("--port", type=int, default=4545, help="port to listen on (default: 4545)")
    p.set_defaults(func=serve)
    p = commands.add_parser("setup", help="write the /factory-connect and /factory-submit skills to ~/.claude")
    p.set_defaults(func=setup)
    p = commands.add_parser("connect", help="register the current git repo as a project")
    p.add_argument("--workspace", required=True, help="workspace to put it in (created if new)")
    p.add_argument("--test-cmd", help="the repo's test command, e.g. \"pytest -q\"")
    p.set_defaults(func=connect)
    p = commands.add_parser("task", help="manage tasks")
    task_commands = p.add_subparsers(dest="task_command", required=True)
    p = task_commands.add_parser("add", help="add a task to the bottom of the current repo's Backlog")
    p.add_argument("title", help='the task\'s title, e.g. "Rate-limit login endpoint"')
    p.add_argument("--run", action="store_true", help="then start a factory run on it")
    p.set_defaults(func=task_add)
    p = commands.add_parser("run", help="start a factory run on a task, or on the top of this repo's Backlog")
    p.add_argument("target", help='a task id, or "next"')
    p.set_defaults(func=run, usage_error=p.error)
    p = commands.add_parser("submit", help="send this tree's changes for review, as a new task or a round")
    p.add_argument("id", nargs="?", type=int, help="the task to add a round to (stdin: build notes)")
    p.add_argument("--new", action="store_true", help="create a task straight in Review (stdin: description)")
    p.add_argument("--title", help="the new task's title, with --new")
    p.set_defaults(func=submit, usage_error=p.error)
    p = commands.add_parser("diff", help="print a round's full patch")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("--round", type=int, help="the round's number (default: the latest)")
    p.set_defaults(func=diff)
    p = commands.add_parser("show", help="print a task as markdown: everything, one round, or my feedback")
    p.add_argument("id", type=int, help="the task")
    view = p.add_mutually_exclusive_group()
    view.add_argument("--round", type=int, help="only this round")
    view.add_argument("--feedback", action="store_true", help="only my latest change request")
    p.set_defaults(func=show)
    p = commands.add_parser("spec", help="save a task's spec (stdin)")
    p.add_argument("id", type=int, help="the task")
    p.set_defaults(func=spec)
    p = commands.add_parser("stage", help="move a task to a stage (orchestrator)")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("stage", choices=STAGES, help="the stage to move to")
    p.set_defaults(func=stage)
    p = commands.add_parser("verdict", help="post a reviewer's verdict on the latest round (stdin: findings)")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("reviewer", choices=REVIEWERS, help="the reviewer posting it")
    p.add_argument("verdict", choices=("PASS", "CHANGES"), help="the verdict")
    p.set_defaults(func=verdict)
    p = commands.add_parser("comment", help="post a reviewer's line comment on the latest round (stdin)")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("reviewer", choices=REVIEWERS, help="the reviewer posting it")
    p.add_argument("--path", required=True, help="a file in the round's diff")
    p.add_argument("--line", type=int, required=True, help="the line in the new file")
    p.set_defaults(func=comment)
    p = commands.add_parser("decide", help="post the approver's decision on the latest round (stdin)")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("decision", choices=DECISIONS, help="the decision")
    p.set_defaults(func=decide)
    p = commands.add_parser("round", help="print the latest round's verdicts, e.g. (3/4)")
    p.add_argument("id", type=int, help="the task")
    p.set_defaults(func=round_status)
    p = commands.add_parser("approve", help="approve a task in review: done, then print the commit commands")
    p.add_argument("id", type=int, help="the task")
    p.set_defaults(func=approve)
    p = commands.add_parser("rework", help="request changes on a task in review: in_progress · rework")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("note", help='what should change, e.g. "Make the limit configurable"')
    p.set_defaults(func=rework)
    args = parser.parse_args(argv)
    args.func(args)
