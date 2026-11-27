"""095 AC1–AC5: lib/rate_limits, a run log's latest rate-limit snapshot and how a window reads at a time."""

import json

import pytest

from workcell.lib.rate_limits import latest, window


def event(five=0.34, seven=0.12, status="allowed", five_status="allowed", seven_status="allowed", overage=False,
          **info) -> str:
    """A rate_limit_event line shaped like the task description's."""
    return json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": status, "resetsAt": 1794414000, "rateLimitType": "five_hour", "isUsingOverage": overage,
        "unifiedWindows": {"five_hour": {"utilization": five, "resetsAt": 1794414000, "status": five_status},
                           "seven_day": {"utilization": seven, "resetsAt": 1794877200, "status": seven_status}},
    } | info})


def test_one_event():  # AC1
    assert latest([event()]) == {
        "five_hour": {"utilization": 0.34, "resets_at": 1794414000, "status": "allowed"},
        "seven_day": {"utilization": 0.12, "resets_at": 1794877200, "status": "allowed"},
        "status": "allowed", "overage": False, "limited": False,
    }
    assert latest([event(overage=True)])["overage"] is True


def bad_window(**window) -> str:
    good = {"utilization": 0.1, "resetsAt": 1794414000, "status": "allowed"}
    return json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": "allowed", "unifiedWindows": {"five_hour": good | window, "seven_day": good}}})


@pytest.mark.parametrize("line", [
    "{not json",
    "",
    json.dumps({"type": "rate_limit_event"}),
    json.dumps({"type": "rate_limit_event", "rate_limit_info": "x"}),
    json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}}),
    json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {
        "five_hour": {"utilization": 0.1, "resetsAt": 1, "status": "allowed"}}}}),  # no seven_day
    bad_window(utilization="0.1"),
    bad_window(utilization=None),
    bad_window(resetsAt=1794414000.5),
    bad_window(resetsAt="1794414000"),
    bad_window(resetsAt=2**63),  # round 2 (security nit): too big for SQLite's INTEGER
    bad_window(resetsAt=-1),
    '{"type":"rate_limit_event","rate_limit_info":{"unifiedWindows":{"five_hour":{"utilization":Infinity,'
    '"resetsAt":1,"status":"allowed"},"seven_day":{"utilization":0.1,"resetsAt":1,"status":"allowed"}}}}',
    bad_window(status=None),
    json.dumps({"type": "assistant", "rate_limit_info": json.loads(event())["rate_limit_info"]}),
])
def test_malformed_ignored(line):  # AC2
    assert latest([line]) is None
    assert latest([line, event(five=0.5)])["five_hour"]["utilization"] == 0.5
    assert latest([event(five=0.5), line])["five_hour"]["utilization"] == 0.5


def test_last_event_wins():  # AC3
    snap = latest([event(five=0.1), "{bad", event(five=0.2, seven=0.3), json.dumps({"type": "result"})])
    assert (snap["five_hour"]["utilization"], snap["seven_day"]["utilization"]) == (0.2, 0.3)


@pytest.mark.parametrize("limited, expected", [
    ({"status": "rejected"}, True),
    ({"five_status": "rejected"}, True),
    ({"seven_status": "blocked"}, True),
    ({"status": "allowed_warning", "five_status": "allowed_warning"}, False),
])
def test_limited_any_event(limited, expected):  # AC4, Q5, Q6
    snap = latest([event(**limited), event()])  # the last one is allowed again
    assert snap["status"] == "allowed"
    assert snap["limited"] is expected


NOW = 1_800_000_000


@pytest.mark.parametrize("stored, state", [
    ({"utilization": 0.34, "status": "allowed"}, "allowed"),
    ({"utilization": 0.79, "status": "allowed"}, "allowed"),
    ({"utilization": 0.8, "status": "allowed"}, "near_limit"),
    ({"utilization": 0.1, "status": "allowed_warning"}, "near_limit"),
    ({"utilization": 0.1, "status": "rejected"}, "limited"),
    ({"utilization": 1.0, "status": "rejected"}, "limited"),
])
def test_window_state(stored, state):  # AC5
    read = window(stored | {"resets_at": NOW + 60}, NOW)
    assert read == {"utilization": stored["utilization"], "resets_at": NOW + 60, "state": state, "reset": False}


@pytest.mark.parametrize("resets_at", [NOW, NOW - 3600])
def test_window_reset(resets_at):  # AC5: never the stale value
    stored = {"utilization": 0.97, "resets_at": resets_at, "status": "rejected"}
    assert window(stored, NOW) == {"utilization": 0, "resets_at": resets_at, "state": "allowed", "reset": True}
