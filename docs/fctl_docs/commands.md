# Commands

Every `fctl` command, grouped by who uses it. Each entry: synopsis, what it calls, stdin, output,
the errors you will meet, and who runs it. Errors every command can print (`can't reach`, `403`,
`not inside a git repository`) are in [troubleshooting.md](troubleshooting.md). The exhaustive
reference is [`src/workcell/fctl.md`](../../src/workcell/fctl.md).

Exit codes for all commands: `0` success; `1` failure, one `fctl: <reason>` line on stderr
(`fctl: <status> <detail>` when the app refused the call); `2` usage error from argparse (unknown
command, bad or missing argument, refused flag combination). `fctl serve` adds `3`: the server
couldn't start.

**Allowed in a run** marks the 9 commands on a factory run's Bash allowlist. Everything else is
denied there.

| Group | Commands |
|---|---|
| [Read](#read) | `show`, `diff`, `round`, `context` |
| [Post records (agents)](#post-records-agents) | `spec`, `submit`, `verdict`, `comment`, `decide`, `stage` |
| [The user's actions](#the-users-actions) | `task add`, `task block`, `task unblock`, `task retry`, `task delete`, `automation run`, `run`, `rework`, `approve` |
| [Projects and bundles](#projects-and-bundles) | `connect`, `context set`, `import-factory`, `export`, `import` |
| [Running the app](#running-the-app) | `serve`, `setup`, `seed`, `service install\|uninstall\|start\|stop\|restart\|reload\|status\|logs` |

---

## Read

### fctl show

```
fctl show <id> [--round N | --feedback]
```

Prints a task as markdown. `GET /api/tasks/{id}/context`. **Allowed in a run.**

- No flag: project context, task heading and status, description, spec, every round with build
  notes, verdicts, comments, and decisions. Layout: [concepts.md § What fctl show prints](concepts.md#what-fctl-show-prints).
- `--round N`: the heading, status, description, spec, and only round N. No project context.
- `--feedback`: the heading, status, description, spec, and the user's latest Request changes
  under `## Feedback on round N`, with the user's line comments. No project context, no rounds.
- Errors: `404 Not Found` (unknown task), `404 #12 has no round 3`, `404 #12 has no feedback`.
  `--round` with `--feedback`: exit `2`.
- Who: every agent. Start every role with it.

```sh
fctl show 12
fctl show 12 --round 1
fctl show 12 --feedback
```

### fctl diff

```
fctl diff <id> [--round N]
```

Prints a round's patch as `git diff` output, file by file. Default: the latest round.
`GET /api/tasks/{id}/rounds/{n}/diff`. **Allowed in a run.**

- Errors: `404 #12 has no rounds`, `404 #12 has no round 3`.
- Who: reviewers, approver; the builder to see what it sent.

```sh
fctl diff 12
fctl diff 12 --round 1
```

### fctl round

```
fctl round <id>
```

Prints the latest round's four verdict slots and how many have posted. `GET /api/tasks/{id}`.
**Allowed in a run.**

```
round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)
```

- Errors: `fctl: #12 has no rounds` (exit `1`).
- Who: the orchestrator, to wait for all reviewers and to check a round was submitted.

### fctl context

```
fctl context
```

Prints the current repo's pinned project context exactly as stored (nothing for an empty one).
Needs the repo. `GET /api/projects?path=…`, then `GET /api/projects/{id}/context`. Context cards
are not included; the full `fctl show` prints those.

- Errors: `404 no project at <path>; in that repo, run fctl connect --workspace <name>, or if the checkout moved, change the path on the project's Settings page`.
- Who: the user's session, before `fctl context set`.

---

## Post records (agents)

### fctl spec

```
fctl spec <id> < .fctl/spec.md
```

Saves the task's spec from stdin, replacing it whole. `PATCH /api/tasks/{id}` `spec_md`.
**Allowed in a run.**

- Stdin: the spec markdown. Blank is refused.
- Output: `Spec saved on #12`
- Errors: `fctl: spec is empty; pass it on stdin`; `404 Not Found`.
- Who: the spec-writer (or the template's spec agent).

### fctl submit

```
fctl submit <id> < .fctl/build.md          # next round of task <id>; stdin: build notes
fctl submit --new --title "T" <<'EOF'      # new task straight in Review; stdin: description
…
EOF
```

Captures the **current directory's** tree, tracked and untracked files, `.gitignore` respected,
against `HEAD`, through a temp index (the real index is untouched), and sends it as a round.
Needs a git repo. **Allowed in a run.**

- `<id>`: `POST /api/tasks/{id}/rounds`. On a standalone task it also moves the task back to
  `review · human_review`; on a factory task status doesn't change.
- `--new --title T`: `POST /api/projects/{id}/tasks` with `submit`; the task starts in
  `review · human_review` with round 1. Needs the repo to be connected.
- Stdin: build notes (`<id>`) or the description (`--new`), sent unchanged, may be empty.
- Output:
  ```
  Round 2 of #12: 4 files, +126 −9 → http://127.0.0.1:4545/tasks/12/review?round=2
  Review #17: 3 files, +38 −2 → http://127.0.0.1:4545/tasks/17/review
  ```
- Errors:
  - `fctl submit: error: give a task id, or --new with --title` (exit `2`): neither form, both,
    or `--title` without `--new`.
  - `fctl: HEAD has no commit yet; commit once before submitting`.
  - `fctl: git <step> failed: <git's error>`.
  - `422 no changes to submit`, `413 patch over 5 MB`: nothing is created.
  - `404 Not Found` (unknown id); `--new`: `404 no project at <path>; …`,
    `422 title must not be blank`.
- Who: the builder, once per round, from its worktree; `/factory-submit` in the user's session.

### fctl verdict

```
fctl verdict <id> security|ux|ui|code PASS|CHANGES < .fctl/verdict-<slot>.md
```

Posts one reviewer's verdict on the **latest** round, replacing any earlier one from that slot.
`PUT /api/tasks/{id}/rounds/latest/verdicts/{reviewer}`. **Allowed in a run.**

- Stdin: the findings markdown; may be empty.
- Output: `Round 2 of #12: security=PASS (3/4)`
- Errors: `404 #12 has no rounds`. A slot or verdict not in the list: exit `2`.
- Who: each reviewer, exactly once per round, in its own slot.

### fctl comment

```
fctl comment <id> security|ux|ui|code --path P --line L <<'EOF'
<comment>
EOF
```

Posts a line comment on the latest round, on line `L` (from 1) of file `P` in the new version.
`POST /api/tasks/{id}/comments`. **Allowed in a run.**

- `--path`: a file in the round's diff, spelled as the diff names it (`b/` path without the
  prefix). `--line`: the line number in the new file.
- Stdin: the comment; blank is refused. A short heredoc is fine.
- Output: `Comment #5 on #12 app/auth.py:44`
- Errors: `422 body_md must not be blank`, `422 app/x.py is not in round 2`,
  `404 #12 has no rounds`; a `--line` under 1 is a `422` with JSON detail. A slot not in the list,
  or a missing `--path`/`--line`: exit `2`.
- Who: reviewers, optional, in addition to their verdict.

### fctl decide

```
fctl decide <id> APPROVE|ESCALATE < .fctl/decision.md
```

Posts the approver's decision on the latest round. Every call adds one; the latest counts. It
does **not** move the task. `POST /api/tasks/{id}/decision`. **Allowed in a run.**

- Stdin: the summary markdown; may be empty.
- Output: `Decision #7 on #12: APPROVE`
- Errors: `404 #12 has no rounds`. A decision not in the list: exit `2`.
- Who: the approver, once.

### fctl stage

```
fctl stage <id> spec|build|agent_review|approval|rework|human_review|escalated
```

Moves a task to a stage, which sets its status: `spec`, `build`, `agent_review`, `approval`,
`rework` → `in_progress`; `human_review`, `escalated` → `review`. `PATCH /api/tasks/{id}` `stage`.
**Allowed in a run.**

- Output: `#12: in_progress · agent_review`
- Errors: a stage not in the list: exit `2`; `404 Not Found`.
- Who: **only the orchestrator.** No other agent runs it, and the orchestrator never sets
  `rework` itself (the user's Request changes does).

---

## The user's actions

The commands here act for the user. None is on a run's allowlist. In an interactive session, run
them when the user asks for that action; `approve` and `rework` are the user's review decisions.

### fctl task add

```
fctl task add "title" [--description TEXT | --description -] [--blocked-by IDS] [--run]
```

Adds a task to the bottom of the current repo's Backlog. Needs the repo.
`POST /api/projects/{id}/tasks` with `title`, `description_md`, `blocked_by`; with `--run` then
`POST /api/tasks/{id}/run`.

- `--description TEXT`: markdown description. `--description -` reads it from stdin (a literal
  `-` must be piped: `printf '%s\n' - | fctl task add "T" --description -`). Blank is refused.
- `--blocked-by 12,14`: tasks of the same project it waits on, comma-separated, no spaces.
- `--run`: then start a run, as `fctl run <id>` (Auto account).
- Output:
  ```
  Added #12 to api-server → http://127.0.0.1:4545/projects/3
  Run #41 on #12 as b@y → http://127.0.0.1:4545/tasks/12      ← with --run
  ```
- Errors: `fctl: description is empty; pass it as text, or on stdin with --description -`;
  `422 title must not be blank`; `422 no task #99`;
  `422 #30 is in another project; a task waits only on tasks of its own project`; a bad
  `--blocked-by` such as `12,x`: exit `2`; `404 no project at <path>; …`. With `--run`, any
  [fctl run](#fctl-run) refusal: the task stays in Backlog, the `Added` line is already printed.

```sh
fctl task add "Rate-limit login endpoint" --description - <<'EOF'
## Why
Max 5 failed logins per minute per IP.
EOF
```

### fctl task block

```
fctl task block <id> --by <id>
```

Makes task `<id>` wait on task `--by`. Idempotent. `PUT /api/tasks/{id}/blocked-by/{blocker}`.
Works anywhere.

- Output: every blocker with its status: `#15 blocked by #12 (backlog), #14 (done)`
- Errors: `404 Task #15 not found`, `422 #15 can't wait on itself`, `422 no task #99`,
  `422 #30 is in another project; …`,
  `422 cycle: #15 waits on #12, which waits on #14, which waits on #15`.

### fctl task unblock

```
fctl task unblock <id> --by <id>
```

Removes one link. `DELETE /api/tasks/{id}/blocked-by/{blocker}`. Works anywhere.

- Output: the blockers left, or `#15 has no blockers`.
- Errors: `404 Task #15 not found`, `404 #15 is not blocked by #12`.

### fctl task retry

```
fctl task retry <id> [--account <id|email>]
```

The user's **Retry** on a task whose latest run failed or was stopped. Reads the latest run with
`GET /api/tasks/{id}`, then `POST /api/tasks/{id}/run` as [fctl run](#fctl-run). Works anywhere.

- Output: `Run #42 on #12 as b@y → http://127.0.0.1:4545/tasks/12`
- Errors: `fctl: #12 never ran; use fctl run 12`, `fctl: run #41 is running on #12; wait for it or stop it`
  (nothing posted), `404 Task #99 not found`, and every [fctl run](#fctl-run) refusal.

### fctl task delete

```
fctl task delete <id> [--yes]
```

Deletes a task and its runs, rounds, verdicts, comments, decisions, and transcript records from the
app, after a `Delete? [y/N]` prompt. `DELETE /api/tasks/{id}`. Its worktree, branch, and run logs stay
on disk. Works anywhere.

- Output: `Deleted #14 Export CSV`
- Errors: `fctl: not a terminal; pass --yes to delete #14 without asking`, `404 Task #14 not found`.

### fctl automation run

```
fctl automation run <id> [--account <id|email>]
```

**Run now** on an automation: its skill, headless, in a fresh worktree from the default branch, with
no board task. `POST /api/factories/{id}/run`. Works anywhere.

- Output: `Run #43 of automation #7 as b@y in .claude/worktrees/automation-security-audit-1a2b3c4d → http://127.0.0.1:4545/agents`
- Errors: `404 Factory #99 not found`, `409 Review loop is a workflow; run it on a task from the board`,
  `409 automation <name> isn't committed on main: …`, and [fctl run](#fctl-run)'s worktree, account,
  and run-cap refusals.

### fctl run

```
fctl run <id> [--account <id|email>]
fctl run next [--module <name>]
```

Starts a factory run: headless `/factory <id>` in the task's worktree. `POST /api/tasks/{id}/run`
(body `{"account_id": N}` with `--account`), or for `next` `POST /api/projects/{id}/run-next`
(needs the repo; the top ready Backlog task, skipping blocked ones; always Auto).

- `--account`: an account id, or an email matched exactly ignoring case. The run uses it even
  when near its limits. Not with `next` (exit `2`).
- `--module`: with `next` only, the top ready task of that module's Backlog, body
  `{"module_id": N}`. The name is matched trimmed, in any case. Not with an id (exit `2`).

**Work on a module.** When the user says "work on frontend", run `fctl run next --module frontend`
in the repo. To see a project's modules, open its Modules page (`/projects/{id}/modules`), or guess:
an unknown name fails with `no module nope in api; known: backend, frontend` and starts nothing.
- Output: `Run #41 on #12 as b@y → http://127.0.0.1:4545/tasks/12`
- The first run makes the worktree `.claude/worktrees/<id>-<slug>` on `factory/<id>-<slug>` with
  worktrunk; every run copies the main checkout's ignored files in.
- Errors (all `409` unless noted):
  - `404 no task #12`
  - `run #41 is already running on #12; wait for it or stop it`
  - `2 runs active (#41 on #12, #42 on #14); the limit is 2. Wait, stop one, or raise it in Settings`
  - `#12 is in review`, `#12 is done`
  - `#15 is blocked by #12, #14; finish those first or remove the dependency`
  - `factory isn't committed on main: …`, `this repo runs the file-based /factory loop: …` (the
    message names the fix)
  - `worktree <path> is missing`; `wt (worktrunk) isn't installed: brew install worktrunk, then run again`;
    `wt switch failed: …`, `wt step copy-ignored failed: …`, `wt switch timed out`,
    `wt step copy-ignored timed out`, `wt put the worktree at <path>, expected <path>`
  - `conf/.env.local is ignored in the main checkout but not on main, so it was left out of the worktree: commit its .gitignore line on main, then run again`
  - `not on subscription auth` + `Sign in to a Claude account, or make one active, under Settings → Claude accounts, then run again.`
  - `all accounts near their limits: a@x 5h 92% (resets 14:10), …`
  - `Claude account b@y isn't logged in to claude.ai; log it in under Settings → Claude accounts, or pick another`
  - `422 no Claude account #99`; `fctl: no Claude account b@y` (no such email)
  - `500 can't start claude: <reason>`
  - `next` only: `404 backlog is empty`, `409 all backlog tasks are blocked: #15 waits on #12, #14`,
    `404 no project at <path>; …`
  - `next --module` only: `404 module frontend has no backlog tasks`,
    `409 all backlog tasks in frontend are blocked: #15 waits on #12, #14`,
    `fctl: no module nope in api; known: backend, frontend` (nothing posted)
  - `--module` without `next`: `fctl run: error: --module only works with next` (exit `2`)
  - not a number or `next`: `fctl run: error: target must be a task id or next, not 'abc'` (exit `2`)

### fctl rework

```
fctl rework <id> "note"
```

The user's **Request changes** on a task in review. `POST /api/tasks/{id}/request-changes`. Moves
it to `in_progress · rework`; for a factory task the app then starts a rework run (Auto), for a
standalone task it only records the note.

- Output: `#12: in_progress · rework`
- Errors: `422 body_md must not be blank`, `409 #12 is not in review`, `404 #12 has no rounds`.
  A factory task is refused before anything is recorded while its run is running or the run cap
  is full. A rework run refused after the note is recorded (for example `not on subscription auth`)
  keeps the note and the move: fix the cause, then `fctl run <id>`.

### fctl approve

```
fctl approve <id>
```

The user's **Approve** on a task in review: moves it to `done` and prints the git commands for the
user to commit. The app runs no git. `POST /api/tasks/{id}/approve`.

- Output (factory task):
  ```
  #12: done
  cd ~/code/api-server/.claude/worktrees/12-rate-limit-login
  git add -A && git commit -m 'Rate-limit login endpoint'
  git push -u origin factory/12-rate-limit-login     # then open a PR, or merge locally
  cd ~/code/api-server && wt remove factory/12-rate-limit-login
  ```
  A standalone task prints only `#17: done` and the commit line.
- Errors: `409 #12 is not in review`, `404 #12 has no rounds`.
- The printed git commands are for the user. Don't run them unless the user asks.

---

## Projects and bundles

### fctl connect

```
fctl connect --workspace W [--test-cmd C]
```

Registers the current repo (its main checkout) as a project, or updates it. Sends the path, the
folder name, the `origin` URL, and the default branch. `POST /api/projects/connect`; then, when
`factory/board.json` or `factory/backlog.md` is a file, `POST /api/projects/{id}/import-factory`.

- `--workspace`: required; a new name creates the workspace. `--test-cmd`: the command that runs
  the whole suite (factory runs execute it; Create factory refuses a project without one).
  Leaving it out on a later connect keeps the stored one. Quote both for the shell.
- Output: `Connected api-server (personal) → http://127.0.0.1:4545/projects/3`, and with factory
  files `Synced factory/: 2 new, 1 updated, 3 skipped`.
- Errors: `422 workspace must not be blank`;
  `can't tell the default branch: no origin/HEAD and HEAD is detached`; a refused sync prints the
  `Connected` line first, then the sync's error (the project stays connected); missing
  `--workspace`: exit `2`.
- Who: `/factory-connect`, after finding the test command and showing it to the user.

### fctl context set

```
fctl context set <<'EOF'
<markdown>
EOF
```

Replaces the current repo's pinned project context from stdin. `PUT /api/projects/{id}/context`.

- Output: `Context saved on api-server (1234 bytes)`
- Errors: `fctl: context is empty; pass it on stdin` (blank is refused; clear it on the Context
  page instead), `413 context over 16 KB`, `404 no project at <path>; …`.

### fctl import-factory

```
fctl import-factory [--job ID]
```

Imports the repo's legacy file-based factory: `factory/board.json` jobs and `factory/jobs/<id>/`
(spec, rounds, diffs, reviews, decisions, feedback, transcript copies) as tasks keyed
`factory:<job id>`, then `factory/backlog.md` lines board.json doesn't list.
`POST /api/projects/{id}/import-factory`. Writes nothing to the repo. A rerun updates in place.

- `--job ID`: only that board.json job; backlog.md isn't read.
- Output: `Imported 001-a → #12 (new, 2 rounds, 3 transcripts)` per job,
  `Skipped 2 lines in factory/backlog.md`, or `No jobs in factory/`.
- Errors: `404 no factory/board.json or factory/backlog.md in <path>`,
  `404 no job <id> in factory/board.json`, `422 <job or problem>` (nothing imported),
  `413 … over 5 MB`, `409 factory:<id> is imported in project #<n>`.
- Not a way to add new work: add tasks with `fctl task add`.

### fctl export

```
fctl export <id> [-o|--output FILE] [--transcripts]
```

Writes a task as a zip bundle another app can import. `GET /api/tasks/{id}/export`. Works
anywhere. Default file `task-<id>.zip`; an existing file is overwritten.

- `--transcripts`: also include the agents' Claude Code transcripts. They can hold paths, env, and
  secrets; say so before the user shares the bundle.
- Output: `Exported #12 → task-12.zip`
- Errors: `404 Task #12 not found`, `fctl: can't write <file>: <reason>`.

### fctl import

```
fctl import FILE
```

Imports a bundle from `fctl export` into the current repo's project. A re-import updates the task
it made. `POST /api/projects/{id}/import`.

- Output: `Imported #12 Rate-limit login endpoint (new, backlog, 2 rounds, 0 transcripts)`
- Errors: `fctl: can't read <file>: <reason>`, `413 bundle over 50 MB` (and other size limits),
  `422 <detail>` (bad zip or layout; nothing imported), `409 <key> is imported in project #<n>`,
  `409 run #<id> active`, `404 no project at <path>; …`.

---

## Running the app

Operator commands. No agent in a run uses them, and an interactive session doesn't start or stop
the user's app on its own: ask first. Full details in
[`fctl.md`](../../src/workcell/fctl.md).

| Command | What it does | Notes |
|---|---|---|
| `fctl serve [--host 127.0.0.1] [--port 4545]` | Runs the backend in the foreground. Prints `Workcell → http://127.0.0.1:4545 (data: …)`. | Exit `3` if it can't bind. Stopping it stops every run. `--host 0.0.0.0` is only for the container. |
| `fctl setup` | Writes `~/.claude/skills/factory-connect/SKILL.md`, `factory-submit/SKILL.md`, and `fctl/SKILL.md`. No HTTP. | Always `~/.claude`, even with `CLAUDE_CONFIG_DIR`. |
| `fctl seed` | Fills an **empty** `FCTL_HOME` with demo workspaces, projects, tasks, and runs. No HTTP. | `FCTL_HOME has data; seed an empty one`. Always with a temp `FCTL_HOME`. |
| `fctl service install [--backend-port 4545] [--frontend-port 3000]` | Installs the backend and frontend as launchd / `systemd --user` services. | Needs an editable install. |
| `fctl service uninstall [--force]` | Stops and removes both; logs stay. | Refuses while runs are active unless `--force`. |
| `fctl service start [backend\|frontend]` | Starts both, or one. | Refuses if another process holds the port. |
| `fctl service stop [backend\|frontend] [--force]` | Stops both, or one. | Stopping the backend stops runs: refused while active unless `--force`. |
| `fctl service restart [backend\|frontend] [--force]` | Restarts both, or one. | Same active-runs check for the backend. |
| `fctl service reload [--force]` | After a pull or merge: `npm ci` if the lockfile changed, build the frontend, restart both. | Prints the `uv tool install --editable --reinstall …` line when Python deps changed. |
| `fctl service status` | Each service's pid, port, uptime, URL, served commit (`stale` vs `main`), and the active runs. | |
| `fctl service logs [backend\|frontend] [-f\|--follow] [-n 50]` | Tails `FCTL_HOME/logs/*.log`; `-f` keeps following. | |

`fctl service` refuses on platforms other than macOS and Linux and inside Docker
(`FCTL_IN_DOCKER=1`), and every subcommand but `install` refuses with
`not installed; run fctl service install` when there's no `service.json`.
