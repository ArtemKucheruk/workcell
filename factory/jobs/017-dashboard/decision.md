APPROVE
Built the read-only dashboard at `/` (docs/ui.md §8 item 1, data-model-and-api.md §6.4). It has nine tiles, each linking to a `/?show=<key>` filtered list, plus an open-tasks table per workspace → project and a rounds-per-task block (average, max, list) for the last 30 days. The old Workspaces list stays below. The `index` route in app.py uses plain SQL, index.html was rewritten, tile styles were appended to base.html, and tests/test_dashboard.py is new. No API, writes, or dependencies were added.
Rounds: 1 of 2. All four reviewers (code, security, ui, ux) said PASS. Only non-blocking nits came up: f-string SQL in `days_ago()` and `TILE_TASKS` is safe because every fragment is a constant, the `<th>` headers above numeric columns are left-aligned, and there is a pre-existing favicon 404.
Tests: 590 passed, in both build.md and review-code.md. AC1–AC20 each have a test in tests/test_dashboard.py. AC21's two existing tests pass unchanged, and no existing test file was modified.

## Open questions
- Q1, where the filtered list lives: on the dashboard itself at `/?show=<key>`, below the tiles. Keys are backlog, in_progress, review, done, waiting, escalated, running, done_week, runs_week. (Default used.)
- Q2, "this week" and "last 30 days": rolling UTC windows `>= now − 7/30 days`, not calendar weeks. They're computed with SQLite `strftime('%Y-%m-%dT%H:%M:%SZ','now','-N days')`, which matches the `db.now()` format, and compared as strings. (Default used.)
- Q3, the runs-this-week list: one row per run (run id, task link, project, status, local start time), newest first. Running now lists the task of each running run, and since `one_active_run` allows only one, that is at most one task. (Default used.)
- Q4, the filtered task list: columns `#id title` → `/tasks/{id}`, project → `/projects/{id}`, and `status · stage`. Status is shown with its tile label, e.g. "In progress". Rows are ordered by `updated_at` desc, then `id` desc, with no pagination. (Default used.)
- Q5, what "open" means: backlog, in_progress, or review. The table has one row per project that has at least one open task, with workspaces and then projects ordered by name. Project id breaks name ties. (Default used.)
- Q6, which tasks count for rounds: `done_at` within 30 days and at least one round. Rounds are `COUNT(rounds)`, the average has one decimal, and the list is ordered by `done_at` desc. (Default used.)
- Q7, an unknown `show` value: ignored. The page returns 200 with no list and no current tile. (Default used.)
- Q8, polling: none. This matches MVP.md §4.1 ("board, task, and run-log fragments poll"). ui.md §8's "live parts poll every 3 s" could be read to cover the Running now tile, so polling it would be a later choice. (Default used.)
- Q9, the old workspace list: kept below the dashboard sections. Its empty state now reads "No projects yet. Run `fctl connect --workspace <name>` inside a repo." (Default used.)
