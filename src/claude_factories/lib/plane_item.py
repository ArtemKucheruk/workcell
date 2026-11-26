"""109: a Plane work item's `tasks.import_key` (`plane:<slug>/<project id>/<item id>`) and an imported task's
description (docs/data-model-and-api.md §5.1). Pure."""

import re

KEY = re.compile(r"plane:([^/\s]+)/([^/\s]+)/([^/\s]+)")


def key(slug: str, project_id: str, item_id: str) -> str:
    return f"plane:{slug}/{project_id}/{item_id}"


def parse_key(import_key: str | None) -> tuple[str, str, str] | None:
    """Q3: (slug, project id, item id) of a `plane:` key; None for any other key, or none."""
    found = KEY.fullmatch(import_key) if import_key else None
    return (found[1], found[2], found[3]) if found else None


def description(text: str | None, identifier: str, sequence_id: int) -> str:
    """AC9, Q5: `description_stripped` right-stripped, a blank line, then the source line; only that line when the
    description is empty."""
    body = (text or "").rstrip()
    line = f"Plane work item: {identifier}-{sequence_id}"
    return f"{body}\n\n{line}" if body else line
