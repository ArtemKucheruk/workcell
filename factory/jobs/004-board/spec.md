# 004-board: Project board (columns, cards, drag and drop, new task)

## Goal
Turn the `/projects/{id}` stub from 002 into the kanban board from docs/ui.md §8.1. There are four columns with counts. Each card shows its stage, the latest round's reviewer chips, and +/−. A human_review card reads "waiting on you", and an escalated card gets a red bar and badge. Cards move between columns, and reorder inside a column, by native HTML5 drag and drop, which calls 003's `PATCH /api/tasks/{id}`. A `+ New task` form adds a card at the bottom of Backlog. The header has the Code link, the factory state, and a disabled Run next. The board refreshes itself every 3 s.

## Implements
- `docs/ui.md §8 item 3`: the board at `/projects/{id}`. Header with **Code**, the factory state, **+ New task**, and **Run next** (disabled here). Native HTML5 drag and drop with no library. Clicking a card opens `/tasks/{id}`.
- `docs/ui.md §8.1`: the wireframe. Column names with counts, `#<id> <title>` cards, a chips row `r<n> sec✓ ux✓ ui· co✗` (✓ PASS, ✗ CHANGES, · pending), `+A −D`, "waiting on you", an escalated card with a red left bar and badge, and `N rounds` on done cards. Not the per-card `[Run]`, the `● running` / `started` lines, or `stalled · <stage> [Retry]` (014).
- `docs/ui.md §8 intro`, `docs/MVP.md §4.1`, `§10 assumption 13`: light and dark follow the system, and the board polls every 3 s through htmx.
- `docs/MVP.md §3.3`: + New task with a title and a markdown description, and the card lands at the bottom of Backlog. Backlog can be reordered by dragging.
- `docs/MVP.md §3.2 step 4`: the factory state (none / uncommitted / ready) is shown in the header, using 002's `factory_state()`.
- `docs/data-model-and-api.md §5.2, §6.2`: a board drag is `PATCH /api/tasks/{id}` with `{"status","position"}`. It clears stage, and a 409 during a run is shown to me. The new-task form reuses `create_task` (`POST /api/projects/{id}/tasks`).
- `docs/claude-code.md §7.5`: the row "Drag on board → any status, stage cleared (blocked during a run)".
- `docs/MVP.md §4.5`: the form post and the drag PATCH both carry `X-Requested-By: fctl`, and titles are HTML-escaped.

## Acceptance criteria

Header (`GET /projects/{id}`)
- [ ] AC1: → 200 from `project.html`. 002's project-page tests (AC26–AC29 in tests/test_projects.py) still pass unchanged: the `<h1>` heading, the path, and the move form.
- [ ] AC2: the header has `<a href="/projects/<id>/code">Code</a>` (Q5).
- [ ] AC3: the header shows `Factory: none` for a project with no SKILL.md, `Factory: uncommitted` when SKILL.md is only on disk, and `Factory: ready ✓` when it is committed on the default branch. Each case uses a real temp repo (Q4).
- [ ] AC4: the header has a `<button>` whose text is `Run next ▶` and which has the `disabled` attribute (Q6).

Columns
- [ ] AC5: the page has exactly four column elements, in this order, with `data-status` set to `backlog`, `in_progress`, `review`, and `done`.
- [ ] AC6: project A has 2 backlog, 1 in_progress, 0 review, and 3 done tasks, and project B has 1 backlog task → the column headings read, with tags stripped and whitespace collapsed, `Backlog 2`, `In progress 1`, `Review 0`, `Done 3`. B's task appears nowhere on A's board.
- [ ] AC7: backlog tasks at positions 2.0, 1.0, and 1.0 → their cards appear in the order (1.0, lower id), (1.0, higher id), (2.0). That is the same order as `GET /api/projects/{id}/tasks`.

Cards
- [ ] AC8: each card has `draggable="true"`, `data-id="<task id>"`, and `data-position="<tasks.position>"` (a task at 2.5 → `data-position="2.5"`), and it sits inside the column for its status (Q13).
- [ ] AC9: a card shows `#<id>` and the title, and links to `/tasks/<id>` (Q5).
- [ ] AC10: a task titled `<script>alert(1)</script>` → the page contains `&lt;script&gt;alert(1)&lt;/script&gt;` and not the raw tag.
- [ ] AC11: an in_progress task with stage `agent_review` → its card shows `agent_review`. A backlog task with no stage shows no stage text (Q2).
- [ ] AC12: a review task with stage `human_review` → its card shows `waiting on you` and has no `escalated` class (Q2, Q3).
- [ ] AC13: a review task with stage `escalated` → its card element has the class `escalated` and shows `⚠ NEEDS YOU — escalated` (Q2, Q3).
- [ ] AC14: an in_progress task with round 1 (all CHANGES) and round 2 (security PASS, ux PASS, no ui verdict, code CHANGES) → its card has exactly one chips row, whose text is `r2 sec✓ ux✓ ui· co✗`. The chips carry the titles `security: PASS`, `ux: PASS`, `ui: pending`, and `code: CHANGES`. Round 1's verdicts don't appear (Q1).
- [ ] AC15: that task's latest round has files +100/−5 and +26/−4 → the card shows `+126 −9`, where the minus is U+2212 (Q1).
- [ ] AC16: a task with no rounds → its card has no chips row and no +/− (Q1).
- [ ] AC17: a done task whose latest round is 3 → its card shows `3 rounds`, and one whose latest round is 1 → `1 round`. Neither shows a chips row or +/−. A done task with no rounds shows neither (Q1).

