"""027: the Docker files, read as text with the stdlib. No Docker and no YAML parser (Q1)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(name) -> str:
    return (ROOT / name).read_text()


def instructions(name) -> list[tuple[str, str]]:
    """A Dockerfile's (KEYWORD, arguments) pairs, comments dropped and continuations joined."""
    text = read(name).replace("\\\n", " ")
    return [(kw.upper(), args.strip()) for kw, args in re.findall(r"^\s*(\w+)\s+(.*)$", text, re.M)]


def stages(name) -> list[list[tuple[str, str]]]:
    """The instructions split at each FROM; each stage starts with its FROM."""
    out = []
    for kw, args in instructions(name):
        if kw == "FROM":
            out.append([])
        if out:
            out[-1].append((kw, args))
    return out


def last_cmd(steps) -> list:
    return json.loads([args for kw, args in steps if kw == "CMD"][-1])


def ignore_rules(name) -> list[str]:
    return [line.strip() for line in read(name).splitlines() if line.strip() and not line.lstrip().startswith("#")]


def blocks(text, indent=0) -> dict[str, str]:
    """The YAML keys at this indent → the lines nested under each, by indentation alone (Q1)."""
    out, key = {}, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if m := re.match(rf" {{{indent}}}([\w-]+):", line):
            key = m[1]
            out[key] = ""
        elif key and line.startswith(" " * (indent + 1)):
            out[key] += line + "\n"
        else:
            key = None
    return out


def services(name) -> dict[str, str]:
    return blocks(blocks(read(name))["services"], 2)


def items(block) -> list[str]:
    """A YAML block list's items, trailing comments dropped."""
    return re.findall(r"^\s*-\s*([^#\s]+)", block, re.M)


# --- Dockerfile ----------------------------------------------------------------


def test_dockerfile_base_uv_and_git():  # AC5
    steps = instructions("Dockerfile")
    assert [args for kw, args in steps if kw == "FROM"][-1] == "python:3.12-slim"  # 099: after the wt stage
    uv = [args for kw, args in steps if kw == "COPY" and "astral-sh/uv" in args]
    assert len(uv) == 1
    assert re.match(r"--from=ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+ ", uv[0])
    assert any(kw == "RUN" and "apt-get install" in args and re.search(r"\bgit\b", args) for kw, args in steps)


def test_dockerfile_cmd():  # AC6
    assert last_cmd(instructions("Dockerfile")) == ["fctl", "serve", "--host", "0.0.0.0"]


def test_dockerfile_data_dir():  # AC7
    steps = instructions("Dockerfile")
    assert any(kw == "ENV" and re.search(r"(^|\s)FCTL_HOME=/data(\s|$)", args) for kw, args in steps)
    assert any(
        kw == "RUN" and re.search(r"(mkdir\b.*-m 0?777|chmod 0?777)\s.*/data\b", args) for kw, args in steps
    )


def test_dockerignore_allowlists_copy_sources():  # AC8
    rules = ignore_rules(".dockerignore")
    sources = set()
    for kw, args in instructions("Dockerfile"):
        if kw == "COPY" and "--from=" not in args:
            sources.update(a.removeprefix("./") for a in args.split()[:-1] if not a.startswith("--"))
    assert rules[0] == "*"
    assert {r[1:] for r in rules if r.startswith("!")} == sources
    assert sources >= {"pyproject.toml", "uv.lock", "src"}


# --- frontend/Dockerfile -------------------------------------------------------


