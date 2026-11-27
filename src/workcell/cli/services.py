"""098: the platform layer of `fctl service`: the launchd plist and systemd unit templates, the
launchctl/systemctl calls, the repo lookup from the editable install's direct_url.json, and
FCTL_HOME/service.json. Stdlib only (AC5); the subcommands are in commands/service.py."""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
from importlib import metadata
from pathlib import Path
from xml.sax.saxutils import escape

from .output import fail

NAMES = ("backend", "frontend")
HOST = "127.0.0.1"  # 098: never 0.0.0.0 (AC9)
LABELS = {name: f"com.workcell.{name}" for name in NAMES}
UNITS = {name: f"workcell-{name}.service" for name in NAMES}
# 116 Q4: the names before the rename, read only to remove the old services (AC11) and move the data dir (Q2)
OLD_LABELS = {name: f"com.claude-factories.{name}" for name in NAMES}
OLD_UNITS = {name: f"claude-factories-{name}.service" for name in NAMES}
HOME = ".workcell"
OLD_HOME = ".claude-factories"
UNSUPPORTED = ("fctl service runs on macOS (launchd) or Linux (systemd --user); in Docker use docker compose up -d"
               " / docker compose restart")
EDITABLE = "fctl service needs an editable install: uv tool install --editable <your checkout>"
LOG_CAP = 10 * 1024 * 1024  # AC17

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>WorkingDirectory</key>
  <string>{cwd}</string>
  <key>EnvironmentVariables</key>
  <dict>
{env}
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
</dict>
</plist>
"""

UNIT = """[Unit]
Description=Workcell {name}

[Service]
ExecStart={exec_start}
WorkingDirectory={cwd}
{env}
Restart=on-failure
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


def platform() -> str:
    """AC3: darwin or linux, else exit 1 before any subprocess. 028: the image sets FCTL_IN_DOCKER=1."""
    if os.environ.get("FCTL_IN_DOCKER") == "1" or sys.platform not in ("darwin", "linux"):
        fail(UNSUPPORTED)
    return sys.platform


def repo_path() -> Path:
    """AC4: the checkout the editable install runs, from its PEP 610 direct_url.json, so any cwd works."""
    try:
        info = json.loads(metadata.distribution("workcell").read_text("direct_url.json") or "")
    except (metadata.PackageNotFoundError, ValueError):
        fail(EDITABLE)
    url = info.get("url", "") if isinstance(info, dict) else ""
    if not url.startswith("file://") or not (info.get("dir_info") or {}).get("editable"):
        fail(EDITABLE)
    return Path(urllib.parse.unquote(urllib.parse.urlparse(url).path))


def home() -> Path:
    """config.data_dir's rule, repeated: cli/ can't import config (tests/cli/test_architecture.py)."""
    return Path(os.environ.get("FCTL_HOME") or Path.home() / HOME)


def migrate_home():
    """116 Q2: config.migrate_home, repeated for `fctl service install`, which writes service.json and logs
    before the backend ever starts. FCTL_HOME set → nothing; a real old dir and no new one → rename, then
    link the old path to the new one (Q1); both → warn and use the new one (AC8)."""
    if os.environ.get("FCTL_HOME"):
        return
    old, new = Path.home() / OLD_HOME, Path.home() / HOME
    if old.is_symlink() or not old.is_dir():
        return
    if os.path.lexists(new):
        print(f"warning: both {old} and {new} exist; using {new}", file=sys.stderr)
        return
    os.rename(old, new)
    try:
        old.symlink_to(new)
    except OSError as e:
        print(f"warning: moved {old} to {new}, but can't link the old path to it: {e.strerror}", file=sys.stderr)
    print(f"Moved {old} to {new}")


def log_path(name: str) -> Path:
    return home() / "logs" / f"{name}.log"


def state_path() -> Path:
    return home() / "service.json"


def load_state() -> dict:
    """AC14: every subcommand but install needs service.json."""
    try:
        return json.loads(state_path().read_text())
    except FileNotFoundError:
        fail("not installed; run fctl service install")
    except ValueError:
        fail(f"{state_path()} isn't valid JSON; run fctl service install")


def save_state(state: dict):
    state_path().parent.mkdir(parents=True, exist_ok=True)
    state_path().write_text(json.dumps(state, indent=2) + "\n")


def sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def rotate(name: str):
    """AC17. ponytail (Q1): only at an fctl-driven (re)start; a service up for weeks can grow past 10 MB."""
    log = log_path(name)
    if log.is_file() and log.stat().st_size > LOG_CAP:
        os.replace(log, log.with_name(log.name + ".1"))


def program(name: str, state: dict, repo: Path) -> tuple[list[str], dict]:
    """AC6, AC7: the absolute argv and env of one service."""
    ports, bins = state["ports"], state["bins"]
    if name == "backend":
        return [bins["fctl"], "serve", "--host", HOST, "--port", str(ports["backend"])], dict(state["env"])
    return [bins["node"], str(repo / "frontend" / "server.js")], {
        "HOST": HOST,
        "PORT": str(ports["frontend"]),
        "FCTL_API_URL": f"http://{HOST}:{ports['backend']}",
        "PATH": state["env"]["PATH"],
    }


