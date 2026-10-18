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
    assert [args for kw, args in steps if kw == "FROM"][0] == "python:3.12-slim"
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


def test_compose_publishes_no_ports():  # AC12
    assert not re.search(r"^\s*ports\s*:", read("compose.yaml"), re.M)


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


def test_override_backend_user_and_same_path_mount():  # AC17
    backend = services("compose.override.example.yaml")["backend"]
    assert re.search(r"^\s+user:\s*\"\d+:\d+\"\s*(#.*)?$", backend, re.M)
    mounts = [re.fullmatch(r"(/[^:]+):(/[^:]+)(:\w+)?", m) for m in items(blocks(backend, 4)["volumes"])]
    assert any(m and m[1] == m[2] for m in mounts)


# --- .gitignore and README -----------------------------------------------------


def test_gitignore_override_only():  # AC18
    lines = read(".gitignore").splitlines()
    assert [line for line in lines if line.startswith("compose.override")] == ["compose.override.yaml"]


def test_readme_docker_quick_start():  # AC19
    readme = read("README.md")
    assert "cp compose.override.example.yaml compose.override.yaml && docker compose up --build" in readme
    assert "http://127.0.0.1:3000" in readme
