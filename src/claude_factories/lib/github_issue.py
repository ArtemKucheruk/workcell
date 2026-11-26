"""108: a GitHub issue's `tasks.import_key` (`github:<owner>/<repo>#<n>`), its URL, an imported task's description,
and Create PR's `Closes` line (docs/data-model-and-api.md §5.1). Pure."""

import re

KEY = re.compile(r"github:([^/\s#]+/[^/\s#]+)#([1-9][0-9]{0,9})")


def key(repo: str, n: int) -> str:
    return f"github:{repo}#{n}"


def parse_key(import_key: str | None) -> tuple[str, int] | None:
    """(owner/repo, n) of a `github:` key; None for any other key, or none."""
    found = KEY.fullmatch(import_key) if import_key else None
    return (found[1], int(found[2])) if found else None


def issue_url(import_key: str | None) -> str | None:
    """AC22: the issue's page on github.com; None for a key that isn't `github:`."""
    found = parse_key(import_key)
    return f"https://github.com/{found[0]}/issues/{found[1]}" if found else None


def description(body: str | None, url: str) -> str:
    """AC13: the body right-stripped, a blank line, then the source line; only that line for an empty body."""
    text = (body or "").rstrip()
    return f"{text}\n\nGitHub issue: {url}" if text else f"GitHub issue: {url}"


def closes_line(import_key: str | None, pr_repo: str) -> str | None:
    """AC24–AC26, Q7: `Closes #n` when the issue is in the PR's repo (compared case-insensitively), else
    `Closes owner/repo#n`; None for a task not imported from an issue."""
    found = parse_key(import_key)
    if found is None:
        return None
    repo, n = found
    return f"Closes #{n}" if repo.lower() == pr_repo.lower() else f"Closes {repo}#{n}"
