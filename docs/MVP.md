# Claude Factories — MVP design

Status: draft · Working name: Claude Factories · CLI name: `fctl`

Built on the loop in [`FACTORY.md`](../FACTORY.md). The loop, the agents, and the rules stay
the same except where this document lists a change (see §4.3).

| File | Sections |
|---|---|
| `MVP.md` (this file) | 1 Overview · 2 Concepts · 3 User flows · 4 Architecture · 9 Scope vs Later · 10 Open questions |
| [`data-model-and-api.md`](data-model-and-api.md) | 5 Data model · 6 API |
| [`claude-code.md`](claude-code.md) | 7 Claude Code integration (commands, templates, submit example, status updates) |
| [`ui.md`](ui.md) | 8 UI (screens, board and review wireframes) |

---

## 1. Overview

### Problem
The factory in FACTORY.md works, but all of its state sits in `board.json` and markdown
files inside each repo. Every repo has its own dashboard. Reviewing means reading markdown
files and running `git diff` in a terminal, and the factory merges to main on its own.
With several projects there is no single place that shows what is queued, what is running,
and what is waiting on me.

### Goals
- One local app tracks the features I want to ship, per project, with projects grouped
  into workspaces.
- The app runs the factory loop. A **Run** button spawns headless Claude Code, and the
  app's API and database are the only place factory state lives.
- Every change gets a GitHub-style review in the app. Agents never commit. I commit and
  merge, either by hand or with the **Create PR** and **Merge PR** buttons (§3.7).
- Installing the factory into a repo takes one click.
- Runs use my Claude Pro subscription through my claude.ai login. They never bill per token
  through the API.

### Non-goals (MVP)
- Multiple users, auth, cloud hosting.
- Agents committing, pushing, merging, or opening GitHub PRs. Only my click on Create PR or
  Merge PR runs git or `gh` writes.
- Any GitHub API integration beyond those two buttons, which go through my `gh` login.
- Editing code in the browser.

---

## 2. Concepts & glossary

| Term | Meaning |
|---|---|
| **Workspace** | A named group of projects, e.g. `work` or `personal`. |
| **Project** | One local git repo, identified by its main checkout path. It is registered by running `/factory-connect` inside the repo. |
| **Task** | One feature or fix in a project. Its **status** is the kanban column: `backlog → in_progress → review → done`. |
| **Stage** | The factory sub-step inside a status: `spec`, `build`, `agent_review`, `approval`, `rework` (all in_progress), and `human_review`, `escalated` (both review). See §5.2. |
| **Run** | One headless `claude -p "/factory <id>"` process that the app spawns to move a task forward. Only one run is active at a time, across all projects (§4.4). |
| **Round** | One builder submission plus the four reviewer verdicts on it. A submission is a diff snapshot plus build notes. Rounds are numbered 1, 2, 3… per task and never reset. Each snapshot is the full diff against the base, not an increment. |
| **Review** | The app's "PR": the review page of a task. It shows every round, the latest snapshot's files and diff with +/− counts, the agent verdicts, the inline comments, the approver's decision, and mine. |
| **Verdict** | A reviewer agent's `PASS` or `CHANGES` on a round, plus a markdown body. |
| **Decision** | The approver's `APPROVE`/`ESCALATE`, or my own `APPROVE`/`CHANGES_REQUESTED`. |
| **Factory** | The `/factory` orchestrator skill plus 7 subagents, which Create factory writes into `<repo>/.claude/` from the app's templates. A project can also hold named factory designs: graphs of agents and conditions edited on a canvas and saved in the app (§3.2). |
| **Agent** | One subagent file: `spec-writer`, `builder`, `review-security`, `review-ux`, `review-ui`, `review-code`, `approver`. |
| **Worktree** | A git worktree at `<repo>/.claude/worktrees/<id>-<slug>` on branch `factory/<id>-<slug>`. The builder edits only this directory. |
| **fctl** | The app's CLI. Agents use it to talk to the API, and I use it to start the server. |

---

## 3. User flows

### 3.0 One-time install
The app runs in Docker (§4.6). In the repo:
```
cp compose.override.example.yaml compose.override.yaml   # then edit the project roots and uid:gid
docker compose up --build                                 # the app, from now on
docker compose exec backend claude auth login             # once, in a second terminal
```
The app opens at `http://127.0.0.1:3000`. `fctl` also goes on the host:
```
uv tool install ~/personalProjects/claude-factories   # puts `fctl` on PATH
fctl setup     # writes ~/.claude/skills/factory-connect and ~/.claude/skills/factory-submit
```
The `/factory-connect` and `/factory-submit` skills run `fctl` on the host against the
backend on `127.0.0.1:4545`.

Without Docker, run `fctl serve` (backend on 127.0.0.1:4545, data in `~/.claude-factories/`)
plus the frontend server: `npm --prefix frontend ci && npm --prefix frontend run build &&
node frontend/server.js` (127.0.0.1:3000). Tests and the factory's reviewers run it this way.

