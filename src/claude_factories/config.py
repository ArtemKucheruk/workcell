"""Env and limits (docs/MVP.md §4.7)."""

import os
from pathlib import Path

MAX_PATCH = 5 * 1024 * 1024  # 005 Q5: UTF-8 bytes of the patch alone
MAX_VIEW = 1024 * 1024  # 016 Q5: over this many bytes, the code page doesn't show a file


def data_dir() -> Path:
    return Path(os.environ.get("FCTL_HOME") or Path.home() / ".claude-factories")
