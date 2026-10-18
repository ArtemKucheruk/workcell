VERDICT: PASS

No blocking findings. Here is what the diff touches and what I checked:

- §4.5 markdown: `src/claude_factories/app.py:57-58` uses `MarkdownIt("js-default", {"html": False})`, not `commonmark`. I ran markdown-it-py 4.2.0 from the worktree venv against hostile inputs:
  - `<script>`, `<img onerror>`, and `<a href="javascript:">` all come out escaped.
  - `javascript:` (any case), `vbscript:`, `data:text/html`, `data:image/svg+xml`, and the `<javascript:…>` autolink are not turned into links.
  - Title-attribute breakout is escaped (`&quot;`).
  - `linkify` is off.
  - This filter is the only `Markup(...)` in the app.
- Jinja autoescape: Starlette's `select_autoescape()` covers `review.html`. No template uses `|safe`. Agent-controlled strings are escaped as plain text: timeline labels, including the comment `path`, the verdict summary's first line, the title, and the project name.
- CSRF and Host: the new `POST /tasks/{id}/comments` goes through the existing `local_safety` middleware, which checks Host and `X-Requested-By: fctl`. There is no CORS middleware. `base.html` keeps `hx-headers`, and AC30 tests the 403. The round selector is a GET and changes nothing.
- SQL: every new query is parameterized (`?` or the named `:task` with a dict). The `||` in `TIMELINE` is SQL concatenation, not Python string formatting.
- Writes: the comment route hardcodes `author="me"` and goes through 006's `post_comment()`. That function validates a blank body, an unknown task, and a task with no rounds, so no new write path skips validation.
- Dependencies: `uv.lock` adds only `markdown-it-py` and `mdurl` from PyPI.
- Not touched by this diff: subprocesses, the run env and auth (§4.3), run allow and deny lists (§4.4), code and file paths, the patch size limit, and logging.
- `tests/test_review.py`: 38 passed when run locally with `.venv/bin/python -m pytest`.

## Nits (non-blocking)
- src/claude_factories/app.py:57 — markdown images are still on. Agent or description text such as `![t](http://host/p.png)` renders `<img src="http://host/p.png">`, so opening the review page makes the browser fetch outside URLs. That is a tracking beacon, not script execution, and §4.5 only requires raw HTML off. — If wanted, add `MD.disable("image")` (or a renderer rule that prints the alt text and URL as a link) in a later job.
- src/claude_factories/app.py:129 (`form_field`, existing code) — the urlencoded body is read with no size cap, so a local caller can post a very large comment. This was already true of every form route before this job. — Cap it if large bodies ever matter.
