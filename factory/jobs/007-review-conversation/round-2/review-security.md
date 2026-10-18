VERDICT: PASS

No blocking findings. Round 1's security review was PASS with nits only, so nothing had to be fixed. Round 2 changes only three things against round 1 (checked by diffing the two patches): the `page_not_found` handler, `one_or_404`'s `detail` argument, and the new `error.html`. Everything round 1 checked is unchanged: the markdown filter (`js-default` with `html: False`), autoescape, the parameterized SQL, the comment route through `post_comment()`, and the lockfile.

What I checked in round 2:

- Reflected input in the HTML 404 (`src/claude_factories/app.py:83-88`, `templates/error.html:5`): `exc.detail` goes into `<h1>{{ detail }}</h1>`. The user controls part of it through `round_or_404`'s `#<id> has no round <n>`, since `n` is the raw `round` query value. Starlette's `Jinja2Templates` uses `select_autoescape()`, which covers `.html`, and there is no `|safe`. I probed it: `?round=<script>alert(1)</script>` gives a 404 `text/html` page containing `&lt;script&gt;alert(1)` and no `<script>alert`. An unknown route with `<img onerror>` in the path renders no `<img`. The other new detail, `Task #<id> not found`, takes an int path parameter.
- Order of the guards: `local_safety` is HTTP middleware and returns its 403 `JSONResponse` before routing, so the new exception handler never runs ahead of it. Probed: a GET with `Host: evil.com` still gets a 403 JSON. A POST to `/tasks/<id>/comments` without `X-Requested-By` still gets a 403.
- Scope of the handler: it only takes 404s on GET outside `/api/`. Everything else goes back to FastAPI's `http_exception_handler`. Probed: `/api/tasks/999` still returns `{"detail": "Not Found"}`, and a POST to an unknown task's comments still gets a JSON 404. The agent API surface is unchanged.
- `one_or_404(..., detail=None)`: the default keeps every other caller's bare 404, so it leaks nothing new.
- The handler adds no subprocesses, SQL, logging, or file-path handling.
- Tests: `tests/test_review.py` plus my 3 probe tests (kept in the scratchpad, not in W) give 41 passed, run with `.venv/bin/python -m pytest` in W.

Not touched by this job: subprocesses, the run env and auth (§4.3), run allow and deny lists (§4.4), code and file paths, the 5 MB patch limit, and logging.

## Nits (non-blocking)
- src/claude_factories/app.py:60 — still open from round 1: markdown images are on, so `![t](http://host/p.png)` in agent or description text makes the browser fetch an outside URL when the review page opens. That's a tracking beacon, not script execution, and §4.5 only requires raw HTML off. — `MD.disable("image")` in a later job, if wanted.
- src/claude_factories/app.py (`form_field`, existing code) — still open from round 1: the urlencoded form body has no size cap. This predates the job and is shared by every form route. — Cap it if large local bodies ever matter.
