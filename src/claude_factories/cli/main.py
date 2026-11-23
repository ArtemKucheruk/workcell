import argparse
from pathlib import Path

from .commands import service
from .commands.agent import DECISIONS, REVIEWERS, STAGES, comment, decide, round_status, show, spec, stage, verdict
from .commands.projects import connect, context, context_set, import_factory
from .commands.review import approve, rework
from .commands.runs import automation_run, run
from .commands.submit import diff, submit
from .commands.tasks import export, import_bundle, task_add, task_block, task_delete, task_ids
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

    print(f"Claude Factories → http://{args.host}:{args.port} (data: {data_dir()})", flush=True)
    uvicorn.run(create_app(port=args.port), host=args.host, port=args.port)  # 104 Q4: the scheduler's FCTL_URL


def seed(args):
    """038: demo data straight into an empty FCTL_HOME. No HTTP, so it works with nothing serving."""
    from ..adapters.git import SubprocessGit  # like serve's: the app's modules stay out of every other command
    from ..config import data_dir
    from ..db import init
    from ..domain.errors import DomainError
    from ..handlers.seed import seed as seed_demo
    from ..server.deps import transaction

    init()
    try:
        made = seed_demo(transaction, SubprocessGit())
    except DomainError as e:  # a refusal, or a git failure: no rows written
        fail(e.detail)
    print(f"Seeded {data_dir()}: {made['workspaces']} workspaces, {made['projects']} projects,"
          f" {made['tasks']} tasks, {made['runs']} runs")


def add_service(commands):
    """098 AC1, AC2: `fctl service <sub>`; the group itself has no func, so fctl.md has one section per sub."""
    p = commands.add_parser("service", help="run the backend and frontend as user services (launchd / systemd)")
    subs = p.add_subparsers(dest="service_command", required=True)
    which = {"nargs": "?", "choices": ("backend", "frontend"), "help": "only this service (default: both)"}
    force = {"action": "store_true", "help": "go on even if runs are active; the backend's restart stops them"}
    p = subs.add_parser("install", help="write and load both services: start at login, restart on crash")
    p.add_argument("--backend-port", type=int, default=4545, help="the backend's port (default: 4545)")
    p.add_argument("--frontend-port", type=int, default=3000, help="the frontend's port (default: 3000)")
    p.set_defaults(func=service.install)
    p = subs.add_parser("uninstall", help="stop and remove both services; the logs stay")
    p.add_argument("--force", **force)
    p.set_defaults(func=service.uninstall)
    p = subs.add_parser("start", help="start both services, or one")
    p.add_argument("which", **which)
    p.set_defaults(func=service.start)
    for name, func, help_text in (("stop", service.stop, "stop both services, or one"),
                                  ("restart", service.restart, "restart both services, or one")):
        p = subs.add_parser(name, help=help_text)
        p.add_argument("which", **which)
        p.add_argument("--force", **force)
        p.set_defaults(func=func)
    p = subs.add_parser("reload", help="after a pull or merge: npm ci if the lockfile changed, build, restart both")
    p.add_argument("--force", **force)
    p.set_defaults(func=service.reload)
    p = subs.add_parser("status", help="each service's pid, port, uptime, URL, and code version, and active runs")
    p.set_defaults(func=service.status)
    p = subs.add_parser("logs", help="print the end of the services' logs")
    p.add_argument("which", **which)
    p.add_argument("-f", "--follow", action="store_true", help="keep printing new lines (tail -f)")
    p.add_argument("-n", type=int, default=50, metavar="N", help="how many lines (default: 50)")
    p.set_defaults(func=service.logs)


