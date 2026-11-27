"""Env and limits (docs/MVP.md §4.7)."""

import os
import sys
from pathlib import Path

MAX_PATCH = 5 * 1024 * 1024  # 005 Q5: UTF-8 bytes of the patch alone
MAX_VIEW = 1024 * 1024  # 016 Q5: over this many bytes, the code page doesn't show a file
MAX_CONTEXT = 16 * 1024  # 033 Q4: UTF-8 bytes of a project's context_md, and 057 of each context card's
MAX_CONTEXT_TOTAL = 64 * 1024  # 057 Q4: UTF-8 bytes of context_md plus every card's content_md, per project
MAX_CONTEXT_FILES = 50  # 057: the files one folder read (from-path) may take
MAX_BUNDLE = 50 * 1024 * 1024  # 032 Q7: the raw body of a task bundle import
MAX_UNPACKED = 500 * 1024 * 1024  # 032 Q7: the sum of a bundle's declared file sizes
MAX_GRAPH = 256 * 1024  # 051 rule 1: UTF-8 bytes of a factory graph's compact JSON as stored


HOME = ".workcell"
OLD_HOME = ".claude-factories"  # 116 Q4: the data dir before the rename, read only by migrate_home


def data_dir() -> Path:
    return Path(os.environ.get("FCTL_HOME") or Path.home() / HOME)


def migrate_home() -> None:
    """116 AC5-AC8: with FCTL_HOME unset, move a real ~/.claude-factories to a missing ~/.workcell once.
    Q1: the old path becomes a symlink to the new one, so every stored absolute path (an account's
    config_dir, a run's log_path, worktrees) still resolves, and no row is rewritten.
    cli/services.py repeats this for `fctl service install` (Q2)."""
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


def claude_config_dir() -> Path:
    """030: where Claude Code keeps its transcripts, `projects/<folder>/<session_id>.jsonl`."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def in_docker() -> bool:
    """028 Q6: the backend image sets FCTL_IN_DOCKER=1; only that exact value counts."""
    return os.environ.get("FCTL_IN_DOCKER") == "1"
