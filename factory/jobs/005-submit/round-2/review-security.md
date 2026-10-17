VERDICT: PASS

No blocking findings. 243 passed in the worktree.

## Round 1 findings
- src/claude_factories/app.py:362-365: `unquote()` no longer gives a 500 on malformed C-quoting. **Fixed.** I re-ran both reproductions: `+++ "b/x\"` and `+++ "b/\x"` now return 422 on `POST /api/tasks/{id}/rounds`, and so does a malformed quoted `diff --git` header (the mode-only fallback). AC16 covers all three.
- Nit, paths git never writes: **Fixed.** `safe_path()` (app.py:368) runs after `unquote`, on every row's `path` and on a renamed row's `old_path`. Probed, each of these returns 422 and writes no row:
  - `..` in the header fallback
  - an octal-escaped `"\056\056/x"`, in both the header and `rename to`
  - `rename to ../y`
  - `rename from /etc/passwd`
  - a deletion's `--- a/../x`
  - `b//etc/passwd`
  - a NUL, including a NUL from `\000`
  - `rename to` with no `rename from`
- Nit, `nosniff`: **Fixed.** app.py:497 sends `X-Content-Type-Options: nosniff`, and AC25 asserts it.
- Nit, `escape_decode` is an undocumented internal: kept, with a stated reason. That is acceptable.

## Checked, no issue
- §4.5 middleware: `POST /api/tasks/{id}/rounds` and `POST /api/projects/{id}/tasks` with `submit` both return 403 without `X-Requested-By: fctl`. The diff route and both POSTs return 403 for Host `evil.com`. Bind address unchanged.
- §4.5 413: the patch is measured in UTF-8 bytes before the other patch checks. 5 MB + 1 returns 413.
- `base_sha` must be 7–64 lowercase hex. The `url` host comes from `request.base_url`, which the middleware restricts to 127.0.0.1/localhost.
- The diff route's 404 echoes `n` only inside a JSON `detail` (`application/json`). It is never rendered as HTML.
- Subprocesses: `capture()` uses argument lists. There is no `shell=True` or `os.system`. `--no-ext-diff --no-textconv` keep config-driven diff drivers out. `base_sha` comes from `rev-parse --verify`. CLI `id` and `--round` are `type=int`, and the project path is urlencoded.
- SQL: every new query takes parameters. The new app code has no f-string SQL.
- §4.3/§4.4 are untouched: no run env, allow/deny lists, templates, markdown, `|safe`, or run spawning changed. No route reaches approve, run, or rework. No new logging, and no secrets in error text.

## Nits (non-blocking)
- src/claude_factories/app.py:363: `codecs.escape_decode` raises only a `DeprecationWarning`, not a `ValueError`, on an unknown escape (`"b/\q"`) or an octal escape above `\377`. Under default warning settings the name is stored as-is (`\q`), or with U+FFFD, and the request returns 201. That is harmless, because neither name contains `/`, `..`, or NUL. If the server ever runs with warnings as errors (`-W error` / `PYTHONWARNINGS=error`), this becomes a 500. Catching `(ValueError, DeprecationWarning)` would close that.
