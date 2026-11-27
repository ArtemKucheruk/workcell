"""097: Auto's account choice from each account's latest usage snapshot (095's usage_snapshots rows), read at a
given `now` (epoch seconds), and the reset-time format of its details (docs/MVP.md §4.3). Pure: no app, no database.
Utilization is a fraction (0.85 = 85%)."""

from datetime import datetime

from .rate_limits import window

FIVE_HOUR_LOW = 0.8  # AC8: an account at or over either is low; the one place these live
SEVEN_DAY_LOW = 0.9


def windows(snap, now: float) -> dict:
    """The snapshot row's two windows as lib/rate_limits.window reads them at `now` (a passed reset reads 0%)."""
    return {name: window({"utilization": snap[f"{name}_utilization"], "resets_at": snap[f"{name}_resets_at"],
                          "status": snap[f"{name}_status"]}, now) for name in ("five_hour", "seven_day")}


def is_low(snap, now: float) -> dict | None:
    """AC2–AC5, Q1: {why, resets_at} when the snapshot row says the account is low at `now`, else None (no snapshot
    is unknown, never low). Limited: a window's state is `limited`, or the row's `limited` flag with its 5h window
    not yet reset (the flag names no window). `why` is `limited`, else `5h 92%`, `7d 93%`, or both, 5h first (Q3);
    `resets_at` is the earliest unreset reset among the windows that made it low (the 5h one for the flag)."""
    if snap is None:
        return None
    five, seven = (w := windows(snap, now))["five_hour"], w["seven_day"]
    limited = [x for x in (five, seven) if x["state"] == "limited"]
    if snap["limited"] and not five["reset"]:
        limited.append(five)
    if limited:
        return {"why": "limited", "resets_at": min(x["resets_at"] for x in limited)}
    high = [(f"{tag} {round(x['utilization'] * 100)}%", x) for tag, x, low in
            (("5h", five, FIVE_HOUR_LOW), ("7d", seven, SEVEN_DAY_LOW)) if x["utilization"] >= low]
    if not high:
        return None
    return {"why": " ".join(why for why, _ in high), "resets_at": min(x["resets_at"] for _, x in high)}


def rank(accounts, latest: dict, now: float) -> tuple[list, list[dict]]:
    """AC6, AC7, Q2: (candidates, low). Candidates are the non-low accounts in Auto's order: the active one first
    (with no snapshot it isn't low, so it's used), then those with a snapshot by lower 5h, lower 7d, lower id, then
    those with none (unknown) by id. `low` is every low account by id as {account, why, resets_at}."""
    keyed, unknown, low, active = [], [], [], None
    for a in sorted(accounts, key=lambda a: a["id"]):
        snap = latest.get(a["id"])
        if found := is_low(snap, now):
            low.append({"account": a} | found)
        elif a["active"]:
            active = a
        elif snap is None:
            unknown.append(a)
        else:
            w = windows(snap, now)
            keyed.append(((w["five_hour"]["utilization"], w["seven_day"]["utilization"], a["id"]), a))
    return [active] * bool(active) + [a for _, a in sorted(keyed, key=lambda k: k[0])] + unknown, low


def when(resets_at: int, now: float) -> str:
    """Q3: `HH:MM` in the server's local time when the reset is within 24 h, else `Nov 15 14:10`."""
    at = datetime.fromtimestamp(resets_at)
    return at.strftime("%H:%M" if resets_at - now < 24 * 3600 else "%b %d %H:%M")


def refusal(low: list[dict], labels: dict, now: float) -> str:
    """AC11, Q10: the 409 detail when every account is low: one `<label> <why> (resets <time>)` per low account."""
    return "all accounts near their limits: " + ", ".join(
        f"{labels[x['account']['id']]} {x['why']} (resets {when(x['resets_at'], now)})" for x in low)
