"""098: `fctl service …`, the backend and the frontend as user services (launchd on macOS, systemd --user on
Linux). The templates and the platform calls live in cli/services.py. Reference: src/workcell/fctl.md."""

import collections
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request

from .. import services
from ..git import default_branch, git
from ..output import fail

REQUIRED = ("fctl", "node", "npm", "git")  # Q9: the services can't start without these
OPTIONAL = ("claude", "uv", "gh", "wt")  # Q9: runs and reviewers need them later
PY_FILES = ("pyproject.toml", "uv.lock")  # AC24
LOCK = "package-lock.json"
PORT_FLAGS = {"backend": "--backend-port", "frontend": "--frontend-port"}


def targets(args) -> list[str]:
    """AC2: `which`, or both."""
    return [args.which] if getattr(args, "which", None) else list(services.NAMES)


def url(port: int) -> str:
    return f"http://{services.HOST}:{port}"


def active_runs(state: dict) -> list[dict] | None:
    """AC18, AC27: the running runs from GET /api/pages/agents; None when the backend doesn't answer (AC20)."""
    try:
        with urllib.request.urlopen(url(state["ports"]["backend"]) + "/api/pages/agents", timeout=3) as r:
            runs = json.loads(r.read())["running"]
        return [run for run in runs if isinstance(run, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def run_list(runs: list[dict]) -> str:
    return ", ".join(f"run #{r['id']} on #{r['task_id']}" for r in runs)


def guard(state: dict, force: bool, names: list[str]):
    """AC18-AC21: the backend's shutdown stops every run, so refuse while one is active, unless --force.
    Q4: frontend-only targets skip it. Q5: a backend that doesn't answer has no runs to protect."""
    if "backend" not in names:
        return
    runs = active_runs(state) or []
    if not runs:
        return
    if force:
        print(f"Stopping active runs: {run_list(runs)}")
        return
    verb = "is active; wait, stop it" if len(runs) == 1 else "are active; wait, stop them"
    fail(f"{run_list(runs)} {verb} in the app, or pass --force")


def npm(state: dict, repo, *step: str):
    """AC22, AC23: npm's output goes to the terminal, so the error points at it."""
    try:
        code = subprocess.run([state["bins"]["npm"], "--prefix", str(repo / "frontend"), *step]).returncode
    except OSError:
        code = 1
    if code:
        fail(f"npm {' '.join(step)} failed; see the output above")


def npm_ci(state: dict, repo):
    """Q3: remember the lockfile it installed, so reload knows when to run it again."""
    npm(state, repo, "ci")
    state.setdefault("hashes", {})[LOCK] = services.sha256(repo / "frontend" / LOCK)
    services.save_state(state)


def ensure_built(state: dict, repo):
    """AC11: no frontend/dist/index.html → ci (without node_modules), then build."""
    if (repo / "frontend" / "dist" / "index.html").is_file():
        return
    if not (repo / "frontend" / "node_modules").is_dir():
        npm_ci(state, repo)
    npm(state, repo, "run", "build")


def mark_served(state: dict, repo, names: list[str]):
    """AC25: the commit each (re)started service serves, for status."""
    sha = git("-C", str(repo), "rev-parse", "--short", "HEAD")
    for name in names:
        state.setdefault("served", {})[name] = sha
    services.save_state(state)


def port_holder(port: int) -> str | None:
    """AC16: `pid N (command)` of what listens on port, `another process` without lsof, or None."""
    if shutil.which("lsof") is None:
        with socket.socket() as s:
            s.settimeout(0.5)
            return "another process" if s.connect_ex((services.HOST, port)) == 0 else None
    pids = services.call("lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t", check=False).stdout.split()
    if not pids:
        return None
    command = services.call("ps", "-o", "comm=", "-p", pids[0], check=False).stdout.strip()
    return f"pid {pids[0]} ({command})" if command else f"pid {pids[0]}"


def check_ports(state: dict, names: list[str]):
    for name in names:
        port = state["ports"][name]
        if holder := port_holder(port):
            fail(f"port {port} is taken by {holder}; stop it, or reinstall with {PORT_FLAGS[name]}")


def restart_services(plat: str, state: dict, repo, names: list[str]):
    """restart's and reload's last step, after the guard."""
    for name in names:
        services.rotate(name)
    services.restart(plat, names)
    mark_served(state, repo, names)
    for name in names:
        print(f"Restarted {name} → {url(state['ports'][name])}")


def previous_state() -> dict:
    try:
        return json.loads(services.state_path().read_text())
    except (OSError, ValueError):
        return {}


def install(args):
    """AC10-AC12: capture the binaries and env, build the frontend if needed, write and load both services."""
    plat = services.platform()
    repo = services.repo_path()
    bins = {}
    for name in REQUIRED + OPTIONAL:
        found = shutil.which(name)
        if found:
            bins[name] = os.path.abspath(found)
        elif name in REQUIRED:
            fail(f"{name} not found on PATH")
        else:
            print(f"warning: {name} not found on PATH; runs and reviewers need it", file=sys.stderr)
    dirs = [os.path.dirname(p) for p in bins.values()] + os.environ.get("PATH", "").split(os.pathsep)
    env = {"PATH": os.pathsep.join(dict.fromkeys(d for d in dirs if d))}
    env |= {k: os.environ[k] for k in ("FCTL_HOME", "CLAUDE_CONFIG_DIR") if os.environ.get(k)}
    old = previous_state()  # Q7: keeps the lockfile hash, so a reinstall doesn't force npm ci
    state = {
        "repo": str(repo),
        "ports": {"backend": args.backend_port, "frontend": args.frontend_port},
        "bins": bins,
        "env": env,
        "hashes": {**old.get("hashes", {}), **{f: services.sha256(repo / f) for f in PY_FILES}},
        "served": old.get("served", {}),
    }
    services.save_state(state)
    ensure_built(state, repo)
    services.log_path("backend").parent.mkdir(parents=True, exist_ok=True)
    for name in services.NAMES:
        path = services.service_file(plat, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(services.render(plat, name, state, repo))
        print(f"Wrote {path}")
        services.rotate(name)
    services.install_units(plat, services.NAMES)
    mark_served(state, repo, list(services.NAMES))
    for name in services.NAMES:
        print(f"Started {name} → {url(state['ports'][name])} (log: {services.log_path(name)})")
    if args.backend_port != 4545:  # Q8
        print(f"export FCTL_URL={url(args.backend_port)}")


def uninstall(args):
    """AC13: stop and remove both services and service.json; the logs stay."""
    plat = services.platform()
    state = services.load_state()
    guard(state, args.force, list(services.NAMES))
    services.remove_units(plat, services.NAMES)
    services.state_path().unlink(missing_ok=True)
    print(f"Uninstalled backend and frontend; logs kept in {services.log_path('backend').parent}")


def start(args):
    """AC15, AC16: start what isn't running, after checking its port is free."""
    plat = services.platform()
    state = services.load_state()
    repo = services.repo_path()
    names = targets(args)
    if "frontend" in names:
        ensure_built(state, repo)
    pids = {name: services.pid(plat, name) for name in names}
    down = [name for name in names if pids[name] is None]
    check_ports(state, down)
    for name in down:
        services.rotate(name)
    if down:
        services.start(plat, down)
        mark_served(state, repo, down)
    for name in names:
        if pids[name] is None:
            print(f"Started {name} → {url(state['ports'][name])}")
        else:
            print(f"{name} is already running (pid {pids[name]})")


def stop(args):
    plat = services.platform()
    state = services.load_state()
    names = targets(args)
    guard(state, args.force, names)
    services.stop(plat, names)
    for name in names:
        print(f"Stopped {name}")


def restart(args):
    plat = services.platform()
    state = services.load_state()
    repo = services.repo_path()
    names = targets(args)
    guard(state, args.force, names)
    restart_services(plat, state, repo, names)


def reload(args):
    """AC22-AC24: after a pull or merge: npm ci if the lockfile changed, build, restart both."""
    plat = services.platform()
    state = services.load_state()
    repo = services.repo_path()
    guard(state, args.force, list(services.NAMES))
    hashes = state.setdefault("hashes", {})
    lock = services.sha256(repo / "frontend" / LOCK)
    if hashes.get(LOCK) is None or hashes[LOCK] != lock or not (repo / "frontend" / "node_modules").is_dir():
        npm_ci(state, repo)
    py = {f: services.sha256(repo / f) for f in PY_FILES}
    if any(hashes.get(f) != h for f, h in py.items()):  # Q2: only the hint; fctl can't reinstall itself safely
        print(f"Python dependencies changed; run: uv tool install --editable --reinstall {repo}")
        hashes.update(py)
        services.save_state(state)
    npm(state, repo, "run", "build")
    restart_services(plat, state, repo, list(services.NAMES))


def uptime(pid: int) -> str:
    return services.call("ps", "-o", "etime=", "-p", str(pid), check=False).stdout.strip() or "-"


def status(args):
    """AC26-AC28. Q6: main is the local default branch, with no fetch."""
    plat = services.platform()
    state = services.load_state()
    repo = services.repo_path()
    main = git("-C", str(repo), "rev-parse", "--short", default_branch(str(repo)))
    for i, name in enumerate(services.NAMES):
        pid = services.pid(plat, name)
        port = state["ports"][name]
        served = state.get("served", {}).get(name)
        if i:
            print()
        print(f"{name}: {'running' if pid else 'stopped'}")
        print(f"  pid: {pid or '-'}")
        print(f"  port: {port}")
        print(f"  uptime: {uptime(pid) if pid else '-'}")
        print(f"  url: {url(port)}")
        print(f"  code: {served or 'unknown'}, main {main or 'unknown'}, "
              f"{'current' if served and served == main else 'stale'}")
    runs = active_runs(state)
    if runs is None:
        listed = "unknown (backend not answering)"
    else:
        listed = ", ".join(f"run #{r['id']} on #{r['task_id']} ({r.get('title', '')})" for r in runs) or "none"
    print(f"\nactive runs: {listed}")
    for name, path in state.get("bins", {}).items():
        if not os.path.exists(path):
            print(f"warning: {name} moved: {path} no longer exists; run fctl service install", file=sys.stderr)


def logs(args):
    """AC29, AC30."""
    services.platform()
    services.load_state()
    paths = [services.log_path(name) for name in targets(args)]
    found = [p for p in paths if p.is_file()]
    for path in paths:
        if path not in found:
            print(f"no log yet: {path}")
        elif not args.follow:
            with open(path, encoding="utf-8", errors="replace") as f:
                tail = collections.deque(f, maxlen=max(args.n, 0))
            print(f"==> {path} <==")
            sys.stdout.writelines(tail)
    if args.follow and found:
        sys.stdout.flush()
        os.execvp("tail", ["tail", "-n", str(max(args.n, 0)), "-f", *map(str, found)])
