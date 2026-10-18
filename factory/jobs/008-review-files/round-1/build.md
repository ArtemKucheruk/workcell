# Round 1
## Changes
- src/claude_factories/app.py: `diff_rows(patch)` turns one `round_files.patch` into hunk/ctx/add/del/note rows with old/new numbers, sign and one trailing `\r` dropped, header lines (before the first `@@`, after any later `diff --git`) skipped (Q5). `review_files(round_id, target)` reads the round's files in rowid order and its inline comments, places comments under their line by `(path, side, line)` (a ctx row takes both sides, merged by id), collects comments whose line isn't in the diff as the file's `orphans`, marks the one row whose anchor matches `target` exactly as strings for the form (Q1, Q2), falls back to `Binary file not shown.` / `No content changes.` for files with no hunk, and sets `lang` from the extension (Q7). `file_tree(files)` builds the nested dict for the tree (Q6). `review_page` takes `tab`, `path`, `side`, `line` strings; `tab` is `files` or else `conversation` (Q4); reuses `round_or_404`, `query`, `round_summaries`. `add_comment_form` reads optional `round`/`path`/`side`/`line` (blank = absent), turns pydantic's `ValidationError` into a 422 with messages only (Q11), and redirects an inline comment to `?round=<n>&tab=files#<path:side:line>` read back from the stored row; a conversation comment keeps 007's redirect (Q3). `ponytail:` comment names the render-everything ceiling (Q10).
- src/claude_factories/templates/review.html: tab bar `<nav class="tabs">` replacing `<h2>Conversation</h2>`, hidden `tab=files` input in the round form, Conversation sections only on the Conversation tab, Files changed body (tree macro, file header, one `diff-table` per file, line-number anchor links, comments rows, orphan row, inline form row, `No rounds yet.`), and the inline highlight script with its `ponytail:` comment on per-line highlighting (Q7). Row loop uses Jinja whitespace control so each row is one line of HTML.
- src/claude_factories/templates/base.html: tab, two-column layout (stacks under 48rem), tree, file header, per-file horizontal scroll, monospace `white-space: pre` table, muted line numbers, hunk/note in `GrayText`, add/del `light-dark()` backgrounds with GitHub's colors (Q9), comment and form rows back to normal text and sticky-left so they stay in view on wide diffs, `code.hljs` transparent.
- tests/test_review_files.py: new; one test per criterion, imports 007's helpers from `test_review.py`, posts patches through `POST /api/tasks/{id}/rounds`.

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

## Open questions
- AC2 says the Conversation page has "no `diff-table`", but base.html's shared `<style>` names the `.diff-table` class on every page, so the literal substring can't be absent. → the test checks for no `class="diff-table"` element.
- A binary file whose patch still has a hunk (005's merged file ↔ symlink typechange) → its hunk rows are shown. `Binary file not shown.` appears only when there are no hunk rows.
- Anchors that repeat (only a malformed patch with overlapping hunks) → the first matching row gets the form and the comments. One form at most.
- The tab nav and the file tree nav carry `aria-label`s ("Review tabs", "Files") so the two landmarks can be told apart. The markup is `<nav class="tabs" aria-label=…>` and `<nav id="file-tree" aria-label=…>`.

## Test output
```
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/008-review-files/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
423 passed, 1 warning in 50.27s
```
