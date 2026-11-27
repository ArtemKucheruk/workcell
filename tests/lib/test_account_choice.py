"""097: Auto's ranking, lib/account_choice.py (AC1–AC8)."""

import ast
import re
from datetime import datetime
from pathlib import Path

from workcell.lib.account_choice import FIVE_HOUR_LOW, SEVEN_DAY_LOW, is_low, rank, refusal, when

NOW = 1_800_000_000
LATER = NOW + 3600  # an unreset window's resets_at
PKG = Path(__file__).resolve().parents[2] / "src" / "workcell"


def acct(i, active=False):
    return {"id": i, "active": active, "email": f"a{i}@x", "config_dir": f"/c/{i}"}


def snap(five=0.1, seven=0.1, five_status="allowed", seven_status="allowed", limited=False, five_resets=LATER,
         seven_resets=LATER + 86400):
    return {"five_hour_utilization": five, "five_hour_resets_at": five_resets, "five_hour_status": five_status,
            "seven_day_utilization": seven, "seven_day_resets_at": seven_resets, "seven_day_status": seven_status,
            "limited": int(limited)}


def pick(accounts, latest):
    candidates, _ = rank(accounts, latest, NOW)
    return candidates[0]["id"] if candidates else None


def test_active_below_thresholds():  # AC1
    assert pick([acct(1, True), acct(2)], {1: snap(0.5, 0.4), 2: snap(0.0, 0.0)}) == 1


def test_active_five_hour_low():  # AC2
    assert pick([acct(1, True), acct(2)], {1: snap(0.85), 2: snap(0.10)}) == 2
    assert is_low(snap(0.85), NOW) == {"why": "5h 85%", "resets_at": LATER}


def test_active_seven_day_low():  # AC3
    assert pick([acct(1, True), acct(2)], {1: snap(0.1, 0.92), 2: snap(0.1, 0.1)}) == 2
    assert is_low(snap(0.1, 0.92), NOW)["why"] == "7d 92%"
    assert is_low(snap(0.92, 0.93), NOW) == {"why": "5h 92% 7d 93%", "resets_at": LATER}  # Q3: 5h first


def test_active_limited():  # AC4, Q1
    others = {2: snap(0.1)}
    assert pick([acct(1, True), acct(2)], {1: snap(0.1, five_status="rejected")} | others) == 2
    assert pick([acct(1, True), acct(2)], {1: snap(0.1, seven_status="rejected")} | others) == 2
    assert pick([acct(1, True), acct(2)], {1: snap(0.1, limited=True)} | others) == 2
    assert is_low(snap(0.1, limited=True), NOW) == {"why": "limited", "resets_at": LATER}
    # the flag sticks only until the 5h window resets
    assert is_low(snap(0.1, limited=True, five_resets=NOW - 1), NOW) is None


def test_reset_window_counts_as_zero():  # AC5
    assert pick([acct(1, True), acct(2)], {1: snap(0.95, five_resets=NOW), 2: snap(0.0)}) == 1
    assert is_low(snap(0.95, five_resets=NOW), NOW) is None


def test_unknown_between_known_and_low():  # AC6
    accounts, latest = [acct(1, True), acct(2), acct(3)], {1: snap(0.9), 3: snap(0.5, 0.5)}
    candidates, low = rank(accounts, latest, NOW)
    assert [a["id"] for a in candidates] == [3, 2]
    assert [x["account"]["id"] for x in low] == [1]
    assert pick([acct(1, True), acct(2)], {1: snap(0.9)}) == 2  # C removed: unknown beats low


def test_headroom_order():  # AC7, Q2
    accounts = [acct(1), acct(2), acct(3), acct(4), acct(5, True)]
    latest = {1: snap(0.5, 0.1), 2: snap(0.3, 0.6), 3: snap(0.3, 0.2), 4: snap(0.3, 0.2), 5: snap(0.7, 0.7)}
    assert [a["id"] for a in rank(accounts, latest, NOW)[0]] == [5, 3, 4, 2, 1]
    # an active account with no snapshot isn't low, so it's first
    assert pick([acct(1), acct(2, True)], {1: snap(0.0)}) == 2
    assert rank([], {}, NOW) == ([], [])


def test_thresholds_in_one_place():  # AC8
    assert (FIVE_HOUR_LOW, SEVEN_DAY_LOW) == (0.8, 0.9)
    assert is_low(snap(0.8), NOW) and not is_low(snap(0.79), NOW)
    assert is_low(snap(0.1, 0.9), NOW) and not is_low(snap(0.1, 0.89), NOW)
    for path in (PKG / "handlers" / "runs.py", PKG / "handlers" / "pages.py"):  # the modules that rank
        consts = {n.value for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.Constant)}
        assert not {0.8, 0.9, 80, 90} & consts, path
    page = (PKG.parents[1] / "frontend" / "src" / "pages" / "task" / "TaskPage.jsx").read_text()
    assert not {"0.8", "0.9"} & set(re.findall(r"\b\d+\.\d+\b", page))  # the frontend shows the server's `auto`


def test_refusal_format():  # AC11, Q3
    low = rank([acct(1, True), acct(2)], {1: snap(0.92), 2: snap(0.1, limited=True, five_resets=NOW + 7200)}, NOW)[1]
    detail = refusal(low, {1: "a@x", 2: "b@y"}, NOW)
    hm = datetime.fromtimestamp(LATER).strftime("%H:%M")
    assert detail == (f"all accounts near their limits: a@x 5h 92% (resets {hm}), "
                      f"b@y limited (resets {datetime.fromtimestamp(NOW + 7200).strftime('%H:%M')})")
    far = NOW + 3 * 86400
    assert when(far, NOW) == datetime.fromtimestamp(far).strftime("%b %d %H:%M")
