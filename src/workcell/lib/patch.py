"""docs/claude-code.md §7.4: a `git diff` patch → one round_files row per file (005 Q6). No app, no database."""

import codecs
import re

from ..domain.errors import Invalid

PATCH_NAMES = {"rename from ": "from", "rename to ": "to", "--- ": "old", "+++ ": "new"}


def unquote(name: str) -> str:
    """Q6: git C-quotes a name holding `"`, `\\`, or control bytes; octal escapes are UTF-8 bytes."""
    if len(name) < 2 or name[0] != '"' or name[-1] != '"':
        return name
    try:
        return codecs.escape_decode(name[1:-1].encode())[0].decode(errors="replace")
    except ValueError:  # a trailing `\` or a bad `\x`: "" makes the caller's 422
        return ""


def safe_path(path: str | None) -> bool:
    """Git never writes an empty, absolute, `..`, or NUL path; refuse them before pages link to it."""
    return bool(path) and not path.startswith("/") and "\0" not in path and ".." not in path.split("/")


def parse_section(section: str) -> dict:
    """Q6: one `diff --git` section → its round_files row."""
    header, *lines = section.split("\n")
    row = {"path": None, "old_path": None, "change": "modified", "binary": 0, "additions": 0,
           "deletions": 0, "patch": section}
    names, in_hunks = {}, False
    for line in lines:
        if in_hunks:
            row["additions"] += line.startswith("+")
            row["deletions"] += line.startswith("-")
        elif line.startswith("@@"):
            in_hunks = True
        elif line.startswith("new file mode "):
            row["change"] = "added"
        elif line.startswith("deleted file mode "):
            row["change"] = "deleted"
        elif line.startswith("Binary files ") and line.endswith(" differ"):
            row["binary"] = 1
        else:
            for prefix, key in PATCH_NAMES.items():
                if line.startswith(prefix):  # git adds a tab after a name with a space
                    names[key] = unquote(line[len(prefix):].removesuffix("\t"))
    new, old = names.get("new", "/dev/null"), names.get("old", "/dev/null")
    if "to" in names:
        row.update(path=names["to"], old_path=names.get("from"), change="renamed")
    elif new != "/dev/null":
        row["path"] = new.removeprefix("b/") if new.startswith("b/") else None
    elif old != "/dev/null":
        row["path"] = old.removeprefix("a/") if old.startswith("a/") else None
    else:  # mode-only, binary, or empty: `diff --git a/X b/X`, split at its midpoint
        pair = header.removeprefix("diff --git ")
        mid = len(pair) // 2
        a, b = unquote(pair[:mid]), unquote(pair[mid + 1:])
        if pair[mid:mid + 1] == " " and a[:2] == "a/" and b[:2] == "b/" and a[2:] == b[2:]:
            row["path"] = a[2:]
    if not safe_path(row["path"]) or (row["change"] == "renamed" and not safe_path(row["old_path"])):
        raise Invalid(f"can't read a safe file path in: {header[:200]}")
    return row


def split_patch(patch: str) -> list[dict]:
    """Q6: one row per file, in patch order. Sections split on \\n only, so joined they give the
    patch back byte for byte."""
    if not patch.startswith("diff --git "):
        raise Invalid('patch must start with "diff --git"')
    rows: dict[str, dict] = {}
    for section in re.split(r"(?m)^(?=diff --git )", patch)[1:]:
        row = parse_section(section)
        if seen := rows.get(row["path"]):  # git splits a file <-> symlink typechange in two
            seen.update(change="modified", old_path=None, binary=seen["binary"] | row["binary"],
                        additions=seen["additions"] + row["additions"],
                        deletions=seen["deletions"] + row["deletions"], patch=seen["patch"] + row["patch"])
        else:
            rows[row["path"]] = row
    return list(rows.values())
