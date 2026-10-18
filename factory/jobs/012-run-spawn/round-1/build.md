# Round 1
## Changes
- src/claude_factories/app.py: new "Runs" section.
  - `PROMPT`, `ALLOWED_TOOLS`, `DISALLOWED_TOOLS` constants (§4.4, §10 OQ1). The test-command entry is built per run from `projects.test_cmd`: the words before the first `-` word (Q7).
  - `slug()` (Q3).
  - `refuse_if_running()`: the shared `409 run #N active` check.
  - `worktree()`: finds `info/exclude` with `git rev-parse --path-format=absolute --git-path`, appends `.claude/worktrees/` once (adding a newline first if needed), then reuses the stored `worktree_path` (409 if it's missing) or runs `git worktree add -b factory/<id>-<slug> <path>/.claude/worktrees/<id>-<slug> <default_branch>` and stores `branch`/`worktree_path` right away (Q4, Q5).
  - `run_env()`: `os.environ` minus `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and `CLAUDE_CODE_USE_*`, with `FCTL_URL` set to the request's base URL (§4.3, Q8).
  - `subscription_auth()`: `claude auth status` with the run's cwd and env, stdin `/dev/null`, and a 30 s timeout. It passes only on exit 0 with JSON `authMethod == "claude.ai"` (Q6).
  - `finish_run()`: the daemon thread's target. It waits for the process, takes the last JSON `type: result` line in the log, and sets status, exit_code, error, session_id, and ended_at (Q10). It never touches the task.
  - `POST /api/tasks/{id}/run`: runs the checks in Q2's order. One `BEGIN IMMEDIATE` transaction re-checks for an active run, inserts the run, sets `log_path`, moves a backlog task to in_progress (stage NULL, position kept), and writes the `app` event (Q9). An `IntegrityError` from `one_active_run` also becomes `409 run #N active`. Then `Popen` with an argument list: cwd is the worktree, stdin `DEVNULL`, stdout and stderr go to `<FCTL_HOME>/runs/<id>.jsonl`, and `start_new_session=True` gives the run its own process group. Then `runs.pid` is stored and the thread starts. If `Popen` raises `OSError`, the run row becomes `failed` and the route answers 500 (Q11).
  - `POST /api/projects/{id}/run-next`: picks the lowest position, then lowest id, among the backlog tasks and calls `run_task` (Q13).
  - Both routes are POSTs, so the existing middleware covers them. No schema change and no new dependency.
- tests/test_runs.py: new. It writes the fake `claude` per test over `tmp_path/bin/claude`, as a Python script whose shebang is `sys.executable`. For `auth status` and for `-p`, the fake records its argv, cwd, env, pid, and pgid as JSON in `$FAKE_CLAUDE_RECORDS`. Its output and exit codes are parameters.
  - AC23 pins `PATH` to the fake's dir plus git's real dir, and asserts that dir has no `claude`. Otherwise, once the fake deletes itself, `Popen` would find the real `~/.local/bin/claude`.

## Criteria → tests
- AC1 → tests/test_runs.py::test_run_response
- AC2 → tests/test_runs.py::test_worktree_and_branch
- AC3 → tests/test_runs.py::test_slug
- AC4 → tests/test_runs.py::test_exclude_line_once
- AC5 → tests/test_runs.py::test_argv
- AC6 → tests/test_runs.py::test_test_cmd_entry (uv run pytest -q, NULL)
- AC7 → tests/test_runs.py::test_cwd_is_worktree
- AC8 → tests/test_runs.py::test_env_stripped
- AC9 → tests/test_runs.py::test_own_process_group
- AC10 → tests/test_runs.py::test_log_and_row
- AC11 → tests/test_runs.py::test_backlog_to_in_progress
- AC12 → tests/test_runs.py::test_rerun_in_progress
- AC13 → tests/test_runs.py::test_exit_success
- AC14 → tests/test_runs.py::test_exit_error_result
- AC15 → tests/test_runs.py::test_exit_without_result (no output, no result)
- AC16 → tests/test_runs.py::test_exit_leaves_task (all 4 exits)
- AC17 → tests/test_runs.py::test_refused_while_running
- AC18 → tests/test_runs.py::test_refused_by_status (review, done)
- AC19 → tests/test_runs.py::test_refused_without_factory (on disk only, absent)
- AC20 → tests/test_runs.py::test_refused_without_subscription (console, not json, exit 1)
- AC21 → tests/test_runs.py::test_refused_when_worktree_add_fails
- AC22 → tests/test_runs.py::test_refused_when_worktree_missing
- AC23 → tests/test_runs.py::test_spawn_fails
- AC24 → tests/test_runs.py::test_unknown_task_and_missing_header
- AC25 → tests/test_runs.py::test_run_next_takes_top
- AC26 → tests/test_runs.py::test_run_next_empty_or_unknown
- AC27 → tests/test_runs.py::test_run_next_while_running

## Open questions
- Q1–Q14 → the spec's defaults, as written.
- In AC21, git 2.49 creates the branch `factory/<id>-<slug>` before it fails on the existing directory, and leaves the branch behind. After the stray directory is removed, the next `/run` fails with `git worktree add failed: fatal: a branch named … already exists` until someone runs `git branch -D`. → Left as is: removing branches is MVP §9 Later, and the spec forbids touching branches here.
- If the thread that waits on a run dies (for example, the log file is deleted while the run is going), the row stays `running` and blocks runs until 013's startup cleanup. → Not guarded. The spec doesn't cover it.

## Test output
```
...........................................................              [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/012-run-spawn/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
347 passed, 1 warning in 51.50s
```
