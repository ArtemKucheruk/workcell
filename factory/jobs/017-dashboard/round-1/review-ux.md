VERDICT: PASS

Walked in headless Chromium against `fctl serve` from the worktree, with FCTL_HOME in a temp dir. Seeded through the real CLI (`fctl connect` ×2, `fctl task add`, `fctl stage`, `fctl submit --new`, `fctl approve`), then added the edge cases by SQL in the temp DB (escalated task, running run, succeeded and failed runs, done tasks at 5, 10, and 31 days ago, a done task with no rounds).

Checked:
- Empty DB: nine tiles all `0`, "No open tasks.", "No tasks done in the last 30 days.", "No projects yet. Run fctl connect --workspace <name> inside a repo.".
- Seeded counts: Backlog 2, In progress 1, Review 2, Done 4, Waiting on me 1, Escalated 1, Running now 1, Done this week 2, Runs this week 2. Each matches the expected value.
- Each tile click lands on `/?show=<key>`; the list under the matching `<h2>` has the expected rows. `aria-current="page"` is set only on the selected tile. `show=bogus` gives the plain dashboard with no list and no current tile.
- Waiting excludes the escalated task. Done this week excludes the 10- and 31-day-old tasks. Runs this week excludes the 8-day-old failed run.
- Open-tasks table: workspaces `personal` then `work`, workspace and project links, Backlog / In progress / Review counts, done tasks excluded.
- Rounds: average `2.0`, max `3`. The 31-day-old task and the no-round task are absent.
- `show=escalated` with no matches shows "No tasks.". A `<script>x</script>` title is escaped in the page and renders as text on `/tasks/10`.
- Clicking a list task link opens `/tasks/10` (200). API-style 404 for an unknown task still works.
- Console: only a favicon.ico 404 on `/`. Nothing on the dashboard or the task page.
- Screenshots looked right (tile grid, tables, rounds block).

## Nits (non-blocking)
- `/favicon.ico` returns 404 in the browser console. It isn't part of this diff, so I didn't check whether it predates the job.
