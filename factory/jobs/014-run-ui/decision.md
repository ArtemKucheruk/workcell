APPROVE
Built: the `Claude: Pro ✓` / red `API key — runs disabled` badge on every page, including the 404. It comes from a 60 s cached `claude_login()` that uses the stripped env with cwd = data dir. The board gets an enabled Run next, Backlog `[Run]`, `● running · <stage>` + `started HH:MM`, and `stalled · <stage> [Retry]`. The task page gets Run/Stop/Retry, `run #N <status>`, the factory hint, the shlex-quoted takeover command or `Stop the run to take over.`, and a collapsed `#run-log` that polls the JSON log route and appends lines with `textContent`. Run/Retry/Run next are disabled when the factory isn't ready or the badge is red. Stop is never disabled. `run_task`'s 409 texts, the API shapes and the routes are unchanged.
Rounds: 1 of 2. All four reviews (code, security, ui, ux) PASS in round 1. ui and ux checked it in headless Chromium.
Tests: `uv run pytest -q` 648 passed (build.md and review-code.md). AC1–AC20 are in tests/test_run_ui.py. AC21 is the whole suite plus the updated tests/test_board.py tests. Each AC has a test that asserts it. I found no conflict with docs/ui.md §8/§8.1, MVP.md §3.2/§3.4/§4.1/§4.3/§4.4/§4.5, data-model-and-api.md §6.2, or claude-code.md §7.5.
Non-blocking nits worth knowing:
- (security) On a cold cache, the async 404 handler runs `claude auth status` on the event loop, so it can block for up to 30 s, at most once per minute.
- (security) `--resume <session_id>` could be hardened by showing the line only for a UUID session id.
- (ux) The log panel keeps polling after its run ends.

## Open questions
- Q1 (cwd/env for the badge check): same stripped env as runs, cwd = data dir (`FCTL_HOME`). Each run's own check is unchanged.
- Q2 (plan label): `Claude: <subscriptionType capitalized> ✓`. Missing or non-string → `Claude: subscription ✓`.
- Q3 (how often to check): cached 60 s per process on `time.monotonic`, 30 s timeout kept, per-run check uncached. `ponytail:` no lock.
- Q4 (what "runs disabled" does): Run, Run next, and Retry get `disabled` while the badge is red. Stop is never disabled. The server check still decides.
- Q5 (when "stalled" applies): in_progress + latest run `running` → `● running · <stage>`. in_progress + latest run failed/stopped/succeeded → `stalled · <stage>` + Retry. Stage NULL drops ` · <stage>`. in_progress with no runs → no run UI. Backlog → Run. Review/Done cards → no run UI. The task page still shows Stop while a run is running.
- Q6 (hint for the `none` state): `run_task`'s 409 detail for the state, next to Run next on the board and Run/Retry on the task page.
- Q7 (`started` format): local `HH:MM` on both pages.
- Q8 (run status format): `run #<id> <status>`. Running adds ` · started HH:MM`. Failed with an error adds `: <error>`, escaped.
- Q9 (when to show takeover): only when the latest run isn't running and `worktree_path` is set. While running: `Stop the run to take over.`. Both parts are `shlex.quote`d.
- Q10 (log panel): an inline script polls the §6.2 JSON route from `after=0`. The panel sits outside `#live`, follows the run that was latest at page load (`ponytail:`), and polls every 3 s only if that run was running, otherwise fetches once.
- Q11 ("every page header"): one `#claude-auth` line in `base.html`, above each page's own header.
- Q12 (disable Run while another run is active): left enabled. The 409 `run #N active` shows in the alert.
- Q13 (Stop on cards): Stop is on the task page only.
- Builder addition: `tests/test_board.py::test_new_task_lands_last` (003 AC30) also compares a Backlog card's exact text, so it was updated to `… Export CSV Run`, like the two tests AC21 names. Its meaning is unchanged.
- Builder addition: the task page's refusal alert `#run-error` uses `hx-preserve` so the 3 s poll doesn't clear it. It clears on the reload that follows a successful action.
- Builder addition: an empty log shows `No output yet.`. ux nit: it stays if every log line is one the display filters out.
