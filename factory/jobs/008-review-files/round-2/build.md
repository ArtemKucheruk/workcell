# Round 2
## Changes
- src/claude_factories/templates/review.html: both comment forms (the inline form and 007's conversation box) end with `<p class="form-error" role="alert"></p>`. One small inline script at the end of the page listens for `htmx:responseError` and `htmx:sendError`. It writes the response's `detail` into the posting form's `.form-error` with `textContent`. It handles `detail` as a string, a list of strings (the 422 from 008 Q11), or a list of `{msg}` objects. With no readable detail it falls back to `Request failed (<status>)`, or `Server unreachable` when the request never got a response. The script is on the review page only, because both forms live there. In base.html it broke 004's `test_drag_script`, which expects exactly one inline `<script>` on the project page.
- src/claude_factories/templates/base.html: `.form-error` is bold in the existing escalated red (`light-dark(#cf222e, #f85149)`), so no new color is added. There's no `:empty { display: none }`: a live region that starts out hidden may not be announced, and an empty `<p>` with no margin takes no space.
- src/claude_factories/app.py: `HUNK` now matches at most 18 digits per line number (`\d{1,18}`). A longer number no longer reaches `int()`, which raised `ValueError` past Python's 4300-digit limit and turned the files tab into a 500. A header like that is now not a hunk, so the file shows `No content changes.`
- tests/test_review_files.py: two new tests, one per fixed finding (below).

## Criteria → tests
- AC1 → tests/test_review_files.py::test_tab_bar
- AC2 → tests/test_review_files.py::test_tab_bodies (007's tests pass unchanged in the full run)
- AC3 → tests/test_review_files.py::test_round_form_keeps_tab
- AC4 → tests/test_review_files.py::test_no_rounds
- AC5 → tests/test_review_files.py::test_round_picks_diff
- AC6 → tests/test_review_files.py::test_file_tree
- AC7 → tests/test_review_files.py::test_tree_links
- AC8 → tests/test_review_files.py::test_file_headers
- AC9 → tests/test_review_files.py::test_auth_rows
- AC10 → tests/test_review_files.py::test_no_newline_note
- AC11 → tests/test_review_files.py::test_binary_and_rename_notes
- AC12 → tests/test_review_files.py::test_crlf
- AC13 → tests/test_review_files.py::test_escaped
- AC14 → tests/test_review_files.py::test_line_anchors
- AC15 → tests/test_review_files.py::test_line_link
- AC16 → tests/test_review_files.py::test_highlight
- AC17 → tests/test_review_files.py::test_inline_form
- AC18 → tests/test_review_files.py::test_no_form_for_bad_target
- AC19 → tests/test_review_files.py::test_inline_post
- AC20 → tests/test_review_files.py::test_inline_post_viewed_round
- AC21 → tests/test_review_files.py::test_inline_post_refused
- AC22 → tests/test_review_files.py::test_conversation_post_unchanged (and 007's test_review.py::test_comment_post)
- AC23 → tests/test_review_files.py::test_comments_in_place
- AC24 → tests/test_review_files.py::test_comment_escaped
- AC25 → tests/test_review_files.py::test_posted_comment_shows
- ui finding (round 1) → tests/test_review_files.py::test_form_errors
- security nit (round 1) → tests/test_review_files.py::test_huge_hunk_number

## Review findings
- ui · a failed inline or conversation post shows nothing (htmx doesn't swap 4xx and there was no `htmx:responseError` handler) → fixed. Both forms now have a `role="alert"` `.form-error`, and the review page fills it from the response's `detail`. `test_form_errors` checks the markup and that the script writes with `textContent`. The handler itself was also run in node against stub events: a 422 string, a 422 list of strings, a 422 list of `{msg}`, a 500 with a non-JSON body, a send error, and an element outside any form. Every case gave the expected text, and none threw. The script went into review.html instead of base.html, for the reason given under Changes.
- ui nit · line numbers in `GrayText` are about 4.1:1 on the light add/del tints → not changed. Spec Q9 makes the add/del backgrounds the only new hard-coded colors, and `GrayText` is the muted color the whole app already uses (004, 007). The fix is one rule if you want the suggested `light-dark(#57606a, #8b949e)`.
- security nit · a hunk header with a 5000-digit number made `int()` raise, so the files tab returned 500 → fixed. `HUNK` is bounded to `\d{1,18}`, and `test_huge_hunk_number` covers it.
- ux nit · 422 details use pydantic's wording → not changed. The form's hidden fields always carry valid values from the page. A pydantic message only shows up for a hand-made request. The errors a user can actually hit (`body_md must not be blank`, `#N has no round N`) are already plain.
- code nit · orphans are found with an O(files × comments) scan → not changed. That's fine at MVP scale, as the reviewer says.

## Open questions
- Where the error script lives (review page only, not base.html) → review.html. The project page's htmx forms (+ New task, Move) keep their current behavior, which is outside this job.
- Round 1's open questions still stand: AC2 checks `class="diff-table"` rather than the bare substring; a binary file with hunks shows its hunks; a repeated anchor gets only the first form; both navs carry an `aria-label`.

## Test output
```
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/008-review-files/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
425 passed, 1 warning in 51.23s
```
