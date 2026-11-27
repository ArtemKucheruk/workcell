"""Agent markdown → HTML (docs/MVP.md §4.5). No app, no database."""

import re

from markdown_it import MarkdownIt

# Q13: raw HTML off, and markdown-it's link check drops javascript:/vbscript:/file:/data: URLs.
MD = MarkdownIt("js-default", {"html": False})


def render(text: str | None) -> str:
    return MD.render(text or "")


def render_with_headings(text: str) -> tuple[str, list[dict]]:
    """029 Q1: render() with an `id` on every heading, plus the headings in document order as
    {id, text, level}. `text` is the heading's plain text (its text and code spans); `id` is that,
    lowercased, with each run of other characters as one `-`. Duplicate ids get no suffix."""
    tokens = MD.parse(text)
    headings = []
    for token, inline in zip(tokens, tokens[1:]):
        if token.type == "heading_open":
            plain = "".join(c.content for c in inline.children or [] if c.type in ("text", "code_inline"))
            slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
            token.attrSet("id", slug)
            headings.append({"id": slug, "text": plain, "level": int(token.tag[1])})
    return MD.renderer.render(tokens, MD.options, {}), headings
