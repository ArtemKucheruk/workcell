# 007-review-conversation: Review page (header, Conversation tab, timeline)

## Goal
Add the review page `/tasks/{id}/review` with its Conversation tab from docs/ui.md §8.2. The header shows the task, status · stage, branch, a round selector (default latest), and the selected round's file count and +/−. Below it: the description, the spec in a collapsed block, every round with its verdict chips and expandable verdict bodies, the approver's latest decision, a timeline built from events, rounds, verdicts, decisions, and comments, and a box for posting a conversation comment. Standalone `/factory-submit` tasks say "no agent review" instead of chips. This is the first job that renders markdown, so it adds markdown-it-py with raw HTML off.

## Implements
- `docs/ui.md §8 item 5`: `/tasks/{id}/review`, GitHub-style, with a round selector that defaults to latest. Not the diff table, the inline comment form, or Approve / Request changes (008, 009).
- `docs/ui.md §8.2`: the Conversation wireframe. `#<id> <title>`, the status · stage line with branch, `round [N ▾]`, and the file count with +/−. Then Description with `(spec ▸)`, one row per round (`Round 1  initial  sec ✗ ux ✓ ui ✓ code ✓  +118 −9`) with expandable verdict bodies, `Approver · APPROVE <body>`, Timeline, and `Leave a comment…`.
- `docs/MVP.md §3.5`: Conversation shows the description, the spec summary, each round's verdicts, and the timeline.
- `docs/data-model-and-api.md §5.1`: the timeline is the union of `events`, `rounds`, `verdicts`, `decisions`, and `comments`, ordered by `created_at`. A conversation comment is a `comments` row with `path`, `line`, and `side` all NULL.
- `docs/data-model-and-api.md §6.3, §6.4`: the comment box posts through 006's `post_comment()` as `author: "me"` on the latest round. The route is `/tasks/{id}/review?round=`.
- `docs/claude-code.md §7.4`: a standalone task's review header reads `3 files changed +38 −2`, and its agent chips say `no agent review`.
- `docs/MVP.md §4.2, §4.5`, FACTORY.md stack: markdown-it-py renders markdown with raw HTML off. Every mutating form carries `X-Requested-By: fctl` (base.html's `hx-headers`).

## Acceptance criteria

Page (`GET /tasks/{id}/review`)
- [ ] AC1: an existing task → 200 from `review.html`, with `<h1>` text `#<id> <title>`.
- [ ] AC2: a task titled `<script>alert(1)</script>` → the page contains `&lt;script&gt;alert(1)&lt;/script&gt;` and not the raw tag.
- [ ] AC3: an unknown task id → 404.
- [ ] AC4: the page links to its project board: `<a href="/projects/<project_id>">` with the project name as its text (Q12).

Header
- [ ] AC5: the status · stage text (tags stripped) is `In progress · build` for in_progress/build, `Review · waiting on you` for review/human_review, `Review · ⚠ NEEDS YOU — escalated` for review/escalated, `Backlog` for backlog with no stage, and `Done` for done. Only the escalated case has an element with class `escalated` (Q2).
- [ ] AC6: a task with `branch = 'factory/12-x'` → the header contains `<code>factory/12-x</code>`. A task with a NULL branch has no branch `<code>` in the header (Q2).
- [ ] AC7: a task with rounds 1, 2, and 3 → the header has one `<form method="get" action="/tasks/<id>/review">` holding a `<select name="round">` with options `1`, `2`, `3` in that order. Only option `3` is `selected` (Q4).
- [ ] AC8: `?round=2` → only option `2` is `selected`. `?round=latest` renders the same as no parameter.
- [ ] AC9: the latest round has files +100/−5 and +26/−4, and round 1 has one file +7/−7 → the header reads `2 files changed +126 −9` with no parameter and `1 file changed +7 −7` with `?round=1`. The minus is U+2212 (Q3).
- [ ] AC10: `?round=99` and `?round=abc` → 404.
- [ ] AC11: a task with no rounds → 200, with no `<select name="round">` and no `files changed` text. `?round=1` on it → 404.

Conversation: description and spec
- [ ] AC12: `description_md = "**Max 5** failed logins"` → the description section contains `<strong>Max 5</strong>`.
- [ ] AC13: an empty description → the description section reads `No description.` (Q14).
- [ ] AC14: a task with `spec_md = "## Criteria\n- 429"` → a `<details>` without `open`, whose `<summary>` is `Spec`, holding `<h2>Criteria</h2>` and `<li>429</li>`. A task whose spec_md is NULL or whitespace has no Spec `<details>` (Q1).
- [ ] AC15: raw HTML stays off. A description of `<script>alert(1)</script>` → `&lt;script&gt;` and no `<script>alert`. A description of `[x](javascript:alert(1))` → no `href="javascript:`. A verdict body whose first line is `<img src=x onerror=alert(1)>` → `&lt;img` in both its summary and its body, and no `<img` anywhere on the page (Q13).

Conversation: rounds
- [ ] AC16: a factory task (worktree_path set) with round 1 (`initial`, security CHANGES, ux/ui/code PASS, +118 −9) and round 2 (`agent`, all PASS, +126 −9) → one block per round, `id="round-1"` then `id="round-2"`. Their row text reads `Round 1 initial sec ✗ ux ✓ ui ✓ code ✓ +118 −9` and `Round 2 agent sec ✓ ux ✓ ui ✓ code ✓ +126 −9`.
- [ ] AC17: each chip carries `title="<reviewer>: <PASS|CHANGES|pending>"`. A round with no ui verdict shows `ui ·` with `title="ui: pending"`.
- [ ] AC18: each posted verdict with a non-blank body → one `<details>` without `open` inside its round's block, in the order security, ux, ui, code. Its `<summary>` text is `<reviewer> · <VERDICT>` followed by the body's first non-blank line as plain text, and its content is the body rendered as markdown. Pending reviewers and blank-body verdicts get no `<details>` (Q5).
- [ ] AC19: a standalone task (worktree_path NULL) whose round has no verdicts → that round's row shows `no agent review` and no chips. A factory task's round with no verdicts shows four pending chips. A standalone round that does have verdicts shows its chips (Q6).
- [ ] AC20: a task with no rounds → the rounds section reads `No rounds yet.`

Conversation: approver decision
- [ ] AC21: approver ESCALATE on round 1, then approver APPROVE on round 2 with body `All **4** PASS`, then my CHANGES_REQUESTED → one approver block whose text starts with `Approver · APPROVE`. It holds `<strong>4</strong>` and contains neither `ESCALATE` nor `CHANGES_REQUESTED` (Q7).
- [ ] AC22: a task with no approver decision → no approver block.

Timeline
- [ ] AC23: rows seeded with increasing `created_at`: the create event (to backlog), an event to in_progress · spec, round 1, a security CHANGES verdict, an inline security comment on `app/limits.py:31`, an approver ESCALATE decision, and my conversation comment. The timeline `<ol>`'s items read, in order: `created · backlog`, `in_progress · spec`, `round 1`, `security CHANGES · round 1`, `security on app/limits.py:31 · round 1`, `approver ESCALATE · round 1`, `me · round 1`. Each item has a `<time datetime="<created_at>">` (Q8).
- [ ] AC24: a standalone task's create event (to review · human_review) reads `created · review · human_review`. A manual move to done reads `done` (Q8).
- [ ] AC25: two rows with the same `created_at` → events before rounds before verdicts before decisions before comments, and within one kind by id (Q8).
- [ ] AC26: comment and decision items include their body rendered as markdown (`**ok**` → `<strong>ok</strong>`). Event, round, and verdict items have no body (Q8).

Comment box (Q9)
- [ ] AC27: a task with rounds → after the timeline, a form with `hx-post="/tasks/<id>/comments"`, a `<textarea name="body_md">` with `required` and the placeholder `Leave a comment…`, and a button labeled `Comment`. A task with no rounds has no such form and shows `Comments open once a round is submitted.`
- [ ] AC28: `POST /tasks/<id>/comments` with the form field `body_md=Looks good` and `X-Requested-By: fctl` → 204 with `HX-Redirect: /tasks/<id>/review`. One `comments` row is written: author `me`, the latest round's `round_id`, `path`/`line`/`side` NULL, body `Looks good`. No `events` row is written, and the task row is unchanged.
- [ ] AC29: `body_md` empty, whitespace-only, or missing → 422, and no row is written.
- [ ] AC30: without `X-Requested-By` → 403. An unknown task → 404. A task with no rounds → 404. No row is written in any of these cases.
- [ ] AC31: after AC28, the review page's timeline ends with `me · round <latest>` and `Looks good`.

## Files
- `pyproject.toml`, `uv.lock`: add `markdown-it-py` with `uv add markdown-it-py`. It is one of FACTORY.md's four fixed runtime dependencies, and this is the first job that renders markdown.
- `src/claude_factories/app.py`:
  - A `markdown` Jinja filter on `templates.env.filters` (Q13).
  - `GET /tasks/{task_id}/review` (`round` query, aliased like `task_context`). It reuses `one_or_404`, `round_or_404`, `round_summaries`, and `query`.
  - `POST /tasks/{task_id}/comments`, a form route that reads `body_md` with `form_field()`, calls `post_comment(task_id, CommentBody(author="me", body_md=…))`, and returns `hx_redirect()`.
- `src/claude_factories/templates/review.html`: new. It extends base.html. Sections carry ids for tests: `description`, `rounds` (with `round-<n>` blocks), `approver`, and `timeline`.
- `src/claude_factories/templates/base.html`: review rules in the existing `<style>`: chips row, one-line ellipsis verdict summaries, and the timeline list. Reuse the existing `light-dark(#cf222e, #f85149)` red for escalated, with no new hard-coded colors.
- `tests/test_review.py`: new, with all criteria above. Seed rows with SQL like `tests/test_agent_api.py`.

No schema change, no new static files, and no change to any `/api` response shape.

## Out of scope
- The Files changed tab and `?tab=files`: file tree, diff table with `path:side:line` anchors, highlight.js, inline comment form, and inline comments shown in place (008).
- Approve and Request changes buttons, my APPROVE / CHANGES_REQUESTED routes, the summary box, and the commit commands (009).
- The task page `/tasks/{id}` with build notes and status history (010). Build notes don't appear on the review page.
- Run status, run log, the takeover command, and the `Claude: Pro ✓` header (013/014).
- Changing the board card for standalone tasks (Q6).
- Polling or SSE on this page (Q10). Also out: replies, threads, resolving, and editing or deleting comments (Later), interdiff and split view (Later), and a link from the board card to Review.

## Open questions
- Q1: docs say "spec summary" and the wireframe shows `(spec ▸)`, but nothing defines a summary. Default: the full `spec_md`, rendered, inside a collapsed `<details><summary>Spec</summary>` placed after the description. It is omitted when spec_md is NULL or blank, as it is for standalone tasks. Nothing is summarized or truncated.
- Q2: the wireframe shows `● Review · waiting on you` but gives no other wordings, and doesn't say what a standalone task shows for branch. Default: the status label (`Backlog`, `In progress`, `Review`, `Done`, same as the board's column names), then ` · ` and the stage text when there is a stage. The stage text uses 004's Q2 words: `waiting on you` for human_review, `⚠ NEEDS YOU — escalated` in the red `.escalated` style for escalated, and the raw stage name otherwise. No `●`. The branch is shown in `<code>` when `tasks.branch` is set and omitted when it is NULL.
- Q3: the §8.2 wireframe says `4 files  +126 −9`, while §7.4 says the header reads `3 files changed +38 −2`. Default: §7.4's `N files changed +A −D`, with `1 file changed` in the singular. Counts come from the selected round's `round_summaries` entry, which is the whole change against the base (§2).
- Q4: docs don't say how the selector navigates or what it changes on Conversation. Default: a GET form to `/tasks/{id}/review` with `<label>round <select name="round" onchange="this.form.submit()">`, ascending options, and a `<noscript><button>Show</button></noscript>`. It changes only the header's files and +/−, and later 008's diff. Conversation always lists every round. An unknown or non-numeric `round` is a 404 through `round_or_404`. Any `tab` parameter is ignored until 008.
- Q5: the wireframe shows one collapsed CHANGES body (`security · CHANGES  app/limits.py:31 trusts X-Forwarded-For …  (expand)`) and none for an all-PASS round. It doesn't say whether PASS bodies expand. Default: every posted verdict with a non-blank body gets a collapsed `<details>`, PASS included, so no reviewer text is hidden. The summary is `<reviewer> · <VERDICT>` and the first non-blank line as escaped plain text, cut to one line with CSS ellipsis. The content is the rendered body. A blank body gets no `<details>`, since the chip already says it all.
- Q6: §7.4 says "no agent review" but not what counts as standalone, and 004 left the board card to this job. Default: a round shows `no agent review` instead of chips when its task's `worktree_path` is NULL (005's test for standalone) and the round has no verdicts. Verdicts posted by hand on a standalone task still show. The board card is unchanged, since the request names only the review page. Say so if the card should switch too.
- Q7: 006 appends a decision on every post, and §2 says Review shows "the approver's decision, and mine". Default: the approver block shows only the latest `actor = 'approver'` decision by id, as `Approver · <DECISION>` with its round and the rendered body. Every decision, mine included, also appears in the timeline. My decisions get their own display with 009's buttons.
- Q8: §5.1 says "union … ordered by created_at" but gives no labels, and `created_at` has one-second resolution. Default: one `<li>` per row, `<time datetime="<created_at>">` using the existing `local_time` filter, then a label:
  - event: `created · ` when `from_status` is NULL, then `to_status`, then ` · <stage>` when a stage is set.
  - round: `round N`.
  - verdict: `<reviewer> <VERDICT> · round N`.
  - decision: `<actor> <DECISION> · round N`.
  - comment: `<author>`, then ` on <path>:<line>` for an inline comment, then ` · round N`.
  Decisions and comments add their rendered body. Ties sort by kind (events, rounds, verdicts, decisions, comments), then by id. A re-posted verdict shows once, at its latest `created_at` (006 Q2). Actors on events and the events `note` column aren't shown.
