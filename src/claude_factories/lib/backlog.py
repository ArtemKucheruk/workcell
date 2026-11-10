"""058: factory/backlog.md's checkbox lines as backlog-only jobs, pure (Q1–Q3)."""

import re

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}")  # 031 Q7: every id on today's board
LINE = re.compile(r"- \[([ xX])\] ([^\s:]+):(\s.*)?")  # Q1: `- [ ] <id>: <text>`, `[x]` and `[X]` done


def title(job_id: str) -> str:
    """Q3: no leading `<digits>-`, dashes as spaces, the first character upper-cased; the id if nothing's left."""
    words = re.sub(r"^[0-9]+-", "", job_id).replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else job_id


def parse(text: str) -> tuple[list[dict], int]:
    """([{id, done, title, description_md}] in file order, the count of checkbox lines skipped). Q1: a checkbox
    line (`- [`) is skipped when it isn't `- [ ] <id>: <text>`, its id fails 031's check, or its id came earlier
    (the first wins). Q2: each takes the nearest `## ` heading above it; other lines are ignored."""
    lines, seen, skipped, section = [], set(), 0, ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("- ["):
            m = LINE.fullmatch(line)
            if not m or not ID.fullmatch(m[2]) or m[2] in seen:
                skipped += 1
                continue
            seen.add(m[2])
            body = (m[3] or "").strip()
            lines.append({"id": m[2], "done": m[1] != " ", "title": title(m[2]),
                          "description_md": f"## {section}\n\n{body}" if section else body})
    return lines, skipped
