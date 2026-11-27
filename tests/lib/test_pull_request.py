"""093: lib/pull_request.py's PR body, checks summary, and PR number."""

import pytest

from workcell.lib.pull_request import checks, pr_body, pr_number

URL = "http://127.0.0.1:4545/tasks/12"


def test_body_in_order():  # AC20
    body = pr_body("Limit logins.\nPer IP.\n\nMore detail.\n", 3, 3, {"security": "PASS", "ux": "PASS", "ui": "PASS",
                                                                       "code": "CHANGES"}, ("APPROVE", "Looks good.\n"),
                   URL)
    assert body == ("Limit logins.\nPer IP.\n\nRounds: 3\n\n"
                    "Verdicts (round 3): security PASS · ux PASS · ui PASS · code CHANGES\n\n"
                    "Approver: APPROVE — Looks good.\n\nTask: http://127.0.0.1:4545/tasks/12")


def test_body_leaves_out_blanks():  # AC20
    assert pr_body("  \n\n", 0, None, {}, None, URL) == f"Rounds: 0\n\nTask: {URL}"
    assert pr_body("", 1, 1, {"ux": "PASS"}, None, URL) == (
        f"Rounds: 1\n\nVerdicts (round 1): security pending · ux PASS · ui pending · code pending\n\nTask: {URL}")
    assert pr_body("", 1, 1, {}, ("ESCALATE", ""), URL).count("Approver: ESCALATE\n") == 1


def test_body_whitespace_line_splits_paragraphs():  # AC20
    assert pr_body("First.\r\n \r\nSecond.", 1, None, {}, None, URL).startswith("First.\n\nRounds: 1")


def test_body_closes_paragraph():  # 108 AC24, AC25
    assert pr_body("", 0, None, {}, None, URL, "Closes #12") == f"Rounds: 0\n\nTask: {URL}\n\nCloses #12"
    assert pr_body("", 0, None, {}, None, URL, None) == pr_body("", 0, None, {}, None, URL)


def test_body_has_no_attribution():  # AC20
    body = pr_body("x", 1, 1, {}, ("APPROVE", "y"), URL)
    assert "Claude" not in body and "Co-Authored-By" not in body


@pytest.mark.parametrize("rollup, expected", [
    (None, (0, 0, 0)),
    ([], (0, 0, 0)),
    ([{"conclusion": c} for c in ("SUCCESS", "NEUTRAL", "SKIPPED")], (3, 0, 0)),
    ([{"conclusion": c} for c in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE")],
     (0, 6, 0)),
    ([{"conclusion": "", "status": "IN_PROGRESS"}, {"status": "QUEUED"}, {"state": "PENDING"}, {"state": "EXPECTED"}],
     (0, 0, 4)),
    ([{"state": "SUCCESS"}, {"state": "ERROR"}, {"state": "FAILURE"}, "junk"], (1, 2, 1)),
])
def test_checks(rollup, expected):  # AC24
    assert checks(rollup) == dict(zip(("passed", "failed", "pending"), expected))


def test_pr_number():  # AC36, Q3
    assert pr_number("https://github.com/o/r/pull/71") == 71
    assert pr_number("https://github.com/o/r/issues/71") is None
    assert pr_number(None) is None
