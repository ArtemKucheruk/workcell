# 006-agent-api: Agent API (verdicts, comments, decision, context, fctl)

## Goal
Give agents everything they need to read and write a task through `fctl`. Reviewers post a verdict on a round (posting again overwrites it) and can leave inline comments. The approver posts a decision. `GET /api/tasks/{id}/context` returns the task as markdown in one of three views: everything, one round, or my latest feedback. `fctl show`, `spec`, `stage`, `verdict`, `comment`, `decide`, and `round` wrap these endpoints and the existing task GET and PATCH, and take their markdown from stdin heredocs.

## Implements
- `docs/data-model-and-api.md §6.3`: `PUT /api/tasks/{id}/rounds/latest/verdicts/{reviewer}` (body `verdict`, `body_md`; the `round`, `reviewer`, `verdict`, `complete` response), `POST /api/tasks/{id}/comments` (body `round`, `author`, `path`, `line`, `side`, `body_md`; `201 {"id"}`), and `POST /api/tasks/{id}/decision` (body `decision`, `body_md`; `201 {"id"}`).
- `docs/data-model-and-api.md §6` (preamble): `latest` can stand in for a round number, on the verdict path, in the comment body, and in the context `?round=`.
- `docs/data-model-and-api.md §6.2`: `GET /api/tasks/{id}/context?round=N | ?feedback=1` as `text/markdown` (the `# #12 Title`, `## Spec`, `## Round 1 — build notes`, `## Verdicts` shape). Also `GET /api/tasks/{id}` (for `fctl round`) and `PATCH /api/tasks/{id}` `spec_md` / `stage` (for `fctl spec` / `fctl stage`), which already exist and are unchanged.
- `docs/data-model-and-api.md §5.1`: writes to `verdicts` (primary key `(round_id, reviewer)`, so posting again overwrites), `comments` (author `me` or a reviewer name; `path`/`line`/`side` all NULL means a conversation comment), and `decisions` (actor `approver`). No schema change.
- `docs/MVP.md §4.3`: content lives in the DB only, and `fctl show` prints the markdown the job folders used to hold. Markdown goes in on stdin heredocs.
- `docs/MVP.md §3.6 step 3`: `fctl show <id> --feedback` has my summary and my inline comments.
- `docs/MVP.md §10 assumption 12`: reviewer agents may leave inline comments.
- `docs/claude-code.md §7.2`: the `show`, `spec`, `verdict`, `comment`, `decide`, `stage`, and `round` rows, including the exact `round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)` output.
- `docs/claude-code.md §7.3`: the template calls `fctl verdict <id> security PASS|CHANGES <<'EOF'`, `fctl show <id> --round <n>`, `fctl show <id> --feedback`, and "go on only when `fctl round <id>` shows 4/4".
- `docs/claude-code.md §7.5`: reviewers and the approver never change status. They post only their own record.
- `docs/MVP.md §4.5`: the new mutating routes sit behind the existing middleware. Agent text is served as markdown text, never as HTML.

## Acceptance criteria

Unless a criterion says otherwise, tasks, rounds, round files, decisions, and comments are set up by SQL, as in `tests/test_rounds.py` and `tests/test_tasks.py`. "Unchanged task" means the same status, stage, position, `updated_at`, and `events` rows.

