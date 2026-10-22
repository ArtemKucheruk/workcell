"""057 Q5, Q6: a context card's extension check, title, and description."""

import pytest

from claude_factories.lib.context_file import allowed, derive


@pytest.mark.parametrize("name, ok", [
    ("a.md", True), ("A.MD", True), ("notes.markdown", True), ("x.Txt", True),
    ("a.pdf", False), ("README", False), ("md", False), ("a.md.bak", False),
])
def test_allowed(name, ok):
    assert allowed(name) == ok


@pytest.mark.parametrize("text, title, description", [
    ("# API rules\n\nUse JSON\neverywhere.\n", "API rules", "Use JSON everywhere."),
    ("Intro first.\n\n# Later title #\n", "Later title", "Intro first."),
    ("API\nrules\n===\n\nbody\n", "API rules", "body"),  # setext, joined onto one line
    ("## h2\n\n```\n# x\n```\n", "notes.txt", ""),  # an h2, and a # line inside a fence, aren't level-1 headings
    ("#\n\n   indented\t  para  \n  goes on\n", "notes.txt", "indented para goes on"),  # a blank h1 → the name
    ("", "notes.txt", ""),
    ("- in a list\n", "notes.txt", "in a list"),
])
def test_derive(text, title, description):  # BE13
    assert derive(text, "notes.txt") == (title, description)


def test_description_cut_at_160():  # BE13: its first 160 characters, no ellipsis
    words = " ".join(f"w{i:03}" for i in range(60))
    assert derive(words.replace(" ", "\n   "), "a.md")[1] == words[:160]
    assert len(words) > 160