Empty states (Q11)
- [ ] AC18: a project with no tasks → all four columns are present with count 0. Backlog shows `No tasks. Add one with + New task, or run fctl task add "title" in the repo.` (tags stripped), and each other column shows `No tasks`.
- [ ] AC19: a project with only done tasks → Backlog shows the AC18 Backlog text, In progress and Review show `No tasks`, and Done shows no empty text.

Polling (Q7)
- [ ] AC20: the element with `id="board"` contains the four columns and has `hx-get="/projects/<id>"`, an `hx-trigger` that starts with `every 3s`, `hx-select="#board"`, and `hx-swap="outerHTML"`.
- [ ] AC21: `#board` contains no `<form` and not the `#board-error` element. The new-task form, the move form, and the error line all sit outside it.

Drag and drop (Q8, Q9)
- [ ] AC22: the page has an element `id="board-error"` with `role="alert"`, empty on load.
- [ ] AC23: the page has an inline `<script>` that contains `/api/tasks/`, `PATCH`, and `X-Requested-By`. It runs no other request type, and it never sends a `stage` key.

`+ New task` (Q10)
- [ ] AC24: the page has a `<details>` whose `<summary>` is `+ New task`. It holds a form with `hx-post="/projects/<id>/tasks"`, a text input `name="title"` with `required`, a `<textarea name="description_md">`, and a submit button labeled `Add task`.
- [ ] AC25: `POST /projects/<id>/tasks` with the form fields `title=Export CSV` and `description_md=**Bold** text` and `X-Requested-By: fctl` → 204 with `HX-Redirect: /projects/<id>`. One `tasks` row holds that title and description with status `backlog` and a position one above the project's highest backlog position. There is one `events` row, me → backlog.
- [ ] AC26: the form with no `description_md` field → 204, and the row's `description_md` is `''`.
- [ ] AC27: `title` empty or whitespace-only → 422, and no `tasks` or `events` row is written.
- [ ] AC28: an unknown project id → 404, and no row is written.
- [ ] AC29: the same post without `X-Requested-By` → 403, and no row is written.
- [ ] AC30: after AC25, `GET /projects/<id>` shows the new card last in the Backlog column.

