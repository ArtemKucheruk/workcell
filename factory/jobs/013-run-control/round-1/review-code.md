VERDICT: PASS
541 passed, 1 warning in 61.65s (0:01:01)

No blocking findings. Checked:
- Stack: stdlib only (`signal`; `run_in_threadpool` ships with Starlette). No new dependency, no schema change, fctl untouched.
- AC1-AC23 each have a test that asserts the criterion. The tests use a temp FCTL_HOME and the fake `claude`, and the `long` fixture reaps the runs it starts.
- app.py matches the spec files section: `stop_run` is shared by the route and the shutdown, `finish_run` only fills in `exit_code` on a row Stop already ended, and `request_changes` refuses an active run before writing anything.

## Nits (non-blocking)
- src/claude_factories/app.py `finish_run` — the `RecursionError` catch is beyond the spec, but it is small and justified in build.md.
