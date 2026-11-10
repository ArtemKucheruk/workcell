`fctl` is the Claude Factories command line. It starts the app's backend, installs the global
skills, and is how you, the `/factory-connect` and `/factory-submit` skills, and the factory's
agents read and write the app. Every command but `fctl serve`, `fctl setup`, and `fctl seed` is a
small HTTP client of the backend at `FCTL_URL`. `fctl --help` lists the commands, and
`fctl <command> --help` prints one command's arguments.

## Install

`fctl` comes with the app's Python package. Install it on the host with uv, from your checkout:

```sh
uv tool install ~/personalProjects/claude-factories   # puts fctl on PATH (~/.local/bin)
fctl setup     # writes ~/.claude/skills/factory-connect and ~/.claude/skills/factory-submit
```

Use the path of your own checkout. With `--editable`
(`uv tool install --editable ~/personalProjects/claude-factories`), `fctl` runs the code in the
checkout, so a `git pull` is enough to update it. Without it, `uv tool install --reinstall` with
the same path picks up new code. If `fctl` isn't found afterwards, run `uv tool update-shell` and
open a new terminal. `uv tool uninstall claude-factories` removes it.

`fctl setup` installs the two global skills into Claude Code, once per machine:

| Skill | Written to |
|---|---|
| `/factory-connect` | `~/.claude/skills/factory-connect/SKILL.md` |
| `/factory-submit` | `~/.claude/skills/factory-submit/SKILL.md` |

The factory itself, the `/factory` skill and its 7 agents, is written into each repo by
**Create factory** on the project's Settings page, not by `fctl`.

