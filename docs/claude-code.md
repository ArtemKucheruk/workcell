# Claude Factories — Claude Code integration

Part of the [MVP design](MVP.md). Section numbers continue from it.

## 7. Claude Code integration

### 7.1 What ships
| Piece | Where | Installed by |
|---|---|---|
| `fctl` CLI | `~/.local/bin/fctl` | `uv tool install` |
| `/factory-connect` skill | `~/.claude/skills/factory-connect/SKILL.md` | `fctl setup` |
| `/factory-submit` skill | `~/.claude/skills/factory-submit/SKILL.md` | `fctl setup` |
| `/factory` orchestrator skill | `<repo>/.claude/skills/factory/SKILL.md` | Create factory, or a design's Write to repo (§7.3) |
| 7 agents | `<repo>/.claude/agents/{spec-writer,builder,review-security,review-ux,review-ui,review-code,approver}.md` | Create factory, or a design's Write to repo (§7.3) |

Agent models are unchanged from FACTORY.md: opus for spec-writer, builder, security, and
approver; sonnet for ux, ui, and code.

### 7.2 Commands
Each command's full reference (flags, stdin, output, exit codes, an example) is the app's
`/docs/fctl` page, rendered from [`../src/claude_factories/fctl.md`](../src/claude_factories/fctl.md).

| Command | Used by | Calls |
|---|---|---|
| `fctl serve [--host 127.0.0.1] [--port 4545]` | me | starts the app |
| `fctl setup` | me, once | writes the 2 global skills |
| `fctl seed` | me | none: writes demo data straight into an empty `FCTL_HOME` |
| `fctl connect --workspace W [--test-cmd C]` | `/factory-connect` | `POST /api/projects/connect`, then `POST /api/projects/{id}/import-factory` `{}` when `factory/board.json` or `factory/backlog.md` is a file |
| `fctl context` | me | `GET /api/projects/{id}/context` → prints `context_md` as stored |
| `fctl context set` (stdin) | me | `PUT /api/projects/{id}/context`; refuses blank stdin (clear it on the project's Context page) |
| `fctl import-factory [--job ID]` | me, `/factory approve` | `POST /api/projects/{id}/import-factory`: the bootstrap `factory/board.json` jobs, then the `factory/backlog.md` lines it doesn't list, become tasks |
| `fctl export <id> [-o FILE] [--transcripts]` | me | `GET /api/tasks/{id}/export` → writes the task bundle, `task-<id>.zip` by default |
| `fctl import FILE` | me | `POST /api/projects/{id}/import` with the bundle as the body: a new task, or an update of the one it made before |
| `fctl task add "title" [--description TEXT] [--run]` (stdin: description, with `--description -`) | me | `POST /api/projects/{id}/tasks` with `description_md` (+ `/run`) |
| `fctl run <id>` / `fctl run next` | me | `POST /api/tasks/{id}/run`, `/api/projects/{id}/run-next` |
| `fctl rework <id> "note"` | me | `POST /api/tasks/{id}/request-changes` |
| `fctl approve <id>` | me | `POST /api/tasks/{id}/approve` |
| `fctl submit --new --title T` (stdin: description) | `/factory-submit` | `POST /api/projects/{id}/tasks` with `submit` |
| `fctl submit <id>` (stdin: build notes) | builder | `POST /api/tasks/{id}/rounds` |
| `fctl show <id> [--round N \| --feedback]` | all agents | `GET /api/tasks/{id}/context`; with no flag, the project context comes first as `## Project context`: the pinned context, then the project's context cards (`### <title>`, a group's cards as `#### <title>`) |
| `fctl diff <id> [--round N]` | reviewers, approver | `GET /api/tasks/{id}/rounds/{n}/diff` |
| `fctl spec <id>` (stdin) | spec-writer | `PATCH /api/tasks/{id}` `spec_md` |
| `fctl verdict <id> <reviewer> PASS\|CHANGES` (stdin) | reviewers | `PUT …/rounds/latest/verdicts/{reviewer}` |
| `fctl comment <id> <reviewer> --path P --line L` (stdin) | reviewers | `POST /api/tasks/{id}/comments` |
| `fctl decide <id> APPROVE\|ESCALATE` (stdin) | approver | `POST /api/tasks/{id}/decision` |
| `fctl stage <id> <stage>` | orchestrator | `PATCH /api/tasks/{id}` `stage` |
| `fctl round <id>` | orchestrator | `GET /api/tasks/{id}` → prints `round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)` |