def test_frontend_dockerfile_stages():  # AC9
    all_stages = stages("frontend/Dockerfile")
    froms = [stage[0][1].split() for stage in all_stages]
    assert len(froms) >= 2
    assert all(f[0] == "node:22-slim" for f in froms)
    earlier = all_stages[:-1]
    runs = [" ".join(args for kw, args in stage if kw == "RUN") for stage in earlier]
    built = [i for i, run in enumerate(runs) if "npm ci" in run and "npm run build" in run]
    assert built
    names = {froms[i][2] for i in built if len(froms[i]) == 3 and froms[i][1].upper() == "AS"} | {str(i) for i in built}
    last = all_stages[-1]
    assert not any("npm" in args for kw, args in last if kw in ("RUN", "CMD", "ENTRYPOINT"))
    dist = [re.match(r"--from=(\S+) ", args) for kw, args in last if kw == "COPY" and re.search(r"\bdist\b", args)]
    assert any(m and m[1] in names for m in dist)
    assert ("USER", "node") in last
    assert last_cmd(last) == ["node", "server.js"]


def test_frontend_dockerignore():  # AC10
    assert {"node_modules", "dist"} <= set(ignore_rules("frontend/.dockerignore"))


# --- compose.yaml --------------------------------------------------------------


def test_compose_services():  # AC11
    svc = services("compose.yaml")
    assert re.search(r"^\s+build:\s*\.\s*$", svc["backend"], re.M)
    assert re.search(r"^\s+build:\s*\./frontend\s*$", svc["frontend"], re.M)


def compose_ports(name) -> dict[str, list[str]]:
    return {svc: items(blocks(body, 4).get("ports", "")) for svc, body in services(name).items()}


def test_compose_backend_default_port():  # 118 AC1
    assert compose_ports("compose.yaml")["backend"] == ['"127.0.0.1:4545:4545"']


def test_compose_frontend_default_port():  # 118 AC2
    assert compose_ports("compose.yaml")["frontend"] == ['"127.0.0.1:3000:3000"']


def test_compose_ports_loopback_only():  # AC12 → 118 AC3: MVP §4.5, never 0.0.0.0 on the host
    ports = [p for ps in compose_ports("compose.yaml").values() for p in ps]
    assert ports and all(p.strip('"').startswith("127.0.0.1:") for p in ports)
    assert "0.0.0.0:" not in read("compose.yaml")


def test_compose_frontend_env_and_depends_on():  # AC13
    frontend = services("compose.yaml")["frontend"]
    assert re.search(r"^\s+-?\s*HOST\s*[:=]\s*[\"']?0\.0\.0\.0[\"']?\s*$", frontend, re.M)
    assert re.search(r"^\s+-?\s*FCTL_API_URL\s*[:=]\s*[\"']?http://backend:4545[\"']?\s*$", frontend, re.M)
    depends = blocks(frontend, 4)["depends_on"]
    assert re.search(r"^\s+condition:\s*service_healthy\s*$", blocks(depends, 6)["backend"], re.M)


def test_compose_backend_data_volume():  # AC14
    assert "fctl-home:/data" in items(blocks(services("compose.yaml")["backend"], 4)["volumes"])
    assert "fctl-home" in blocks(blocks(read("compose.yaml"))["volumes"], 2)


def test_compose_healthchecks():  # AC15
    svc = services("compose.yaml")
    checks = {name: blocks(body, 4).get("healthcheck", "") for name, body in svc.items()}
    assert all(checks.values())
    assert "http://127.0.0.1:4545/api/workspaces" in checks["backend"]
    assert "http://127.0.0.1:3000/" in checks["frontend"]


# --- compose.override.example.yaml ---------------------------------------------


def test_override_ports_on_loopback_only():  # AC16
    text = read("compose.override.example.yaml")
    svc = services("compose.override.example.yaml")
    ports = {name: items(blocks(body, 4).get("ports", "")) for name, body in svc.items()}
    assert {name: p for name, p in ports.items() if p} == {
        "backend": ['"127.0.0.1:4545:4545"'],
        "frontend": ['"127.0.0.1:3000:3000"'],
    }
    assert len(re.findall(r"^\s*ports\s*:", text, re.M)) == 2


def test_override_ports_replace_defaults():  # 118 AC4
    text = read("compose.override.example.yaml")
    assert len(re.findall(r"^\s*ports:\s*!override\s*$", text, re.M)) == 2
    assert not re.search(r"^\s*ports:\s*(#.*)?$", text, re.M)


