# 010-task-detail: Task page (spec, rounds, verdicts, history)

## Goal
Add the task page `/tasks/{id}` from docs/ui.md §8 item 4, without run controls. Board cards already link to it, and today that link 404s. The page shows a header (title, status · stage, branch, a link to Review), the task's description and rendered spec, and every round. Each round has collapsible build notes, 4 reviewer chips that open their verdict, and +/−. Below the rounds come the approver's latest decision and the status history from `events`. The page polls every 3 s like the board.

## Implements
- `docs/ui.md §8 item 4`: the header's title, status · stage, and branch. The spec as rendered markdown. Rounds with build notes (collapsible), 4 chips that open the verdict, and +/−. The approver's decision. Status history (`events`). A link to Review. Not Run / Stop / Retry, run status, the run log tail, or the takeover command (014).
- `docs/ui.md §8 item 3`: clicking a board card opens the task detail. The card's `<a href="/tasks/{id}">` already exists (004).
- `docs/ui.md §8` intro, `docs/MVP.md §4.1`: live parts poll every 3 s, and the task fragment is one of them. Light and dark follow the system.
- `docs/data-model-and-api.md §5.1`: `rounds.build_md`, `verdicts`, the `decisions` row with `actor = 'approver'`, and `events` (`from_status`, `to_status`, `stage`, `created_at`) as the history.
- `docs/data-model-and-api.md §6.4`: the HTML route `/tasks/{id}`.
- `docs/claude-code.md §7.4`: a standalone task's chips say "no agent review".
- `docs/MVP.md §4.5`: all agent and user markdown is rendered with raw HTML off, through the existing `markdown` filter.

## Acceptance criteria

Page (`GET /tasks/{id}`)
- [ ] AC1: an existing task → 200 from `task.html`, with `<h1>` text `#<id> <title>`.
- [ ] AC2: an unknown task id → 404, and the HTML error page reads `Task #<id> not found`.
- [ ] AC3: the page links to its board: `<a href="/projects/<project_id>">` with the project name as its text (Q9).
- [ ] AC4: every task's header has `<a href="/tasks/<id>/review">Review</a>`, including a task with no rounds (Q9).

Header
- [ ] AC5: the status · stage text (tags stripped) is `In progress · build` for in_progress/build, `Review · waiting on you` for review/human_review, `Review · ⚠ NEEDS YOU — escalated` for review/escalated, `Backlog` for backlog with no stage, and `Done` for done. Only the escalated case has an element with class `escalated` (Q9).
- [ ] AC6: `branch = 'factory/12-x'` → the header contains `<code>factory/12-x</code>`. A NULL branch → no branch `<code>` in the header.

Description and spec
- [ ] AC7: `description_md = "**Max 5** failed logins"` → `<section id="description">` contains `<strong>Max 5</strong>`. An empty description → it reads `No description.` (Q5, Q11).
- [ ] AC8: `spec_md = "## Criteria\n- 429"` → `<section id="spec">` contains `<h2>Criteria</h2>` and `<li>429</li>`, not inside a `<details>` (Q6).
- [ ] AC9: `spec_md` NULL or whitespace-only → the spec section reads `No spec yet.` (Q6, Q11).

Rounds
- [ ] AC10: a factory task (worktree_path set) with round 1 (`initial`, security CHANGES, ux/ui/code PASS, files +100/−5 and +18/−4) and round 2 (`agent`, all PASS, +126 −9) → inside `<section id="rounds">`, a block `id="round-1"` and then `id="round-2"`. Their row text reads `Round 1 initial sec ✗ ux ✓ ui ✓ code ✓ +118 −9` and `Round 2 agent sec ✓ ux ✓ ui ✓ code ✓ +126 −9`. The minus is U+2212 (Q3).
- [ ] AC11: a posted verdict with a non-blank body, e.g. round 1 security CHANGES with body `Trusts **X-Forwarded-For**` → its chip is a `<button type="button" popovertarget="verdict-1-security" title="security: CHANGES">`. Round 1's block holds one `<div popover id="verdict-1-security">` whose text starts with `security · CHANGES` and which contains `<strong>X-Forwarded-For</strong>` (Q1).
- [ ] AC12: a pending reviewer → a chip `ui ·` with `title="ui: pending"`, and no `popovertarget` and no `popover` element for it. A posted verdict with a blank body gets the same plain chip with its `title`, also with no popover (Q1).
- [ ] AC13: a standalone task (worktree_path NULL) whose round has no verdicts → that round's row shows `no agent review`, with no chips and no popovers. A factory task's round with no verdicts shows four pending chips (Q2).
- [ ] AC14: `build_md = "Token **bucket**"` → the round's block holds one `<details>` without `open`, whose `<summary>` is `Build notes`, containing `<strong>bucket</strong>` (Q4).
- [ ] AC15: `build_md` NULL or whitespace-only → the round's block reads `No build notes.` and holds no `<details>` (Q4, Q11).
- [ ] AC16: a task with no rounds → the rounds section reads `No rounds yet.` (Q11).

