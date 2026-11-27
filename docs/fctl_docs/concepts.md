# Concepts

What `fctl` reads and writes, and how the pieces fit. Field names match the API
([`docs/data-model-and-api.md`](../data-model-and-api.md)).

## Workspaces and projects

- A **workspace** is a named group of projects, for example `personal` or `work`.
- A **project** is one git repo, identified by its **main checkout's** absolute path. It holds the
  repo's default branch (`origin/HEAD`, else the main checkout's current branch), its `origin` URL,
  its **test command** (`test_cmd`, which factory runs execute), and its **project context**.
- `fctl connect --workspace W [--test-cmd C]` registers the repo, or updates it. Commands that
  work "on the current repo" resolve the project from the main checkout, so they work the same from
  a worktree or a subdirectory (`git rev-parse --git-common-dir`, then
  `GET /api/projects?path=…`). An unconnected repo gets
  `404 no project at <path>; in that repo, run fctl connect --workspace <name>, or if the checkout
  moved, change the path on the project's Settings page`. After a move, the Settings page's Path form
  points the existing project at the new folder and keeps its tasks and history (119).

## Tasks

A task is one unit of work in a project. **Task ids are global** across projects, so commands
that take an id work from any directory.

There are two kinds, and the difference matters:

| | Factory task | Standalone (submitted) task |
|---|---|---|
| Made by | `fctl task add`, **+ New task**, `fctl import-factory`, `fctl import` | `fctl submit --new` (the `/factory-submit` skill) |
| Starts in | Backlog | Review · human_review, with round 1 |
| Branch and worktree | `factory/<id>-<slug>` in `<repo>/.claude/worktrees/<id>-<slug>`, made on the first run | none: the change lives in the user's own tree |
| Agents | the `/factory` loop: spec, build, agent review, approval | none ("no agent review") |
| A new round | `fctl submit <id>` from the builder; status unchanged | `fctl submit <id>`; puts the task back in Review |
| Request changes | records the note, moves to `in_progress · rework`, and starts a rework run | records the note and moves it; no run |
| Approve | `done`, and prints commit, push, and `wt remove` commands | `done`, and prints the commit line only |

## Status and stage

**Status** is the board column. **Stage** says where in the loop a task is. Setting a stage sets
the status:

| Stage | Status it sets | Set by |
|---|---|---|
| (none) | `backlog` | the user adds a task |
| (none) | `in_progress` | the app, when a run starts |
| `spec` | `in_progress` | orchestrator, `fctl stage <id> spec` |
| `build` | `in_progress` | orchestrator |
| `agent_review` | `in_progress` | orchestrator |
| `approval` | `in_progress` | orchestrator |
| `rework` | `in_progress` | the user's Request changes (`fctl rework`), not the orchestrator |
| `human_review` | `review` | orchestrator after APPROVE; the app on `fctl submit --new` |
| `escalated` | `review` | orchestrator after ESCALATE or no decision |
| (none) | `done` | the user's Approve (`fctl approve`) |

A board drag (`PATCH` status and position) clears the stage and is refused while a run is active.
Spec-writer, builder, reviewers, and approver never change status or stage.

`fctl show <id>` prints `Status: in_progress · agent_review` (status, then stage when there is one).

## Spec

The spec is one markdown document per task, `spec_md`. `fctl spec <id>` replaces it whole; blank
stdin is refused, so it can't be wiped by accident. Until one is posted, `fctl show` prints
`_No spec yet._` under `## Spec`.

