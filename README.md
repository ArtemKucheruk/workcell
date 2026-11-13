# Claude Factories

A local control center for Claude Code "software factories": a loop of subagents that
specs a feature, builds it in a git worktree, reviews it four ways, and hands it to you.
Agents never commit. You review the diff, then commit and merge by hand or with the app's
Create PR and Merge PR buttons.

> **Status: early.** The app is being built by its own bootstrap factory, a file-based
> version of the same loop that lives in [`factory/`](factory/). Job 001 (package layout,
> `fctl serve`, schema, local-safety middleware) is done. What's next is in
> [`factory/backlog.md`](factory/backlog.md).

## What it will be

- A kanban board per project, with projects grouped into workspaces.
- A **Run** button that spawns headless Claude Code (`claude -p "/factory <id>"`) on your
  Claude Pro login. Runs never bill per token through the API.
- A GitHub-style review page per task: files changed, +/−, the agent verdicts, and inline
  comments. **Approve** gives you the commit commands. **Request changes** starts a new
  builder round.
- **Create factory**, one click that writes the `/factory` skill and its 7 agents into a
  repo's `.claude/`.
- Local only: one process on `127.0.0.1:4545` with SQLite. No auth, no cloud.

The full design is in [`docs/MVP.md`](docs/MVP.md).

## Install

You need:
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which fetches Python 3.12
  if you don't have it
