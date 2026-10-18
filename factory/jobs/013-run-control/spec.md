# 013-run-control: Run control: stop, log, startup cleanup, Retry, rework runs

## Goal
This job lets the app control the runs that 012 spawns. `POST /api/runs/{id}/stop` sends SIGTERM to a run's process group. Stopping `fctl serve` stops every active run, and at startup any run still marked `running` becomes `failed` with error `app restarted`. `GET /api/runs/{id}/log?after=` turns a run's stream-json log into display lines. Retry needs no new route: it is the existing `POST /api/tasks/{id}/run` on a stalled in_progress task. Request changes on a factory task now spawns the rework run.

## Implements
- `docs/MVP.md §4.4`: Stop sends SIGTERM to the run's process group. Stopping `fctl serve` stops every run. At startup, a run still marked `running` becomes `failed: app restarted`. "Denials show up in the run log."
- `docs/data-model-and-api.md §6.2`:
  - `POST /api/runs/{id}/stop` → 200 `{"id","status":"stopped"}`.
  - `GET /api/runs/{id}/log?after=` → 200 `{"next","lines":[{"t","text"}]}`.
  - `POST /api/tasks/{id}/run` doubles as Retry. Its code is unchanged.
- `docs/data-model-and-api.md §6.3`: `POST /api/tasks/{id}/request-changes` returns the rework run's `run_id`, or null for a standalone task.
- `docs/data-model-and-api.md §5.1`: the `runs` columns `status` (`stopped`, `failed`), `error`, `exit_code`, and `ended_at`. No schema change.
- `docs/MVP.md §3.4` (last paragraph): Retry spawns `/factory <id>` again, and the orchestrator picks up from the task's current stage.
- `docs/MVP.md §3.6 step 2`, `docs/claude-code.md §7.4` (last paragraph) and `§7.5`:
  - Request changes spawns `/factory <id>` in the same worktree.
  - A standalone task gets no run.
  - A run that fails or is stopped leaves the task unchanged ("stalled").
- `docs/MVP.md §10 assumptions 6 and 8`: rework starts a fresh session, and stopping the app stops all runs.
- `docs/MVP.md §4.5`: the stop route sits behind the existing middleware. Signals only ever go to a pid the app stored for a run it spawned.

## Acceptance criteria
Setup is 012's (`tests/test_runs.py`), unless a criterion says otherwise:
- The project is the `repo` fixture, with SKILL.md committed on `main` and `test_cmd` `pytest -q`.
- The fake `claude` answers `auth status` with the claude.ai JSON.
- The **long-running fake** handles `-p` like this:
  - It records its pid as 012's fake does and prints one `{"type":"system",…}` line.
  - It starts a background child (`sleep 60`) that stays in its process group, and records that child's pid.
  - It then sleeps 60 s.
- "Gone" means `os.kill(pid, 0)` raises `ProcessLookupError` within a 5 s deadline.

Stop
- [ ] AC1: a run of the long-running fake, on a task set to in_progress · build → `POST /api/runs/{id}/stop` → 200 with exactly `{"id": <id>, "status": "stopped"}`. When the response arrives, the row is already `stopped`, with `ended_at` set and `error` NULL.
- [ ] AC2: after AC1's stop, the fake's pid and its background child's pid are both gone. SIGTERM reached the whole group.
- [ ] AC3: once the fake has exited, the row is still `stopped`. `error` is NULL, `ended_at` is the value the stop set, and `exit_code` is not NULL (Q1).
- [ ] AC4: AC1's stop leaves the task's `status`, `stage`, and `updated_at` unchanged, and adds no `events` row (Q3).
- [ ] AC5: stop on a run that is `succeeded`, `failed`, or `stopped` → 409 `{"detail":"run #<id> is not running"}`, and the row is unchanged. An unknown run id → 404.
- [ ] AC6: stop without `X-Requested-By: fctl` → 403. The row is still `running`, and the fake is not gone.
- [ ] AC7: a `running` row inserted by SQL with `pid` NULL → stop → 200 `stopped`. Then a `running` row whose `pid` belongs to a process that has already exited and been reaped → stop → 200 `stopped` (Q2).

Stopping `fctl serve`
- [ ] AC8: a run of the long-running fake is started inside its own `with TestClient(app, base_url="http://127.0.0.1:4545"):` block. Leaving the block, which runs the lifespan shutdown, leaves the row `stopped` with `ended_at` set, and the fake and its child are gone (Q4).

