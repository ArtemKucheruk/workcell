---
name: fctl
description: How to work with Workcell through its fctl CLI. Use whenever the user mentions fctl, Workcell, the factory, the board, the backlog, a factory task or run (e.g. "#12", "run 12", "what's in review"), or asks to connect a repo, add/list/inspect tasks, start or follow a run, read a round's diff or verdicts, approve or request changes, block/unblock tasks, set project context, export/import a task, or run the app (fctl serve, fctl service).
---

# fctl: working with Workcell

Workcell is a local app that runs a software factory on a repo's tasks: spec → build →
four agent reviews → approver → the user's review. All of its state (workspaces, projects, tasks,
specs, rounds, verdicts, decisions, runs) lives in the app's database behind its backend. `fctl` is
the command line for it: most commands are a small HTTP client of the backend at `FCTL_URL`
(default `http://127.0.0.1:4545`). Markdown goes in on stdin, comes out on stdout.

`fctl --help` lists the commands; `fctl <command> --help` prints one command's flags.

## Rules

1. **Read and write factory state only through `fctl`.** Never write `factory/board.json` or
   `factory/backlog.md` to add work, never open `factory.db`, never send writes to the API with
   curl. The only exception: read-only `GET`s for listing, below, since `fctl` has no list command.
2. **The user's decisions stay the user's.** `fctl run` (spends their Claude usage),
   `fctl approve`, and `fctl rework` (their review verdicts): run them when the user asks for
   that action, not on your own initiative. Same for the git commands `fctl approve` prints.
3. **Don't post agent records into a factory task.** `fctl spec`, `verdict`, `comment`, `decide`,
   `stage`, and `submit <id>` on a factory task belong to the factory's agents. Use them only when
   the user explicitly asks (for example, to post a spec they wrote).
4. **Never write git history** for a submit: no `git add`, `commit`, or `stash`. `fctl submit`
   captures the tree through a temp index.
5. **`can't reach … — is "fctl serve" running?` → ask the user to start the app.** Don't start
   `fctl serve` or a service yourself.
6. **Never quote secrets** from `.env` or other ignored files into anything you post.
7. **Quote heredocs** (`<<'EOF'`) so the shell expands nothing, and make sure no line of the text
   is exactly `EOF`.

## Find your bearings

```sh
U="${FCTL_URL:-http://127.0.0.1:4545}"

fctl context                    # in a repo: prints its pinned context; 404 no project at … → not connected

# this repo's project (id, name, default_branch, factory state); works from a worktree too
curl -s -G "$U/api/projects" \
  --data-urlencode "path=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"

# every workspace with its projects: id, name, and counts in review / running / escalated
curl -s "$U/api/pages/sidebar"

# a project's tasks, not done, one per line
curl -s "$U/api/projects/<project-id>/tasks" | python3 -c '
import json, sys
for t in json.load(sys.stdin):
    if t["status"] != "done":
        waits = ", ".join("#%s" % b["id"] for b in t["blocked_by"] if b["status"] != "done")
        blocked = " (blocked by %s)" % waits if t["blocked"] else ""
        print("#%s %s %s %s%s" % (t["id"], t["status"], t["stage"] or "", t["title"], blocked))'

fctl show 12                    # one task in full
fctl round 12                   # its latest round's verdicts
```

