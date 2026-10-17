---
name: factory
description: Bootstrap software factory orchestrator. Each run drives one job through spec → build → 4 reviews → approval → human review, with all state in factory/. Independent jobs run side by side in separate terminals. Use only when the user types /factory.
argument-hint: "<feature> | next | resume [job-id] | approve <job-id> | rework <job-id> <note>"
disable-model-invocation: true
---

# /factory $ARGUMENTS

You are the orchestrator. FACTORY.md is the design; this file is how you run it. If they
disagree, stop and tell me.

You spawn every agent, create worktrees, snapshot diffs, and, with the orchestrators in other
terminals, are the only writers of `factory/board.json`. You write no code, specs, reviews, or
decisions: each agent writes its own file. The one exception is a skipped review-ui file
(agent_review step 2). Agents never run git writes. Yours are exactly:
`git fetch`, `git worktree add`, publish (commit, push, PR), and approve (PR merge, worktree
remove, branch delete). Nobody rebases, stashes, resets, force-pushes, or switches branches.
Commits and PRs carry no Claude attribution: no `Co-Authored-By` trailer, no "Generated with
Claude Code" line.

Work from the repo root (where FACTORY.md is). For job `<id>`:
J = `factory/jobs/<id>`, W = `.claude/worktrees/<id>`, B = `factory/<type>/<id>`, the board's
`branch`.
Print one short line per step, e.g. `001-setup · round 1 · security CHANGES (3/4)`.

This terminal drives one job. Other terminals may run their own `/factory` jobs at the same
time: touch only your job's W, J, and board entry. Run `approve` and `rework` in the terminal
that ran the job; its builder lives there.

## Commands

| command | does |
|---|---|
| `/factory <feature>` | start gate → new job with the next free id → loop from spec |
| `/factory next` | start gate → first `- [ ] <id>: <text>` line in factory/backlog.md that no active job blocks → loop from spec |
| `/factory resume [<id>]` | continue an in_progress job whose session ended (default: the only in_progress job) |
| `/factory approve <id>` | review job → merge its PR, done, tick its backlog line, stop its builder, remove worktree and branch |
| `/factory rework <id> <note>` | review job → feedback-<n>.md, stage rework, loop from build round n, push to the same PR |

No arguments or anything unclear: print this table and stop.

## Board

`factory/board.json` is `{"jobs": [...]}`, one entry per job:

```json
{ "id": "004-submit", "title": "fctl submit and review rounds",
  "description": "<the feature text or the backlog line, verbatim>",
  "status": "in_progress", "stage": "agent_review", "round": 2,
  "branch": "factory/feat/004-submit", "worktree": ".claude/worktrees/004-submit", "pr": null,
  "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" },
  "history": [ { "at": "2026-10-17T10:03:00Z", "status": "in_progress", "stage": "spec" } ] }
```

- `title`: you write it, under 60 chars. It becomes the commit message and the PR title.
- `pr`: null until publish opens the PR, then its URL.
- `round`: the current round, 0 before the first build. `reviews`: that round's verdicts.
- Every status or stage change appends `{"at": <date -u +%FT%TZ>, "status", "stage"}` to `history`.
- Setting a stage sets the status:

  | stage | status |
  |---|---|
  | spec, build, agent_review, approval, rework | in_progress |
  | human_review, escalated | review |
  | null (only via approve) | done |

- Other terminals write board.json too. Change it only with this command, which holds a lock
  while it reads and writes, and touch only your job's entry (on start, append it). The
  dashboard polls this file.
  ```sh
  python3 - <<'EOF'
  import fcntl, json
  with open("factory/board.json", "r+") as f:
      fcntl.flock(f, fcntl.LOCK_EX)
      board = json.load(f)
      job = next(j for j in board["jobs"] if j["id"] == "<id>")
      # your change here, plus its history entry
      f.seek(0); json.dump(board, f, indent=2); f.write("\n"); f.truncate()
  EOF
  ```

## Start gate (`<feature>` and `next`)

Stop and tell me what to do if any check fails:
1. `git fetch origin`, then `git rev-parse --verify -q origin/main^{commit}` fails, or
   `gh auth status` fails → I must push main to GitHub or run `gh auth login`.
2. A done job still has its worktree or its local branch → I must finish its cleanup
   (approve step 5).
3. Blocked (below). `next`: walk the unchecked backlog lines in order, skipping ids already on
   the board, and take the first that isn't blocked. `<feature>`: check the feature alone.
   Print one line per blocked candidate, e.g.
   `007-review-conversation · blocked by 006-agent-api: shows the verdicts 006 stores`.
   Nothing left → tell me which job each candidate waits on, and that `/factory next` after
   an approve tries again.

**Blocked.** Active jobs are the board's in_progress and review jobs. Read the candidate's
text and the doc sections it cites; for each active job, its description, J/spec.md `## Files`,
and the file list of its latest diff.patch. The candidate is blocked when it:
- needs something an active job or an earlier unchecked backlog line adds (a table, endpoint,
  page, or CLI command it calls or extends), or
