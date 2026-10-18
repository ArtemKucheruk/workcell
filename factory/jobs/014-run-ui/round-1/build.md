# Round 1
## Changes
- src/claude_factories/app.py:
  - `auth_status()` is split out of `subscription_auth`. It returns the parsed dict when the exit code is 0 and `authMethod == "claude.ai"`, and `None` otherwise. `subscription_auth` is now `auth_status(...) is not None`, so `run_task`'s per-run check is unchanged and still uncached.
  - `stripped_env()` is split out of `run_env` (the §4.3 stripping). `run_env` = `stripped_env() | FCTL_URL`.
  - `claude_login()` returns `(label, runs allowed)`. It runs `auth_status(db.data_dir(), stripped_env())` and caches the answer in the module-level `LOGIN` dict for 60 s on `time.monotonic` (imported as `monotonic`, so tests can move this clock alone). It's a Jinja global, so `base.html` renders it on every page, the 404 page included. The `ponytail:` comment notes there's no lock.
  - `factory_hint(state, branch)`: one helper for the `uncommitted` and `none` texts. `run_task`'s two 409s now use it, and their text is the same.
  - The `local_time` filter takes an optional format (`local_time("%H:%M")`).
  - `project_page`: `started_at` for each card's latest run, read after `list_tasks` the way `positions` is. The API's `run` is still `{id, status}`. Also `hint`, and `can_run` = factory ready and the login allows runs.
  - `PAGE_TASK` gains `p.default_branch`. `task_page` adds the latest run row (id, status, error, session_id, started_at), `hint`, `can_run`, and the `shlex.quote`d takeover string.
- src/claude_factories/templates/base.html: `<p id="claude-auth">` sits before `{% block content %}`, outside any `<header>`/`<section>`. `.off` uses the existing red `light-dark(#cf222e, #f85149)`. Also minimal CSS for the run controls row, the card's run line, and the log box.
- src/claude_factories/templates/project.html:
  - A `run_button` macro: `hx-swap="none"`, `hx-disabled-elt="this"`, and `disabled` unless `can_run`. It renders the enabled **Run next ▶** and the hint beside it, `[Run]` on Backlog cards, and `● running · <stage>` + `started HH:MM` / `stalled · <stage> [Retry]` on in_progress cards that have a run. An in_progress card with no runs is unchanged.
  - `#board`'s poll pauses while `#board .htmx-request` exists, and `beforeSwap` drops a poll already in flight then.
  - An `htmx:afterRequest` listener on `.run-action`: on success it clears `#board-error` and refreshes `#board`. On refusal it puts the reply's `detail` in `#board-error`.
- src/claude_factories/templates/task.html:
  - Inside `#live`'s `<header>`: Stop (never disabled) while the latest run is `running`. Otherwise Run for a backlog task, or Retry for in_progress with a run. Then `#run-status`, the hint next to Run/Retry, a `role="alert"` `#run-error` with `hx-preserve` so the 3 s polls don't wipe it, and the takeover line or `Stop the run to take over.`.
  - `#live`'s poll pauses on `#live .htmx-request`. The afterRequest listener reloads on success and fills `#run-error` on refusal. That script sits before `#live`, so 010's `</main>\s*</div>\s*</body>` check still holds.
  - After `#live`, and only when the task has a run: `<details id="run-log" data-run>` and a script. The script fetches `/api/runs/<R>/log?after=<next>` from 0, appends each item as a `<div>` set by `textContent`, and keeps the box scrolled to the end, on `toggle` too. It polls every 3 s if the run was `running` at page load (`data-live`), and fetches once otherwise. A `ponytail:` comment says it follows the run that was latest at page load.
- tests/conftest.py: the autouse `isolated` fixture clears `LOGIN`.
- tests/test_run_ui.py (new): AC1–AC20. It imports `fake`, `project`, `add_task`, `connect`, `SKILL`, and `AUTH_OK` from `test_runs`. AC5 uses its own `sh` fake that appends a line per call.
- tests/test_board.py: the exact Backlog card text now ends in ` Run` (AC21).

## Criteria → tests
- AC1 → tests/test_run_ui.py::test_badge_on_every_page
- AC2 → tests/test_run_ui.py::test_badge_plan (parametrized: max, no subscriptionType)
- AC3 → tests/test_run_ui.py::test_badge_off (parametrized: console, not json, AUTH_OK + exit 1)
- AC4 → tests/test_run_ui.py::test_badge_check_env_and_cwd
- AC5 → tests/test_run_ui.py::test_badge_cached_60s
- AC6 → tests/test_run_ui.py::test_backlog_card_run
- AC7 → tests/test_run_ui.py::test_run_next_enabled
- AC8 → tests/test_run_ui.py::test_running_card
- AC9 → tests/test_run_ui.py::test_stalled_card (parametrized: failed, stopped, succeeded)
- AC10 → tests/test_run_ui.py::test_in_progress_without_runs
- AC11 → tests/test_run_ui.py::test_board_factory_not_ready (parametrized: uncommitted, none)
- AC12 → tests/test_run_ui.py::test_board_api_key
- AC13 → tests/test_run_ui.py::test_task_backlog_run
- AC14 → tests/test_run_ui.py::test_task_running_stop
- AC15 → tests/test_run_ui.py::test_task_stalled_retry (parametrized: failed + error, stopped, succeeded, failed + NULL)
- AC16 → tests/test_run_ui.py::test_task_run_error_escaped
- AC17 → tests/test_run_ui.py::test_task_review_and_done
- AC18 → tests/test_run_ui.py::test_task_runs_disabled (parametrized: uncommitted, api key)
- AC19 → tests/test_run_ui.py::test_task_run_log
- AC20 → tests/test_run_ui.py::test_task_takeover (parametrized: plain path, path with a space), tests/test_run_ui.py::test_task_no_takeover
- AC21 → the whole suite, plus tests/test_board.py::test_stage_text, tests/test_board.py::test_no_rounds_no_chips, and tests/test_board.py::test_new_task_lands_last (test_run_next_disabled is unchanged and passes)

## Open questions
- Q1–Q13 → the spec's defaults, as written.
- AC21 lists two 004 tests whose exact card text gains ` Run`. A third, `test_board.py::test_new_task_lands_last` (003 AC30), also compares a Backlog card's exact text. I updated it the same way (`… Export CSV Run`), and its meaning is unchanged.
- The refusal alert on the task page sits inside `#live` with `hx-preserve`, so the 3 s poll keeps it. It clears on reload, which follows every successful action.
- An empty log shows `No output yet.` until the first line arrives.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
648 passed, 1 warning in 106.12s (0:01:46)
```
