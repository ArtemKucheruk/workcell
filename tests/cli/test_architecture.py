import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
CLI = SRC / "claude_factories" / "cli"


def inside_cli(name: str) -> bool:
    return name == "claude_factories.cli" or name.startswith("claude_factories.cli.")


def module_level_imports(node):
    """The import statements that run at import time: all but those in function bodies (Q3)."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            yield child
        elif not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from module_level_imports(child)


def violations(source: str, path: Path) -> list[str]:
    """`source`'s module-level imports, as if it lived at `path`, that are neither stdlib nor inside
    claude_factories.cli, as `file:line name`."""
    package = ".".join(path.relative_to(SRC).parent.parts)  # also right for __init__.py
    bad = []
    for node in module_level_imports(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            names = [importlib.util.resolve_name("." * node.level + (node.module or ""), package)]
        bad += [f"{path.relative_to(SRC)}:{node.lineno} {name}" for name in names
                if name.split(".")[0] not in sys.stdlib_module_names and not inside_cli(name)]
    return bad


def test_cli_imports_only_stdlib():  # AC12 (001 AC3, tightened to claude_factories.cli.*)
    code = (
        "import sys; before = set(sys.modules); import claude_factories.cli.main; "
        "print('\\n'.join(sorted(set(sys.modules) - before)))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    added = r.stdout.split()
    assert "claude_factories.cli.main" in added
    bad = [
        m
        for m in added
        if m.split(".")[0] not in sys.stdlib_module_names and m != "claude_factories" and not inside_cli(m)
    ]
    assert bad == []


def test_cli_modules_import_only_stdlib_or_cli():  # AC13
    files = sorted(CLI.rglob("*.py"))
    assert CLI / "main.py" in files and CLI / "commands" / "agent.py" in files
    assert [v for f in files for v in violations(f.read_text(), f)] == []


@pytest.mark.parametrize("source, flagged", [
    ("import fastapi\n", True),
    ("from .. import app\n", True),
    ("from claude_factories import db\n", True),
    ("def serve():\n    import uvicorn\n", False),
    ("import os.path\nfrom urllib import parse\n", False),
    ("from .commands.agent import REVIEWERS\nfrom . import client\n", False),
])
def test_checker_flags_samples(source, flagged):  # AC14
    assert bool(violations(source, CLI / "main.py")) == flagged
