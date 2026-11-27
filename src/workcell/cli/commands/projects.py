import os
import sys
import urllib.parse

from ..client import api
from ..git import default_branch, git, main_checkout
from ..output import fail, stdin_text


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
    # 058 Q13: only for the files a sync reads, so an unrelated factory/ folder doesn't fail connect
    if any(os.path.isfile(os.path.join(main, "factory", name)) for name in ("board.json", "backlog.md")):
        out = api("POST", f"/api/projects/{project['id']}/import-factory", {})
        new = sum(j["created"] for j in out["imported"])
        print(f"Synced factory/: {new} new, {len(out['imported']) - new} updated, {out['skipped']} skipped")


def project_at(main: str) -> dict:
    """The connected project whose main checkout is `main`; 404 `no project at …` if none."""
    return api("GET", "/api/projects?" + urllib.parse.urlencode({"path": main}))


def context(args):
    """033 Q5: the stored context exactly; an empty one prints nothing."""
    project = project_at(main_checkout())
    sys.stdout.write(api("GET", f"/api/projects/{project['id']}/context")["context_md"])


def context_set(args):
    text = stdin_text()
    if not text.strip():  # 033 Q5: a hand-typed `fctl context set` can't wipe the context; the Context page can
        fail("context is empty; pass it on stdin")
    project = project_at(main_checkout())
    saved = api("PUT", f"/api/projects/{project['id']}/context", {"context_md": text})
    print(f"Context saved on {project['name']} ({saved['bytes']} bytes)")


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def import_factory(args):
    """031 Q1: one line per imported job. 058 Q14: then backlog.md's skipped lines."""
    project = project_at(main_checkout())
    body = {} if args.job is None else {"job": args.job}
    out = api("POST", f"/api/projects/{project['id']}/import-factory", body)
    for j in out["imported"]:
        print(f"Imported {j['job']} → #{j['task_id']} ({'new' if j['created'] else 'updated'},"
              f" {plural(j['rounds'], 'round')}, {plural(j['transcripts'], 'transcript')})")
    if out["skipped"]:
        print(f"Skipped {plural(out['skipped'], 'line')} in factory/backlog.md")
    elif not out["imported"]:
        print("No jobs in factory/")