How the FACTORY.md commands map to the new ones:

| FACTORY.md | Now |
|---|---|
| `/factory <feature>` | **+ New task** then **Run**, or `fctl task add "…" --run` |
| `/factory next` | **Run next**, or `fctl run next` |
| `/factory rework <id> <note>` | **Request changes**, or `fctl rework <id> "note"` |
| `/factory approve <id>` | **Approve**, or `fctl approve <id>` (marks done, no merge) |

All of them end in the app spawning `/factory <id>`, except approve.

### 7.3 Templates
`.claude/skills/factory/SKILL.md` (excerpt). Create factory renders it with `skill` = `factory`:
```markdown
---
name: {{ skill }}
description: Factory orchestrator. The app runs it headless as "/{{ skill }} <task-id>".
---
# /{{ skill }} $ARGUMENTS
You orchestrate task $ARGUMENTS in {{ name }}. All state lives in the app; read and write it only with fctl.
You are the only one who runs `fctl stage`. Never commit, push, merge, or switch branches.
Test command for this repo: {{ test_cmd }}

## Where to start
`fctl show <id>`, then the step for its stage: no spec → the spec step, no rounds or the latest has verdicts →
the build step with the next round, agent_review → the agent_review step, approval → the approval step.
A stage's step is the first step in the loop below that runs its `fctl stage`. A stage the loop never sets → step 2.

## The loop
1. `fctl show <id>`: read the task, then continue from its current stage (table above).
2. spec → `fctl stage <id> spec`. Spawn `spec-writer`: "Task <id>." Wait for it.
3. build, the next round n → `fctl stage <id> build`. Round 1, or no `builder-<id>` in this session:
   spawn `builder` named `builder-<id>`. Otherwise SendMessage `builder-<id>`. Done when `fctl round <id>` shows round n.
4. agent_review → `fctl stage <id> agent_review`. Spawn these in ONE message, each with "Task <id>.":
   `review-security`, `review-ux`, `review-ui`, `review-code`.
   WAIT FOR ALL: go on only when `fctl round <id>` shows a verdict from each.
5. All reviews PASS? yes → step 6, no → step 7.
6. approval → `fctl stage <id> approval`. Spawn `approver`: "Task <id>, rounds used <x> of 2."
   Rounds exhausted with CHANGES → it must ESCALATE. Wait for it.
   Then step 8.
7. Rounds used < 2? yes → step 3, no → step 6.
8. APPROVE → `fctl stage <id> human_review`. ESCALATE, no decision, or anything else →
   `fctl stage <id> escalated`. Stop and report.

## Conditions
- All reviews PASS?: every verdict on the latest round in `fctl round <id>` is PASS.
- Any review CHANGES?: any of those verdicts is CHANGES.
- Rounds used < N?: this run has used fewer than N rounds (rounds after the one my latest feedback is on).
- Decision APPROVE?: the approver's latest decision in `fctl show <id> --round <n>` is APPROVE.

## Rework
Spawn the build step's agent fresh, with the name that step gives it: "Task <id>, round <n>. Address
`fctl show <id> --feedback`." Keep the rework stage, then go on from the build step's wait.
```

