"""104: lib/cron's parse, next_after, and describe, pure, with `now` passed in (AC1–AC6)."""

import datetime
import os
import time

import pytest

from workcell.domain.errors import Invalid
from workcell.lib import cron


@pytest.fixture
def tz(monkeypatch):
    """tz(name) makes `name` the process's local zone until the test ends (AC5)."""
    def use(name):
        monkeypatch.setenv("TZ", name)
        time.tzset()

    yield use
    monkeypatch.undo()
    time.tzset()


def local(y, mo, d, h=0, mi=0) -> float:
    return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))


def wall(t: float) -> str:
    return time.strftime("%Y-%m-%d %a %H:%M", time.localtime(t))


def test_parse_grammar():  # AC1
    c = cron.parse("  */15   9-17,20  1,15 */3 1-5/2 ")
    assert c.text == "*/15 9-17,20 1,15 */3 1-5/2"
    assert c.minutes == (0, 15, 30, 45)
    assert c.hours == (9, 10, 11, 12, 13, 14, 15, 16, 17, 20)
    assert c.days == {1, 15}
    assert c.months == {1, 4, 7, 10}
    assert c.weekdays == {1, 3, 5}
    assert cron.parse("0 0 * * 0").weekdays == cron.parse("0 0 * * 7").weekdays == {0}  # both Sunday
    assert cron.parse("59 23 31 12 0-7").weekdays == set(range(7))
    assert (c.day_any, c.weekday_any) == (False, False)
    assert (cron.parse("* * * * *").day_any, cron.parse("* * * * *").weekday_any) == (True, True)


@pytest.mark.parametrize("expr, detail", [
    ("0 9 * *", "cron needs 5 fields (minute hour day month weekday), got 4"),
    ("", "cron needs 5 fields (minute hour day month weekday), got 0"),
    ("0 9 * * * *", "cron needs 5 fields (minute hour day month weekday), got 6"),
    ("61 * * * *", "cron minute 61 is out of range 0–59"),
    ("0 24 * * *", "cron hour 24 is out of range 0–23"),
    ("0 0 0 * *", "cron day 0 is out of range 1–31"),
    ("0 0 * 13 *", "cron month 13 is out of range 1–12"),
    ("0 0 * * 8", "cron weekday 8 is out of range 0–7"),
    ("0 x * * *", 'cron hour "x" isn\'t a number, range, list, or step'),
    ("5/10 * * * *", 'cron minute "5/10" isn\'t a number, range, list, or step'),
    ("*/0 * * * *", 'cron minute "*/0" isn\'t a number, range, list, or step'),
    ("1,,2 * * * *", 'cron minute "1,,2" isn\'t a number, range, list, or step'),
    ("-1 * * * *", 'cron minute "-1" isn\'t a number, range, list, or step'),
    ("MON * * * *", 'cron minute "MON" isn\'t a number, range, list, or step'),
    ("0 17-9 * * *", "cron hour range 17-9 runs backwards"),
    ("0 0 30 2 *", "cron 0 0 30 2 * never runs"),
    ("0 0 31 4,6 *", "cron 0 0 31 4,6 * never runs"),
])
def test_parse_refusals(expr, detail):  # AC2
    with pytest.raises(Invalid) as e:
        cron.parse(expr)
    assert e.value.detail == detail


def test_feb_29_runs():  # Q5: 8 years cover a leap day
    assert cron.parse("0 0 29 2 *").text == "0 0 29 2 *"


def test_next_after(tz):  # AC3
    tz("UTC")
    assert datetime.date(2026, 11, 18).strftime("%A") == "Wednesday"
    assert datetime.date(2026, 11, 20).strftime("%A") == "Friday"
    cases = [
        ("0 * * * *", local(2026, 11, 18, 10, 20), "2026-11-18 Wed 11:00"),
        ("0 9 * * *", local(2026, 11, 18, 9, 0), "2026-11-19 Thu 09:00"),  # strictly after
        ("0 9 * * *", local(2026, 11, 18, 8, 59) + 59, "2026-11-18 Wed 09:00"),
        ("30 8 * * 1", local(2026, 11, 18, 12, 0), "2026-11-23 Mon 08:30"),
        ("*/15 9-17 * * 1-5", local(2026, 11, 20, 17, 50), "2026-11-23 Mon 09:00"),
        ("*/15 9-17 * * 1-5", local(2026, 11, 20, 17, 44), "2026-11-20 Fri 17:45"),
        ("0 0 1 1 *", local(2026, 11, 18), "2027-01-01 Fri 00:00"),
        ("0 0 29 2 *", local(2026, 11, 18), "2028-02-29 Tue 00:00"),
    ]
    assert [wall(cron.next_after(expr, now)) for expr, now, _ in cases] == [want for *_, want in cases]


