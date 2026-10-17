"""fctl, the Claude Factories CLI. Stdlib only at import time, so agents' calls start fast."""

import argparse
import json
import os
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
    args = parser.parse_args(argv)
    args.func(args)
