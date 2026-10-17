VERDICT: CHANGES

## Findings

- src/claude_factories/app.py:362 — `unquote()` passes untrusted patch text straight to `codecs.escape_decode`. That function raises `ValueError` on a malformed C-quoted name, such as a trailing backslash (`+++ "b/x\"`) or a bad `\x` escape (`+++ "b/\x"`). It is reached from the `---`/`+++`/`rename` lines (line 386) and from the `diff --git` header fallback (line 397). The result is an unhandled 500 at the trust boundary. Spec Q4 says "A section whose path can't be read → 422". I reproduced it: both bodies return `500 Internal Server Error` on `POST /api/tasks/{id}/rounds`. The transaction rolls back and nothing is written, so this is a wrong status code with no data loss or leak. — Fix: in `unquote`, catch `ValueError` around `escape_decode` and return `""`. An empty name already leads to the existing `422 can't read the file path in: …` on every path branch. Add one case for it to AC16's parametrize list.

## Checked, no issue
- §4.5 middleware: the new `POST /api/tasks/{id}/rounds` and `POST /api/projects/{id}/tasks` with `submit` both return 403 without `X-Requested-By: fctl`. Both, plus `GET …/rounds/{n}/diff`, return 403 for Host `evil.com` and `127.0.0.1.evil.com`. Bind address unchanged.
- §4.5 413: the patch is measured in UTF-8 bytes before any other patch check, on both routes. 5 MB + 1 returns 413 and writes nothing.
- `base_sha` pattern (pydantic's Rust regex, so `$` means end of text) rejects `abcdef0\n`, uppercase, and `-…`. It can't become a git option later.
- Subprocesses: `capture()` and `_git` use argument lists. There is no `shell=True` or `os.system`. `--no-ext-diff --no-textconv` keep config-driven drivers out of the diff. `git add -A` stores symlinks as links and never follows them out of the tree.
- SQL: every new query is parameterized, including `CAST(n AS TEXT) = ?`. f-strings appear only in tests, and only with constant table and column names.
- No templates, markdown rendering, `|safe`, run spawning, run env, or allow/deny lists changed. §4.3/§4.4 aren't touched, and no route reaches approve, run, or rework. The `url` host comes from the Host header, which the middleware limits to 127.0.0.1/localhost.
- No new logging. CLI errors print only git's stderr and the server's `detail`.

## Nits (non-blocking)
- src/claude_factories/app.py:387-401 — paths that git never produces are stored as-is: `../../etc/passwd`, `/etc/passwd` (from `b//etc/passwd`), and names containing NUL all return 201. Nothing in this job opens files by `round_files.path`, and §4.5's root check belongs to the code page. Still, rejecting a leading `/`, any `..` segment, or a NUL with the existing 422 would be cheap defense in depth before 008 starts linking these paths.
- src/claude_factories/app.py:488 — the `text/x-diff` response has no `X-Content-Type-Options: nosniff`. Modern browsers don't sniff a declared `text/x-diff` as HTML, so agent-written patch text isn't exposed as same-origin HTML today. The header would make that explicit.
- src/claude_factories/app.py:362 — `codecs.escape_decode` is an undocumented CPython internal. A small explicit octal/escape decoder would avoid depending on it. This is optional once the `ValueError` above is handled.
