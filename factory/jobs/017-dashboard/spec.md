# 017-dashboard: Dashboard: status tiles, open tasks, rounds per task

## Goal
Replace the placeholder index at `/` (today a workspace list) with the dashboard from docs/ui.md
§8 item 1. It covers every project: tiles that count tasks per status, tasks waiting on me,
escalated tasks, the run going now, tasks done this week, and runs this week. Each tile links to a
filtered list. Below the tiles go a table of open tasks per workspace → project, and rounds per task
for tasks done in the last 30 days. The page only reads. It adds no API, no writes, and no
dependency.

## Implements
- `docs/ui.md §8 item 1`: the tiles, the open-tasks table, the rounds-per-task block, and a filtered list behind each tile.
- `docs/data-model-and-api.md §6.4`: `/` is the dashboard.
- `docs/data-model-and-api.md §5.1, §5.2`: what the page reads. That is `tasks.status`, `stage`, `done_at`, and `updated_at`; `runs.status` and `started_at`; and `rounds` per task. `human_review` means waiting on me.
- `docs/MVP.md §9`: Dashboard is MVP scope.

## Acceptance criteria
Counts cover all projects. "Within the last N days" means `>= now − N days` in UTC (Q2). In the
tests, set `done_at` and `started_at` directly in SQL to 6 days ago and 8 days ago (or 29 and 31),
so no test lands on the boundary.

- [ ] AC1: With an empty database, `GET /` → 200, rendered from `index.html`. All nine tiles show `0`, and the page contains `No projects yet.`.
- [ ] AC2: Status tiles. Set up 2 backlog, 1 in_progress, 1 review, and 1 done task, spread over two projects in two workspaces. `GET /` shows tiles Backlog 2, In progress 1, Review 1, and Done 1, linked to `/?show=backlog`, `/?show=in_progress`, `/?show=review`, and `/?show=done`.
- [ ] AC3: The "Waiting on me" tile counts tasks with stage `human_review` and links to `/?show=waiting`. An `escalated` task is not counted.
- [ ] AC4: The "Escalated" tile counts tasks with stage `escalated` and links to `/?show=escalated`.
- [ ] AC5: The "Running now" tile counts runs with status `running` and links to `/?show=running`. A `succeeded` or `failed` run is not counted.
- [ ] AC6: The "Done this week" tile counts tasks whose `done_at` is within the last 7 days and links to `/?show=done_week`. A task done 8 days ago is not counted.
- [ ] AC7: The "Runs this week" tile counts runs whose `started_at` is within the last 7 days, whatever their status, and links to `/?show=runs_week`. A run started 8 days ago is not counted.
- [ ] AC8: For each status, `GET /?show=<status>` lists exactly the tasks in that status, across all projects. Each row has `#<id> <title>` linked to `/tasks/<id>` and the project name linked to `/projects/<project_id>`. Tasks in other statuses are absent.
- [ ] AC9: `GET /?show=waiting`, `escalated`, `running`, and `done_week` each list exactly the tasks their tile counts (parametrized test). For `running`, that is the task of the running run.
- [ ] AC10: `GET /?show=runs_week` lists one row per run started in the last 7 days. Each row has `run #<id>`, its task's `#<id> <title>` linked to `/tasks/<id>`, and the run's status. The 8-day-old run is absent.
- [ ] AC11: A filtered list sits under an `<h2>` with its tile's label, and that tile has `aria-current="page"`. Without `show`, no tile has `aria-current`.
- [ ] AC12: A filtered list with no matches shows `No tasks.`. For `runs_week` it shows `No runs.`.
- [ ] AC13: `GET /?show=bogus` → 200, the dashboard with no filtered list and no tile marked current.
- [ ] AC14: Open-tasks table. Each project with at least one backlog, in_progress, or review task gets one row, under its workspace name linked to `/workspaces/<id>`. The row has the project name linked to `/projects/<id>` and Backlog, In progress, and Review counts. Done tasks are not counted, and a project with only done tasks has no row.
- [ ] AC15: The open-tasks table orders workspaces by name, and projects by name within each workspace.
- [ ] AC16: With no open tasks anywhere, the open-tasks section shows `No open tasks.`.
- [ ] AC17: Rounds per task. Three tasks were done within the last 30 days, with 1, 2, and 4 rounds. The section shows average `2.3`, max `4`, and one row per task: `#<id> <title>` linked to `/tasks/<id>`, plus its round count.
- [ ] AC18: Rounds per task leaves out a task done 31 days ago, a task not done, and a done task with no rounds.
- [ ] AC19: With no qualifying tasks, the rounds section shows `No tasks done in the last 30 days.`. No average or max is shown.
- [ ] AC20: A task titled `<script>x</script>` comes out escaped (`&lt;script&gt;`) in the filtered list, and the raw tag is not in the page.
- [ ] AC21: These existing tests still pass unchanged: `tests/test_app.py::test_index_uses_base_layout` (template `index.html` on base.html) and `tests/test_projects.py::test_index_lists_workspaces` (workspace links with project counts, and `No projects yet.` when empty).

