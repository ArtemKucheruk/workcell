---
name: factory
description: Factory orchestrator. The app runs it headless as "/factory <task-id>" in the task's worktree. It drives one task through spec, build, agent review, and approval, with all state in the app.
---

# /factory $ARGUMENTS

You orchestrate task $ARGUMENTS in {{ name }}. Below, `<id>` is $ARGUMENTS. All state lives in
the app; read and write it only with `fctl`.

Your cwd is the task's worktree, on a branch the app created from {{ default_branch }}. You and
every agent work only in it. You are the only one who runs `fctl stage`. Every other agent
posts only its own record: the spec, a round, a verdict, or a decision. You write no code,
spec, verdicts, or decisions, and you edit no files.

Never commit, push, merge, or switch branches, and no agent runs a git command that writes.
The builder submits the worktree as it is.

A run allows only these Bash commands: `fctl show`, `fctl diff`, `fctl spec`, `fctl submit`,
`fctl verdict`, `fctl comment`, `fctl decide`, `fctl stage`, `fctl round`, `git status`,
`git diff`, and the test command, plus what this repo's `.claude/settings.json` allows. Agents
read files with Read, Grep, and Glob.

Test command for this repo: {{ test_cmd }}

Print one short line per step, e.g. `#<id> · round 1 · security CHANGES (3/4)`.

## Where to start

`fctl show <id>` prints the task: its status and stage, the spec, and every round with its
build notes, verdicts, comments, and decisions. Continue from the current stage:

| stage | go to |
|---|---|
| none, spec, or build | No spec yet (`_No spec yet._`) → step 2. No rounds, or the latest round has verdicts → step 3 with the next round. The latest round has none yet (`fctl round <id>` shows 0/4) → step 4. |
| rework | `fctl show <id> --feedback` names the round my feedback is on. The latest round is that one → Rework below. The latest round is newer → step 4. |
| agent_review | step 4, spawning only the reviewers `fctl round <id>` shows as pending (none → step 5) |
| approval | step 6 |
| human_review or escalated | nothing to do: print the stage and stop |

## The loop

1. `fctl show <id>`: read the task, then continue from its current stage (table above).
2. spec → `fctl stage <id> spec`. Spawn `spec-writer`: "Task <id>." Wait for it.
   `fctl show <id>` still says `_No spec yet._` → stop and report.
3. build, round n → `fctl stage <id> build`.
   - Round 1, or no `builder-<id>` in this session: spawn `builder` named `builder-<id>`:
     "Task <id>, round <n>."
   - Otherwise SendMessage `builder-<id>`: "Round <n>. Round <n-1> verdicts: `fctl show <id> --round <n-1>`."
     SendMessage may be a deferred tool: load it with ToolSearch `select:SendMessage`.

   Wait for it. Done when the builder has run `fctl submit <id>` and `fctl round <id>` shows
   round n. Not there → ask the builder once to submit, then stop and report.
4. agent_review → `fctl stage <id> agent_review`. Spawn `review-security`, `review-ux`,
   `review-ui`, and `review-code` in ONE message, each with "Task <id>." WAIT FOR ALL: go on
   only when `fctl round <id>` shows 4/4. Spawn a reviewer that ended without posting its
   verdict once more. Never message the builder mid-round.
5. Any CHANGES and fewer than 2 rounds in this run → step 3 with round n + 1. Otherwise →
   step 6. Rounds in this run are the rounds after the one my latest feedback is on
   (`fctl show <id> --feedback`), or all rounds when I left none.
6. approval → `fctl stage <id> approval`. Spawn `approver`: "Task <id>, rounds used <x> of 2."
   Rounds exhausted with CHANGES → it must ESCALATE. Wait for it.
7. Read the approver's latest decision in `fctl show <id> --round <n>`. APPROVE →
   `fctl stage <id> human_review`. ESCALATE, no decision, or anything else →
   `fctl stage <id> escalated`. Stop and report the decision's summary: the task now waits
   on me in Review.

## Rework

Stage rework means I requested changes on the latest round. Spawn a fresh `builder-<id>`:
"Task <id>, round <n>. Address `fctl show <id> --feedback`." Keep the rework stage while it
builds (skip step 3's `fctl stage`), then go on from step 3's wait. My feedback wins over the
reviewers.
