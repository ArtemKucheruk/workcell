"""098: fctl service. Fake launchctl, systemctl, npm, lsof, ps, fctl, and node on PATH log their argv to
FAKE_LOG; FAKE_RULES gives one its stdout and exit code. HOME and FCTL_HOME are tmp (tests/conftest.py)."""

import json
import os
import plistlib
import shutil
import socket
import sys
from pathlib import Path

import pytest
from conftest import commit, git, write

from workcell.cli import services
from workcell.cli.main import build_parser, main

from ..conftest import reply

FAKE = '''#!PYTHON
import json, os, sys
argv = [os.path.basename(sys.argv[0]), *sys.argv[1:]]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(argv) + "\\n")
rules = os.environ["FAKE_RULES"]
for rule in (json.load(open(rules)) if os.path.exists(rules) else []):
    if argv[0] == rule["argv"][0] and all(token in argv[1:] for token in rule["argv"][1:]):
        sys.stdout.write(rule["out"])
        sys.exit(rule["code"])
'''
FAKES = ("launchctl", "systemctl", "npm", "lsof", "ps", "fctl", "node")
SUBS = ("install", "uninstall", "start", "stop", "restart", "reload", "status", "logs")
DOMAIN = f"gui/{os.getuid()}"
LABEL = {"backend": "com.workcell.backend", "frontend": "com.workcell.frontend"}  # 116 AC10
UNIT = {"backend": "workcell-backend.service", "frontend": "workcell-frontend.service"}
RUN_68 = {"id": 68, "task_id": 92, "title": "Rate-limit login"}
RUN_70 = {"id": 70, "task_id": 95, "title": "Dark mode"}
UNSUPPORTED = ("fctl: fctl service runs on macOS (launchd) or Linux (systemd --user); in Docker use docker compose"
               " up -d / docker compose restart\n")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fctl(*argv):
    main(["service", *argv])


def refused(capsys, *argv) -> str:
    """The stderr of a command that exits 1 (earlier output, e.g. install's, is dropped first)."""
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        fctl(*argv)
    assert e.value.code == 1
    return capsys.readouterr().err


class Svc:
    def __init__(self, tmp_path, repo):
        self.tmp, self.repo, self.bin = tmp_path, repo, tmp_path / "bin"
        self.log, self.rules_file = tmp_path / "fake-log", tmp_path / "fake-rules"
        self.home = Path(os.environ["FCTL_HOME"])
        self.ports = {"backend": free_port(), "frontend": free_port()}

    def rule(self, *argv, out="", code=0):
        rules = json.loads(self.rules_file.read_text()) if self.rules_file.exists() else []
        self.rules_file.write_text(json.dumps([*rules, {"argv": list(argv), "out": out, "code": code}]))

    def calls(self, *tools, skip=("print", "show")) -> list[list[str]]:
        """The fakes' argv, oldest first; by default without the read-only launchctl print / systemctl show."""
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        calls = [c for c in map(json.loads, lines) if not tools or c[0] in tools]
        return [c for c in calls if not (c[0] == "launchctl" and c[1] in skip) and
                not (c[0] == "systemctl" and c[2] in skip)]

    def clear(self):
        self.log.unlink(missing_ok=True)
        self.rules_file.unlink(missing_ok=True)

    def state(self) -> dict:
        return json.loads((self.home / "service.json").read_text())

    def install(self, *extra):
        fctl("install", "--backend-port", str(self.ports["backend"]), "--frontend-port",
             str(self.ports["frontend"]), *extra)
        self.clear()

    def file(self, name) -> Path:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "LaunchAgents" / f"{LABEL[name]}.plist"
        return Path.home() / ".config" / "systemd" / "user" / UNIT[name]

    def logfile(self, name) -> Path:
        return self.home / "logs" / f"{name}.log"

    def not_loaded(self, name):
        self.rule("launchctl", "print", f"{DOMAIN}/{LABEL[name]}", code=113)

    def git_only_path(self, monkeypatch):
        """PATH = the fakes plus a folder holding only git, so no real node, lsof, uv, or gh is found."""
        gitbin = self.tmp / "gitbin"
        gitbin.mkdir(exist_ok=True)
        (gitbin / "git").symlink_to(shutil.which("git"))
        monkeypatch.setenv("PATH", f"{self.bin}{os.pathsep}{gitbin}")
        return gitbin


