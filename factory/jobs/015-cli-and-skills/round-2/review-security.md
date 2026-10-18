VERDICT: PASS

No blocking findings. Both round-1 security nits are fixed. Round 2's new server changes (app.py) were checked against docs/MVP.md §4.3–§4.5:

- Round-1 nit 1 (test command comes from repo files) → fixed. factory-connect/SKILL.md:17–18 tells Claude to show the chosen command, and the file it came from, before running `fctl connect`.
- Round-1 nit 2 (a line that is exactly `EOF` ends the heredoc early) → fixed. factory-submit/SKILL.md:23–24 forbids it, and step 4 applies the same rule to the build notes.
- app.py:237 `find_project` 404 detail: it now adds a hint after the path, which was already echoed back. It goes out as JSON. Every UI place that shows a `detail` uses `textContent` (review.html:192, project.html:108) or autoescaped Jinja (error.html, factory_result.html), so nothing renders it as HTML. The SQL is still parameterized.
- app.py:541 `run_task` 404 `no task #{task_id}`: `task_id` is an `int` path param and the query stays parameterized. The §4.5 middleware (app.py:71–76) checks Host and `X-Requested-By` before the route runs, so an unknown task still needs the header.
- app.py:547–553 factory 409s: `factory_state` (app.py:132–143) can only return `ready`, `uncommitted`, or `none`. The two new branches therefore refuse every non-`ready` state, as the old `!= "ready"` did, so the "factory committed" gate is intact. The added detail is the fixed `COMMIT_HINT` text plus the branch name, which was already echoed back.
- §4.3: `run_env` (app.py:492), the `authMethod: claude.ai` check (app.py:504), and the spawn command (no `--bare`) are untouched.
- §4.4: `ALLOWED_TOOLS` and `DISALLOWED_TOOLS` (app.py:436–444) are unchanged and match the doc. Neither `fctl run`, `fctl task`, `fctl approve`, nor `fctl rework` is allowed, so agents still can't start runs, including through `task add --run`. No git write command is allowed.
- §4.5: the CLI still sends `X-Requested-By: fctl` (cli.py:34), defaults to `127.0.0.1`, and `serve` still binds `127.0.0.1` (cli.py:269). The diff doesn't touch markdown, Jinja, code paths, or the 413 limit.
- Subprocesses: the diff adds none. `run next` reuses `main_checkout()`, which passes an argument list. There's no `shell=True` or `os.system`.
- `fctl setup` (cli.py:86) writes only to the fixed paths `Path.home()/.claude/skills/{factory-connect,factory-submit}/SKILL.md`, sends no HTTP, and logs nothing secret. `run` checks the target with `isdecimal()` and converts it to `int` before building the URL (cli.py:139).
- tests/conftest.py points `HOME` at a temp dir. I checked this by running tests/test_cli.py, test_runs.py, and test_projects.py with `HOME` set to an empty scratch dir: 170 passed, and the dir stayed empty.

## Nits (non-blocking)
- src/claude_factories/app.py:548–553 — the factory check now lists the failing states (`uncommitted`, `none`) instead of requiring `ready`. That covers every state today, but if `factory_state` ever gains a new state, runs would start without a committed factory. Fix (optional): `if state != "ready":` and choose the message inside it.
- src/claude_factories/global_skills/factory-connect/SKILL.md:21–23 — the example quotes `--test-cmd "<test command>"` in double quotes. A repo-supplied command containing `$(…)` or backticks would then run when `fctl connect` is called. The user approves the call by hand, and the skill now shows the command first. Fix (optional): tell Claude to single-quote the values.
