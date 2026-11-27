"""058: factory/backlog.md's parser."""

import pytest

from workcell.lib.backlog import parse, title


def test_line_under_heading():  # BE1, Q2
    assert parse("# Backlog\n\n## Repo backlog\n\n- [ ] 059-legacy-factory: the text \n") == ([{
        "id": "059-legacy-factory", "done": False, "title": "Legacy factory",
        "description_md": "## Repo backlog\n\nthe text"}], 0)


@pytest.mark.parametrize("mark", ["x", "X"])
def test_done(mark):  # BE2
    [line], _ = parse(f"- [{mark}] 001-a: t")
    assert line["done"] is True


def test_sections():  # BE3
    text = ("- [ ] 001-a: before\n# Top\n- [ ] 002-b: still none\n## One\n### Sub\n- [ ] 003-c: in one\n"
            "# Other top\n- [ ] 004-d: still one\n##   Two  \n- [ ] 005-e: in two\r\n")
    assert [line["description_md"] for line in parse(text)[0]] == [
        "before", "still none", "## One\n\nin one", "## One\n\nstill one", "## Two\n\nin two"]


@pytest.mark.parametrize("job_id, expected", [
    ("058-backlog-sync", "Backlog sync"), ("018-merge-013", "Merge 013"), ("setup", "Setup"), ("12-", "12-")])
def test_title(job_id, expected):  # BE4, Q3
    assert title(job_id) == expected


def test_skipped():  # BE5, Q1
    text = ("# Heading\n\n## Section\nSome prose.\n- a plain bullet\n* another\n\n"
            "- [ ] 001-a: first\n"
            "- [ ] ../x: t\n"  # bad id
            "- [ ] just text\n"  # no <id>:
            "- [~] 001-b: t\n"  # another mark
            "- [x] 001-a: repeat\n"  # the first wins
            "- [ ] 002-b: second\n")
    lines, skipped = parse(text)
    assert [(line["id"], line["done"], line["description_md"]) for line in lines] == [
        ("001-a", False, "## Section\n\nfirst"), ("002-b", False, "## Section\n\nsecond")]
    assert skipped == 4
