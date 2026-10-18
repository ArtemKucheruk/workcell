VERDICT: PASS

Round 1 findings are fixed and checked live: the unconnected-repo 404 now names the next command, `fctl run 999` says `no task #999`, both factory 409s name the next step, and the `Added` line comes before the refused-run error when stdout is a pipe.

## Nits (non-blocking)
- src/claude_factories/app.py:610 (run_next, project lookup) — `POST /api/projects/999/run-next` returns a bare `{"detail": "Not Found"}`. fctl never sends an unknown project id, so it's not reachable from the CLI. — Pass a detail such as `f"no project #{project_id}"`. Pre-existing from 012, so it can wait.
- src/claude_factories/app.py:551 (run_task, uncommitted factory 409) — the message reads `factory isn't committed on main: on main, run git add …`, so "on main" appears twice. — Drop the `on {branch}, ` prefix so it reads `…on main: run git add …`.
- Board page (014's Run next button, out of scope): `Run next ▶` stayed disabled on /projects/1 while the factory was ready and Backlog held a card, and nothing was running. Not counted here. Also, the favicon 404 from round 1 is still there.

## Checked live
- `fctl setup`: exit 0, prints the two `Wrote <HOME>/.claude/skills/<name>/SKILL.md` lines, and a second run is clean. With a regular file where `skills/` should be: `fctl: can't write …/skills/factory-connect/SKILL.md: Not a directory`, exit 1, no traceback.
- `fctl connect --workspace personal --test-cmd "pytest -q"` → `Connected repo (personal) → http://127.0.0.1:<port>/projects/1`.
- Unconnected repo: `fctl task add "Z" --run` and `fctl submit --new` → `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit 1. The `no project at` prefix still matches the factory-submit skill.
- `fctl task add "T1"` → `Added #1 to repo → …/projects/1`, exit 0. `fctl task add "T2" --run` → `Added #2 …` then `Run #1 on #2 → …/tasks/2`, exit 0.
- `fctl run 999` → `fctl: 404 no task #999`, exit 1. `fctl run abc` and `fctl run` → `usage: fctl run …`, exit 2. `fctl run --help` lists the target.
- While a run is active, `fctl run 1`, `fctl run next` and `fctl task add "T3" --run` → `fctl: 409 run #1 active`, exit 1. The T3 card stays in Backlog, and its `Added` line prints first when piped.
- Factory states: uncommitted on disk → `fctl: 409 factory isn't committed on main: on main, run git add .claude/skills/factory .claude/agents && git commit -m "Add factory"`. No factory → `fctl: 409 factory isn't committed on main: Create factory on the project board, then commit it on main`. Both via `run` and `run next`, exit 1.
- `fctl run next` in a ready repo → `Run #3 on #1 → …/tasks/1`, exit 0. A second `run next` with an empty Backlog → `fctl: 404 backlog is empty`, exit 1.
- `fctl run next` outside a repo → `fctl: not inside a git repository: <cwd>`, exit 1. Server down → `fctl: can't reach http://127.0.0.1:1 — is "fctl serve" running?`, exit 1.
- `fctl submit --new --title "Add new.txt"` → `Review #6: 1 file, +1 −0 → …/tasks/6/review`, exit 0. `fctl submit 6` → `Round 2 of #6: 1 file, +2 −0 → …/tasks/6/review?round=2`. The real index stays clean.
- Curl: `GET /api/projects?path=/nope` → 404 with the new detail. `POST /api/tasks/999/run` → 404 `{"detail":"no task #999"}`.
- Browser (headless): `/` → workspace `personal`, which lists 3 projects (`repo` Factory ready, `repoB` uncommitted, `repoC` none), with the CLI-created tasks counted in Backlog/In progress. `/projects/1` shows `#1 T1` in Backlog and `#2 T2`, `#3 T3` in In progress. No console errors besides the favicon.

Method: built from W's working tree (`W/.venv/bin/fctl serve` on a free port, FCTL_HOME in a temp dir, `HOME` set to a temp dir for `setup`). The fake `claude` (a shell script in a temp bin dir, first on PATH) answered `auth status` with claude.ai JSON and slept 25s for anything else. No real claude ran. The server and browser are closed. Temp repos live under /private/tmp/claude-501/ux015-ha5b.
