VERDICT: CHANGES

- src/claude_factories/cli.py:114-116 (project_at, used by task_add, run next, submit --new) — an unconnected repo prints `fctl: 404 no project at /…/repo` and stops. Nothing says what to do next, and `task add --run` and `run next` are new paths that hit it. Checked live: `fctl task add "Z" --run` and `fctl submit --new` in an unconnected repo both print exactly that, exit 1. — Give project_at a 404 hint so the error reads `fctl: this repo isn't connected; run fctl connect --workspace <name> here` (or similar, naming the next command), e.g. an optional hint argument on api() that _fail uses for 404.

- src/claude_factories/app.py:538 (run_task, via one_or_404 without a detail; root cause for all callers of one_or_404 that pass no detail) — `fctl run 999` prints `fctl: 404 Not Found`. It does not name the task. Checked live. — Pass detail=f"no task #{task_id}" in run_task's lookup. Same change applies to the other one_or_404 calls that give no detail, e.g. app.py:375, 748, 968.

- src/claude_factories/app.py:548 (run_task, 409 when the factory isn't committed) — the CLI user gets `fctl: 409 factory isn't committed on main` with no next step. The docs (§3.2 step 4) say to commit the factory, and the message doesn't say so. Not exercised live (needs an uncommitted factory); found by reading the code. — Add the commit command to the detail, e.g. "factory isn't committed on main: commit .claude/skills/factory and .claude/agents there, then retry".

## What passed (checked live)
- `fctl setup`: exit 0, prints the two `Wrote …/SKILL.md` lines, idempotent (shipped files byte-identical after a second run). A regular file in the skills path → `fctl: can't write …/skills/factory-connect/SKILL.md: Not a directory`, exit 1, no traceback.
- `fctl connect` → `Connected repo (personal) → http://127.0.0.1:<port>/projects/1`. Re-running works.
- `fctl task add "T"` → `Added #1 to repo → …/projects/1`. The card shows in Backlog on the board in the browser.
- `fctl task add "T" --run` and `fctl run <id>` → `Run #1 on #1 → …/tasks/1`. `fctl run next` → `Run #2 on #2 → …`. The card moves to In progress in the browser.
- Active-run refusal: `run 1`, `run next`, `task add --run` → `fctl: 409 run #1 active`, exit 1.
- Usage errors: `fctl run` and `fctl run abc` → exit 2, `usage: fctl run …`, no request.
- `fctl run next` with an empty backlog → `fctl: 404 backlog is empty`, exit 1.
- `fctl run next` outside a repo → `fctl: not inside a git repository: <cwd>`, exit 1. `fctl run 1` outside a repo still starts the run.
- `fctl submit --new --title T <<'EOF'` → `Review #5: 2 files, +2 −0 → …/tasks/5/review`, exit 0. `fctl submit 1 <<'EOF'` → `Round 1 of #1: … → …/tasks/1/review?round=1`. Both match §7.4's format.
- `fctl submit` with no args → usage error, exit 2.
- Server down → `fctl: can't reach http://127.0.0.1:1 — is "fctl serve" running?`, exit 1, for both `run` and `run next`.
- Browser: the workspace list → the project board (Backlog 1, In progress 3) shows the CLI-created tasks. Console: only a favicon 404 from the app.

## Nits (non-blocking)
- src/claude_factories/cli.py:119-130 (task_add) — when the run is refused, the `Added #…` line goes to stdout and the 409 to stderr. On a terminal they show in order. When piped, stdout is buffered, so the 409 can appear first. Harmless, but flush stdout before the run POST if you want ordering to hold everywhere.
- Browser console shows a 404 for /favicon.ico from the app. Not in this job's scope.
- The board's "Run next ▶" button is shown disabled while the factory is ready and the backlog is not empty. That's 014's Run button, so I didn't count it here.

## Method note
Ran the W build of fctl (`W/.venv/bin/fctl`) from a temp git repo (T/repo, with the factory committed on main) instead of from inside W. Running inside W would have connected the real repo and created worktrees in it. Fake `claude` first on PATH (exit 0 for `auth status` with claude.ai JSON; sleeps 25s for `-p`). `HOME` was set to a temp dir for `setup`, so the real ~/.claude was not touched. No real claude was run. Server and browser are closed.