def test_override_explains_override_tag():  # 118 AC6
    comments = "\n".join(line.split("#", 1)[1] for line in read("compose.override.example.yaml").splitlines()
                         if "#" in line)
    assert "!override" in comments
    assert re.search(r"concatenat|replace", comments)
    assert "v2.24.4" in comments


def test_override_backend_port_needs_fctl_url():  # 118 AC7
    assert "FCTL_URL=http://127.0.0.1:" in read("compose.override.example.yaml")


def test_override_backend_user_and_same_path_mount():  # AC17
    backend = services("compose.override.example.yaml")["backend"]
    assert re.search(r"^\s+user:\s*\"\d+:\d+\"\s*(#.*)?$", backend, re.M)
    mounts = [re.fullmatch(r"(/[^:]+):(/[^:]+)(:\w+)?", m) for m in items(blocks(backend, 4)["volumes"])]
    assert any(m and m[1] == m[2] for m in mounts)


# --- .gitignore and README -----------------------------------------------------


def test_gitignore_override_only():  # AC18
    lines = read(".gitignore").splitlines()
    assert [line for line in lines if line.startswith("compose.override")] == ["compose.override.yaml"]


def docker_section() -> str:
    """README's "Run with Docker", up to the next ## or ### heading."""
    readme = read("README.md")
    start = readme.index("\n### Run with Docker\n")
    return readme[start:re.compile(r"\n#{2,3} ").search(readme, start + 1).start()]


def test_readme_docker_quick_start():  # AC19 → 118 AC9: no override needed for the first `up`
    docker = docker_section()
    assert re.search(r"```sh\n(.*?)```", docker, re.S)[1] == "docker compose up --build\n"
    assert "http://127.0.0.1:3000" in docker
    assert "optional" in docker
    assert "cp compose.override.example.yaml compose.override.yaml" in docker


def test_readme_docker_connect_needs_mount():  # 118 AC10
    docker = docker_section()
    assert "compose.override.yaml" in docker and "/path/to/code:/path/to/code" in docker


def test_readme_docker_backend_port_fctl_url():  # 118 AC11
    assert "FCTL_URL=http://127.0.0.1:" in docker_section()


def test_mvp_default_ports_documented():  # 118 AC12
    mvp = " ".join(read("docs/MVP.md").split())
    assert "publishes no ports" not in mvp and "publishes no" not in mvp
    assert "ports: !override" in mvp and "127.0.0.1:4545" in mvp and "127.0.0.1:3000" in mvp


# --- 028: runs inside the backend container --------------------------------------


def env(steps) -> dict[str, str]:
    """Every ENV's KEY=value pairs, later ones winning, as Docker applies them."""
    return {k: v for kw, args in steps if kw == "ENV" for k, v in re.findall(r"(\w+)=(\S+)", args)}


def test_dockerfile_node():  # 028 AC7
    steps = instructions("Dockerfile")
    assert [args for kw, args in steps if kw == "FROM"][-1] == "python:3.12-slim"  # 099: after the wt stage
    node = [args.split()[1] for kw, args in steps if kw == "COPY" and args.startswith("--from=node:22-slim ")]
    assert set(node) == {"/usr/local/bin/node", "/usr/local/lib/node_modules"}


def test_dockerfile_claude_pinned():  # 028 AC8
    steps = instructions("Dockerfile")
    last_node = max(i for i, (kw, args) in enumerate(steps) if kw == "COPY" and "--from=node:" in args)
    installs = [i for i, (kw, args) in enumerate(steps) if kw == "RUN" and "@anthropic-ai/claude-code" in args]
    assert len(installs) == 1 and installs[0] > last_node
    assert re.search(r"\bnpm install -g @anthropic-ai/claude-code@\d+\.\d+\.\d+(\s|$)", steps[installs[0]][1])
    assert env(steps)["DISABLE_AUTOUPDATER"] == "1"


