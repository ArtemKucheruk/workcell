# Round 2
## Changes
- src/claude_factories/app.py:
  - `request_changes`: when `run_task` refuses after `decide_review` has committed, the HTTPException gets `recorded = True` and is re-raised. The API response stays exactly as before: same status, same detail.
  - `request_changes_form`: a refusal with `recorded` now answers 200 with the review page as it is now, plus `HX-Retarget: header`, `HX-Reselect: header`, and `HX-Reswap: outerHTML`. htmx swaps the header in, so it reads "In progress · rework" with the Summary and both buttons disabled, and the refusal's detail sits in the Request changes alert. The round and tab come from htmx's `HX-Current-URL`, so the swapped header keeps the page's round and its `tab=files` input. A refusal before any write (`run #N active`, blank summary, not in review) is still the plain 4xx, and the existing script puts it in the alert.
  - `review_page` is split into the route and `review_context(task_id, n, tab, path, side, line)`, so the form can render the same page with `refused` added. `refused` is not a query parameter of the GET route, so a link can't inject a message.
  - `finish_run` writes `exit_code` in its own commit right after `proc.wait()`, before it reads the log. `stop_run` returns `pid, exit_code` and sends a signal only while `exit_code` is NULL, so a reaped leader's pgid is never signalled. It catches `PermissionError` beside `ProcessLookupError`.
  - `stop_run` and `run_log` 404s now say `run #N not found`.
- src/claude_factories/templates/review.html: the Request changes `.form-error` renders `{{ refused }}`, which is empty unless the form route set it. This is the only template change. The spec says no template change, but the ux CHANGES finding needs the server-rendered alert.
- tests/test_run_control.py:
  - New `test_rework_form_refused_after_write` covers the ux finding.
  - New `test_stop_skips_reaped_leader` covers the security nit.
  - AC5 and AC17 now also assert the `run #999 not found` detail.

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

## Review findings
- ux · the form gets a 409 after the decision is recorded and the page isn't refreshed → fixed. The form answers 200 with the current header swapped in, showing "In progress · rework", the controls disabled, and the detail in the alert. Test: `test_rework_form_refused_after_write`. I didn't re-walk it in a browser, because there was no browser tool in this session. The test checks the HX headers and the rendered header.
- ux nit · unknown-run 404 says only "Not Found" → fixed for the run routes (`run #N not found`). Task 404s from approve and request-changes still come from 009's `decide_review` as before. I left them alone to stay in scope.
- ux nit · `?after=-1` gives FastAPI's validation list → not changed. It is the same 422 shape as every other validation error in the app, and AC17 only asks for a 422.
- ux nit · `run #N active` and `not on subscription auth` give no next step → not changed. The API text is spec'd, and fctl hints are a CLI change, which is out of scope (015).
- ux nit · `exit_code` stays NULL after SIGINT on serve → by design (Q4: shutdown doesn't wait for exits).
- security nit · `killpg` on a pgid reaped before `finish_run` updates the row → fixed. `exit_code` is written right after `proc.wait()`, and `stop_run` signals only while it is NULL. Test: `test_stop_skips_reaped_leader`.
- security nit · `PermissionError` from `killpg` becomes a 500 → fixed: it is caught beside `ProcessLookupError`. It has no test, because a test would need a process group owned by another user.
- code nit · `RecursionError` catch beyond the spec → kept. It is justified in round 1's build.md.

## Open questions
- Round 1's four open questions still hold: non-empty name and summary strings, `agent` for a non-string parent id, the check-then-decide gap in Q12, and an empty log page for any `OSError`.
- The form's post-write refusal is a 200, not a 409, because htmx swaps only 2xx responses. The JSON API keeps the spec'd status and detail.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
543 passed, 1 warning in 62.43s (0:01:02)
```
