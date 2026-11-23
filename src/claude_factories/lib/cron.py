"""104: 5-field cron, read in the server's local time zone (docs/MVP.md §4.3, The scheduler runs inside the backend).
Stdlib only: `time.mktime` and `time.localtime` carry the zone and its DST changes (Q2, Q3).

Q5's grammar: minute hour day month weekday, each `*`, `n`, `a-b`, a `,` list of those, and a `/step` on `*` or
`a-b`; weekday 0 and 7 are both Sunday. No names, macros, or seconds."""

import datetime
import time
from typing import NamedTuple

from ..domain.errors import Invalid

FIELDS = (("minute", 0, 59), ("hour", 0, 23), ("day", 1, 31), ("month", 1, 12), ("weekday", 0, 7))
YEARS = 8  # Q5: covers a Feb 29 schedule; nothing matching within it is `never runs`
WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


class Cron(NamedTuple):
    text: str  # the expression normalized: its fields joined by single spaces
    minutes: tuple[int, ...]
    hours: tuple[int, ...]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]  # 0 = Sunday; a 7 is stored as 0
    day_any: bool  # the day field is `*`
    weekday_any: bool  # the weekday field is `*`


def values(name: str, lo: int, hi: int, field: str) -> set[int]:
    """One field's values. Raises Invalid naming the field: a bad item, or a value out of range."""
    def bad():
        return Invalid(f'cron {name} "{field}" isn\'t a number, range, list, or step')

    def number(text: str) -> int:
        if not text.isdigit():  # ascii digits only: no sign, no space
            raise bad()
        n = int(text)
        if not lo <= n <= hi:
            raise Invalid(f"cron {name} {n} is out of range {lo}–{hi}")
        return n

    found = set()
    for item in field.split(","):
        base, slash, step = item.partition("/")
        if slash and not (step.isdigit() and int(step) > 0):
            raise bad()
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = number(a), number(b)
            if start > end:
                raise Invalid(f"cron {name} range {base} runs backwards")
        elif slash:  # Q5: a step only on `*` or a range
            raise bad()
        else:
            start = end = number(base)
        found.update(range(start, end + 1, int(step) if slash else 1))
    return found


def parse(expr: str) -> Cron:
    """AC1, AC2: the parsed expression, or Invalid with the reason. Surrounding and repeated whitespace is ignored.
    An expression no date matches within YEARS from today is refused as `never runs`."""
    fields = expr.split()
    if len(fields) != 5:
        raise Invalid(f"cron needs 5 fields (minute hour day month weekday), got {len(fields)}")
    parts = [values(name, lo, hi, field) for (name, lo, hi), field in zip(FIELDS, fields)]
    minutes, hours, days, months, weekdays = parts
    cron = Cron(" ".join(fields), tuple(sorted(minutes)), tuple(sorted(hours)), frozenset(days), frozenset(months),
                frozenset(w % 7 for w in weekdays), fields[2] == "*", fields[4] == "*")
    if next(dates(cron, datetime.date.today()), None) is None:
        raise Invalid(f"cron {cron.text} never runs")
    return cron


def matches(cron: Cron, d: datetime.date) -> bool:
    """AC4: the date's month, then its day and weekday. With both restricted, either one matching is enough
    (standard cron); with one of them `*`, only the other counts."""
    if d.month not in cron.months:
        return False
    day, weekday = d.day in cron.days, d.isoweekday() % 7 in cron.weekdays
    if cron.day_any or cron.weekday_any:
        return day and weekday
    return day or weekday


def dates(cron: Cron, start: datetime.date):
    """The matching dates from `start` on, for YEARS."""
    for n in range(YEARS * 366):
        d = start + datetime.timedelta(days=n)
        if matches(cron, d):
            yield d


def wall(d: datetime.date, hour: int, minute: int) -> float | None:
    """Q3: the epoch time of a local wall-clock minute. None when it doesn't exist (the spring-forward gap); the first
    of the two when it exists twice (fall-back). Each guess's isdst is tried and kept only if it reads back the same."""
    want = (d.year, d.month, d.day, hour, minute)
    found = []
    for dst in (0, 1):
        try:
            t = time.mktime((*want, 0, 0, 0, dst))
        except (OverflowError, ValueError):
            continue
        if tuple(time.localtime(t)[:5]) == want:
            found.append(t)
    return min(found) if found else None


def next_after(expr: str, now: float) -> float:
    """AC3, AC5: the epoch time of the first matching local wall-clock minute strictly after `now` (epoch seconds).
    ponytail: a matching day walks its hours and minutes in order, at most 1440 mktime pairs; a smarter skip if it
    shows up in a profile."""
    cron = parse(expr)
    for d in dates(cron, datetime.date.fromtimestamp(now) - datetime.timedelta(days=1)):  # the day before: a zone's
        for hour in cron.hours:                                                            # date can lag fromtimestamp's
            for minute in cron.minutes:
                t = wall(d, hour, minute)
                if t is not None and t > now:
                    return t
    raise Invalid(f"cron {cron.text} never runs")


def describe(expr: str) -> str:
    """AC6, Q6: the preset shapes in words, else `Custom: <expr as normalized>`."""
    cron = parse(expr)
    minute, hour, day, month, weekday = cron.text.split()
    if day != "*" or month != "*" or not minute.isdigit():
        return f"Custom: {cron.text}"
    if hour == "*" and weekday == "*":
        return f"Hourly at :{int(minute):02}"
    if not hour.isdigit():
        return f"Custom: {cron.text}"
    at = f"{int(hour):02}:{int(minute):02}"
    if weekday == "*":
        return f"Daily at {at}"
    if weekday.isdigit():
        return f"Weekly on {WEEKDAYS[int(weekday) % 7]} at {at}"
    return f"Custom: {cron.text}"
