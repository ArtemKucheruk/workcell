# Round 1
## Changes
- src/claude_factories/app.py: `index` takes an optional `show` query parameter. `TILES` (key → label, the `?show=` keys from Q1) and `TILE_TASKS` (key → constant WHERE on `tasks t`) feed one `COUNT(*) FILTER (WHERE …)` query for the tile counts, plus a `runs` subquery for Runs this week. A known `show` adds the filtered list (tasks, or runs for `runs_week`), and an unknown one is dropped (Q7). There's also the open-tasks query, grouped per workspace with `itertools.groupby`, and the rounds-per-task query (an inner JOIN on `rounds`, so tasks with no rounds drop out). `days_ago(n)` is SQLite `strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-n days')`, so windows compare as `db.now()` strings in UTC (Q2). Every SQL fragment is a constant. `show` only selects one after a dict membership check. Deleted the `ponytail: workspace list until the dashboard` comment.
- src/claude_factories/templates/index.html: the dashboard, still extending base.html. It has nine tiles (`<ul class="tiles">`, each `<a href="/?show=<key>">` with label and count, and `aria-current="page"` on the selected one). Then `section#list` with an `<h2>` for the tile label, a task table (`#id title` → task, project → project, `status · stage`) or a runs table (`run #id`, task, project, status, start time), or `No tasks.` / `No runs.`. Then `section#open-tasks`, one `<tbody>` per workspace with a `rowgroup` header linking the workspace, and project rows with Backlog / In progress / Review counts, or `No open tasks.`. Then `section#rounds` with average (one decimal), max, and the list, or `No tasks done in the last 30 days.`. Last, the existing `section#workspaces` list (Q9). Its empty state adds the `fctl connect --workspace <name>` hint.
- src/claude_factories/templates/base.html: dashboard styles appended at the end of `<style>`. Tiles are a grid of `GrayText`-bordered cards with a big count. The current tile gets a `currentColor` border and box-shadow, and the open-tasks project cells are indented under their workspace row. No new colors (`CanvasText`/`currentColor` are system colors).
- tests/test_dashboard.py: new, one test per acceptance criterion.

## Criteria → tests
- AC1 → tests/test_dashboard.py::test_empty_database
- AC2 → tests/test_dashboard.py::test_status_tiles
- AC3 → tests/test_dashboard.py::test_waiting_tile
- AC4 → tests/test_dashboard.py::test_escalated_tile
- AC5 → tests/test_dashboard.py::test_running_tile
- AC6 → tests/test_dashboard.py::test_done_this_week_tile
- AC7 → tests/test_dashboard.py::test_runs_this_week_tile
- AC8 → tests/test_dashboard.py::test_status_list (parametrized over the 4 statuses)
- AC9 → tests/test_dashboard.py::test_tile_lists (parametrized: waiting, escalated, running, done_week)
- AC10 → tests/test_dashboard.py::test_runs_week_list
- AC11 → tests/test_dashboard.py::test_list_heading_and_current_tile
- AC12 → tests/test_dashboard.py::test_empty_lists
- AC13 → tests/test_dashboard.py::test_unknown_show
- AC14 → tests/test_dashboard.py::test_open_tasks_table
- AC15 → tests/test_dashboard.py::test_open_tasks_order
- AC16 → tests/test_dashboard.py::test_no_open_tasks
- AC17 → tests/test_dashboard.py::test_rounds_per_task
- AC18 → tests/test_dashboard.py::test_rounds_leave_out
- AC19 → tests/test_dashboard.py::test_no_rounds
- AC20 → tests/test_dashboard.py::test_title_escaped
- AC21 → tests/test_app.py::test_index_uses_base_layout, tests/test_projects.py::test_index_lists_workspaces (unchanged, passing)

## Open questions
- Q1 → the filtered list renders on `/?show=<key>` below the tiles, with the nine keys from the spec.
- Q2 → rolling UTC windows (`>= now − 7 days`, `>= now − 30 days`), computed in SQLite and compared as `YYYY-MM-DDTHH:MM:SSZ` strings.
- Q3 → one row per run (run id, task link, project, status, `local_time` start), newest first. Running now lists the task of each running run. Its filter is `t.id IN (running runs)`, and `one_active_run` allows only one running run, so the task count equals the run count.
- Q4 → task list columns `#id title`, project, `status · stage`, ordered `updated_at` desc then `id` desc. No pagination.
- Q5 → open = backlog/in_progress/review. One row per project with ≥1 open task, workspaces then projects by name (project id breaks name ties).
- Q6 → `done_at` within 30 days and ≥1 round. Rounds = `COUNT(rounds)`, average to one decimal (`%.1f`), list ordered `done_at` desc.
- Q7 → an unknown `show` is ignored: 200, no list, no current tile.
- Q8 → no polling.
- Q9 → the Workspaces list stays below the dashboard. Its empty state reads `No projects yet. Run fctl connect --workspace <name> inside a repo.`

## Test output
```
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/017-dashboard/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
590 passed, 1 warning in 69.16s (0:01:09)
```