`.claude/agents/review-security.md`:
```markdown
---
name: review-security
description: Security review of the latest round of a factory task.
tools: Read, Grep, Glob, Bash
model: opus
---
Input: a task id. Read `fctl show <id>` and `fctl diff <id>`. Read files in your cwd (the
worktree) as needed. Look for injection, missing authz, secret leaks, unsafe input handling.
Post exactly one verdict, most severe finding first, each with file:line and the fix:
  fctl verdict <id> security PASS|CHANGES <<'EOF'
  …
  EOF
Optional line comments: fctl comment <id> security --path <file> --line <n> <<'EOF' … EOF
Do not edit code. Write nothing else.
```
The builder template says: work only in your cwd, run `{{ test_cmd }}` against the spec's
acceptance criteria, end every round with `fctl submit <id> <<'EOF' <build notes> EOF`, and
never commit.

All 7 agent templates take the stack and conventions from the project context:
"Stack and conventions: the `## Project context` at the top of `fctl show <id>`. Follow it;
don't re-read docs for them. No such section → take them from the repo's docs and code."
The spec-writer and approver still read the docs the request or spec relies on.

**Compiling a design.** `GET /api/factories/{id}/files`, its zip, and Write to repo (`docs/data-model-and-api.md
§6.1`) compile the factory's stored graph in `lib/factory_compile.py`. The default graph compiles byte for byte to
what Create factory writes.
- The slug is the factory's name lowercased, each run of characters outside `a-z0-9` turned into one `-`, and `-`
  trimmed at both ends; nothing left → `factory`. `Nightly Build!` → `nightly-build`. The files are
  `.claude/skills/<slug>/SKILL.md`, then `.claude/agents/<name>.md` per agent node in node order, reachable or not.
  Only the skill named `factory` is the one runs start.
- SKILL.md is the template above with `skill` = the slug, where only the body of `## The loop` (after its heading's
  blank line, up to the blank line before `## Conditions`) is generated from the graph. The template is split before
  any value goes in, so no project value can move that boundary.
- The walk is breadth-first from start, which is step 1. A step is start, one agent, a group of agents, or one
  condition. A step's next nodes are its edges' targets in edge-list order without repeats; a condition has two
  sets, yes then no; a group's set is the union of its members' targets. Each set resolves to: End when empty; the
  step whose nodes it is exactly; a new step when every node is new (two or more agents → one group step). Steps are
  numbered as found, and End last. Nodes no step reaches get no step, but agents still get their files.
- Each step's text is the default listing's for its kind: start, spec writer, builder, and approver alone, reviewers
  (one or more, all reviewers, named in backticks), and End. A custom agent alone is
  ``N. Spawn `notify`: "Task <id>." Wait for it.``; any other group is `N. Spawn these in ONE message, each with
  "Task <id>.":`, the names, and `WAIT FOR ALL: go on only when every one of them has ended.` A condition is
  `N. {question} yes → step k, no → step m.` A step whose next step isn't N+1 ends with `   Then step k.`
  Continuation lines are indented 3 spaces. The approver's `of {n}` takes `n` from the first Rounds used < N step,
  and is left out with none. `side` and `focus` change nothing.
- Refusals are 422s with a string detail. First, over the agents in node order:
  `agent spec-writer needs a description` (blank after trimming; Claude Code needs one to load a subagent). Then,
  in walk order: a set of two or more nodes holding a condition → `builder leads to review-security, …, All reviews
  PASS?: a condition must be the only node it leads to`; a set that is neither all new nor exactly one step's nodes
  → `Rounds used < 2? yes leads to review-security: those must be new nodes, or exactly the nodes of one earlier
  step`. The source is `Start`, an agent's name, a group's names, or `{question} yes`/`no`, and the targets are card
  titles. Everything else compiles: orphans, cycles, a missing branch (→ End), and a handle with two agent edges.
- An agent file is `---\nname: …\ndescription: …\ntools: Read, Grep\nmodel: …\n---\n` and the prompt. Line
  breaks in the description or a tool become spaces, nothing is YAML-quoted, `model: inherit` stays, and an empty
  tools list leaves the `tools:` line out, so the agent gets Claude Code's default tools. Exactly `{{ name }}`,
  `{{ test_cmd }}`, and `{{ default_branch }}` are filled, in one pass over the file. A value is never re-scanned,
  any other `{{ … }}`, `{% … %}`, or `{# … #}` stays as typed, and no graph text goes through Jinja.
