# Round 2
## Changes
- src/claude_factories/templates/review.html: the header content now sits in a `div.review-header` grid. The test helpers match a bare `<header>`, so the grid goes on an inner div. The two action forms are direct children of that grid. The Request changes form holds a `div.summary` (the "Summary" label, the `<textarea name="body_md" required>`, and its `.form-error`) and then the `button.request-changes`. The Approve form holds `button.approve` and its `.form-error`. The DOM order is unchanged (title, meta, Summary, buttons), so the reading order and the Tab order are still: fill in Summary, then Request changes, then Approve.
- src/claude_factories/templates/base.html: replaced the `.review-actions` flex rules with a grid on `.review-header` (`minmax(0, 1fr) auto auto`, `align-items: center`). Both forms are `display: contents`, which lets the two buttons go on the title row (row 2, beside the `<h1>`, on one line) while the textarea stays inside its form, as AC18 requires. Approve's `.form-error` sits right-aligned in the row under the buttons. The Summary block runs full width under the meta line, max 48rem. Checked in headless Chrome at 1200px: a review task, a done task (disabled buttons and `#commit`), and a long title that wraps beside the buttons.

## Criteria → tests
- AC1 → tests/test_review_actions.py::test_approve
- AC2 → tests/test_review_actions.py::test_approve_decision
- AC3 → tests/test_review_actions.py::test_approve_event
- AC4 → tests/test_review_actions.py::test_approve_escalated
- AC5 → tests/test_review_actions.py::test_commit_hint_factory
- AC6 → tests/test_review_actions.py::test_commit_hint_quoted
- AC7 → tests/test_review_actions.py::test_commit_hint_standalone
- AC8 → tests/test_review_actions.py::test_approve_not_in_review, tests/test_review_actions.py::test_approve_twice
- AC9 → tests/test_review_actions.py::test_approve_missing
- AC10 → tests/test_review_actions.py::test_request_changes
- AC11 → tests/test_review_actions.py::test_request_changes_rows
- AC12 → tests/test_review_actions.py::test_request_changes_standalone
- AC13 → tests/test_review_actions.py::test_request_changes_blank
- AC14 → tests/test_review_actions.py::test_request_changes_refused
- AC15 → tests/test_review_actions.py::test_request_changes_feedback
- AC16 → tests/test_review_actions.py::test_request_changes_then_submit
- AC17 → tests/test_review_actions.py::test_actions_need_fctl_header
- AC18 → tests/test_review_actions.py::test_action_forms
- AC19 → tests/test_review_actions.py::test_action_forms_disabled
- AC20 → tests/test_review_actions.py::test_approve_form
- AC21 → tests/test_review_actions.py::test_request_changes_form
- AC22 → tests/test_review_actions.py::test_commit_section
- AC23 → tests/test_review_actions.py::test_timeline_after_actions
- AC24 → tests/test_cli.py::test_approve
- AC25 → tests/test_cli.py::test_rework
- AC26 → tests/test_cli.py::test_rework_needs_note, tests/test_cli.py::test_approve_refused

## Review findings
- ui · buttons not on the title row per the §8.2 wireframe; the stacked row looks broken and Approve doesn't line up with Request changes → fixed. `[Request changes] [Approve]` are now top right beside the `<h1>`, centred on one line. The Summary label and textarea are in their own row under the title and meta line. The meta line and tabs are unchanged.
- ux · nit: `align-items: end` puts Approve lower than Request changes → fixed by the same change. The flex row is gone, and the two buttons share one grid row with `align-items: center`.
- ux · nit: an unknown id gives `fctl: 404 Not Found` without naming the task → not changed. The reviewer notes that `fctl show` and `fctl stage` already behave this way across the app. Changing only these two routes would make them inconsistent with the rest. It's better done once for every route in a separate job.
- ui, ux · nit: `/favicon.ico` 404 on every page → not changed. It predates this job, and the spec limits base.html to the action forms' CSS.
- ui · nit: the disabled Approve button is faint in light mode → not changed. Disabled controls are exempt from the contrast rule, as the reviewer says.
- security · nit: `fctl approve` prints the title in the hint without stripping terminal control bytes → not changed. Every `fctl` command that echoes task text does the same. The fix the reviewer suggests (reject control characters in titles at the API) belongs in task creation, not in this job.
- security · nit: a run's per-project test command could call `/api/tasks/{id}/approve` directly → not changed. This predates the job, and the reviewer asks for a docs Open question (§4.4) rather than code. Flagging it here for the docs.
- code · nits (narrowed 008 assertions, the worktree-without-branch hint) → no change. Both are documented in round 1 and the reviewer accepts them.

## Open questions
- Q1–Q12 → the spec's defaults, as in round 1.
- Narrow viewports: the button columns are `auto` and the title column is `minmax(0, 1fr)`, so on a narrow window the title wraps beside the buttons rather than going under them. There's no media query, because the rest of the app (the board) isn't laid out for narrow screens either.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
492 passed, 1 warning in 54.43s
```
