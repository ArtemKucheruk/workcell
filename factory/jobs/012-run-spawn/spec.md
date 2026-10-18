# 012-run-spawn: Run spawn (run, run-next, worktree, auth, one at a time)

## Goal
`POST /api/tasks/{id}/run` and `POST /api/projects/{id}/run-next` start one headless `claude -p` run. The run happens in the task's own worktree, `<repo>/.claude/worktrees/<id>-<slug>`, on branch `factory/<id>-<slug>`. The app refuses with 409 when another run is active, when the factory isn't committed on the default branch, or when `claude auth status` isn't claude.ai. It strips the API-key and provider variables from the run's environment. It spawns §4.4's command in its own process group and writes stdout to `runs/<run-id>.jsonl`. When the process exits, it records the exit code and reads the final `result` event. The task's status and stage stay as they are.

## Implements
- `docs/data-model-and-api.md §6.2`: `POST /api/tasks/{id}/run` → 202 `{"run_id","session_id","worktree"}`, with a 409 if any run is active, auth isn't claude.ai, or the factory isn't committed on `default_branch`. `POST /api/projects/{id}/run-next` → 202 `{"task_id","run_id"}`, or 404 if the backlog is empty.
- `docs/data-model-and-api.md §5.1`: writes `runs` rows (`session_id`, `pid`, `status`, `exit_code`, `error`, `log_path`, `started_at`, `ended_at`) and sets `tasks.branch` and `tasks.worktree_path`. The existing `one_active_run` index backs "one at a time". No schema change.
- `docs/data-model-and-api.md §5.2` and `docs/claude-code.md §7.5`: "— → in_progress, set by app (run spawned)", with an `events` row. A failed run leaves the status unchanged.
- `docs/MVP.md §2` (Run, Worktree) and `§10 assumption 4`: the worktree path and branch names, and `.claude/worktrees/` in `.git/info/exclude`.
- `docs/MVP.md §3.2 step 4` and `§10 assumption 3`: no run until `.claude/skills/factory/SKILL.md` is committed on `default_branch`.
- `docs/MVP.md §3.4 steps 1 and 8`: create the worktree from the default branch, spawn, backlog → in_progress. On exit, record the exit code, and leave status and stage unchanged.
- `docs/MVP.md §4.1`: stdout (stream-json) goes to `runs/<run-id>.jsonl`. On exit, the app reads the final `result` event for status and `session_id`.
- `docs/MVP.md §4.3`: remove `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and every `CLAUDE_CODE_USE_*` variable. Run `claude auth status` with the same environment and working directory as the run, and refuse with `409 not on subscription auth` unless `authMethod` is `claude.ai`. Never pass `--bare`.
- `docs/MVP.md §4.4`: the exact spawn command, with `FCTL_URL`, the allow and deny lists, and the test command from `projects.test_cmd`. The cwd is the worktree, stdin is `/dev/null`, stdout and stderr go to the log, and the process gets its own process group. One run at a time across all projects, refused with `409 run #N active`.
- `docs/MVP.md §10 open question 1`: the prompt string lives in one constant.
- `docs/MVP.md §4.5`: the two new mutating routes sit behind the existing middleware. Every subprocess takes an argument list, never a shell string.

## Acceptance criteria

Setup, unless a criterion says otherwise:
- The project is the `repo` fixture, connected with `default_branch` `main` and `test_cmd` `pytest -q`, with `.claude/skills/factory/SKILL.md` committed on `main`.
- The test replaces conftest's fake `claude`. For `auth status`, the fake prints `{"loggedIn":true,"authMethod":"claude.ai","subscriptionType":"pro"}` and exits 0.
- For `-p`, it records its argv, cwd (`pwd -P`), env, `$$`, and process group to files. It then prints one `{"type":"system",…}` line and one `{"type":"result","subtype":"success","is_error":false,"session_id":<its --session-id>,"result":"ok"}` line to stdout, writes `warn` to stderr, and exits 0.
- Tests wait, with a deadline, until the run row leaves `running`.

