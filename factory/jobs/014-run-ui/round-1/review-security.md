VERDICT: PASS

No blocking findings. What I checked, by item:

- §4.5 Host / X-Requested-By: `local_safety` (app.py:80-88) is unchanged and covers every request. The new buttons (Run, Run next, Retry, Stop) are htmx `hx-post`s inside `<body hx-headers='{"X-Requested-By": "fctl"}'>`. No `hx-disinherit` or `htmx.config` override exists. The log panel's `fetch` is a same-origin GET.
- §4.5 escaping: Starlette's `Jinja2Templates` uses `select_autoescape()`, which is on for `.html`. No `|safe` was added. Agent-derived text is autoescaped: `run.error`, `t.stage`, the `subscriptionType` label, `hint`, `takeover`. AC16 tests `<script>` in `run.error`. Log items and the 409 `detail` go in with `textContent` only. The diff adds no `innerHTML` or `insertAdjacentHTML`. POST buttons use `hx-swap="none"`, so JSON replies never become DOM. The markdown filter (`js-default`, `html: False`) is untouched.
- Subprocess: `auth_status` passes an argument list, with `stdin=DEVNULL` and a 30 s timeout. There is no shell, and the diff adds no `os.system`.
- §4.3: `stripped_env()` is the old `run_env` filter, moved as is. It drops `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and `CLAUDE_CODE_USE_*`. The badge check uses it, with cwd = `db.data_dir()`, so no project's settings apply (AC4). `run_task` still calls `subscription_auth(wt, run_env(request))` on every run, uncached, with the run's own cwd and env. The 60 s cache only feeds the page badge and the buttons' `disabled`. `--bare` appears nowhere.
- §4.4: the spawn `cmd`, allow list, and deny list are untouched. The takeover string is built with `shlex.quote` on both parts and is display-only. No new route, so agents get nothing new to reach.
- SQL: the new queries (app.py `project_page` started_at, `task_page` latest run, `PAGE_TASK` + `p.default_branch`) are parameterized or literal. The auth-status output (which may hold email or org) is neither logged nor rendered beyond the plan name.
- Ran `uv run pytest -q tests/test_run_ui.py tests/test_board.py tests/test_runs.py` in W: 102 passed.

## Nits (non-blocking)

- src/claude_factories/app.py:1525 — `shlex.quote` stops shell injection, but not option injection. `session_id` comes from the last `type: result` line in the run log, and that log also captures stderr. So code that can append to the log could set S to something like `--dangerously-skip-permissions`, which shows up unquoted after `claude --resume`. The only code that can do that is code the run already executes (e.g. via `pytest *`), so this gives no new privilege. — Show the takeover line only when `uuid.UUID(run["session_id"])` parses. Session ids are always UUIDs.
- src/claude_factories/app.py:100-104 — `page_not_found` is `async`, and `error.html` extends `base.html`. On a cold cache, `claude_login()` (app.py:540-547) runs a blocking `subprocess.run` on the event loop thread, for up to 30 s, and every request stalls until it returns. The 60 s cache keeps this to one stall per minute. — Render the 404 page with `await run_in_threadpool(templates.TemplateResponse, ...)`, or make the handler sync-safe some other way.