def render_plist(name: str, state: dict, repo: Path) -> str:
    args, env = program(name, state, repo)
    return PLIST.format(
        label=escape(LABELS[name]),
        args="\n".join(f"    <string>{escape(a)}</string>" for a in args),
        cwd=escape(str(repo)),
        env="\n".join(f"    <key>{escape(k)}</key>\n    <string>{escape(v)}</string>" for k, v in env.items()),
        log=escape(str(log_path(name))),
    )


def unit_quote(value: str) -> str:
    """systemd's double-quoted word: backslash and quote escaped, % doubled so no specifier expands."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def render_unit(name: str, state: dict, repo: Path) -> str:
    args, env = program(name, state, repo)
    return UNIT.format(
        name=name,
        exec_start=" ".join(unit_quote(a).replace("$", "$$") for a in args),
        cwd=str(repo).replace("%", "%%"),
        env="\n".join(f"Environment={unit_quote(f'{k}={v}')}" for k, v in env.items()),
        log=str(log_path(name)).replace("%", "%%"),
    )


def service_file(plat: str, name: str) -> Path:
    if plat == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{LABELS[name]}.plist"
    return Path.home() / ".config" / "systemd" / "user" / UNITS[name]


def render(plat: str, name: str, state: dict, repo: Path) -> str:
    return (render_plist if plat == "darwin" else render_unit)(name, state, repo)


def call(*argv: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run launchctl/systemctl/lsof/ps; a failure with check exits 1 with the tool's stderr."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True)
    except OSError as e:
        if check:
            fail(f"can't run {argv[0]}: {e.strerror}")
        return subprocess.CompletedProcess(argv, 127, "", "")
    if check and r.returncode:
        fail(f"{' '.join(argv[:3])} failed: {(r.stderr or r.stdout).strip() or f'exit {r.returncode}'}")
    return r


def domain() -> str:
    return f"gui/{os.getuid()}"


def target(name: str) -> str:
    return f"{domain()}/{LABELS[name]}"


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return call("systemctl", "--user", *args, check=check)


def launchd_print(name: str) -> subprocess.CompletedProcess:
    return call("launchctl", "print", target(name), check=False)


def loaded(name: str) -> bool:
    """launchd only: is the agent bootstrapped (AC15)."""
    return launchd_print(name).returncode == 0


def pid(plat: str, name: str) -> int | None:
    """AC26: the running process, or None."""
    if plat == "darwin":
        r = launchd_print(name)
        m = re.search(r"^\s*pid = (\d+)", r.stdout, re.M) if r.returncode == 0 else None
    else:
        r = systemctl("show", "-p", "MainPID", "--value", UNITS[name], check=False)
        m = re.fullmatch(r"\s*(\d+)\s*", r.stdout) if r.returncode == 0 else None
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def load(plat: str, name: str):
    """darwin: bootstrap the agent, AC12/AC15."""
    call("launchctl", "bootstrap", domain(), str(service_file(plat, name)))


def install_units(plat: str, names: tuple):
    """AC12: (re)load each written file, backend first."""
    if plat == "darwin":
        for name in names:
            call("launchctl", "bootout", target(name), check=False)
            load(plat, name)
    else:
        systemctl("daemon-reload")
        for name in names:
            systemctl("enable", "--now", UNITS[name])


def remove_units(plat: str, names: tuple):
    """AC13: stop, then delete the files."""
    for name in names:
        if plat == "darwin":
            call("launchctl", "bootout", target(name), check=False)
        else:
            systemctl("disable", "--now", UNITS[name], check=False)
        service_file(plat, name).unlink(missing_ok=True)
    if plat == "linux":
        systemctl("daemon-reload")


def remove_old_units(plat: str):
    """116 AC11: stop and delete the services installed under the old names, so two backends never fight
    over the port. Only where the old file exists; none → no old-name command runs. lexists, so a dangling
    symlinked unit is removed too."""
    removed = False
    for name in NAMES:
        if plat == "darwin":
            path = Path.home() / "Library" / "LaunchAgents" / f"{OLD_LABELS[name]}.plist"
            if os.path.lexists(path):
                call("launchctl", "bootout", f"{domain()}/{OLD_LABELS[name]}", check=False)
        else:
            path = Path.home() / ".config" / "systemd" / "user" / OLD_UNITS[name]
            if os.path.lexists(path):
                systemctl("disable", "--now", OLD_UNITS[name], check=False)
        if os.path.lexists(path):
            path.unlink()
            removed = True
            print(f"Removed the old service {path}")
    if removed and plat == "linux":
        systemctl("daemon-reload")


def start(plat: str, names: list):
    """AC15: launchd kickstarts a loaded agent, bootstraps one that isn't."""
    if plat == "darwin":
        for name in names:
            if loaded(name):
                call("launchctl", "kickstart", target(name))
            else:
                load(plat, name)
    else:
        systemctl("start", *(UNITS[n] for n in names))


def stop(plat: str, names: list):
    """AC15: bootout unloads (a missing agent is already stopped); the plist stays, so login loads it again."""
    if plat == "darwin":
        for name in names:
            call("launchctl", "bootout", target(name), check=False)
    else:
        systemctl("stop", *(UNITS[n] for n in names))


def restart(plat: str, names: list):
    if plat == "darwin":
        for name in names:
            if loaded(name):
                call("launchctl", "kickstart", "-k", target(name))
            else:
                load(plat, name)
    else:
        systemctl("restart", *(UNITS[n] for n in names))
