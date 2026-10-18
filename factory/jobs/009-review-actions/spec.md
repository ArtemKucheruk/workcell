# 009-review-actions: Approve, Request changes, fctl approve / rework

## Goal
This job lets me finish a review. **Approve** records my APPROVE decision, moves the task to done, and shows the git commands I run myself. **Request changes** records my CHANGES_REQUESTED decision with a required summary and moves the task to in_progress · rework. Both are available as JSON endpoints, as buttons on the review page that are enabled only in `review`, and as `fctl approve` / `fctl rework`. This job never spawns a run. 013 adds the rework run for factory tasks.

## Implements
- `docs/MVP.md §3.6`: step 1 (summary plus inline comments, then Request changes or `fctl rework 12 "note"`) and the record-and-move half of step 2 (my `CHANGES_REQUESTED` decision, in_progress · rework). Spawning `/factory 12` is 013's.
- `docs/MVP.md §3.7`: Approve records my `APPROVE`, moves the task to done, and shows the commit commands. The app never runs them.
- `docs/data-model-and-api.md §5.2`: `rework` → in_progress and done are set by my actions. Every change writes an `events` row.
- `docs/data-model-and-api.md §6.3`: `POST /api/tasks/{id}/request-changes` (202, `run_id` null) and `POST /api/tasks/{id}/approve` (200, `status` + `commit_hint`).
- `docs/claude-code.md §7.2`: `fctl rework <id> "note"` and `fctl approve <id>`.
- `docs/claude-code.md §7.4` (last paragraph), `§7.5`: Request changes on a standalone task records feedback without a run. Approve gives done, and Request changes gives in_progress · rework.
- `docs/ui.md §8 item 5`, `§8.2`: `[Request changes] [Approve]` on the review page, enabled only in `review`, with a required summary box for Request changes.

## Acceptance criteria
In these criteria, a "factory task" has `branch` and `worktree_path` set, and a "standalone task" has both NULL. "Nothing written" means the `decisions` and `events` row counts and the task row (status, stage, position, done_at, updated_at) are unchanged.

Approve API
- [ ] AC1: `POST /api/tasks/{id}/approve` with `{"body_md": ""}` on a task in `review` · `human_review` with rounds 1 and 2 → `200`, and the JSON is exactly `{"status": "done", "commit_hint": …}`. The task row now has status `done`, stage NULL, `done_at` and `updated_at` set to a current `YYYY-MM-DDTHH:MM:SSZ` timestamp, and its position unchanged.
- [ ] AC2: the same call adds exactly one `decisions` row with actor `me`, decision `APPROVE`, `round_id` = round 2's id, and `body_md` as sent. A body of `{}` stores `body_md` `''`.
- [ ] AC3: the same call adds exactly one `events` row with actor `me`, from_status `review`, to_status `done`, stage NULL.
- [ ] AC4: a task in `review` · `escalated` can be approved too → `200`, status `done`.
- [ ] AC5: `commit_hint` for a factory task (project path `/code/api`, worktree `/code/api/.claude/worktrees/12-rate-limit-login`, branch `factory/12-rate-limit-login`, title `Rate-limit login endpoint`) is exactly these 4 lines joined by `\n`, with no trailing newline:
  ```
  cd /code/api/.claude/worktrees/12-rate-limit-login
  git add -A && git commit -m 'Rate-limit login endpoint'
  git push -u origin factory/12-rate-limit-login     # then open a PR, or merge locally
  cd /code/api && git worktree remove .claude/worktrees/12-rate-limit-login
  ```
- [ ] AC6: every value in `commit_hint` is shell-quoted. For a title of `it's $(touch x) "q"`, line 2 is `git add -A && git commit -m ` + `shlex.quote(title)`.
- [ ] AC7: `commit_hint` for a standalone task titled `Fix open redirect after login` is exactly `git add -A && git commit -m 'Fix open redirect after login'`.
- [ ] AC8: approving a task in `backlog`, `in_progress`, or `done` → `409` with detail `#<id> is not in review`, and nothing is written. Approving the same review task twice → the second call gets `409`, and only one APPROVE row exists.
- [ ] AC9: approving an unknown task id → `404`. A task in `review` with no rounds → `404` with detail `#<id> has no rounds`, and nothing is written.