A project's `factory` field says whether runs can start: `ready` (factory committed on the default
branch), `uncommitted` (written but not committed: commit it), `none` (no factory: **Create
factory** on the project's Settings page), `legacy` (the old file-based `/factory` loop).

The links `fctl` prints start with `FCTL_URL`, which answers only `/api/`. The pages are on the
frontend: open the same path on `http://127.0.0.1:3000`.

## The model in brief

- **Workspace** → **project** (one git repo, by its main checkout path, with a test command and a
  project context) → **tasks**. Task ids are global; commands taking an id work from any directory.
- **Status** is the board column: `backlog`, `in_progress`, `review`, `done`. **Stage** is the loop
  step: `spec`, `build`, `agent_review`, `approval`, `rework` (all `in_progress`), `human_review`,
  `escalated` (both `review`). `fctl show` prints `Status: in_progress · agent_review`.
- **Factory task** (made by `fctl task add` or the board): runs in its own worktree
  `<repo>/.claude/worktrees/<id>-<slug>` on branch `factory/<id>-<slug>`. **Submitted task** (made
  by `fctl submit --new`): starts in Review, no worktree, no agents.
- **Round**: one submitted snapshot (patch + build notes), numbered from 1. Each round has four
  verdict slots, `security`, `ux`, `ui`, `code`: `pending`, `PASS`, or `CHANGES`.
- **Decisions** on the latest round: the approver agent's `APPROVE`/`ESCALATE`; the user's
  `APPROVE` (`fctl approve`) and `CHANGES_REQUESTED` (`fctl rework`). **Feedback** is the user's
  latest change request; `fctl show <id> --feedback` prints it.
- **Blockers**: a task can wait on tasks of the same project; it can't run until they're done.
- **Runs**: the app spawns headless `claude -p "/factory <id>"` in the worktree. One per task, at
  most `max_concurrent_runs` (default 2) overall. Each uses a Claude account: Auto, or
  `--account`. A run's agents may use only `fctl show/diff/spec/submit/verdict/comment/decide/stage/round`,
  `git status/diff`, and the test command.

The loop: spec-writer posts a spec → builder submits round n → four reviewers post verdicts →
any CHANGES and rounds left (2 per run) → round n+1 → approver decides → `human_review` on
APPROVE, else `escalated` → the user approves (`done`) or requests changes (a rework run).

## Recipes

### Connect a repo

Use the `/factory-connect <workspace>` skill if it's installed. By hand, from inside the repo:

```sh
fctl connect --workspace "personal" --test-cmd "uv run pytest -q"
# Connected api-server (personal) → http://127.0.0.1:4545/projects/3
```

The test command is the one command that runs the whole suite (what CI runs); factory runs execute
it. Show it to the user, with the file you found it in, before connecting. Rerunning updates the
project; leaving `--test-cmd` out keeps the stored one.

### Add a task

From inside the connected repo. Write the description as a good request: goal, the docs and
sections it relies on, scope, out of scope, and how it should be tested. The spec-writer turns it
into a spec.

```sh
fctl task add "Rate-limit login endpoint" --description - <<'EOF'
## Goal
Max 5 failed logins per minute per IP; the 6th gets 429.

## Scope
- app/auth.py login handler (docs/api.md § Auth)
- a test per behavior

## Out of scope
Per-user lockout.
EOF
# Added #12 to api-server → http://127.0.0.1:4545/projects/3
```

- `--blocked-by 12,14`: it waits on those tasks (same project, comma-separated, no spaces).
- `--run`: also start a run on it. Only when the user asked to start it.
- Never also add it to `factory/backlog.md`: that would make a second copy.

### Dependencies

```sh
fctl task block 15 --by 12      # → #15 blocked by #12 (backlog)
fctl task unblock 15 --by 12    # → #15 has no blockers
```

### Start and follow a run

```sh
fctl run 12                     # Auto picks the account → Run #41 on #12 as b@y → …/tasks/12
fctl run 12 --account b@y       # this account (id or email), even near its limits
fctl run next                   # top ready Backlog task of this repo (always Auto)
fctl run next --module frontend # top ready Backlog task of module frontend
fctl show 12                    # where it is: status, stage, spec, rounds
fctl round 12                   # round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)
fctl diff 12                    # latest round's patch; --round N for another
```

**"Work on <module>"** (e.g. "work on frontend") means `fctl run next --module frontend` in the repo:
it starts that module's top ready Backlog task. The project's modules are on its Modules page
(`/projects/{id}/modules`); an unknown name fails with `no module nope in api; known: backend, frontend`
and starts nothing, so that error also lists them.

`fctl run <id>` on a task already in progress continues from its stage. Before re-running a
stalled task, make sure no other run or terminal session still drives it: two orchestrators on one
worktree overwrite each other.

### Review a task in Review

```sh
fctl show 12                    # spec, every round's build notes, verdicts, comments, decisions
fctl show 12 --round 2          # one round only
fctl diff 12                    # the patch
```

Summarize for the user: what was built, verdicts, the approver's decision and open questions.
Then, only on their word:

```sh
fctl approve 12                                  # → #12: done, then the git commands to commit it
fctl rework 12 "Make the limit configurable"     # → #12: in_progress · rework (a rework run starts)
```

`fctl approve` runs no git. It prints `cd <worktree>`, `git add -A && git commit -m …`,
`git push -u origin factory/…`, and `wt remove …` for the user; run them only if asked.

### Submit changes made in this session

Use the `/factory-submit` skill if it's installed. By hand, from the working tree, without staging
or committing:

```sh
fctl submit --new --title "Fix open redirect after login" <<'EOF'
`next` was passed to redirect() unvalidated. Added is_safe_url(); tests: pytest -q (48 passed).
EOF
# Review #17: 3 files, +38 −2 → …/tasks/17/review

fctl submit 17 <<'EOF'
Kept the redirect on the same host only; tests: pytest -q (49 passed).
EOF
# Round 2 of #17: …
```

It sends tracked and untracked files that aren't `.gitignore`d, diffed against `HEAD`.

### Project context

The stack and conventions every agent reads at the top of `fctl show`. At most 16 KB, replaced
whole, so start from the current one:

```sh
fctl context
fctl context set <<'EOF'
Python 3.12 with uv. Tests: uv run pytest -q. FastAPI, no ORM.
EOF
# Context saved on api-server (61 bytes)
```

### Move a task to another app

```sh
fctl export 12 -o rate-limit.zip     # --transcripts adds agent transcripts: they can hold paths, env, secrets
fctl import rate-limit.zip           # in the target repo; re-importing updates the task it made
```

### Run the app

Operator commands; use them when the user asks.

| Command | What it does |
|---|---|
| `fctl serve [--host 127.0.0.1] [--port 4545]` | the backend in the foreground; stopping it stops every run |
| `fctl service install` / `uninstall` | the backend and frontend as launchd / `systemd --user` services |
| `fctl service start\|stop\|restart [backend\|frontend] [--force]` | `stop`/`restart` of the backend refuse while runs are active unless `--force` |
| `fctl service reload [--force]` | after a pull or merge: rebuild the frontend, restart both |
| `fctl service status` / `logs [-f] [-n N]` | pids, ports, served commit (`stale`), active runs / the logs |
| `fctl setup` | (re)writes the global skills into `~/.claude/skills` |
| `fctl seed` | demo data into an **empty** `FCTL_HOME`; always with a temp one: `FCTL_HOME=$(mktemp -d) fctl seed` |

With Docker (`docker compose up`), the backend is already on `127.0.0.1:4545`; don't run
`fctl serve` or `fctl service` on the host.

## Commands

| Command | Stdin | Notes |
|---|---|---|
| `fctl show <id> [--round N \| --feedback]` | | task as markdown; full view starts with `## Project context` |
| `fctl diff <id> [--round N]` | | a round's patch, default latest |
| `fctl round <id>` | | latest round's four verdicts, `(k/4)` |
| `fctl context` / `fctl context set` | set: context | needs the repo |
| `fctl connect --workspace W [--test-cmd C]` | | needs the repo |
| `fctl task add "title" [--description TEXT\|-] [--blocked-by IDS] [--run]` | with `-`: description | needs the repo |
| `fctl task block\|unblock <id> --by <id>` | | |
| `fctl run <id> [--account <id\|email>]` / `fctl run next [--module <name>]` | | `next` needs the repo |
| `fctl rework <id> "note"` / `fctl approve <id>` | | task must be in `review` |
| `fctl submit --new --title T` / `fctl submit <id>` | description / build notes | diffs the current tree |
| `fctl export <id> [-o FILE] [--transcripts]` / `fctl import FILE` | | import needs the repo |
| `fctl import-factory [--job ID]` | | imports a legacy file-based `factory/` |
| `fctl spec <id>` | spec | factory agents (spec-writer) |
| `fctl verdict <id> security\|ux\|ui\|code PASS\|CHANGES` | findings | factory agents (reviewers) |
| `fctl comment <id> <slot> --path P --line L` | comment | factory agents (reviewers) |
| `fctl decide <id> APPROVE\|ESCALATE` | summary | factory agents (approver) |
| `fctl stage <id> <stage>` | | the orchestrator only |

"Needs the repo" means run it inside the connected repo (any subdirectory or worktree); elsewhere
it fails with `not inside a git repository`.

## When a command fails

Exit `0` is success. Exit `1` prints one `fctl: <reason>` line on stderr, `fctl: <status> <detail>`
when the app refused; most name the fix. Exit `2` is a usage error. Don't retry a refusal unchanged.

| Message | Do |
|---|---|
| `can't reach http://127.0.0.1:4545 — is "fctl serve" running?` | Ask the user to start the app, or fix `FCTL_URL`. |
| `404 no project at <path>; in that repo, run fctl connect --workspace <name>, or if the checkout moved, change the path on the project's Settings page` | Connect the repo first, or after a move change the path in Settings. |
| `not inside a git repository: <cwd>` | `cd` into the repo. |
| `404 Not Found` | Unknown task id. |
| `409 run #41 is already running on #12; …` | Wait, or the user stops it in the app. |
| `409 2 runs active (…); the limit is 2. …` | The global run cap is full; wait or stop one. |
| `409 #15 is blocked by #12, #14; …` | Finish those, or `fctl task unblock`. |
| `409 #12 is in review` / `is done` | Nothing to run; the user approves or requests changes. |
| `409 #12 is not in review` | `approve`/`rework` need status `review`. |
| `409 factory isn't committed on main: …` / `this repo runs the file-based /factory loop: …` | Follow the message: usually Create factory, then commit it on the default branch. |
| `409 not on subscription auth` | No Claude account is signed in; Settings → Claude accounts. |
| `409 all accounts near their limits: …` | Wait for a reset, or `--account` if the user wants. |
| `409 wt (worktrunk) isn't installed: …` / `wt … failed` | `brew install worktrunk`, or fix what wt says. |
| `409 <file> is ignored in the main checkout but not on main, …` | Commit that `.gitignore` line on the default branch. |
| `HEAD has no commit yet; commit once before submitting` | Tell the user; don't make the commit. |
| `422 no changes to submit` / `413 patch over 5 MB` | Nothing outside `.gitignore` changed / a generated file is in the tree. |
| `spec is empty` / `context is empty` / `description is empty` | Pass the text on stdin (a pipe, file, or heredoc). |

## If you are an agent inside a factory run

Your agent file or the `/factory` skill is your instruction; these are the `fctl` constraints
behind it. Your cwd is the task's worktree. Bash allows only `fctl show/diff/spec/submit/verdict/comment/decide/stage/round`,
`git status`, `git diff`, and the test command; everything else (including `fctl run`, `approve`,
`rework`, and git writes) is denied with no one to approve. Write long markdown with the Write tool
to `.fctl/<name>.md` (git ignores `.fctl/`) and post it with `fctl <command> … < .fctl/<name>.md`:
a heredoc over about 10,000 characters, or one holding `{"`, is denied. Each `fctl submit` makes a
new round, so submit once per round. Only the orchestrator runs `fctl stage`. Edits under
`.claude/` are denied in a run. If you start a server, use `$FCTL_BACKEND_PORT` /
`$FCTL_FRONTEND_PORT` and a temp `FCTL_HOME`, never the user's.

Inside the workcell checkout itself, `docs/fctl_docs/` has the full agent docs and
`src/workcell/fctl.md` the full reference.
