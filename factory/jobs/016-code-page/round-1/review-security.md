VERDICT: PASS

No blocking findings. The diff adds one read-only GET route (`/projects/{id}/code`), a template, CSS, and tests. It does not touch the middleware, server bind, run spawn/env (§4.3, §4.4), mutating routes, or the patch limit.

Checked against §4.5 and the job's checklist:
- Path containment (§4.5, spec Q2): `path` must be an exact entry of `git ls-files -z` before any filesystem call (app.py `code_page`). Then `realpath(root/path)` must be inside `realpath(root)` (app.py:1029-1030), and only `isfile` targets are opened (app.py:1032). I probed these and each one 404'd without leaking content: `./README.md`, `src/../README.md`, `README.md/`, `/README.md`, `src//app.py`, a trailing NUL, `..`, `%2e%2e/…`, a backslash path, `README.MD`, and a `<script>` path. These were also contained: a symlink chain out, a symlink into a sibling dir with a shared name prefix (`r` vs `r2`), a tracked dir swapped on disk for a symlink out, and a FIFO swapped in for a tracked file (no hang).
- Markdown: the README goes through the existing `MD = MarkdownIt("js-default", {"html": False})` filter. Raw HTML is off, and AC3's test covers it.
- Escaping: `code.html` gets Starlette's `select_autoescape()` and has no `|safe`. File text, names, the error detail, and `data-lang` are autoescaped. Hrefs use `|urlencode`. I tested a hostile file name (`x"><img src=x onerror=alert(1)>.p"y`) in the tree and the viewer, and it was escaped. The inline script interpolates no server data. highlight.js 11.12's `getLanguage` uses `Object.create(null)` maps, and its output is escaped.
- Subprocess: `["git", "-C", root, *args]` with fixed args, `timeout=10`, no shell. The user's `path` never reaches git.
- SQL: one parameterized `SELECT … WHERE id = ?`. Nothing new is logged.
- The Host check still applies to the new route (GET with `Host: evil.com` → 403).

## Nits (non-blocking)
- src/claude_factories/app.py:1029-1032 — a tracked symlink to a file under `<root>/.git/` is followed and displayed. For example, `cfg -> .git/config` showed a token in a remote URL. This is allowed by §4.5 and spec Q3, and build.md documents it, so it is not a defect. Only the local user sees it. — Optionally treat a resolved path under `realpath(root)/.git` as "not a regular file" too.
- src/claude_factories/app.py:1029-1037 — there is a check-then-open race. A path swapped for a symlink or FIFO between `realpath`/`isfile` and `open` would be followed, or would block the worker thread. It needs concurrent local writes to the main checkout. — Optionally open `real` with `os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK`, then `os.fstat` the fd for `S_ISREG` and the size check.
