# Round 1
## Changes
- src/claude_factories/app.py: `ApproveBody` (optional `body_md`, default `''`) and `ChangesBody` (required `body_md`); `commit_hint(task)` builds §3.7's 4 lines with every value `shlex.quote`d (Q4), or the commit line alone when the task lacks a branch or worktree (Q5); `decide_review()` is the one shared transaction (`BEGIN IMMEDIATE`, 404 unknown task, 409 `#<id> is not in review`, 404 `#<id> has no rounds`, then decision on the latest round, task update with position kept, event with actor `me`); `POST /api/tasks/{id}/approve` (200, `status` + `commit_hint`) and `POST /api/tasks/{id}/request-changes` (202, `run_id` null, blank `body_md` → 422); the htmx form routes `POST /tasks/{id}/approve` and `/request-changes` (`form_field`, then `hx_redirect` to the review page); `review_page` selects `p.path` and passes `commit_hint` for a `done` task (Q6).
- src/claude_factories/templates/review.html: a `.review-actions` row in the `<header>` (so both tabs get it) with the Request changes form (labelled "Summary" `<textarea name="body_md" required>`, button, `.form-error`) and the Approve form (button, `.form-error`). Both buttons and the textarea get `disabled` unless the task is in `review` with at least one round (Q2, Q3). `section#commit` at the top of `<main>` shows the hint in an autoescaped `<pre>` for a done task.
- src/claude_factories/templates/base.html: 3 CSS lines for the action row and the `#commit pre` block.
- src/claude_factories/cli.py: `fctl approve <id>` (sends `{"body_md": ""}`, prints `#<id>: done` then the hint) and `fctl rework <id> <note>` (note is a required positional, prints `#<id>: in_progress · rework`). Updated the stale `DECISIONS` comment.
- tests/test_review_actions.py (new): AC1–AC23.
- tests/test_cli.py: AC24–AC26 appended, on the existing `server` fixture.
- tests/test_review_files.py: two 008 assertions (`test_tab_bodies`, `test_no_form_for_bad_target`) said "no `<textarea>` / `hx-post` anywhere on the Files tab". AC18 now puts the Summary box and the action forms in the header on that tab, so those assertions now check only the part of the page after `</header>`. What they test (no inline comment form) is the same.

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

## Open questions
- Q1–Q12 → the spec's defaults, as written.
- Check order when several apply (e.g. a backlog task with no rounds): 404 unknown task, then 409 not in review, then 404 no rounds, in the order the spec's Files section lists. For request-changes, the blank-body 422 comes before all of them because the body is checked first.
- A task with `worktree_path` set but `branch` NULL (only possible from a hand edit or a test fixture): `commit_hint` treats it as standalone and returns only the commit line, because there's no branch to push.
- The Summary textarea is also `disabled` when the buttons are, so I can't type a note that can't be sent.
- AC17 also covers the two form routes (`/tasks/{id}/approve`, `/tasks/{id}/request-changes`), not only the API ones.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
492 passed, 1 warning in 56.35s
```
