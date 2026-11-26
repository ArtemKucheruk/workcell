# Roles

One playbook per role. In a factory run, the `/factory` skill and the agent files in the repo's
`.claude/` are your instructions; this page explains the `fctl` side of them and the traps around
it. Where your own skill or agent file says something more specific, follow it.

- [Orchestrator (`/factory <id>`)](#orchestrator-factory-id)
- [Spec-writer](#spec-writer)
- [Builder](#builder)
- [Reviewers](#reviewers)
- [Approver](#approver)
- [Interactive session (working for the user)](#interactive-session-working-for-the-user)

Every role in a run shares this:

- Your cwd is the task's worktree. Work only there.
- Bash runs only the allowlist ([environment.md § What Bash may run](environment.md#what-bash-may-run)).
  Read files with Read, Grep, and Glob.
- Stack and conventions come from `## Project context` at the top of `fctl show <id>`. No such
  section → the repo's docs and code.
- Post markdown from a `.fctl/<name>.md` file, never a long heredoc.
- Never write git history; never quote secrets.

---

## Orchestrator (`/factory <id>`)

The app starts you headless as `claude -p "/factory <id>"`. You drive one task through the loop.
You are the **only** agent that runs `fctl stage`. You write no code, spec, verdicts, or
decisions, and you edit no files.

### Commands you use

| Command | For |
|---|---|
| `fctl show <id>` | Where to start, and to read the spec and rounds |
| `fctl show <id> --round <n>` | The approver's latest decision on round n |
| `fctl show <id> --feedback` | Which round the user's feedback is on (rework, rounds used) |
| `fctl round <id>` | Whether round n exists and how many verdicts are in |
| `fctl stage <id> <stage>` | Every step's move |

### Where to start

Read `fctl show <id>` and continue from the stage:

| Stage | Go to |
|---|---|
| none, `spec`, or `build` | `_No spec yet._` → spec step. No rounds, or the latest round has verdicts → build step with the next round. The latest round has none (`fctl round` shows `(0/4)`) → agent_review step. |
| `rework` | `fctl show <id> --feedback` names the round the feedback is on. Latest round is that one → Rework. Latest round is newer → agent_review step. |
| `agent_review` | agent_review step, spawning only reviewers still `pending` in `fctl round` (none → the step after it) |
| `approval` | approval step |
| `human_review`, `escalated` | nothing to do: print the stage and stop |

### The loop (default template)

1. `fctl show <id>`, then the step for the stage.
2. `fctl stage <id> spec` → spawn `spec-writer` ("Task <id>."), wait. Still `_No spec yet._` →
   stop and report.
3. `fctl stage <id> build` → round 1, or no `builder-<id>` in this session: spawn `builder` named
   `builder-<id>` ("Task <id>, round <n>."). Otherwise SendMessage `builder-<id>`
   ("Round <n>. Round <n-1> verdicts: `fctl show <id> --round <n-1>`."). Done when
   `fctl round <id>` shows `round <n>`. Not there → ask the builder once to submit, then stop and
   report.
4. `fctl stage <id> agent_review` → spawn the four reviewers in **one** message, each "Task <id>.".
   Wait until `fctl round <id>` shows all four posted. Respawn a reviewer that ended without
   posting, once. Never message the builder mid-round.
5. All four PASS → step 6. Otherwise step 7.
6. `fctl stage <id> approval` → spawn `approver` ("Task <id>, rounds used <x> of 2."). Rounds
   exhausted with CHANGES → it must ESCALATE. Wait, then step 8.
7. Rounds used < 2 → step 3 with round n+1. Otherwise step 6.
8. Latest approver decision in `fctl show <id> --round <n>`: `APPROVE` →
   `fctl stage <id> human_review`. `ESCALATE`, no decision, or anything else →
   `fctl stage <id> escalated`. Stop and report the decision's summary.

**Rework.** Stage `rework` means the user requested changes on the latest round. Spawn the
builder fresh, named `builder-<id>`: "Task <id>, round <n>. Address `fctl show <id> --feedback`."
Keep the `rework` stage while it builds (skip step 3's `fctl stage`), then continue from step 3's
wait. The user's feedback wins over the reviewers.

**Rounds used** are the rounds after the one the user's latest feedback is on (from
`fctl show <id> --feedback`), or every round when `--feedback` says `404 … has no feedback`.

**Other templates** (Bug fix, Security audit, ML experiment, Test coverage) have fewer reviewers.
Their unused slots stay `pending`, so they branch on "Any review CHANGES?" rather than "All
reviews PASS?". The ML experiment template allows 3 rounds.

### Output and stopping

Print one short line per step, e.g. `#12 · round 1 · security CHANGES (3/4)`. Stop and report
(don't improvise a workaround) when an agent couldn't post its record, a `fctl` call is refused, or
a Bash call is denied. A denied action stays denied; asking another agent to do the same thing a
different way just launders it.

---

## Spec-writer

Input: "Task <id>." Your worktree is fresh from the default branch; nothing is built yet.

1. `fctl show <id>`: the title and description are the request; `## Project context` is the stack.
2. Read the repo's docs (README, `docs/`, design notes) and the code the request touches, with
   Read, Grep, and Glob.
3. Write the spec with the Write tool to `.fctl/spec.md` (Read it first if it exists):
   ```markdown
   # <short title>

   ## Goal
   2–4 sentences.

   ## Acceptance criteria
   - [ ] AC1: <behavior> → <expected result: status code, output, row, page content>

   ## Files
   ## Out of scope
   ## Open questions
   - Q1: <what the request and docs don't decide>. Default: <what the builder should do>.
   ```
4. `fctl spec <id> < .fctl/spec.md` → expect `Spec saved on #<id>`.

Rules:
- The request and the docs decide. Anything they leave open goes under Open questions with a
  default; never settle it silently in a criterion.
- One testable behavior per criterion. Stay inside the request. A new dependency needs its reason.
- If the spec needs edits under `.claude/` (agents, skills, settings), say so under Open questions:
  the builder can't write there in a headless run.
- Bash only for `fctl`. Write nothing but `.fctl/spec.md`.

Template variants post the same way: `bug-spec-writer` (root cause as `file:line`, every caller,
AC1 a failing regression test), `security-auditor` (`## Report` the builder writes to
`SECURITY-AUDIT.md`; cite secrets by `file:line`, never value), `data-check` (`## Metrics gate`),
`coverage-planner` (at most 5 risky untested behaviors).

---

## Builder

Input: "Task <id>, round <n>." The orchestrator spawns you as `builder-<id>` and messages you for
later rounds; a rework spawns you fresh.

1. Read:
   - `fctl show <id>`: the spec, and every earlier round's notes, verdicts, and comments.
   - Round n > 1: `fctl show <id> --round <n-1>`. Fix every finding in a CHANGES verdict.
   - Rework: `fctl show <id> --feedback`. The user's note and line comments win over reviewers.
2. Implement the spec in your cwd, following the code around it.
3. One test per acceptance criterion. Run the test command until it passes. `.venv/` isn't copied:
   `uv sync` (or the repo's install step) first if the tests need it.
4. Keep `.gitignore` covering generated files (build output, caches, virtualenvs). `fctl submit`
   sends every changed and untracked file that isn't ignored.
5. Write the build notes with the Write tool to `.fctl/build.md`:
   ```markdown
   # Round <n>
   ## Changes
   - path: what changed and why
   ## Criteria → tests
   - AC1 → <test file>::<test name>
   ## Review findings          (round > 1)
   - reviewer · finding → fixed, or why not
   ## Open questions
   - Q1 → the default you used
   ## Test output
   <the last lines of the test command's output, verbatim>
   ```
6. `fctl submit <id> < .fctl/build.md` → expect `Round <n> of #<id>: …`.
7. End with one line: `round <n> done: <N> passed`.

Traps:
- **Every `fctl submit` makes a new round.** Submit exactly once per round. Don't resubmit to fix
  typos in the notes: it burns a round of the run's 2.
- Check the printed round number. `Round 3` when you expected 2 means a round was already
  submitted; report it rather than submitting again.
- `422 no changes to submit`: the tree has nothing git doesn't ignore. Check `git status`; maybe
  your output landed in an ignored path. A task whose deliverable is a file (an audit report)
  must write it every run.
- `413 patch over 5 MB`: a generated or vendored file is in the diff; ignore it.
- Edits under `.claude/` are denied in a run. Don't retry; say so in the notes' Open questions
  and submit the rest.
- If you start a server to try the change, use `$FCTL_BACKEND_PORT` / `$FCTL_FRONTEND_PORT` and stop
  it before you finish ([environment.md](environment.md#testing-the-app-without-touching-real-data)).
- No git writes. `git status` and `git diff` only.

---

## Reviewers

Input: "Task <id>." You review the **latest** round and post exactly **one** verdict in your slot.

| Agent | Slot | Looks at |
|---|---|---|
| `review-security` | `security` | injection, shell strings in subprocesses, missing authz, secret leaks, unsafe input at trust boundaries |
| `review-ux` | `ux` | user-facing flows, CLI output, error messages, exit codes, API status codes |
| `review-ui` | `ui` | pages vs spec and design docs, empty and error states, light and dark, accessibility basics |
| `review-code` | `code` | runs the test command; each AC has a real passing test; conventions; layout rules; nothing unrequested |
| `review-eval`, `review-tests` (other templates) | `code` | metrics gate / test quality |

1. `fctl show <id>` (spec, build notes, earlier verdicts) and `fctl diff <id>` (the patch).
2. Read the changed files and their surroundings in your cwd. Only `review-code` runs the test
   command; the others use Bash only for `fctl`, `git status`, and `git diff`.
3. Round n > 1: check your own findings on the round before are fixed.
4. Nothing in your area → `PASS` with one line, e.g. "no security surface in this task".
5. Write the verdict with the Write tool to `.fctl/verdict-<slot>.md`: most severe first, each as
   `file:line — problem — fix`. Nits go under `## Nits (non-blocking)` and never make CHANGES.
   `review-code` starts with the test command's summary line.
6. `fctl verdict <id> <slot> PASS|CHANGES < .fctl/verdict-<slot>.md` → expect
   `Round <n> of #<id>: <slot>=<verdict> (k/4)`.
7. Optional line comments, short heredocs:
   ```sh
   fctl comment <id> <slot> --path app/auth.py --line 44 <<'EOF'
   Key the limiter on the username too, or one IP can lock out everyone behind a NAT.
   EOF
   ```
   `--path` must be a file in the round's diff; `--line` is the line in the new file.

Rules:
- CHANGES only for real defects against the spec or your checks.
- Posting again replaces your verdict on the same round, so a mistaken one can be corrected; but
  post once when you can. Never post in another reviewer's slot.
- Don't edit code. Write nothing but `.fctl/verdict-<slot>.md`.

---

## Approver

Input: "Task <id>, rounds used <x> of <N>."

1. `fctl show <id>`: spec, every round's notes, verdicts, comments, decisions, and the user's
   feedback if any. `fctl diff <id>`: the latest patch. Read the docs the spec relies on.
2. ESCALATE if any holds:
   - a verdict on the latest round is still CHANGES (the round cap was hit);
   - tests fail or didn't run;
   - an acceptance criterion has no passing test;
   - the work conflicts with the repo's docs (cite both sides);
   - an open question's answer changed behavior (the user decides those).

   Otherwise APPROVE.
3. Write the decision with the Write tool to `.fctl/decision.md`:
   ```markdown
   <2–5 lines: what was built, rounds used, tests. For ESCALATE: what the user has to decide.>

   ## Open questions
   - Each one and the default the builder used.
   ```
4. `fctl decide <id> APPROVE|ESCALATE < .fctl/decision.md` → expect `Decision #<k> on #<id>: …`.

`fctl decide` doesn't move the task; the orchestrator does. Post once. Bash only for `fctl`,
`git status`, `git diff`. Write nothing but `.fctl/decision.md`.

---

## Interactive session (working for the user)

You are a Claude Code session the user talks to, in or near a connected repo. You aren't bound by
a run's allowlist, but you act only on what the user asks. The user's review decisions (approve,
request changes) and starting runs (which spend their Claude usage) are theirs: run those
commands when asked, not on your own initiative.

### Is this repo connected?

```sh
fctl context            # prints the pinned context, or nothing; 404 no project at … → not connected
```

`can't reach … — is "fctl serve" running?` → ask the user to start the app. Don't start it
yourself.

### Connect a repo — `/factory-connect <workspace>`

1. No workspace given → ask, and run nothing until answered.
2. Find the one command that runs the whole suite (CI config, `pyproject.toml`, `package.json`,
   Makefile, README). Show it to the user with the file it came from.
3. `fctl connect --workspace "<workspace>" --test-cmd "<test command>"`
4. Show the `Connected <name> (<workspace>) → <url>` line.

### Add a task

From inside the repo:

```sh
fctl task add "Rate-limit login endpoint" --description - <<'EOF'
## Goal
Max 5 failed logins per minute per IP; the 6th gets 429.

## Scope
- app/auth.py login handler; docs/api.md § Auth
- tests: one per behavior

## Out of scope
Per-user lockout.
EOF
```

- Write the description like a good request: goal, doc § references, scope, out of scope, tests.
  The spec-writer turns it into a spec.
- Add `--blocked-by 12,14` when it depends on other tasks of the project.
- Add `--run` only if the user asked to start it.
- In a repo that uses the app, `fctl task add` is the only way to add work. Don't add lines to
  `factory/backlog.md` (and never both): a fctl task has no import key, so the backlog sync would
  make a second copy.

### Start, follow, and recover runs

```sh
fctl run 12                     # Auto account
fctl run 12 --account b@y       # a specific account, even near its limits
fctl run next                   # top ready Backlog task of this repo
fctl show 12                    # where it is
fctl round 12                   # verdicts on the latest round
fctl diff 12                    # the latest patch
```

- A refused run names its fix: blocked → finish or `fctl task unblock`; cap full → wait or stop
  one; account limits → wait or `--account`; worktree or `wt` problems → as the message says.
- **Before re-running a stalled task, check nothing still drives it**: another run of the same
  task, or another terminal's session. Two orchestrators on one task overwrite each other.
  `fctl run` refuses `run #41 is already running on #12`, but a session outside the app isn't
  visible to it.
- `fctl run <id>` on an in-progress task continues from its stage; it doesn't start over.

### Submit your own changes — `/factory-submit [id]`

For work done in this session in the user's tree, not in a factory worktree.

1. Read `git status`, `git diff HEAD`, and every untracked file `git status` lists.
2. New review:
   ```sh
   fctl submit --new --title "Fix open redirect after login" <<'EOF'
   `next` was passed to redirect() unvalidated. Added is_safe_url(); tests: pytest -q (48 passed).
   EOF
   ```
   Show the `Review #N: …` line.
3. Next round of task N (given, or `Review #N` printed earlier this session for the same change):
   `fctl submit N <<'EOF' … EOF`, then show `Round <n> of #N: …`.
4. Never stage, commit, or stash. `HEAD has no commit yet` → tell the user; don't make the commit.
   `404 no project at …` → suggest `/factory-connect`.

### The user's review

Only on the user's explicit word:

```sh
fctl approve 12                                # → done; prints git commands for the user
fctl rework 12 "Make the limit configurable"   # → in_progress · rework; factory task: rework run starts
```

The commit, push, and `wt remove` lines `fctl approve` prints are the user's to run. Show them;
run them only if asked.

### Dependencies

```sh
fctl task block 15 --by 12      # #15 waits on #12
fctl task unblock 15 --by 12
```

### Project context

```sh
fctl context                       # print the current pinned context
fctl context set <<'EOF'           # replace it whole (≤ 16 KB; blank refused)
Python 3.12 with uv. Tests: uv run pytest -q. FastAPI, no ORM.
EOF
```

`fctl context set` replaces everything, so start from what `fctl context` printed.

Keep it to the stack and conventions every agent needs. Longer reference material belongs in
context cards on the project's Context page.

### Move tasks between apps

```sh
fctl export 12 -o rate-limit.zip                 # add --transcripts only if the user wants them
fctl import rate-limit.zip                       # in the target repo
```

`--transcripts` bundles can hold paths, env, and secrets. Say so before the user shares one.
