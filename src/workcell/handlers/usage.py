"""095: GET /api/usage, the accounts' latest Claude limits and the token and run stats (docs/data-model-and-api.md
§6.4), and the sidebar's compact `usage` (docs/ui.md §8.4). No git, no claude: the limits are only as fresh as each
account's last run (Q2, option a)."""

import time
from datetime import UTC, datetime, timedelta
from pathlib import PurePath

from ..domain.errors import Invalid
from ..lib.rate_limits import WINDOWS, window
from ..repositories.claude_accounts import ClaudeAccountsRepo
from ..repositories.usage import UsageRepo

DAYS = (7, 30)  # AC14: the page's two periods
TOP_TASKS = 10  # AC17
LIMITED_RUNS = 20  # AC18
TOKENS = ("input_tokens", "cache_read_tokens", "output_tokens")


def label(email: str | None, config_dir: str | None) -> str:
    """AC12, Q3: the stored email, else the config dir's last path component; `unknown` with neither (AC16)."""
    return email or (PurePath(config_dir).name if config_dir else "") or "unknown"


def accounts_usage(accounts: ClaudeAccountsRepo, usage: UsageRepo, now: float | None = None) -> list[dict]:
    """AC13, AC19: every account by id with its latest snapshot's windows as they read `now` (AC5). No config_dir,
    tokens, or credentials."""
    now = time.time() if now is None else now
    latest = usage.latest()
    found = []
    for row in accounts.all():
        snap = latest.get(row["id"])
        windows = {name: snap and window({"utilization": snap[f"{name}_utilization"],
                                          "resets_at": snap[f"{name}_resets_at"],
                                          "status": snap[f"{name}_status"]}, now) for name in WINDOWS}
        found.append({"id": row["id"], "label": label(row["email"], row["config_dir"]), "active": bool(row["active"]),
                      "recorded_at": snap and snap["recorded_at"], "run_id": snap and snap["run_id"],
                      "overage": snap and bool(snap["overage"])} | windows)
    return found


def totals(rows, key) -> dict[str, dict]:
    """Token rows summed under key(row), as {key: {input_tokens, cache_read_tokens, output_tokens}}."""
    found = {}
    for r in rows:
        sums = found.setdefault(key(r), dict.fromkeys(TOKENS, 0))
        for t in TOKENS:
            sums[t] += r[t] or 0
    return found


def largest_first(found: dict[str, dict]) -> list[dict]:
    """AC16: {key: sums} as a list, the largest total first, then by key."""
    return sorted(({"key": k} | v for k, v in found.items()), key=lambda r: (-sum(r[t] for t in TOKENS), r["key"]))


def stats(usage: UsageRepo, days: int, today=None) -> dict:
    """AC14–AC17, Q8: UTC calendar days, today and the days - 1 before it."""
    today = today or datetime.now(UTC).date()
    first = today - timedelta(days=days - 1)
    since = f"{first.isoformat()}T00:00:00Z"
    tokens, runs = {r["day"]: r for r in usage.by_day(since)}, usage.runs_by_day(since)
    by_day = []
    for i in range(days):
        day = (first + timedelta(days=i)).isoformat()
        by_day.append({"day": day} | {t: (tokens[day][t] or 0) if day in tokens else 0 for t in TOKENS}
                      | {"runs": runs.get(day, 0)})
    accounts = totals(usage.by_account(since), lambda r: label(r["email"], r["config_dir"]))
    run_counts = {}
    for r in usage.runs_by_account(since):
        key = label(r["email"], r["config_dir"])
        run_counts[key] = run_counts.get(key, 0) + r["runs"]
        accounts.setdefault(key, dict.fromkeys(TOKENS, 0))
    by_account = [r | {"runs": run_counts.get(r["key"], 0)} for r in largest_first(accounts)]
    return {
        "days": days, "by_day": by_day, "by_account": by_account,
        "by_model": [dict(r) for r in usage.by_column("model", "unknown", since)],
        "by_agent": [dict(r) for r in usage.by_column("agent_type", "agent", since)],
        "top_tasks": [dict(r) for r in usage.top_tasks(since, TOP_TASKS)],
    }


def usage(accounts: ClaudeAccountsRepo, usage: UsageRepo, days: int) -> dict:
    """AC13, AC14, AC18: GET /api/usage."""
    if days not in DAYS:
        raise Invalid("days must be 7 or 30")
    limited = [{"run_id": r["run_id"], "task_id": r["task_id"], "title": r["title"],
                "label": label(r["email"], r["config_dir"]), "ended_at": r["ended_at"]}
               for r in usage.limited_runs(LIMITED_RUNS)]
    return {"accounts": accounts_usage(accounts, usage), "stats": stats(usage, days), "limited_runs": limited}
