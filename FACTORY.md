Build a simple, visual "software factory" in this repo using a Claude Code skill,
subagents, and markdown files. Its first product is this repo's own app, Claude Factories,
which is designed in docs/ (start at docs/MVP.md). Keep the factory small: a viewer should
understand the whole thing in a few minutes.

This is the bootstrap factory. State lives in files, because the app that will hold it
doesn't exist yet. It follows the app's rules (worktrees, agents never touch git, I approve)
with one difference: the orchestrator commits each job to its branch and opens a GitHub PR
against main, and my approve merges that PR. Moving it into the app later changes where the
state lives, not how the loop works.

## The repo and its stack

The repo holds only docs; job 001 creates the project. Don't infer the stack from the repo.
Use this one (docs/MVP.md §4.2):
- Python 3.12, managed with uv. The package is `claude_factories` and the console script is `fctl`.
- FastAPI and uvicorn. stdlib sqlite3 with one `schema.sql` applied at startup, in WAL mode. No ORM.
- The frontend in `frontend/`: a Vite + React SPA in plain JSX, Tailwind v4, react-router,
  and highlight.js from npm, tested with vitest + @testing-library/react + jsdom.
  `frontend/server.js` serves the built SPA and proxies `/api` to the backend, on
  `node:http` with no extra dependencies. Node 22 and npm.
- markdown-it-py with raw HTML turned off.
- The `fctl` CLI module imports only the stdlib.
- Backend code follows the layout and import rules in `docs/MVP.md §4.7`, and
  `tests/test_architecture.py` checks its imports.
- Runtime dependencies: fastapi, uvicorn, jinja2, markdown-it-py. Dev dependencies: pytest,
  httpx. Any other dependency needs a reason in the spec.
- npm dependencies: react, react-dom, react-router, highlight.js. Dev dependencies: vite,
  @vitejs/plugin-react, tailwindcss, @tailwindcss/vite, vitest, @testing-library/react,
  jsdom. `server.js` uses Node built-ins only. Any other package needs a reason in the spec.
- Test commands: `uv run pytest -q`, plus `npm --prefix frontend test` once
  `frontend/package.json` exists. Tests use a temp data dir (`FCTL_HOME`) and a fake
  `claude` on PATH. They never call the real `claude`, the network, or `~/.claude*`, and
  `CLAUDE_CONFIG_DIR` points into the test's temp dir.
  Frontend tests mock fetch and never call the backend or the network.

docs/ is the source of truth for what to build. Specs cite doc sections, for example
`docs/data-model-and-api.md §6.2`. The table at the top of docs/MVP.md says which file
holds which section.

## The orchestrator

The factory is one skill, /factory. Whichever Claude Code session runs it becomes the
orchestrator of one job. It runs the loop below, spawns every agent, creates worktrees, and
writes its job's entry in factory/board.json. To run a second job alongside, I run
/factory next in another terminal.

## The loop (edit this to change the factory)

                   ┌──────────────────┐
                   │     feature      │
                   └─────────┬────────┘
                             ▼
                   ┌──────────────────┐
                   │   spec-writer    │
                   │       opus       │
                   └─────────┬────────┘
                             ▼ the spec's builds pick one or both
    ┌─────────────────────────────────────────────────┐
    │  ┌──────────────────┐     ┌──────────────────┐  │
    │  │ builder-backend  │     │ builder-frontend │  │◄────┐
    │  │       opus       │     │ opus + frontend- │  │     │
    │  │ outside frontend/│     │   design skill   │  │     │
    │  └──────────────────┘     └──────────────────┘  │     │
    │    one or both, side by side in one worktree    │     │
    └────────────────────────┬────────────────────────┘     │
        ┌─────────────┬──────┴──────┬─────────────┐         │
        ▼             ▼             ▼             ▼         │
  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
  │  security │ │     ux    │ │ ui design │ │    code   │   │
  │    opus   │ │   haiku   │ │   haiku   │ │   sonnet  │   │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘   │
        └─────────────┴──────┬──────┴─────────────┘         │
                             ▼                              │
                   ┌──────────────────┐   any CHANGES:      │
                   │   WAIT FOR ALL   ├─────────────────────┤
                   │   4 reviews in   │   resume builders   │
                   └─────────┬────────┘   (max 2 rounds)    │
                             ▼ all PASS / rounds used up    │
                   ┌──────────────────┐                     │
                   │     approver     │                     │
                   │       opus       │                     │
                   └─┬───────────────┬┘                     │
             APPROVE │               │ ESCALATE             │
                     ▼               ▼                      │
              ┌─────────────┐ ┌─────────────┐               │
              │human_review │ │  escalated  │               │
              └──────┬──────┘ └──────┬──────┘               │
                     └───────┬───────┘                      │
                             ▼                              │
                   ┌──────────────────┐                     │
                   │ commit, push,    │                     │
                   │ open/update PR   │                     │
                   └─────────┬────────┘                     │
                             ▼ waits on me                  │
                   ┌──────────────────┐ /factory rework     │
                   │ I read the job + ├─────────────────────┘
                   │     the PR       │ (new round)
                   └─────────┬────────┘
                             ▼ /factory approve
                   ┌──────────────────┐
                   │ done: PR merged, │
                   │ worktree removed │
                   └──────────────────┘

