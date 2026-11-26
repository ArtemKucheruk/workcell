"""109: lib/plane_item (AC9, Q3, Q5)."""

from claude_factories.lib.plane_item import description, key, parse_key


def test_key_round_trip():  # AC9, Q3
    k = key("acme", "p-1", "item-7")
    assert k == "plane:acme/p-1/item-7"
    assert parse_key(k) == ("acme", "p-1", "item-7")
    assert parse_key("github:o/r#1") is None and parse_key(None) is None and parse_key("plane:a/b") is None


def test_description():  # AC9, Q5
    assert description("Fix it\n\n", "ENG", 12) == "Fix it\n\nPlane work item: ENG-12"
    assert description("  \n", "ENG", 3) == "Plane work item: ENG-3"
    assert description(None, "ENG", 3) == "Plane work item: ENG-3"
