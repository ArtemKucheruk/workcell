APPROVE
Built: `POST /api/tasks/{id}/approve` (200, `status` + shell-quoted `commit_hint`) and `POST /api/tasks/{id}/request-changes` (202, `run_id` null, blank `body_md` → 422). Both use `decide_review()`, which does everything in one `BEGIN IMMEDIATE`: the checks (404 unknown, 409 `#<id> is not in review`, 404 `#<id> has no rounds`), my decision on the latest round, the move with position kept, and a `me` event. Also built: the htmx form routes; `[Request changes] [Approve]` on the review page's title row, with the Summary textarea under the meta line and everything disabled unless the task is in review with a round; `section#commit` for done tasks; `fctl approve` and `fctl rework`. Nothing spawns a run.
Rounds: 2 of 2. In round 1, security, ux and code passed. ui asked for changes: the buttons weren't on the §8.2 title row. Round 2 fixed that with a grid in the header, and all four round-2 reviews PASS. There are no feedback files.
Tests: 492 passed (round-2 build.md; review-code re-ran them and got 492 passed). Each of AC1–AC26 maps to a test in tests/test_review_actions.py or tests/test_cli.py, and each test checks its criterion (exact JSON, row snapshots for "nothing written", shlex quoting, disabled buttons, escaped `<pre>`, CLI requests and stderr).
Docs: matches MVP §3.6, §3.7, §4.4, §10 OQ2; data-model §5.2, §6.3; claude-code §7.2, §7.4, §7.5; ui.md §8 item 5, §8.2. The only text difference is the commit-hint wording (Q4 below). One file is outside the spec's Files list: tests/test_review_files.py. Two 008 assertions (AC2, AC18: "no `<textarea`/`hx-post` on the Files tab") now check only the part of the page after `</header>`, because 009 AC18 puts the Summary box in the header.

## Open questions
Spec questions. The builder used every default as written:
- Q1 (standalone Request changes): the task moves to in_progress · rework like a factory task, with `run_id` null and no run. The next `fctl submit` creates round 3 (trigger `human`) and puts the task back in review · human_review. This matches §6.3 and §7.5. §7.4's "only records my feedback (no run)" is taken to mean "no run".
- Q2 (other statuses): both endpoints return 409 `#<id> is not in review` unless the status is review (either stage). The check runs inside the write transaction, so a double click can't approve twice.
- Q3 (review task with no rounds): 404 `#<id> has no rounds`, and both buttons are disabled.
- Q4 (commit_hint format): §3.7's 4 lines joined by `\n`, with no trailing newline. Line 1 `cd`s to the absolute worktree path. Line 4 is `cd <project path> && git worktree remove <worktree relative to project>`. Every value goes through `shlex.quote`, so the message is single-quoted. This differs from the literal text in docs/MVP.md §3.7 (relative `cd`, double quotes, a line 4 that fails after line 1's `cd`) and from docs/data-model-and-api.md §6.3's one-line `cd … && git add -A && …` example. Both doc examples could be updated to match.
- Q5 (standalone hint): only `git add -A && git commit -m <quoted title>`.
- Q6 (how long the commands show): the review page shows `section#commit` for any done task, built from the task row. It survives a reload and also appears after `fctl approve` or a drag to Done.
- Q7 (event actor): `me` for both actions.
- Q8 (position in the new column): unchanged.
- Q9 (summary): the API requires a non-blank `body_md` for request-changes (422 `body_md must not be blank`). Approve's `body_md` is optional and defaults to `''`. The `fctl rework` note is a required positional argument.
- Q10 (which round): both decisions always go on the latest round, whichever round the page shows.
- Q11 (fctl output): `fctl approve` prints `#<id>: done`, then the hint. `fctl rework` prints `#<id>: in_progress · rework`.
- Q12 (form placement): both forms are in the review page `<header>` on both tabs. The Approve form sends no summary.

Raised by the builder. None of these changes behavior the spec defines:
- Check order: 404 unknown task, then 409, then 404 no rounds. On request-changes the blank-body 422 comes first, so a blank note on a backlog task gets 422, not 409.
- A task with `worktree_path` set but `branch` NULL (only possible by hand) gets the one-line standalone hint.
- The Summary textarea is disabled along with the buttons. On a done task it stays visible, but disabled.
- AC17's 403 test also covers the two form routes.
- Round 2: there's no media query. On a narrow window the title wraps beside the buttons. ui checked 390px and nothing overflows.

Reviewer nits the builder declined (reasons in round-2/build.md):
- security: the per-project test-command allow entry (e.g. `Bash(pytest *)`) runs worktree code, and that code could POST `/api/tasks/{id}/approve` with the fctl header directly. So MVP §4.4's "agents can't call `fctl approve`" holds only at the fctl allowlist level. This predates the job; the reviewer suggests an Open question in docs/MVP.md §4.4.
- security: `fctl approve` prints the title without stripping terminal control bytes, as every `fctl` command that echoes task text does.
- ux: `fctl approve 999` prints `fctl: 404 Not Found` without naming the task. The whole app does this.
- ux (round 2): 007's TIMELINE puts events before decisions within the same second, so `done` shows above `me APPROVE · round N`. That's 007's query, which this job doesn't change.
- ui/ux: favicon 404 on every page (predates the job). Disabled buttons look faint in light mode, which the contrast rule allows for disabled controls.
