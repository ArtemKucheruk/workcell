Build a simple, visual "software factory" in this repo using a Claude Code skill,
subagents, and markdown files. Its first product is this repo's own app, Claude Factories,
which is designed in docs/ (start at docs/MVP.md). Keep the factory small: a viewer should
understand the whole thing in a few minutes.

This is the bootstrap factory. State lives in files, because the app that will hold it
doesn't exist yet. It already follows the app's rules: worktrees, Claude never commits, and
I approve. Moving it into the app later changes where the state lives, not how the loop works.

## The repo and its stack

The repo holds only docs; job 001 creates the project. Don't infer the stack from the repo.
Use this one (docs/MVP.md §4.2):
- Python 3.12, managed with uv. The package is `claude_factories` and the console script is `fctl`.
- FastAPI and uvicorn. stdlib sqlite3 with one `schema.sql` applied at startup, in WAL mode. No ORM.
- Jinja2 templates and htmx, rendered on the server, with no frontend build. htmx and
  highlight.js are vendored under `static/`.
- markdown-it-py with raw HTML turned off.
- The `fctl` CLI module imports only the stdlib.
- Runtime dependencies: fastapi, uvicorn, jinja2, markdown-it-py. Dev dependencies: pytest,
  httpx. Any other dependency needs a reason in the spec.
- Test command: `uv run pytest -q`. Tests use a temp data dir (`FCTL_HOME`) and a fake
  `claude` on PATH. They never call the real `claude`, the network, or `~/.claude*`.

docs/ is the source of truth for what to build. Specs cite doc sections, for example
`docs/data-model-and-api.md §6.2`. The table at the top of docs/MVP.md says which file
holds which section.

## The orchestrator

The factory is one skill, /factory. Whichever Claude Code session runs it becomes the
orchestrator. It runs the loop below, spawns every agent, creates worktrees, and is the
only writer of factory/board.json.

## The loop (edit this to change the factory)

                   ┌──────────────────┐
                   │     feature      │
                   └─────────┬────────┘
                             ▼
                   ┌──────────────────┐
                   │   spec-writer    │
                   │       opus       │
                   └─────────┬────────┘
                             ▼
                   ┌──────────────────┐
                   │     builder      │◄────────────────────┐
                   │       opus       │                     │
                   └─────────┬────────┘                     │
        ┌─────────────┬──────┴──────┬─────────────┐         │
        ▼             ▼             ▼             ▼         │
  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
  │  security │ │     ux    │ │ ui design │ │    code   │   │
  │    opus   │ │   sonnet  │ │   sonnet  │ │   sonnet  │   │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘   │
        └─────────────┴──────┬──────┴─────────────┘         │
                             ▼                              │
                   ┌──────────────────┐   any CHANGES:      │
                   │   WAIT FOR ALL   ├─────────────────────┤
                   │   4 reviews in   │   resume builder    │
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
                             ▼ waits on me                  │
                   ┌──────────────────┐ /factory rework     │
                   │ I read the job + ├─────────────────────┘
                   │  worktree diff   │ (new round)
                   └─────────┬────────┘
                             ▼ /factory approve
                   ┌──────────────────┐
                   │ done: I commit + │
                   │  merge to main   │
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
  worktrees/004-submit/            # builder's checkout, branch factory/004-submit
factory/
  board.json                       # durable state, drives the dashboard
  dashboard.html                   # visual board, polls board.json
  backlog.md                       # ordered queue for /factory next (seed below)
  jobs/004-submit/                 # one folder per job
    spec.md
    round-1/                       # one folder per review round
      build.md                     # builder: what changed, criteria → tests, test output
      diff.patch                   # orchestrator: worktree snapshot vs main
      review-security.md           # one file per reviewer
      review-ux.md
      review-ui.md
      review-code.md
    feedback-2.md                  # my /factory rework note, numbered by the round it starts
    decision.md

## Agents

| agent | model | tools | reads | writes |
|---|---|---|---|---|
| spec-writer | opus | Read, Grep, Glob, Write | the feature or backlog line, docs/, code on main | `spec.md` |
| builder | opus | Read, Edit, Write, Grep, Glob, Bash | `spec.md`, the last round's reviews, `feedback-N.md` | code in its worktree, `round-N/build.md` |
| review-security | opus | Read, Grep, Glob, Bash, Write | spec, build.md, diff.patch, worktree | `round-N/review-security.md` |
| review-ux | sonnet | same | same | `round-N/review-ux.md` |
| review-ui | sonnet | same | same | `round-N/review-ui.md` |
| review-code | sonnet | same | same, plus it runs the tests in the worktree | `round-N/review-code.md` |
| approver | opus | Read, Grep, Glob, Write | the whole job folder | `decision.md` |

What each one does:
- **spec-writer** writes the goal, the doc sections the job implements, acceptance criteria
  as a checklist (each one testable), the files it expects to touch, what's out of scope,
  and open questions. Anything the docs don't decide goes under open questions, never
  guessed silently.
