`fctl` is the Claude Factories command line. It starts the app's backend, installs the global
skills, and is how you, the `/factory-connect` and `/factory-submit` skills, and the factory's
agents read and write the app. Every command but `fctl serve`, `fctl setup`, `fctl seed`, and
`fctl service` is a small HTTP client of the backend at `FCTL_URL`. `fctl --help` lists the commands, and
`fctl <command> --help` prints one command's arguments.

## Install

`fctl` comes with the app's Python package. Install it on the host with uv, from your checkout:

```sh
uv tool install ~/personalProjects/claude-factories   # puts fctl on PATH (~/.local/bin)
fctl setup     # writes ~/.claude/skills/factory-connect, factory-submit, and fctl
```

Use the path of your own checkout. With `--editable`
(`uv tool install --editable ~/personalProjects/claude-factories`), `fctl` runs the code in the
checkout, so a `git pull` is enough to update it. Without it, `uv tool install --reinstall` with
the same path picks up new code. If `fctl` isn't found afterwards, run `uv tool update-shell` and
open a new terminal. `uv tool uninstall claude-factories` removes it.

`fctl setup` installs the three global skills into Claude Code, once per machine:

| Skill | Written to |
|---|---|
| `/factory-connect` | `~/.claude/skills/factory-connect/SKILL.md` |
| `/factory-submit` | `~/.claude/skills/factory-submit/SKILL.md` |
| `fctl` (loaded when you work with fctl) | `~/.claude/skills/fctl/SKILL.md` |

The factory itself, the `/factory` skill and its 7 agents, is written into each repo by
**Create factory** on the project's Settings page, not by `fctl`.