### 3.1 Connect a project
1. In the repo, in my Claude Code session: `/factory-connect personal`
2. Claude inspects the repo to find the test command, then runs:
   `fctl connect --workspace personal --test-cmd "pytest -q"`
3. `fctl` collects the path (`git rev-parse --show-toplevel`), the name (directory name),
   the remote (`git remote get-url origin`), and the default branch (`origin/HEAD`, falling
   back to the current branch). It sends `POST /api/projects/connect`.
4. The output is `Connected api-server (personal) → http://127.0.0.1:4545/projects/3`.
   Running it again updates the project. An unknown workspace is created on the spot.

### 3.2 Create a factory
1. Project **Settings** (`/projects/{id}/settings`) → **Create factory**.
2. The app renders its templates with the project's name, test command, and default branch,
   and writes 8 files: `.claude/skills/factory/SKILL.md` and `.claude/agents/*.md`.
   Existing files are skipped and listed, unless I tick *Overwrite*.
3. The page shows the files it wrote and the command to commit them:
   `git add .claude/skills/factory .claude/agents && git commit -m "Add factory"`
4. **Run** stays disabled, with that same hint, until the factory is `ready`. Worktrees are created
   from `main`, so the factory has to be committed there before a run can see it. The app reads
   one of four factory states with one `git cat-file blob main:.claude/skills/factory/SKILL.md`,
   in this order:
   - `ready`: SKILL.md is a committed file on `main` containing the bytes `fctl stage`. The app's
     template always calls `fctl stage`, so a committed Create factory reads `ready`.
   - `legacy`: SKILL.md is committed on `main` but lacks `fctl stage`. This is the file-based
     bootstrap loop (this repo's own `/factory`): it keeps its state in `factory/` and reads
     `/factory <id>` as a new feature, so a run would start the wrong job.
   - `uncommitted`: SKILL.md isn't committed on `main` (or git fails, or it isn't a file there),
     but it is on disk.
   - `none`: neither.

   Every run (Run, Retry, Run next, and Request changes' rework run) refuses a `legacy` repo with
   `this repo runs the file-based /factory loop: Create factory with Overwrite, then commit it on main`,
   and the board and task pages show it as the hint. To fix it, Create factory with *Overwrite*,
   then commit the files on `main`. Until that commit the state stays `legacy`: the committed file
   decides, not the one on disk. Meanwhile the board's automatic `factory/` sync
   (`docs/data-model-and-api.md §6.1` import-factory) keeps showing the bootstrap's jobs.

Design a factory: Project → **Factories** → **+ New factory** (a name and a template) → the designer
opens on the template's graph → drag or click agents and conditions from the palette, connect handles, and edit the
selected node in the side panel → **Save** or Ctrl/⌘+S. Save shows a refusal (a bad graph,
`docs/data-model-and-api.md §6.1`) beside it, and the design stays unsaved. → **Files** shows the
last saved design compiled into Claude Code files (`docs/claude-code.md §7.3`):
`.claude/skills/<factory-slug>/SKILL.md` and one `.claude/agents/<name>.md` per agent node. A graph
the compile refuses shows its detail instead. **Download .zip** saves them, and **Write to repo**
writes them with step 2's writer: existing files skipped unless *Overwrite*, the same written and
skipped lists, and a commit hint naming `.claude/skills/<factory-slug>`. A design reaches
`.claude/` only through Write to repo, and runs use `.claude/skills/factory/`: only a factory
whose name slugs to `factory` writes the skill runs start, and step 4 is unchanged.

The templates (088; graphs in `docs/data-model-and-api.md §6.1`, agents in `docs/claude-code.md §7.3`):
- **Standard** (the default): the default loop. Spec, build, then security, UX, UI, and code reviews; up to 2
  rounds; the approver decides.
- **Bug fix**: reproduce the bug as a failing test, fix its root cause, then code and security reviews.
- **Security audit**: audit dependencies, secrets, and code; write `SECURITY-AUDIT.md` and fix what is safe;
  security review. Built for scheduled runs (the cron recipe is in §7.3; the app has no scheduler).
- **ML experiment**: check the data and baseline, run the experiment, and gate it on eval metrics against the
  baseline.
- **Test coverage**: find risky untested code and pin its behavior with tests, leaving production code unchanged.

### 3.3 Add a feature
Board → **+ New task** → title and description (markdown) → the card lands at the bottom of
Backlog as `#12`. CLI alternative: `fctl task add "Rate-limit login endpoint"`.
I can reorder Backlog by dragging. **Run next** always takes the top card.

### 3.4 Run the factory
I click **Run** on #12, or **Run next**. What follows:

| # | Who | What happens | Status · stage |
|---|---|---|---|
| 1 | app | Creates the worktree `.claude/worktrees/12-rate-limit-login` on `factory/12-rate-limit-login` from `main`, then spawns `claude -p "/factory 12"` in it (§4.4) | backlog → **in_progress** · — |
| 2 | orchestrator | `fctl stage 12 spec`, spawns spec-writer → `fctl spec 12` | in_progress · spec |
| 3 | orchestrator | `fctl stage 12 build`, spawns `builder-12` → edits the worktree, runs `pytest -q`, `fctl submit 12` → round 1 | in_progress · build |
| 4 | orchestrator | `fctl stage 12 agent_review`, spawns 4 reviewers in one message → each runs `fctl verdict 12 <reviewer> …`. The chips fill in live. | in_progress · agent_review |
| 5 | orchestrator | WAIT FOR ALL (4/4 verdicts). If any is CHANGES and this run has had fewer than 2 rounds: `fctl stage 12 build`, SendMessage `builder-12` → round 2 → back to step 4 | in_progress · build ↔ agent_review |
| 6 | orchestrator | All PASS, or round cap reached → `fctl stage 12 approval`, spawns approver → `fctl decide 12 APPROVE\|ESCALATE` | in_progress · approval |
| 7 | orchestrator | APPROVE → `fctl stage 12 human_review`. ESCALATE → `fctl stage 12 escalated` (red "needs you"). The orchestrator then stops. | **review** · human_review / escalated |
| 8 | app | The process exits. The app records the exit code on the run. | unchanged |

If a run dies before step 7, the card shows **stalled · build** (for example) with
**Retry**. That includes a run that hit the Pro usage limit: I Retry once the limit resets.
Retry spawns `/factory 12` again, and the orchestrator picks up from the task's current
stage.

### 3.5 Review in the app
I open the card and go to **Review**. The **Conversation** tab shows the description, the
spec summary, each round's verdicts, and the timeline. **Files changed** shows the file tree
with +/− per file and a unified diff. Clicking a line number adds an inline comment, and
reviewer agents' inline comments show up in the same place.

### 3.6 Request changes
1. I add inline comments and a summary, then click **Request changes** (CLI alternative:
   `fctl rework 12 "note"`).
2. The app records my `CHANGES_REQUESTED` decision, sets status · stage to in_progress · rework,
   and spawns `/factory 12` in the same worktree.
3. The orchestrator sees `rework` and spawns a fresh `builder-12`. That builder reads
   `fctl show 12 --feedback`, which has my summary and inline comments, and submits round 3
   (trigger `human`). Agent review and the approver then run as in §3.4 steps 4–7, and the
   task returns to Review.

### 3.7 Approve and commit
Agents never commit. I commit and merge either by hand (step 2) or with the buttons (steps 3–4).
1. **Approve** records my `APPROVE` decision and moves the task to done. Approving runs no git.
2. The review page shows the commands under **Commit it yourself**, for doing it by hand:
   ```
   cd .claude/worktrees/12-rate-limit-login
   git add -A && git commit -m "Rate-limit login endpoint"
   git push -u origin factory/12-rate-limit-login     # then open a PR, or merge locally
   git worktree remove .claude/worktrees/12-rate-limit-login
   ```
3. Or **Create PR** (task and review pages, docs/ui.md §8.2), for a done task whose worktree has
   uncommitted changes or commits beyond the default branch. It runs `git add -A` and
   `git commit -m <task title>` in the worktree under my git identity (hooks and signing apply; no
   attribution), `git push -u origin <branch>` (never forced), then `gh pr create` against the
   default branch, or reuses the branch's open PR. The body holds the description's first
   paragraph, the round count, the latest verdicts, the approver's decision, and the task's app
   URL. The PR's URL is saved on the task, with a `PR #N opened` event. The page then shows the
   PR link, its state, and its checks, polled every 10 s while it is open.
4. **Merge PR** asks in a dialog, then runs `gh pr merge <n> --merge` (a merge commit). Then
   `git fetch origin` in the main checkout and `git merge --ff-only origin/<default>`, but only
   when the checkout is on the default branch, clean (untracked files count), and behind origin;
   otherwise it skips that and says why. Last, `git worktree remove`, `git branch -d`, and
   `git push origin --delete <branch>`, none forced; a failed step is a note, and the rest still
   run.

Both buttons need `origin` on github.com and `gh` installed and logged in (`gh auth status`).
Every refusal shows git's or gh's own message.

### 3.8 Submit without the factory
Any Claude Code session, in any connected repo: `/factory-submit` creates a task straight in
Review from the current working tree. The full example is in §7.4.

---

## 4. Architecture

### 4.1 Components

```
     Browser                         My Claude Code terminal
        │ fetch JSON (poll 3s)             │ /factory-connect, /factory-submit → fctl
        ▼                                  │
┌─ frontend/server.js (127.0.0.1:3000) ─┐  │
│ built SPA (dist/)    /api/* proxy     │  │
└───────┬───────────────────────────────┘  │
        │ /api/* (HTTP)                    │ (HTTP)
        ▼                                  ▼
┌─────────────────────────── fctl serve  (127.0.0.1:4545, backend) ─────────────────────────┐
│  JSON API   run manager   template writer   git reader (tree, file, worktree)             │
└────┬──────────────▲──────────┬────────────────┬──────────────────────┬────────────────────┘
     │ sqlite3      │ fctl     │ spawn / stop   │ write once           │ git subprocess
     ▼              │ (HTTP)   ▼                ▼                      ▼
 ~/.claude-     ┌───┴──────────────────────────────┐  <repo>/.claude/     <repo> main checkout
 factories/     │ claude -p "/factory 12"          │  skills/factory/     + .claude/worktrees/*
 factory.db     │ cwd = .claude/worktrees/12-…     │  agents/*.md
 runs/*.jsonl ◄─┤ orchestrator → spec-writer,      │
  (stdout log)  │ builder-12, 4 reviewers, approver│── edits files ──► worktree only
                └──────────────────────────────────┘
```

- **Browser → frontend → backend.** The browser loads the SPA from the frontend server. The
  SPA fetches JSON through the frontend's `/api` proxy, which forwards it to `fctl serve`.
  The board, task, and run-log views poll every 3 s.
- **App → Claude Code.** The app spawns a subprocess. stdout (`stream-json`) goes to
  `runs/<run-id>.jsonl`, and on exit the app reads the final `result` event for status,
  and `session_id`.
- **Agents → app.** Agents run `fctl …` through Bash, which makes a JSON HTTP call to
  127.0.0.1. Agents never touch the database or any file outside the worktree.
- **App → DB.** stdlib `sqlite3`, WAL mode. The app is the only process that writes.
- **App → git.** The app shells out to `git` to add worktrees, list files, show files, and
  check whether the factory is committed.

### 4.2 Stack
Python 3.12 with FastAPI and uvicorn. Storage is stdlib `sqlite3`, with no ORM and one
`schema.sql` that runs at startup. markdown-it-py renders markdown with raw HTML turned off.
The package is built with uv and has 4 runtime dependencies.

The frontend lives in `frontend/`: a Vite + React SPA in plain JSX, styled with Tailwind v4
and routed with react-router. highlight.js, installed from npm, highlights code. The fonts
come from `@fontsource-variable/ibm-plex-sans` and `@fontsource-variable/jetbrains-mono`, which
Vite bundles into `dist/`: they are self-hosted, so the app on 127.0.0.1 works offline and
calls no CDN. Components come from Preline UI, the free `preline` package (MIT, with Preline's
Fair Use License), installed from npm and bundled into `dist/` the same way, with no Preline
Pro. Tests run on
vitest with @testing-library/react and jsdom. `frontend/server.js` serves the built SPA and
proxies `/api` to the backend. It runs on `node:http` with no extra dependencies. The
frontend needs Node 22 and npm.

Why this stack: the app is mostly subprocess, git, SQLite, and text handling, which is
boring and well supported in Python. FastAPI validates requests and serves `/docs` for free,
which helps when writing agent prompts. SQLite fits one user and one writer process, and it
is one file to back up. The `fctl` CLI ships in the same package but imports only the
stdlib, so agents' calls start fast.

Why this frontend:
- The pages are interactive: drag and drop with inline 409s, the review page's round
  selector, deep-linkable line anchors, inline comment forms, and the run-log tail. React
  components hold that state more simply than htmx fragments plus per-page scripts.
- Vite gives a fast dev server and a static build. Plain JSX skips a TypeScript toolchain.
- Tailwind v4 keeps styles next to the markup, light/dark included.
- highlight.js from npm replaces a vendored copy.
- A dependency-free `node:http` server serves `dist/` and proxies `/api`, so the browser
  talks to one origin and the backend stays a JSON API.
- Node 22 is an LTS line, and npm ships with Node, so there is no extra package manager.

### 4.3 Decisions

**Runs are spawned by the app (option b).** The app owns the whole lifecycle: Run, Retry,
Stop, and rework on Request changes. Running `/factory` from my own terminal is on the Later
list.

**Runs bill against my Pro subscription, not the API.** A run is my own `claude` CLI,
logged in through claude.ai, running on my machine. It uses the same Pro limits as my
interactive sessions.
- The app removes `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and every `CLAUDE_CODE_USE_*`
  provider variable from the run's environment. With any of them set, `claude -p` would
  quietly bill per token or route to Bedrock or Vertex.
- Before every run, the app runs `claude auth status` with the same environment and working
  directory, which carries the active Claude account's `CLAUDE_CONFIG_DIR` (§4.6). If the result
  is not `"authMethod": "claude.ai"`, or no account is active, the run is refused with
  `409 not on subscription auth`. With no active account, claude isn't called at all. The app
  header shows the reported plan, `subscriptionType: "pro"`.
- Runs never use `--bare`, which accepts only API keys, or the Agent SDK, which needs an API
  key. Headless `claude -p` is the only way a run starts.
- There is no dollar budget, because the Pro usage limits are the budget. That is why only
  one run is active at a time (§4.4).

**Agents call the app through the `fctl` CLI.**
- Not curl. Escaping markdown and multi-KB diffs as JSON inside Bash is fragile, and every
  prompt would have to repeat URLs and headers. Capturing a diff that includes untracked
  files takes several git steps, and those belong in one tested place, not in seven prompts.
- Not MCP. It would need a server and its registration for every session, and tool
  permissions for headless runs. It is also harder to try out by hand.
- `fctl` works from any subagent that has Bash. One allowlist covers it in headless runs.
  Markdown goes in on stdin: a heredoc by hand, a file under `.fctl/` in a run (§4.4). I can run the
  exact same commands in a shell.

**Spec, build, and review content lives in the DB only.**
- It is a single source of truth, and the UI needs it in the DB anyway.
- Markdown files on disk would land in the worktree and show up in the very diff under review.
- Agents still "get context from files, not the conversation". `fctl show 12` prints the
  same markdown the job folders used to hold.

**The builder works in a worktree.** Several tasks can run in parallel, and my main checkout
is never touched. The branch is created but gets no commits.

**Changes vs FACTORY.md**
- There is no merge to main. Approver APPROVE moves the task to review · human_review, and
  only my Approve moves it to done.
- Agents make no commits. git write commands are denied in runs (§4.4). I commit and merge by
  hand or with Create PR and Merge PR (§3.7), which the app runs only on my click, through the
  git adapter with timeouts (60 s local, 120 s for push, fetch, and gh).
- `board.json`, `dashboard.html`, and `jobs/*` are replaced by the DB and the API. Stages
  are set only by the orchestrator through `fctl stage`, the same way the orchestrator was
  the only writer of `board.json`.
- `/factory approve` used to merge. Now it only marks the task done.
- `/factory <feature>`, `next`, and `rework` become app actions (§7.2). The skill has a
  single entry point, `/factory <id>`, which continues from the task's current stage.

### 4.4 How a run is spawned
```
cd /Users/artem/code/api-server/.claude/worktrees/12-rate-limit-login
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN FCTL_URL=http://127.0.0.1:4545 \
    CLAUDE_CONFIG_DIR=~/.claude-factories/claude-accounts/… \
claude -p "/factory 12" \
  --session-id 6f1c2e0a-…  --output-format stream-json --verbose --forward-subagent-text \
  --permission-mode acceptEdits --permission-prompts none \
  --allowedTools "Bash(fctl show *)" "Bash(fctl diff *)" "Bash(fctl spec *)" "Bash(fctl submit *)" \
                 "Bash(fctl verdict *)" "Bash(fctl comment *)" "Bash(fctl decide *)" \
                 "Bash(fctl stage *)" "Bash(fctl round *)" "Bash(git status *)" "Bash(git diff *)" \
                 "Bash(pytest *)" \
  --disallowedTools "Bash(git commit *)" "Bash(git push *)" "Bash(git merge *)" \
                    "Bash(git rebase *)" "Bash(git reset *)" "Bash(git checkout *)" \
  < /dev/null  > ~/.claude-factories/runs/41.jsonl 2>&1
```
- `env -u` stands for the app removing these variables from the run's environment. The app
  removes every `CLAUDE_CODE_USE_*` variable as well (§4.3).
- `CLAUDE_CONFIG_DIR` is the active Claude account's config dir (§4.6), for the auth check and the
  run alike, so the run bills to that account's subscription.
- After the auth check, the app sets `projects["<repo path>"].hasTrustDialogAccepted` in that
  account's `.claude.json` when it's missing. Nobody can answer the trust dialog in a headless run,
  and an untrusted repo's `.claude/settings.json` allow rules are ignored. Connecting the repo is the
  consent.
- Only one run is active at a time, across all projects. While a run is going, starting
  another is refused with `409 run #41 active`. Pro limits are shared with my own sessions,
  and parallel opus runs would use them up quickly.
- The working directory is the worktree, so `acceptEdits` covers only that tree.
  `--permission-prompts none` denies anything not on the allowlist instead of hanging on a
  prompt. It also denies any Bash command over about 10,000 characters, which Claude Code can't
  parse to match a rule. So agents write long markdown to `.fctl/<name>.md` and redirect it in
  (`fctl spec 12 < .fctl/spec.md`), and the non-builder agents get Write for that.
- The test command comes from `projects.test_cmd`. Each `&&`/`||`/`;`/`|` part (split outside
  quotes) gets its own `Bash(<words> *)` rule, deduplicated in order: the part's words before the
  first flag. When that is only the program and the flag is followed by a value and a subcommand
  (`npm --prefix frontend ci`, or `npm --prefix=frontend ci`), the rule runs through them
  (`Bash(npm --prefix frontend ci *)`) instead of `Bash(npm *)`. Flag arity isn't known, so a flag
  followed by one word only (`npm -s test`) still gets `Bash(npm *)`. Extra commands a project needs go in its
  own `.claude/settings.json` `permissions.allow`. Denials show up in the run log.
- Agents can't call `fctl approve`, `run`, or `rework`, so a run can't approve its own work
  or start other runs.
- The process runs in its own process group. **Stop** sends SIGTERM to that group. Stopping
  `fctl serve` stops every run, and at startup any run still marked `running` becomes
  `failed: app restarted`.
- The task page shows a takeover command:
  `cd <worktree> && CLAUDE_CONFIG_DIR=<account dir> claude --resume <session-id>`, with the active
  account's dir, or without it when no account is active.
- When a run ends, on exit, on **Stop**, and in the startup cleanup (`failed: app restarted`),
  the app copies the run's Claude Code transcripts into `FCTL_HOME/transcripts/<run-id>/` and
  indexes each in `transcripts`. Claude Code prunes old transcripts and the worktree gets
  removed, so the copy is the record. They come from the worktree's folder under the active
  account's `<config dir>/projects/`: the run's own session, its teammates, and their subagents.
  Make active and Disconnect are refused during a run, so that is the run's own account. A
  failed copy leaves that file out and never fails the run.

### 4.5 Local safety
Single user and no auth still need these, because the API can start processes that edit code.
- Both servers, `fctl serve` and the frontend server, bind `127.0.0.1` by default.
- Docker: inside their containers both bind `0.0.0.0`. `compose.yaml` publishes no ports,
  and `compose.override.yaml` publishes them only on `127.0.0.1` (§4.6).
- Every mutating request must carry `X-Requested-By: fctl`, and the `Host` must be
  `127.0.0.1` or `localhost`. That blocks CSRF from web pages and DNS rebinding. `fctl` and
  the SPA's fetch wrapper both send the header. One GET writes: the board's view-model
  (`GET /api/pages/projects/{id}`) syncs `factory/` when its files change (058), so it skips
  that sync, not the page, when the browser sends `Sec-Fetch-Site: cross-site`.
- The frontend server (`frontend/server.js`) applies its own Host check: `127.0.0.1` or
  `localhost`, else `403`. It proxies `/api/*` to `FCTL_API_URL` with `Host: 127.0.0.1`, and
  passes the browser's `X-Requested-By` through without adding it. This follows the CSRF
  rule above: the header has to come from the page's own code.
- The frontend server serves files only inside `dist/`, falling back to `index.html`.
- Markdown (READMEs, agent output, project context, transcripts) is rendered with raw HTML
  off. The code viewer escapes everything.
- The SPA inserts HTML only from the backend's `*_html` fields and highlight.js output.
  Everything else renders as text, because React escapes it.
- The code page resolves paths inside the project root only: no `..`, and no symlinks that
  point outside it. Its `?branch=` accepts only a listed branch, passed to git by its full
  refname (`refs/heads/x`, `refs/remotes/origin/x`), and only paths that branch's tree lists.
- Create factory and Write to repo write only under `<repo>/.claude/`. Before any write, every
  target must resolve inside the project, and no path component from `.claude` down to it may be
  a symlink (a broken one included), or the request is refused with `409` and nothing is written.
- The server rejects with `413` patches over 5 MB, a project's pinned context or any one
  context card over 16 KB (`MAX_CONTEXT`), and a project's context over 64 KB in all: the
  pinned context plus every card, in UTF-8 bytes (`MAX_CONTEXT_TOTAL`).
- A path read (Context page → **Add from path**, **Reload from path**) reads on the backend's
  machine, where in Docker only mounted folders exist. It takes only `.md`, `.markdown`, and
  `.txt` regular files, symlinks followed: the file given, or the ones directly in the folder
  given, never subfolders. Each is at most 16 KB, at most 50 per folder
  (`MAX_CONTEXT_FILES`), and must be UTF-8, or the whole read is refused. It writes nothing to
  disk. Uploads go through the same 16 KB and extension checks, and their name never touches
  the filesystem.
- `fctl import-factory`, and the board's sync of `board.json` and `backlog.md`, reads only
  inside `<project>/factory/`, which must resolve inside the project root. Every file it reads
  must resolve inside `factory/` and be a regular file, or it counts as missing, and a file
  over 5 MB is refused with `413`.
- A task bundle import (`POST /api/projects/{id}/import`) refuses a body over `MAX_BUNDLE` (50 MB)
  with `413`, on its `Content-Length` and again as the stream comes in. Every zip entry must be a
  name the layout has (`task.json`, 031's job files, and `transcripts/…` files `task.json` lists),
  with no absolute path, no `..`, no symlink, and no encryption, or it is refused with `422`. The
  entries' declared sizes may sum to `MAX_UNPACKED` (500 MB) at most, else `413`. It unpacks into
  a temp folder that is removed afterwards. Export leaves transcripts out unless asked
  (`?transcripts=1`), since they can hold paths, env, and secrets.
- Transcript text is shown escaped. Text blocks go through `lib/markdown.render` with raw HTML
  off, and the SPA inserts only their `*_html`. Tool inputs, tool results, and thinking are
  plain text. `/api/transcripts/{id}/raw` serves only files that resolve inside
  `FCTL_HOME/transcripts/`, and the copy skips symlinks in Claude Code's folder.

### 4.6 Containers
`docker compose up` runs the app (§3.0).
- **compose.yaml** has two services. `backend` runs `fctl serve --host 0.0.0.0` with
  `FCTL_HOME` on a named volume. `frontend` runs `node server.js` with `HOST=0.0.0.0` and
  `FCTL_API_URL=http://backend:4545`. Both have healthchecks. compose.yaml publishes no
  ports.
- **Override.** `compose.override.example.yaml` is copied to `compose.override.yaml`, which
  is gitignored. It publishes `127.0.0.1:3000:3000` and `127.0.0.1:4545:4545`, so `fctl` on
  the host keeps using 4545.
- **Mounts.** The override mounts my project roots at the same absolute path, because
  projects store host paths from `fctl connect`. The backend runs as my uid:gid, so worktree
  files stay mine and git doesn't refuse them with "dubious ownership".
- **Login.** Runs need a one-time `docker compose exec backend claude auth login`, and the
  container's `~/.claude` sits on a named volume so the login survives restarts. My host
  login can't be reused: macOS keeps it in the Keychain, which the container can't read.
  That `~/.claude` is the first Claude account, the one this command signs in. The Settings page
  (`/settings`) lists the accounts and does the same login from the browser: it shows claude's
  sign-in link and passes the pasted code to claude. **+ Add account** logs in to a fresh config
  dir under `FCTL_HOME/claude-accounts/`. Runs use the one active account's `CLAUDE_CONFIG_DIR`,
  and **Make active** picks it. **Disconnect** runs `claude auth logout` in the account's dir and
  removes the account, deleting its dir only if it is under `claude-accounts/`. Make active and
  Disconnect are refused while a run is active. §4.3's env stripping and auth check are unchanged.
- **Image.** The backend image has git, uv, node, and the `claude` CLI. Anything else a
  project's test command needs goes in a custom image, set in compose.override.yaml.
- **No gh login.** The image has no `gh` and no GitHub login, so Create PR and Merge PR (§3.7)
  are refused in Docker with a hint to create the PR from the host.
- **Takeover.** The session lives in the container, so §4.4's takeover command becomes
  `docker compose exec -w <worktree> -e CLAUDE_CONFIG_DIR=<account dir> backend claude --resume <session-id>`.

### 4.7 Code layout
The backend under `src/claude_factories/` is split into layers:

```
src/claude_factories/
├── server/         create_app(), lifespan, the §4.5 middleware, domain error → HTTP mapping, deps.py providers
├── controllers/    one APIRouter per resource: reads the request, calls a handler
├── handlers/       use cases as plain functions, one module per resource
├── dto/            pydantic request and response models, one module per resource
├── repositories/   all SQL, one class per table group, wrapping a connection
├── adapters/       subprocesses, each a Protocol plus its implementation, run with argument lists
│   ├── git.py      git
│   └── claude.py   the claude CLI
├── domain/         Status, Stage, and Reviewer enums, the §5.2 stage → status map, NotFound / Conflict / Invalid / TooLarge / Failed
├── lib/            pure parsers and renderers: patch split, diff rows, run log, transcripts, markdown, slug, context files
├── db/             connection, now(), and schema.sql, applied at startup
├── config.py       env and limits: data_dir(), claude_config_dir(), MAX_PATCH, MAX_VIEW, MAX_CONTEXT, MAX_CONTEXT_TOTAL, MAX_CONTEXT_FILES, MAX_BUNDLE, MAX_UNPACKED, MAX_GRAPH
└── cli/            fctl, stdlib only (§4.2)
```

Rules:
- Imports go one way. Imports inside a package are always fine. Across packages:

  | Package | May import |
  |---|---|
  | server/ | controllers, repositories, adapters, db, config, domain |
  | controllers/ | handlers, dto, domain, lib, `server.deps` (not `server.app`) |
  | handlers/ | repositories, adapters, dto, domain, lib, config |
  | repositories/ | db, domain, config |
  | adapters/ | domain, config |
  | dto/ | domain |
  | db/ | config |
  | lib/ | domain |
  | domain/, config.py | nothing |

- Only server/ and controllers/ import fastapi (or starlette). Handlers raise domain errors,
  and server/ maps them to `{"detail": …}`: `NotFound` → 404, `Conflict` → 409,
  `Invalid` → 422, `TooLarge` → 413, `Failed` → 500.
- SQL lives only in repositories/ and db/.
- Handlers get repositories and adapters as arguments. Controllers get them through
  `Depends` on the providers in `server/deps.py`, so tests can swap in fakes with
  `app.dependency_overrides`.
- One handler call is one transaction. A request gets one connection, which commits when
  the handler returns and rolls back if it raises, before the response goes out. Run handlers
  commit before a spawn and record the exit after the request, so they open one transaction
  per step through `transaction()` in `server/deps.py`.
- tests/ mirrors `src/claude_factories/`, for example `tests/controllers/test_projects.py`.
  Each test subdirectory has an `__init__.py`.
- `tests/test_architecture.py` reads every module with `ast` and fails on a wrong import
  direction, fastapi outside server/ and controllers/, or SQL outside repositories/ and db/.
  A new edge changes this section and that test together.

---

## 9. MVP scope vs Later

**MVP**
- `fctl serve`, `fctl setup`, and the CLI in §7.2.
- Workspaces, projects, and `/factory-connect`.
- Create factory (templates → `.claude/`).
- Factory designer: named factories per project, designed on a canvas, with any reviewer set (§3.2).
- Tasks, the board with drag and drop, Run / Run next / Stop / Retry, and run logs.
- Subscription-only runs with the auth check (§4.3), one run at a time.
- Headless runs in worktrees, rework on Request changes, and takeover by
  `claude --resume`.
- Review page: rounds, verdict chips, unified diff, inline comments, Approve, Request changes,
  and Create PR / Merge PR (§3.7).
- `/factory-submit` for changes made without the factory.
- Dashboard, project code page with README landing and a branch picker.
- The local safety measures in §4.5.

**Later**
- Running `/factory <id>` from my own terminal against the same API (option a). Needs a
  `fctl worktree <id>` helper.
- On rework, resuming the previous session (`--resume`) so the builder keeps its memory.
- `claude --bg` with `claude attach` to watch or join a live run.
- Split diff view, interdiff ("changes since round N"), suggestion blocks, resolving comment
  threads.
- A run queue, and parallel runs if I move to Max or to an API key. With an API key, add
  `--max-budget-usd` budgets and per-run cost from the `result` event's `total_cost_usd`.
- Detecting the usage-limit error so the card shows the reset time.
- Switching agents to sonnet if opus uses up Pro limits too fast.
- A warning on Approve if the worktree changed since the latest snapshot.
- A worktree cleanup button for tasks that never go through Merge PR.
- SSE instead of polling, and desktop notifications when a review is waiting.
- Factory template upgrades with a 3-way merge.
- `fctl export` of a task to markdown, search, labels, and priorities.
- Worktree browsing on the code page.
- Scheduled runs (cron checkup agents, other codebase automations), each a run of its own kind
  beside `factory` on the Agents page.

---

## 10. Open questions & assumptions

### Assumptions
1. FACTORY.md is the "factory example" this app runs. Its loop, agents, and rules carry over
   except for §4.3.
2. "max 2 rounds" means at most 2 agent review rounds per run. If round 2 still has CHANGES,
   the approver runs and must ESCALATE. A rework run gets its own 2.
3. The factory files must be committed on `default_branch` before the first Run, because
   worktrees branch from it. The app shows the command; agents never commit, and the app
   commits only a task's worktree, and only when I click Create PR (§3.7).
4. Worktrees live in `<repo>/.claude/worktrees/<id>-<slug>` (Claude Code's own convention).
   The app adds `.claude/worktrees/` and `.fctl/` (agents' text for fctl's stdin, §4.4) to
   `.git/info/exclude`, so the main checkout stays clean and no tracked file changes.
5. Each round's snapshot is the full diff against `HEAD`, which is the base, because agents
   never commit.
6. Rework starts a fresh session. The builder gets its context from the app, not from
   memory.
7. Runs use my Claude Pro subscription through my normal Claude Code login, checked as
   `authMethod: claude.ai`, `subscriptionType: pro` (§4.3). They share usage limits with my
   interactive sessions.
8. One run is active at a time, across all projects. Stopping the app stops
   all runs.
9. Task ids are global integers, the runs' reviewer set is fixed (security, ux, ui, code), and
   the port is 4545. A factory design's reviewers are stored in its graph only.
10. Approve means done, whether or not I have committed yet. I commit and merge by hand or
    with Create PR and Merge PR.
11. The app runs on macOS or Linux. `git`, `claude`, and `uv` are on PATH.
12. Reviewer agents may leave inline comments, and they render like mine.
13. Polling every 3 s is fast enough. There are no websockets in the MVP.
14. The agents keep FACTORY.md's models: opus for spec-writer, builder, security, and
    approver; sonnet for ux, ui, and code. Changing that later means editing one `model:`
    line per agent file.
15. A run that hits the Pro usage limit fails like any other run: the card shows "stalled",
    and I Retry once the limit resets. Detecting the limit itself is on the Later list.

### Open questions
1. Does `claude -p "/factory 12"` reliably invoke a project skill in print mode? If not, the
   prompt becomes "Use the factory skill on task 12". This needs verifying with the
   installed CLI before implementation. The flags themselves are checked against
   `claude --help`.
2. Should Approve be blocked until the worktree branch has a commit? It's not blocked in
   this design, to keep "commit myself" fully manual.