`PUT /api/tasks/{id}/rounds/{n|latest}/verdicts/{reviewer}`
- [ ] AC1: a task with rounds 1 and 2, and `PUT …/rounds/latest/verdicts/security` with `{"verdict":"CHANGES","body_md":"1. app/limits.py:31 trusts X-Forwarded-For …"}` → 200 with exactly `{"round":2,"reviewer":"security","verdict":"CHANGES","complete":"1/4"}`. One `verdicts` row on round 2 holds that verdict and body, with `created_at` in the `db.now()` format. Round 1 has no row.
- [ ] AC2: round 2 already has `ux` and `code` verdicts → a `security` PUT returns `"complete":"3/4"`. A following `ui` PUT returns `"complete":"4/4"` (Q2).
- [ ] AC3: a `security` row on round 2 inserted by SQL as CHANGES, with `created_at` `2026-01-01T00:00:00Z`, then a PUT with `{"verdict":"PASS","body_md":"Fixed."}` → 200 with `"complete":"1/4"`. There is still exactly one `(round 2, security)` row, now PASS with `Fixed.` and a new `created_at` (Q2).
- [ ] AC4: `PUT …/rounds/1/verdicts/ux` on a task with rounds 1 and 2 → the row lands on round 1, and the response has `"round":1` and counts round 1's verdicts only.
- [ ] AC5: a body without `body_md` → 200, and the stored `body_md` is `''` (Q2).
- [ ] AC6: each of these → 422, and no `verdicts` row is written: reviewer `approver` or `Security` in the path, or a body whose verdict is `pass`, `APPROVE`, or missing.
- [ ] AC7: a task without rounds, with `latest` → 404 `{"detail":"#<id> has no rounds"}`. `/rounds/9/verdicts/ux` → 404 `{"detail":"#<id> has no round 9"}`. An unknown task → 404. None of them writes a row (Q1).
- [ ] AC8: a verdict on a task in done, and on a standalone task (`worktree_path` NULL) → 200 both times (Q2).

`POST /api/tasks/{id}/comments`
- [ ] AC9: round 2 holds a `round_files` row for `app/limits.py`. §6.3's body `{"round":"latest","author":"security","path":"app/limits.py","line":31,"side":"new","body_md":"Use request.client.host unless behind a known proxy."}` → 201 with exactly `{"id":<new id>}`. The `comments` row has that `task_id`, round 2's `round_id`, author `security`, path, line 31, side `new`, the body, and `created_at` set.
- [ ] AC10: `{"author":"me","body_md":"Looks close."}`, with no `round`, `path`, `line`, or `side` → 201. The row is on the latest round, with `path`, `line`, and `side` all NULL (Q3).
- [ ] AC11: rounds 1 and 2, and `{"round":1,"author":"ux","path":<a file in round 1>,"line":3,"body_md":"x"}` → the row is on round 1, with side `new` (Q3).
- [ ] AC12: each of these → 422, and no `comments` row is written: author `approver` or `bob`; `path` without `line`; `line` without `path`; `side` without `path`; side `both`; line `0`; `body_md` missing or `"  "`; and path `app/nope.py`, which is not in round 2's files, → 422 `{"detail":"app/nope.py is not in round 2"}` (Q3).
- [ ] AC13: `"round":9` → 404 `#<id> has no round 9`. A task without rounds → 404 `#<id> has no rounds`. An unknown task → 404. None of them writes a row (Q1).

`POST /api/tasks/{id}/decision`
- [ ] AC14: rounds 1 and 2, and `{"decision":"APPROVE","body_md":"All 4 PASS on round 2; criteria met; tests green."}` → 201 with exactly `{"id":<new id>}`. The `decisions` row has round 2's `round_id`, actor `approver`, APPROVE, the body, and `created_at` set. `GET /api/tasks/{id}` then lists it with `"round":2,"actor":"approver"`.
- [ ] AC15: `{"decision":"ESCALATE"}` → 201, and the stored `body_md` is `''` (Q4).
- [ ] AC16: a second POST on the same round → 201 with a new id. Both rows are kept (Q4).
- [ ] AC17: decision `CHANGES_REQUESTED`, `approve`, or missing → 422, and no row is written (Q4).
- [ ] AC18: a task without rounds → 404 `#<id> has no rounds`. An unknown task → 404. Neither writes a row (Q1).

All three write routes
- [ ] AC19: a task in in_progress · agent_review, then a verdict, a comment, and a decision → the task is unchanged (§7.5, Q2).
- [ ] AC20: the verdict PUT, comment POST, and decision POST without `X-Requested-By: fctl` → 403, and no row is written.

`GET /api/tasks/{id}/context`

