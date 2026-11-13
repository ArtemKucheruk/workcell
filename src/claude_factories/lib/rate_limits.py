"""095: a run's stream-json log → its latest Claude rate-limit snapshot, and how a stored window reads at a given
time. Pure: no app, no database."""

import math
from collections.abc import Iterable

from .run_log import parse

WINDOWS = ("five_hour", "seven_day")
OK = ("allowed", "allowed_warning")  # Q5: any other status string (e.g. `rejected`) is limited
NEAR = 0.8  # Q5: near limit from 80% utilization


def window_of(raw) -> dict | None:
    """AC2: one `unifiedWindows` entry, or None unless utilization is a number, resetsAt an int, status a string."""
    if not isinstance(raw, dict):
        return None
    used, resets, status = raw.get("utilization"), raw.get("resetsAt"), raw.get("status")
    if isinstance(used, bool) or not isinstance(used, int | float) or not math.isfinite(used):
        return None
    if isinstance(resets, bool) or not isinstance(resets, int) or not isinstance(status, str):
        return None
    if not 0 <= resets < 2**63:  # SQLite's INTEGER: a larger one would fail the insert, and with it finish()
        return None
    return {"utilization": float(used), "resets_at": resets, "status": status}


def snapshot(event) -> dict | None:
    """AC1, AC2: a `rate_limit_event` with both windows valid → {five_hour, seven_day, status, overage}."""
    if not isinstance(event, dict) or event.get("type") != "rate_limit_event":
        return None
    info = event.get("rate_limit_info")
    if not isinstance(info, dict):
        return None
    windows = info.get("unifiedWindows")
    windows = windows if isinstance(windows, dict) else {}
    found = {name: window_of(windows.get(name)) for name in WINDOWS}
    if None in found.values():
        return None
    status = info.get("status")
    return found | {"status": status if isinstance(status, str) else None,
                    "overage": info.get("isUsingOverage") is True}


def is_limited(snap: dict) -> bool:
    """AC4: the top-level or either window's status is something other than allowed / allowed_warning."""
    statuses = [snap["status"]] if snap["status"] is not None else []
    return any(s not in OK for s in statuses + [snap[name]["status"] for name in WINDOWS])


def latest(lines: Iterable[str]) -> dict | None:
    """AC3, AC4: the last valid event in log order, with `limited` true if any valid event was limited (Q6).
    None when the log has no valid event (AC2)."""
    found, limited = None, False
    for line in lines:
        if snap := snapshot(parse(line)):
            found, limited = snap, limited or is_limited(snap)
    return found and found | {"limited": limited}


def window(stored: dict | None, now: float) -> dict | None:
    """AC5: a stored window {utilization, resets_at, status} as it reads at `now` (epoch seconds). A passed
    resets_at reads as reset at 0%, never the stored value."""
    if stored is None:
        return None
    if stored["resets_at"] <= now:
        return {"utilization": 0.0, "resets_at": stored["resets_at"], "state": "allowed", "reset": True}
    status, used = stored["status"], stored["utilization"]
    state = ("limited" if status not in OK else
             "near_limit" if status == "allowed_warning" or used >= NEAR else "allowed")
    return {"utilization": used, "resets_at": stored["resets_at"], "state": state, "reset": False}
