VERDICT: PASS

590 passed, 1 warning in 68.06s (0:01:08)

No blocking findings.

- Stack: no new dependency; plain SQL via `query()`, `itertools.groupby`, no frontend build.
- AC1-AC20 each have a test in tests/test_dashboard.py that asserts the criterion (exact id sets, ordering, escaping, boundaries at 6/8 and 29/31 days). AC21 tests pass unchanged.
- Tests use the shared `client` fixture (temp FCTL_HOME); no `claude` is spawned, so no fake is needed.
- Nothing unrequested: only the four files in the spec changed; SQL fragments are constants and `show` is checked against a dict before use; the `ponytail` comment is deleted.

## Nits (non-blocking)
- src/claude_factories/app.py (`TILE_TASKS`) — the f-string `t.status = '{status}'` builds SQL from `COLUMNS`; safe because `COLUMNS` is constant, a short comment saying so would help.