The app runs in Docker (see [Using fctl with Docker](#using-fctl-with-docker)). Without Docker,
`fctl serve` runs the backend on `127.0.0.1:4545`, and the frontend server runs next to it:
`npm --prefix frontend ci && npm --prefix frontend run build && node frontend/server.js`, on
`127.0.0.1:3000`.

## FCTL_URL and FCTL_HOME

| Variable | Default | Read by | What it is |
|---|---|---|---|
| `FCTL_URL` | `http://127.0.0.1:4545` | every command that calls the app | the backend's address; a trailing `/` is dropped |
| `FCTL_HOME` | `~/.claude-factories` | `fctl serve`, `fctl seed` | the data dir: `factory.db`, and `runs/<id>.jsonl` for each run's log |

Set `FCTL_URL` when the backend isn't on port 4545, for example after `fctl serve --port 5000`:

```sh
export FCTL_URL=http://127.0.0.1:5000
```

The backend refuses any `Host` but `127.0.0.1` or `localhost`, so `FCTL_URL` names one of those.
Runs get their own `FCTL_URL`: the app starts every agent with `FCTL_URL=http://127.0.0.1:<port>`,
the port the backend listens on.

`FCTL_HOME` matters only to `fctl serve` and `fctl seed`. Either creates the folder and `factory.db`
when they're missing. Every other command works through the API and never opens the data dir.

The links `fctl` prints (`fctl connect`, `fctl task add`, `fctl run`, `fctl submit`) start with
`FCTL_URL`, the backend, which answers only `/api/` calls. The pages are on the frontend server:
open the same path on `http://127.0.0.1:3000`.

## Using fctl with Docker

With `docker compose up`, the backend runs `fctl serve --host 0.0.0.0` in its container, and
`compose.override.yaml` (your copy of `compose.override.example.yaml`) publishes it on the host at
`127.0.0.1:4545`. So:

- `fctl` on the host needs no setting: it keeps `FCTL_URL` at its default, `http://127.0.0.1:4545`.
- Don't run `fctl serve` on the host while compose is up. Port 4545 is taken.
- `FCTL_HOME` doesn't apply on the host. The data lives in the `fctl-home` volume, mounted at
  `/data` in the container, where the image sets `FCTL_HOME=/data`. `docker compose down -v`
  deletes it.
- `fctl connect` stores the host path of your repo. The override mounts each project root at the
  same absolute path in the container, so the backend finds the repo there. Add a volume line for
  every root that holds a connected project.
- `fctl setup` writes the skills into the host's `~/.claude`, where your own Claude Code sessions
  read them.
- Agents in a run use the image's `fctl`, inside the container, with
  `FCTL_URL=http://127.0.0.1:4545`.

To run a command inside the container, from the checkout next to `compose.yaml`:

```sh
docker compose exec backend fctl --help
```

## Exit codes and errors

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | The command failed. One line on stderr, starting `fctl: `. |
| `2` | A usage error: an unknown command, a missing or invalid argument, or a flag combination the command refuses. argparse prints the usage line and the error on stderr. |

`fctl serve` has one more: `3` when the server can't start, for example because the port is taken.

The `fctl: ` lines every command can print:

- `fctl: <status> <detail>`: the app refused the call, for example `fctl: 404 Not Found` for an
  unknown task id or `fctl: 409 run #41 active`. `<detail>` is the response's `detail`. A 422 from
  request validation prints its `detail` list as JSON.
- `fctl: can't reach http://127.0.0.1:4545 — is "fctl serve" running?`: nothing answered at
  `FCTL_URL`. Start `fctl serve`, or `docker compose up`, or fix `FCTL_URL`.
- `fctl: 403 Host must be 127.0.0.1 or localhost`: `FCTL_URL` names another host.
- `fctl: not inside a git repository: <cwd>`: the command works on the current repo and the
  current directory isn't in one.
- `fctl: can't tell the default branch: no origin/HEAD and HEAD is detached`: `fctl connect`
  found neither `origin/HEAD` nor a current branch in the main checkout.
- `fctl: HEAD has no commit yet; commit once before submitting`: `fctl submit` needs a commit to
  diff against.

Each command's section lists only its own messages and refers here for the rest.

## fctl serve

Starts the app's backend in the foreground. It makes no API call; it is the API.

**Synopsis**

```
fctl serve [--host HOST] [--port PORT]
```

**Arguments and flags**

- `--host HOST`: the address to bind. Default `127.0.0.1`. `0.0.0.0` is the Docker container's
  setting; don't use it on the host.
- `--port PORT`: the port to listen on. Default `4545`. Other commands find it through `FCTL_URL`.

**Stdin**

none

**Output**

One line, then uvicorn's request log on stderr until you stop it with Ctrl-C:

```
Claude Factories → http://127.0.0.1:4545 (data: /Users/me/.claude-factories)
```

The data dir is `FCTL_HOME`. Stopping `fctl serve` stops every run; at the next start, a run still
marked running becomes `failed: app restarted`.

**Exit codes and errors**

- `0` after Ctrl-C.
- `3` when the server can't start: uvicorn logs the reason on stderr, for example
  `[Errno 48] error while attempting to bind on address ('127.0.0.1', 4545): [errno 48] address already in use`
  when the port is taken.
- `2` for a usage error, such as a `--port` that isn't a number.

See [Exit codes and errors](#exit-codes-and-errors).

**Called by**

me. The backend container runs `fctl serve --host 0.0.0.0`.

**Example**

```sh
fctl serve --port 5000
```

## fctl setup

Installs the `/factory-connect` and `/factory-submit` skills for Claude Code. No HTTP.

**Synopsis**

```
fctl setup
```

**Arguments and flags**

none

**Stdin**

none

**Output**

One line per skill:

```
Wrote /Users/me/.claude/skills/factory-connect/SKILL.md
Wrote /Users/me/.claude/skills/factory-submit/SKILL.md
```

`fctl` owns each `SKILL.md` and overwrites it, so running `fctl setup` again after an update
installs the new skills. Other files in those folders stay. It always writes under
`~/.claude`, also when `CLAUDE_CONFIG_DIR` is set.

**Exit codes and errors**

- `fctl: can't write <path>: <reason>`, exit `1`. It stops at the first failed write.

**Called by**

me, once per machine and after updating `fctl`.

**Example**

```sh
fctl setup
```

## fctl seed

Fills an empty `FCTL_HOME` with demo data, so every page and state of the app has something to show
without running an agent. No HTTP: it writes `factory.db` and the demo repos itself, so the backend
doesn't have to be up.

**Synopsis**

```
fctl seed
```

**Arguments and flags**

none

**Stdin**

none

**Output**

One line:

```
Seeded /Users/me/.claude-factories-demo: 2 workspaces, 3 projects, 14 tasks, 7 runs
```

What it writes, all in one transaction:

- Two workspaces, `personal` and `work`, with three projects. Each is a small git repo on `main`
  under `FCTL_HOME/demo/`, one per factory state: `api-server` is ready, `web-shop` has its
  factory written but not committed, and `notes-cli` has none.
- Tasks in every status and stage: specs, rounds whose diffs are real `git diff` output, verdicts,
  inline and conversation comments, decisions, and ended runs (succeeded, failed, and stopped)
  with their logs in `FCTL_HOME/runs/`. Each factory task has its worktree under
  `api-server/.claude/worktrees/`.
- Context cards on `api-server`: two top-level cards, one read from its `README.md` (so
  **Reload from path** shows), and a `Runbooks` group with two cards.
- Timestamps spread over the last 30 days.

The demo is ordinary data. **Run** and **Retry** on a demo task start real runs against the demo
repos. Delete the whole `FCTL_HOME` to remove it.

Next, start the app on the same `FCTL_HOME`, with your own `fctl serve` stopped, since both use port
4545. With Docker, seed a separate compose project instead (see the example).

**Exit codes and errors**

- `fctl: FCTL_HOME has data; seed an empty one`, exit `1`: the database already has a workspace.
  Nothing is written.
- `fctl: <FCTL_HOME>/demo exists; seed an empty FCTL_HOME`, exit `1`: probably left by a seed that
  failed. Delete that folder and run `fctl seed` again.
- `fctl: can't run git: <reason>`, `fctl: git failed: <git's error>`, and
  `fctl: git worktree add failed: <git's error>`, exit `1`. No rows are written, but `demo/` may be
  left behind.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me, to try the app or to work on its pages.

**Example**

```sh
FCTL_HOME=~/.claude-factories-demo fctl seed
FCTL_HOME=~/.claude-factories-demo fctl serve
```

With Docker, in a compose project of its own, so its volumes never touch your real data:

```sh
docker compose down                          # your own app; its data stays in its volumes
docker compose -p claude-factories-demo up --build -d
docker compose -p claude-factories-demo exec backend fctl seed
docker compose -p claude-factories-demo down -v   # later: deletes the demo
```

## fctl connect

Registers the current repo as a project in a workspace, or updates it if it's connected already.
Calls `POST /api/projects/connect`.

**Synopsis**

```
fctl connect --workspace W [--test-cmd C]
```

Run it anywhere inside the repo, also from a worktree or a subdirectory: the project is the main
checkout. `fctl` sends its absolute path, its folder name as the project name, the `origin`
remote's URL if there is one, and the default branch: `origin/HEAD`, else the main checkout's
current branch.

**Arguments and flags**

- `--workspace W`: required. The workspace to put the project in. A new name creates the
  workspace. Surrounding spaces are dropped.
- `--test-cmd C`: the command that runs the repo's whole test suite, for example
  `"uv run pytest -q"`. Factory runs execute it, and **Create factory** refuses a project without
  one. Leaving it out on a later connect keeps the stored one.

**Stdin**

none

**Output**

```
Connected api-server (personal) → http://127.0.0.1:4545/projects/3
```

**Exit codes and errors**

- `fctl: not inside a git repository: <cwd>` and
  `fctl: can't tell the default branch: no origin/HEAD and HEAD is detached`, exit `1`.
- `fctl: 422 workspace must not be blank`, exit `1`.
- `--workspace` missing: exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

`/factory-connect`, which finds the test command first. Also me.

**Example**

```sh
fctl connect --workspace personal --test-cmd "uv run pytest -q"
```

## fctl context

Prints the current repo's project context: the stack and conventions the agents read at the top of
`fctl show`. Calls `GET /api/projects?path=…`, then `GET /api/projects/{id}/context`.

**Synopsis**

```
fctl context
```

**Arguments and flags**

none. `fctl context set` is its own command, below.

**Stdin**

none

**Output**

The stored `context_md` exactly, with nothing added. An empty context prints nothing.

**Exit codes and errors**

- `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.
- `fctl: not inside a git repository: <cwd>`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl context > context.md
```

## fctl context set

Saves the current repo's project context from stdin, replacing it. Calls `GET /api/projects?path=…`,
then `PUT /api/projects/{id}/context`.

**Synopsis**

```
fctl context set <<'EOF'
<markdown>
EOF
```

**Arguments and flags**

none

**Stdin**

The new context, as markdown, sent unchanged. Pass it in a quoted heredoc or a pipe. From a
terminal `fctl` reads nothing, and blank stdin is refused, so a hand-typed `fctl context set`
can't wipe the context. To clear it, empty it on the project's Context page.

**Output**

```
Context saved on api-server (1234 bytes)
```

**Exit codes and errors**

- `fctl: context is empty; pass it on stdin`, exit `1`.
- `fctl: 413 context over 16 KB`: over 16384 UTF-8 bytes, exit `1`.
- `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl context set <<'EOF'
Python 3.12 with uv. Tests: uv run pytest -q. FastAPI, no ORM.
EOF
```

## fctl import-factory

Imports the repo's bootstrap factory, `factory/board.json` and `factory/jobs/<id>/`, as tasks in its
project: each job's board entry, history, spec, rounds with their diffs and reviews, decisions, and
feedback, plus copies of the Claude Code transcripts of the sessions that ran it. Calls
`GET /api/projects?path=…`, then `POST /api/projects/{id}/import-factory`.

**Synopsis**

```
fctl import-factory [--job ID]
```

Run it in the connected repo. A job becomes the task whose import key is `factory:<job id>`, so a
rerun updates that task in place: the files win over moves and decisions made in the app, and
comments are kept. A new task, or one whose status changed, goes to the bottom of its column.

**Arguments and flags**

- `--job ID`: only this job, for example `014-run-ui`. Without it, every job in `board.json`, in
  its order.

**Stdin**

none

**Output**

One line per job:

```
Imported 001-a → #12 (new, 2 rounds, 3 transcripts)
Imported 002-b → #13 (updated, 1 round, 0 transcripts)
```

`No jobs in factory/board.json` when the board is empty.

**Exit codes and errors**

- `fctl: 404 no factory/board.json in <path>`, also when `factory/` or `board.json` is a symlink
  that leads outside the repo, exit `1`.
- `fctl: 404 no job <id> in factory/board.json`, exit `1`.
- `fctl: 422 <job or problem>`: `board.json` isn't JSON or has no `jobs` list, a job's id, title,
  status, or stage is bad, or a `diff.patch` isn't a git diff. Nothing is imported, exit `1`.
- `fctl: 413 <job>/round-<n>/diff.patch over 5 MB`, exit `1`.
- `fctl: 409 factory:<id> is imported in project #<n>`: another repo already imported that job id,
  exit `1`.
- `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

`/factory approve`, as its last step, for the job it just merged; a failure there only warns.
Also me, once, for every job.

**Example**

```sh
fctl import-factory --job 014-run-ui
```

## fctl export

Writes a task as a zip bundle that another Claude Factories app can import with
[fctl import](#fctl-import): its spec, each round's build notes, diff, and reviews, my change
requests, the approver's decision, and a `task.json` with the title, description, status, events,
and comments. Calls `GET /api/tasks/{id}/export`.

**Synopsis**

```
fctl export <id> [-o FILE] [--transcripts]
```

Task ids are global, so it runs anywhere, not only in the task's repo.

**Arguments and flags**

- `id`: the task, for example `12`.
- `-o FILE`, `--output FILE`: the file to write. Default: `task-<id>.zip` in the current
  directory. An existing file is overwritten.
- `--transcripts`: also put in the copies of its agents' Claude Code transcripts. They can hold
  paths, env, and secrets, so read them before you share the bundle.

**Stdin**

none

**Output**

```
Exported #12 → task-12.zip
```

**Exit codes and errors**

- `fctl: 404 Task #12 not found`, exit `1`.
- `fctl: can't write <file>: <reason>`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl export 12 -o rate-limit.zip --transcripts
```

## fctl import

Imports a task bundle from [fctl export](#fctl-export) into the current repo's project. Calls
`GET /api/projects?path=…`, then `POST /api/projects/{id}/import` with the file as the body.

**Synopsis**

```
fctl import FILE
```

Run it in the connected repo. The bundle's import key names the task, so importing an updated
bundle again updates the task it made: the bundle wins over moves, decisions, and comments made
since. A done or review task keeps its status; any other lands in Backlog. Imported tasks have no
branch or worktree.

**Arguments and flags**

- `FILE`: the bundle, for example `task-12.zip`.

**Stdin**

none

**Output**

```
Imported #12 Rate-limit login endpoint (new, backlog, 2 rounds, 0 transcripts)
```

`updated` in place of `new` when the bundle's task was imported before.

**Exit codes and errors**

- `fctl: can't read <file>: <reason>`, with no call to the app, exit `1`.
- `fctl: 413 bundle over 50 MB`, `bundle unpacks to over 500 MB`, or `<file> over 5 MB`, exit `1`.
- `fctl: 422 <detail>`: not a zip, an entry that isn't in the layout, is unsafe or a symlink, or
  can't be read, or a bad `task.json` field. Nothing is imported, exit `1`.
- `fctl: 409 <key> is imported in project #<n>`, or `fctl: 409 run #<id> active` while that task
  runs, exit `1`.
- `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl import task-12.zip
```

## fctl task add

Adds a task to the bottom of the current repo's Backlog, with an optional markdown description, and
with `--run` starts a factory run on it. Calls `POST /api/projects/{id}/tasks` with `title` and,
when given, `description_md`, then with `--run` `POST /api/tasks/{id}/run`.

**Synopsis**

```
fctl task add "title" [--description TEXT] [--run]
```

**Arguments and flags**

- `title`: the task's title, quoted for the shell, for example `"Rate-limit login endpoint"`.
- `--description TEXT`: the task's description, as markdown, sent unchanged. `--description -`
  reads it from stdin instead, so a literal `-` is sent by piping it:
  `printf '%s\n' - | fctl task add "T" --description -`. Without the flag the task has only a title.
- `--run`: then start a factory run on it, as `fctl run <id>` does.

**Stdin**

Read only with `--description -`: the description, as markdown, sent unchanged. From a terminal
`fctl` reads nothing. A blank description, as text or on stdin, is refused before any request, so
a hand-typed `--description -` never makes a title-only task. Without `--description -` stdin is
ignored.

**Output**

```
Added #12 to api-server → http://127.0.0.1:4545/projects/3
```

With `--run`, a second line:

```
Run #41 on #12 → http://127.0.0.1:4545/tasks/12
```

**Exit codes and errors**

- `fctl: description is empty; pass it as text, or on stdin with --description -`, exit `1`.
- `fctl: 422 title must not be blank`, exit `1`.
- `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.
- With `--run`, any refusal of [fctl run](#fctl-run), exit `1`. The task stays in Backlog and the
  `Added` line is already printed.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl task add "Rate-limit login endpoint" --run --description - <<'EOF'
## Why
Max 5 failed logins per minute per IP.
EOF
```

## fctl run

Starts a factory run: `/factory <id>` in the task's worktree. Calls `POST /api/tasks/{id}/run`, or
for `next` `POST /api/projects/{id}/run-next`.

**Synopsis**

```
fctl run <id>
fctl run next
```

**Arguments and flags**

- `<id>`: the task to run. It works from any directory.
- `next`: the top of the current repo's Backlog. It needs the repo.

**Stdin**

none

**Output**

```
Run #41 on #12 → http://127.0.0.1:4545/tasks/12
```

The first run on a task creates its worktree, `.claude/worktrees/12-rate-limit-login`, on a new
branch `factory/12-rate-limit-login` from the default branch. Later runs reuse it.

**Exit codes and errors**

- `fctl: 404 no task #12`, exit `1`.
- `fctl: 409 run #41 active`: only one run at a time, across all projects, exit `1`.
- `fctl: 409 #12 is in review` or `fctl: 409 #12 is done`, exit `1`.
- `fctl: 409 factory isn't committed on main: …`: the message names the next step, exit `1`.
- `fctl: 409 worktree <path> is missing` and `fctl: 409 git worktree add failed: <git's error>`,
  exit `1`.
- `fctl: 409 not on subscription auth`, then a second line,
  `Sign in to a Claude account, or make one active, under Settings → Claude accounts, then run again.`:
  no Claude account is active, the active one isn't signed in, or it is logged in with an API key,
  exit `1`.
- `fctl: 500 can't start claude: <reason>`, exit `1`.
- `next` only: `fctl: 404 backlog is empty` and
  `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.
- A target that is neither a number nor `next`:
  `fctl run: error: target must be a task id or next, not 'abc'`, exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me. A run can't call it: agents can't call `fctl approve`, `run`, or `rework`, so a run can't
approve its own work or start other runs.

**Example**

```sh
fctl run next
```

## fctl rework

Requests changes on a task in review, with a note: my **Request changes**. Calls
`POST /api/tasks/{id}/request-changes`. The task moves to `in_progress · rework`. For a factory
task the app then starts a rework run; a task from `/factory-submit` only records the note.

**Synopsis**

```
fctl rework <id> "note"
```

**Arguments and flags**

- `<id>`: the task.
- `note`: what should change, quoted for the shell, for example `"Make the limit configurable"`.

**Stdin**

none

**Output**

```
#12: in_progress · rework
```

**Exit codes and errors**

- `fctl: 422 body_md must not be blank`: the note is blank, exit `1`.
- `fctl: 409 #12 is not in review` and `fctl: 404 #12 has no rounds`, exit `1`.
- `fctl: 409 run #41 active`: a factory task is refused while any run is active, before anything
  is recorded, exit `1`.
- A factory task's rework run can still be refused after the note is recorded, with
  [fctl run](#fctl-run)'s messages, for example `fctl: 409 not on subscription auth` and its
  second line,
  `Sign in to a Claude account, or make one active, under Settings → Claude accounts, then run again.`,
  exit `1`. The note and the move stay; fix the cause, then start the run again with
  `fctl run <id>`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me. A run can't call it: agents can't call `fctl approve`, `run`, or `rework`, so a run can't
approve its own work or start other runs.

**Example**

```sh
fctl rework 12 "Make the limit configurable"
```

## fctl approve

Approves a task in review: my **Approve**. Calls `POST /api/tasks/{id}/approve`. The task moves to
`done`. The app never runs git: it prints the commands to commit the work yourself.

**Synopsis**

```
fctl approve <id>
```

**Arguments and flags**

- `<id>`: the task.

**Stdin**

none

**Output**

The new status, then the commands. For a factory task:

```
#12: done
cd /Users/me/code/api-server/.claude/worktrees/12-rate-limit-login
git add -A && git commit -m 'Rate-limit login endpoint'
git push -u origin factory/12-rate-limit-login     # then open a PR, or merge locally
cd /Users/me/code/api-server && git worktree remove .claude/worktrees/12-rate-limit-login
```

For a task from `/factory-submit`, which has no worktree, only the commit line:

```
#17: done
git add -A && git commit -m 'Fix open redirect after login'
```

**Exit codes and errors**

- `fctl: 409 #12 is not in review` and `fctl: 404 #12 has no rounds`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me. A run can't call it: agents can't call `fctl approve`, `run`, or `rework`, so a run can't
approve its own work or start other runs.

**Example**

```sh
fctl approve 12
```

## fctl submit

Sends the current tree's changes for review: tracked and untracked files alike, `.gitignore`
respected, against `HEAD`, through a temp index so the real one is untouched. It has two forms.

**Synopsis**

```
fctl submit --new --title T    # stdin: the description
fctl submit <id>               # stdin: the build notes
```

`--new` creates a task straight in Review with round 1. Calls `POST /api/projects/{id}/tasks` with
`submit`. `<id>` adds the next round to that task. Calls `POST /api/tasks/{id}/rounds`. A round on a
task from `/factory-submit` puts it back in Review.

**Arguments and flags**

- `<id>`: the task to add a round to. Not with `--new`.
- `--new`: create a new task. Needs `--title`.
- `--title T`: the new task's title, only with `--new`.

**Stdin**

`--new`: the task's description, as markdown. `<id>`: the round's build notes, as markdown. Both
are sent unchanged and may be empty. Pass them in a quoted heredoc (`<<'EOF'`), so the shell
expands nothing; from a terminal `fctl` reads nothing.

**Output**

```
Review #17: 3 files, +38 −2 → http://127.0.0.1:4545/tasks/17/review
Round 2 of #12: 4 files, +126 −9 → http://127.0.0.1:4545/tasks/12/review?round=2
```

The first line is `--new`'s, the second `<id>`'s.

**Exit codes and errors**

- `fctl submit: error: give a task id, or --new with --title`: neither form, or both, exit `2`.
- `fctl: HEAD has no commit yet; commit once before submitting` and
  `fctl: git <step> failed: <git's error>`, exit `1`.
- `fctl: 422 no changes to submit` and `fctl: 413 patch over 5 MB`, exit `1`. Nothing is created.
- `--new`: `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>` and
  `fctl: 422 title must not be blank`, exit `1`.
- `<id>`: `fctl: 404 Not Found` for an unknown task, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

`fctl submit --new` by `/factory-submit`, for a change made in my own session. `fctl submit <id>`
by the builder, from its worktree, for each round, and by `/factory-submit` for the next round of
a task it submitted.

**Example**

```sh
fctl submit --new --title "Fix open redirect after login" <<'EOF'
`next` was passed to redirect() unvalidated. Added is_safe_url(); tests: pytest -q (48 passed).
EOF
fctl submit 17 <<'EOF'
Kept the redirect on the same host only; tests: pytest -q (49 passed).
EOF
```

## fctl show

Prints a task as markdown: everything, one round, or my latest feedback. Calls
`GET /api/tasks/{id}/context`.

**Synopsis**

```
fctl show <id> [--round N | --feedback]
```

**Arguments and flags**

- `<id>`: the task.
- `--round N`: only round N, with its build notes, verdicts, comments, and decisions.
- `--feedback`: only my latest **Request changes**: its note and my line comments, under
  `## Feedback on round N`.

`--round` and `--feedback` don't go together.

**Stdin**

none

**Output**

Markdown. With no flag, the project context comes first, as `## Project context`: the pinned
context set with `fctl context set`, then each card of the project's Context page in its order,
as `### <title>` and its text, a group's cards under it as `#### <title>`. It is left out when
the pinned context is blank and there are no cards. Then the task's heading and status, the
description, the spec (`_No spec yet._` if none), and every round:

```
# #12 Rate-limit login endpoint
Status: in_progress · agent_review

## Description
…
```

**Exit codes and errors**

- `fctl: 404 #12 has no round 3` and `fctl: 404 #12 has no feedback`, exit `1`.
- `--round` with `--feedback`: exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

all agents: the orchestrator, the spec-writer, the builder, the reviewers, and the approver.

**Example**

```sh
fctl show 12 --feedback
```

## fctl diff

Prints a round's full patch. Calls `GET /api/tasks/{id}/rounds/{n}/diff`.

**Synopsis**

```
fctl diff <id> [--round N]
```

**Arguments and flags**

- `<id>`: the task.
- `--round N`: the round. Default: the latest.

**Stdin**

none

**Output**

The round's patch as `git diff` prints it, file by file:

```
diff --git a/app/auth.py b/app/auth.py
…
```

**Exit codes and errors**

- `fctl: 404 #12 has no rounds` and `fctl: 404 #12 has no round 3`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

the reviewers and the approver.

**Example**

```sh
fctl diff 12 --round 1
```

## fctl spec

Saves a task's spec from stdin, replacing it. Calls `PATCH /api/tasks/{id}` with `spec_md`.

**Synopsis**

```
fctl spec <id> <<'EOF'
<markdown>
EOF
```

**Arguments and flags**

- `<id>`: the task.

**Stdin**

The spec, as markdown, sent unchanged. Blank stdin is refused, so a hand-typed `fctl spec 12`
can't wipe the spec; from a terminal `fctl` reads nothing.

**Output**

```
Spec saved on #12
```

**Exit codes and errors**

- `fctl: spec is empty; pass it on stdin`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

the spec-writer.

**Example**

```sh
fctl spec 12 <<'EOF'
# Rate-limit login endpoint
## Acceptance criteria
- [ ] AC1: the 6th failed login in a minute gets 429.
EOF
```

## fctl verdict

Posts a reviewer's verdict on the task's latest round. Calls
`PUT /api/tasks/{id}/rounds/latest/verdicts/{reviewer}`. Posting again replaces that reviewer's
verdict.

**Synopsis**

```
fctl verdict <id> <reviewer> PASS|CHANGES <<'EOF'
<findings>
EOF
```

**Arguments and flags**

- `<id>`: the task.
- `<reviewer>`: one of `security`, `ux`, `ui`, `code`.
- `PASS|CHANGES`: the verdict, `PASS` or `CHANGES`.

**Stdin**

The findings, as markdown, sent unchanged. May be empty; from a terminal `fctl` reads nothing.

**Output**

The round, the verdict, and how many of the 4 reviewers have posted:

```
Round 2 of #12: security=PASS (3/4)
```

**Exit codes and errors**

- `fctl: 404 #12 has no rounds`, exit `1`.
- A reviewer or verdict not in the list: exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

the reviewers.

**Example**

```sh
fctl verdict 12 security CHANGES <<'EOF'
- app/auth.py:44: the limiter keys on the client IP only; key on the username too.
EOF
```

## fctl comment

Posts a reviewer's comment on one line of the latest round's new file. Calls
`POST /api/tasks/{id}/comments`.

**Synopsis**

```
fctl comment <id> <reviewer> --path P --line L <<'EOF'
<comment>
EOF
```

**Arguments and flags**

- `<id>`: the task.
- `<reviewer>`: one of `security`, `ux`, `ui`, `code`.
- `--path P`: required. A file in the round's diff, as the diff names it.
- `--line L`: required. The line number in the new file, from 1.

**Stdin**

The comment, as markdown, sent unchanged. It must not be blank.

**Output**

```
Comment #5 on #12 app/auth.py:44
```

**Exit codes and errors**

- `fctl: 422 body_md must not be blank`, exit `1`.
- `fctl: 422 app/x.py is not in round 2`, exit `1`.
- `fctl: 404 #12 has no rounds`, exit `1`.
- A `--line` under 1 is a `422` with the validation error as JSON, exit `1`.
- A reviewer not in the list, or `--path` or `--line` missing: exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

the reviewers.

**Example**

```sh
fctl comment 12 security --path app/auth.py --line 44 <<'EOF'
Key the limiter on the username too, or one IP can lock out everyone behind a NAT.
EOF
```

## fctl decide

Posts the approver's decision on the latest round. Calls `POST /api/tasks/{id}/decision`. Every
call adds a decision; the latest one counts. It doesn't move the task: the orchestrator does that
with `fctl stage`.

**Synopsis**

```
fctl decide <id> APPROVE|ESCALATE <<'EOF'
<summary>
EOF
```

**Arguments and flags**

- `<id>`: the task.
- `APPROVE|ESCALATE`: the decision, `APPROVE` or `ESCALATE`. My own approve and request changes
  are `fctl approve` and `fctl rework`.

**Stdin**

The decision's summary, as markdown, sent unchanged. May be empty; from a terminal `fctl` reads
nothing.

**Output**

```
Decision #7 on #12: APPROVE
```

**Exit codes and errors**

- `fctl: 404 #12 has no rounds`, exit `1`.
- A decision not in the list: exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

the approver.

**Example**

```sh
fctl decide 12 APPROVE <<'EOF'
All four reviewers pass; the limit and its test match the spec.
EOF
```

## fctl stage

Moves a task to a stage, which also sets its status. Calls `PATCH /api/tasks/{id}` with `stage`.

**Synopsis**

```
fctl stage <id> <stage>
```

**Arguments and flags**

- `<id>`: the task.
- `<stage>`: one of `spec`, `build`, `agent_review`, `approval`, and `rework`, which set status
  `in_progress`, or `human_review` and `escalated`, which set status `review`.

**Stdin**

none

**Output**

The task's new status and stage:

```
#12: in_progress · agent_review
```

**Exit codes and errors**

- A stage not in the list: exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

the orchestrator, the `/factory` skill, at each step of the loop. No other agent changes status.

**Example**

```sh
fctl stage 12 agent_review
```

## fctl round

Prints the latest round's verdicts, so the orchestrator can wait for all four. Calls
`GET /api/tasks/{id}`.

**Synopsis**

```
fctl round <id>
```

**Arguments and flags**

- `<id>`: the task.

**Stdin**

none

**Output**

Each reviewer's verdict, `pending` until posted, and how many have posted:

```
round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)
```

**Exit codes and errors**

- `fctl: #12 has no rounds`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

the orchestrator.

**Example**

```sh
fctl round 12
```
