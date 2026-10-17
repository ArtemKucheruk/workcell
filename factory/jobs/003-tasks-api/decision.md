APPROVE
Built the Tasks API in app.py: `GET`/`POST /api/projects/{id}/tasks`, `GET /api/tasks/{id}`, and `PATCH /api/tasks/{id}` with the spec_md, stage, and status + position bodies, the stage → status map, `events` rows, and the 409 during a run. The 409 check, the update, and the event run in one `BEGIN IMMEDIATE` transaction. Also built `fctl task add "title"` in cli.py (stdlib only, works from a worktree). No schema change, no new dependencies, and the §4.5 middleware is untouched.
Rounds: 1 of 2. All four reviews (security, ux, ui, code) say PASS with only non-blocking nits.
Tests: 144 passed, 1 warning (build.md, re-run in review-code.md). AC1–AC40 each map to a test in tests/test_tasks.py or tests/test_cli.py that asserts the criterion.
Behavior outside the spec's list, none of it against docs/: a global `RequestValidationError` handler drops the echoed `input` from every route's 422. It is needed so the NaN body in AC33 gets 422 instead of 500. Also, `GET /api/tasks/{id}` adds `title` to the §6.2 shape (Q10), and the CLI's "can't reach" message no longer ends in `/`.

## Open questions
- Q1 (whose run blocks a manual move): only a `running` run of this task returns 409 `run #<id> active`. spec_md and stage PATCHes are never blocked. Builder used the default.
- Q2 (what counts as a change): an `events` row is written only when status or stage differs. A reorder, a repeated stage, or a spec_md edit writes none. Every successful PATCH bumps `updated_at`. Builder used the default.
- Q3 (actors): create and manual move use `me`, a stage PATCH uses `orchestrator`. The event's `stage` is the new stage, `note` is NULL, and a create logs NULL → backlog. Builder used the default.
- Q4 (PATCH validation): a body must hold exactly one of spec_md, stage, or status + finite position. An empty body, mixed groups, a null, an unknown value, or NaN/Inf gets 422. Unknown keys are ignored. Builder used the default.
- Q5 (stage guards): a stage PATCH works in any status, also while a run is active, and never changes position. Builder used the default.
- Q6 (done_at): a move to done sets `done_at` to now, or keeps it if the task was already done. Any other status clears it. Builder used the default, with one edge: a done task whose `done_at` is NULL (only possible through raw SQL) gets now instead of keeping NULL.
- Q7 (create body): the title is stripped, and a blank title gets 422 `title must not be blank`. `description_md` defaults to `''`. `submit` is ignored until 005. Builder used the default.
- Q8 (bottom of Backlog): position is 1 + the highest backlog position in the project, or 1.0 if it has none. Builder used the default.
- Q9 (list item): the item has exactly the §6.2 keys, taken from the latest round. A missing verdict is `pending`, and with no round those four keys are null. `run` is the latest run by id, whatever its status. Order is column, then position, then id. Builder used the default.
- Q10 (task detail): the §6.2 keys plus `title`. Rounds are ordered by n and include a `files` count. Each decision is `{id, round(n), actor, decision, body_md, created_at}`, ordered by id. Builder used the default.
- Q11 (fctl task add): resolves the repo with `main_checkout()`, looks up the project with `GET /api/projects?path=`, and POSTs only the title. It prints `Added #<id> to <name> → <base>/projects/<id>`. An unconnected repo gets the usual 404 message and no "run fctl connect" hint. Builder used the default.
- Builder-added: the PATCH body check runs before the 404 lookup, so an invalid body on an unknown task gets 422, not 404. Pydantic's own type errors come first anyway.
- Builder-added: the body-shape and null errors return string details: `send exactly one of: spec_md, stage, or status with position` and `<keys> must not be null`.
- Builder-added: the list route runs 3 queries per task, marked `ponytail:`. It should become one grouped query if a board grows past a few hundred tasks.
