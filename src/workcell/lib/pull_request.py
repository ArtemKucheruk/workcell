"""093: Create PR's body, a PR's checks as counts, and a PR's number from its URL. Pure."""

import re

from ..domain.enums import Reviewer

PULL = re.compile(r"/pull/([0-9]{1,9})\b")  # 031 Q6, 093 Q3: a PR's number in its URL
BLANK_LINE = re.compile(r"\n[ \t]*\n")
# AC24: gh's statusCheckRollup conclusions (CheckRun) and states (StatusContext); anything else is pending
PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILED = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def pr_number(url: str | None) -> int | None:
    """Q3: N of a `/pull/N` URL; None without one."""
    found = PULL.search(url) if url else None
    return int(found[1]) if found else None


def pr_body(description_md: str, rounds: int, latest: int | None, verdicts: dict[str, str],
            approver: tuple[str, str] | None, task_url: str, closes: str | None = None) -> str:
    """AC20: the description's first paragraph (left out if blank), `Rounds: <count>`, round `latest`'s verdicts in
    reviewer order (`pending` for a missing one; left out with no round), the approver's latest decision with its
    body (left out with none), and the task's app URL, as paragraphs. No attribution. 108 AC24: `closes`, e.g.
    `Closes #12`, is a final paragraph."""
    first = BLANK_LINE.split(description_md.strip().replace("\r\n", "\n"), maxsplit=1)[0].strip()
    parts = [first] if first else []
    parts.append(f"Rounds: {rounds}")
    if latest is not None:
        parts.append(f"Verdicts (round {latest}): " + " · ".join(f"{who} {verdicts.get(who, 'pending')}"
                                                                  for who in Reviewer))
    if approver:
        decision, body = approver
        parts.append(f"Approver: {decision}" + (f" — {body.strip()}" if body.strip() else ""))
    parts.append(f"Task: {task_url}")
    if closes:
        parts.append(closes)
    return "\n\n".join(parts)


def checks(rollup: list | None) -> dict[str, int]:
    """AC24: {passed, failed, pending} over gh's statusCheckRollup. A check run's `conclusion` decides, else a status
    context's `state`; an empty conclusion (still running) and PENDING or EXPECTED count as pending."""
    counts = {"passed": 0, "failed": 0, "pending": 0}
    for check in rollup or []:
        value = (check.get("conclusion") or check.get("state") or "") if isinstance(check, dict) else ""
        value = str(value).upper()
        counts["passed" if value in PASSED else "failed" if value in FAILED else "pending"] += 1
    return counts