@pytest.fixture
def svc(tmp_path, repo, monkeypatch):
    s = Svc(tmp_path, repo)
    for name in FAKES:
        (s.bin / name).write_text(FAKE.replace("PYTHON", sys.executable))
        (s.bin / name).chmod(0o755)
    monkeypatch.setenv("FAKE_LOG", str(s.log))
    monkeypatch.setenv("FAKE_RULES", str(s.rules_file))
    commit(repo, {
        "frontend/dist/index.html": "<!doctype html>",
        "frontend/package-lock.json": "{}",
        "frontend/node_modules/.keep": "",
        "frontend/server.js": "",
        "pyproject.toml": "[project]\n",
        "uv.lock": "version = 1\n",
    })
    monkeypatch.setattr(services, "repo_path", lambda: repo)
    monkeypatch.setattr(sys, "platform", "darwin")
    return s


@pytest.fixture(params=["darwin", "linux"])
def plat(request, svc, monkeypatch):
    monkeypatch.setattr(sys, "platform", request.param)
    return request.param


@pytest.fixture
def agents(server, svc):
    """The cli conftest's HTTP server as the backend, answering /api/pages/agents with server.reply."""
    svc.ports["backend"] = server.server_port
    server.reply = reply({"running": [], "recent": []})
    return server


def running(server, *runs):
    server.reply = reply({"running": list(runs), "recent": []})


# Parser and platform


def test_parser_has_the_service_group():  # AC1
    from test_fctl_md import walk

    found = walk(build_parser())
    assert "service" not in found
    assert {f"service {s}" for s in SUBS} <= set(found)
    assert len({found[f"service {s}"].get_default("func") for s in SUBS}) == 8


def test_parser_flags():  # AC2
    parse = build_parser().parse_args
    for sub in ("start", "stop", "restart", "logs"):
        assert parse(["service", sub]).which is None
        assert parse(["service", sub, "frontend"]).which == "frontend"
        with pytest.raises(SystemExit):
            parse(["service", sub, "db"])
    logs = parse(["service", "logs", "backend", "-f", "-n", "7"])
    assert (logs.follow, logs.n) == (True, 7)
    assert (parse(["service", "logs"]).follow, parse(["service", "logs", "--follow"]).n) == (False, 50)
    install = parse(["service", "install"])
    assert (install.backend_port, install.frontend_port) == (4545, 3000)
    assert parse(["service", "install", "--backend-port", "5000", "--frontend-port", "5001"]).frontend_port == 5001
    for sub in ("stop", "restart", "reload", "uninstall"):
        assert parse(["service", sub]).force is False and parse(["service", sub, "--force"]).force is True


@pytest.mark.parametrize("sub", SUBS)
@pytest.mark.parametrize("platform, docker", [("win32", None), ("darwin", "1"), ("linux", "1"), ("cygwin", None)])
def test_unsupported_platform(svc, monkeypatch, capsys, sub, platform, docker):  # AC3
    monkeypatch.setattr(sys, "platform", platform)
    if docker:
        monkeypatch.setenv("FCTL_IN_DOCKER", docker)
    assert refused(capsys, sub) == UNSUPPORTED
    assert svc.calls(skip=()) == []


class Dist:
    def __init__(self, text):
        self.text = text

    def read_text(self, name):
        assert name == "direct_url.json"
        return self.text


def test_repo_path_from_direct_url(monkeypatch, tmp_path):  # AC4
    url = {"url": "file:///home/me/my%20repo", "dir_info": {"editable": True}}
    monkeypatch.setattr(services.metadata, "distribution", lambda name: Dist(json.dumps(url)))
    assert services.repo_path() == Path("/home/me/my repo")


def test_repo_path_reads_the_workcell_distribution(monkeypatch):  # 116 AC3
    url = {"url": "file:///home/me/workcell", "dir_info": {"editable": True}}
    asked = []
    monkeypatch.setattr(services.metadata, "distribution", lambda name: asked.append(name) or Dist(json.dumps(url)))
    assert services.repo_path() == Path("/home/me/workcell")
    assert asked == ["workcell"]


