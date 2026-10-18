"""docs/MVP.md §4.7: the layout's docs, and its rules read from every module with ast (034)."""

import ast
import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
PKG = SRC / "claude_factories"
ALLOWED = {  # §4.7's table: what each layer may import besides itself; app.py for server/ until 036
    "server": {"controllers", "repositories", "adapters", "db", "config", "domain", "app"},
    "controllers": {"handlers", "dto", "domain", "server.deps"},
    "handlers": {"repositories", "adapters", "dto", "domain", "lib", "config"},
    "repositories": {"db", "domain", "config"},
    "adapters": {"domain", "config"},
    "dto": {"domain"},
    "db": {"config"},
    "lib": {"domain"},
}
SQL_CALLS = {"execute", "executemany", "executescript"}
SQL = re.compile(r"\bSELECT\b.*\bFROM\b|\bINSERT INTO\b|\bUPDATE\b.*\bSET\b|\bDELETE FROM\b", re.S)  # Q2


def checked() -> list[Path]:
    """Every module but app.py (exempt until 036) and cli/ (tests/cli/test_architecture.py, Q3)."""
    return sorted(p for p in PKG.rglob("*.py") if p != PKG / "app.py" and not p.is_relative_to(PKG / "cli"))


def layer(path: Path) -> str:
    """handlers/factory.py → handlers, config.py → config."""
    return path.relative_to(PKG).parts[0].removesuffix(".py")


def imported(tree: ast.AST, path: Path) -> list[tuple[int, str]]:
    """(line, absolute name) of every import anywhere in the module, function bodies included (Q3).
    `from .. import db` is claude_factories.db."""
    package = ".".join(path.relative_to(SRC).parent.parts)  # also right for __init__.py
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
            found += [(node.lineno, f"{base}.{a.name}") for a in node.names]
    return found


def wrong_edges(tree: ast.AST, path: Path) -> list[str]:
    allowed = ALLOWED.get(layer(path), set()) | {layer(path)}
    return [f"{path.relative_to(PKG)}:{line} imports {name}" for line, name in imported(tree, path)
            if name.startswith("claude_factories.")
            and not any(f"{name}.".startswith(f"claude_factories.{a}.") for a in allowed)]


def fastapi_outside(tree: ast.AST, path: Path) -> list[str]:
    if layer(path) in ("server", "controllers"):
        return []
    return [f"{path.relative_to(PKG)}:{line} imports {name}" for line, name in imported(tree, path)
            if name.split(".")[0] in ("fastapi", "starlette")]


def sql_outside(tree: ast.AST, path: Path) -> list[str]:
    if layer(path) in ("repositories", "db"):
        return []
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in SQL_CALLS:
            bad.append(f"{path.relative_to(PKG)}:{node.lineno} calls .{node.func.attr}()")
        text = (node.value if isinstance(node, ast.Constant) and isinstance(node.value, str)
                else "".join(v.value for v in node.values if isinstance(v, ast.Constant))
                if isinstance(node, ast.JoinedStr) else "")
        if SQL.search(text):
            bad.append(f"{path.relative_to(PKG)}:{node.lineno} has SQL {text[:40]!r}")
    return bad


def section(text: str, heading: str, end: str) -> str:
    start = text.index(heading)
    return text[start:text.index(end, start + len(heading))]


# --- The docs ----------------------------------------------------------------------


def test_mvp_code_layout_section():  # AC1
    mvp = (REPO / "docs" / "MVP.md").read_text()
    assert mvp.index("\n### 4.6 ") < mvp.index("\n### 4.7 Code layout\n") < mvp.index("\n## 9.")
    body = section(mvp, "\n### 4.7 Code layout\n", "\n## 9.")
    tree = body.split("```")[1]
    entries = {line.lstrip("│├└─ ").split()[0] for line in tree.strip().splitlines()[1:]}
    assert entries >= {"server/", "controllers/", "pages/", "handlers/", "dto/", "repositories/", "adapters/",
                       "git.py", "claude.py", "domain/", "lib/", "db/", "config.py", "cli/"}


def test_conventions_point_at_layout():  # AC2
    stack = section((REPO / "FACTORY.md").read_text(), "## The repo and its stack\n", "\n## ")
    assert "docs/MVP.md §4.7" in stack
    assert "tests/test_architecture.py" in stack
    review = (REPO / ".claude" / "agents" / "review-code.md").read_text()
    assert "docs/MVP.md §4.7" in section(review, "\nCheck:\n", "\n\n")


# --- The tree ----------------------------------------------------------------------


def test_tree_follows_the_rules():  # AC16
    found = []
    for path in checked():
        tree = ast.parse(path.read_text())
        found += wrong_edges(tree, path) + fastapi_outside(tree, path) + sql_outside(tree, path)
    assert found == []


def test_checked_files():  # AC16
    files = checked()
    for rel in ("server/app.py", "handlers/factory.py", "repositories/projects.py"):
        assert PKG / rel in files
    assert PKG / "app.py" not in files
    assert not [f for f in files if f.is_relative_to(PKG / "cli")]


# --- The checks, on samples ----------------------------------------------------------


def check(checker, where: str, source: str) -> bool:
    """Whether `checker` flags `source` as a module in the `where` layer."""
    return bool(checker(ast.parse(source), PKG / where / "sample.py"))


@pytest.mark.parametrize("where, source, flagged", [
    ("handlers", "from ..controllers import projects\n", True),
    ("repositories", "from ..handlers import factory\n", True),
    ("domain", "from claude_factories.repositories import projects\n", True),
    ("lib", "from .. import db\n", True),
    ("controllers", "from ..server import app\n", True),
    ("handlers", "from ..repositories.projects import ProjectsRepo\n", False),
    ("handlers", "from ..domain.errors import NotFound\n", False),
    ("controllers", "from ..server.deps import Projects\n", False),
])
def test_direction_check(where, source, flagged):  # AC17
    assert check(wrong_edges, where, source) == flagged


@pytest.mark.parametrize("where, source, flagged", [
    ("handlers", "from fastapi import HTTPException\n", True),
    ("handlers", "def f():\n    from fastapi import HTTPException\n", True),
    ("dto", "import starlette.responses\n", True),
    ("controllers", "from fastapi import APIRouter\n", False),
    ("server", "from fastapi import APIRouter\n", False),
])
def test_fastapi_check(where, source, flagged):  # AC18
    assert check(fastapi_outside, where, source) == flagged


@pytest.mark.parametrize("where, source, flagged", [
    ("handlers", "conn.execute(q)\n", True),
    ("server", '"SELECT id FROM projects"\n', True),
    ("handlers", 'f"SELECT {columns} FROM projects"\n', True),
    ("repositories", "conn.execute(q)\n", False),
    ("repositories", '"SELECT id FROM projects"\n', False),
    ("db", "conn.execute(q)\n", False),
    ("db", '"SELECT id FROM projects"\n', False),
    ("handlers", 'def f():\n    """Select the project."""\n', False),
])
def test_sql_check(where, source, flagged):  # AC19
    assert check(sql_outside, where, source) == flagged