`POST /api/tasks/{id}/run`: a successful spawn
- [ ] AC1: a backlog task titled `Rate-limit login endpoint` → 202 with exactly `{"run_id":<the new runs.id>,"session_id":<sid>,"worktree":".claude/worktrees/<id>-rate-limit-login"}`. `sid` parses as a UUID.
- [ ] AC2: `git -C repo worktree list --porcelain` lists `<repo>/.claude/worktrees/<id>-rate-limit-login` on `refs/heads/factory/<id>-rate-limit-login`, and its HEAD equals `main`'s. The task row has `branch` `factory/<id>-rate-limit-login`, and `worktree_path` holds that absolute path (Q4).
- [ ] AC3: the titles `Fix: the  API!!` and `Добавить вход` → worktree names `<id>-fix-the-api` and `<id>-task`. Test this through the route (one run after another) or through the slug helper (Q3).
- [ ] AC4: `.git/info/exclude` keeps its earlier content and gains the line `.claude/worktrees/` exactly once, still once after a second run on another task. `git -C repo status --porcelain` is empty afterwards (Q5).
- [ ] AC5: the `-p` argv is exactly `-p`, `/factory <id>`, `--session-id`, `<sid>`, `--output-format`, `stream-json`, `--verbose`, `--forward-subagent-text`, `--permission-mode`, `acceptEdits`, `--permission-prompts`, `none`, `--allowedTools`, `Bash(fctl show *)`, `Bash(fctl diff *)`, `Bash(fctl spec *)`, `Bash(fctl submit *)`, `Bash(fctl verdict *)`, `Bash(fctl comment *)`, `Bash(fctl decide *)`, `Bash(fctl stage *)`, `Bash(fctl round *)`, `Bash(git status *)`, `Bash(git diff *)`, `Bash(pytest *)`, `--disallowedTools`, `Bash(git commit *)`, `Bash(git push *)`, `Bash(git merge *)`, `Bash(git rebase *)`, `Bash(git reset *)`, `Bash(git checkout *)` (§4.4).
- [ ] AC6: `test_cmd` `uv run pytest -q` → the last `--allowedTools` entry is `Bash(uv run pytest *)`. `test_cmd` NULL → the allowed list has only the 11 `fctl`/`git` entries (Q7).
- [ ] AC7: the `-p` process and the `auth status` process both ran with cwd equal to the worktree's real path (§4.3, §4.4).
- [ ] AC8: the server's env has `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOO`, and `FOO=bar` set (monkeypatch). Neither the `auth status` env nor the `-p` env holds any of the first five. Both hold `FOO=bar` and `FCTL_URL=http://127.0.0.1:4545` (Q8).
- [ ] AC9: the `-p` process's process group id equals its own pid and differs from `os.getpgrp()` in the test. `runs.pid` equals that pid.
- [ ] AC10: `runs.log_path` is `<FCTL_HOME>/runs/<run_id>.jsonl`, and that file holds both stdout lines and the stderr `warn`. The runs row has the task's `task_id`, `session_id` = `sid`, and a `started_at` timestamp.
- [ ] AC11: a backlog task at position 3.0 → afterwards it is in_progress with stage NULL, position 3.0, and `updated_at` bumped, with exactly one new `events` row: actor `app`, `backlog` → `in_progress`, stage NULL (Q9).
- [ ] AC12: an in_progress · build task that already has `branch` and `worktree_path` from an earlier run, with the worktree on disk → 202 with the same `worktree`. The worktree list is unchanged, the `-p` cwd is the stored worktree, status and stage are unchanged, and no `events` row is added (Q4, Q9).

On exit
- [ ] AC13: the fake's result event has `"is_error":false` and `"session_id":"S2"`, and it exits 0 → the run is `succeeded`, with `exit_code` 0, `error` NULL, `ended_at` set, and `session_id` `S2` (Q10).
- [ ] AC14: the result event is `{"type":"result","is_error":true,"result":"Claude AI usage limit reached",…}` and the fake exits 1 → `failed`, `exit_code` 1, `error` `Claude AI usage limit reached`.
- [ ] AC15: no output and exit 3 → `failed`, `exit_code` 3, `error` `exit code 3`. Exit 0 with no result event → `failed`, `error` `no result event` (Q10).
- [ ] AC16: after each exit in AC13–AC15, the task's status and stage are what they were just after the spawn, and no `events` row was added (§3.4 step 8, §7.5).

Refusals: none of these writes a runs row
- [ ] AC17: a `running` runs row with id N, on a task in another project, inserted by SQL → 409 `{"detail":"run #N active"}`. No worktree is created, and the fake is not invoked at all, not even `auth status`.
- [ ] AC18: a task in review · human_review → 409 `{"detail":"#<id> is in review"}`. A done task → 409 `{"detail":"#<id> is done"}`. No worktree, and the fake is not invoked (Q1).
- [ ] AC19: `SKILL.md` only on disk (uncommitted), or absent → 409 `{"detail":"factory isn't committed on main"}`. No worktree, and the fake is not invoked (Q12).
- [ ] AC20: `auth status` prints `{"authMethod":"console"}`, or prints `not json`, or prints the claude.ai JSON but exits 1 → each one gives 409 `{"detail":"not on subscription auth"}`. The `-p` command never ran and the task stays in backlog. The worktree exists and the task has `branch` and `worktree_path` set (Q2, Q6). After restoring the fake, the next `/run` → 202 and reuses that worktree.
- [ ] AC21: `<repo>/.claude/worktrees/<id>-<slug>` already exists as a non-empty directory that git doesn't know about → 409 with a detail starting `git worktree add failed: `. The task stays in backlog with `branch` and `worktree_path` NULL, and the fake is not invoked (Q4).
- [ ] AC22: the stored `worktree_path` was removed from disk → 409 `{"detail":"worktree <worktree_path> is missing"}`, and the fake is not invoked (Q4).
- [ ] AC23: the fake deletes itself while answering `auth status`, so the spawn fails → 500 with a detail starting `can't start claude: `. The runs row is `failed`, with that text as `error` and `ended_at` set. The task stays in_progress. After restoring the fake, `/run` on another backlog task → 202, not `run #N active` (Q11).
- [ ] AC24: an unknown task → 404. A POST without `X-Requested-By: fctl` → 403. Neither invokes the fake.

