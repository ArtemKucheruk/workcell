VERDICT: PASS

Checked in the worktree with a temp FCTL_HOME: `tests/test_review.py` 38 passed. The worktree's app.py, base.html, and pyproject.toml match round-1/diff.patch. A manual flow (connect project → submit standalone task → review page → comment → blank/no-header/unknown-round/unknown-task requests) matched the docs:
- `Review · waiting on you`, `1 file changed +2 −1`, `no agent review` on the standalone round, and the timeline reads `created · review · human_review`, then `round 1`, then `me · round 1` with `<p>Looks good</p>` after the comment.
- POST comment → 204 with `HX-Redirect: /tasks/1/review`. Blank body → 422 `body_md must not be blank`. Missing `X-Requested-By` → 403. Unknown round → 404 `#1 has no round 9`. Unknown task → 404.
- Titles and project name are escaped. The project link is `<a href="/projects/1">api</a>`.

## Nits (non-blocking)
- review.html:72-75 — a whitespace-only comment passes the `required` check, the server answers 422 JSON, and htmx does not swap on 4xx, so the user sees nothing happen. Spec Q9 accepts this, as 004's form does. Fix if wanted: an `htmx:responseError` handler on the form that shows the response's `detail` next to the button.
- app.py:760-770 and base.html:39 — an unknown review page (`/tasks/999/review`) returns the bare `{"detail":"Not Found"}` JSON, and `?round=9` returns `{"detail":"#1 has no round 9"}`. Both are readable and use the documented 404s, but they are JSON, not a page. This matches how the other HTML routes already behave, so fixing it is out of this job's scope.
- base.html:39 — `text-overflow: ellipsis` on `details.verdict summary` was not checked in a real browser, and `summary` is not always a block box, so the one-line clip may not appear. Confirm visually.
- app.py:787-791 — `add_comment_form` is `async` but calls the sync `post_comment` (DB writes) on the event loop. Not user-visible at this size. Fine to leave, or make the route `def` and read the form with a thread-safe path.
