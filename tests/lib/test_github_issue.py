"""108: lib/github_issue.py's key, URL, description, and Closes line."""

import pytest

from claude_factories.lib.github_issue import closes_line, description, issue_url, key, parse_key

URL = "https://github.com/o/r/issues/12"


def test_key_round_trips():  # AC13
    assert key("o/r", 12) == "github:o/r#12"
    assert parse_key("github:o/r#12") == ("o/r", 12)


@pytest.mark.parametrize("found", [None, "", "factory:12-x", "github:o#12", "github:o/r#0", "github:o/r#x",
                                   "github:o/r/s#1", "github:o/r#12 "])
def test_parse_key_other(found):  # AC22
    assert parse_key(found) is None and issue_url(found) is None


def test_issue_url():  # AC22
    assert issue_url("github:o/r#12") == URL


def test_description():  # AC13
    assert description("Fix it.\n\n", URL) == f"Fix it.\n\nGitHub issue: {URL}"
    assert description("  Indented stays.  ", URL) == f"  Indented stays.\n\nGitHub issue: {URL}"


@pytest.mark.parametrize("body", [None, "", " \n "])
def test_description_empty(body):  # AC13
    assert description(body, URL) == f"GitHub issue: {URL}"


def test_closes_line():  # AC24–AC26, Q7
    assert closes_line("github:o/r#12", "o/r") == "Closes #12"
    assert closes_line("github:O/R#12", "o/r") == "Closes #12"  # case-insensitive
    assert closes_line("github:old/name#12", "o/r") == "Closes old/name#12"
    assert closes_line("factory:12-x", "o/r") is None and closes_line(None, "o/r") is None