- No test command → the 409 Create factory gives, before compiling.

### 7.4 Submit for review, end to end
In a Claude Code session in `~/code/api-server`, where I fixed a bug in my main checkout,
including one new untracked test file:

```
> /factory-submit
```
Claude writes a title and description from the diff and the conversation, then runs:
```
fctl submit --new --title "Fix open redirect after login" <<'EOF'
`next` was passed to redirect() unvalidated. Added is_safe_url(); tests: pytest -q (48 passed).
EOF
```
`fctl` then:
1. Resolves the project. `git rev-parse --path-format=absolute --git-common-dir` gives the
   repo, and `GET /api/projects?path=…` maps it to project `3`. This works the same from a
   worktree.
2. Captures tracked and untracked changes without touching my real index:
   ```
   GIT_INDEX_FILE=$tmp git read-tree HEAD
   GIT_INDEX_FILE=$tmp git add -A            # respects .gitignore
   GIT_INDEX_FILE=$tmp git diff --cached -M HEAD
   ```
3. Sends:
```http
POST /api/projects/3/tasks HTTP/1.1
Host: 127.0.0.1:4545
Content-Type: application/json
X-Requested-By: fctl

{"title": "Fix open redirect after login",
 "description_md": "`next` was passed to redirect() unvalidated. Added is_safe_url(); …",
 "submit": {"base_sha": "9f2c1e4b7d0a",
            "patch": "diff --git a/app/auth.py b/app/auth.py\nindex 4c1d2aa..e81f0b3 100644\n--- a/app/auth.py\n+++ b/app/auth.py\n@@ -41,7 +41,9 @@ def login():\n-    return redirect(request.args.get(\"next\", \"/\"))\n+    nxt = request.args.get(\"next\", \"/\")\n+    return redirect(nxt if is_safe_url(nxt) else \"/\")\n…diff --git a/tests/test_redirect.py b/tests/test_redirect.py\nnew file mode 100644\n…"}}
```
```
← 201 {"task_id":17,"round":1,"files_changed":3,"additions":38,"deletions":2,
       "url":"http://127.0.0.1:4545/tasks/17/review"}
```
The CLI prints `Review #17: 3 files, +38 −2 → http://127.0.0.1:4545/tasks/17/review`.

In the app, card #17 appears in **Review**, marked "waiting on you". The review header reads
`3 files changed +38 −2`. Files changed lists `app/auth.py +4 −2`, `app/safe_url.py (new)
+12`, and `tests/test_redirect.py (new) +22`. The agent chips say "no agent review"
because no factory ran.

**Request changes** on a standalone task only records my feedback (no run). I fix it in my
session and run `/factory-submit` again, which runs `fctl submit 17` and creates round 2.
Inside the factory, the builder runs the same `fctl submit 12` from its worktree.

### 7.5 Who sets status and when
| When | Who | How | Result |
|---|---|---|---|
| I add a task | me | UI / `fctl task add` | backlog |
| Run starts | app | `POST …/run` | in_progress |
| Each loop step | orchestrator | `fctl stage` | in_progress · spec / build / agent_review / approval |
| Approver APPROVE / ESCALATE | orchestrator | `fctl stage` | review · human_review / escalated |
| `/factory-submit` | me via Claude | `POST …/tasks` + submit | review · human_review |
| Request changes | me | UI / `fctl rework` | in_progress · rework (app spawns run) |
| Approve | me | UI / `fctl approve` | done |
| Drag on board | me | `PATCH` | any status, stage cleared (blocked during a run) |
| Run fails | app | — | unchanged; card shows "stalled" + Retry |

Spec-writer, builder, reviewers, and approver never change status. They post only their own
record: spec, round, verdict, or decision.