`POST /api/projects/{id}/run-next`
- [ ] AC25: backlog tasks B (1.0), then C (1.0, created after B), then A (2.0), plus an in_progress task at 0.5 → 202 with exactly `{"task_id":<B>,"run_id":<the new runs.id>}`. B is now in_progress, and the `-p` prompt is `/factory <B>` (Q13).
- [ ] AC26: a project with no backlog task → 404 `{"detail":"backlog is empty"}`. An unknown project → 404. No runs row is written.
- [ ] AC27: a `running` runs row with id N → run-next → 409 `{"detail":"run #N active"}`, and B stays in backlog.

## Files
- `src/claude_factories/app.py`:
  - `PROMPT = "/factory {task_id}"`, the one place the prompt lives (§10 OQ1).
  - The allow and deny tuples from §4.4, plus the test-command entry (Q7).
  - A slug helper (Q3).
  - A worktree helper: exclude line, create or reuse, store `branch`/`worktree_path` (Q4, Q5).
  - The run env: a copy of `os.environ` without the §4.3 variables, plus `FCTL_URL`.
  - The `claude auth status` check.
  - The spawn: `subprocess.Popen` with an argument list, `cwd` the worktree, `stdin=DEVNULL`, stdout to the log file with `stderr=STDOUT`, and `start_new_session=True`.
  - A daemon `threading.Thread` per run that waits for the process, reads the log's last `result` event, and updates the runs row (Q10).
  - The two routes. Run-next picks its task and calls the same function as `/run`.
  - Reuse `factory_state()`, `query()`, `one_or_404()`, and `db.data_dir()`. Insert the runs row inside `BEGIN IMMEDIATE`: re-check for a running run, insert the row, move the task, and write the event. A `sqlite3.IntegrityError` from `one_active_run` also gives `409 run #N active`.
- `tests/test_runs.py`: new. The fake `claude` is written per test over `tmp_path/bin/claude`. Its record directory comes from an env var the test sets.
- `tests/conftest.py`: change it only if a helper gets shared.

No schema change, no new dependency (`uuid`, `threading`, `json`, and `re` are stdlib), and no CLI change.

## Out of scope
- `POST /api/runs/{id}/stop`, stopping every run when `fctl serve` stops, startup cleanup to `failed: app restarted`, `GET /api/runs/{id}/log`, Retry as a feature, and Request changes spawning a rework run (013). This job only defines what `/run` does to an in_progress task (Q9).
- Run / Run next / Stop / Retry buttons, enabling the board's Run next, "stalled" cards, run status and the takeover command on the task page, and the `Claude: Pro ✓` header (014).
- `fctl run <id>`, `fctl run next`, and `fctl task add --run` (015). Create factory (011).
- Approve / Request changes (009).
- Removing worktrees or branches, a run queue, parallel runs, `--max-budget-usd`, detecting the usage-limit reset time, and editing a project's `.claude/settings.json` (MVP §9 Later).
- Checking the flags against the real `claude --help`. Tests never call the real `claude` (Q14).

## Open questions
- Q1: docs don't say which statuses `/run` accepts. Default: backlog and in_progress run. Review gives 409 `#<id> is in review` (the orchestrator stops at human_review and escalated; rework goes through Request changes, 013), and done gives 409 `#<id> is done`.
- Q2: §4.3 runs `claude auth status` "with the same … working directory" as the run, which is the worktree, so the worktree has to exist before the auth check. Default check order:
  1. 404 unknown task
  2. 409 run active
  3. 409 status (Q1)
  4. 409 factory not committed
  5. worktree: reuse, or create and store `branch`/`worktree_path` right away (Q4)
  6. 409 auth
  7. one transaction: re-check for an active run, insert the run, move the task, write the event
  8. spawn

  On an auth refusal, the worktree and the stored columns stay, so the next Run reuses them.
