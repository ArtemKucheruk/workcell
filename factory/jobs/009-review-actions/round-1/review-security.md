VERDICT: PASS

No blocking findings. Checked against MVP §4.3–§4.5 and the job's security surface:

- §4.5 header/Host: all four new mutating routes (`POST /api/tasks/{id}/approve`, `/api/tasks/{id}/request-changes`, `/tasks/{id}/approve`, `/tasks/{id}/request-changes`) go through the existing `local_safety` middleware (src/claude_factories/app.py:69). It checks the Host allowlist and `X-Requested-By: fctl`. The test `test_actions_need_fctl_header` covers all four routes with 403 and nothing written. `fctl` (cli.py:32) and htmx (base.html `hx-headers`) send the header.
- Autoescape / Markdown: `section#commit` renders `{{ commit_hint }}` in a `<pre>` with Starlette's default autoescape, and there is no `|safe` anywhere in templates. AC22 tests `<b>` showing as `&lt;b&gt;`. The new CHANGES_REQUESTED/APPROVE bodies reach the page only through the existing `markdown` filter (`MarkdownIt("js-default", {"html": False})`, app.py:65), not `commonmark`.
- Shell safety of `commit_hint` (app.py:852): every interpolated value goes through `shlex.quote`. The values that could otherwise act as options are app-generated: branch is `factory/<id>-<slug>` and the worktree is `<absolute project path>/.claude/worktrees/<name>` (app.py:477). Project path must be absolute (app.py:207). So no value can start with `-` in `cd`/`git push`/`git worktree remove`. The title follows `-m`, so a leading `-` there is harmless. The app never runs these commands, and the diff adds no subprocess call.
- SQL: `decide_review` (app.py:867) uses `?` parameters for every value. Check and writes share one `BEGIN IMMEDIATE` transaction (app.py:871), so a failed check rolls back, and a double submit can't record two decisions (AC8 test).
- §4.4: `ALLOWED_TOOLS` (app.py:436–440) is unchanged and does not include `fctl approve` or `fctl rework`. `fctl stage` can only set stages that map to in_progress/review (`STAGE_STATUS`, app.py:44), so an agent can't reach done through it. No agent template under `factory_templates/` mentions approve or rework. The deny list is unchanged, and no git write command is allowed.
- §4.3: run env / auth / `--bare` untouched by this diff.
- No secrets logged. The new code doesn't log anything.

Tests: `uv run --offline pytest -q tests/test_review_actions.py tests/test_cli.py tests/test_review_files.py` → 153 passed.

## Nits (non-blocking)

- src/claude_factories/cli.py:200 — `fctl approve` prints `commit_hint` straight to the terminal. `shlex.quote` neutralises shell metacharacters but not terminal control bytes, so a title with ESC sequences (e.g. from a `/factory-submit` session) would reach the terminal raw. The same is true of every other `fctl` command that echoes task text. Low risk, since titles come from me or my own sessions. Fix if wanted: reject control characters in task titles at the API boundary.
- src/claude_factories/app.py:436 (pre-existing, not this job's defect) — "agents can't reach approve or rework" holds only at the `fctl` allowlist level. The per-project test-command entry (e.g. `Bash(pytest *)`) runs worktree code, which could POST `/api/tasks/{id}/approve` with `X-Requested-By: fctl` directly. This job makes that endpoint exist, so it's worth an Open-question note in docs/ (§4.4) rather than a code change here.