def build_parser() -> argparse.ArgumentParser:
    """Every command and its flags. 029 Q11: tests/test_fctl_md.py walks it against fctl.md."""
    parser = argparse.ArgumentParser(prog="fctl", description="Claude Factories CLI.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("serve", help="start the app's backend")
    p.add_argument("--host", default="127.0.0.1", help="address to bind (default: 127.0.0.1; 0.0.0.0 is for the container)")
    p.add_argument("--port", type=int, default=4545, help="port to listen on (default: 4545)")
    p.set_defaults(func=serve)
    add_service(commands)
    p = commands.add_parser("setup", help="write the /factory-connect and /factory-submit skills to ~/.claude")
    p.set_defaults(func=setup)
    p = commands.add_parser("seed", help="fill an empty FCTL_HOME with demo workspaces, projects, and tasks")
    p.set_defaults(func=seed)
    p = commands.add_parser("connect", help="register the current git repo as a project; syncs its factory/ files if any")
    p.add_argument("--workspace", required=True, help="workspace to put it in (created if new)")
    p.add_argument("--test-cmd", help="the repo's test command, e.g. \"pytest -q\"")
    p.set_defaults(func=connect)
    p = commands.add_parser("context", help="print the current repo's project context; `set` saves it")
    context_commands = p.add_subparsers(dest="context_command")
    p.set_defaults(func=context)
    p = context_commands.add_parser("set", help="save the current repo's project context (stdin)")
    p.set_defaults(func=context_set)
    p = commands.add_parser("import-factory", help="import this repo's factory/ jobs and backlog.md lines as tasks")
    p.add_argument("--job", help="only this board.json job, e.g. 014-run-ui (default: every job, then backlog.md)")
    p.set_defaults(func=import_factory)
    p = commands.add_parser("export", help="write a task as a zip bundle another app can import")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("-o", "--output", metavar="FILE", help="the file to write (default: task-<id>.zip here)")
    p.add_argument("--transcripts", action="store_true",
                   help="include its agent transcripts, which can hold paths, env, and secrets")
    p.set_defaults(func=export)
    p = commands.add_parser("import", help="import a task bundle into the current repo's project")
    p.add_argument("file", help="the bundle, e.g. task-12.zip")
    p.set_defaults(func=import_bundle)
    p = commands.add_parser("task", help="manage tasks")
    task_commands = p.add_subparsers(dest="task_command", required=True)
    p = task_commands.add_parser("add", help="add a task to the bottom of the current repo's Backlog")
    p.add_argument("title", help='the task\'s title, e.g. "Rate-limit login endpoint"')
    p.add_argument("--description", metavar="TEXT", help='its markdown description; "-" reads it from stdin')
    p.add_argument("--blocked-by", metavar="IDS", type=task_ids,
                   help="the tasks it waits on, comma-separated, e.g. 12,14")
    p.add_argument("--run", action="store_true", help="then start a factory run on it")
    p.set_defaults(func=task_add)
    for name, method, help_text in (("block", "PUT", "make a task wait on another task of its project"),
                                    ("unblock", "DELETE", "stop a task waiting on another task")):
        p = task_commands.add_parser(name, help=help_text)
        p.add_argument("id", type=int, help="the task that waits")
        p.add_argument("--by", type=int, required=True, help="the task it waits on")
        p.set_defaults(func=task_block, method=method)
    p = task_commands.add_parser("delete", help="delete a task and its runs, rounds, and records from the app")
    p.add_argument("id", type=int, help="the task")
    p.add_argument("--yes", action="store_true", help="don't ask first; needed off a terminal")
    p.set_defaults(func=task_delete)
    p = commands.add_parser("run", help="start a factory run on a task, or on the top of this repo's Backlog")
    p.add_argument("target", help='a task id, or "next"')
    p.add_argument("--account", metavar="ID|EMAIL",
                   help="the Claude account to run in, by id or email (default: Auto; not with next)")
    p.set_defaults(func=run, usage_error=p.error)
    p = commands.add_parser("automation", help="run an automation: a design that works on the repo, with no task")
    automation_commands = p.add_subparsers(dest="automation_command", required=True)
    p = automation_commands.add_parser("run", help="start an automation by hand, in a fresh worktree")
    p.add_argument("id", type=int, help="the automation, its id on the Workflows page")
    p.add_argument("--account", metavar="ID|EMAIL",
                   help="the Claude account to run in, by id or email (default: Auto)")
    p.set_defaults(func=automation_run)
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
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)