The default spec layout (the spec-writer's template): `# title`, `## Goal`,
`## Acceptance criteria` (`- [ ] AC1: <behavior> → <expected result>`), `## Files`,
`## Out of scope`, `## Open questions` (`- Q1: … Default: …`).

## Rounds

A **round** is one submitted snapshot of work: `n` (from 1), the `base_sha` it was diffed against,
the patch, and the build notes. It is never edited; the next submit makes round `n+1`.

- `fctl submit` captures the patch from the current directory's tree: tracked and untracked
  files, `.gitignore` respected, against `HEAD`, through a temp index (the real index is
  untouched). Ignored files never reach a round.
- The patch must be non-empty (`422 no changes to submit`) and at most 5 MB
  (`413 patch over 5 MB`).
- Each round has a trigger: `initial` (round 1), `human` (the round after the user's Request
  changes on the one before), or `agent` (after reviewers' CHANGES).
- `fctl diff <id> [--round N]` prints a round's patch; the default is the latest.

**Rounds used** in a run are the rounds after the one the user's latest feedback is on, or every
round when there is no feedback. The default factory allows 2 per run (`Rounds used < 2?`); the
ML experiment template allows 3.

## Verdicts

Each round has four verdict **slots**: `security`, `ux`, `ui`, `code`. A slot is `pending` until
its reviewer posts `PASS` or `CHANGES` with markdown findings. Verdicts always go on the
**latest** round, and posting again replaces that slot's verdict.

- `fctl round <id>` prints `round 2: security=PASS ux=PASS ui=pending code=PASS (3/4)`.
- **All reviews PASS?** means all four slots on the latest round are `PASS`.
- **Any review CHANGES?** means at least one is `CHANGES`.
- Templates with fewer than four reviewers leave the unused slots `pending`, so they branch on
  "Any review CHANGES?" instead. A reviewer with its own focus (`review-eval`, `review-tests`)
  posts under `code`.

## Comments

A **line comment** sits on one line of a file in a round's diff, on the new side:
`fctl comment <id> <reviewer> --path P --line L`. It always goes on the latest round, `P` must be
a file in that round's diff (`422 app/x.py is not in round 2`), and `L` counts from 1. The author
is the reviewer slot. The user's own comments (author `me`) come with their feedback.

## Decisions

A **decision** sits on the latest round. Every post adds one; the latest counts.

| Who | Decisions | How |
|---|---|---|
| approver agent | `APPROVE`, `ESCALATE` | `fctl decide <id> APPROVE\|ESCALATE` (does not move the task) |
| the user (`me`) | `APPROVE`, `CHANGES_REQUESTED` | `fctl approve <id>`, `fctl rework <id> "note"` (both move the task, both need status `review`) |

The orchestrator reads the approver's latest decision and moves the task itself with
`fctl stage`.

## Feedback

**Feedback** is the user's latest `CHANGES_REQUESTED`: its note plus the user's line comments on
that round. `fctl show <id> --feedback` prints it under `## Feedback on round N`;
`404 #12 has no feedback` when there is none. In a rework, the user's feedback wins over the
reviewers.

## Project context

The **project context** is the stack and conventions every agent follows. It has two parts:

- the pinned `context_md`, at most 16 KB: `fctl context` prints it, `fctl context set` replaces it
  from stdin;
- **context cards** from the project's Context page (some read from a repo file), in order, with
  groups.

The full `fctl show <id>` (no flag) puts both first, under `## Project context`. Agents follow it
and don't re-read the docs it already covers. With no such section, take the stack from the repo's
docs and code.

## Blockers

A task can wait on other tasks of the **same project** (`blocked_by`). It is blocked until all of
them are `done`, and Run, Retry, Run next, and a rework's run refuse it:
`409 #15 is blocked by #12, #14; finish those first or remove the dependency`. Links are set with
`fctl task add --blocked-by 12,14`, `fctl task block <id> --by <id>`, and
`fctl task unblock <id> --by <id>`. A self-link, a cross-project link, or a cycle is a `422`.
`fctl run next` skips blocked tasks.

## Runs

A **run** is the app spawning headless `claude -p "/factory <id>"` in the task's worktree. One run
per task at a time, and at most `max_concurrent_runs` (default 2, on Settings) across all projects.

- Started by the user: **Run**, **Retry**, **Run next**, **Request changes**, or `fctl run`,
  `fctl run next`, `fctl task add --run`, `fctl rework`.
- The first run creates the worktree with worktrunk; later runs reuse it. Before every run the
  app copies the main checkout's gitignored files in (not `.venv/`,
  `.claude/settings.local.json`, or `.fctl/`).
- Each run uses one **Claude account**. **Auto** picks the preferred account unless it is low
  (5h ≥ 80%, 7d ≥ 90%, or limited), then the logged-in account with the most headroom.
  `fctl run <id> --account <id|email>` forces one. Run next, Retry, and rework's run always use
  Auto.
- A run that dies leaves the task's status as it was; the card shows "stalled" and Retry. The next
  `/factory <id>` continues from the stage (see [roles.md § Orchestrator](roles.md#orchestrator-factory-id)).
- Stopping the backend stops every run; at the next start a run still marked running becomes
  `failed: app restarted`.

## The loop

```
fctl show ─► no spec ─► stage spec ─► spec-writer ─► fctl spec
                │
                ▼
          stage build ─► builder ─► fctl submit <id>          (round n)
                │
                ▼
       stage agent_review ─► 4 reviewers in parallel ─► fctl verdict (+ fctl comment)
                │
     all PASS? ─┼─ no ─► rounds used < 2? ─ yes ─► stage build (round n+1)
                │                         └─ no ──┐
               yes                                │
                ▼                                 ▼
          stage approval ─► approver ─► fctl decide APPROVE|ESCALATE
                │
   APPROVE ─► stage human_review      anything else ─► stage escalated
                │
                ▼
     user: fctl approve (done)  or  fctl rework "note" (rework run starts)
```

## What `fctl show` prints

`fctl show <id>` is markdown blocks joined by one blank line. A heading's body is left out when it
is blank. Agent text passes through unchanged, so a spec's own headings appear inside `## Spec`.

```
## Project context                      ← full view only, when there is context or cards
<pinned context_md>
### <card title>
<card text>
#### <grouped card title>
<card text>

# #12 Rate-limit login endpoint
Status: in_progress · agent_review

## Description
<description_md>

## Spec
<spec_md, or _No spec yet._>

## Round 1 — build notes                ← one set per round, oldest first
<build_md>

## Verdicts
### security: PASS
<findings>
### ux: pending
### ui: CHANGES
<findings>
### code: PASS
<findings>

## Comments                             ← only when the round has comments
### security on app/auth.py:44 (new)
<comment>

## Decisions                            ← only when the round has decisions
### approver: ESCALATE
<summary>
### me: CHANGES_REQUESTED
<the user's note>

## Feedback on round 1                  ← --feedback only
<the user's note>
## Comments
### me on app/auth.py:40 (new)
<comment>
```

- `fctl show <id> --round N` prints the heading, status, description, spec, and only round N.
  No project context.
- `fctl show <id> --feedback` prints the heading, status, description, spec, and the feedback
  block only. No project context, no rounds.
- `--round` and `--feedback` don't go together (exit `2`).
