"""008: a round_files patch → display rows, and paths → a file tree. No app, no database."""

import re

# at most 18 digits: int() refuses a 4300+ digit string, and no file has 10**18 lines (security review)
HUNK = re.compile(r"@@ -(\d{1,18})(?:,\d+)? \+(\d{1,18})(?:,\d+)? @@")


def diff_rows(patch: str) -> list[dict]:
    """008 Q5: one round_files.patch → display rows (hunk, ctx, add, del, note), with old and new
    line numbers and the text without its sign or one trailing \\r. Header lines get no row."""
    rows, old, new, in_hunk = [], 0, 0, False
    lines = patch.split("\n")
    if lines[-1] == "":  # the empty string after the final \n
        lines.pop()
    for line in lines:
        line = line.removesuffix("\r")
        if line.startswith("diff --git "):  # 005's merged typechange sections
            in_hunk = False
        elif m := HUNK.match(line):
            old, new, in_hunk = int(m[1]), int(m[2]), True
            rows.append({"kind": "hunk", "old": None, "new": None, "text": line})
        elif not in_hunk:
            continue
        elif line.startswith("+"):
            rows.append({"kind": "add", "old": None, "new": new, "text": line[1:]})
            new += 1
        elif line.startswith("-"):
            rows.append({"kind": "del", "old": old, "new": None, "text": line[1:]})
            old += 1
        elif line.startswith("\\"):
            rows.append({"kind": "note", "old": None, "new": None, "text": line})
        else:
            rows.append({"kind": "ctx", "old": old, "new": new, "text": line[1:]})
            old, new = old + 1, new + 1
    return rows


def file_tree(files: list[dict]) -> dict:
    """008 Q6: {"dir/": {...}, "name": file} in patch order; a directory sits where its first file is."""
    root: dict = {}
    for f in files:
        *dirs, name = f["path"].split("/")
        node = root
        for d in dirs:
            node = node.setdefault(d + "/", {})
        node[name] = f
    return root