## Stages and statuses

These are the same as the app's (docs/data-model-and-api.md §5.2), so board.json maps
one-to-one onto the app's tables later.

| stage | status |
|---|---|
| — | backlog |
| spec, build, agent_review, approval, rework | in_progress |
| human_review, escalated | review |
| — | done |

## Target file system

.claude/
  skills/factory/SKILL.md          # the orchestrator's instructions
  agents/                          # one file per agent in the loop
  worktrees/004-submit/            # builder's checkout, branch factory/feat/004-submit
factory/
  board.json                       # durable state, drives the dashboard
  dashboard.html                   # visual board, polls board.json
  backlog.md                       # ordered queue for /factory next (seed below)
  jobs/004-submit/                 # one folder per job
    spec.md
    round-1/                       # one folder per review round
      build-backend.md             # builder-backend: what changed, criteria → tests, test output
      build-frontend.md            # builder-frontend: the same, plus its design choices
      build.md                     # orchestrator: the build-*.md files joined
      diff.patch                   # orchestrator: worktree snapshot vs its base on main
      review-security.md           # one file per reviewer
      review-ux.md
      review-ui.md
      review-code.md
    feedback-2.md                  # my /factory rework note, numbered by the round it starts
    decision.md

## Agents

| agent | model | tools | reads | writes |
|---|---|---|---|---|
| spec-writer | opus | Read, Grep, Glob, Write | the feature or backlog line, docs/, code on main (the job's fresh worktree) | `spec.md` |
| builder-backend | opus | Read, Edit, Write, Grep, Glob, Bash | `spec.md` (Backend build, API contract), the last round's reviews, `feedback-N.md` | code outside `frontend/` in its worktree, `round-N/build-backend.md` |
| builder-frontend | opus, frontend-design skill | same | `spec.md` (Frontend build, API contract), docs §8, the last round's reviews, `feedback-N.md` | `frontend/` in its worktree, `round-N/build-frontend.md` |
| review-security | opus | Read, Grep, Glob, Bash, Write | spec, build.md, diff.patch, worktree | `round-N/review-security.md` |
| review-ux | haiku | same | same | `round-N/review-ux.md` |
| review-ui | haiku | same | same | `round-N/review-ui.md` |
| review-code | sonnet | same | same, plus it runs the tests in the worktree | `round-N/review-code.md` |
| approver | opus | Read, Grep, Glob, Write | the whole job folder | `decision.md` |

What each one does:
- **spec-writer** writes the goal, the doc sections the job implements, and the work
  split into a Backend build (everything outside `frontend/`) and a Frontend build
  (`frontend/`), each with its acceptance criteria (each one testable) and files, what's
  out of scope, and open questions. It leaves out a build the job doesn't need, and when
  the job has both, it writes the API contract between them. Anything the docs don't
  decide goes under open questions, never guessed silently.
- **the orchestrator picks the builders**: in round 1, one per build section in the spec;
  in later rounds, by where the findings are (`frontend/` or a page → frontend, anything
  else → backend, unsure → both). Picked builders run side by side in the job's one
  worktree, since they own disjoint files. When they're done, it joins their
  `build-<side>.md` files into `build.md`, which the reviewers, the approver, and
  `fctl import-factory` read.
- **builder-backend** implements the Backend build, runs `uv run pytest -q`, and maps each
  criterion to its test in build-backend.md. Endpoints follow the API contract exactly. In
  a job with no Frontend build, it still builds the frontend once for the reviewers
  (`npm --prefix frontend ci` if needed, `npm --prefix frontend run build`) without
  editing it.
- **builder-frontend** implements the Frontend build with the frontend-design skill
  preloaded (plugin `frontend-design@claude-plugins-official`): the skill decides what the
  spec, docs §8 and its wireframes, and the theme leave open; where they decide, they win.
  It tests against the API contract with mocked fetch, runs `npm --prefix frontend ci` if
  `frontend/node_modules` is missing, the frontend tests, then `npm --prefix frontend run
  build`, leaving `node_modules/` and `dist/` in place for the reviewers.
- **security** checks docs §4.5 (127.0.0.1 bind, Host and `X-Requested-By` checks, raw
  HTML off in markdown, path containment, the 5 MB limit). Subprocesses must take argument
  lists, never shell strings. It also checks env stripping and the subscription-only auth
  check (§4.3), and the allow/deny lists for runs (§4.4).
- **ux** reviews the docs §3 flows and the CLI's ergonomics: `fctl` output, error messages,
  and exit codes. It clicks through the web parts in a real browser. If the job changes
  nothing a user sees, it writes `VERDICT: PASS` with "nothing user-facing".
- **ui** reviews pages against docs §8 and its wireframes, including empty and error states
  and light/dark, by screenshotting them in a real browser. If the job has no UI, it writes
  `VERDICT: PASS` with "no UI in this job".
- ux and ui start the job's backend with `fctl serve --port <free port>`. When the worktree
  has `frontend/`, they also start the frontend server on a second free port, pointed at
  that backend (`HOST=127.0.0.1 PORT=<port> FCTL_API_URL=http://127.0.0.1:<backend port>
  node server.js`), and drive the browser against the frontend. They never install or
  build; the builders already did. They drive headless Chrome with `playwright-cli`
  (`npm install -g @playwright/cli`), one `-s=<job-id>-<reviewer>` session each, from a temp
  dir so its output stays out of the worktree.
  If the diff touches nothing under `frontend/`, the orchestrator skips review-ui and writes
  its PASS file itself. review-ux always runs, because it also reviews `fctl` output and
  errors.
- **code** checks the stack and conventions above, runs both test commands, and checks that
  every acceptance criterion has a passing test and that there are no unrequested
  abstractions or dependencies, Python or npm.
- **approver** writes APPROVE or ESCALATE. It escalates if CHANGES remain after round 2,
  tests fail, the work conflicts with docs/, or an open question changed behavior.

## Example files

.claude/agents/review-code.md  (Claude Code subagent syntax)
---
name: review-code
description: Code review of the latest round of a factory job. Use after the builders finish a round.
tools: Read, Grep, Glob, Bash, Write
model: sonnet
---
Input: a job id and its round folder. Read spec.md, round-N/build.md, round-N/diff.patch,
and the files in .claude/worktrees/<job-id>. Run `uv run pytest -q` in that worktree, and
`npm --prefix frontend test` if it has `frontend/package.json`.
Check the stack and conventions in FACTORY.md, that every acceptance criterion has a
passing test, and that nothing unrequested was added. Write only round-N/review-code.md:
first line VERDICT: PASS or VERDICT: CHANGES, then findings as file:line, problem, fix.

factory/board.json
{ "jobs": [ { "id": "004-submit", "title": "fctl submit and review rounds",
  "status": "in_progress", "stage": "agent_review", "round": 2,
  "branch": "factory/feat/004-submit", "worktree": ".claude/worktrees/004-submit",
  "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" },
  "history": [ { "at": "2026-10-17T10:03:00Z", "status": "in_progress", "stage": "spec" } ] } ] }