Startup
- [ ] AC9: the DB is initialized, then these rows are inserted by SQL:
  - run A, `running`, with `pid` set to a live `sleep 60` that the test started with `start_new_session=True`;
  - run B, `succeeded`.

  Entering a TestClient (lifespan startup) makes A `failed`, with `error` `app restarted`, `ended_at` set, and `exit_code` NULL. B is unchanged. The `sleep` is still alive, because startup sends no signal. No task row or `events` row changed (Q5).

Retry
- [ ] AC10: after AC1's stop, `POST /api/tasks/{id}/run` → 202 with the same `worktree` as before.
  - There is a new runs row, and its `session_id` differs from the stopped run's.
  - The `-p` prompt is `/factory <id>`, and its cwd is the stored worktree.
  - The task is still in_progress · build, and no `events` row was added (Q10).
- [ ] AC11: a task in_progress · approval with a stored worktree on disk, plus a leftover `running` row cleaned up as in AC9 → `POST /api/tasks/{id}/run` → 202, not `run #N active`. The stage stays `approval`.

Run log. "The fixture log" is this file, each line ending in `\n`, as a run's `log_path`:
```
{"type":"system","subtype":"init","session_id":"S"}
{"type":"assistant","message":{"content":[{"type":"text","text":"Reading #12"}]},"parent_tool_use_id":null}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tu1","name":"Agent","input":{"subagent_type":"builder","name":"builder-12","description":"Build round 1","prompt":"go"}}]},"parent_tool_use_id":null}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tu2","name":"Bash","input":{"command":"pytest -q\necho done"}}]},"parent_tool_use_id":"tu1"}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"tu2","is_error":false,"content":"3 passed"}]},"parent_tool_use_id":"tu1"}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"tu3","is_error":true,"content":[{"type":"text","text":"Permission to use Bash with command git commit -m x has been denied.\nmore"}]}]},"parent_tool_use_id":"tu1"}
warn
{"type":"result","subtype":"success","is_error":false,"result":"#12 is in review","session_id":"S"}
```
- [ ] AC12: `GET /api/runs/{id}/log` on the fixture log → 200 with exactly this body (Q6, Q7, Q8):
  ```json
  {"next": 8, "lines": [
    {"t": "text", "text": "orchestrator · Reading #12"},
    {"t": "tool", "text": "orchestrator · Agent builder-12"},
    {"t": "tool", "text": "builder-12 · Bash pytest -q"},
    {"t": "error", "text": "builder-12 · Permission to use Bash with command git commit -m x has been denied."},
    {"t": "raw", "text": "warn"},
    {"t": "result", "text": "#12 is in review"}]}
  ```
- [ ] AC13: `?after=3` on the fixture log → `next` 8, and `lines` are AC12's last 4 items. `builder-12` still resolves, even though its spawn is on a line before `after`.
- [ ] AC14: an `Agent` tool_use with id `tu9` whose input has `subagent_type` `review-code` and no `name` → its line is `orchestrator · Agent review-code`. A later `Bash` tool_use `fctl verdict 12 code PASS` with `parent_tool_use_id` `tu9` → `review-code · Bash fctl verdict 12 code PASS` (Q8).
- [ ] AC15: a log of the fixture's first 2 lines, then `{"type":"assistant"` with no trailing newline → `next` 2, and `lines` has only the `Reading #12` item. Appending the rest of a valid line plus `\n`, then `?after=2` → `next` 3 with that line's item (Q6).
- [ ] AC16: a log of `{"type":"assistant","message":null}`, `{"type":"assistant","message":{"content":"plain"}}`, `{"type":"user","message":{"content":[null,3]}}`, an empty line, and `[1,2]` → 200 with exactly `{"next": 5, "lines": [{"t": "raw", "text": "[1,2]"}]}` (Q7).
- [ ] AC17: a run whose `log_path` file doesn't exist → 200 `{"next": 0, "lines": []}`. An unknown run → 404. `?after=-1` → 422. The GET succeeds without `X-Requested-By` (Q9).

