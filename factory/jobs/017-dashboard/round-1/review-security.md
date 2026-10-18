VERDICT: PASS

The diff touches two security areas. One is SQL in a new read-only `GET /` route. The other is Jinja output of DB text in `index.html`. It touches no bind or Host/header middleware, markdown, file paths, patches, subprocesses, run env, or allowlists.

## Findings
None blocking.

- SQL injection: no untrusted value reaches a SQL string. `show` is never interpolated. It is only used as a dict key after `show == "runs_week"` or `show in TILE_TASKS` (src/claude_factories/app.py:1031), and any other value is reset to `""`. Every interpolated fragment is a module constant: `COLUMNS`, `TILE_TASKS`, the `TILE_TASKS` keys used as column aliases, and `days_ago()` called with the int literals 7 and 30.
- XSS: `index.html` renders through Starlette's `Jinja2Templates`, which uses `select_autoescape()`, so `.html` output is escaped. There is no `|safe`. `local_time` returns a plain `str`, not `Markup`. Task, project, and workspace names are escaped, and test_title_escaped (AC20) checks this. `show` is only echoed as `tiles[show]` after the membership check, never raw.
- The route only reads: GET, SELECTs only, no new mutating endpoint, so the `X-Requested-By` and Host checks are unaffected.

## Nits (non-blocking)
- src/claude_factories/app.py:996 — `days_ago(n)` builds SQL with an f-string. That is safe today because every caller passes an int literal, but it is the first f-string SQL in `src/` and would become injectable if someone later wired it to a query parameter (say `?days=`). Fix: bind the modifier instead, e.g. `strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)` with args `('-7 days',)`, or compute the cutoff in Python as `db.now()`-format text and bind that.
- src/claude_factories/app.py:1008 — `f"t.status = '{status}'"` puts `COLUMNS` values into SQL. They are constants, so this is fine. A comment saying TILE_TASKS must stay constant (the docstring at 1018 already says this) is enough.