## Rules
- Agents get context from files, not the conversation, and write only their own file.
- Each review starts with `VERDICT: PASS` or `VERDICT: CHANGES`. decision.md starts with
  APPROVE or ESCALATE.
- One job per terminal. `/factory next` starts one job; run in another terminal while
  jobs are active, it starts the first backlog line that can safely run alongside them: one
  that doesn't need code from, or edit the same part of a file as, a job that's in_progress
  or review (or an earlier unchecked backlog line). If none can, it stops and tells me what
  each one waits on. Every done job's worktree and branch must be gone first.
- When a job starts, the orchestrator runs `git fetch origin` and creates its worktree with
  `git worktree add --no-track -b factory/<type>/<job-id> .claude/worktrees/<job-id> origin/main`.
  `<type>` is feat, fix, ci, docs, refactor, test, or chore, picked from the job's
  description. The first time, it also adds `.claude/worktrees/` to `.git/info/exclude`.
- Builders edit only their own files in the job's worktree (builder-frontend `frontend/`,
  builder-backend the rest), plus their own build-<side>.md, and run every command inside
  the worktree.
- Agents never run git writes. The orchestrator's are: fetch, `worktree add`, the job's
  commit + push + PR when it reaches review, and on approve the PR merge, `worktree remove`,
  and deleting the job branch. Nobody rebases, stashes, resets, force-pushes, or switches
  branches.
