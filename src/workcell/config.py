"""Env and limits (docs/MVP.md §4.7)."""

import os
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


def data_dir() -> Path:
    return Path(os.environ.get("FCTL_HOME") or Path.home() / HOME)


def claude_config_dir() -> Path:
    """030: where Claude Code keeps its transcripts, `projects/<folder>/<session_id>.jsonl`."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def in_docker() -> bool:
    """028 Q6: the backend image sets FCTL_IN_DOCKER=1; only that exact value counts."""
    return os.environ.get("FCTL_IN_DOCKER") == "1"
