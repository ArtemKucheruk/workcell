VERDICT: PASS

The diff adds one read-only HTML route (`GET /tasks/{id}`), a template, CSS, and tests, and moves two of review_page's queries into helpers. Checked against §4.5, §4.3–§4.4, subprocess, and SQL:

- Markdown: every untrusted body (description, spec, build notes, verdict bodies, approver body) goes through the existing `markdown` filter (`MarkdownIt("js-default", {"html": False})`, app.py:65). That filter is the only place text becomes Markup. task.html has no `|safe`, and the new code adds no Markup.
- Autoescape: task.html renders through `templates` (Starlette Jinja2Templates, autoescape on). The title, project name, branch, stage, history labels, and `title=` attributes are escaped, quotes included. `hx-trigger` is a static string with no data in it. Ids in attributes (`task.id`, `r.n`, reviewer names from REVIEWERS) are ints or fixed names. The `autoescape=False` env at app.py:250 is the existing FACTORY_TEMPLATES one, which this diff doesn't touch.
- htmx swap: markdown with raw HTML off can't emit `hx-*` attributes, so the polled `#live` swap can't pick up injected htmx behavior.
- Host / X-Requested-By: the route is a GET and goes through the existing `local_safety` middleware's Host check. No mutating endpoint is added.
- SQL: `PAGE_TASK`, `posted_verdicts`, `approver_decision`, the build-notes SELECT, and `TIMELINE` all bind parameters (`?` / `:task`). There is no string formatting of values. The f-string at app.py's `task_page` builds only the 404 detail from an int path param, and error.html escapes it.
- No subprocess, run env, auth, allow/deny list, path, patch-size, or logging change.
- AC22 (`test_raw_html_off`) covers `<script>`/`<img onerror>` in the title, spec, build note, verdict, and approver body. tests/test_task_page.py and tests/test_review.py pass in W (67 passed).

## Nits (non-blocking)
- tests/test_task_page.py:442 — AC22 doesn't seed an HTML payload in `description_md` or the project name. They use the same filter and autoescape, so they're safe today — add the description to the test if you want the regression locked in.
