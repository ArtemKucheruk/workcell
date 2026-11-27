"""057: what a context card takes from a file (docs/MVP.md §4.5). Pure: the extension check, and the title and
description from markdown-it-py's tokens (Q5), so a `# x` inside a code fence isn't a heading."""

from .markdown import MD

EXTENSIONS = (".md", ".markdown", ".txt")
MAX_DESCRIPTION = 160


def allowed(name: str) -> bool:
    """Q6: by the name's extension, case-insensitively."""
    return name.lower().endswith(EXTENSIONS)


def one_line(text: str) -> str:
    """Q8: each whitespace run as one space, trimmed."""
    return " ".join(text.split())


def derive(text: str, name: str) -> tuple[str, str]:
    """Q5: (title, description). The title is the first level-1 heading's text (ATX or setext), else `name` as
    given; the description the first paragraph's source text on one line, cut to 160 characters, else ""."""
    tokens = MD.parse(text)
    title = description = None
    for token, inline in zip(tokens, tokens[1:]):
        if title is None and token.type == "heading_open" and token.tag == "h1":
            title = one_line(inline.content)
        elif description is None and token.type == "paragraph_open":
            description = one_line(inline.content)[:MAX_DESCRIPTION]
    return title or one_line(name), description or ""
