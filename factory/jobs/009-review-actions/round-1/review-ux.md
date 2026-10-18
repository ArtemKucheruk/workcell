VERDICT: PASS

Walked in a headless browser on a temp FCTL_HOME (server on 127.0.0.1, project connected through `fctl connect`), and ran `fctl` against it:
- Review page, factory task in review: Request changes with an empty Summary is blocked by the `required` textarea. A whitespace-only summary gets the red `body_md must not be blank` under the button, and the task stays in review. A valid summary redirects to the review page, which then shows `In progress · rework`, disabled Summary, Request changes and Approve, and the timeline `me CHANGES_REQUESTED · round 1` with the note under it.
- Review page, standalone task: Approve shows `Done`, the `Commit it yourself` section with `git add -A && git commit -m 'Fix open redirect after login'`, the buttons disabled, and the timeline `me APPROVE · round 1` then `done`. DB row: status done, done_at and updated_at set, position unchanged, one APPROVE decision, one event `review → done`.
- Factory task with an awkward title (`'`, `<b>`, `$(…)`) and a worktree path with a space: the commit section shows the four quoted lines, `<b>` shows as literal text, nothing runs. (The `cd /Users/…/claude-factories && git worktree remove '../../…'` line in my fixture is an artifact of my test setup, which connected the project from the wrong cwd; not a defect.)
- `fctl rework 4 "Make the limit configurable"` → `#4: in_progress · rework`, exit 0. A second rework → `fctl: 409 #4 is not in review`, exit 1. `fctl approve` on in_progress, backlog → 409, exit 1. `fctl rework 4` with no note → argparse usage on stderr, exit 2. `fctl rework 4 "   "` → `fctl: 422 body_md must not be blank`, exit 1.
- `fctl approve 6` on a review task → `#6: done` then the commit line, exit 0. Second approve → `fctl: 409 #6 is not in review`, exit 1, on stderr.
- Raw API: no `X-Requested-By` → 403; malformed body → 422; the htmx form routes return `{"detail": …}` 422/409 as expected.
- Browser console: no errors from this job (only a pre-existing `favicon.ico` 404).

Spec checks ran green: `pytest -q tests/test_review_actions.py tests/test_cli.py` → 113 passed.

## Nits (non-blocking)
- `src/claude_factories/app.py:~861` (`decide_review`, `raise HTTPException(404)`) — an unknown task id gives `fctl: 404 Not Found` on stderr, which doesn't name the task. Fix: `raise HTTPException(404, f"Task #{task_id} not found")` as `one_or_404` does on the review page. `fctl show 999` and `fctl stage 999` already print the same `404 Not Found`, so this is an app-wide pattern to change in one place, not a 009 regression.
- `src/claude_factories/templates/base.html` (the `.review-actions` rule, `align-items: end`) — the Approve button sits lower than Request changes, because the flex row aligns to the bottom of each form, including its empty `.form-error` line. Fix: `align-items: start` (or `flex-start`), and keep the Summary box at its top edge.
- `favicon.ico` returns 404 on every page. Pre-existing and not from this job; a `<link rel="icon" href="data:,">` in base.html would silence it.
