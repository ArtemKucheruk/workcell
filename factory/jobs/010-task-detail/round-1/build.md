# Round 1
## Changes
- src/claude_factories/app.py: new `GET /tasks/{task_id}` (`task_page`), 404 detail `Task #<id> not found`. Moved review_page's two inline queries into `posted_verdicts(task_id)` (round n → {reviewer: verdict row}) and `approver_decision(task_id)` (latest `actor = 'approver'` by id, or None); both pages call them. The task row SELECT both pages run is one `PAGE_TASK` constant now. Build notes come from one `SELECT n, build_md FROM rounds WHERE task_id = ?`. History is `query(TIMELINE, …)` filtered to `kind == 0`, so the event labels and the created_at-then-id order come from the existing query. `round_summaries` and `/api/tasks/{id}` are unchanged.
- src/claude_factories/templates/task.html: new. Extends base.html. Inside one `<div id="live">` (Q10 poll, with a `ponytail:` comment naming the ceiling and the afterSwap upgrade path): a header (project link, `<h1>#id title</h1>`, Review's status · stage span, the branch `<code>` when set, and the `Review` link), then sections `description`, `spec` (rendered in the open), `rounds` (`round-<n>` blocks: Review's row with chips, a `<div popover>` per verdict with a non-blank body after the row's `<p>`, then collapsed `Build notes` or `No build notes.`), `approver` (only when one exists), and `history` (`<ol>` of `<time datetime>` + label).
- src/claude_factories/templates/base.html: `.chips span + span` → `.chips > * + *`, so button chips get the same spacing (same result on Review and the board). `.chips button` looks like Review's text chips plus a dotted underline to show it opens something. `[popover]` gets a width (`min(48rem, 90vw)`), a 70vh height limit with scroll, padding, and the GrayText border the page already uses. `#history` shares `#timeline`'s list and time rules. No new colors.
- tests/test_task_page.py: new, one test per AC. Imports test_review.py's seeding helpers (`add_task`, `add_round`, `add_verdict`, `add_decision`, `add_event`, `add_comment`, `at`, `project`, `text`, `section`, `header`, `not_found_page`) the way test_review_actions.py and test_review_files.py already do. Nothing is copied. Its own `block()` reads up to the next round or `</section>`, because test_review's `round_block` stops at the first `</div>`, which is now a popover's.

## Criteria → tests
- AC1 → tests/test_task_page.py::test_page_renders
- AC2 → tests/test_task_page.py::test_unknown_task_404
- AC3 → tests/test_task_page.py::test_project_link
- AC4 → tests/test_task_page.py::test_review_link
- AC5 → tests/test_task_page.py::test_status_stage (5 cases)
- AC6 → tests/test_task_page.py::test_branch
- AC7 → tests/test_task_page.py::test_description
- AC8 → tests/test_task_page.py::test_spec_open
- AC9 → tests/test_task_page.py::test_no_spec (NULL, whitespace)
- AC10 → tests/test_task_page.py::test_round_rows
- AC11 → tests/test_task_page.py::test_verdict_popover
- AC12 → tests/test_task_page.py::test_plain_chips
- AC13 → tests/test_task_page.py::test_no_agent_review
- AC14 → tests/test_task_page.py::test_build_notes
- AC15 → tests/test_task_page.py::test_no_build_notes (NULL, whitespace)
- AC16 → tests/test_task_page.py::test_no_rounds
- AC17 → tests/test_task_page.py::test_approver_latest
- AC18 → tests/test_task_page.py::test_no_approver
- AC19 → tests/test_task_page.py::test_history_labels
- AC20 → tests/test_task_page.py::test_history_events_only
- AC21 → tests/test_task_page.py::test_history_ties
- AC22 → tests/test_task_page.py::test_raw_html_off
- AC23 → tests/test_task_page.py::test_live_poll
- AC24 → tests/test_review.py (all 38 pass; `git diff` on the file is empty)

## Open questions
- Q1–Q11 → the spec's defaults, as written.
- Q12 (new): the spec says task.html "reuses review.html's `labels`, `short`, and `symbol` maps". They are `{% set %}`s inside review.html's content block, so they can't be imported, and review.html isn't in the Files list. Default: task.html carries the same three lines verbatim, with a comment saying where they come from. Moving them into `templates.env.globals` would mean editing review.html (and project.html has its own `short` with `co`). Say so if that's wanted.
- Checked in headless Chrome (playwright-cli, scratch FCTL_HOME): a title change shows up within one 3 s poll. Clicking `sec ✗` opens the popover, and no poll runs while it's open (a second rename stayed hidden). After Esc, the next poll showed it. The only console message was the existing favicon 404.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
546 passed, 1 warning in 58.57s
```
