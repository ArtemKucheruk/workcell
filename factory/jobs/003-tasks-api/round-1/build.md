# Round 1
## Changes
- src/claude_factories/app.py: the four task routes (`GET`/`POST /api/projects/{id}/tasks`, `GET`/`PATCH /api/tasks/{id}`). Adds `TaskBody` and `TaskPatch` (`FiniteFloat` position, `Literal` stage and status), the `STAGE_STATUS` dict, and two helpers: `round_summaries()` (per-round file count, +/− sums, and 4 verdicts with `pending`), used by both GETs, and `latest_run()`. The PATCH runs the 409 check, the update, and the `events` insert in one `BEGIN IMMEDIATE` transaction. The create does the same, so the bottom-of-Backlog position and the insert are atomic.
- src/claude_factories/app.py: a `RequestValidationError` handler. It is FastAPI's default 422 without each error's echoed `input`. Without it, the raw `{"position":NaN}` body from AC33 (and any NaN or Infinity in any field, on any route) became a 500: `json.loads` accepts NaN, but `JSONResponse` can't encode it back. The detail stays pydantic's list shape, minus `input`.
- src/claude_factories/cli.py: adds `fctl task add "title"`, which uses `main_checkout()`, a `GET /api/projects?` + `urlencode` lookup, and a `POST`. Adds `base_url()`, now shared by `api()` and the success line. Side effect: the "can't reach" message now shows the URL without a trailing `/`.
- tests/conftest.py: `sql()` moved here from test_projects.py, because test_tasks.py also uses it.
- tests/test_projects.py: imports `sql` from conftest and drops the unused `closing` import.
- tests/test_tasks.py: new, covering AC1–AC34. Rounds, files, verdicts, decisions, and runs are inserted by SQL.
- tests/test_cli.py: the `server` fixture gains `server.replies`, a queue that is used before `server.reply`, so the existing tests are unchanged. Adds the AC35–AC40 tests.

## Criteria → tests
- AC1 → tests/test_tasks.py::test_create
- AC2 → tests/test_tasks.py::test_create_without_description
- AC3 → tests/test_tasks.py::test_create_strips_title
- AC4 → tests/test_tasks.py::test_create_blank_title
- AC5 → tests/test_tasks.py::test_create_unknown_project
- AC6 → tests/test_tasks.py::test_first_task_position
- AC7 → tests/test_tasks.py::test_new_task_at_bottom_of_backlog
- AC8 → tests/test_tasks.py::test_create_writes_event
- AC9 → tests/test_tasks.py::test_list_empty
- AC10 → tests/test_tasks.py::test_list_unknown_project
- AC11 → tests/test_tasks.py::test_list_fresh_task
- AC12 → tests/test_tasks.py::test_list_latest_round
- AC13 → tests/test_tasks.py::test_list_pending_verdicts
- AC14 → tests/test_tasks.py::test_list_latest_run
- AC15 → tests/test_tasks.py::test_list_order
- AC16 → tests/test_tasks.py::test_get_fresh_task
- AC17 → tests/test_tasks.py::test_get_rounds
- AC18 → tests/test_tasks.py::test_get_decisions
- AC19 → tests/test_tasks.py::test_get_branch_and_run
- AC20 → tests/test_tasks.py::test_get_unknown_task
- AC21 → tests/test_tasks.py::test_patch_spec
- AC22 → tests/test_tasks.py::test_patch_stage_maps_status
- AC23 → tests/test_tasks.py::test_patch_stage_events
- AC24 → tests/test_tasks.py::test_patch_same_stage_no_event
- AC25 → tests/test_tasks.py::test_patch_stage_during_run
- AC26 → tests/test_tasks.py::test_patch_stage_keeps_position
- AC27 → tests/test_tasks.py::test_move_clears_stage
- AC28 → tests/test_tasks.py::test_move_writes_event
- AC29 → tests/test_tasks.py::test_reorder_no_event
- AC30 → tests/test_tasks.py::test_move_refused_during_run
- AC31 → tests/test_tasks.py::test_move_allowed_with_other_or_ended_runs
- AC32 → tests/test_tasks.py::test_done_at
- AC33 → tests/test_tasks.py::test_patch_invalid
- AC34 → tests/test_tasks.py::test_patch_unknown_task
- AC35 → tests/test_cli.py::test_task_add
- AC36 → tests/test_cli.py::test_task_add_path_with_space
- AC37 → tests/test_cli.py::test_task_add_from_worktree
- AC38 → tests/test_cli.py::test_task_add_unconnected
- AC39 → tests/test_cli.py::test_task_add_outside_repo
- AC40 → tests/test_cli.py::test_task_usage_errors

## Open questions
- Q1–Q11 → the spec's defaults, as written.
- The PATCH group check runs before the 404 lookup, so an invalid body on an unknown task gets 422, not 404. Pydantic's type and enum errors come first anyway.
- The group and null errors return string details: `send exactly one of: spec_md, stage, or status with position` and `<keys> must not be null`.
- Q6 edge: a task that is already `done` but has a NULL `done_at` (possible only through raw SQL) gets `done_at` = now on its next move to done, rather than keeping NULL.
- The list route makes 3 queries per task. It is marked `ponytail:`; switch to one grouped query if a board grows past a few hundred tasks.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
144 passed, 1 warning in 12.32s
```
