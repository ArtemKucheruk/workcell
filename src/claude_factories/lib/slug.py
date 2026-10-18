"""012 Q3: a task title → its worktree and branch name part. No app, no database."""

import re


def slug(title: str) -> str:
    """Q3: `Rate-limit login endpoint` → `rate-limit-login`; nothing left → `task`."""
    return "-".join(re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-").split("-")[:3]) or "task"
