# Round 1
## Changes
- src/claude_factories/app.py: `project_page` now builds the board. It calls `list_tasks(project_id)` and then reads `position` per task in a second query, after `list_tasks`, so every listed task has a position (Q13; the API shape is unchanged). It groups tasks into the four `COLUMNS` and passes `factory_state(path, default_branch)` to the template. I removed 002's "stub" ponytail comment and added the Q7 ponytail about each poll rendering the whole page. New `POST /projects/{id}/tasks` (`add_task_form`): it reads `title` and `description_md` with `form_field()`, calls `create_task(project_id, TaskBody(...))` for validation, the position, and the event (422, 404), and returns `hx_redirect(f"/projects/{id}")`. The middleware gives the 403.
- src/claude_factories/templates/project.html:
  - Header: the `<h1>` is unchanged. A `.toolbar` row next to it holds the Code link, `Factory: <state>` (with ` ✓` for ready), the `<details>` + New task form, and the disabled `Run next ▶` (Q4–Q6, Q10, Q14).
  - Below the header and outside `#board`: the path, the move form, and `<p id="board-error" role="alert">`.
  - `#board`: polls with `hx-trigger="every 3s [!document.querySelector('.dragging')], refresh"`, `hx-select="#board"`, and `hx-swap="outerHTML"`. It holds four `<section class="column" data-status>` columns, each with an `<h2>` label and count, an `<ol>` of cards, and the Q11 empty text.
  - Cards: each is a `<li class="card[ escalated]" draggable="true" data-id data-position>` with an `<a draggable="false">` link. Under the link come the stage text (Q2), then either the chips row and `+A −D` (non-done) or `N round(s)` (done) (Q1).
  - One inline script (Q8, Q9) with listeners delegated from `document`. It computes the gap from card midpoints, skips a drop into the same gap, and sends `PATCH /api/tasks/<id>` with `{status, position}` and `X-Requested-By: fctl`. It shows a string `detail` or `Move failed (<code>)` in `#board-error` via `textContent` and clears it on success. In every case it then fires the `refresh` trigger on `#board`.
  - An `htmx:beforeSwap` guard drops a poll response that lands while a drag is in progress. The trigger filter only stops new polls from starting, not one already in flight.
- src/claude_factories/templates/base.html: board CSS rules: toolbar, the four-column grid, columns, cards, `.dragging`, and the `.escalated` red left bar and badge using `light-dark(#cf222e, #f85149)` (Q3). No other hard-coded colors.
- tests/test_board.py: new, with one test per criterion. Its helpers (`add_task`, `add_round`) are local, so tests/conftest.py and 002's and 003's test files are unchanged.

## Criteria → tests
- AC1 → tests/test_board.py::test_page_renders. 002's AC26–AC29 are unchanged and still pass: tests/test_projects.py::test_project_page, ::test_project_page_unknown, ::test_move_project, ::test_move_project_invalid.
- AC2 → tests/test_board.py::test_code_link
- AC3 → tests/test_board.py::test_factory_state (parametrized none / uncommitted / ready, real temp repo)
- AC4 → tests/test_board.py::test_run_next_disabled
- AC5 → tests/test_board.py::test_four_columns_in_order
- AC6 → tests/test_board.py::test_column_counts
- AC7 → tests/test_board.py::test_backlog_order
- AC8 → tests/test_board.py::test_card_drag_attributes
- AC9 → tests/test_board.py::test_card_id_title_link
- AC10 → tests/test_board.py::test_title_escaped
- AC11 → tests/test_board.py::test_stage_text
- AC12 → tests/test_board.py::test_human_review_card
- AC13 → tests/test_board.py::test_escalated_card
- AC14 → tests/test_board.py::test_chips_latest_round
- AC15 → tests/test_board.py::test_additions_deletions
- AC16 → tests/test_board.py::test_no_rounds_no_chips
- AC17 → tests/test_board.py::test_done_round_count
- AC18 → tests/test_board.py::test_empty_board
- AC19 → tests/test_board.py::test_only_done_tasks
- AC20 → tests/test_board.py::test_board_polls
- AC21 → tests/test_board.py::test_board_holds_no_forms
- AC22 → tests/test_board.py::test_board_error_element
- AC23 → tests/test_board.py::test_drag_script (also asserts no `GET`/`POST`/`PUT`/`DELETE`/`XMLHttpRequest`/`htmx.ajax`/`stage` and exactly one `fetch(`)
- AC24 → tests/test_board.py::test_new_task_form
- AC25 → tests/test_board.py::test_new_task_post
- AC26 → tests/test_board.py::test_new_task_no_description
- AC27 → tests/test_board.py::test_new_task_blank_title (parametrized: empty, whitespace, field missing)
- AC28 → tests/test_board.py::test_new_task_unknown_project
- AC29 → tests/test_board.py::test_new_task_needs_header
- AC30 → tests/test_board.py::test_new_task_lands_last

### Q9 browser check
The Claude-in-Chrome tools weren't available in this session. Instead I drove headless Chrome 155 over CDP with `Input.setInterceptDrags` and `Input.dispatchDragEvent`, the same path as Puppeteer's `dragAndDrop`. The mouse press and moves start a native drag, and the drop goes to screen coordinates. It ran against `fctl serve --port 4599` with a scratch `FCTL_HOME`. All checks behaved as specified:
1. Drag between columns: I grabbed #1 by its title link (`draggable="false"`) and dropped it at the bottom of Review. The drag data was `text/plain=1`, so the card was dragged, not the URL. Then `PATCH /api/tasks/1` → 200, and the card moved to Review at position 3.0 (last + 1).
2. Backlog reorder: I dropped #5 (4.0) into the gap above #3, between #2 (2.0) and #3 (3.0). `PATCH` → 200, position 2.5, and the Backlog order became #2, #5, #3.
3. Same gap: I dropped #2 onto its own lower half. No PATCH appears in the server log.
4. 409: #4 had a `running` run, and I dragged it to Done. `PATCH` → 409, `#board-error` read `run #1 active`, and the card stayed in In progress.
5. Next successful move (#2 → Done) → 200, and `#board-error` was cleared.
6. Polling: I moved #3 to in_progress through the API, outside the page. Within 3.5 s the board showed it without a reload.
7. + New task: I opened the `<details>`, filled in the title `Typed <i>in</i> browser` and the description `**Bold** text`, and clicked Add task. `POST /projects/1/tasks` → 204 with HX-Redirect. The row was backlog at position 3.5 (max + 1), and the card rendered last in Backlog with its title escaped.

Screenshots in light and dark showed the escalated red bar and badge, `waiting on you` in bold, the chips, `+126 −9`, and `3 rounds`/`1 round`. A drop into an empty column (position 1.0) wasn't exercised in the browser, only by code reading.

## Open questions
- None new. I used the spec's defaults Q1–Q14 as written.
- Q7 detail: the after-drop refresh is a `refresh` event on `#board` (`htmx.trigger`), not `htmx.ajax`, so the script makes no request other than the PATCH (AC23). htmx's default `hx-sync` drops the refresh if a poll is already in flight. The next poll, 3 s later, catches up.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
178 passed, 1 warning in 13.05s
```
