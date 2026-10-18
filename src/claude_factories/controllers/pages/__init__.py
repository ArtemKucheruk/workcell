"""The Jinja pages and their htmx forms (docs/ui.md §8), until the SPA replaces them: the templates
with their filters and the header badge, and the form helpers."""

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Request, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from ...handlers.pages import claude_login
from ...lib import markdown
from ...server.deps import get_claude

templates = Jinja2Templates(directory=Path(__file__).parents[2] / "templates")
templates.env.filters["local_time"] = (  # 014 Q7: local_time("%H:%M") for run start times
    lambda iso, fmt="%Y-%m-%d %H:%M": datetime.fromisoformat(iso).astimezone().strftime(fmt)
)
# Q13: lib.markdown has raw HTML off and drops unsafe link schemes; this filter is the only place
# agent text becomes Markup.
templates.env.filters["markdown"] = lambda text: Markup(markdown.render(text))
# 036 Q4: base.html and the server's 404 page render it with no controller in between, so no Depends
templates.env.globals["claude_login"] = lambda: claude_login(get_claude())


async def form_field(request: Request, name: str) -> str:
    """Q10: htmx sends urlencoded forms; parse with the stdlib (no python-multipart)."""
    values = parse_qs((await request.body()).decode(errors="replace")).get(name)
    return values[0].strip() if values else ""


def hx_redirect(url: str) -> Response:
    return Response(status_code=204, headers={"HX-Redirect": url})