Approver decision
- [ ] AC17: approver ESCALATE on round 1, then approver APPROVE on round 2 with body `All **4** PASS`, then my CHANGES_REQUESTED → one `<section id="approver">`. Its text starts with `Approver · APPROVE` and contains `round 2`. It holds `<strong>4</strong>` and contains neither `ESCALATE` nor `CHANGES_REQUESTED` (Q7).
- [ ] AC18: a task with no approver decision → no `<section id="approver">`.

Status history
- [ ] AC19: events seeded with increasing `created_at`: create (NULL → backlog), backlog → in_progress (no stage), in_progress → in_progress · spec, in_progress → review · human_review, and review → done (no stage). The `<ol>` in `<section id="history">` then has items reading, in order, `created · backlog`, `in_progress`, `in_progress · spec`, `review · human_review`, and `done`. Each item has a `<time datetime="<created_at>">` (Q8).
- [ ] AC20: a task with 2 events, plus a round, a verdict, a decision, and a comment → the history has exactly 2 items (Q8).
- [ ] AC21: two events with the same `created_at` → listed by id (Q8).

Safety and polling
- [ ] AC22: raw HTML stays off on this page. Each of these renders escaped (`&lt;script&gt;` / `&lt;img`), and the page contains no `<script>alert` and no `<img`: a title, a spec, a build note, a verdict body, and an approver body of `<script>alert(1)</script>` or `<img src=x onerror=alert(1)>`.
- [ ] AC23: the header and every section sit inside one `<div id="live">` with `hx-get="/tasks/<id>"`, `hx-select="#live"`, and `hx-swap="outerHTML"`. Its `hx-trigger` starts with `every 3s` and has a filter naming `details[open]` and `:popover-open` (Q10).
- [ ] AC24: `tests/test_review.py` passes unmodified after review_page's queries move into the shared helpers (Files).

## Files
- `src/claude_factories/app.py`:
  - `GET /tasks/{task_id}` (`task_page`). Its 404 detail is `Task #<id> not found`, like `review_page`.
  - Move `review_page`'s two inline queries into two helpers that both pages call: verdict rows by round n (`posted`) and the approver's latest decision. Review's output stays the same.
  - Build notes come from one `SELECT n, build_md FROM rounds WHERE task_id = ?`. `round_summaries` and the `/api/tasks/{id}` response stay as they are.
  - History is `query(TIMELINE, …)` filtered to the event rows (`kind = 0`), so the labels aren't written twice.
- `src/claude_factories/templates/task.html`: new. It extends base.html and reuses review.html's `labels`, `short`, and `symbol` maps. Section ids: `description`, `spec`, `rounds` (with `round-<n>` blocks), `approver`, and `history`. Each `<div popover>` goes after the round's row, outside any `<p>`, because a `<div>` inside a `<p>` makes the parser close the `<p>` early.
- `src/claude_factories/templates/base.html`: task page rules in the existing `<style>`: chip buttons styled like the review chips, and a popover width and scroll limit. No new hard-coded colors.
- `tests/test_task_page.py`: new, covering every criterion above. Reuse test_review.py's seeding helpers (`add_task`, `add_round`, `add_verdict`, …) by importing them or moving them to `conftest.py`. Don't copy them.

No schema change, no new dependency, no new static file, and no change to any `/api` response.

