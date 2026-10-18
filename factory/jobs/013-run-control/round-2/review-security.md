VERDICT: PASS

No blocking findings. Round 1 had no blocking findings, and both of its nits are fixed:
- Reaped-pgid signal: `finish_run` now commits `exit_code` right after `proc.wait()` (app.py:520-522). `stop_run` uses `RETURNING pid, exit_code` and calls `killpg` only when `exit_code IS NULL` (app.py:619-632). `test_stop_skips_reaped_leader` covers it.
- `PermissionError` from `killpg` is caught beside `ProcessLookupError` (app.py:633). The route and the shutdown loop can no longer 500 or abort on it.

What round 2 adds, checked against §4.3–§4.5 and the checklist:
- Template: `{{ refused }}` (review.html:34) is `HTTPException.detail` from `run_task`. Starlette's `Jinja2Templates` uses `select_autoescape()`, which is on for `.html`, and the value has no `|safe`, so it is escaped. The details are fixed strings plus a branch name, a worktree path, or an OSError message. None of them carries a secret.
- `HX-Current-URL` (app.py:1436-1437) is a request header, so a cross-origin page can't set it without CORS, and the route is a POST behind `local_safety` (Host allowlist plus `X-Requested-By: fctl`). Its `tab` is normalized to `files`/`conversation`, and its `round` goes through `round_or_404`. `path`/`side`/`line` stay `""`. That is no wider than the GET `review_page`'s own query parameters. `refused` can only come from the POST, so a GET link can't inject an alert message.
- `review_context` is a pure split of `review_page`. Every query is still parameterized.
- The rework spawn still goes through `run_task` unchanged: env strip (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_USE_*`), the `claude auth status` → `authMethod: claude.ai` check with 409, no `--bare`, argument-list `Popen` with `start_new_session=True`. From the async form route it runs through `run_in_threadpool`.
- §4.4: `ALLOWED_TOOLS` and `DISALLOWED_TOOLS` (app.py:446-454) are untouched. No git write command, `curl`, `fctl rework`, `approve`, or `run` is allowed, so agents can't reach request-changes, Stop, or a spawn.
- Startup marks leftover runs `failed: app restarted` and sends no signal (Q5). Shutdown reuses `stop_run`, so it gets the same `exit_code` guard.
- SQL: every new statement uses parameters. Nothing new is logged. Test subprocesses (`sleep`, `true`, the fake) use argument lists. No `shell=True`, `os.system`, or `os.popen`.
- Ran in W: `.venv/bin/python -m pytest -q tests/test_run_control.py tests/test_runs.py tests/test_review_actions.py` → 97 passed.

## Nits (non-blocking)
- src/claude_factories/app.py:520-522 — there is still a sub-millisecond window between `proc.wait()` reaping the leader and the `exit_code` commit. A Stop inside it would `killpg` a reaped pgid. The window is now as small as it can be without a lock. — Fix if it ever matters: take a per-run lock around both the reap/commit and Stop's read/signal.
- src/claude_factories/app.py:630 — once `exit_code` is set, Stop doesn't signal at all. If the leader has exited but its group still has members (an orphaned background Bash child, say), those keep running. While the group has live members, its pgid can't be reused, so signalling would be safe. Spec Q2 accepts this, and `finish_run` ends the row right after anyway. — Fix if it matters: send `killpg` whenever the group still exists, for example by checking `os.getpgid` on a stored child, or leave it to 014's orphan handling (MVP §9 Later).
