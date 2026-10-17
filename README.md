# Claude Factories

A local control center for Claude Code "software factories": a loop of subagents that
specs a feature, builds it in a git worktree, reviews it four ways, and hands it to you.
Claude never commits. You review the diff and commit yourself.

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

```sh
fctl serve                # http://127.0.0.1:4545
fctl serve --port 5000    # another port
```

Open http://127.0.0.1:4545 in your browser and press Ctrl-C to stop. The first start
creates the data dir and `factory.db` in it.

| env var | default | used for |
|---|---|---|
| `FCTL_HOME` | `~/.claude-factories` | the data dir: `factory.db`, and run logs once runs exist |
| `FCTL_URL` | `http://127.0.0.1:4545` | where `fctl` sends its API calls; set it if you changed `--port` |

The app listens only on 127.0.0.1. It rejects requests whose `Host` isn't `127.0.0.1` or
`localhost`, and it refuses any write that lacks the `X-Requested-By: fctl` header
(docs/MVP.md §4.5).

**What works today:** `fctl serve` with a placeholder home page. The rest of the setup
below is designed but not built yet. Each step lists the backlog job that adds it:

```sh
fctl setup                  # 015: installs the /factory-connect and /factory-submit skills
/factory-connect personal   # 002: run in a repo's Claude Code session to register the repo
                            # 011: board → Create factory writes .claude/ into the repo
```

The full walkthrough, from connecting a repo to approving a task, is in
[docs/MVP.md §3](docs/MVP.md#3-user-flows).

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

The stack is Python 3.12 with [uv](https://docs.astral.sh/uv/), FastAPI, stdlib `sqlite3`,
and Jinja2 with htmx. There is no frontend build. The `fctl` CLI imports only the stdlib.

You don't need the global install to work on the app itself:

```sh
uv sync                  # creates .venv with runtime and dev dependencies
uv run fctl serve        # runs the app from .venv
uv run pytest -q         # tests
```

Each test gets a temp `FCTL_HOME` and a fake `claude` on `PATH`. Tests never call the real
`claude`, the network, or `~/.claude*`.

## Layout

```
src/claude_factories/   app (FastAPI), fctl CLI, schema.sql, templates/, vendored static/
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
