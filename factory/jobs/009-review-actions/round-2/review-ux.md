VERDICT: PASS

Walked in headless Chrome on a temp FCTL_HOME, server on 127.0.0.1, project connected with `fctl connect`, and ran the worktree's `fctl` against it (`uv run --project W fctl`). Round 1 findings are fixed: the buttons now sit on the title row (screenshot at 1280px), with Approve level with Request changes.

- Factory task in review: an empty Summary is stopped by the `required` textarea. A whitespace-only summary shows `body_md must not be blank` under the button, the task stays in review, and the console logs the 422. A valid summary posts and redirects to the review page, which shows `In progress · rework`, disabled Summary, Request changes and Approve, and the timeline `me CHANGES_REQUESTED · round 1` with the note.
- Request changes from the Files changed tab works the same way (redirect goes to the Conversation tab).
- Standalone task in review: Approve shows `Done`, `Commit it yourself` with `git add -A && git commit -m 'Fix open redirect after login'`, both buttons disabled, timeline `me APPROVE · round 1`.
- Factory task with an awkward title (`it's <b>x</b> $(touch x) "q"`) and a worktree path with a space: the commit section shows the four lines, shell-quoted; `<b>` is HTML-escaped and shows as text; nothing runs. The `git worktree remove '../../…'` line comes from my fixture (I set the worktree path under `/var/…` while the project path was stored as `/private/var/…`). It is not an app defect.
- A review task with no rounds (set by hand in the temp DB): both buttons render disabled.
- `GET /tasks/999/review` → 404 with `Task #999 not found`.
- CLI, from the worktree code:
  - `fctl rework 5 "Make the limit configurable"` → `#5: in_progress · rework`, exit 0.
  - `fctl approve 6` → `#6: done`, then the commit line, exit 0. A second approve → `fctl: 409 #6 is not in review` on stderr, exit 1.
  - `fctl approve 2` on backlog → `fctl: 409 #2 is not in review`, exit 1.
  - `fctl rework 5` with no note → argparse usage on stderr, exit 2. `fctl approve` with no id → exit 2.
  - `fctl rework 5 '   '` → `fctl: 422 body_md must not be blank`, exit 1.
- API: no `X-Requested-By` on the JSON and form routes → 403. Malformed JSON → 422. Request changes on an in_progress task → 409.
- Browser console: only the pre-existing `favicon.ico` 404, plus the expected 422 logged for the whitespace summary.

Checks: round 1 UI finding (buttons off the title row) fixed. Round 1 UX nit (`align-items: end`) fixed by the grid. Test suite not re-run; the UX walk did not depend on it.

## Nits (non-blocking)
- `src/claude_factories/app.py` (`TIMELINE`, 007's query, `ORDER BY created_at, kind, id`) — within one second the event sorts before the decision, so the timeline shows `done` above `me APPROVE · round 1`, and `in_progress · rework` above `me CHANGES_REQUESTED`. The decision happens first, so the order reads backwards. Fix (if wanted): sort decisions before events at the same second, or use a sub-second `created_at`. This is 007's query, so it can wait for a later job.
- `fctl approve 999` → `fctl: 404 Not Found` doesn't name the task. Already noted in round 1 and accepted as an app-wide pattern. Nothing to change in this job.
- `favicon.ico` 404 on every page. Pre-existing; not from this job.