def test_home_defaults_to_workcell(monkeypatch, tmp_path):  # 116 AC4
    monkeypatch.delenv("FCTL_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert services.home() == tmp_path / ".workcell"
    assert services.state_path() == tmp_path / ".workcell" / "service.json"


@pytest.mark.parametrize("text", [
    None,
    json.dumps({"url": "file:///home/me/repo", "dir_info": {}}),
    json.dumps({"url": "file:///home/me/repo", "dir_info": {"editable": False}}),
    json.dumps({"url": "https://github.com/x/y", "vcs_info": {}}),
    "not json",
])
def test_repo_path_needs_editable(monkeypatch, capsys, text):  # AC4
    monkeypatch.setattr(services.metadata, "distribution", lambda name: Dist(text))
    with pytest.raises(SystemExit):
        services.repo_path()
    assert capsys.readouterr().err == (
        "fctl: fctl service needs an editable install: uv tool install --editable <your checkout>\n")


def test_repo_path_not_installed(monkeypatch, capsys):  # AC4
    def missing(name):
        raise services.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(services.metadata, "distribution", missing)
    with pytest.raises(SystemExit):
        services.repo_path()
    assert "needs an editable install" in capsys.readouterr().err


# Templates


def test_backend_plist(svc):  # AC6
    svc.install()
    plist = plistlib.loads(svc.file("backend").read_bytes())
    log = str(svc.logfile("backend"))
    assert plist["Label"] == LABEL["backend"]
    assert plist["ProgramArguments"] == [str(svc.bin / "fctl"), "serve", "--host", "127.0.0.1", "--port",
                                         str(svc.ports["backend"])]
    assert plist["WorkingDirectory"] == str(svc.repo)
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["StandardOutPath"] == plist["StandardErrorPath"] == log
    assert plist["EnvironmentVariables"] == {
        "PATH": svc.state()["env"]["PATH"],
        "FCTL_HOME": os.environ["FCTL_HOME"],
        "CLAUDE_CONFIG_DIR": os.environ["CLAUDE_CONFIG_DIR"],
    }
    assert "<key>KeepAlive</key>\n  <dict><key>SuccessfulExit</key><false/></dict>" in svc.file("backend").read_text()


def test_backend_plist_env_only_when_set(svc, monkeypatch):  # AC6
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.delenv("FCTL_HOME")
    svc.home = Path.home() / ".workcell"
    svc.install()
    plist = plistlib.loads(svc.file("backend").read_bytes())
    assert set(plist["EnvironmentVariables"]) == {"PATH"}
    assert plist["StandardOutPath"] == str(Path.home() / ".workcell" / "logs" / "backend.log")


def test_plist_values_are_escaped(tmp_path):  # AC6
    repo = tmp_path / "a&b <c>"
    state = {"ports": {"backend": 4545, "frontend": 3000}, "bins": {"fctl": "/x&y/fctl", "node": "/n<1>/node"},
             "env": {"PATH": "/a&b:/c<d>", "FCTL_HOME": "/h\"&'"}}
    for name in ("backend", "frontend"):
        text = services.render_plist(name, state, repo)
        assert "a&b" not in text and "/a&amp;b:/c&lt;d&gt;" in text
        plist = plistlib.loads(text.encode())
        assert plist["WorkingDirectory"] == str(repo)
        assert plist["EnvironmentVariables"]["PATH"] == "/a&b:/c<d>"
    assert plistlib.loads(services.render_plist("backend", state, repo).encode())["EnvironmentVariables"] == \
        state["env"]


def test_frontend_plist(svc):  # AC7
    svc.install()
    plist = plistlib.loads(svc.file("frontend").read_bytes())
    log = str(svc.logfile("frontend"))
    assert plist["Label"] == LABEL["frontend"]
    assert plist["ProgramArguments"] == [str(svc.bin / "node"), str(svc.repo / "frontend" / "server.js")]
    assert plist["WorkingDirectory"] == str(svc.repo)
    assert plist["EnvironmentVariables"] == {
        "HOST": "127.0.0.1",
        "PORT": str(svc.ports["frontend"]),
        "FCTL_API_URL": f"http://127.0.0.1:{svc.ports['backend']}",
        "PATH": svc.state()["env"]["PATH"],
    }
    assert plist["StandardOutPath"] == plist["StandardErrorPath"] == log
    assert plist["RunAtLoad"] is True and plist["KeepAlive"] == {"SuccessfulExit": False}


def test_linux_units(svc, monkeypatch):  # AC8
    monkeypatch.setattr(sys, "platform", "linux")
    svc.install()
    backend, frontend = (svc.file(n).read_text().splitlines() for n in ("backend", "frontend"))
    path = svc.state()["env"]["PATH"]
    assert f'ExecStart="{svc.bin / "fctl"}" "serve" "--host" "127.0.0.1" "--port" "{svc.ports["backend"]}"' in backend
    assert f'ExecStart="{svc.bin / "node"}" "{svc.repo / "frontend" / "server.js"}"' in frontend
    for name, lines in (("backend", backend), ("frontend", frontend)):
        log = svc.logfile(name)
        for line in (f"WorkingDirectory={svc.repo}", f'Environment="PATH={path}"', "Restart=on-failure",
                     f"StandardOutput=append:{log}", f"StandardError=append:{log}", "WantedBy=default.target"):
            assert line in lines, (name, line)
    assert "Description=Workcell backend" in backend and "Description=Workcell frontend" in frontend  # 116 AC10
    assert f'Environment="FCTL_HOME={os.environ["FCTL_HOME"]}"' in backend
    assert f'Environment="CLAUDE_CONFIG_DIR={os.environ["CLAUDE_CONFIG_DIR"]}"' in backend
    for line in ('Environment="HOST=127.0.0.1"', f'Environment="PORT={svc.ports["frontend"]}"',
                 f'Environment="FCTL_API_URL=http://127.0.0.1:{svc.ports["backend"]}"'):
        assert line in frontend


def test_unit_quoting(tmp_path):  # AC8
    state = {"ports": {"backend": 4545, "frontend": 3000}, "bins": {"fctl": '/my "bin"/fctl', "node": "/n"},
             "env": {"PATH": "/a 100%:/b\\c"}}
    text = services.render_unit("backend", state, tmp_path)
    assert 'ExecStart="/my \\"bin\\"/fctl" "serve"' in text
    assert 'Environment="PATH=/a 100%%:/b\\\\c"' in text


def test_no_wildcard_bind(plat, svc):  # AC9
    svc.ports = {"backend": 5123, "frontend": 5124}
    svc.install()
    for name in ("backend", "frontend"):
        text = svc.file(name).read_text()
        assert "0.0.0.0" not in text and "127.0.0.1" in text
        assert ("5123" if name == "backend" else "5124") in text


# install / uninstall


def test_install_requires_binaries(svc, monkeypatch, capsys):  # AC10
    (svc.bin / "node").unlink()
    svc.git_only_path(monkeypatch)
    assert refused(capsys, "install") == "fctl: node not found on PATH\n"
    assert not (svc.home / "service.json").exists()
    assert svc.calls() == []


def test_install_warns_and_saves(svc, monkeypatch, capsys):  # AC10
    gitbin = svc.git_only_path(monkeypatch)
    monkeypatch.setenv("PATH", f"{svc.bin}{os.pathsep}{gitbin}{os.pathsep}{svc.bin}")
    svc.install()
    err = capsys.readouterr().err
    assert "warning: uv not found on PATH; runs and reviewers need it" in err
    assert "warning: gh not found on PATH; runs and reviewers need it" in err
    assert "claude" not in err and "wt " not in err
    state = svc.state()
    assert state["ports"] == svc.ports
    assert state["bins"] == {name: str(svc.bin / name) for name in ("fctl", "node", "npm")} | {
        "git": str(gitbin / "git"), "claude": str(svc.bin / "claude"), "wt": str(svc.bin / "wt")}
    assert state["env"] == {"PATH": f"{svc.bin}{os.pathsep}{gitbin}", "FCTL_HOME": os.environ["FCTL_HOME"],
                            "CLAUDE_CONFIG_DIR": os.environ["CLAUDE_CONFIG_DIR"]}


def test_install_builds_missing_frontend(svc):  # AC11
    (svc.repo / "frontend" / "dist" / "index.html").unlink()
    shutil.rmtree(svc.repo / "frontend" / "node_modules")
    fctl("install", "--backend-port", str(svc.ports["backend"]), "--frontend-port", str(svc.ports["frontend"]))
    frontend = str(svc.repo / "frontend")
    calls = svc.calls("npm", "launchctl")
    assert calls[:2] == [["npm", "--prefix", frontend, "ci"], ["npm", "--prefix", frontend, "run", "build"]]
    assert [c[0] for c in calls[2:]] == ["launchctl"] * 4


def test_install_and_start_build_without_ci(svc):  # AC11
    (svc.repo / "frontend" / "dist" / "index.html").unlink()
    svc.install()
    fctl("start")
    frontend = str(svc.repo / "frontend")
    calls = svc.calls("npm", "launchctl")
    assert calls[0] == ["npm", "--prefix", frontend, "run", "build"]
    assert all(c[0] == "launchctl" for c in calls[1:]) and calls[1:]


def test_install_darwin_calls(svc):  # AC12
    svc.rule("launchctl", "bootout", code=3)  # nothing loaded yet: ignored
    for _ in range(2):
        fctl("install", "--backend-port", str(svc.ports["backend"]), "--frontend-port", str(svc.ports["frontend"]))
        assert svc.calls() == [
            ["launchctl", "bootout", f"{DOMAIN}/{LABEL['backend']}"],
            ["launchctl", "bootstrap", DOMAIN, str(svc.file("backend"))],
            ["launchctl", "bootout", f"{DOMAIN}/{LABEL['frontend']}"],
            ["launchctl", "bootstrap", DOMAIN, str(svc.file("frontend"))],
        ]
        assert svc.file("backend").is_file() and svc.file("frontend").is_file()
        svc.log.unlink()


def test_install_linux_calls(svc, monkeypatch):  # AC12
    monkeypatch.setattr(sys, "platform", "linux")
    for _ in range(2):
        fctl("install", "--backend-port", str(svc.ports["backend"]), "--frontend-port", str(svc.ports["frontend"]))
        assert svc.calls() == [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", UNIT["backend"]],
            ["systemctl", "--user", "enable", "--now", UNIT["frontend"]],
        ]
        svc.log.unlink()


def test_install_prints_fctl_url_hint(svc, capsys):  # Q8
    svc.install()
    out = capsys.readouterr().out
    assert f"Started backend → http://127.0.0.1:{svc.ports['backend']}" in out
    assert f"export FCTL_URL=http://127.0.0.1:{svc.ports['backend']}\n" in out


def test_uninstall(plat, svc, capsys):  # AC13
    svc.install()
    svc.logfile("backend").write_text("kept\n")
    fctl("uninstall")
    if plat == "darwin":
        assert svc.calls() == [["launchctl", "bootout", f"{DOMAIN}/{LABEL[n]}"] for n in ("backend", "frontend")]
    else:
        assert svc.calls() == [
            ["systemctl", "--user", "disable", "--now", UNIT["backend"]],
            ["systemctl", "--user", "disable", "--now", UNIT["frontend"]],
            ["systemctl", "--user", "daemon-reload"],
        ]
    assert not svc.file("backend").exists() and not svc.file("frontend").exists()
    assert not (svc.home / "service.json").exists()
    assert svc.logfile("backend").read_text() == "kept\n"


@pytest.mark.parametrize("sub", [s for s in SUBS if s != "install"])
def test_not_installed(svc, capsys, sub):  # AC14
    assert refused(capsys, sub) == "fctl: not installed; run fctl service install\n"
    assert svc.calls(skip=()) == []


# start / stop / restart


def test_start_darwin(svc, capsys):  # AC15
    svc.install()
    svc.not_loaded("backend")  # frontend: loaded, no pid
    fctl("start")
    assert svc.calls("launchctl") == [
        ["launchctl", "bootstrap", DOMAIN, str(svc.file("backend"))],
        ["launchctl", "kickstart", f"{DOMAIN}/{LABEL['frontend']}"],
    ]
    assert "Started backend" in capsys.readouterr().out


def test_start_skips_running(svc, capsys):  # AC15
    svc.install()
    svc.rule("launchctl", "print", f"{DOMAIN}/{LABEL['backend']}", out="\tpid = 4321\n")
    fctl("start", "backend")
    assert svc.calls("launchctl") == []
    assert capsys.readouterr().out.endswith("backend is already running (pid 4321)\n")


def test_stop_and_restart_darwin(svc):  # AC15
    svc.install()
    fctl("stop")
    assert svc.calls() == [["launchctl", "bootout", f"{DOMAIN}/{LABEL[n]}"] for n in ("backend", "frontend")]
    svc.clear()
    svc.not_loaded("frontend")
    fctl("restart")
    assert svc.calls() == [
        ["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL['backend']}"],
        ["launchctl", "bootstrap", DOMAIN, str(svc.file("frontend"))],
    ]
    svc.clear()
    fctl("stop", "frontend")
    assert svc.calls() == [["launchctl", "bootout", f"{DOMAIN}/{LABEL['frontend']}"]]


def test_start_stop_restart_linux(svc, monkeypatch):  # AC15
    monkeypatch.setattr(sys, "platform", "linux")
    svc.install()
    for sub in ("start", "stop", "restart"):
        fctl(sub)
        assert svc.calls("systemctl") == [["systemctl", "--user", sub, UNIT["backend"], UNIT["frontend"]]]
        svc.clear()
        fctl(sub, "frontend")
        assert svc.calls("systemctl") == [["systemctl", "--user", sub, UNIT["frontend"]]]
        svc.clear()


@pytest.mark.parametrize("which, flag", [("backend", "--backend-port"), ("frontend", "--frontend-port")])
def test_start_port_taken(plat, svc, capsys, which, flag):  # AC16
    svc.install()
    port = svc.ports[which]
    svc.rule("lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-t", out="1234\n")
    svc.rule("ps", "comm=", "1234", out="python3\n")
    assert refused(capsys, "start", which) == (
        f"fctl: port {port} is taken by pid 1234 (python3); stop it, or reinstall with {flag}\n")
    assert svc.calls("launchctl", "systemctl") == []


def test_start_port_taken_without_lsof(svc, monkeypatch, capsys):  # AC16
    svc.install()
    (svc.bin / "lsof").unlink()
    svc.git_only_path(monkeypatch)
    with socket.socket() as s:
        s.bind(("127.0.0.1", svc.ports["backend"]))
        s.listen()
        assert refused(capsys, "start") == (f"fctl: port {svc.ports['backend']} is taken by another process; stop it,"
                                            " or reinstall with --backend-port\n")
    assert svc.calls("launchctl") == []


def test_log_rotates_over_10_mb(svc):  # AC17
    svc.install()
    big, small = svc.logfile("backend"), svc.logfile("frontend")
    with open(big, "wb") as f:
        f.truncate(10 * 1024 * 1024 + 1)
    big.with_name("backend.log.1").write_text("older\n")
    small.write_text("small\n")
    fctl("restart")
    assert not big.exists()
    assert big.with_name("backend.log.1").stat().st_size == 10 * 1024 * 1024 + 1
    assert small.read_text() == "small\n" and not small.with_name("frontend.log.1").exists()


# Active runs guard


@pytest.mark.parametrize("argv", [["stop"], ["stop", "backend"], ["restart"], ["restart", "backend"], ["reload"],
                                  ["uninstall"]])
def test_guard_refuses(plat, svc, agents, capsys, argv):  # AC18
    svc.install()
    running(agents, RUN_68)
    assert refused(capsys, *argv) == "fctl: run #68 on #92 is active; wait, stop it in the app, or pass --force\n"
    assert svc.calls("launchctl", "systemctl", "npm") == []
    assert agents.requests[-1][:2] == ("GET", "/api/pages/agents")
    assert (svc.home / "service.json").exists()


def test_guard_lists_several(svc, agents, capsys):  # AC18
    svc.install()
    running(agents, RUN_68, RUN_70)
    assert refused(capsys, "restart") == (
        "fctl: run #68 on #92, run #70 on #95 are active; wait, stop them in the app, or pass --force\n")


@pytest.mark.parametrize("argv", [["stop"], ["restart"], ["reload"], ["uninstall"]])
def test_guard_force(plat, svc, agents, capsys, argv):  # AC19
    svc.install()
    running(agents, RUN_68, RUN_70)
    capsys.readouterr()
    fctl(*argv, "--force")
    assert capsys.readouterr().out.startswith("Stopping active runs: run #68 on #92, run #70 on #95\n")
    assert svc.calls("launchctl", "systemctl")


def test_guard_backend_down(svc, capsys):  # AC20
    svc.install()  # nothing listens on svc.ports["backend"]
    capsys.readouterr()
    fctl("stop")
    assert capsys.readouterr().out == "Stopped backend\nStopped frontend\n"
    assert len(svc.calls("launchctl")) == 2


@pytest.mark.parametrize("sub", ["stop", "restart"])
def test_guard_skips_frontend(svc, agents, sub):  # AC21
    svc.install()
    running(agents, RUN_68)
    fctl(sub, "frontend")
    assert agents.requests == []
    assert svc.calls("launchctl")


# reload


def test_reload_unchanged_lockfile(plat, svc, capsys):  # AC22
    svc.install()
    fctl("reload")  # no stored hash yet: ci once
    svc.clear()
    fctl("reload")
    frontend = str(svc.repo / "frontend")
    restart = ([["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL[n]}"] for n in ("backend", "frontend")]
               if plat == "darwin" else [["systemctl", "--user", "restart", UNIT["backend"], UNIT["frontend"]]])
    assert svc.calls() == [["npm", "--prefix", frontend, "run", "build"], *restart]
    assert "Python dependencies changed" not in capsys.readouterr().out


def test_reload_changed_lockfile(svc):  # AC22
    svc.install()
    fctl("reload")
    assert svc.state()["hashes"]["package-lock.json"]
    svc.clear()
    write(svc.repo, {"frontend/package-lock.json": '{"v": 2}'})
    fctl("reload")
    frontend = str(svc.repo / "frontend")
    assert [c[:5] for c in svc.calls()] == [
        ["npm", "--prefix", frontend, "ci"],
        ["npm", "--prefix", frontend, "run", "build"],
        ["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL['backend']}"],
        ["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL['frontend']}"],
    ]
    assert svc.state()["hashes"]["package-lock.json"] == services.sha256(svc.repo / "frontend" / "package-lock.json")


def test_reload_without_node_modules(svc):  # AC22
    svc.install()
    fctl("reload")
    shutil.rmtree(svc.repo / "frontend" / "node_modules")
    svc.clear()
    fctl("reload")
    assert ["npm", "--prefix", str(svc.repo / "frontend"), "ci"] in svc.calls("npm")


@pytest.mark.parametrize("step", ["ci", "build"])
def test_reload_npm_fails(svc, capsys, step):  # AC23
    svc.install()
    svc.rule("npm", step, code=1)
    assert refused(capsys, "reload") == f"fctl: npm {'run build' if step == 'build' else 'ci'} failed; see the output above\n"
    assert svc.calls("launchctl") == []


def test_reload_python_hint(svc, capsys):  # AC24
    svc.install()
    write(svc.repo, {"uv.lock": "version = 2\n"})
    fctl("reload")
    out = capsys.readouterr().out
    assert f"Python dependencies changed; run: uv tool install --editable --reinstall {svc.repo}\n" in out
    assert svc.state()["hashes"]["uv.lock"] == services.sha256(svc.repo / "uv.lock")
    assert all(c[0] != "uv" for c in svc.calls(skip=()))
    fctl("reload")
    assert "Python dependencies changed" not in capsys.readouterr().out


def test_served_sha(svc):  # AC25
    svc.install()
    head = git(svc.repo, "rev-parse", "--short", "HEAD")
    assert svc.state()["served"] == {"backend": head, "frontend": head}
    new = commit(svc.repo, {"a.py": "x = 1\n"})[:len(head)]
    fctl("restart", "frontend")
    assert svc.state()["served"] == {"backend": head, "frontend": new}
    fctl("reload")
    assert svc.state()["served"]["backend"] == new
    commit(svc.repo, {"a.py": "x = 2\n"})
    svc.not_loaded("backend")
    fctl("start", "backend")
    assert svc.state()["served"]["backend"] == git(svc.repo, "rev-parse", "--short", "HEAD")


# status


def test_status(plat, svc, capsys):  # AC26
    svc.install()
    head = git(svc.repo, "rev-parse", "--short", "HEAD")
    if plat == "darwin":
        svc.rule("launchctl", "print", f"{DOMAIN}/{LABEL['backend']}", out="state = running\n\tpid = 4321\n")
        svc.not_loaded("frontend")
    else:
        svc.rule("systemctl", "show", "MainPID", UNIT["backend"], out="4321\n")
        svc.rule("systemctl", "show", "MainPID", UNIT["frontend"], out="0\n")
    svc.rule("ps", "etime=", "4321", out="  01:02:03\n")
    capsys.readouterr()
    fctl("status")
    b, f = svc.ports["backend"], svc.ports["frontend"]
    assert capsys.readouterr().out == (
        f"backend: running\n  pid: 4321\n  port: {b}\n  uptime: 01:02:03\n  url: http://127.0.0.1:{b}\n"
        f"  code: {head}, main {head}, current\n\n"
        f"frontend: stopped\n  pid: -\n  port: {f}\n  uptime: -\n  url: http://127.0.0.1:{f}\n"
        f"  code: {head}, main {head}, current\n\n"
        "active runs: unknown (backend not answering)\n")


def test_status_stale(svc, capsys):  # AC26
    svc.install()
    served = git(svc.repo, "rev-parse", "--short", "HEAD")
    main_sha = commit(svc.repo, {"a.py": "x = 1\n"})[:len(served)]
    capsys.readouterr()
    fctl("status")
    assert f"  code: {served}, main {main_sha}, stale\n" in capsys.readouterr().out


def test_status_runs(svc, agents, capsys):  # AC27
    svc.install()
    running(agents, RUN_68, RUN_70)
    capsys.readouterr()
    fctl("status")
    assert capsys.readouterr().out.endswith(
        "active runs: run #68 on #92 (Rate-limit login), run #70 on #95 (Dark mode)\n")
    running(agents)
    fctl("status")
    assert capsys.readouterr().out.endswith("active runs: none\n")


def test_status_moved_binary(svc, capsys):  # AC28
    svc.install()
    state = svc.state()
    state["bins"]["node"] = "/gone/node"
    (svc.home / "service.json").write_text(json.dumps(state))
    capsys.readouterr()
    fctl("status")  # no SystemExit: exit 0
    assert capsys.readouterr().err == "warning: node moved: /gone/node no longer exists; run fctl service install\n"


# logs


def test_logs(svc, capsys):  # AC29
    svc.install()
    svc.logfile("backend").write_text("".join(f"line {i}\n" for i in range(100)))
    capsys.readouterr()
    fctl("logs", "backend", "-n", "3")
    assert capsys.readouterr().out == f"==> {svc.logfile('backend')} <==\nline 97\nline 98\nline 99\n"
    fctl("logs")
    out = capsys.readouterr().out
    assert out.startswith(f"==> {svc.logfile('backend')} <==\nline 50\n")
    assert out.endswith(f"line 99\nno log yet: {svc.logfile('frontend')}\n")


def test_logs_follow(svc, monkeypatch, capsys):  # AC30
    svc.install()
    svc.logfile("backend").write_text("b\n")
    svc.logfile("frontend").write_text("f\n")
    execs = []
    monkeypatch.setattr(os, "execvp", lambda file, argv: execs.append((file, argv)))
    capsys.readouterr()
    fctl("logs", "-f", "-n", "5")
    assert execs == [("tail", ["tail", "-n", "5", "-f", str(svc.logfile("backend")), str(svc.logfile("frontend"))])]
    assert capsys.readouterr().out == ""


# Docs


def test_fctl_md_home_row():  # AC31
    from test_fctl_md import SECTIONS

    [row] = [line for line in SECTIONS["fctl-url-and-fctl-home"].splitlines() if line.startswith("| `FCTL_HOME` |")]
    cells = row.split("|")
    assert "`fctl service`" in cells[3]
    assert "`logs/`" in cells[4] and "`service.json`" in cells[4]


def test_docs():  # AC32
    root = Path(__file__).resolve().parents[3]
    readme = (root / "README.md").read_text()
    run = readme[readme.index("## Run the app"):readme.index("## Run with Docker")]
    assert run.index("fctl service install") < run.index("fctl serve ")
    for text in ("fctl service reload", "fctl service status", "fctl service logs"):
        assert text in run, text
    assert "docker compose up -d" in readme[readme.index("## Run with Docker"):]
    mvp = (root / "docs" / "MVP.md").read_text()
    assert "fctl service install" in mvp[mvp.index("### 3.0"):mvp.index("### 3.1")]
    claude_code = (root / "docs" / "claude-code.md").read_text()
    commands = claude_code[claude_code.index("### 7.2 Commands"):claude_code.index("### 7.3")]
    assert any(line.startswith("| `fctl service ") for line in commands.splitlines())
    from test_fctl_md import SECTIONS

    assert "docker compose restart" in SECTIONS["using-fctl-with-docker"]
