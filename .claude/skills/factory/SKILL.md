---
name: factory
description: Bootstrap software factory orchestrator. Runs one job at a time through spec → build → 4 reviews → approval → human review, with all state in factory/. Use only when the user types /factory.
argument-hint: "<feature> | next | resume [job-id] | approve <job-id> | rework <job-id> <note>"
disable-model-invocation: true
---

# /factory $ARGUMENTS

You are the orchestrator. FACTORY.md is the design; this file is how you run it. If they
disagree, stop and tell me.

You spawn every agent, create worktrees, snapshot diffs, and are the only writer of
`factory/board.json`. You write no code, specs, reviews, or decisions: each agent writes its
own file. Nobody commits, pushes, merges, rebases, stashes, resets, or switches branches. Your
one git write is `git worktree add`.

Work from the repo root (where FACTORY.md is). For job `<id>`:
J = `factory/jobs/<id>`, W = `.claude/worktrees/<id>`, branch = `factory/<id>`.
Print one short line per step, e.g. `001-setup · round 1 · security CHANGES (3/4)`.

## Commands

| command | does |
|---|---|
| `/factory <feature>` | start gate → new job with the next free id → loop from spec |
| `/factory next` | start gate → first `- [ ] <id>: <text>` line in factory/backlog.md → loop from spec |
| `/factory resume [<id>]` | continue an in_progress job whose session ended (default: the in_progress job) |
| `/factory approve <id>` | review job → done, tick its backlog line, print my git commands |
| `/factory rework <id> <note>` | review job → feedback-<n>.md, stage rework, loop from build round n |

No arguments or anything unclear: print this table and stop.

## Board

`factory/board.json` is `{"jobs": [...]}`, one entry per job:

```json
{ "id": "004-submit", "title": "fctl submit and review rounds",
  "description": "<the feature text or the backlog line, verbatim>",
  "status": "in_progress", "stage": "agent_review", "round": 2,
  "branch": "factory/004-submit", "worktree": ".claude/worktrees/004-submit",
  "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" },
  "history": [ { "at": "2026-10-17T10:03:00Z", "status": "in_progress", "stage": "spec" } ] }
```

- `title`: you write it, under 60 chars. It becomes the commit message.
- `round`: the current round, 0 before the first build. `reviews`: that round's verdicts.
- Every status or stage change appends `{"at": <date -u +%FT%TZ>, "status", "stage"}` to `history`.
- Setting a stage sets the status:

  | stage | status |
  |---|---|
  | spec, build, agent_review, approval, rework | in_progress |
  | human_review, escalated | review |
  | null (only via approve) | done |

- After every write, `python3 -m json.tool factory/board.json >/dev/null` must pass. The
  dashboard polls this file.

## Start gate (`<feature>` and `next`)

Stop and tell me what to do if any check fails:
1. `git rev-parse --verify -q main^{commit}` fails → I must run
   `git init -b main && git add -A && git commit -m "Docs and factory"`.
2. A job is in_progress or review → name it and its next command (resume, approve, rework).
3. A done job still has its worktree, or its branch exists and is missing from
   `git branch --merged main` → I must finish that job's approve commands.

## Start a job

1. Id. `next`: the id on the line, description = the line's text. `<feature>`: the next number
   after the highest in backlog.md and board.json, zero-padded to 3, plus a 1–3 word slug
   (`013-rate-limit`), description = the feature text. backlog.md is not changed.
2. `grep -qxF .claude/worktrees/ .git/info/exclude || echo .claude/worktrees/ >> .git/info/exclude`
3. `git worktree add -b factory/<id> .claude/worktrees/<id> main`
4. `mkdir -p factory/jobs/<id>`. Add the board entry: stage spec, round 0, reviews pending.

## The loop

### spec
Spawn `spec-writer`: "Job <id>." Wait for it. No J/spec.md → stop and report.

### build, round n
n is 1 for a new job, round + 1 after a CHANGES round, set by `rework`, or the current round on `resume`.
1. Set `round` = n, all reviews pending, stage build (keep rework if `rework` just set it).
   `mkdir -p J/round-<n>`.
2. Builder:
   - n = 1: spawn `builder` with name `builder-<id>`: "Job <id>, round 1."
   - otherwise SendMessage `builder-<id>`: "Round <n>. Read J/round-<n-1>/review-*.md and
     J/feedback-<n>.md if it exists. Write J/round-<n>/build.md." If that builder is gone
     (new session), spawn a fresh `builder` named `builder-<id>` with "Job <id>, round <n>."
     SendMessage may be a deferred tool: load it with ToolSearch `select:SendMessage`.
3. Wait for it. No J/round-<n>/build.md → ask the builder once to write it, then stop and
   report if it's still missing (`/factory resume` picks up from here).
4. Snapshot the worktree, untracked files included, without touching its index:
   ```sh
   t=$(mktemp -d); wt=.claude/worktrees/<id>
   GIT_INDEX_FILE=$t/index git -C $wt read-tree HEAD
   GIT_INDEX_FILE=$t/index git -C $wt add -A
   GIT_INDEX_FILE=$t/index git -C $wt diff --cached -M HEAD > factory/jobs/<id>/round-<n>/diff.patch
   rm -rf $t
   ```
   Over 5 MB means generated files got in (.venv/, caches): have the builder fix .gitignore,
   then snapshot again.

### agent_review, round n
1. Stage agent_review.
2. Spawn `review-security`, `review-ux`, `review-ui`, `review-code` in ONE message, each with
   "Job <id>, round <n>."
3. As each finishes, read the first line of J/round-<n>/review-<r>.md and set `reviews.<r>`.
   Anything but `VERDICT: PASS` counts as CHANGES.
4. WAIT FOR ALL: the round is done only when all 4 review files exist. Spawn a reviewer
   that ended without its file once more. Never message the builder mid-round.

### next round or approval
- This run started at round s = the highest k with J/feedback-k.md, else 1.
  Rounds used = n − s + 1 (max 2).
- Any CHANGES and rounds used < 2 → build, round n + 1.
- Otherwise → approval.

### approval
Stage approval. Spawn `approver`: "Job <id>, round <n>, rounds used <x> of 2." Wait for it.
Read the first line of J/decision.md:
- `APPROVE` → stage human_review.
- `ESCALATE`, a missing file, or anything else → stage escalated.

Stop. Report the decision's summary, J, and my next step: read the job on the dashboard,
then `/factory approve <id>` or `/factory rework <id> <note>`.

## approve <id>

The job must be in review (human_review or escalated). Set status done, stage null, append
history. In backlog.md change `- [ ] <id>:` to `- [x] <id>:` if that line exists. Print:

```
git -C .claude/worktrees/<id> add -A
git -C .claude/worktrees/<id> commit -m "<title>"
git merge --ff-only factory/<id>
git worktree remove .claude/worktrees/<id> && git branch -d factory/<id>
```

and: "Don't commit to main before the merge, or --ff-only fails."

## rework <id> <note>

The job must be in review. n = round + 1. Write the note verbatim to J/feedback-<n>.md. Set
stage rework, then run the loop from build, round n.

## resume [<id>]

The job must be in_progress. Continue from its stage:
- spec: J/spec.md exists → build round 1; else spec.
- build or rework: J/round-<round>/build.md exists → snapshot (build step 4), then
  agent_review; else build with n = round.
- agent_review: fill `reviews` from the files that exist; spawn only the missing reviewers.
- approval: run approval again.

## Dashboard

`python3 -m http.server -b 127.0.0.1 -d factory` → http://127.0.0.1:8000/dashboard.html