- Q3: §3.4's only example is `Rate-limit login endpoint` → `12-rate-limit-login`. Default slug: lowercase the title, replace each run of characters outside `[a-z0-9]` with `-`, strip `-` from both ends, and keep the first 3 `-`-separated words. If nothing is left, use `task`.
- Q4: docs don't cover reuse, failures, or how paths are stored. Default:
  - The base is the local `default_branch`. The command is `git -C <project path> worktree add -b factory/<id>-<slug> <project path>/.claude/worktrees/<id>-<slug> <default_branch>`.
  - `worktree_path` is stored absolute. The response's `worktree` is relative to the project path, as in §6.2.
  - A task with a stored `worktree_path` reuses it, and the slug isn't recomputed even if the title changed. If that directory is gone → 409 `worktree <path> is missing`.
  - A failing `git worktree add` → 409 `git worktree add failed: <git's stderr, stripped>`, with nothing stored.
- Q5: docs say only "adds `.claude/worktrees/` to `.git/info/exclude`". Default:
  - Find the file with `git -C <path> rev-parse --path-format=absolute --git-path info/exclude`, and create `info/` if it's missing.
  - Append the line only when no line already equals `.claude/worktrees/`. Add a newline first if the file doesn't end with one.
  - Do this on every run, before `worktree add`.
- Q6: §4.3 shows `"authMethod": "claude.ai"` but not the output format. Default:
  - Run `["claude", "auth", "status"]` with a 30 s timeout and parse stdout as JSON.
  - Allowed only if the exit code is 0 and `authMethod == "claude.ai"`. A non-zero exit, non-JSON output, a timeout, or a missing binary all give the same 409 `not on subscription auth`.
  - `subscriptionType` isn't checked; the header shows it (014).
  - If the real CLI turns out to need a `--json` flag, adding it is a one-line change.
- Q7: §4.4 shows `"Bash(pytest *)"` for the test command `pytest -q` but doesn't give the rule. Default:
  - Split `test_cmd` on whitespace and keep the words before the first one that starts with `-`. If any are left, add `Bash(<words joined by spaces> *)` as the last `--allowedTools` entry. Otherwise, or if `test_cmd` is NULL, add no entry.
  - `uv run pytest -q` → `Bash(uv run pytest *)`.
  - Other commands a project needs go in its own `.claude/settings.json` (§4.4).
- Q8: §4.4 sets `FCTL_URL=http://127.0.0.1:4545`, but `fctl serve --port` can change the port. Default: `FCTL_URL` is the request's base URL without the trailing slash. The middleware already limits its host to 127.0.0.1 or localhost. Any `FCTL_URL` already in the server's env is replaced. Only the §4.3 variables are removed; everything else is inherited, as with `env -u`.
- Q9: §5.2 says a spawned run moves the task to in_progress, but not what happens to the other fields. Default:
  - A backlog task → in_progress with stage NULL. `position` is kept (as in 005 Q2) and `updated_at` is bumped. One `events` row: actor `app`, `from_status` backlog, `to_status` in_progress, stage NULL, `note` NULL.
  - An in_progress task keeps its status and stage, and gets no event: the orchestrator picks up from the current stage (§3.4).
- Q10: §4.1 says the app reads the `result` event "for status, and `session_id`" but doesn't give the rules. Default:
  - Take the last log line that parses as a JSON object with `"type":"result"`. Lines that aren't JSON, such as stderr, are skipped.
  - `succeeded` when the exit code is 0 and that event has `is_error` false. Otherwise `failed`, with `error` set to:
    - the event's `result` string, if `is_error` is true;
    - otherwise `exit code N` when N ≠ 0;
    - otherwise `no result event`.
  - The event's `session_id`, when present, replaces `runs.session_id`, since that is what `claude --resume` needs.
  - `exit_code` and `ended_at` are always set.
  - The task row is never touched.
- Q11: docs don't say what happens if the spawn itself fails. Left alone, a `running` row with no process would block every run. Default: if `Popen` raises `OSError`, the run row becomes `failed` with `error` `can't start claude: <error>` and `ended_at`, and the route answers 500 with that detail. The task keeps the in_progress it was already given, and 014 shows it as stalled.
- Q12: §6.2 gives no text for the factory 409. Default: `factory isn't committed on <default_branch>`, where ready means `factory_state() == "ready"`. The commit hint is the UI's job (011/014).
- Q13: §3.3 says "Run next always takes the top card". Default: the project's backlog task with the lowest `position`, ties broken by the lowest `id`. With none → 404 `backlog is empty`. All of `/run`'s checks and responses apply to the task it picks.
- Q14: §10 OQ1 says the `/factory <id>` prompt and the flags (`--forward-subagent-text`, `--permission-prompts none`) must be checked against the installed `claude`. Default: use §4.4's command verbatim, with the prompt in `PROMPT`. Checking it is a manual step before the first real run, outside `uv run pytest -q`.
