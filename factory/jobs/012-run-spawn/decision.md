APPROVE
Built: `POST /api/tasks/{id}/run` and `POST /api/projects/{id}/run-next` in src/claude_factories/app.py. The checks run in Q2's order (404, run active, status, factory committed, worktree create/reuse plus the `.git/info/exclude` line, `claude auth status` == claude.ai). Then one `BEGIN IMMEDIATE` transaction inserts the runs row, moves backlog → in_progress, and writes the `app` event. The §4.4 command is then spawned with an argument list, a stripped env plus `FCTL_URL`, cwd = worktree, its own process group, and stdout+stderr going to `runs/<id>.jsonl`. A daemon thread records exit_code, status, error, and session_id from the last `result` event. It never touches the task.
Rounds: 1 of 2. All four reviews PASS in round 1 (review-ui skipped: no templates/static touched). No feedback files.
Tests: 347 passed (build.md and review-code.md). The new tests/test_runs.py maps AC1–AC27 one-to-one, with a per-test fake `claude` that never calls the real CLI.
Docs check: no conflict with data-model-and-api §5.1/§5.2/§6.2, claude-code §7.5, or MVP §2, §3.2, §3.4, §4.1, §4.3, §4.4, §4.5, §10. No schema change, no new dependency.

## Open questions
Spec questions. The builder used every default as written:
- Q1 (which statuses `/run` accepts): backlog and in_progress run. Review → 409 `#<id> is in review`. Done → 409 `#<id> is done`.
- Q2 (check order): 404 → run active → status → factory → worktree (created and stored right away) → auth → transaction → spawn. If auth refuses, the worktree and the stored branch/worktree_path stay for the next run to reuse.
- Q3 (slug): lowercase, each run of non-`[a-z0-9]` characters becomes `-`, trim the ends, keep the first 3 words. If nothing is left, use `task`.
- Q4 (worktree): `git worktree add -b factory/<id>-<slug> <path>/.claude/worktrees/<id>-<slug> <default_branch>`. `worktree_path` is stored absolute and the response gives it relative. A stored path is reused (no recomputed slug). Missing dir → 409 `worktree <path> is missing`. A failing add → 409 `git worktree add failed: <stderr>`, with nothing stored.
- Q5 (exclude): the file is found with `rev-parse --git-path info/exclude`. The line is appended once, with a newline added first if the file lacks one, and this is checked on every run.
- Q6 (auth): `claude auth status`, 30 s timeout, JSON stdout. It passes only on exit 0 with `authMethod == "claude.ai"`. Anything else, including a missing binary, gives 409 `not on subscription auth`. `subscriptionType` isn't checked.
- Q7 (test-command allow entry): the words of `test_cmd` before the first `-`-word become `Bash(<words> *)`. NULL or empty → no entry.
- Q8 (FCTL_URL): taken from the request's base URL, which is `http://127.0.0.1:4545` by default. Only the §4.3 variables are removed. Everything else is inherited.
- Q9 (task fields on spawn): backlog → in_progress, stage NULL, position kept, updated_at bumped, one `app` event. An in_progress task is left unchanged, with no event.
- Q10 (reading the result): the last JSON line with `type: result` decides. Success needs exit 0 and `is_error` false. Otherwise error = the event's `result`, else `exit code N`, else `no result event`. The event's `session_id` replaces `runs.session_id`.
- Q11 (spawn failure): if `Popen` raises OSError, the run row becomes `failed` with `can't start claude: …`, the route returns 500, and the task stays in_progress.
- Q12 (factory 409 text): `factory isn't committed on <default_branch>`, gated on `factory_state() == "ready"`.
- Q13 (run-next): the backlog task with the lowest position, ties broken by lowest id. No such task → 404 `backlog is empty`.
- Q14 (CLI flags): §4.4 is used verbatim and the prompt lives in `PROMPT`. Checking it against the real `claude --help` / `/factory <id>` in print mode is still a manual step before the first real run.

Raised during build or review. None of these changed behavior; all were left as is:
- After an AC21 failure, git 2.49 has already created the branch `factory/<id>-<slug>`. The next `/run` fails with `a branch named … already exists` until you run `git branch -D` by hand. Default: no handling, because branch removal is MVP §9 Later.
- If the waiting thread dies (log deleted, DB locked for more than 5 s), the row stays `running` and blocks every run until 013's startup cleanup. Default: not guarded.
- `test_cmd` isn't validated. A value like `git add` or `fctl approve` would land on the allowlist, against §4.4's "no git write / can't approve". Default: trusted, since it's user-set at connect. A guard could go in connect later.
- The `FCTL_URL` port follows the Host header; only a local caller could choose it. The test fake writes the full env to pytest's tmp dir. Both are non-blocking nits.
