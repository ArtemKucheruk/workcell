import os
import urllib.parse

from ..client import api
from ..git import default_branch, git, main_checkout


def connect(args):
    main = main_checkout()
    body = {
        "path": main,
        "workspace": args.workspace,
        "name": os.path.basename(main),
        "remote_url": git("-C", main, "remote", "get-url", "origin"),
        "default_branch": default_branch(main),
        "test_cmd": args.test_cmd,
    }
    project = api("POST", "/api/projects/connect", body)
    print(f"Connected {body['name']} ({args.workspace.strip()}) → {project['url']}")


def project_at(main: str) -> dict:
    """The connected project whose main checkout is `main`; 404 `no project at …` if none."""
    return api("GET", "/api/projects?" + urllib.parse.urlencode({"path": main}))