Request changes spawns the rework run
In these criteria, a "factory task" has `branch` and `worktree_path` set, with the worktree on disk from an earlier `/run` (Q11). It is in review · human_review and has at least one round.
- [ ] AC18: `POST /api/tasks/{id}/request-changes` with a summary on a factory task → 202 with exactly `{"status": "in_progress", "stage": "rework", "run_id": <the new runs.id>}`.
  - The new run's `-p` prompt is `/factory <id>`, its cwd is the stored worktree, and its `session_id` differs from the earlier run's (Q13).
  - After the run exits, the task is still in_progress · rework.
  - The call added exactly one `CHANGES_REQUESTED` decision and one `events` row: actor `me`, `review` → `in_progress`, stage `rework`.
- [ ] AC19: a standalone task (`branch` and `worktree_path` NULL), while another task has a `running` row → 202 `{"status": "in_progress", "stage": "rework", "run_id": null}`. No runs row is added, and the fake is not invoked.
- [ ] AC20: a factory task while a `running` row N exists → 409 `{"detail": "run #N active"}`. The decisions and events counts and the task row are unchanged, and the fake is not invoked (Q12).
- [ ] AC21: a factory task with the fake's `auth status` answering `{"authMethod":"console"}` → 409 `{"detail": "not on subscription auth"}`.
  - The `CHANGES_REQUESTED` decision and the in_progress · rework move are recorded anyway, and no runs row is added (Q12).
  - After the fake is restored, `POST /api/tasks/{id}/run` (Retry) → 202, and the task stays in_progress · rework.
- [ ] AC22: the form `POST /tasks/{id}/request-changes` with `body_md=Make+it+configurable` on a factory task → 204 with `HX-Redirect: /tasks/{id}/review`, and the task has a new runs row.
- [ ] AC23: in `tests/test_review_actions.py`, update 009's tests that request changes on the `factory_task` fixture and expect `run_id` null, a 202, or a 204: AC10, the last two asserts of AC12, and AC21. That fixture's project (`/code/api`) isn't a repo, so its spawn now answers 409 `factory isn't committed on main`. Either assert that, or use a standalone task where the test is only about the decision rows. `uv run pytest -q` passes as a whole.

## Files
- `src/claude_factories/app.py`:
  - `lifespan`, after `db.init()`: one `UPDATE runs SET status = 'failed', error = 'app restarted', ended_at = now WHERE status = 'running'`. After `yield`: stop every `running` run.
  - A stop helper, shared by the route and the shutdown:
    - In one transaction, change `running` to `stopped` and set `ended_at`. Zero rows changed → 409.
    - Then call `os.killpg(pid, signal.SIGTERM)` if `pid` is set, ignoring `ProcessLookupError`.
  - `finish_run`: if the row is no longer `running`, fill in only `exit_code`.
  - `POST /api/runs/{run_id}/stop`.
  - `GET /api/runs/{run_id}/log` with `after: int = Query(0, ge=0)`, plus one small function that turns stream-json lines into items (Q6–Q8). Reading the log reuses nothing from `finish_run` unless that makes the code shorter.
  - `request_changes` takes `request`:
    - For a factory task, call `refuse_if_running` before anything is written.
    - Then call `decide_review`, then `run_task(task_id, request)`, and return its `run_id`.
    - `request_changes_form` passes the request through. It is an `async def`, so it must not run the blocking spawn on the event loop: use `starlette.concurrency.run_in_threadpool`, which ships with FastAPI.
- `tests/test_run_control.py` (new): AC1–AC22. Import 012's helpers and fixtures from `test_runs`, the way `test_review_actions.py` imports from `test_review`. Add the long-running fake there, or as an option on `test_runs.py`'s `fake`.
- `tests/test_review_actions.py`: AC23.

No schema, CLI, or template change. No new dependency: `signal` is stdlib.

## Out of scope
- The Run, Run next, Stop, and Retry buttons, "stalled · <stage>" cards, the task page's run status, the polling run-log panel, the takeover command, and the `Claude: Pro ✓` header. All of these are 014's.
- `fctl run <id>`, `fctl run next`, and `fctl task add --run` (015). There is no `fctl stop` (§7.2 has none). `fctl rework` output stays as 009 left it.
- Escalating to SIGKILL, killing orphaned runs left by a crashed server, a run queue, and detecting the usage-limit reset time (MVP §9 Later).
- A tail or limit parameter on the log endpoint. 014 can add one if its panel needs it.
- Queuing a rework while another run is active. It is refused instead (Q12).
- Any change to `/run`'s checks, the spawn command, or the env (012).

## Open questions
- Q1: docs only say Stop gives `stopped`. Default:
  - Stop marks the row `stopped` with `ended_at` = now and `error` NULL before it signals, so the exit thread can't record `failed` first.
  - When the process exits, `finish_run` fills in only `exit_code` on a row that is no longer `running`.
- Q2: docs don't cover the edge cases. Default:
  - A run that isn't `running` → 409 `run #N is not running`. An unknown id → 404.
  - `pid` NULL means no signal; the row is still marked `stopped`. A process group that is already gone (`ProcessLookupError`) is ignored.
  - There is SIGTERM only, no SIGKILL escalation, as §4.4 says.
  - Known gap: there are milliseconds between the runs insert and `pid` being stored. A Stop inside that gap marks the row without signalling. That is accepted, with a `ponytail:` comment.
