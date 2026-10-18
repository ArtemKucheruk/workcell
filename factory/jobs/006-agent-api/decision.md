ESCALATE
Built: the verdict PUT (one row per round and reviewer, posting again overwrites it), the comment POST, the decision POST, and `GET /api/tasks/{id}/context` as markdown (everything, `?round=`, or `?feedback=1`), all using one shared `round_or_404`. Also `fctl show/spec/stage/verdict/comment/decide/round`. No schema change and no new dependencies.
Rounds used: 2 of 2. All four round-2 reviews are PASS. 311 tests pass (build.md and review-code.md), and AC1–AC39 each map to a passing test in tests/test_agent_api.py or tests/test_cli.py.
You need to decide: Q11 changed the documented CLI. docs/claude-code.md §7.2 (line 35) and the §7.3 review-security template (line 89) give `fctl comment <id> --path P --line L`. The built CLI requires `fctl comment <id> <reviewer> --path P --line L` and rejects the documented form with exit 2.
In round 2, after round 1's ux CHANGES, the builder edited both docs lines to the new form. That was the only change in round 2. docs/ isn't in the spec's Files list, and the ux reviewer said the drift needs your explicit OK.
Accept Q11 and the docs edit (then approve as is), or reject them (the CLI then needs another way to name the comment author, and docs/claude-code.md goes back to how it was).

## Open questions
- Q1: Default used. One `round_or_404` serves the diff, verdict, comment, decision (always `latest`), and context routes. An unknown task gets the bare 404, checked first. Otherwise the 404 is `#<id> has no round <n>` or `#<id> has no rounds`.
- Q2: Default used. The path takes `n` or `latest`, and `fctl verdict` always sends `latest`. `body_md` defaults to `''`. Posting again replaces the verdict, body, and created_at. `complete` is the round's row count over 4. No status, stage, standalone, or run check blocks a write, and no write touches the task row or `events`.
- Q3: Default used. `round` is a number or `latest` (default `latest`). `author` is me, security, ux, ui, or code. `path` and `line` go together, `line` must be ≥ 1, and `side` is old or new (default new). A side without a path → 422. The path must be in the round's `round_files` (422 `<path> is not in round <n>`), and a blank body → 422 `body_md must not be blank`.
  - Builder additions: the two 422 texts the spec didn't give (`path and line go together`, `side needs a path`), and a cap of `line < 2**63`, so an oversized line gets a 422 instead of a SQLite overflow 500.
  - Security note for 012: the API accepts `author: "me"` from any caller that sends the fctl header. Only the CLI's choices stop an agent from posting as you.
- Q4: Default used. The actor is always `approver`, and only APPROVE or ESCALATE is accepted. `body_md` defaults to `''`. The decision goes on the latest round, every POST adds a row, and 4/4 verdicts aren't required first.
- Q5: Default used. Blocks are joined by one blank line. The view opens with `# #<id> <title>` and `Status: <status> · <stage>`, then `## Description` and `## Spec`. `_No spec yet._` shows only when spec_md is NULL. An empty string gives a bare heading. Each round has build notes, then Verdicts, then Comments and Decisions when there are any. The response is text/markdown with nosniff.
  - This goes beyond §6.2's literal example (`# #12 …\n## Spec\n…`), which has no Status line, no Description block, and no blank lines.
- Q6: Default used. Feedback is your latest CHANGES_REQUESTED (by id), shown under `## Feedback on round <n>` with only your comments on that round. No such decision → 404 `#<id> has no feedback`.
- Q7: Default used. `feedback` is a boolean query parameter, so `?round=1&feedback=0` is allowed. Sending both → 422, checked before the task lookup.
- Q8: Default used. Every output format is as listed in the spec.
- Q9: Default used. Ids are ints, values are checked by case-sensitive argparse choices, and `--round` and `--feedback` are mutually exclusive. Stdin comes through `stdin_text()`. A blank spec exits 1 and sends nothing. The CLI doesn't check `--line` ≥ 1; the server's 422 covers it.
- Q10: Default used. `fctl round` exits 1 with `fctl: #<id> has no rounds`.
- Q11: Default used. The command is `fctl comment <id> <reviewer> --path P --line L`, with reviewer choices security, ux, ui, or code, and it always sends `"round":"latest"` and `"side":"new"`. The builder also edited docs/claude-code.md to match (see above).