- git
- [Claude Code](https://claude.com/claude-code), logged in with a Claude subscription. Runs
  will refuse to start on an API key (docs/MVP.md §4.3).

```sh
git clone https://github.com/ArtemKucheruk/claude-factories.git
cd claude-factories
uv tool install --editable .     # puts `fctl` on your PATH (~/.local/bin)
fctl --help
```

With `--editable`, `fctl` always runs the code in your checkout, so a `git pull` is enough
to update. If the dependencies in `pyproject.toml` change, run
`uv tool install --editable --reinstall .`. To remove it, run
`uv tool uninstall claude-factories`.

If `fctl` isn't found, run `uv tool update-shell` and open a new terminal.

## Run the app

Install the backend and the frontend once as background services (launchd on macOS,
`systemd --user` on Linux). They start at login, restart if they crash, and keep running
when you close the terminal:

```sh
fctl service install      # builds the frontend if needed, then starts both
fctl service reload       # after a git pull or merge: npm ci if the lockfile changed, build, restart
fctl service status       # running or not, pid, uptime, URL, served commit vs main, active runs
fctl service logs -f      # tail ~/.claude-factories/logs/{backend,frontend}.log
```

The app opens at http://127.0.0.1:3000. `stop`, `restart`, `reload`, and `uninstall` refuse
while a run is active, since restarting the backend stops every run; `--force` goes on anyway.
`fctl service install` needs the editable install above. Every subcommand is in
[fctl.md](src/claude_factories/fctl.md).

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
| `FCTL_HOME` | `~/.claude-factories` | the data dir: `factory.db`, and run logs once runs exist |
| `FCTL_URL` | `http://127.0.0.1:4545` | where `fctl` sends its API calls; set it if you changed `--port` |
| `FCTL_IN_DOCKER` | unset | `1` in the backend image, where the takeover command becomes `docker compose exec …` |

The app listens on 127.0.0.1 by default. `--host 0.0.0.0` is the Docker container's setting,
not one to use on the host. The app rejects requests whose `Host` isn't `127.0.0.1` or
`localhost`, and it refuses any write that lacks the `X-Requested-By: fctl` header
(docs/MVP.md §4.5).

To use the app on a repo:

1. `fctl setup` installs the `/factory-connect` and `/factory-submit` skills.
2. In the repo, run `/factory-connect <workspace>` in Claude Code, or
   `fctl connect --workspace W --test-cmd "<cmd>"`.
3. Project Settings → **Create factory**, then commit `.claude/` on the default branch.
4. `fctl task add "<title>" [--description TEXT] [--run]`, or **+ New task** on the board.

The full walkthrough, from connecting a repo to approving a task, is in
[docs/MVP.md §3](docs/MVP.md#3-user-flows).

## Run with Docker

You need Docker with Compose. In the repo:

```sh
cp compose.override.example.yaml compose.override.yaml && docker compose up --build
```

Before the first `up`, edit `compose.override.yaml`: set `user:` to your `id -u`:`id -g`, and
mount every folder that holds a connected project at its own path (`/Users/you/code:/Users/you/code`).
That file is gitignored, and it publishes both servers on 127.0.0.1 only.

The app opens at http://127.0.0.1:3000. The backend is on `127.0.0.1:4545` as before, so
`fctl` on the host needs no change. Its data lives in the `fctl-home` Docker volume, not in
`~/.claude-factories`. `docker compose down` stops it, and `docker compose down -v` also
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
own image `FROM claude-factories-backend`. The steps are in the comments of
`compose.override.example.yaml`.

To take over a stopped run, the task page gives a command like
`docker compose exec -w <worktree> -e CLAUDE_CONFIG_DIR=<account dir> backend claude --resume <session-id>`.
Run it from this checkout, next to `compose.yaml`.

## Demo data

`fctl seed` fills an empty data dir with demo data: two workspaces, three projects backed by small
git repos, and tasks in every status and stage, with rounds, reviews, comments, and finished runs
with their logs. Every page has something to show without running an agent. It refuses a data dir
that already has a workspace, so the demo always gets a data dir of its own.

On the host, with your own `fctl serve` stopped (both use port 4545):

```sh
FCTL_HOME=~/.claude-factories-demo fctl seed
FCTL_HOME=~/.claude-factories-demo fctl serve
```

Then start the frontend server next to it (`node frontend/server.js`, see
[Developing the app](#developing-the-app)) and open http://127.0.0.1:3000. To delete the demo,
stop the server and run `rm -rf ~/.claude-factories-demo`.

With Docker, run the demo as a separate compose project. It gets its own `fctl-home` and
`backend-home` volumes, so your real data is never touched:

```sh
docker compose down                                   # your app; its data stays in its volumes
docker compose -p claude-factories-demo up --build -d
docker compose -p claude-factories-demo exec backend fctl seed
```

Open http://127.0.0.1:3000. The demo container has no Claude login, so its header shows
`Not signed in — runs disabled`. When you're done, `docker compose -p claude-factories-demo down -v`
deletes the demo, and `docker compose up` brings your own app back.

## The factory loop

```
feature
  → spec-writer    spec.md: goal, doc sections, testable acceptance criteria, open questions
  → builder        implements in .claude/worktrees/<id>, runs the tests, writes build.md
  → 4 reviewers    security · ux · ui · code, in parallel, each PASS or CHANGES
      ↺ any CHANGES → builder again (at most 2 rounds per run)
  → approver       APPROVE → human_review · ESCALATE → escalated
  → you            approve: commit and merge yourself
                   rework <note>: new builder round with your feedback
```

| agent | model | writes |
|---|---|---|
| `spec-writer` | opus | `spec.md` |
| `builder` | opus | code in its worktree, `round-N/build.md` |
| `review-security` | opus | `round-N/review-security.md` |
| `review-ux` | sonnet | `round-N/review-ux.md` |
| `review-ui` | sonnet | `round-N/review-ui.md` |
| `review-code` | sonnet | `round-N/review-code.md` (it also runs the tests) |
| `approver` | opus | `decision.md` |

Rules that hold everywhere:
- Agents get their context from files, not from the conversation, and each writes only its
  own file.
- One job per terminal. Run `/factory next` in another terminal to start a second job; it
  skips backlog lines that need code from, or would edit the same code as, an unfinished job.
- Nobody but you commits, pushes, merges, rebases, or switches branches. The orchestrator's
  only git write is `git worktree add`.

[`FACTORY.md`](FACTORY.md) is the design of the loop, and
[`.claude/skills/factory/SKILL.md`](.claude/skills/factory/SKILL.md) is how the
orchestrator runs it. To change the factory, edit those two files.

## Running the bootstrap factory

You need [Claude Code](https://claude.com/claude-code), git, and Python 3. In a Claude
Code session at the repo root:

| command | does |
|---|---|
| `/factory next` | runs the first unchecked line in `factory/backlog.md` that no active job blocks |
| `/factory <feature>` | adds a job with the next free id and runs it |
| `/factory resume [<id>]` | continues an in-progress job whose session ended |
| `/factory approve <id>` | marks the job done, ticks the backlog, and prints your git commands |
| `/factory rework <id> <note>` | saves your note as feedback and runs a new builder round |

`/factory approve` prints commands like these for you to run:

```sh
git -C .claude/worktrees/<id> add -A
git -C .claude/worktrees/<id> commit -m "<title>"
git merge --ff-only factory/<id>
git worktree remove .claude/worktrees/<id> && git branch -d factory/<id>
```

Don't commit to `main` before the merge, or `--ff-only` fails.

To watch the board, start the dashboard. It polls `factory/board.json`, and clicking a card
shows its spec, build notes, reviews, decision, and diff.

```sh
python3 -m http.server -b 127.0.0.1 -d factory
# → http://127.0.0.1:8000/dashboard.html
```

## Developing the app

The stack is Python 3.12 with [uv](https://docs.astral.sh/uv/), FastAPI, and stdlib
`sqlite3`. The `fctl` CLI imports only the stdlib. The frontend in `frontend/` is a Vite +
React SPA with Tailwind v4, built with Node 22 and npm.

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
src/claude_factories/   app (FastAPI), fctl CLI, schema.sql
tests/
docs/                   the design, which is the source of truth for what to build
FACTORY.md              the bootstrap factory's design
.claude/skills/factory/ the /factory orchestrator
.claude/agents/         the 7 subagents
.claude/worktrees/      one builder checkout per job (git-excluded)
factory/                board.json, backlog.md, dashboard.html, jobs/<id>/ (spec, rounds, decision)
```

## Docs

| file | covers |
|---|---|
| [`docs/MVP.md`](docs/MVP.md) | §1 overview · §2 concepts · §3 user flows · §4 architecture · §9 scope · §10 open questions |
| [`docs/data-model-and-api.md`](docs/data-model-and-api.md) | §5 data model · §6 API |
| [`docs/claude-code.md`](docs/claude-code.md) | §7 Claude Code integration: `fctl`, skills, agent templates |
| [`docs/ui.md`](docs/ui.md) | §8 screens and wireframes |

Specs cite these sections, for example `docs/data-model-and-api.md §6.2`.

After backlog job 015 the app can run factories itself. At that point this repo gets
connected to the app with `/factory-connect`, and `factory/` retires along with the
file-based loop.