The context fixture is a task titled `Rate-limit login endpoint` in in_progress · agent_review, with `description_md` `Max 5 failed logins/min per IP.\n` and `spec_md` `- 6th failed login within 60s → 429\n`.
- Round 1 has `build_md` `Token bucket in app/limits.py.\n` and three verdicts: security CHANGES `Trusts X-Forwarded-For.`, ux PASS `''`, and code PASS `Tests cover it.\n`. It has one comment: security on `app/limits.py`, line 31, side `new`, `Use request.client.host.`
- Round 2 has `build_md` NULL, and no verdicts or comments.
- [ ] AC21: `?round=1` → 200. The content type starts with `text/markdown`, `X-Content-Type-Options` is `nosniff`, and the body is exactly the block below, followed by one `\n` (Q5):
  ```
  # #<id> Rate-limit login endpoint
  Status: in_progress · agent_review

  ## Description
  Max 5 failed logins/min per IP.

  ## Spec
  - 6th failed login within 60s → 429

  ## Round 1 — build notes
  Token bucket in app/limits.py.

  ## Verdicts

  ### security: CHANGES
  Trusts X-Forwarded-For.

  ### ux: PASS

  ### ui: pending

  ### code: PASS
  Tests cover it.

  ## Comments

  ### security on app/limits.py:31 (new)
  Use request.client.host.
  ```
- [ ] AC22: no query on the same task → AC21's body without its final `\n`, then `\n\n## Round 2 — build notes\n\n## Verdicts\n\n### security: pending\n\n### ux: pending\n\n### ui: pending\n\n### code: pending\n`. Round 2 has no comments, so it has no `## Comments` block (Q5).
- [ ] AC23: `?round=latest` → the same body as `?round=2`.
- [ ] AC24: an approver ESCALATE decision on round 1 with body `Round cap reached.` → `?round=1` ends with `Use request.client.host.\n\n## Decisions\n\n### approver: ESCALATE\nRound cap reached.\n` (Q5).
- [ ] AC25: a fresh task titled `x`, with no description, no spec, and no rounds → exactly `# #<id> x\nStatus: backlog\n\n## Description\n\n## Spec\n_No spec yet._\n` (Q5).
- [ ] AC26: the fixture is set to stage rework, with these extra rows, in this order:
  - my CHANGES_REQUESTED on round 1, `Old note.`;
  - my CHANGES_REQUESTED on round 2, `Make the limit configurable via settings.`;
  - on round 2, my inline comment on `app/limits.py`, line 12, side `old`, `Keep the old default.`;
  - on round 2, my conversation comment `Also log it.`;
  - on round 2, a security comment `x`.

  `?feedback=1` → the body starts with `# #<id> Rate-limit login endpoint\nStatus: in_progress · rework\n\n## Description\n` and ends with `## Spec\n- 6th failed login within 60s → 429\n\n## Feedback on round 2\nMake the limit configurable via settings.\n\n## Comments\n\n### me on app/limits.py:12 (old)\nKeep the old default.\n\n### me\nAlso log it.\n`. It contains neither `Old note.` nor `## Round` (Q6).
- [ ] AC27: a task whose only decision is an approver ESCALATE → `?feedback=1` gives 404 `{"detail":"#<id> has no feedback"}` (Q6).
- [ ] AC28: `?round=9` → 404 `#<id> has no round 9`. `?round=latest` on a task without rounds → 404 `#<id> has no rounds`. An unknown task → 404. `?round=1&feedback=1` → 422 `{"detail":"give round or feedback, not both"}` (Q1, Q7).