def test_next_after_in_local_time(tz):  # AC3, Q2: the server's zone decides
    tz("Asia/Tokyo")
    t = cron.next_after("0 9 * * *", local(2026, 11, 18, 10))
    assert wall(t) == "2026-11-19 Thu 09:00"
    assert datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%d %H:%M") == "19 00:00"


def test_day_or_weekday(tz):  # AC4
    tz("UTC")
    t, seen = local(2026, 11, 18), []
    for _ in range(8):
        t = cron.next_after("0 0 1 * 1", t)
        seen.append(wall(t)[:14])
    assert seen == ["2026-11-23 Mon", "2026-11-30 Mon", "2026-12-01 Tue", "2026-12-07 Mon", "2026-12-14 Mon",
                    "2026-12-21 Mon", "2026-12-28 Mon", "2027-01-01 Fri"]
    # with one of them `*`, only the other counts
    assert wall(cron.next_after("0 0 1 * *", local(2026, 11, 18)))[:14] == "2026-12-01 Tue"
    assert wall(cron.next_after("0 0 * * 1", local(2026, 11, 24)))[:14] == "2026-11-30 Mon"


def test_dst(tz):  # AC5, Q3
    tz("America/New_York")
    assert os.environ["TZ"] == "America/New_York"
    # 2026: spring forward on Sunday March 8 (02:00 → 03:00), fall back on Sunday November 1 (02:00 → 01:00)
    for before, days, gap in ((local(2026, 3, 6, 10), ["2026-03-07", "2026-03-08"], 23),
                              (local(2026, 10, 30, 10), ["2026-10-31", "2026-11-01"], 25)):
        first = cron.next_after("0 9 * * *", before)
        second = cron.next_after("0 9 * * *", first)
        assert [wall(first), wall(second)] == [time.strftime("%Y-%m-%d %a 09:00", time.strptime(d, "%Y-%m-%d"))
                                               for d in days]
        assert (second - first) / 3600 == gap
    t = cron.next_after("30 2 * * *", local(2026, 3, 7, 3))
    assert wall(t) == "2026-03-09 Mon 02:30"  # 02:30 doesn't exist on the 8th: skipped that day
    first = cron.next_after("30 1 * * *", local(2026, 10, 31, 3))
    assert wall(first) == "2026-11-01 Sun 01:30"
    assert time.localtime(first).tm_isdst == 1  # the first 01:30, still EDT
    assert wall(cron.next_after("30 1 * * *", first)) == "2026-11-02 Mon 01:30"  # not the second 01:30
    assert cron.next_after("30 1 * * *", first) - first == 25 * 3600


@pytest.mark.parametrize("expr, words", [
    ("5 * * * *", "Hourly at :05"),
    ("0 * * * *", "Hourly at :00"),
    ("0 9 * * *", "Daily at 09:00"),
    ("30 17 * * *", "Daily at 17:30"),
    ("0 9 * * 1", "Weekly on Monday at 09:00"),
    ("0 9 * * 0", "Weekly on Sunday at 09:00"),
    ("0 9 * * 7", "Weekly on Sunday at 09:00"),
    ("  0  9 * * 6 ", "Weekly on Saturday at 09:00"),
    ("*/15 9-17 * * 1-5", "Custom: */15 9-17 * * 1-5"),
    ("0 9 1 * *", "Custom: 0 9 1 * *"),
    ("0 * * * 1", "Custom: 0 * * * 1"),
    ("0  9 * * 1,3", "Custom: 0 9 * * 1,3"),
])
def test_describe(expr, words):  # AC6, Q6
    assert cron.describe(expr) == words