def test_dockerfile_wt_pinned():  # 099 AC11
    build, app = stages("Dockerfile")
    assert build[0] == ("FROM", "rust:1-slim AS worktrunk")
    [install] = [args for kw, args in build if kw == "RUN"]
    assert re.fullmatch(r"cargo install worktrunk --version \d+\.\d+\.\d+ --locked --root /opt/worktrunk", install)
    assert ("COPY", "--from=worktrunk /opt/worktrunk/bin/wt /usr/local/bin/wt") in app
    assert ("RUN", "wt --version") in app  # the build fails if wt can't run in the final image
    assert "latest" not in read("Dockerfile")


def test_dockerfile_home_and_in_docker():  # 028 AC9
    steps = instructions("Dockerfile")
    assert (env(steps)["FCTL_IN_DOCKER"], env(steps)["HOME"]) == ("1", "/home/fctl")
    assert any(kw == "RUN" and re.search(r"mkdir\b.*-m 1777\s+/home/fctl(\s|$)", args) for kw, args in steps)


def test_dockerfile_path_keeps_app_fctl():  # 028 AC10
    assert env(instructions("Dockerfile"))["PATH"].startswith("/app/.venv/bin:")


def test_dockerfile_python_downloads_only_off_for_build():  # 028 AC11
    steps = instructions("Dockerfile")
    assert "UV_PYTHON_DOWNLOADS" not in env(steps)
    [sync] = [args for kw, args in steps if kw == "RUN" and "uv sync" in args]
    assert re.search(r"(^|\s)UV_PYTHON_DOWNLOADS=never\s+uv sync\b", sync)


def test_compose_backend_init():  # 028 AC12
    assert re.search(r"^\s+init:\s*true\s*(#.*)?$", services("compose.yaml")["backend"], re.M)


def test_compose_backend_home_volume():  # 028 AC13
    assert items(blocks(services("compose.yaml")["backend"], 4)["volumes"]) == ["fctl-home:/data",
                                                                               "backend-home:/home/fctl"]
    assert {"fctl-home", "backend-home"} <= set(blocks(blocks(read("compose.yaml"))["volumes"], 2))


def test_compose_backend_image_name():  # 028 AC14
    backend = services("compose.yaml")["backend"]
    assert re.search(r"^\s+image:\s*workcell-backend\s*(#.*)?$", backend, re.M)
    assert re.search(r"^\s+build:\s*\.\s*$", backend, re.M)


def test_override_custom_image_recipe():  # 028 AC15
    backend = read("compose.override.example.yaml").split("\n  backend:\n", 1)[1].split("\n  frontend:\n", 1)[0]
    comments = [line.strip() for line in backend.splitlines() if line.lstrip().startswith("#")]
    assert any("FROM workcell-backend" in c for c in comments)
    assert any(c.startswith("# image: ") for c in comments)
    assert "# build: !reset null" in comments


def test_readme_docker_runs():  # 028 AC16; Q11: this claude has `auth login`, no `login`
    readme = read("README.md")
    assert "docker compose exec backend claude auth login" in readme
    assert "docker compose exec backend claude auth status" in readme
    assert "docker compose exec -w" in readme and "backend-home" in readme
    assert "Runs don't work inside Docker yet" not in readme
    assert "| `FCTL_IN_DOCKER` |" in readme


def test_readme_demo_data():  # 038 AC38, Q8
    readme = read("README.md")
    start = readme.index("\n## Demo data\n")
    demo = readme[start:readme.index("\n## ", start + 1)]
    for text in ("FCTL_HOME=~/.workcell-demo fctl seed", "FCTL_HOME=~/.workcell-demo fctl serve",
                 "docker compose -p workcell-demo up",
                 "docker compose -p workcell-demo exec backend fctl seed"):
        assert text in demo, text
