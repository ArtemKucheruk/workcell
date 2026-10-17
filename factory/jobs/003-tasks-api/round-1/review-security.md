VERDICT: PASS

No blocking findings.

## Checked
- §4.5 Host and CSRF: the new `POST /api/projects/{id}/tasks` and `PATCH /api/tasks/{id}` sit behind the existing global `local_safety` middleware, which this job leaves alone. I tested it in W with TestClient: POST or PATCH without `X-Requested-By: fctl` → 403, and a POST, PATCH, or GET with `Host: evil.example` or `attacker.localhost` → 403.
- SQL: every new query in `src/claude_factories/app.py` (`round_summaries`, `latest_run`, the four routes) passes values as `?` parameters. No string formatting. `PATCH /api/tasks/1 OR 1=1` → 422 (int path param).
- The 409 check, the update, and the `events` insert run in one `BEGIN IMMEDIATE` transaction inside `with conn:`, so an `HTTPException` (404 or 409) rolls back and no partial row is written.
- New `RequestValidationError` handler: it removes the echoed `input` and keeps `jsonable_encoder`. It leaks nothing new, and a NaN or Infinity body now gets 422 instead of 500 (checked: `position: Infinity` → 422).
- Subprocesses: none added. `fctl task add` reuses `main_checkout()` (git takes an argument list) and `api()`. The path goes through `urllib.parse.urlencode`. Agents can't run `fctl task add`, because it isn't on the §4.4 allowlist.
- §4.3 and §4.4: there is no run spawning, env handling, or allow/deny list in this job. Stages map only to `in_progress` and `review`, so `fctl stage` (006) can't move a task to `done`. Only the manual move can, and only with the header.
- No templates, markdown rendering, file-path serving, patch upload, or logging in this diff.
- Suite in W: 144 passed.

## Nits (non-blocking)
- tests/test_tasks.py: no test checks that the new POST and PATCH routes refuse a request without `X-Requested-By: fctl`. The global middleware and its existing tests cover this today. A one-line 403 check on `PATCH /api/tasks/{id}` would catch it if the route ever moved to a sub-app or router that skips the middleware.