## Out of scope
- Run / Stop / Retry buttons, run status, the run log tail, the takeover command, and the `Claude: Pro ✓` header (014). The run endpoints (012, 013).
- Changing anything from this page: no spec editing, comments, Approve, or Request changes. Those live on Review (007–009).
- My own decisions as their own block (Q7). The diff, the file list, and the round selector (Review's).
- A link from Review back to the task page, and any board card change.
- Restoring open `<details>` and popovers across a poll (Q10).

## Open questions
- Q1: "4 chips that open the verdict" doesn't say how a chip opens. Default: the native popover API, no JS. A chip whose verdict has a non-blank body is `<button type="button" popovertarget="verdict-<n>-<reviewer>" title="<reviewer>: <VERDICT>">`. Its `<div popover id="verdict-<n>-<reviewer>">` shows `<reviewer> · <VERDICT>` and the rendered body. Light dismiss and Esc close it. A pending chip, or one whose verdict body is blank, has nothing to open. It is a plain `<span>` with the same `title`, as on Review. A `<details>` per chip was rejected: opening one inside the chip row pushes the other chips around.
- Q2: what counts as standalone isn't defined for this page. Default: 007 Q6's rule. A round shows `no agent review` instead of chips when its task's `worktree_path` is NULL and the round has no verdicts.
- Q3: §8 item 4 gives no row layout. Default: Review's row (`Round N <trigger> sec ✓ ux ✓ ui ✓ code ✓ +A −D`), with rounds in ascending n. It uses §8.2's `code` label, not the board's `co`, and the §8.1 legend: ✓ PASS, ✗ CHANGES, · pending. There's no file count, since the request says only +/−.
- Q4: "build notes (collapsible)" gives no wording. Default: a collapsed `<details><summary>Build notes</summary>`, rendered, after the row and the popovers. A NULL or blank `build_md` shows muted `No build notes.` instead.
- Q5: §8 item 4 doesn't list the description. Without it, a backlog task, which has no spec or rounds yet, would show only its title. Default: show the rendered description in `<section id="description">` above the spec, with `No description.` when it's empty. Drop it if the page should list only §8 item 4.
- Q6: Review collapses the spec (`(spec ▸)`), while §8 item 4 says just "Spec (rendered markdown)" and marks only build notes collapsible. Default: the spec is rendered in the open. NULL or blank shows `No spec yet.`, the same words as `fctl show`.
- Q7: 006 appends a decision on every post, and §8 item 4 names only "the approver's decision". Default: 007 Q7's rule. Show only the latest `actor = 'approver'` decision by id, as `Approver · <DECISION>`, `round N`, and the rendered body. My decisions show up only as their status moves in the history (`done`, `in_progress · rework`) and on Review's timeline.
- Q8: docs give no history labels. Default: Review's timeline labels for events. `created · ` when `from_status` is NULL, then `to_status`, then ` · <stage>` when one is set. Oldest first, ties by id, each with `<time datetime>` through `local_time`. The actor and `note` aren't shown, since nothing writes `note`. Add the actor if who moved the task matters.
- Q9: the header's wording and the Review link's place aren't given. Default: 007 Q2's status · stage words (`waiting on you`, red `⚠ NEEDS YOU — escalated`, the raw stage otherwise). The branch goes in `<code>` when it's set. A top line links to the project board (007 Q12). `Review` sits on the meta line next to the branch, on every task. Review renders a page even with no rounds.
- Q10: §4.1 says the task fragment polls every 3 s, but not what's in it, and a swap closes open `<details>` and popovers. Default: wrap the whole page body in `<div id="live" hx-get="/tasks/<id>" hx-trigger="every 3s [!document.querySelector('#live details[open], #live :popover-open')]" hx-select="#live" hx-swap="outerHTML">`, like the board's whole-page poll. Polling pauses while anything is open. The cost: the page stops updating while I read open build notes or a verdict. The builder notes this ceiling in a `ponytail:` comment, with the upgrade path of reopening open elements by id on `htmx:afterSwap`.
- Q11: docs don't word the empty states. Default: muted `No description.`, `No spec yet.`, `No rounds yet.`, and `No build notes.`. A task with no approver decision has no approver section. The history is never empty, because every task gets its create event.