## Files
- `src/claude_factories/app.py`: `project_page` adds the factory state, the cards (built from `list_tasks(project_id)`, plus each task's `position`), and the per-column counts. A new form route, `POST /projects/{id}/tasks`, reads fields with `form_field()`, calls `create_task()`, and returns `hx_redirect()`. Remove 002's "stub" ponytail comment.
- `src/claude_factories/templates/project.html`: the header, the `+ New task` form, `#board-error`, the `#board` columns and cards, and the inline drag script. The existing `<h1>`, path, and move form stay.
- `src/claude_factories/templates/base.html`: board rules in the existing `<style>` block: the four-column grid, the cards, and the `.escalated` red left bar (Q3).
- `tests/test_board.py`: new, with all criteria above.
- `tests/conftest.py`: only if helpers such as `add_task`, `add_round`, or `commit_skill` get shared between test files.

No schema change, no new dependencies, no new static files, and no change to any `/api` response shape.

## Out of scope
- Per-card `[Run]`, an enabled Run next, Stop and Retry, the `● running` / `started HH:MM` lines, and `stalled · <stage> [Retry]` cards (014, on top of 012/013's endpoints).
- The Create factory button, its result, and the commit hint (011). The header shows the state only.
- The `/tasks/{id}` page (010) and the `/projects/{id}/code` page (016). This job only links to them.
- The `Claude: Pro ✓` / `API key — runs disabled` header (014).
- "no agent review" for standalone tasks (§7.4). 005 creates those rounds, and 007 decides how they look. Until then a standalone card shows pending chips.
- Rendering or previewing the description markdown. The board never shows the description, and 007/010 render it.
- Editing or deleting tasks, a keyboard alternative to drag (Q12), Done-column paging, renumbering positions, SSE (Later), and a JS test runner.

## Open questions
- Q1: the request says "chips per round", but the §8.1 wireframe shows a single `r2 …` row on cards with two rounds. Default: one row for the latest round only, `r<n>` followed by `sec`, `ux`, `ui`, `co`, each with its symbol attached (`sec✓`, `ui·`, `co✗`). Each chip has `title="<reviewer>: <PASS|CHANGES|pending>"` so the symbols aren't the only cue. `+A −D` (U+2212) is the latest round's total, which is the whole change because each snapshot is the full diff against the base (§2). Cards in backlog, in_progress, and review show chips and +/− when a round exists. Done cards show `N round`/`N rounds` instead, as in the wireframe, and nothing when there are no rounds.
- Q2: the wireframe's in-progress stage text (`running · review`) mixes run state with stage. Default: an in_progress card shows the raw stage name (`spec`, `build`, `agent_review`, `approval`, `rework`), the same words `fctl stage` uses. `human_review` shows `waiting on you`. `escalated` shows `⚠ NEEDS YOU — escalated`. A null stage shows nothing. Run state is 014's.
- Q3: docs say escalated is red, and FACTORY.md says human_review should stand out. Neither fixes a color. Default: `.escalated` gets a red left border and red badge text, using `light-dark(#cf222e, #f85149)` so both schemes keep contrast. `waiting on you` is bold, with no color. The chips use symbols only. No other hard-coded colors (002 Q16).
- Q4: §8 item 3 says "factory state or Create factory" without giving the wording. Default: `Factory: none`, `Factory: uncommitted`, `Factory: ready ✓`, from `factory_state(path, default_branch)`. 011 adds the button and the commit hint.
- Q5: the Code page (016) and the task page (010) don't exist yet. Default: render both links anyway, since the request and §8 item 3 call for them. They 404 until those jobs land. Set `draggable="false"` on the card link so dragging moves the card instead of the URL.
- Q6: Run next comes in 012/014. Default: `<button disabled title="Runs aren't available yet">Run next ▶</button>` with no handler. 014 enables it.
- Q7: docs say the board polls every 3 s but give no fragment route (§6.4 lists only full pages). Default: no new route. `#board` re-fetches `/projects/{id}` with `hx-select="#board"` and `hx-swap="outerHTML"`. The trigger is `every 3s` with an htmx filter that skips the poll while a drag is in progress, so a swap can't land mid-drag. Forms and `#board-error` sit outside `#board`, so a poll never wipes half-typed text. ponytail: each poll renders the whole page, including one `git cat-file` call. Add a `/projects/{id}/board` fragment route if that ever shows up in profiling.
- Q8: docs give the PATCH body but not how the position is computed. Default: every column accepts drops, and the same rule applies everywhere. The drop point is the gap before the first card whose vertical midpoint is below the pointer. Between cards A and B, the position is `(A.position + B.position) / 2`. Before the first card it is `first − 1`, after the last card `last + 1`, and in an empty column `1.0`. A drop that leaves the card in the same column and gap sends nothing. ponytail: repeated midpoints at one spot run out of float precision after about 50 drops. Add renumbering if that ever happens.
- Q9: docs don't say how the drag talks to the API or shows a refusal. Default: one inline `<script>` with listeners delegated from `document`, so they survive the poll swap. `fetch` sends `PATCH /api/tasks/<id>` with a JSON body `{"status","position"}` and the headers `Content-Type: application/json` and `X-Requested-By: fctl`. Afterwards it refreshes `#board` immediately (for example with `htmx.ajax` and the same select and swap). On a non-2xx response, `#board-error` gets the response's `detail` when it is a string (for example `run #41 active`), else `Move failed (<status code>)`. Set it with `textContent`, never `innerHTML`. The next successful move clears it. Unit tests can't run this JS: the builder checks one drag between columns, one Backlog reorder, and the 409 message by hand in a browser, and records the result in build.md.
- Q10: docs give the form's fields but no HTML route, and htmx posts urlencoded, not JSON. Default: follow 002 Q10. Add `POST /projects/{id}/tasks` (a form route, separate from `/api/...`), parse fields with the existing `form_field()`, call `create_task(project_id, TaskBody(...))` for validation, the position, and the event, and return 204 with `HX-Redirect: /projects/{id}`. `form_field()` strips both values, which is acceptable for a description. The form is a native `<details>` disclosure, so it needs no JS. The title input has `required` and `pattern=".*\S.*"` like 002's workspace input. The description is a plain `<textarea>` with a "Markdown" label or placeholder, and there is no preview.
- Q11: docs don't word the empty states. Default: an empty Backlog says `No tasks. Add one with + New task, or run <code>fctl task add "title"</code> in the repo.` Any other empty column says `No tasks`. Both are muted text. All four columns always render, so they stay drop targets.
- Q12: native drag and drop has no keyboard path, and docs ask for nothing else. Default: none built in this job. The cards and links are focusable, and the chips have text titles. A keyboard move control (for example a status `<select>` per card) needs a decision from me.
- Q13: the board needs each task's `position` for the midpoint math, but 003's `GET /api/projects/{id}/tasks` doesn't return it (003 Q9 fixed its keys). Default: the page route reads `position` itself and leaves the API shape unchanged.
- Q14: 002's project page holds the path and the move form, and §8.1 doesn't place them. Default: keep the `<h1>` exactly as it is. Put the Code link, the factory state, `+ New task`, and Run next in the header next to it. Keep the path and the move form below the header, outside `#board`.
