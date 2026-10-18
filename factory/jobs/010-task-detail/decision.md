APPROVE
Built `GET /tasks/{id}` (task.html): header with project link, `#id title`, status · stage, branch, and Review link; description; spec rendered open; rounds with Review's row, native-popover verdict chips, and collapsed build notes; the approver's latest decision; status history from `events`. The whole page polls every 3 s inside `#live` and pauses while anything is open. review_page's two queries moved into `posted_verdicts` / `approver_decision`, and both pages use them. Base.html CSS gained a few rules and no new colors. No schema, dependency, or `/api` change.
Rounds: 1 of 2. All four reviews (code, security, ux, ui) are PASS, with non-blocking nits only.
Tests: 546 passed (build.md, re-run in review-code.md). Each of AC1–AC23 has a test in tests/test_task_page.py. AC24 holds: tests/test_review.py is unchanged and passes.
Docs: matches docs/ui.md §8 items 3–4 (run controls, run log, takeover, and the `Claude: Pro ✓` header are deferred to 014, as the spec says), MVP §4.1 / §4.5, data-model §5.1 / §6.4, and claude-code §7.4.

## Open questions
- Q1 (how a chip opens): native popover, no JS. A chip with a non-blank body is a `<button popovertarget>` that opens a `<div popover>`. Pending or blank-body chips are plain `<span title>`.
- Q2 (standalone): 007 Q6's rule. `worktree_path` NULL and no verdicts → `no agent review`.
- Q3 (row layout): Review's row, `code` label, §8.1 legend, rounds ascending, no file count.
- Q4 (build notes): collapsed `<details><summary>Build notes</summary>`, or muted `No build notes.`.
- Q5 (description, not in §8 item 4): shown above the spec, or `No description.`. Drop it if the page should list only §8 item 4.
- Q6 (spec collapsed?): rendered open, or `No spec yet.`.
- Q7 (which decision): only the latest `actor = 'approver'` decision by id. Your decisions show up only in the history.
- Q8 (history labels): Review's timeline event labels, oldest first, ties by id, with `<time datetime>`. Actor and note not shown.
- Q9 (header wording): 007 Q2's status · stage words, branch in `<code>`, a project link on top, Review link on every task.
- Q10 (poll): whole-page `#live` poll that pauses while a `details[open]` or `:popover-open` is open. The page goes stale while you read. A `ponytail:` comment names the upgrade path: reopen elements by id on `htmx:afterSwap`.
- Q11 (empty states): muted `No description.` / `No spec yet.` / `No rounds yet.` / `No build notes.`. No approver section when there's no decision.
- Q12 (new, from the builder): review.html's `labels` / `short` / `symbol` maps can't be imported (they are `{% set %}` inside its content block), so task.html copies the three lines verbatim, with a comment. They are identical today. No behavior change. To share them, move them to `templates.env.globals` (touches review.html).
