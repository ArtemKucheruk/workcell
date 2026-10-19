# Claude Factories — Claude Code integration

Part of the [MVP design](MVP.md). Section numbers continue from it.

## 7. Claude Code integration

### 7.1 What ships
| Piece | Where | Installed by |
|---|---|---|
| `fctl` CLI | `~/.local/bin/fctl` | `uv tool install` |
| `/factory-connect` skill | `~/.claude/skills/factory-connect/SKILL.md` | `fctl setup` |
| `/factory-submit` skill | `~/.claude/skills/factory-submit/SKILL.md` | `fctl setup` |
| `/factory` orchestrator skill | `<repo>/.claude/skills/factory/SKILL.md` | Create factory |
| 7 agents | `<repo>/.claude/agents/{spec-writer,builder,review-security,review-ux,review-ui,review-code,approver}.md` | Create factory |

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
| `fctl connect --workspace W [--test-cmd C]` | `/factory-connect` | `POST /api/projects/connect` |
| `fctl context` | me | `GET /api/projects/{id}/context` → prints `context_md` as stored |
| `fctl context set` (stdin) | me | `PUT /api/projects/{id}/context`; refuses blank stdin (clear it on the board) |
| `fctl task add "title" [--run]` | me | `POST /api/projects/{id}/tasks` (+ `/run`) |
| `fctl run <id>` / `fctl run next` | me | `POST /api/tasks/{id}/run`, `/api/projects/{id}/run-next` |
| `fctl rework <id> "note"` | me | `POST /api/tasks/{id}/request-changes` |
| `fctl approve <id>` | me | `POST /api/tasks/{id}/approve` |
| `fctl submit --new --title T` (stdin: description) | `/factory-submit` | `POST /api/projects/{id}/tasks` with `submit` |
| `fctl submit <id>` (stdin: build notes) | builder | `POST /api/tasks/{id}/rounds` |
| `fctl show <id> [--round N \| --feedback]` | all agents | `GET /api/tasks/{id}/context`; with no flag, the project context comes first as `## Project context` |
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
`.claude/skills/factory/SKILL.md` (excerpt):
```markdown
---
name: factory
description: Factory orchestrator. The app runs it headless as "/factory <task-id>".
---
You orchestrate task $ARGUMENTS. All state lives in the app; read and write it only with fctl.
You are the only one who runs `fctl stage`. Never commit, push, merge, or switch branches.

1. `fctl show <id>`: read the task, then continue from its current stage.
2. No spec yet → `fctl stage <id> spec`, spawn spec-writer.
3. build → `fctl stage <id> build`. On the first round or after rework, spawn builder named
   builder-<id>. Otherwise SendMessage builder-<id>: "Round <n> verdicts: fctl show <id> --round <n>".
   Done when the builder has run `fctl submit <id>`.
4. agent_review → `fctl stage <id> agent_review`. Spawn review-security, review-ux, review-ui,
   review-code in ONE message. WAIT FOR ALL: go on only when `fctl round <id>` shows 4/4.
5. Any CHANGES and fewer than 2 rounds in this run → step 3. Otherwise → step 6.
6. approval → `fctl stage <id> approval`, spawn approver. Rounds exhausted with CHANGES → it must ESCALATE.
7. APPROVE → `fctl stage <id> human_review`. ESCALATE → `fctl stage <id> escalated`. Stop.
Stage rework → spawn a fresh builder-<id>: "Address `fctl show <id> --feedback`", then step 3 on.
Test command for this repo: {{ test_cmd }}
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

