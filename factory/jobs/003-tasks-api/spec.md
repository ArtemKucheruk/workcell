# 003-tasks-api: Tasks API (CRUD, stage and status, events, task add)

## Goal
Add tasks to projects and move them through the kanban statuses through the JSON API. A new
task lands at the bottom of its project's Backlog. `PATCH /api/tasks/{id}` sets the spec, sets
a stage (the server derives the status from it), or makes a manual move (status + position,
stage cleared, refused with 409 while the task's run is active). Every status or stage change
writes an `events` row. `fctl task add "title"` creates a task in the project of the current repo.

## Implements
- `docs/MVP.md §3.3`: a new task lands at the bottom of Backlog as `#<id>`. The CLI alternative is `fctl task add "…"`.
- `docs/MVP.md §10 assumption 9`: task ids are global integers, and the reviewer set is fixed (security, ux, ui, code).
- `docs/data-model-and-api.md §5.1`: `tasks` and `events` writes. `rounds`, `round_files`, `verdicts`, `decisions`, and `runs` are only read here, for the response shapes. No schema change.
- `docs/data-model-and-api.md §5.2`: the stage → status mapping, an `events` row on every change, and a manual move that sets status, clears stage, and gets `409` while a run is active.
- `docs/data-model-and-api.md §6.2`: `GET /api/projects/{id}/tasks`, `POST /api/projects/{id}/tasks` (without `submit`), `GET /api/tasks/{id}`, and `PATCH /api/tasks/{id}` with the three bodies `spec_md`, `stage`, and `status` + `position`.
- `docs/claude-code.md §7.2`: `fctl task add "title"` → `POST /api/projects/{id}/tasks` (not `--run`).
- `docs/claude-code.md §7.4 step 1`: the project is resolved with `--git-common-dir` and `GET /api/projects?path=`, so this works from a worktree too.
- `docs/claude-code.md §7.5`: rows "I add a task → backlog", "Each loop step → in_progress · <stage>", "Approver APPROVE / ESCALATE → review · human_review / escalated", and "Drag on board → any status, stage cleared (blocked during a run)".
- `docs/MVP.md §4.5`: the new mutating routes sit behind the existing middleware. No middleware change.

## Acceptance criteria

`POST /api/projects/{id}/tasks`
- [ ] AC1: `{"title":"Rate-limit login endpoint","description_md":"Max 5 failed logins/min per IP."}` on a connected project → 201 `{"id":<id>,"status":"backlog"}`. One `tasks` row holds that `project_id`, the title, the description, `status` backlog, and NULL `stage`, `spec_md`, `branch`, `worktree_path`, and `done_at`. Its `created_at` equals its `updated_at`, in the `db.now()` format.
- [ ] AC2: `{"title":"x"}` with no `description_md` → 201, and the row's `description_md` is `''`.
- [ ] AC3: `"title":"  Export CSV  "` → the stored title is `Export CSV` (Q7).
- [ ] AC4: `"title":""` or `"title":"   "` → 422 with a string `detail`, and no `tasks` or `events` row is written (Q7).
- [ ] AC5: an unknown project id → 404, and no row is written.
- [ ] AC6: the first task in a project → `position` 1.0 (Q8).
- [ ] AC7: a project with backlog tasks at positions 1.0 and 5.0 and a review task at 9.0, plus another project with a backlog task at 20.0 → the new task's `position` is 6.0 (Q8).
- [ ] AC8: a create → exactly one `events` row for the task: `actor` me, `from_status` NULL, `to_status` backlog, `stage` NULL, `note` NULL, and `created_at` set (Q3).

`GET /api/projects/{id}/tasks`
- [ ] AC9: a project with no tasks → 200 `[]`.
- [ ] AC10: an unknown project id → 404.
- [ ] AC11: a task with no rounds and no runs → its item is exactly `{"id":…,"title":…,"status":"backlog","stage":null,"round":null,"verdicts":null,"additions":null,"deletions":null,"run":null}` (Q9).
- [ ] AC12: rows inserted directly. Round 1 has files +50/−50 and verdicts all CHANGES. Round 2 has files +100/−5 and +26/−4 and verdicts all PASS → `"round":2`, `"verdicts":{"security":"PASS","ux":"PASS","ui":"PASS","code":"PASS"}`, `"additions":126`, `"deletions":9`. Only the latest round counts.
- [ ] AC13: the latest round has verdicts only for security and code → `ux` and `ui` are `"pending"`.
- [ ] AC14: the task has runs #1 `failed` and #2 `running` → `"run":{"id":2,"status":"running"}`. A task whose only run is `failed` → `"run":{"id":…,"status":"failed"}` (Q9).
- [ ] AC15: tasks in all four statuses with mixed positions, plus another project's tasks → only this project's tasks are listed, ordered by column (backlog, in_progress, review, done), then `position`, then `id` (Q9).

`GET /api/tasks/{id}`
- [ ] AC16: a fresh task → 200 with exactly `{"id":…,"title":…,"status":"backlog","stage":null,"branch":null,"rounds":[],"decisions":[],"run":null}` (Q10).
- [ ] AC17: round 1 (`initial`, 4 files totaling +118/−9, verdicts security CHANGES, ux PASS, code PASS) and round 2 (`agent`, no files, no verdicts) → `"rounds":[{"n":1,"trigger":"initial","files":4,"additions":118,"deletions":9,"verdicts":{"security":"CHANGES","ux":"PASS","ui":"pending","code":"PASS"}},{"n":2,"trigger":"agent","files":0,"additions":0,"deletions":0,"verdicts":{"security":"pending","ux":"pending","ui":"pending","code":"pending"}}]`.
- [ ] AC18: an approver ESCALATE on round 1, then my CHANGES_REQUESTED on round 2 → `decisions` lists both in id order, each exactly `{"id","round","actor","decision","body_md","created_at"}`, where `round` is the round's `n` (Q10).
- [ ] AC19: `tasks.branch` set to `factory/12-x` and a `running` run → `"branch":"factory/12-x"` and `"run":{"id":<run id>,"status":"running"}`.
- [ ] AC20: an unknown task id → 404.

`PATCH /api/tasks/{id}` with `spec_md`
- [ ] AC21: `{"spec_md":"## Acceptance criteria\n- x"}` → 200 `{"id":…,"status":…,"stage":…}` with status and stage unchanged. `tasks.spec_md` holds the text, `updated_at` has changed (it was first set to `2026-01-01T00:00:00Z`), and no `events` row is added (Q2).

`PATCH /api/tasks/{id}` with `stage`
- [ ] AC22: each of the 7 stages, on a backlog task → 200 `{"id":…,"status":<mapped>,"stage":<stage>}`, and the row holds the same values. `spec`, `build`, `agent_review`, `approval`, and `rework` map to `in_progress`. `human_review` and `escalated` map to `review`.
- [ ] AC23: `build` on a backlog task, then `agent_review` → two new `events` rows with `actor` orchestrator: (backlog → in_progress, stage build) and (in_progress → in_progress, stage agent_review) (Q2, Q3).
- [ ] AC24: the stage the task already has → 200, and no new `events` row (Q2).
- [ ] AC25: the task has a `running` run → a stage PATCH still gets 200 and is applied (Q5).
- [ ] AC26: the stage leaves `position` unchanged.

`PATCH /api/tasks/{id}` with `status` + `position` (manual move)
- [ ] AC27: a task in review · human_review, then `{"status":"backlog","position":1.5}` → 200 `{"id":…,"status":"backlog","stage":null}`. The row holds status backlog, stage NULL, and position 1.5.
- [ ] AC28: that move adds one `events` row: `actor` me, review → backlog, `stage` NULL (Q3).
- [ ] AC29: a backlog task moved to `{"status":"backlog","position":0.5}` (a reorder) → `position` 0.5, and no new `events` row (Q2).
- [ ] AC30: the task has a `running` run → 409 `{"detail":"run #<run id> active"}`. The row's status, stage, position, and `updated_at` are unchanged, and no `events` row is added (Q1).
- [ ] AC31: a `running` run on another task, or only `failed`/`succeeded`/`stopped` runs on this task → the move gets 200 (Q1).
- [ ] AC32: a move to `done` → `done_at` is set in the `db.now()` format. A later move to `backlog` → `done_at` is NULL. A stage PATCH on a done task → `done_at` is NULL (Q6).

PATCH validation
- [ ] AC33: each of these bodies → 422. The row and its `events` are unchanged: `{}`, `{"status":"backlog"}`, `{"position":2}`, `{"stage":"build","status":"review","position":1}`, `{"spec_md":"x","stage":"build"}`, `{"stage":null}`, `{"spec_md":null}`, `{"stage":"deploy"}`, `{"status":"archived","position":1}`, and the raw body `{"status":"backlog","position":NaN}` (Q4).
- [ ] AC34: an unknown task id → 404.

`fctl task add` (`cli.main([...])` in a temp repo, against 002's recording `server` fixture, extended so each request gets its own reply)
- [ ] AC35: the replies are `GET` → `{"id":3,"name":"api","default_branch":"main","factory":"none"}` and `POST` → 201 `{"id":12,"status":"backlog"}`. `fctl task add "Rate-limit login endpoint"` → exactly two requests: `GET /api/projects?path=<realpath of the repo>`, then `POST /api/projects/3/tasks` with body `{"title":"Rate-limit login endpoint"}`. Then stdout is `Added #12 to api → <FCTL_URL>/projects/3` (Q11).
- [ ] AC36: a repo directory named `my repo` → the GET's `path` query parameter decodes (`urllib.parse.parse_qs`) to the exact realpath.
- [ ] AC37: run from a worktree at `<repo>/.claude/worktrees/x` → the GET's `path` is the main checkout's realpath.
- [ ] AC38: the GET answers 404 `{"detail":"no project at <path>"}` → exit 1, stderr `fctl: 404 no project at <path>`, and no POST is sent (Q11).
- [ ] AC39: run outside any git repo → exit 1, stderr `fctl: not inside a git repository: <cwd>`, and no request is sent.
- [ ] AC40: `fctl task add` with no title, or `fctl task` with no subcommand → exit 2, with usage on stderr.

## Files
- `src/claude_factories/app.py`: the four routes. Pydantic bodies for create and PATCH. A stage → status dict. One helper that builds a task's round summaries (files, +/−, verdicts with `pending`), used by both GET routes. The 409 check, the task update, and the `events` insert run in one transaction.
- `src/claude_factories/cli.py`: the `task add` subcommand (stdlib only, so 001's AC3 keeps passing). It reuses `main_checkout()` and `api()`.
- `tests/test_tasks.py`: new. The API criteria, with rounds, files, verdicts, decisions, and runs inserted by SQL.
- `tests/test_cli.py`: the `fctl task add` tests. The `server` fixture is extended so each request can get its own reply, and the existing tests keep passing unchanged.
- `tests/conftest.py`: only if a helper (for example `sql` or a connected-project fixture) is shared between test files.

No schema change and no new dependencies.

## Out of scope
- `submit` in the create body, `POST /api/tasks/{id}/rounds`, the diff route, and `fctl submit` / `fctl diff` (005). Until then an extra `submit` key is ignored, as with any unknown key (Q7).
- `GET /api/tasks/{id}/context`, and the CLI commands that call this job's PATCH and GET: `fctl spec`, `fctl stage`, and `fctl round` (006).
- The board page, drag and drop, the `+ New task` form, and showing `run` / stalled state on cards (004, 014).
- `run`, `run-next`, `stop`, `log`, worktrees, and setting `branch` / `worktree_path` (012, 013). `fctl task add --run` (015).
- Approve and Request changes, which also change status (009). The task page (010).
- Editing a task's title or description, deleting tasks, and a CLI flag for the description.
- Ids beyond SQLite's integer range returning 500 instead of 404. This is the existing behavior from 002, not changed here.

## Open questions
- Q1: §5.2 says "refused with 409 while a run is active" without saying whose run. Default: only a `running` run of *this* task blocks the move. A run on another task doesn't, so I can still reorder Backlog during a run. The detail is `run #<id> active`, the wording from MVP §4.4. Only manual moves are checked: `spec_md` and `stage` are always allowed, because the orchestrator sends them during its own run.
- Q2: "every change writes an events row" doesn't say what counts as a change. Default: an `events` row is written exactly when `status` or `stage` differs from before. So a pure Backlog reorder, a repeated stage, and a `spec_md` update write none. Every successful PATCH bumps `updated_at`. The update and its event commit together.
- Q3: docs list the actors (`me`, `app`, `orchestrator`) but the PATCH can't tell who is calling. Default: create → `me`, `status` + `position` → `me` (the board drag), `stage` → `orchestrator` (`fctl stage`). `stage` on the event is the task's new stage (NULL after a move), and `note` stays NULL. A create writes one event with `from_status` NULL and `to_status` backlog, which gives 010's history and 007's timeline their "created" entry.
- Q4: docs show three PATCH bodies but don't say how to combine or validate them. Default: a body holds exactly one of `spec_md` (a string), `stage` (one of the 7), or `status` (one of the 4) together with `position` (a finite number). An empty body, a mix of groups, `status` without `position` or the reverse, an explicit null, an unknown value, or a NaN/infinite position → 422. Detect the sent keys with `model_fields_set`. Unknown keys are ignored, so a body with only unknown keys counts as empty. Pydantic's own list-shaped `detail` is fine for the type and enum errors.
- Q5: docs don't guard stage changes. Default: a stage PATCH works on any task in any status, including done, and while a run is active. It never changes `position`.
- Q6: docs don't say who sets `done_at` on a manual move to done (009's Approve is the documented path). Default: any change whose new status is `done` sets `done_at` to `db.now()`, or keeps the existing value if the task was already done. Any change to another status sets it to NULL.
- Q7: docs don't validate the create body. Default: `title` is stripped and must be non-empty, or 422 `title must not be blank`. `description_md` is optional, defaults to `''`, and is stored as sent. `submit` isn't handled yet (005).
- Q8: "the bottom of Backlog" isn't given as a number. Default: `position` = 1 + the highest `position` among this project's backlog tasks, or 1.0 if it has none. Other statuses and other projects don't count. Run next takes the lowest (§5.1 comment).
- Q9: the list item's shape is given, but not its order or its values before a round exists. Default: exactly the §6.2 keys. `round`, `verdicts`, `additions`, and `deletions` describe the latest round (the highest `n`): verdicts carry all 4 reviewers, with `pending` for a missing row, and +/− are the sums over its `round_files`. With no round, all four are null. `run` is the task's latest run by id as `{"id","status"}`, whatever its status (so 014 can show "stalled"), or null. The order is by column (backlog, in_progress, review, done), then `position`, then `id`.
- Q10: `GET /api/tasks/{id}` in §6.2 has no `title` and doesn't show what a decision looks like. Default: the §6.2 keys plus `title`. `rounds` are ordered by `n`, each exactly `{"n","trigger","files","additions","deletions","verdicts"}`, where `files` is the count of its `round_files` rows (0 and +0/−0 when it has none). Each `decisions` item is `{"id","round","actor","decision","body_md","created_at"}`, where `round` is the round's `n`, ordered by id. `run` works as in Q9.
- Q11: §7.2 gives `fctl task add` no output, no project lookup, and no description input. Default: resolve the project with `main_checkout()`, then `GET /api/projects?` + `urllib.parse.urlencode({"path": main})`. POST `{"title": <arg>}` only, with no stdin read. On success, print `Added #<id> to <project name> → <base>/projects/<project id>`, where `<base>` is the same `FCTL_URL`-or-default base that `api()` uses, without a trailing `/`. An unconnected repo shows `api()`'s usual `fctl: 404 no project at <path>`. A "run fctl connect" hint would need `api()` to stop exiting on errors, so it's left out.
