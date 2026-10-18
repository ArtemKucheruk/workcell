VERDICT: CHANGES

- src/claude_factories/app.py:96-99 — `one_or_404` raises a bare `HTTPException(404)`, and no handler renders it as HTML. A browser on `/tasks/999/review`, `/tasks/<id>/review?round=99`, or `?round=abc` gets `{"detail":"Not Found"}` (application/json) or `{"detail":"#2 has no round 99"}`, not a designed error state. The check requires unknown-id error states to be designed. Fix: add an HTML handler for 404s on HTML routes (or a `review_missing` page that `review_page` renders with status 404) that shows a short "Task #N not found" or "#N has no round X" message and a link back to the project. This is app-wide, since the project and task pages share the bare 404. If it is scoped out of this job, say so in the job's notes and the finding stands for the review page.

## Nits (non-blocking)

- src/claude_factories/templates/review.html:73 — a whitespace-only comment passes `required`, gets the 422 `body_md must not be blank` (app.py:558), and htmx ignores 4xx, so the click appears to do nothing. Q9 accepts this, matching 004's new-task form. An inline message or a `pattern` attribute would be an improvement later.
- src/claude_factories/templates/review.html (comment form and round select) — the page has no live parts, so the 3 s poll rule is not triggered. Q10 chose no polling. Confirm this is intended.
- src/claude_factories/templates/base.html:39 — `text-overflow: ellipsis` on `details.verdict summary`. Summary elements are `display: list-item` in some engines, so the one-line clamp may not apply. Not checked in a real browser (none run here); verify the summary clamps on one line in Chrome and Safari.
- src/claude_factories/templates/review.html:73 — the textarea's only accessible name is `aria-label="Comment"` with no visible label. Meets the basics, but a visible or `sr-only` label would be clearer.

## Checked and OK

- Rendered with TestClient (base URL 127.0.0.1) in a temp FCTL_HOME: header and status text (`In progress · build`, `Review · waiting on you`, `Review · ⚠ NEEDS YOU — escalated`, `Backlog`), branch `<code>`, round select with `selected`, `1 file changed +118 −9` (U+2212), backlog task with no rounds (no selector, no files, `No rounds yet.`, comment-box hint), standalone round showing `no agent review`, and `?round=1` on a single-round task.
- Layout and labels match §8.2: project link, `#id title`, status line, branch, round selector, file count, Description with `(spec ▸)` as a collapsed `<details>`, round rows with chips and expandable verdict bodies, approver line, timeline, comment box.
- Light and dark: `<meta name="color-scheme" content="light dark">`, colors via `light-dark()` and system keywords (`GrayText`), no hard-coded backgrounds. The only color literal is the existing escalated red, now reused on `#status .escalated`.
- No build step. htmx, highlight.js, and both GitHub CSS themes are vendored under `src/claude_factories/static/`. Forms use `hx-post` and a real `<button>`. The round selector is a labeled `<select>` in a GET form, with a `<noscript>` submit fallback.
- Escaping: a verdict body `<img src=x onerror=…>` and a description `<script>` render as escaped text, and no raw `<img`/`<script` appears on the page.
- Focus: no `outline: none` anywhere in base.html, so the browser focus ring remains.
- Round-1 verification in build.md: 349 tests passed. Not re-run here.
