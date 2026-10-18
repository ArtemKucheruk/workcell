# Round 1
## Changes
- src/claude_factories/app.py:
  - `lifespan`: after `db.init()`, one `UPDATE` turns every `running` row into `failed` / `app restarted` with `ended_at`, and sends no signal (Q5). After `yield`, it calls `stop_run` on every `running` row and ignores a 409 if a run ended in between (Q4).
  - `stop_run` is both `POST /api/runs/{run_id}/stop` and the shutdown helper. One `UPDATE … WHERE status = 'running' RETURNING pid` sets `stopped` and `ended_at`. If no row changed, the answer is a 404 for an unknown id, else 409 `run #N is not running`. Then it calls `os.killpg(pid, SIGTERM)` when `pid` is set and ignores `ProcessLookupError` (Q1, Q2). A `ponytail:` comment notes the gap between the insert and the pid being stored.
  - `finish_run`: always records `exit_code`. Status, error, session, and `ended_at` change only `WHERE status = 'running'`, so a stopped row stays `stopped` (Q1). It also catches `RecursionError` beside `ValueError`. Without that, one very deeply nested JSON line in a log would kill the exit thread and leave the row `running` for good, which blocks every run.
  - `GET /api/runs/{run_id}/log?after=` (`Query(0, ge=0)`) reads the whole file with `newline=""` and `errors="replace"`. It counts complete `\n` lines and holds back a trailing partial line (Q6). A missing or unreadable file gives `{"next":0,"lines":[]}` (Q9). `log_items` maps the lines as Q7 says. Agent names come from every `tool_use` in the file (Q8), so a name still resolves when the spawn is before `after`. Any unexpected shape gives no item and never a 500.
  - `request_changes` now takes `request`. It reads `branch` and `worktree_path`, and a factory task (both set, Q11) gets `refuse_if_running` before anything is written. Then come `decide_review` and, for a factory task only, `run_task`, whose `run_id` is returned. A refusal from `run_task` keeps its status and detail, and the decision and the move stay (Q12).
  - `request_changes_form` runs `request_changes` through `run_in_threadpool`, so the spawn doesn't block the event loop.
- tests/test_runs.py: the `fake` fixture takes a new `long=False` option (the long-running fake). It prints the system line, starts `sleep 60` in its own process group, writes the child's pid atomically to `records/child`, and then sleeps 60 s.
- tests/test_run_control.py (new): AC1–AC22. The `long` fixture stops and reaps every run it started at teardown, so no late exit writes into the next test's database.
- tests/test_review_actions.py (AC23): AC10 and the last two asserts of AC12 now expect 409 `factory isn't committed on main`, because `/code/api` isn't a repo. AC21's form test now uses the `standalone` task, since it only checks the decision rows.

## Criteria → tests
- AC1 → tests/test_run_control.py::test_stop
- AC2 → tests/test_run_control.py::test_stop_signals_group
- AC3 → tests/test_run_control.py::test_stop_then_exit
- AC4 → tests/test_run_control.py::test_stop_leaves_task
- AC5 → tests/test_run_control.py::test_stop_not_running
- AC6 → tests/test_run_control.py::test_stop_needs_header
- AC7 → tests/test_run_control.py::test_stop_without_live_pid
- AC8 → tests/test_run_control.py::test_shutdown_stops_runs
- AC9 → tests/test_run_control.py::test_startup_fails_leftover_runs
- AC10 → tests/test_run_control.py::test_retry_after_stop
- AC11 → tests/test_run_control.py::test_retry_after_restart
- AC12 → tests/test_run_control.py::test_log
- AC13 → tests/test_run_control.py::test_log_after
- AC14 → tests/test_run_control.py::test_log_subagent_type
- AC15 → tests/test_run_control.py::test_log_partial_line
- AC16 → tests/test_run_control.py::test_log_odd_shapes
- AC17 → tests/test_run_control.py::test_log_missing_and_bad
- AC18 → tests/test_run_control.py::test_rework_spawns_run
- AC19 → tests/test_run_control.py::test_rework_standalone
- AC20 → tests/test_run_control.py::test_rework_while_running
- AC21 → tests/test_run_control.py::test_rework_spawn_refused
- AC22 → tests/test_run_control.py::test_rework_form
- AC23 → tests/test_review_actions.py::test_request_changes, ::test_request_changes_standalone, ::test_request_changes_form, plus the full `uv run pytest -q`

## Open questions
- Q7: the summary is the first *non-empty* string among the listed input keys, and the same goes for the Q8 name. An empty `command` falls through to the next key instead of giving `Bash` with an empty summary.
- Q7: `who` is `agent` when `parent_tool_use_id` is not null and not a string. Only string ids are looked up.
- Q12: for a factory task, `refuse_if_running` runs before `decide_review` and in a separate transaction. If a run starts in the gap between them, `run_task` refuses after the decision is written, and the task waits as stalled · rework, as Q12 already allows.
- Q9: the log route also answers `{"next":0,"lines":[]}` for any `OSError`, not just a missing file (for example a directory or a permission error), so a poll never errors.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
541 passed, 1 warning in 61.63s (0:01:01)
```