Request changes API
- [ ] AC10: `POST /api/tasks/{id}/request-changes` with `{"body_md": "Make the limit configurable via settings."}` on a factory task in `review` · `human_review` → `202`, and the JSON is exactly `{"status": "in_progress", "stage": "rework", "run_id": null}`. The task row is now `in_progress` · `rework`, with `done_at` NULL, `updated_at` current, and position unchanged.
- [ ] AC11: the same call adds exactly one `decisions` row with actor `me`, decision `CHANGES_REQUESTED`, the latest round's id, and `body_md` as sent. It adds exactly one `events` row with actor `me`, from_status `review`, to_status `in_progress`, stage `rework`.
- [ ] AC12: the same call on a standalone task gives the same `202` body and the same task, decision, and event rows. For both kinds of task, no `runs` row is created.
- [ ] AC13: `body_md` that is missing, `""`, or `"  \n"` → `422`, with detail `body_md must not be blank` for the two strings, and nothing is written.
- [ ] AC14: request-changes on a task not in `review` → `409` `#<id> is not in review`. An unknown id → `404`. A review task with no rounds → `404` `#<id> has no rounds`. Nothing is written in any of these cases.
- [ ] AC15: request-changes on round 2, with my inline comment on round 2 posted first → `GET /api/tasks/{id}/context?feedback=1` contains `## Feedback on round 2`, then the summary, then my comment (006's context, unchanged).
- [ ] AC16: request-changes on a standalone task, then `POST /api/tasks/{id}/rounds` with a valid patch → round 3 with trigger `human`, and the task is back in `review` · `human_review` (005's logic, unchanged).
- [ ] AC17: both endpoints without `X-Requested-By: fctl` → `403`, and nothing is written.

Review page
- [ ] AC18: `GET /tasks/{id}/review` for a task in `review` with rounds, on both the Conversation and Files changed tabs: the `<header>` contains a form with `hx-post="/tasks/{id}/request-changes"`, which holds a `<textarea name="body_md" required>` and a "Request changes" button. It also contains a form with `hx-post="/tasks/{id}/approve"` and an "Approve" button. Neither button is `disabled`.
- [ ] AC19: for a task in `backlog`, `in_progress`, or `done`, and for a task in `review` with no rounds, both buttons render with the `disabled` attribute.
- [ ] AC20: form `POST /tasks/{id}/approve` (with the header and an empty urlencoded body) → `204` with `HX-Redirect: /tasks/{id}/review`, and the task is `done`.
- [ ] AC21: form `POST /tasks/{id}/request-changes` with `body_md=Make+it+configurable` → `204` with `HX-Redirect: /tasks/{id}/review`, and the decision is stored with body `Make it configurable`. With `body_md=` or whitespace only → `422` `body_md must not be blank`, and nothing is written.
- [ ] AC22: the review page of a `done` task contains `<section id="commit">` showing that task's `commit_hint` in a `<pre>`, HTML-escaped (a title containing `<b>` shows as `&lt;b&gt;`). The section is absent for every status other than `done`.
- [ ] AC23: after request-changes, the Conversation timeline shows `me CHANGES_REQUESTED · round 2` with the summary and `in_progress · rework`. After approve, it shows `me APPROVE · round 2` and `done` (007's TIMELINE, unchanged).

CLI
- [ ] AC24: `fctl approve 12` → exactly one request, `POST /api/tasks/12/approve` with `{"body_md": ""}`. With the reply `{"status": "done", "commit_hint": "<hint>"}`, stdout is `#12: done\n<hint>\n` and the exit code is 0.
- [ ] AC25: `fctl rework 12 "Make the limit configurable"` → exactly one request, `POST /api/tasks/12/request-changes` with `{"body_md": "Make the limit configurable"}`. With the reply `{"status": "in_progress", "stage": "rework", "run_id": null}`, stdout is `#12: in_progress · rework\n`.
- [ ] AC26: `fctl rework 12` without a note → argparse usage error (exit 2), and no request is sent. When the server answers `409 {"detail": "#12 is not in review"}`, `fctl approve 12` prints `fctl: 409 #12 is not in review` to stderr and exits 1.

## Files
- `src/claude_factories/app.py`: the body models, a `commit_hint(task)` helper, the two `/api/tasks/{id}/…` routes sharing one transaction helper (`BEGIN IMMEDIATE`, then the status check, `round_or_404`-style latest round, decision, task update, and event), the two htmx form routes `POST /tasks/{id}/approve` and `/request-changes` (`form_field`, then `hx_redirect`), and `review_page` passing the commit hint for a done task.
- `src/claude_factories/templates/review.html`: the two action forms in the header (each with a `.form-error`, which the page's existing error script fills) and `section#commit`.
- `src/claude_factories/templates/base.html`: only if the action forms need a few lines of CSS.
- `src/claude_factories/cli.py`: the `approve` and `rework` subcommands. Update the stale `DECISIONS` comment that says "come in 009".
- `tests/test_review_actions.py` (new): AC1–AC23.
- `tests/test_cli.py`: AC24–AC26, appended with the existing `server` fixture.

No new dependencies. `shlex` is stdlib and already imported in app.py.

## Out of scope
- Spawning `/factory <id>` on Request changes for factory tasks, a non-null `run_id`, and refusing Request changes while a run is active. All of that comes with the spawn in 013.
- Run / Stop / Retry buttons, the run log, and the takeover command (014). The task page `/tasks/{id}` (010). `fctl run`, `fctl task add --run`, and `fctl setup` (015).
- A separate "my decision" block on the review page. The timeline already lists my decisions with their bodies (AC23).
- Running any git command, blocking Approve until the branch has a commit (MVP §10 OQ2: not blocked), and warning when the worktree changed since the last snapshot (Later).
- A summary on Approve from the UI or from `fctl approve` (§7.2 gives it no note). The API still accepts `body_md`.
- Board changes. The board already shows `rework` and done cards (004).

## Open questions
- Q1: §7.4 says Request changes on a standalone task "only records my feedback (no run)", but §6.3 gives standalone tasks the same `in_progress` · `rework` response with only `run_id` null. Default: a standalone task moves to in_progress · rework like a factory task, with `run_id` null. 005 already puts it back in review · human_review on the next `fctl submit <id>`, with trigger `human` (AC12, AC16).
- Q2: docs say the buttons are enabled only in `review` but don't say whether the API refuses other statuses. Default: both endpoints return `409` `#<id> is not in review` unless status is `review` (either stage). The check runs inside the write transaction, so a double click can't approve twice (AC8, AC14).
- Q3: `decisions.round_id` is NOT NULL, so a review task with no rounds (dragged there by hand) has nothing to attach a decision to. Default: `404` `#<id> has no rounds`, the same as 006's `POST /decision`, and both buttons are disabled on such a task (AC9, AC14, AC19).
- Q4: the `commit_hint` format. §6.3 shows one `&&`-joined line, and §3.7 shows 4 lines whose relative `git worktree remove .claude/worktrees/…` would fail after line 1's `cd`. The title would also be pasted into a shell unescaped. Default: §3.7's 4 lines joined by `\n`. Line 1 `cd`s to the absolute worktree path. Line 4 is `cd <project path> && git worktree remove <worktree path relative to the project>`. Every interpolated value goes through `shlex.quote`, so the message is single-quoted, not double-quoted as in §3.7 (AC5, AC6).
- Q5: §3.7 only covers factory tasks. A standalone task has no worktree or branch, and the app doesn't know which checkout its submit came from. Default: `git add -A && git commit -m <quoted title>` alone (AC7).
- Q6: docs say the page shows the commands after Approve but not for how long. Default: the review page shows `section#commit` for any `done` task, computed from the task row, so it survives a reload and also appears after `fctl approve` or a drag to Done. The Approve form route redirects to the review page (AC20, AC22).
- Q7: §5.2's "set by" column says "app (my Approve)", while `events.actor` allows `me`, `app`, or `orchestrator`. Default: actor `me` for both actions, as for board moves (AC3, AC11).
- Q8: docs don't say where a task lands in its new column. Default: position unchanged, as 012's Run does (AC1, AC10).
- Q9: the summary is required in the UI (§8 item 5). Default: the API enforces it too. request-changes rejects a blank or whitespace-only `body_md` with `422`. Approve's `body_md` is optional and defaults to `''` (AC2, AC13). `fctl rework` takes the note as a required positional argument.
- Q10: the review page can show an older round. Default: both decisions always attach to the task's latest round, whichever round the page shows, as 006's `POST /decision` does.
- Q11: `fctl` output isn't specified. Default: `fctl approve` prints `#<id>: done`, then the commit hint, as 006's `fctl stage` prints `#<id>: <status> · <stage>`. `fctl rework` prints `#<id>: in_progress · rework` (AC24, AC25).
- Q12: the wireframe shows only `[Request changes] [Approve]` and doesn't say where the summary box goes. Default: both forms sit in the review page `<header>` on both tabs. The Request changes form has a textarea labelled "Summary" with `required` and its button. The Approve form has only its button and sends no summary (AC18).
