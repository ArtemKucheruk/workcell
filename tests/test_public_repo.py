"""114: the repo is ready to go public: MIT license, README for a first-time user, no personal or
machine-specific data in tracked files, and docs that match the CLI."""

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from claude_factories.cli.main import build_parser

REPO = Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")
# 114 AC6: the retired bootstrap factory. The build couldn't delete these (no approval for rm); until
# they are gone they are the only files allowed to hold the old links and local paths.
PENDING_DELETE = ("factory/", "FACTORY.md", "MVP_DOCS_PROMPT.md", ".claude/agents/builder-backend.md",
                  ".claude/agents/builder-frontend.md")
HOME = "/" + "Users/"  # split so this file doesn't match itself


def tracked() -> dict[str, str]:
    """Every tracked file that still exists, minus PENDING_DELETE, as {path: text}."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    files = {}
    for rel in filter(None, out.split("\0")):
        path = REPO / rel
        if rel.startswith(PENDING_DELETE) or not path.is_file():
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return files


def walk(parser: argparse.ArgumentParser, words: tuple = ()) -> dict[str, argparse.ArgumentParser]:
    """Every runnable command ("task add") and every group ("task") → its parser."""
    found = {" ".join(words): parser} if words else {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found |= walk(sub, (*words, name))
    return found


PARSER = build_parser()
COMMANDS = walk(PARSER)


def options(parser: argparse.ArgumentParser) -> set[str]:
    return {o for a in parser._actions for o in a.option_strings}


def sections(text: str) -> list[str]:
    return re.findall(r"^## (.+)$", text, re.M)


def section(text: str, heading: str) -> str:
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start:end if end > 0 else None]


def test_license_file():  # AC1
    text = (REPO / "LICENSE").read_text()
    assert text.startswith("MIT License\n")
    assert "Copyright (c) 2026 Artem Kucheruk" in text.splitlines()
    assert "Permission is hereby granted, free of charge" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND' in text


def test_pyproject_license():  # AC2: uv sync and this very test run build it with uv_build
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert data["project"]["license"] == "MIT"
    assert data["build-system"]["build-backend"] == "uv_build"


def test_frontend_license():  # AC3: npm ci in the test command checks the lockfile against package.json
    assert json.loads((REPO / "frontend" / "package.json").read_text())["license"] == "MIT"
    lock = json.loads((REPO / "frontend" / "package-lock.json").read_text())
    assert lock["packages"][""]["license"] == "MIT"


@pytest.mark.xfail(strict=True, reason="114 AC6: rm was denied in the build session. Delete PENDING_DELETE by hand; "
                                       "this then XPASSes and fails: drop this marker and PENDING_DELETE")
def test_bootstrap_files_are_deleted():  # AC6: the tripwire that ends the exemption above
    assert [p for p in PENDING_DELETE if (REPO / p).exists()] == []


def test_nothing_reads_the_bootstrap_files():  # AC5
    reads = re.compile(r'(REPO|ROOT)\s*/\s*"(FACTORY\.md|MVP_DOCS_PROMPT\.md|factory)"')
    found = [rel for rel, text in tracked().items()
             if rel.startswith(("src/", "tests/")) and rel.endswith(".py") and reads.search(text)]
    assert found == []


def test_no_links_to_the_bootstrap_files():  # AC6: import-feature code and tests may name factory/ files
    found = [f"{rel}: {pat}" for rel, text in tracked().items() if not rel.startswith(("src/", "tests/", "frontend/src/"))
             for pat in ("FACTORY.md", "MVP_DOCS_PROMPT", "](factory/") if pat in text]
    assert found == []
    assert ".claude/skills/factory/SKILL.md" in tracked()


def test_no_home_paths():  # AC7
    assert [rel for rel, text in tracked().items() if HOME in text] == []
    assert "/path/to/code:/path/to/code" in (REPO / "compose.override.example.yaml").read_text()


def test_no_personal_email():  # AC8
    gmail = re.compile(r"[A-Za-z0-9._%+-]+@" + "gmail" + r"\.com")
    found = [rel for rel, text in tracked().items() if "na.test" + ".pochta" in text.lower()]
    found += [f"{rel}: {m}" for rel, text in tracked().items() if rel != "pyproject.toml" for m in gmail.findall(text)]
    assert found == []
    authors = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["authors"]
    assert [a["email"] for a in authors if gmail.fullmatch(a["email"])] == [a["email"] for a in authors]


def test_gitignore():  # AC9
    lines = (REPO / ".gitignore").read_text().splitlines()
    for line in (".env", "compose.override.yaml", ".fctl/", ".claude/worktrees/", "*.db"):
        assert line in lines, line
    assert not [line for line in lines if line.startswith("factory/")]  # the jobs/ and board.json lines
    assert "/factory/" in lines  # the retired dir as a whole, so old local job logs can't be added again


def test_claude_dir_is_not_machine_local():  # AC10
    claude = {rel: text for rel, text in tracked().items() if rel.startswith(".claude/")}
    assert ".claude/skills/factory/SKILL.md" in claude
    assert not [rel for rel in claude if rel.endswith("settings.local.json") or rel.startswith(".claude/worktrees/")]
    assert [rel for rel, text in claude.items() if HOME in text or "/home/" in text or "@" + "gmail" in text] == []


def test_readme_sections_in_order():  # AC11
    want = ["Requirements", "Install", "Run the app", "Connect a repo", "A first task and run", "Security", "License"]
    heads = sections(README)
    assert [h for h in heads if h in want] == want
    assert README.index("A local control center") < README.index("## Requirements")  # what it is, first
    reqs = section(README, "Requirements")
    for text in ("Python 3.12", "uv", "Node 22", "npm", "git", "worktrunk", "`wt`", "Claude Code",
                 "Claude subscription"):
        assert text in reqs, text
    run = section(README, "Run the app")
    for text in ("fctl service install", "fctl serve", "docker compose up --build"):
        assert text in run, text
    lic = section(README, "License")
    assert "MIT" in lic and "not affiliated with or endorsed by Anthropic" in lic


def test_readme_describes_the_app_as_it_is():  # AC12
    for text in ("Status: early", "What it will be", "Running the bootstrap factory", "dashboard.html",
                 "http.server", "After backlog job 015", "/factory next", "round-N/", "board.json"):
        assert text not in README, text
    assert not [line for line in section(README, "Layout").splitlines() if line.startswith(("FACTORY.md", "factory/"))]


def test_readme_security_note():  # AC13
    sec = " ".join(section(README, "Security").split())
    for text in ("no auth", "127.0.0.1", "`Host`", "`X-Requested-By: fctl`",
                 "Claude Code agents with shell access inside your repos"):
        assert text in sec, text


def fctl_uses(text: str) -> list[tuple[str, list[str]]]:
    """Every `fctl …` in the README's code spans and blocks → (command, its flags)."""
    blocks = re.findall(r"^```.*?\n(.*?)^```", text, re.M | re.S)
    spans = re.findall(r"`([^`\n]+)`", re.sub(r"^```.*?^```", "", text, flags=re.M | re.S))
    uses = []
    for code in [*blocks, *spans]:
        code = re.sub(r'"[^"\n]*"', '""', code)  # a quoted argument ("pytest -q") isn't a flag
        for m in re.finditer(r"(?:^|\s)fctl((?:[ \t]+[^\s#|&;`]+)*)", code, re.M):
            tokens = m.group(1).split()
            words = " ".join(t for t in tokens[:2] if not t.startswith("-"))
            while words and words not in COMMANDS:
                words = words.rpartition(" ")[0]
            uses.append((words, [t for t in tokens if t.startswith("-")]))
    return uses


def test_readme_fctl_commands_exist():  # AC14
    uses = fctl_uses(README)
    used = {w for w, _ in uses}
    assert {"serve", "service install", "setup", "connect", "task add", "run", "show", "approve", "rework"} <= used
    for words, flags in uses:
        parser = COMMANDS[words] if words else PARSER
        assert set(flags) <= options(parser), (words, flags)


def test_every_command_is_in_the_guides():  # AC15: docs/fctl_docs and claude-code.md §7.2 list every command
    runnable = [w for w, p in COMMANDS.items() if p.get_default("func")]
    guide = (REPO / "docs" / "fctl_docs" / "commands.md").read_text()
    cc = (REPO / "docs" / "claude-code.md").read_text()
    table = cc[cc.index("### 7.2"):cc.index("### 7.3")]
    for words in runnable:
        group, _, sub = words.partition(" ")
        if group == "service":  # both list the service subcommands as one `install|uninstall|…` row
            assert sub in guide and sub in table, words
            continue
        assert f"fctl {words}" in guide, words
        assert f"`fctl {words}" in table, words