- Q9: htmx posts urlencoded, and docs give no HTML route for comments. Default: follow 004 Q10 with a form route `POST /tasks/{id}/comments`. A conversation comment always attaches to the latest round, whatever the selector shows, matching the API's `"round": "latest"` default. That way 009's feedback picks up comments on the round it requests changes on. The textarea is `required`. A whitespace-only body gets the server's 422 with no inline message, the same as 004's new-task form. The redirect goes to `/tasks/{id}/review`, which shows the latest round. A task with no rounds has no box, because `comments.round_id` is NOT NULL.
- Q10: §8 says "live parts poll every 3 s", and §4.1 lists only the board, task, and run-log fragments. Default: no polling on the review page. A reload shows new verdicts. Add a poll if verdicts should fill in live here too.
- Q11: the wireframe has a `Conversation | Files changed 4` tab bar and `[Request changes] [Approve]`. Default: render the Conversation heading only. 008 adds the Files changed tab, and 009 adds the buttons. Neither is shown disabled, so there is no dead control.
- Q12: §8.2 shows no way back to the board. Default: a top line `<a href="/projects/<project_id>">` with the project name, in the place of the board's `Claude Factories` link.
- Q13: docs say "raw HTML off" but don't name a preset. Default: one module-level `MarkdownIt("js-default", {"html": False})`, which turns on tables and strikethrough without linkify, so no extra package is needed. It is exposed as a `markdown` filter that returns `Markup(md.render(text or ""))`. markdown-it's own link validation drops `javascript:`, `vbscript:`, `file:`, and non-image `data:` URLs. Never mark agent text safe any other way.
- Q14: docs don't word the empty states. Default: `No description.`, `No rounds yet.`, and `Comments open once a round is submitted.`, all as muted text. An empty timeline can't happen, because every task has its create event.