The app runs in Docker (see [Using fctl with Docker](#using-fctl-with-docker)). Without Docker,
[fctl service install](#fctl-service-install) runs the backend on `127.0.0.1:4545` and the
frontend server on `127.0.0.1:3000` as user services that start at login, and
[fctl service reload](#fctl-service-reload) picks up new code after a merge. In the foreground
instead, `fctl serve` runs the backend, and the frontend server runs next to it:
`npm --prefix frontend ci && npm --prefix frontend run build && node frontend/server.js`.

## FCTL_URL and FCTL_HOME

| Variable | Default | Read by | What it is |
|---|---|---|---|
| `FCTL_URL` | `http://127.0.0.1:4545` | every command that calls the app | the backend's address; a trailing `/` is dropped |
| `FCTL_HOME` | `~/.claude-factories` | `fctl serve`, `fctl seed`, `fctl service` | the data dir: `factory.db`, `runs/<id>.jsonl` for each run's log, and for `fctl service` its `logs/` (`backend.log`, `frontend.log`) and `service.json` |

Set `FCTL_URL` when the backend isn't on port 4545, for example after `fctl serve --port 5000`:

```sh
export FCTL_URL=http://127.0.0.1:5000
```

The backend refuses any `Host` but `127.0.0.1` or `localhost`, so `FCTL_URL` names one of those.
Runs get their own `FCTL_URL`: the app starts every agent with `FCTL_URL=http://127.0.0.1:<port>`,
the port the backend listens on.

`FCTL_HOME` matters only to `fctl serve`, `fctl seed`, and `fctl service`. The first two create the
folder and `factory.db` when they're missing. `fctl service` keeps the services' output in
`logs/backend.log` and `logs/frontend.log`, and what it installed (ports, binary paths, env, file
hashes, the commit each service serves) in `service.json`. Every other command works through the API
and never opens the data dir.

The links `fctl` prints (`fctl connect`, `fctl task add`, `fctl task retry`, `fctl run`, `fctl submit`) start with
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
- `fctl service` doesn't apply: compose already runs the app in the background and restarts it.
  Use `docker compose up -d` to start it and `docker compose restart` after a pull.

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
Claude Factories → http://127.0.0.1:4545 (data: ~/.claude-factories)
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

Installs the `/factory-connect`, `/factory-submit`, and `fctl` skills for Claude Code. No HTTP. The
`fctl` skill teaches a Claude Code session the app, its commands, and their errors.

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
Wrote ~/.claude/skills/factory-connect/SKILL.md
Wrote ~/.claude/skills/factory-submit/SKILL.md
Wrote ~/.claude/skills/fctl/SKILL.md
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
Seeded ~/.claude-factories-demo: 2 workspaces, 3 projects, 14 tasks, 7 runs
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
- `fctl: can't run git: <reason>` and `fctl: git failed: <git's error>`, exit `1`. No rows are
  written, but `demo/` may be left behind.
- The task worktrees come from worktrunk's `wt switch`, as `fctl run`'s do, with no copy step (the
  demo repos have no ignored files). So `fctl: wt (worktrunk) isn't installed: brew install
  worktrunk, then run again`, `fctl: wt switch failed: <wt's first stderr line>`, and
  `fctl: wt switch timed out`, exit `1`, the same way.

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

## fctl service install

Installs the backend (`fctl serve`) and the frontend server (`node frontend/server.js`) as user
services and starts them: launchd agents on macOS, `systemd --user` units on Linux. They start at
login and restart when they crash, and closing the terminal doesn't stop them. No API call.

**Synopsis**

```
fctl service install [--backend-port PORT] [--frontend-port PORT]
```

It serves the checkout of the editable install (`uv tool install --editable <checkout>`), found
from the installed package, so it works from any directory. It:

1. Looks up the absolute paths of `fctl`, `node`, `npm`, and `git` (required) and `claude`, `uv`,
   `gh`, and `wt` (only warned about), and builds the services' `PATH`: each found binary's folder,
   then the current `PATH`. `FCTL_HOME` and `CLAUDE_CONFIG_DIR` go into the backend's env when set.
   It all goes into `FCTL_HOME/service.json`.
2. Builds the frontend when `frontend/dist/index.html` is missing: `npm --prefix <repo>/frontend ci`
   (only without `frontend/node_modules`), then `npm --prefix <repo>/frontend run build`.
3. Writes `~/Library/LaunchAgents/com.claude-factories.backend.plist` and `…frontend.plist`, then
   for each runs `launchctl bootout gui/<uid>/<label>` and `launchctl bootstrap gui/<uid> <plist>`.
   On Linux it writes `~/.config/systemd/user/claude-factories-backend.service` and
   `…-frontend.service`, then runs `systemctl --user daemon-reload` and
   `systemctl --user enable --now <unit>`. Both bind `127.0.0.1` only; `KeepAlive` and
   `Restart=on-failure` restart a crash, not a clean exit.

Running it again rewrites the files and restarts both, for example after the checkout moved or a
binary did. On Linux the services start at login; `loginctl enable-linger` (not done here) starts
them at boot.

**Arguments and flags**

- `--backend-port PORT`: the backend's port. Default `4545`. Set `FCTL_URL` to match.
- `--frontend-port PORT`: the frontend's port. Default `3000`.

**Stdin**

none

**Output**

A warning line on stderr for each optional binary it didn't find, then:

```
Wrote ~/Library/LaunchAgents/com.claude-factories.backend.plist
Wrote ~/Library/LaunchAgents/com.claude-factories.frontend.plist
Started backend → http://127.0.0.1:4545 (log: ~/.claude-factories/logs/backend.log)
Started frontend → http://127.0.0.1:3000 (log: ~/.claude-factories/logs/frontend.log)
```

With a `--backend-port` other than 4545, a last line: `export FCTL_URL=http://127.0.0.1:<port>`.

**Exit codes and errors**

- `fctl: fctl service runs on macOS (launchd) or Linux (systemd --user); in Docker use docker compose up -d / docker compose restart`,
  exit `1`, on any other platform or with `FCTL_IN_DOCKER=1`. Every `fctl service` command says it.
- `fctl: fctl service needs an editable install: uv tool install --editable <your checkout>`,
  exit `1`.
- `fctl: node not found on PATH` (or `fctl`, `npm`, `git`), exit `1`. Nothing is written.
- `warning: gh not found on PATH; runs and reviewers need it` (or `claude`, `uv`, `wt`): it goes on.
- `fctl: npm ci failed; see the output above` and `fctl: npm run build failed; see the output above`,
  exit `1`, before any service is loaded.
- `fctl: launchctl bootstrap gui/<uid> failed: <its error>` or
  `fctl: systemctl --user enable failed: <its error>`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me, once per machine, and again after the checkout or a binary moves.

**Example**

```sh
fctl service install
fctl service install --backend-port 5000 --frontend-port 5001
```

## fctl service uninstall

Stops both services and removes them. The logs stay. No API call but the active runs check.

**Synopsis**

```
fctl service uninstall [--force]
```

On macOS it runs `launchctl bootout gui/<uid>/<label>` and deletes each plist. On Linux it runs
`systemctl --user disable --now <unit>`, deletes each unit, then `systemctl --user daemon-reload`.
Then it deletes `FCTL_HOME/service.json`.

Stopping the backend stops every run, so first it asks the backend for active runs
(`GET http://127.0.0.1:<backend port>/api/pages/agents`) and refuses while there are any. A backend
that doesn't answer has none.

**Arguments and flags**

- `--force`: go on even with active runs. The backend's shutdown stops them.

**Stdin**

none

**Output**

```
Uninstalled backend and frontend; logs kept in ~/.claude-factories/logs
```

With `--force` and active runs, first `Stopping active runs: run #68 on #92`.

**Exit codes and errors**

- `fctl: run #68 on #92 is active; wait, stop it in the app, or pass --force`, exit `1`. With
  several: `fctl: run #68 on #92, run #70 on #95 are active; wait, stop them in the app, or pass --force`.
- `fctl: not installed; run fctl service install`, exit `1`: there is no `service.json`. Every
  `fctl service` command but `install` says it.

See [fctl service install](#fctl-service-install) for the platform error, and
[Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl service uninstall
```

## fctl service start

Starts both services, or one. A service that is already running is left alone.

**Synopsis**

```
fctl service start [backend|frontend]
```

On macOS it runs `launchctl kickstart gui/<uid>/<label>` for a loaded agent and
`launchctl bootstrap gui/<uid> <plist>` for one that isn't (after `fctl service stop`). On Linux,
`systemctl --user start <unit…>`. Before starting a service that isn't running, it checks that
nothing else listens on its port, such as a `fctl serve` started by hand. With the frontend among
them, it builds the frontend first when `frontend/dist/index.html` is missing, as `install` does.
A log over 10 MB is renamed to `<name>.log.1` first, replacing the older one.

**Arguments and flags**

- `backend` or `frontend`: only that service. Default: both.

**Stdin**

none

**Output**

```
Started backend → http://127.0.0.1:4545
frontend is already running (pid 4322)
```

**Exit codes and errors**

- `fctl: port 4545 is taken by pid 1234 (python3); stop it, or reinstall with --backend-port`
  (`--frontend-port` for the frontend), exit `1`, and nothing starts. The pid and command come from
  `lsof` and `ps`; without `lsof`, the message says `taken by another process`.
- `fctl: npm run build failed; see the output above`, exit `1`.
- `fctl: not installed; run fctl service install`, exit `1`.

See [fctl service install](#fctl-service-install) for the platform error, and
[Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl service start backend
```

## fctl service stop

Stops both services, or one, until the next `start`, `restart`, or login.

**Synopsis**

```
fctl service stop [backend|frontend] [--force]
```

On macOS it runs `launchctl bootout gui/<uid>/<label>`; the plist stays, so the next login loads it
again. On Linux, `systemctl --user stop <unit…>`. When the backend is among them, it refuses while
runs are active, as [fctl service uninstall](#fctl-service-uninstall) does. Stopping only the
frontend doesn't touch runs, so it doesn't check.

**Arguments and flags**

- `backend` or `frontend`: only that service. Default: both.
- `--force`: go on even with active runs. The backend's shutdown stops them.

**Stdin**

none

**Output**

```
Stopped backend
Stopped frontend
```

With `--force` and active runs, first `Stopping active runs: run #68 on #92`.

**Exit codes and errors**

- `fctl: run #68 on #92 is active; wait, stop it in the app, or pass --force`, exit `1`.
- `fctl: not installed; run fctl service install`, exit `1`.

See [fctl service install](#fctl-service-install) for the platform error, and
[Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl service stop frontend
```

## fctl service restart

Restarts both services, or one.

**Synopsis**

```
fctl service restart [backend|frontend] [--force]
```

On macOS it runs `launchctl kickstart -k gui/<uid>/<label>`, or bootstraps an agent that isn't
loaded. On Linux, `systemctl --user restart <unit…>`. When the backend is among them, it refuses
while runs are active, as [fctl service uninstall](#fctl-service-uninstall) does. A log over 10 MB
is renamed to `<name>.log.1` first. It records the checkout's `HEAD` as the code each restarted
service serves, for [fctl service status](#fctl-service-status).

**Arguments and flags**

- `backend` or `frontend`: only that service. Default: both.
- `--force`: go on even with active runs. The backend's shutdown stops them.

**Stdin**

none

**Output**

```
Restarted backend → http://127.0.0.1:4545
Restarted frontend → http://127.0.0.1:3000
```

**Exit codes and errors**

- `fctl: run #68 on #92 is active; wait, stop it in the app, or pass --force`, exit `1`.
- `fctl: not installed; run fctl service install`, exit `1`.

See [fctl service install](#fctl-service-install) for the platform error, and
[Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl service restart backend --force
```

## fctl service reload

Picks up new code after a `git pull` or a merge: rebuilds the frontend and restarts both services.

**Synopsis**

```
fctl service reload [--force]
```

In order:

1. Refuses while runs are active, as [fctl service uninstall](#fctl-service-uninstall) does.
2. `npm --prefix <repo>/frontend ci`, only when `frontend/package-lock.json` changed since the last
   `ci` (its sha256 is kept in `service.json`), or `frontend/node_modules` is missing.
3. `npm --prefix <repo>/frontend run build`.
4. Restarts both, as [fctl service restart](#fctl-service-restart) does.

When `pyproject.toml` or `uv.lock` changed since the last `install` or `reload`, it prints the
command that installs the new Python dependencies. It doesn't run it: an editable install needs it
only when the dependencies change.

**Arguments and flags**

- `--force`: go on even with active runs. The backend's shutdown stops them.

**Stdin**

none

**Output**

npm's own output, then:

```
Python dependencies changed; run: uv tool install --editable --reinstall ~/code/claude-factories
Restarted backend → http://127.0.0.1:4545
Restarted frontend → http://127.0.0.1:3000
```

The first line only when they changed.

**Exit codes and errors**

- `fctl: run #68 on #92 is active; wait, stop it in the app, or pass --force`, exit `1`.
- `fctl: npm ci failed; see the output above` and `fctl: npm run build failed; see the output above`,
  exit `1`. Nothing is restarted, so the old code keeps running.
- `fctl: not installed; run fctl service install`, exit `1`.

See [fctl service install](#fctl-service-install) for the platform error, and
[Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me, after each merge or pull.

**Example**

```sh
git pull && fctl service reload
```

## fctl service status

Prints each service's state, the code it serves, and the active runs.

**Synopsis**

```
fctl service status
```

The pid comes from `launchctl print` (macOS) or `systemctl --user show` (Linux), the uptime from
`ps`, and the active runs from `GET /api/pages/agents`. `main` is the checkout's default branch
(`origin/HEAD`, else its current branch), with no fetch. `stale` means the service runs another
commit than `main`: run [fctl service reload](#fctl-service-reload).

**Arguments and flags**

none

**Stdin**

none

**Output**

```
backend: running
  pid: 4321
  port: 4545
  uptime: 01:02:03
  url: http://127.0.0.1:4545
  code: 3f2a1bc, main 9e8d7f6, stale

frontend: stopped
  pid: -
  port: 3000
  uptime: -
  url: http://127.0.0.1:3000
  code: 9e8d7f6, main 9e8d7f6, current

active runs: run #68 on #92 (Rate-limit login endpoint)
```

`active runs:` is `none` with none, and `unknown (backend not answering)` when the backend is down.

**Exit codes and errors**

- `warning: node moved: /opt/homebrew/bin/node no longer exists; run fctl service install`, on
  stderr, for each saved binary path that is gone. The exit code stays `0`.
- `fctl: not installed; run fctl service install`, exit `1`.

See [fctl service install](#fctl-service-install) for the platform error, and
[Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl service status
```

## fctl service logs

Prints the end of the services' logs, `FCTL_HOME/logs/backend.log` and `frontend.log`. They hold
each process's stdout and stderr.

**Synopsis**

```
fctl service logs [backend|frontend] [-f] [-n N]
```

**Arguments and flags**

- `backend` or `frontend`: only that log. Default: both.
- `-f`, `--follow`: keep printing new lines: it runs `tail -n N -f <logs…>` until Ctrl-C.
- `-n N`: how many lines from the end. Default `50`.

**Stdin**

none

**Output**

Each log under a header, as `tail` prints them:

```
==> ~/.claude-factories/logs/backend.log <==
Claude Factories → http://127.0.0.1:4545 (data: ~/.claude-factories)
no log yet: ~/.claude-factories/logs/frontend.log
```

`no log yet: <path>` for a log that doesn't exist.

**Exit codes and errors**

- `fctl: not installed; run fctl service install`, exit `1`.

See [fctl service install](#fctl-service-install) for the platform error, and
[Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl service logs backend -f -n 100
```

## fctl connect

Registers the current repo as a project in a workspace, or updates it if it's connected already.
Calls `POST /api/projects/connect`. When the main checkout has a `factory/board.json` or
`factory/backlog.md` file, it then syncs them onto the board with
`POST /api/projects/{id}/import-factory` `{}`, as [fctl import-factory](#fctl-import-factory) does.

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

With a `factory/board.json` or `factory/backlog.md`, a second line counts the sync's tasks: new
ones, ones that were there already, and `backlog.md` lines it skipped:

```
Connected api-server (personal) → http://127.0.0.1:4545/projects/3
Synced factory/: 2 new, 1 updated, 3 skipped
```

**Exit codes and errors**

- `fctl: not inside a git repository: <cwd>` and
  `fctl: can't tell the default branch: no origin/HEAD and HEAD is detached`, exit `1`.
- `fctl: 422 workspace must not be blank`, exit `1`.
- A refused sync prints the `Connected` line, then
  [fctl import-factory](#fctl-import-factory)'s error, for example
  `fctl: 422 factory/board.json isn't valid JSON`, exit `1`. The project stays connected, and its
  board shows the same error.
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
feedback, plus copies of the Claude Code transcripts of the sessions that ran it. Then each
`factory/backlog.md` line that `board.json` doesn't list, `- [ ] <id>: <text>` (`- [x]` when done),
becomes a backlog-only task: titled from the id, described by its `## ` section and text, in Backlog
or Done. Calls `GET /api/projects?path=…`, then `POST /api/projects/{id}/import-factory`. The board
runs the same sync on its own when either file changes, and nothing is written to the repo.

**Synopsis**

```
fctl import-factory [--job ID]
```

Run it in the connected repo. A job becomes the task whose import key is `factory:<job id>`, so a
rerun updates that task in place: the files win over moves and decisions made in the app, and
comments are kept. A new task, or one whose status changed, goes to the bottom of its column.
A backlog-only task is different: a rerun changes only its description and status, and leaves it
alone once the app has started it (a run, a round, or a move out of Backlog). A removed line never
deletes its task.

**Arguments and flags**

- `--job ID`: only this `board.json` job, for example `014-run-ui`; `backlog.md` isn't read.
  Without it, every job in `board.json`, in its order, then `backlog.md`'s lines in file order.

**Stdin**

none

**Output**

One line per job, then the `backlog.md` lines it skipped (a checkbox line with no `<id>:`, another
mark, a bad id, or a repeated id), if any:

```
Imported 001-a → #12 (new, 2 rounds, 3 transcripts)
Imported 002-b → #13 (updated, 1 round, 0 transcripts)
Imported 059-legacy-factory → #14 (new, 0 rounds, 0 transcripts)
Skipped 2 lines in factory/backlog.md
```

`No jobs in factory/` when nothing was imported or skipped.

**Exit codes and errors**

- `fctl: 404 no factory/board.json or factory/backlog.md in <path>`, also when `factory/` or a file
  is a symlink that leads outside the repo, exit `1`.
- `fctl: 404 no factory/board.json in <path>` and `fctl: 404 no job <id> in factory/board.json`,
  with `--job`, exit `1`.
- `fctl: 422 <job or problem>`: `board.json` isn't JSON or has no `jobs` list, a job's id, title,
  status, or stage is bad, or a `diff.patch` isn't a git diff. Nothing is imported, exit `1`.
- `fctl: 413 <job>/round-<n>/diff.patch over 5 MB` or `fctl: 413 backlog.md over 5 MB`, exit `1`.
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

Adds a task to the bottom of the current repo's Backlog, with an optional markdown description,
the tasks it waits on, and its module, and with `--run` starts a factory run on it. With `--module`
it first reads the project's modules with `GET /api/projects/{id}/modules`. Then it calls
`POST /api/projects/{id}/tasks` with `title` and, when given, `description_md`, `blocked_by`, and
`module_id`, then with `--run` `POST /api/tasks/{id}/run`.

**Synopsis**

```
fctl task add "title" [--description TEXT] [--blocked-by IDS] [--module NAME] [--run]
```

**Arguments and flags**

- `title`: the task's title, quoted for the shell, for example `"Rate-limit login endpoint"`.
- `--description TEXT`: the task's description, as markdown, sent unchanged. `--description -`
  reads it from stdin instead, so a literal `-` is sent by piping it:
  `printf '%s\n' - | fctl task add "T" --description -`. Without the flag the task has only a title.
- `--blocked-by IDS`: the tasks it waits on, comma-separated with no spaces, for example `12,14`.
  Each must be a task of the same project. The new task is blocked until all of them are done. Change
  the links later with [fctl task block](#fctl-task-block) and
  [fctl task unblock](#fctl-task-unblock).
- `--module NAME`: the project's module the task belongs to, for example `frontend`, matched in any
  case after trimming. Create modules on the project's Modules page; change a task's module on its
  task page. Without the flag the task has no module.
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

With `--run`, a second line, naming the Claude account Auto picked:

```
Run #41 on #12 as b@y → http://127.0.0.1:4545/tasks/12
```

**Exit codes and errors**

- `fctl: description is empty; pass it as text, or on stdin with --description -`, exit `1`.
- `--blocked-by` with a part that isn't a positive integer, such as `12,x`: argparse's usage error,
  with no call to the app, exit `2`.
- `fctl: 422 title must not be blank`, exit `1`.
- `fctl: 422 no task #99` or
  `fctl: 422 #30 is in another project; a task waits only on tasks of its own project`: no task is
  added, exit `1`.
- `fctl: no module nope in api-server; known: backend, frontend` (or `known: none` when the
  project has no modules): no task is added, exit `1`.
- `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.
- With `--run`, any refusal of [fctl run](#fctl-run), exit `1`. The task stays in Backlog and the
  `Added` line is already printed. A task added with open blockers is refused as blocked.

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

## fctl task block

Makes a task wait on another task of its project: the task is blocked until that one is done, and
Run, Retry, and Run next refuse it until then. Calls `PUT /api/tasks/{id}/blocked-by/{blocker}`.

**Synopsis**

```
fctl task block <id> --by <id>
```

Task ids are global, so it works from any directory. Blocking a task again on the same task changes
nothing and prints the same line.

**Arguments and flags**

- `<id>`: the task that waits.
- `--by <id>`: the task it waits on, one per call.

**Stdin**

none

**Output**

Every task it now waits on, by id, with that task's status:

```
#15 blocked by #12 (backlog), #14 (done)
```

**Exit codes and errors**

- `fctl: 404 Task #15 not found`, exit `1`.
- `fctl: 422 #15 can't wait on itself`, exit `1`.
- `fctl: 422 no task #99`, exit `1`.
- `fctl: 422 #30 is in another project; a task waits only on tasks of its own project`, exit `1`.
- `fctl: 422 cycle: #15 waits on #12, which waits on #14, which waits on #15`: the link would close a
  loop, so nothing is added, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl task block 15 --by 12
```

## fctl task unblock

Stops a task waiting on another task. Calls `DELETE /api/tasks/{id}/blocked-by/{blocker}`.

**Synopsis**

```
fctl task unblock <id> --by <id>
```

Task ids are global, so it works from any directory.

**Arguments and flags**

- `<id>`: the task that waits.
- `--by <id>`: the task to stop waiting on, one per call.

**Stdin**

none

**Output**

Every task it still waits on, as [fctl task block](#fctl-task-block) prints them, or, with none left:

```
#15 has no blockers
```

**Exit codes and errors**

- `fctl: 404 Task #15 not found`, exit `1`.
- `fctl: 404 #15 is not blocked by #12`, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl task unblock 15 --by 12
```

## fctl task retry

Starts a new run on a task whose latest run failed or was stopped: my **Retry** (task page header,
stalled board card). Reads the latest run with `GET /api/tasks/{id}`, then calls the same
`POST /api/tasks/{id}/run` as Retry and [fctl run](#fctl-run).

**Synopsis**

```
fctl task retry <id> [--account <id|email>]
```

Task ids are global, so it works from any directory, outside a git repo too.

**Arguments and flags**

- `<id>`: the task to retry.
- `--account <id|email>`: the Claude account to run in, by its id or its email, as
  [fctl run](#fctl-run) takes it. Without the flag, no body is sent and the app picks with **Auto**.

**Stdin**

none

**Output**

The same line as [fctl run](#fctl-run):

```
Run #42 on #12 as b@y → http://127.0.0.1:4545/tasks/12
```

**Exit codes and errors**

- `fctl: #12 never ran; use fctl run 12`: the task has no run to retry. Nothing is posted, exit `1`.
- `fctl: run #41 is running on #12; wait for it or stop it`: its latest run is still running.
  Nothing is posted, exit `1`.
- `fctl: 404 Task #99 not found`, exit `1`.
- `fctl: no Claude account b@y`: no account has that email; no run is started, exit `1`.
- Every refusal of `POST /api/tasks/{id}/run` prints as given, as [fctl run](#fctl-run) lists them:
  blocked, the run cap, accounts, and `fctl: 409 #12 is in review` or `fctl: 409 #12 is done`,
  exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me. A run can't call it: agents can't call `fctl run`, `fctl task retry`, `approve`, or `rework`.

**Example**

```sh
fctl task retry 12
fctl task retry 12 --account b@y
```

## fctl task delete

Deletes a task, like the board card's **Delete**. Calls `GET /api/tasks/{id}` for its title, asks to
confirm, then calls `DELETE /api/tasks/{id}`. The app forgets the task's runs, rounds and their files,
verdicts, comments, decisions, status history, and transcript records. Its worktree, branch, run logs,
and copied transcript files stay on disk.

**Synopsis**

```
fctl task delete <id> [--yes]
```

Task ids are global, so it works from any directory.

**Arguments and flags**

- `<id>`: the task.
- `--yes`: delete without asking. Off a terminal (a script, a pipe) it is required.

**Stdin**

On a terminal without `--yes`, one line: the answer to the prompt. `y` or `yes`, in any case, deletes;
anything else, an empty line, or end of input keeps the task. With `--yes` stdin isn't read.

**Output**

Without `--yes`, the prompt first:

```
Delete #14 Export CSV?
This removes its runs, rounds and their files, verdicts, comments, decisions, status history, and transcript records from the app. Its worktree, branch, run logs, and copied transcript files stay on disk.
Delete? [y/N] y
```

Then, once deleted:

```
Deleted #14 Export CSV
```

**Exit codes and errors**

- `fctl: not a terminal; pass --yes to delete #14 without asking`: no `--yes` off a terminal; no
  request is made, exit `1`.
- `fctl: not deleted`: the prompt was answered with anything but `y`; nothing is deleted, exit `1`.
- `fctl: 404 Not Found`: no task #14 (from the title lookup), exit `1`.
- `fctl: 409 run #41 active`: the task's run is running; stop it first, then delete, exit `1`.
- A non-integer `<id>`: a usage error, exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me.

**Example**

```sh
fctl task delete 14 --yes
```

## fctl run

Starts a factory run: `/factory <id>` in the task's worktree. Calls `POST /api/tasks/{id}/run`, or
for `next` `POST /api/projects/{id}/run-next`.

**Synopsis**

```
fctl run <id> [--account <id|email>]
fctl run next
```

**Arguments and flags**

- `<id>`: the task to run. It works from any directory.
- `next`: the top ready task of the current repo's Backlog, skipping blocked ones. It needs the repo.
- `--account <id|email>`: the Claude account to run in, by its id or its email (matched exactly,
  ignoring case, against `GET /api/auth/accounts`), sent as `{"account_id": 2}`. The run uses it even
  when it is near or at its limits. Without the flag, no body is sent and the app picks with **Auto**:
  the preferred (active) account unless its latest usage says it is low (5h at 80% or more, 7d at 90%
  or more, or limited), then the logged-in account with the most headroom. Not with `next`, which
  always uses Auto.

**Stdin**

none

**Output**

The account the run uses, by its email (or its config dir's name):

```
Run #41 on #12 as b@y → http://127.0.0.1:4545/tasks/12
```

The first run on a task creates its worktree, `.claude/worktrees/12-rate-limit-login`, on a new
branch `factory/12-rate-limit-login` from the default branch, with worktrunk (`wt switch --create`,
no hooks). Later runs reuse it. Before every run, new or reused, the app copies the main checkout's
gitignored files (`.env`, `node_modules`, caches) into it with `wt step copy-ignored`, so the
agents' tests run as in the main checkout. It skips files already there, `.venv/`,
`.claude/settings.local.json` (its permissions would widen the run's tools), and `.fctl/`. A
repo's `.worktreeinclude` narrows the copy, as wt does. `wt` must be on PATH: `brew install
worktrunk`.

**Exit codes and errors**

- `fctl: 404 no task #12`, exit `1`.
- `fctl: 409 run #41 is already running on #12; wait for it or stop it`: the task already has a
  running run, exit `1`.
- `fctl: 409 2 runs active (#41 on #12, #42 on #14); the limit is 2. Wait, stop one, or raise it in
  Settings`: the run cap (`max_concurrent_runs`, across all projects) is full, exit `1`.
- `fctl: 409 #12 is in review` or `fctl: 409 #12 is done`, exit `1`.
- `fctl: 409 #15 is blocked by #12, #14; finish those first or remove the dependency`: the task
  waits on tasks that aren't done (only those are named). Finish them, or remove the link with
  [fctl task unblock](#fctl-task-unblock), exit `1`.
- `fctl: 409 factory isn't committed on main: …`: the message names the next step, exit `1`.
- `fctl: 409 this repo runs the file-based /factory loop: …`: the committed SKILL.md isn't the app's
  template, and the message names the fix, exit `1`.
- `fctl: 409 worktree <path> is missing`, exit `1`.
- `fctl: 409 wt (worktrunk) isn't installed: brew install worktrunk, then run again`, exit `1`.
- `fctl: 409 wt switch failed: <wt's first stderr line>`,
  `fctl: 409 wt step copy-ignored failed: <wt's first stderr line>`,
  `fctl: 409 wt switch timed out` (60 s), `fctl: 409 wt step copy-ignored timed out` (300 s), and
  `fctl: 409 wt put the worktree at <path>, expected <path>`, exit `1`. No run starts. A worktree
  made before the refusal stays, so the next run reuses it and copies again.
- `fctl: 409 conf/.env.local is ignored in the main checkout but not on main, so it was left out of
  the worktree: commit its .gitignore line on main, then run again`: the copy added a file the
  worktree doesn't ignore, which would reach the round's diff. The app deletes it from the worktree.
  With several, the first is named, followed by `(and 2 more)`. Exit `1`.
- `fctl: 409 not on subscription auth`, then a second line,
  `Sign in to a Claude account, or make one active, under Settings → Claude accounts, then run again.`:
  no Claude account is signed in to claude.ai (an API-key login doesn't count), exit `1`.
- `fctl: 409 all accounts near their limits: a@x 5h 92% (resets 14:10), b@y limited (resets Nov 15
  16:00)`: Auto found no logged-in account with headroom. Wait for a reset, or pick one with
  `--account`, exit `1`.
- `fctl: 409 Claude account b@y isn't logged in to claude.ai; log it in under Settings → Claude
  accounts, or pick another`: the `--account` one is signed out, exit `1`.
- `fctl: 422 no Claude account #99`: no account has that id, exit `1`.
- `fctl: no Claude account b@y`: no account has that email; no run is started, exit `1`.
- `--account` with `next`: argparse's usage error, exit `2`.
- `fctl: 500 can't start claude: <reason>`, exit `1`.
- `next` only: `fctl: 404 backlog is empty` and
  `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>`, exit `1`.
- `next` only: `fctl: 409 all backlog tasks are blocked: #15 waits on #12, #14`: `next` skips
  blocked tasks and takes the top ready one; with none ready it names the top Backlog task and the
  tasks it waits on, exit `1`.
- A target that is neither a number nor `next`:
  `fctl run: error: target must be a task id or next, not 'abc'`, exit `2`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me. A run can't call it: agents can't call `fctl approve`, `run`, or `rework`, so a run can't
approve its own work or start other runs.

**Example**

```sh
fctl run next
fctl run 12 --account b@y
```

## fctl automation run

Starts an automation by hand (**Run now** on the Workflows page): its compiled skill, `/<slug>`,
headless on the repo itself, with no board task. Calls `POST /api/factories/{id}/run`.

**Synopsis**

```
fctl automation run <id> [--account <id|email>]
```

**Arguments and flags**

- `<id>`: the automation, its id on the Workflows page (`/projects/3/factories/7` is `7`). It works
  from any directory. Not a number: argparse's usage error.
- `--account <id|email>`: the Claude account to run in, by id or email, as for
  [fctl run](#fctl-run). Without it, no body is sent and the app picks with **Auto**.

**Stdin**

none

**Output**

The run, its account, and its worktree, then the Agents page, where it shows under the automation's
name:

```
Run #43 of automation #7 as b@y in .claude/worktrees/automation-security-audit-1a2b3c4d → http://127.0.0.1:4545/agents
```

Every run gets a fresh worktree from the default branch, on a new branch
`automation/<slug>-<first 8 characters of the session id>`, made and filled with the ignored files
as for `fctl run`. Two runs of one automation run side by side; only the run cap limits them. The
worktree and branch stay after the run.

**Exit codes and errors**

- `fctl: 404 Factory #99 not found`, exit `1`.
- `fctl: 409 Review loop is a workflow; run it on a task from the board`, exit `1`.
- `fctl: 409 2 runs active (#41 on #12, #43 on automation Security audit); the limit is 2. Wait,
  stop one, or raise it in Settings`: the run cap is full, exit `1`.
- `fctl: 409 automation Security audit isn't committed on main: open it, Files → Write to repo, then
  on main run git add .claude/skills/security-audit .claude/agents && git commit -m "Add factory"`:
  its `.claude/skills/<slug>/SKILL.md` isn't committed on the default branch, exit `1`.
- `fctl run`'s worktree, account, auth, and spawn refusals, exit `1`. A refusal after the worktree
  is made removes it and its branch again.
- `fctl: no Claude account b@y`: no account has that email; no run is started, exit `1`.

See [Exit codes and errors](#exit-codes-and-errors) for the rest.

**Called by**

me. A run can't call it.

**Example**

```sh
fctl automation run 7
fctl automation run 7 --account b@y
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
- `fctl: 409 run #41 is already running on #12; …` or `fctl: 409 2 runs active (…); the limit is
  2. …`: a factory task is refused while its own run is running or the run cap is full, before
  anything is recorded, exit `1`.
- A factory task's rework run can still be refused after the note is recorded, with
  [fctl run](#fctl-run)'s messages, for example `fctl: 409 not on subscription auth` and its
  second line,
  `Sign in to a Claude account, or make one active, under Settings → Claude accounts, then run again.`,
  exit `1`. The note and the move stay; fix the cause, then start the run again with
  `fctl run <id>`. The rework run always uses Auto; to pick its account, start it with
  `fctl run <id> --account <id|email>` after the refusal.

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
cd ~/code/api-server/.claude/worktrees/12-rate-limit-login
git add -A && git commit -m 'Rate-limit login endpoint'
git push -u origin factory/12-rate-limit-login     # then open a PR, or merge locally
cd ~/code/api-server && wt remove factory/12-rate-limit-login
```

The last line removes the worktree with worktrunk once the work is committed.

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
the pinned context is blank and there are no cards. Then the task's heading and status, a
`Module: <name>` line when the task has a module (none without one), the description, the spec
(`_No spec yet._` if none), and every round:

```
# #12 Rate-limit login endpoint
Status: in_progress · agent_review
Module: backend

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