- would edit the same part of a file as an active job: the same function, template block,
  route or import list, or test. New files and far-apart edits in one file merge cleanly.

When unsure, it's blocked.

## Start a job

1. Id. `next`: the id on the line, description = the line's text. `<feature>`: the next number
   after the highest in backlog.md and board.json, zero-padded to 3, plus a 1–3 word slug
   (`013-rate-limit`), description = the feature text. backlog.md is not changed.
   Type, from the description: feat (new behavior), fix, ci, docs, refactor, test, or chore.
2. `grep -qxF .claude/worktrees/ .git/info/exclude || echo .claude/worktrees/ >> .git/info/exclude`
3. `git worktree add --no-track -b B .claude/worktrees/<id> origin/main`. It fails
   because the branch exists → another terminal just took this id: back to start gate check 3,
   skipping it.
4. `mkdir -p factory/jobs/<id>`. Add the board entry: branch B, stage spec, round 0, reviews
   pending, pr null.

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
4. Snapshot the worktree, untracked files included, without touching its index, against the
   job's base on main (after a rework, HEAD is the job's earlier commit). Vendored `*.min.*`
   files and `uv.lock` stay out of the patch: every reviewer and the approver read it.
   ```sh
   t=$(mktemp -d); wt=.claude/worktrees/<id>
   base=$(git -C $wt merge-base HEAD origin/main)
   GIT_INDEX_FILE=$t/index git -C $wt read-tree HEAD
   GIT_INDEX_FILE=$t/index git -C $wt add -A
   GIT_INDEX_FILE=$t/index git -C $wt diff --cached -M $base -- . ':!*.min.*' ':!uv.lock' > factory/jobs/<id>/round-<n>/diff.patch
   rm -rf $t
   ```
   Over 5 MB means generated files got in (.venv/, caches): have the builder fix .gitignore,
   then snapshot again.

### agent_review, round n
1. Stage agent_review.
2. Spawn `review-security`, `review-ux`, `review-ui`, `review-code` in ONE message, each with
   "Job <id>, round <n>." Skip `review-ui` when the diff touches no UI files, i.e.
   `grep -qE '^diff --git .*/(templates|static)/' J/round-<n>/diff.patch` fails: write
   J/round-<n>/review-ui.md yourself, `VERDICT: PASS` then
   `no UI in this job (diff touches no templates/ or static/; review-ui skipped)`.
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

Then publish.

### publish
Commit message: `<title>` for the first commit, `<title> (round <n>)` after a rework.
```sh
git -C W add -A
git -C W diff --cached --quiet || git -C W commit -m "<message>"
git -C W push -u origin B
```
- `pr` null → `gh pr create --base main --head B --title "<title>" --body-file J/decision.md`
  (no decision.md: `--body "<description>"`). Set `pr` to the URL it prints.
- `pr` set → `gh pr edit B --body-file J/decision.md`. The push already updated it.
- Any command fails → stop and report it. The job stays in review; approve publishes again
  before merging.

Stop. Report the decision's summary, J, the PR URL, and my next step: read the PR (or the
job on the dashboard), then `/factory approve <id>` or `/factory rework <id> <note>`.

## approve <id>

The job must be in review (human_review or escalated).
1. `git -C W status --porcelain` not empty → stop, list the files, and ask whether to
   publish them into the PR first. `pr` null (publish failed earlier) → publish first.
2. `gh pr merge B --merge`. Fails (conflict, required checks, already closed) →
   stop and report it; the job stays in review.
3. Set status done, stage null, append history. In backlog.md change `- [ ] <id>:` to
   `- [x] <id>:` if that line exists.
4. Stop the builder: TaskStop `builder-<id>` (deferred: ToolSearch `select:TaskStop`).
   Not found (a new session, or another terminal ran the job) is fine.
5. Clean up. A branch that's already gone (GitHub auto-delete) is fine:
   ```sh
   git worktree remove .claude/worktrees/<id>
   git branch -D B        # -D: the merge commit is on origin/main, not local
   git push origin --delete B
   git fetch origin --prune
   ```
   `worktree remove` refuses (dirty files) → stop and tell me; never `--force`.

Report the merged PR URL, and that my main checkout isn't updated: `git pull` when I want it.

## rework <id> <note>

The job must be in review. n = round + 1. Write the note verbatim to J/feedback-<n>.md. Set
stage rework, then run the loop from build, round n. Publish adds the new commit to the open PR.

## resume [<id>]

The job must be in_progress. No id and more than one in_progress job → list them and stop; I
name one. Continue from its stage:
- spec: J/spec.md exists → build round 1; else spec.
- build or rework: J/round-<round>/build.md exists → snapshot (build step 4), then
  agent_review; else build with n = round.
- agent_review: fill `reviews` from the files that exist; spawn only the missing reviewers
  (review-ui follows the skip rule in agent_review step 2).
- approval: run approval again.

## Dashboard

`python3 -m http.server -b 127.0.0.1 -d factory` → http://127.0.0.1:8000/dashboard.html