`fctl` commands (`cli.main([...])` against the recording `server` fixture in `tests/test_cli.py`, with `sys.stdin` replaced as in 005's tests)
- [ ] AC29: the reply is `text/markdown` with body `# #12 x\n…`. `fctl show 12` → one `GET /api/tasks/12/context`, and stdout equals the body exactly. `--round 2` → `GET /api/tasks/12/context?round=2`. `--feedback` → `GET /api/tasks/12/context?feedback=1`.
- [ ] AC30: with stdin `## Acceptance criteria\n- x\n`, `fctl spec 12` → one `PATCH /api/tasks/12` with body exactly `{"spec_md":"## Acceptance criteria\n- x\n"}`. Stdout is `Spec saved on #12\n` (Q8).
- [ ] AC31: `fctl spec 12` with stdin `"  \n"`, or with stdin a terminal (005's `Terminal` stand-in) → exit 1, stderr `fctl: spec is empty; pass it on stdin\n`, and no request (Q9).
- [ ] AC32: the reply is `{"id":12,"status":"in_progress","stage":"agent_review"}`. `fctl stage 12 agent_review` → one `PATCH /api/tasks/12` with body exactly `{"stage":"agent_review"}`, and stdout `#12: in_progress · agent_review\n` (Q8).
- [ ] AC33: the reply is §6.3's `{"round":1,"reviewer":"security","verdict":"CHANGES","complete":"3/4"}`. With stdin `1. app/limits.py:31 …\n`, `fctl verdict 12 security CHANGES` → one `PUT /api/tasks/12/rounds/latest/verdicts/security` with body exactly `{"verdict":"CHANGES","body_md":"1. app/limits.py:31 …\n"}`, and stdout `Round 1 of #12: security=CHANGES (3/4)\n` (Q8).
- [ ] AC34: the reply is `{"id":88}`. With stdin `Use request.client.host.\n`, `fctl comment 12 security --path app/limits.py --line 31` → one `POST /api/tasks/12/comments` with body exactly `{"round":"latest","author":"security","path":"app/limits.py","line":31,"side":"new","body_md":"Use request.client.host.\n"}`, and stdout `Comment #88 on #12 app/limits.py:31\n` (Q8, Q11).
- [ ] AC35: the reply is `{"id":7}`. With stdin `All 4 PASS.\n`, `fctl decide 12 APPROVE` → one `POST /api/tasks/12/decision` with body exactly `{"decision":"APPROVE","body_md":"All 4 PASS.\n"}`, and stdout `Decision #7 on #12: APPROVE\n` (Q8).
- [ ] AC36: with stdin a terminal, `fctl verdict 12 ux PASS`, `fctl comment 12 ux --path a.py --line 1`, and `fctl decide 12 ESCALATE` each send `"body_md":""` without reading stdin (005 Q9).
- [ ] AC37: the reply is a `GET /api/tasks/12` body with rounds 1 and 2, where round 2's verdicts are security PASS, ux PASS, ui pending, and code PASS. `fctl round 12` → one `GET /api/tasks/12`, and stdout exactly `round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)\n`.
- [ ] AC38: the reply has `"rounds":[]` → `fctl round 12` exits 1 with stderr `fctl: #12 has no rounds\n` (Q10).
- [ ] AC39: each of these → exit 2, stderr starting with `usage: fctl <command>`, and no request (Q9, Q11):
  - `fctl show 12 --round 2 --feedback`, `fctl show abc`;
  - `fctl stage 12 deploy`;
  - `fctl verdict 12 approver PASS`, `fctl verdict 12 security pass`, `fctl verdict 12 security`;
  - `fctl comment 12 me --path a.py --line 1`, `fctl comment 12 security --path a.py`, `fctl comment 12 security --path a.py --line x`, `fctl comment 12 --path a.py --line 1`;
  - `fctl decide 12 CHANGES_REQUESTED`, `fctl decide 12 approve`;
  - `fctl round`.

## Files
- `src/claude_factories/app.py`:
  - The four new routes, and Pydantic bodies for the verdict, the comment, and the decision.
  - Pull `round_diff`'s round lookup into one helper that takes `n` or `latest` and raises 005's 404 details. Use it in the diff route, the verdict, comment, and decision routes, and the context route. 005's diff tests keep passing unchanged.
  - One function renders the context markdown (Q5, Q6).
- `src/claude_factories/cli.py`: the `show`, `spec`, `stage`, `verdict`, `comment`, `decide`, and `round` subcommands. They reuse `api()` and `stdin_text()`. None of them needs git or the cwd. The CLI keeps its own tuples of reviewers, stages, and decisions for argparse `choices`, because it must not import `app.py` (001's AC3).
- `tests/test_agent_api.py`: new. AC1–AC28.
- `tests/test_cli.py`: AC29–AC39. The `server` fixture's handler also answers PUT and PATCH (`do_PUT = do_PATCH = handle_one`). The existing tests keep passing unchanged.
- `tests/conftest.py`: only for helpers both test files share.

No schema change and no new dependencies.

## Out of scope
- Showing verdicts, comments, and decisions on the review page, and the conversation comment box (007). The inline comment UI that posts `me` comments (008).
- `POST /api/tasks/{id}/approve` and `/request-changes`, my APPROVE and CHANGES_REQUESTED decisions, and `fctl approve` / `fctl rework` (009). Tests insert my decisions by SQL.
- The task page (010). The factory templates that call these commands, including the comment reviewer argument (011). The run allowlist (012).
- Any status or stage change from a verdict, comment, or decision. Only the orchestrator's `fctl stage` changes stage (§4.3, §7.5).
- Editing or deleting comments, replies and threads, resolving comments (Later, §9), verdict history beyond the overwrite, a `--side` flag, and conversation comments from the CLI.
- Size limits on verdict, comment, decision, or spec bodies. Checking that a command runs inside the task's project.

## Open questions
- Q1: The new routes need a round that may not exist, and docs give no error for that. Default: reuse 005 Q7's lookup and details everywhere. `latest` is the highest `n`. A missing round, or an `n` that matches none, → 404 `#<id> has no round <n>`. `latest` on a task without rounds → 404 `#<id> has no rounds`. The decision route always uses `latest`. An unknown task → the bare 404, checked first.
- Q2: §6.3 shows one verdict call. Default:
  - The path takes `n` or `latest` (§6 preamble). `fctl verdict` always sends `latest`.
  - `body_md` is optional and defaults to `''`. The schema column is NOT NULL, and a PASS may say nothing.
  - Posting again replaces `verdict`, `body_md`, and `created_at`, so the timeline shows when the current verdict was given.
  - `complete` is `"<rows on that round>/4"`.
  - No status, stage, standalone, or running-run check blocks a verdict, comment, or decision (as in 005 Q2). None of them touches the task row or writes an `events` row: they aren't status changes, and 007's timeline reads their own tables.
- Q3: §5.1 and §6.3 give the comment fields but no rules. Default:
  - `round` is a number or `latest`, and defaults to `latest`.
  - `author` is one of `me`, `security`, `ux`, `ui`, or `code` (the schema comment).
  - A conversation comment has `path`, `line`, and `side` all NULL. An inline comment needs `path` and `line` together. `line` must be ≥ 1, and `side` is `old` or `new`, defaulting to `new`. A `side` without a `path` → 422.
  - `path` must be one of the round's `round_files.path`, or 422 `<path> is not in round <n>`, so every inline comment has a file to show up next to in 008. The line itself isn't checked against the hunks.
  - A blank `body_md` → 422 `body_md must not be blank`, stored as sent otherwise.
  - The response is exactly `{"id"}`.
- Q4: §6.3 shows one decision call. Default:
  - The actor is always `approver`, and `decision` is `APPROVE` or `ESCALATE`. My `APPROVE` and `CHANGES_REQUESTED` go through 009's routes, so they → 422 here.
  - `body_md` defaults to `''` (the schema default).
  - The decision is on the latest round. Every POST adds a row: unlike verdicts, the schema doesn't key decisions per round, and readers take the latest.
  - The route doesn't require 4/4 verdicts first. WAIT FOR ALL is the orchestrator's job.
- Q5: §6.2's example gives only `# #12 Rate-limit login endpoint\n## Spec\n…\n## Round 1 — build notes\n…\n## Verdicts\n…`. Default:
  - The text is a list of blocks, joined by one blank line, and ends with one `\n`. A block is a heading line, followed on the next lines by its body with trailing whitespace stripped, when the body isn't blank.
  - Every view starts with these blocks:
    - `# #<id> <title>` with body `Status: <status> · <stage>`, or `Status: <status>` when the stage is NULL. The orchestrator reads its current stage here (§7.3 step 1).
    - `## Description`, with the description.
    - `## Spec`, with the spec, or `_No spec yet._` when it is NULL.
  - Blocks for one round:
    - `## Round <n> — build notes` (with an em dash), with its `build_md`.
    - `## Verdicts`, then one `### <reviewer>: <PASS|CHANGES|pending>` for each of security, ux, ui, and code, in that order, with its body.
    - Only if the round has comments: `## Comments`, then by id `### <author> on <path>:<line> (<side>)`, or `### <author>` for a conversation comment, with its body.
    - Only if it has decisions: `## Decisions`, then by id `### <actor>: <decision>`, with its body.
  - No query → every round in `n` order (the whole job folder, §4.3). `?round=` → only that round.
  - Agent text is passed through as is. Headings inside a spec aren't demoted.
  - The response type is `text/markdown; charset=utf-8`, with `X-Content-Type-Options: nosniff` as on the diff route.
- Q6: §3.6 says `--feedback` "has my summary and inline comments" but doesn't say which. Default:
  - Feedback is my latest CHANGES_REQUESTED decision (actor `me`, highest id).
  - The view is the common blocks, then `## Feedback on round <n>` with that decision's body, then `## Comments` with my comments only (inline and conversation, by id) on that decision's round. The `## Comments` block appears only when there are any.
  - Reviewer verdicts and comments aren't included: the builder can run `fctl show <id> --round <n>`.
  - No such decision → 404 `#<id> has no feedback`.
- Q7: §6.2 shows `?round=1 | ?feedback=1` as alternatives. Default: `feedback` is a boolean query parameter. Sending both `round` and a true `feedback` → 422 `give round or feedback, not both`.
- Q8: §7.2 gives output only for `fctl round`. Default:
  - `show` writes the body unchanged.
  - `spec` prints `Spec saved on #<id>`.
  - `stage` prints `#<id>: <status> · <stage>` from the PATCH reply.
  - `verdict` prints `Round <round> of #<id>: <reviewer>=<verdict> (<complete>)`, matching 005's `Round <n> of #<id>:`.
  - `comment` prints `Comment #<comment id> on #<id> <path>:<line>`.
  - `decide` prints `Decision #<decision id> on #<id>: <decision>`.
  - `round` prints `round <n>: security=… ux=… ui=… code=… (<k>/4)` for the last item of `rounds`, where `k` counts the non-`pending` verdicts.
- Q9: docs give no argument rules. Default:
  - Every `<id>` is an int.
  - `stage` takes one of the 7 stages, `verdict` takes security / ux / ui / code and then PASS / CHANGES, and `decide` takes APPROVE / ESCALATE, each case-sensitive, through argparse `choices`.
  - `show` has `--round N` (an int) and `--feedback` as a mutually exclusive group.
  - Any violation is an argparse usage error (exit 2) before any request.
  - Stdin is read with 005's `stdin_text()` (a terminal gives `""`) and sent unchanged.
  - `fctl spec` with a blank spec exits 1 with `fctl: spec is empty; pass it on stdin` and sends nothing, so a hand-typed `fctl spec 12` can't wipe the spec.
- Q10: docs don't say what `fctl round` prints before round 1. Default: exit 1 with `fctl: #<id> has no rounds`, the same text as the 404s.
- Q11: §7.2's `fctl comment <id> --path P --line L` has no way to name the reviewer, yet the API needs `author`, and defaulting it to `me` would slip agent comments into my `--feedback`. Default: a required positional `<reviewer>` after the id, mirroring `fctl verdict <id> <reviewer>`: `fctl comment <id> <reviewer> --path P --line L`. Its choices are security / ux / ui / code. The CLI can't post as `me`, since those comments come from the UI (008). The CLI always sends `"round":"latest"` and `"side":"new"`. 011 writes the templates with this form.
