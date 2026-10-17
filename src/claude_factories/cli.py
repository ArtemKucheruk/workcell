"""fctl, the Claude Factories CLI. Stdlib only at import time, so agents' calls start fast."""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:4545"


def _fail(message: str):
    print(f"fctl: {message}", file=sys.stderr)
    raise SystemExit(1)


def api(method: str, path: str, body=None):
    """Call the app. Returns parsed JSON or text; on any failure prints to stderr and exits 1."""
    base = os.environ.get("FCTL_URL") or DEFAULT_URL
    headers = {"X-Requested-By": "fctl"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if resp.headers.get_content_type() == "application/json":
                return json.loads(raw)
            return raw.decode()
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            detail = json.loads(text)["detail"]
        except (ValueError, KeyError, TypeError):
            detail = text or e.reason
        if not isinstance(detail, str):
            detail = json.dumps(detail)
        _fail(f"{e.code} {detail}")
    except OSError:  # URLError (refused, DNS) and resets mid-response
        _fail(f'can\'t reach {base} — is "fctl serve" running?')


def _git(*args: str) -> str | None:
    """Run git; its stripped stdout, or None if it fails."""
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main_checkout() -> str:
    """docs/claude-code.md §7.4 step 1: the main checkout, also from a worktree or a subdirectory."""
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and os.path.basename(common) == ".git":
        root = os.path.dirname(common)
    else:  # a bare repo or a separate git dir
        root = common and _git("rev-parse", "--show-toplevel")
    if not root:
        _fail(f"not inside a git repository: {os.getcwd()}")
    return os.path.realpath(root)


def default_branch(main: str) -> str:
    """origin/HEAD, else the main checkout's current branch (not the worktree's)."""
    ref = _git("-C", main, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    branch = ref.removeprefix("origin/") if ref else _git("-C", main, "branch", "--show-current")
    if not branch:
        _fail("can't tell the default branch: no origin/HEAD and HEAD is detached")
    return branch


def connect(args):
    main = main_checkout()
    body = {
        "path": main,
        "workspace": args.workspace,
        "name": os.path.basename(main),
        "remote_url": _git("-C", main, "remote", "get-url", "origin"),
        "default_branch": default_branch(main),
        "test_cmd": args.test_cmd,
    }
    project = api("POST", "/api/projects/connect", body)
    print(f"Connected {body['name']} ({args.workspace.strip()}) → {project['url']}")


def serve(args):
    import uvicorn  # heavy imports stay out of every other command

    from . import db
    from .app import app

    print(f"Claude Factories → http://127.0.0.1:{args.port} (data: {db.data_dir()})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fctl", description="Claude Factories CLI.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("serve", help="start the app on 127.0.0.1")
    p.add_argument("--port", type=int, default=4545, help="port to listen on (default: 4545)")
    p.set_defaults(func=serve)
    p = commands.add_parser("connect", help="register the current git repo as a project")
    p.add_argument("--workspace", required=True, help="workspace to put it in (created if new)")
    p.add_argument("--test-cmd", help="the repo's test command, e.g. \"pytest -q\"")
    p.set_defaults(func=connect)
    args = parser.parse_args(argv)
    args.func(args)