- Q3: docs don't say what Stop does to the task. Default: nothing. Status, stage, and `updated_at` are unchanged and no event is written, as for a failed run (§7.5). 014 shows the task as stalled with Retry.
- Q4: §4.4 says stopping `fctl serve` stops every run, but not what the row says. Default: the lifespan shutdown does exactly what Stop does to each `running` run (`stopped`, SIGTERM to its group), without waiting for the exits. `failed: app restarted` is for runs a crash left behind.
- Q5: `failed: app restarted` read as status `failed` with `error` `app restarted`. Default:
  - Set `ended_at` = now, leave `exit_code` NULL, and leave the task alone.
  - No signal goes to the stored pid. After a restart it may belong to an unrelated process.
- Q6: §6.2 shows `after=120` → `next: 134` but doesn't define the cursor. Default:
  - `after` and `next` count complete log lines (lines ending in `\n`). `lines` covers file lines `after…next-1`, and `next` is the file's complete-line count.
  - A trailing partial line is held back until its newline arrives.
  - The whole file is read on each poll, opened with `errors="replace"`. `ponytail:` byte offsets if logs get big.
- Q7: §6.2 shows only `t` values `tool` and `text`. Default mapping, per log line:
  - A line that isn't a JSON object → `raw`, the line without its line ending. Blank lines → nothing.
  - `assistant` content blocks:
    - `text` → `text`, as `<who> · <text stripped>`. Empty text → nothing.
    - `tool_use` → `tool`, as `<who> · <name>`, followed by ` <summary>` when there is one. The summary is the first line of the first string among the input keys `command`, `file_path`, `pattern`, `name`, `subagent_type`, `description`.
    - Other blocks, such as thinking → nothing.
  - `user` content blocks: a `tool_result` with `is_error: true` → `error`, as `<who> · <first line of its content>`. The content is a string, or the `text` of its list items joined by `\n`. This is how permission denials show up (§4.4). A tool result without an error → nothing.
  - `result` → `result`, with its `result` string, or else its `subtype`.
  - Any other event type, and any object of an unexpected shape → nothing, never a 500.
- Q8: §6.2's example says `builder-12 · Bash pytest -q` without saying where the name comes from. Default:
  - Every `tool_use` in the file whose input has a string `name` or `subagent_type` records `id → name` (or `subagent_type`).
  - `<who>` is the name recorded for the event's `parent_tool_use_id`. A null or missing parent gives `orchestrator`, and a parent id with no recorded name gives `agent`.
- Q9: a missing log file → 200 `{"next": 0, "lines": []}`, so a poll never errors. A negative `after` → 422.
- Q10: Retry has no route of its own. §6.2 lists `POST /api/tasks/{id}/run` for "Run, Retry". 012 already re-runs an in_progress task in its stored worktree, keeping status and stage, with a new `session_id`. This job only adds the tests that a stopped or restarted run frees the slot.
- Q11: a factory task is one with both `branch` and `worktree_path` set, as in 009. Anything else is standalone and gets `run_id` null (§7.4).
- Q12: docs don't say what Request changes does when the spawn is refused. Default:
  - For a factory task, an active run → 409 `run #N active` before anything is written. This is the common case: one run at a time.
  - Otherwise the decision and the in_progress · rework move are committed first, then `run_task` runs.
  - If `run_task` refuses or fails (auth, factory, missing worktree, spawn error), its status code and detail are returned. The decision and the rework stage stay. The task waits as stalled · rework, and Retry (`POST /run`) recovers it.
- Q13: the rework run is the same `/factory <id>` command with a new `--session-id`. MVP §10 assumption 6 says rework starts a fresh session; `--resume` is on the Later list.
