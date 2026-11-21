"""029: the shipped src/claude_factories/fctl.md against the real CLI. A section is the markdown from a `##`
heading to the next one, found from markdown-it's tokens, since heredoc examples can hold `##` lines."""

import argparse
import re
from pathlib import Path

import pytest

from claude_factories.cli.main import build_parser
from claude_factories.lib.markdown import MD, render_with_headings

REPO = Path(__file__).resolve().parents[1]
FCTL_MD = REPO / "src" / "claude_factories" / "fctl.md"
LABELS = ("**Synopsis**", "**Arguments and flags**", "**Stdin**", "**Output**", "**Exit codes and errors**",
          "**Called by**", "**Example**")
STDIN = ("context set", "submit", "spec", "verdict", "comment", "decide", "task add")  # 060 BE7: task add


def walk(parser: argparse.ArgumentParser, words: tuple = ()) -> dict[str, argparse.ArgumentParser]:
    """Q11: "context set" → its parser, for every parser with a `func` default, through every nested
    subparsers action (private argparse API, stable)."""
    found = {" ".join(words): parser} if parser.get_default("func") else {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found |= walk(sub, (*words, name))
    return found


COMMANDS = walk(build_parser())


def sections() -> dict[str, str]:
    """Level-2 heading id → its section's markdown, cut at each h2 heading_open's map."""
    text = FCTL_MD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    starts = [t.map[0] for t in MD.parse(text) if t.type == "heading_open" and t.tag == "h2"]
    ids = [h["id"] for h in render_with_headings(text)[1] if h["level"] == 2]
    assert len(ids) == len(starts)
    bounds = [*starts, len(lines)]
    return {i: "".join(lines[a:b]) for i, a, b in zip(ids, bounds, bounds[1:])}


SECTIONS = sections()


def section(words: str) -> str:
    return SECTIONS["fctl-" + words.replace(" ", "-")]


def test_every_command_has_a_section(client):  # AC7
    assert {"serve", "setup", "context", "context set", "task add", "run", "submit", "round"} <= set(COMMANDS)
    assert "task" not in COMMANDS
    headings = client.get("/api/docs/fctl").json()["headings"]
    for words in COMMANDS:
        heading = {"id": "fctl-" + words.replace(" ", "-"), "text": f"fctl {words}", "level": 2}
        assert heading in headings, words


def test_no_stale_section(client):  # AC8
    headings = client.get("/api/docs/fctl").json()["headings"]
    named = [h["text"] for h in headings if h["level"] == 2 and h["text"].startswith("fctl ")]
    assert named and all(text.removeprefix("fctl ") in COMMANDS for text in named)


@pytest.mark.parametrize("words", COMMANDS)
def test_section_layout(words):  # AC9, Q5
    body = section(words)
    at = [body.find(label) for label in LABELS]
    assert -1 not in at and at == sorted(at), words
    assert body[at[-1] + len(LABELS[-1]):].lstrip().startswith("```sh\n"), words


@pytest.mark.parametrize("words", COMMANDS)
def test_section_names_every_flag_and_choice(words):  # AC10
    body = section(words)
    for action in COMMANDS[words]._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue  # context's `set` has its own section
        for option in action.option_strings:
            if option not in ("-h", "--help"):
                assert option in body, (words, option)
        for choice in action.choices or ():
            assert str(choice) in body, (words, choice)


def test_flag_check_sees_these():  # AC10: the walk reaches the flags the spec names
    options = {o for p in COMMANDS.values() for a in p._actions for o in a.option_strings}
    assert options >= {"--workspace", "--test-cmd", "--round", "--feedback", "--path", "--line", "--new", "--title",
                       "--run", "--host", "--port"}


def test_stdin_commands_show_heredocs():  # AC11
    for words in STDIN:
        assert "<<'EOF'" in section(words), words
    submit = section("submit")
    assert "fctl submit --new --title" in submit
    assert re.search(r"fctl submit \d+ <<'EOF'", submit)


def test_install_and_environment():  # AC12, Q3
    install, env = SECTIONS["install"], SECTIONS["fctl-url-and-fctl-home"]
    assert "uv tool install" in install and "fctl setup" in install
    for text in ("FCTL_URL", "http://127.0.0.1:4545", "FCTL_HOME", "~/.claude-factories"):
        assert text in env, text


def test_docker():  # AC13, Q13
    docker = SECTIONS["using-fctl-with-docker"]
    for text in ("compose.override.yaml", "127.0.0.1:4545", "fctl-home"):
        assert text in docker, text


def test_exit_codes():  # AC14, Q12
    codes = SECTIONS["exit-codes-and-errors"]
    for text in ("`0`", "`1`", "`2`", "fctl: ", 'is "fctl serve" running?'):
        assert text in codes, text


def test_claude_code_links_the_page():  # AC15
    doc = (REPO / "docs" / "claude-code.md").read_text()
    start = doc.index("### 7.2 Commands")
    commands = doc[start:doc.index("### 7.3", start)]
    assert "/docs/fctl" in commands
    assert "](../src/claude_factories/fctl.md)" in commands


def test_claude_code_task_add_row():  # 060 BE8, 094 AC21
    doc = (REPO / "docs" / "claude-code.md").read_text()
    start = doc.index("### 7.2 Commands")
    commands = doc[start:doc.index("### 7.3", start)]
    [row] = [line for line in commands.splitlines() if line.startswith("| `fctl task add")]
    assert row.startswith('| `fctl task add "title" [--description TEXT] [--blocked-by IDS] [--run]`')
    assert "`--description -`" in row and "`description_md`" in row.split("|")[3]
    assert "`blocked_by`" in row.split("|")[3]


def test_task_block_sections():  # 094 AC21: the new commands' rows, and fctl run's new 409s
    doc = (REPO / "docs" / "claude-code.md").read_text()
    commands = doc[doc.index("### 7.2 Commands"):doc.index("### 7.3")]
    for words, method in (("block", "PUT"), ("unblock", "DELETE")):
        [row] = [line for line in commands.splitlines() if line.startswith(f"| `fctl task {words} <id> --by <id>`")]
        assert f"`{method} /api/tasks/{{id}}/blocked-by/{{blocker}}`" in row
        assert f"fctl task {words} <id> --by <id>" in section(f"task {words}")
    assert "--blocked-by IDS" in section("task add")
    run = section("run")
    assert "409 #15 is blocked by #12, #14; finish those first or remove the dependency" in run
    assert "409 all backlog tasks are blocked: #15 waits on #12, #14" in run


def test_task_delete_section():  # 105 AC16, AC18
    body = section("task delete")
    for text in ("fctl task delete <id> [--yes]", "`--yes`", "Deleted #14 Export CSV", "fctl: 404 Not Found",
                 "fctl: 409 run #41 active", "fctl: not deleted", "pass --yes to delete #14 without asking"):
        assert text in body, text
    doc = (REPO / "docs" / "claude-code.md").read_text()
    commands = doc[doc.index("### 7.2 Commands"):doc.index("### 7.3")]
    [row] = [line for line in commands.splitlines() if line.startswith("| `fctl task delete <id> [--yes]`")]
    assert row == ("| `fctl task delete <id> [--yes]` | me | `DELETE /api/tasks/{id}` (after `GET /api/tasks/{id}` for"
                   " the title) |")
    api = (REPO / "docs" / "data-model-and-api.md").read_text()
    assert "(board Delete, fctl task delete 14)" in api


def test_run_account_section():  # 097 AC33
    run = section("run")
    for text in ("fctl run <id> [--account <id|email>]", "Run #41 on #12 as b@y →",
                 "409 all accounts near their limits: a@x 5h 92% (resets 14:10)",
                 "409 Claude account b@y isn't logged in to claude.ai", "422 no Claude account #99",
                 "fctl: no Claude account b@y", "--account` with `next`"):
        assert text in run, text


def test_automation_run_section():  # 102 AC22; the parametrized tests above check its labels and flags
    body = section("automation run")
    for text in ("fctl automation run <id> [--account <id|email>]", "POST /api/factories/{id}/run",
                 "Run #43 of automation #7 as b@y in .claude/worktrees/automation-security-audit-1a2b3c4d →",
                 "404 Factory #99 not found",
                 "is a workflow; run it on a task from the board", "#43 on automation Security audit",
                 "isn't committed on main: open it, Files → Write to repo"):
        assert text in body, text
    doc = (REPO / "docs" / "claude-code.md").read_text()
    commands = doc[doc.index("### 7.2 Commands"):doc.index("### 7.3")]
    assert "| `fctl automation run <id> [--account <id\\|email>]`" in commands


def test_seed_section_and_home():  # 038 AC37; the parametrized tests above check its labels and sh example
    assert "seed" in COMMANDS
    assert "fctl seed" in section("seed")
    [row] = [line for line in SECTIONS["fctl-url-and-fctl-home"].splitlines() if line.startswith("| `FCTL_HOME` |")]
    assert "`fctl seed`" in row.split("|")[3]