- Commits and PRs carry no Claude attribution: no `Co-Authored-By` trailer, no
  "Generated with Claude Code" line.
- After every builder round, the orchestrator snapshots the worktree, including untracked
  files, without touching the index, against the job's base on main (so rework rounds
  still show the whole job, not just what changed since the last commit). Vendored
  `*.min.*` files, `uv.lock`, and `package-lock.json` stay out, since every reviewer reads
  the patch:
      t=$(mktemp -d); wt=.claude/worktrees/<job-id>
      base=$(git -C $wt merge-base HEAD origin/main)
      GIT_INDEX_FILE=$t/index git -C $wt read-tree HEAD
      GIT_INDEX_FILE=$t/index git -C $wt add -A
      GIT_INDEX_FILE=$t/index git -C $wt diff --cached -M $base -- . ':!*.min.*' ':!uv.lock' ':!*package-lock.json' > factory/jobs/<job-id>/round-<n>/diff.patch
      rm -rf $t
- WAIT FOR ALL: a review round is done only when every reviewer's file exists in the
  round folder. Never resume a builder mid-round.
- At most 2 agent review rounds per run. If round 2 still has CHANGES, the approver runs
  anyway and must ESCALATE.
- Spawn each builder with a name (builder-backend-<job-id>, builder-frontend-<job-id>), and
  resume that same builder with SendMessage when a later round picks its side, pointing it
  at the round folder. If it's gone (a new session, or a rework after I quit), or the side
  is new to the job, spawn a fresh one. The files hold everything it needs. On approve,
  once the PR is merged, the orchestrator stops both.
- Orchestrators are the only writers of board.json. Each changes only its own job's entry,
  under a file lock, and appends every status or stage change to the job's history.

## Commands
/factory <feature>               add a job (next free id) and run it through the loop
/factory next                    run the first unchecked item in backlog.md that no active
                                 job blocks
/factory approve <job-id>        merge the job's PR, mark it done, tick it in backlog.md, stop
                                 its builder, and remove its worktree and branch (below)
/factory rework <job-id> <note>  save my note as feedback-<n>.md, set stage rework, and
                                 resume the builders it needs for round <n>; the new commit lands on
                                 the same PR

When a job reaches review, the orchestrator runs:
    git -C .claude/worktrees/<job-id> add -A
    git -C .claude/worktrees/<job-id> commit -m "<job title>"
    git -C .claude/worktrees/<job-id> push -u origin factory/<type>/<job-id>
    gh pr create --base main --head factory/<type>/<job-id> --title "<job title>" --body-file factory/jobs/<job-id>/decision.md

