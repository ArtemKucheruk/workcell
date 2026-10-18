VERDICT: PASS

Round-1 UX findings are fixed. Checked against a temp-home server on port 4601 in the worktree (`FCTL_HOME` set to a scratch dir):
- `GET /tasks/999/review` → 404 `text/html`, `<h1>Task #999 not found</h1>`, home link. `?round=9` and `?round=abc` → 404 page `#1 has no round 9` / `#1 has no round abc`. `/projects/999` and `/nope` → 404 page `Not Found`. `/api/tasks/999` → 404 JSON `{"detail":"Not Found"}`, unchanged.
- Standalone flow: `fctl connect` → `Connected repo-api (personal) → …/projects/1`, exit 0. `fctl submit --new` → `Review #1: 1 file, +2 −0 → …/tasks/1/review`, exit 0. Review header reads `Review · waiting on you`, `1 file changed +2 −0`, round selector `round 1 ▾`. The round row shows `no agent review`. The timeline reads `created · review · human_review`, then `round 1`.
- Comment: a blank body → 422 `body_md must not be blank`. A valid body → 204 with `HX-Redirect: /tasks/1/review`, then `me · round 1` appears in the timeline. Raw HTML in the comment is escaped (`&lt;b&gt;`). A request without `X-Requested-By` → 403.
- CLI errors go to stderr and exit 1 (`fctl: 404 #1 has no round 9`, `fctl: 422 title must not be blank`). Success exits 0.

## Nits (non-blocking)
- app.py:477 — `fctl submit 999` prints `fctl: 404 Not Found`. It is readable but does not name the task. The route is outside this job's diff (`submit_round`, app.py:477, calls `one_or_404` without `detail`). Fix: pass `f"Task #{task_id} not found"` in `one_or_404` at app.py:505 and the other API lookups, so the CLI says what went wrong.
- app.py:83 — `/projects/999` and unknown routes show the generic `Not Found` on the error page. Fix: pass a specific detail at app.py:264 and app.py:712 for projects, as done for tasks and rounds.
- review.html:73 — a whitespace-only comment still gives a silent 422 in the browser (round-1 nit, accepted by Q9). Fix if wanted: an `htmx:responseError` handler that shows the response's `detail` next to the button.
- base.html:39 — `text-overflow: ellipsis` on `details.verdict summary` is still not checked in a real browser (round-1 nit). Confirm visually.
