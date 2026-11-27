# Workcell

A local control center for Claude Code "software factories": a loop of subagents that
specs a task, builds it in a git worktree, reviews it four ways (security, ux, ui, code),
and hands it to you. Agents never commit. You review the diff, then commit and merge by hand
or with the app's Create PR and Merge PR buttons.

- A kanban board per project, with projects grouped into workspaces.
- A **Run** button that spawns headless Claude Code (`claude -p "/factory <id>"`) on your
  Claude subscription login. Runs never bill per token through the API.
- A GitHub-style review page per task: files changed, +/−, the agent verdicts, and inline
  comments. **Approve** gives you the commit commands. **Request changes** starts a new
  builder round.
- **Create factory**, one click that writes the `/factory` skill and its 7 agents into a
  repo's `.claude/`. Workflows let you design your own loops and automations.
- Local only: a backend on `127.0.0.1:4545` with SQLite and a frontend on `127.0.0.1:3000`.
  No auth, no cloud.

The full design is in [`docs/MVP.md`](docs/MVP.md).

## Requirements

- Python 3.12 via [uv](https://docs.astral.sh/uv/getting-started/installation/), which fetches
  Python 3.12 if you don't have it.
- Node 22 and npm, for the frontend.
- git.
- [worktrunk](https://github.com/max-sixty/worktrunk) (`wt`): runs make each task's worktree
  with it (`brew install worktrunk`).
- [Claude Code](https://claude.com/claude-code), signed in with a Claude subscription. Runs
  refuse to start on an API key (docs/MVP.md §4.3).

macOS and Linux are supported. With Docker you need only Docker with Compose (see
[Run with Docker](#run-with-docker)).

## Install

```sh
git clone https://github.com/ArtemKucheruk/workcell.git
cd workcell
uv tool install --editable .     # puts `fctl` on your PATH (~/.local/bin)
fctl --help
```

With `--editable`, `fctl` always runs the code in your checkout, so a `git pull` is enough
to update. If the dependencies in `pyproject.toml` change, run
`uv tool install --editable --reinstall .`. To remove it, run
`uv tool uninstall workcell`.

If `fctl` isn't found, run `uv tool update-shell` and open a new terminal.

### Upgrading from claude-factories

The app used to be called Claude Factories. In your checkout, after pulling:

```sh
uv tool uninstall claude-factories
uv tool install --editable .
fctl service install      # removes the old com.claude-factories / claude-factories-* services first
```

The old backend keeps running on port 4545 until that last command stops it, so run all three.

On the first start, the data in `~/.claude-factories` moves to `~/.workcell`, and the old
path stays as a symlink to it, so signed-in accounts and every task's history carry over.

## Run the app

Install the backend and the frontend once as background services (launchd on macOS,
`systemd --user` on Linux). They start at login, restart if they crash, and keep running
when you close the terminal:

```sh
fctl service install      # builds the frontend if needed, then starts both
fctl service reload       # after a git pull or merge: npm ci if the lockfile changed, build, restart
fctl service status       # running or not, pid, uptime, URL, served commit vs main, active runs
fctl service logs -f      # tail ~/.workcell/logs/{backend,frontend}.log
```

The app opens at http://127.0.0.1:3000. `stop`, `restart`, `reload`, and `uninstall` refuse
while a run is active, since restarting the backend stops every run; `--force` goes on anyway.
`fctl service install` needs the editable install above. Every subcommand is in
[fctl.md](src/workcell/fctl.md).

Or run the backend in the foreground:

```sh
fctl serve                # http://127.0.0.1:4545
fctl serve --port 5000    # another port
```

Press Ctrl-C to stop it. The frontend server runs next to it:
`npm --prefix frontend ci && npm --prefix frontend run build && node frontend/server.js`
(http://127.0.0.1:3000). The first start creates the data dir and `factory.db` in it.

| env var | default | used for |
|---|---|---|
| `FCTL_HOME` | `~/.workcell` | the data dir: `factory.db`, run logs, and the services' logs |
| `FCTL_URL` | `http://127.0.0.1:4545` | where `fctl` sends its API calls; set it if you changed `--port` |
| `FCTL_IN_DOCKER` | unset | `1` in the backend image, where the takeover command becomes `docker compose exec …` |

### Run with Docker

You need Docker with Compose. In the repo:

```sh
docker compose up --build
```

The app opens at http://127.0.0.1:3000. The backend is on `127.0.0.1:4545` as before, so
`fctl` on the host needs no change. Both are published on 127.0.0.1 only.

An override file is optional. It's for other host ports, your uid:gid, project mounts, and a
custom image:

```sh
cp compose.override.example.yaml compose.override.yaml
```

A project can be connected from Docker only once its root is mounted, so before you connect
one, edit `compose.override.yaml`: set `user:` to your `id -u`:`id -g`, and mount every folder
that holds a connected project at its own path (`/path/to/code:/path/to/code`). That file is
gitignored. To use other ports, change the left number of its `ports: !override` items (Docker
Compose v2.24.4 or later). If you change the backend port, `fctl` on the host needs
`FCTL_URL=http://127.0.0.1:<port>`.

The app's data lives in the `fctl-home` Docker volume, not in
`~/.workcell`. `docker compose down` stops it, and `docker compose down -v` also
deletes the data. `fctl service` doesn't apply here: run `docker compose up -d` to keep the app in
the background, and `docker compose restart` after a pull.

Runs happen inside the backend container, on a Claude login of its own: your host login stays
in the macOS Keychain, which the container can't read. Log in once, with the app up, in a
second terminal:

```sh
docker compose exec backend claude auth login    # sign in with your Claude subscription
docker compose exec backend claude auth status   # check it: "authMethod": "claude.ai"
```

Until you do, the header shows the red `Not signed in — runs disabled` and Run is refused. The
login lives in the `backend-home` volume, the container's home, so restarts and rebuilds keep
it, and `docker compose down -v` deletes it. Settings (`/settings`) can also log in from the
browser, and hold more Claude accounts, with one active for runs.

Runs get git, uv, node, and npm. If a project's test command needs anything else, build your
own image `FROM workcell-backend`. The steps are in the comments of
`compose.override.example.yaml`.

To take over a stopped run, the task page gives a command like
`docker compose exec -w <worktree> -e CLAUDE_CONFIG_DIR=<account dir> backend claude --resume <session-id>`.
Run it from this checkout, next to `compose.yaml`.

## Connect a repo

1. `fctl setup` installs the `/factory-connect`, `/factory-submit`, and `fctl` skills into
   `~/.claude/skills/`.
2. In the repo, run `/factory-connect <workspace>` in Claude Code, or
   `fctl connect --workspace personal --test-cmd "pytest -q"`. The workspace is created if
   it's new.
3. In the app, open the project's Settings → **Create factory**, then commit `.claude/` on the
   default branch. Runs refuse until the factory is committed there.

### Moving a checkout

The app knows a project by its main checkout's path. To move or rename that folder and keep the
project's tasks and history:

1. Wait until none of the project's runs are going, then move the folder.
2. In the moved folder, run `git worktree repair` so git finds any remaining task worktrees again.
3. In the app, open the project's Settings and change **Path** to the new folder.
4. If it is this app's own checkout, also run `uv tool install --editable --reinstall .` and
   `fctl service install` from the new folder.

## A first task and run

1. Add a task: **+ New task** on the board, or in the repo
   `fctl task add "Rate-limit login endpoint" --description "Max 5 failed logins per minute per IP."`.
2. Start it: **Run** on the card, or `fctl run <id>` (`fctl run next` takes the top of the
   Backlog; `fctl task add … --run` adds and runs in one step).
3. Watch the card move through spec, build, and agent review. `fctl show <id>` prints the task,
   its spec, and every round's build notes and verdicts.
4. When it reaches Review, open its review page. **Approve** (or `fctl approve <id>`) marks it
   done and prints the git commands to commit; **Request changes** (or `fctl rework <id> "note"`)
   starts a new builder round with your note.

The full walkthrough is in [docs/MVP.md §3](docs/MVP.md#3-user-flows), and every command is in
[fctl.md](src/workcell/fctl.md).

## Security

- The backend has no auth. It must stay on 127.0.0.1: it rejects requests whose `Host` isn't
  `127.0.0.1` or `localhost`, and every write needs the `X-Requested-By: fctl` header
  (docs/MVP.md §4.5). Don't bind it to `0.0.0.0` or expose its port outside your machine;
  `--host 0.0.0.0` is only for inside the Docker container.
- Runs execute Claude Code agents with shell access inside your repos: they edit files and run
  commands (your test command among them) in each task's worktree, as your user. Connect only
  repos you trust, and review every diff before you commit it.

## Demo data

`fctl seed` fills an empty data dir with demo data: two workspaces, three projects backed by small
git repos, and tasks in every status and stage, with rounds, reviews, comments, and finished runs
with their logs. Every page has something to show without running an agent. It refuses a data dir
that already has a workspace, so the demo always gets a data dir of its own.

On the host, with your own `fctl serve` stopped (both use port 4545):

```sh
FCTL_HOME=~/.workcell-demo fctl seed
FCTL_HOME=~/.workcell-demo fctl serve
```

Then start the frontend server next to it (`node frontend/server.js`, see
[Developing the app](#developing-the-app)) and open http://127.0.0.1:3000. To delete the demo,
stop the server and run `rm -rf ~/.workcell-demo`.

With Docker, run the demo as a separate compose project. It gets its own `fctl-home` and
`backend-home` volumes, so your real data is never touched:

```sh
docker compose down                                   # your app; its data stays in its volumes
docker compose -p workcell-demo up --build -d
docker compose -p workcell-demo exec backend fctl seed
```

Open http://127.0.0.1:3000. The demo container has no Claude login, so its header shows
`Not signed in — runs disabled`. When you're done, `docker compose -p workcell-demo down -v`
deletes the demo, and `docker compose up` brings your own app back.

## The factory loop

```
task
  → spec-writer    the task's spec: goal, testable acceptance criteria, open questions
  → builder        implements in .claude/worktrees/<id>-<slug>, runs the tests, fctl submit <id>
  → 4 reviewers    security · ux · ui · code, in parallel, each PASS or CHANGES
      ↺ any CHANGES → builder again (at most 2 rounds per run)
  → approver       APPROVE → review · human_review, ESCALATE → review · escalated
  → you            Approve: commit and merge yourself, or with Create PR / Merge PR
                   Request changes <note>: a rework run with your feedback
```

| agent | model | posts |
|---|---|---|
| `spec-writer` | opus | the spec (`fctl spec`) |
| `builder` | opus | code in its worktree, then a round with build notes (`fctl submit`) |
| `review-security` | opus | a verdict and line comments (`fctl verdict`, `fctl comment`) |
| `review-ux` | sonnet | a verdict and line comments |
| `review-ui` | sonnet | a verdict and line comments |
| `review-code` | sonnet | a verdict and line comments (it also runs the tests) |
| `approver` | opus | the decision (`fctl decide`) |

Rules that hold everywhere:
- Agents read their context with `fctl show`, not from the conversation, and all state lives
  in the app's database, not in files in the repo.
- Nobody but you commits, pushes, merges, rebases, or switches branches: git write commands are
  denied in runs. Each task gets its own worktree, so tasks run in parallel up to the run cap
  in Settings.

[`.claude/skills/factory/SKILL.md`](.claude/skills/factory/SKILL.md) is how the orchestrator
runs the loop, and [`docs/claude-code.md`](docs/claude-code.md) §7 describes the skills and
agent templates.

## Developing the app

The stack is Python 3.12 with [uv](https://docs.astral.sh/uv/), FastAPI, and stdlib
`sqlite3`. The `fctl` CLI imports only the stdlib. The frontend in `frontend/` is a Vite +
React SPA with Tailwind v4, built with Node 22 and npm. Backend code follows the layout and
import rules in `docs/MVP.md §4.7`, and `tests/test_architecture.py` checks its imports.

You don't need the global install to work on the app itself:

```sh
uv sync                  # creates .venv with runtime and dev dependencies
uv run fctl serve        # runs the backend from .venv on 127.0.0.1:4545
uv run pytest -q         # tests
```

The frontend, with the backend running:

```sh
npm --prefix frontend ci         # installs the frontend's dependencies
npm --prefix frontend run dev    # dev server on http://localhost:5173
npm --prefix frontend test       # frontend tests
npm --prefix frontend run build && node frontend/server.js   # the built app on http://127.0.0.1:3000
```

Both the dev server and `frontend/server.js` send `/api` to `FCTL_API_URL`
(default `http://127.0.0.1:4545`). `server.js` also reads `HOST` (default `127.0.0.1`) and
`PORT` (default `3000`).

Each test gets a temp `FCTL_HOME` and a fake `claude` on `PATH`. Tests never call the real
`claude`, the network, or `~/.claude*`. Frontend tests mock `fetch`, and `server.test.js` runs
against a fake backend on 127.0.0.1.

## Layout

```
src/workcell/   app (FastAPI), fctl CLI, schema.sql, factory templates
frontend/               the React SPA and its server.js
tests/
docs/                   the design, which is the source of truth for what to build
.claude/skills/factory/ this repo's /factory orchestrator (written by Create factory)
.claude/agents/         its 7 subagents
.claude/worktrees/      one checkout per task (gitignored)
```

## Docs

| file | covers |
|---|---|
| [`docs/MVP.md`](docs/MVP.md) | §1 overview · §2 concepts · §3 user flows · §4 architecture · §9 scope · §10 open questions |
| [`docs/data-model-and-api.md`](docs/data-model-and-api.md) | §5 data model · §6 API |
| [`docs/claude-code.md`](docs/claude-code.md) | §7 Claude Code integration: `fctl`, skills, agent templates |
| [`docs/ui.md`](docs/ui.md) | §8 screens and wireframes |
| [`docs/fctl_docs/`](docs/fctl_docs/README.md) | a guide to `fctl` for people and agents |
| [`src/workcell/fctl.md`](src/workcell/fctl.md) | every `fctl` command, also served at `/docs/fctl` |

Specs cite these sections, for example `docs/data-model-and-api.md §6.2`.

## License

MIT. See [LICENSE](LICENSE).

Workcell is an independent project. It is not affiliated with or endorsed by Anthropic.