## Files
- `src/claude_factories/app.py`: the `index` route takes an optional `show` query parameter and builds the tile counts, the filtered list, the open-tasks rows, and the rounds stats. Use plain SQL through the existing `query()`, as the workspace page does with `COUNT(...) FILTER (WHERE ...)`. Delete the `ponytail: workspace list until the dashboard` comment.
- `src/claude_factories/templates/index.html`: the dashboard, kept under this name and extending base.html.
- `src/claude_factories/templates/base.html`: a few tile styles appended at the end of the `<style>` block, using `GrayText` borders like `.card` and no new colors.
- `tests/test_dashboard.py`: new.

## Out of scope
- The `Claude: Pro ✓` / `API key — runs disabled` page header, plus Run, Stop, Retry, and stalled cards. Those belong to 014-run-ui.
- Run control, run logs, and the 013 merge (013-run-control, 018-merge-013).
- A JSON API for the dashboard. docs §6 defines none.
- A separate `/tasks` or `/runs` list route, pagination, search, and sorting controls.
- Polling or live updates on the dashboard (Q8).
- Any change to the workspace page, board, task page, or review page.

## Open questions
- Q1: Where the filtered list lives. §8 says each tile links to one, and §6.4 lists no list route. Default: the dashboard itself at `/?show=<key>`, with the list rendered below the tiles. Keys: `backlog`, `in_progress`, `review`, `done`, `waiting`, `escalated`, `running`, `done_week`, `runs_week`.
- Q2: What "this week" and "the last 30 days" mean. Default: rolling windows in UTC, `>= now − 7 days` and `>= now − 30 days`, compared as the stored `YYYY-MM-DDTHH:MM:SSZ` strings (`db.now()` format). Not calendar weeks.
- Q3: What the runs-this-week list shows. Default: one row per run, not per task, since the tile counts runs. A row has run id, task link, project, run status, and start time (`local_time`), newest run first. Running now lists tasks, one per running run.
- Q4: The filtered task list's columns and order. Default: `#id title` → `/tasks/{id}`, project → `/projects/{id}`, and `status · stage`, ordered by `updated_at` desc, then `id` desc. No pagination.
- Q5: What "open" means, and the table's shape. Default: open is backlog, in_progress, or review. The table has one row per project with counts per open status, not one row per task, and lists only projects with at least one open task. Workspaces and projects are ordered by name.
- Q6: Which tasks count for rounds per task. Default: `done_at` within the last 30 days and at least one round. A task's rounds = `COUNT(rounds)`. The average has one decimal. The list shows `#id title`, project, rounds, and done time, ordered by `done_at` desc.
- Q7: An unknown `show` value. Default: ignored, so the page is a 200 dashboard with no list, not a 404 or 422.
- Q8: Whether the dashboard polls. §8 says "live parts poll every 3 s", and §4.1 names only the board, task, and run-log fragments. Default: no polling.
- Q9: Whether the old workspace list stays. §8 item 1 doesn't mention it. Without it, a workspace with no open tasks has no link from `/`. Default: keep the existing Workspaces list and its `No projects yet.` empty state as is, below the dashboard sections. The empty state may add the hint `Run fctl connect --workspace <name> inside a repo.`, as the workspace page does.