- **builder** implements the spec in the worktree, runs `uv run pytest -q` there, and maps
  each acceptance criterion to its test in build.md.
- **security** checks docs §4.5 (127.0.0.1 bind, Host and `X-Requested-By` checks, raw
  HTML off in markdown, path containment, the 5 MB limit). Subprocesses must take argument
  lists, never shell strings. It also checks env stripping and the subscription-only auth
  check (§4.3), and the allow/deny lists for runs (§4.4).
- **ux** reviews the docs §3 flows and the CLI's ergonomics: `fctl` output, error messages,
  and exit codes. If the job changes nothing a user sees, it writes `VERDICT: PASS` with
  "nothing user-facing".
- **ui** reviews pages against docs §8 and its wireframes, including empty and error states
  and light/dark. If the job has no UI, it writes `VERDICT: PASS` with "no UI in this job".
- **code** checks the stack and conventions above, that every acceptance criterion has a
  passing test, and that there are no unrequested abstractions or dependencies.
- **approver** writes APPROVE or ESCALATE. It escalates if CHANGES remain after round 2,
  tests fail, the work conflicts with docs/, or an open question changed behavior.

## Example files

.claude/agents/review-code.md  (Claude Code subagent syntax)
---
name: review-code
description: Code review of the latest round of a factory job. Use after the builder finishes a round.
tools: Read, Grep, Glob, Bash, Write
model: sonnet
---
Input: a job id and its round folder. Read spec.md, round-N/build.md, round-N/diff.patch,
and the files in .claude/worktrees/<job-id>. Run `uv run pytest -q` in that worktree.
Check the stack and conventions in FACTORY.md, that every acceptance criterion has a
passing test, and that nothing unrequested was added. Write only round-N/review-code.md:
first line VERDICT: PASS or VERDICT: CHANGES, then findings as file:line, problem, fix.

factory/board.json
{ "jobs": [ { "id": "004-submit", "title": "fctl submit and review rounds",
  "status": "in_progress", "stage": "agent_review", "round": 2,
  "branch": "factory/004-submit", "worktree": ".claude/worktrees/004-submit",
  "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" },
  "history": [ { "at": "2026-10-17T10:03:00Z", "status": "in_progress", "stage": "spec" } ] } ] }

## Rules
- Agents get context from files, not the conversation, and write only their own file.
- Each review starts with `VERDICT: PASS` or `VERDICT: CHANGES`. decision.md starts with
  APPROVE or ESCALATE.
- One job at a time. A job starts only when no other job is in_progress or review, and
  every done job's branch is merged into main (`git branch --merged main`). Otherwise stop
  and tell me what to merge.
- When a job starts, the orchestrator creates its worktree with
  `git worktree add -b factory/<job-id> .claude/worktrees/<job-id> main`.
  The first time, it also adds `.claude/worktrees/` to `.git/info/exclude`.
- The builder edits only its worktree, plus its own build.md, and runs every command
  inside the worktree.
- Nobody commits, pushes, merges, rebases, or switches branches. I do all git writes.
- After every builder round, the orchestrator snapshots the worktree, including untracked
  files, without touching the index:
      t=$(mktemp -d); wt=.claude/worktrees/<job-id>
      GIT_INDEX_FILE=$t/index git -C $wt read-tree HEAD
      GIT_INDEX_FILE=$t/index git -C $wt add -A
      GIT_INDEX_FILE=$t/index git -C $wt diff --cached -M HEAD > factory/jobs/<job-id>/round-<n>/diff.patch
      rm -rf $t
- WAIT FOR ALL: a review round is done only when every reviewer's file exists in the
  round folder. Never resume the builder mid-round.
- At most 2 agent review rounds per run. If round 2 still has CHANGES, the approver runs
  anyway and must ESCALATE.
- Spawn the builder with a name (builder-<job-id>), and resume that same builder with
  SendMessage for each new round, pointing it at the round folder. If it's gone (a new
  session, or a rework after I quit), spawn a fresh builder-<job-id>. The files hold
  everything it needs.
- The orchestrator is the only writer of board.json. It appends every status or stage
  change to the job's history.

## Commands
/factory <feature>               add a job (next free id) and run it through the loop
/factory next                    run the first unchecked item in backlog.md
/factory approve <job-id>        mark a review job done, tick it in backlog.md, and print my
                                 commit + merge commands (below)
/factory rework <job-id> <note>  save my note as feedback-<n>.md, set stage rework, and
                                 resume the builder for round <n>

What `/factory approve` prints for me to run:
    git -C .claude/worktrees/<job-id> add -A
    git -C .claude/worktrees/<job-id> commit -m "<job title>"
    git merge --ff-only factory/<job-id>
    git worktree remove .claude/worktrees/<job-id> && git branch -d factory/<job-id>

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

Worktrees branch from main, so main needs a commit. /factory refuses to start a job
without one.
