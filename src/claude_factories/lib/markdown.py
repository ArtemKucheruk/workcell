"""Agent markdown → HTML (docs/MVP.md §4.5). No app, no database."""

from markdown_it import MarkdownIt

# Q13: raw HTML off, and markdown-it's link check drops javascript:/vbscript:/file:/data: URLs.
MD = MarkdownIt("js-default", {"html": False})


def render(text: str | None) -> str:
    return MD.render(text or "")
