VERDICT: PASS

No blocking findings. What I checked against the diff:
- §4.5 middleware: both new mutating routes (`POST /api/projects/{id}/factory`, `POST /projects/{id}/factory`) go through `local_safety`. A probe with `Host: evil.com` got 403 on both and wrote nothing. A missing `X-Requested-By` gets 403 (AC19, AC25).
- Write containment (Q8): every check runs before any write. `realpath(target).is_relative_to(realpath(root))` compares path components, so `/repo-evil` doesn't pass as `/repo`. Probes gave 409 with nothing written for: `.claude` symlinked out, `.claude/agents` symlinked out (AC18), `builder.md` symlinked to an outside file (overwrite false and true), and a dangling `builder.md` link pointing outside (overwrite false and true). Template names come from the constant `FACTORY_FILES` and never from input.
- Jinja: `FACTORY_TEMPLATES` turns autoescape off only for the markdown output. The templates are package files, and inserted values are never re-evaluated (AC9). `factory_result.html` renders through `Jinja2Templates` with autoescape on and no `|safe`. `error` (path, workspace name) is escaped.
- SQL: the new SELECT and UPDATE use `?` parameters.
- Subprocess: the app adds none. The tests' git calls use argument lists. No `shell=True` and no `os.system`. `shlex.quote` only formats a message string.
- §4.4 template content: the allowlist in SKILL.md matches docs/MVP.md §4.4. Grepping the 8 templates found no `fctl approve|run|rework`, no `curl`, no `--bare`, and no git write command given as an instruction. builder.md and SKILL.md forbid commits and git writes. AC7's regex test enforces the fctl subcommand set.
- No secrets and no logging added. Markdown preset and 413 handling are unchanged.

## Nits (non-blocking)
- src/claude_factories/app.py:284 — with overwrite, a target that is a symlink to another file inside the repo is written through. A probe linked `.claude/agents/builder.md` to `<repo>/Makefile`, and the Makefile was replaced by the builder template. It stays inside the project root, so Q8 holds, but the user didn't ask for that file to change. Fix: `if overwrite and target.is_symlink(): target.unlink()` before writing.
- src/claude_factories/app.py:1002 — `bool(form_field(...))` treats any non-empty value as overwrite, so `overwrite=false` or `overwrite=0` replaces files. Only htmx's `on` can reach this route behind `X-Requested-By`, so it can't be exploited. Fix: `== "on"`.
- src/claude_factories/app.py:274-284 — check-then-write leaves a same-user TOCTOU window (a link swapped in between the check and `write_text`). It's local and single-user, and agents can't create links outside their worktree, so the spec's Q8 approach is acceptable.