What `/factory approve` runs:
    gh pr merge factory/<type>/<job-id> --merge
    TaskStop builder-backend-<job-id> builder-frontend-<job-id>
    git worktree remove .claude/worktrees/<job-id>
    git branch -D factory/<type>/<job-id> && git push origin --delete factory/<type>/<job-id>
    git fetch origin --prune
    fctl import-factory --job <job-id>

## Dashboard
One self-contained HTML file, served with `python3 -m http.server` from factory/.
- Four columns: Backlog (the unchecked lines in backlog.md), In progress, Review, and Done.
  Each card shows its stage.
- Each review round shows as a row of reviewer chips that fill in as verdicts land.
- human_review and escalated jobs stand out; escalated ones are red.
- Click a card to read its markdown files and its diff.patch, with +/− lines colored and
  +N −M per file.
- Clean and minimal.

## Backlog
Seed factory/backlog.md with these lines, in this order. Each one is a job for
/factory next. § numbers point into docs/.

- [ ] 001-setup: uv project and package layout; `fctl serve` on 127.0.0.1:4545; data dir `FCTL_HOME` (default `~/.claude-factories`); full `schema.sql` from §5.1 applied at startup in WAL mode; base Jinja layout with vendored htmx and highlight.js; local-safety middleware (§4.5: Host check, `X-Requested-By: fctl` on mutating requests); pytest + TestClient wired to a temp `FCTL_HOME`.
- [ ] 002-projects: workspaces; `GET /api/workspaces`, `POST /api/projects/connect`, `GET /api/projects?path=` (§6.1); `fctl connect` collecting git info and resolving the main repo from inside a worktree (§3.1); workspace page (§8 item 2).
- [ ] 003-tasks-board: task endpoints in §6.2 except run/run-next/stop/log; stage → status mapping and `events` rows (§5.2); manual moves clear stage and are refused during a run; project board (§8.1) with native drag and drop; `fctl task add`.
- [ ] 004-submit: `fctl submit --new` and `fctl submit <id>` with the temp-index capture (§7.4); `POST /api/tasks/{id}/rounds` and task create with `submit`; per-file split and +/− counts into `round_files`; 413 over 5 MB; `fctl diff`; `GET /api/tasks/{id}/context` and `fctl show`.
- [ ] 005-review-page: review page (§8 item 5, §8.2, §8.3): header, round selector, Conversation tab with timeline, Files changed with a server-rendered diff table and highlight.js, inline comments, Approve, Request changes (standalone tasks: no run).
- [ ] 006-agent-api: `fctl spec`, `stage`, `verdict`, `comment`, `decide`, `round` and their endpoints (§6.3, §7.2).
- [ ] 007-task-detail: task page (§8 item 4) without run controls: spec, rounds with reviewer chips, approver decision, status history.
- [ ] 008-factory-templates: Create factory (§3.2, §6.1): SKILL.md and the 7 agent templates from §7.3, rendered per project; skip or overwrite; factory state none / uncommitted / ready.
- [ ] 009-run-manager: run, run-next, stop, and log endpoints (§6.2); worktree creation and `.git/info/exclude`; auth check, env stripping, and the spawn command (§4.3, §4.4); one run at a time; Stop by process group; startup cleanup; Request changes spawns a rework run; run controls, run log, and takeover command on the task page; `Claude: Pro ✓` header.
- [ ] 010-cli-and-skills: `fctl setup` writing `~/.claude/skills/factory-connect` and `factory-submit` (§7.1); `fctl run`, `fctl rework`, `fctl approve` (§7.2).
- [ ] 011-code-page: project code page (§8 item 6): `git ls-files` tree, README landing, highlighted file viewer, path containment (§4.5).
- [ ] 012-dashboard: dashboard (§8 item 1).

Once 009 and 010 are done, the app can run factories itself. At that point, connect this
repo with `/factory-connect`, click Create factory, and retire factory/ along with this
file-based loop.

## Before the first run
After writing the factory files, stop and tell me to run:

    git init -b main && git add -A && git commit -m "Docs and factory"
    gh repo create --source . --push --private

Worktrees branch from origin/main, so main needs a commit on GitHub. /factory refuses
to start a job without one.
