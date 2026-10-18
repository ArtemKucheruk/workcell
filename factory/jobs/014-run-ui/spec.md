# 014-run-ui: Run controls, stalled cards, run log, auth badge

## Goal
Put the run endpoints from 012 and 013 on the pages. The board gets a working **Run next**, a **Run** button on Backlog cards, `● running · <stage>` / `started HH:MM` lines, and `stalled · <stage>` cards with **Retry**. The task page gets Run, Stop, and Retry, the latest run's status, a collapsed run log that polls every 3 s, and the takeover command. Every page shows `Claude: Pro ✓`, or a red `API key — runs disabled`, from `claude auth status`. No API route or response shape changes.

## Implements
- `docs/ui.md §8` (intro): every page header shows the login runs will use, from `claude auth status`. It reads `Claude: Pro ✓` for a subscription and a red `API key — runs disabled` otherwise.
- `docs/MVP.md §4.3`: the header shows the reported plan (`subscriptionType`). The check runs with the same stripped environment as runs. Each run's own check in `run_task` stays as it is.
- `docs/ui.md §8 item 3` and `§8.1`: **Run next** in the board header. `[Run]` on Backlog cards. `● running · <stage>` and `started 10:02` on a running card. `stalled · build  [Retry]`.
- `docs/MVP.md §3.4` (last paragraph) and `docs/claude-code.md §7.5` (last row): a run that died shows "stalled" and Retry. Retry is `/factory <id>` again.
- `docs/MVP.md §3.2 step 4`: Run stays disabled, showing the commit hint, until the factory is committed on the default branch.
- `docs/ui.md §8 item 4`: the header holds Run / Stop / Retry and the run status. Also the run log tail (collapsed) and "Take over in terminal".
- `docs/MVP.md §4.4`: Stop. The takeover command `cd <worktree> && claude --resume <session-id>`.
- `docs/data-model-and-api.md §6.2`: Run and Retry → `POST /api/tasks/{id}/run`. Run next → `POST /api/projects/{id}/run-next`. Stop → `POST /api/runs/{id}/stop`. The run log panel polls `GET /api/runs/{id}/log?after=`.
- `docs/MVP.md §4.1`, `§10 assumption 13`: the run log polls every 3 s.
- `docs/MVP.md §4.5`: the buttons send `X-Requested-By: fctl` through the existing `hx-headers` on `<body>`. Agent-derived text (run error, log lines) is escaped and never parsed as HTML.

## Acceptance criteria
Setup is 012's (`tests/test_runs.py`) unless a criterion says otherwise:
- `project` is a repo with SKILL.md committed on `main`, so the factory is `ready`.
- `fake`'s `auth status` prints `AUTH_OK` (claude.ai, pro).
- Runs are rows inserted by SQL, with the given `status`, `started_at`, `error`, and `session_id`.
- "Local HH:MM" means `datetime.fromisoformat(started_at).astimezone().strftime("%H:%M")`.
- "Text" means the element's text with tags stripped, whitespace collapsed, and HTML entities unescaped.

Header badge
- [ ] AC1: with `AUTH_OK`, each of these pages has exactly one `id="claude-auth"` element: `GET /`, `/workspaces/{id}`, `/projects/{id}`, `/projects/{id}/code`, `/tasks/{id}`, `/tasks/{id}/review`, and the 404 page `/tasks/999`. Its text is `Claude: Pro ✓`, and it doesn't have the class `off`.
- [ ] AC2: `{"authMethod":"claude.ai","subscriptionType":"max"}` → `Claude: Max ✓`. `{"authMethod":"claude.ai"}` with no `subscriptionType` → `Claude: subscription ✓` (Q2).
- [ ] AC3: 012 AC20's three non-subscription answers: `{"authMethod":"console"}`, `not json`, and `AUTH_OK` with exit code 1. Each gives `#claude-auth` the text `API key — runs disabled` and the class `off`. In `base.html`, `.off` uses the existing red `light-dark(#cf222e, #f85149)`.
- [ ] AC4: the server env has `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and `CLAUDE_CODE_USE_BEDROCK` set. A page load runs `claude auth status` without any of them in its env, and with cwd = the data dir `FCTL_HOME` (Q1).
- [ ] AC5: two page loads in a row run `claude auth status` once. After the clock the cache reads moves past 60 s, the next page load runs it again (Q3).

Board (`/projects/{id}`)
- [ ] AC6: a Backlog card has a `<button>` with text `Run` and `hx-post="/api/tasks/<id>/run"`, without `disabled`. Review and Done cards have no Run or Retry button.
- [ ] AC7: the header's `Run next ▶` button has `hx-post="/api/projects/<id>/run-next"` and no `disabled`.
- [ ] AC8: an in_progress · build task whose latest run is `running` → the card's text contains `● running · build` and `started <local HH:MM>`, and the card has no Run or Retry button. With stage NULL, the line is `● running` with no ` · ` (Q5, Q7).
- [ ] AC9: an in_progress · build task whose latest run is `failed`, `stopped`, or `succeeded` (parametrized) → the card's text contains `stalled · build`. It has a `<button>` with text `Retry` and `hx-post="/api/tasks/<id>/run"`, and no `● running`. With stage NULL, the text is `stalled` with no ` · ` (Q5).
- [ ] AC10: an in_progress task with no runs → no Run or Retry button, and no `stalled` or `● running`. The card is what 004 renders today (Q5).
- [ ] AC11: SKILL.md written but not committed (`uncommitted`) → Run next and every card's Run and Retry buttons have `disabled`. The header's text contains `run_task`'s 409 detail for that state: `factory isn't committed on main: on main, run git add .claude/skills/factory .claude/agents && git commit -m "Add factory"`. With no SKILL.md (`none`), the buttons are disabled and the header shows the `none` detail: `factory isn't committed on main: Create factory on the project board, then commit it on main` (Q6).
- [ ] AC12: factory `ready`, but `auth status` answers `{"authMethod":"console"}` → Run next and every card's Run and Retry buttons have `disabled` (Q4).

Task page (`/tasks/{id}`)
- [ ] AC13: a backlog task with no runs → inside `#live`, a `<button>` with text `Run` and `hx-post="/api/tasks/<id>/run"`. There is no Stop or Retry button, no run status, no `id="run-log"`, and no takeover command.
- [ ] AC14: the latest run R is `running` → inside `#live`, a `<button>` with text `Stop` and `hx-post="/api/runs/<R>/stop"`, and the run status text `run #<R> running · started <local HH:MM>`. There is no Run or Retry button (Q8).
- [ ] AC15: an in_progress task whose latest run R is `failed` with error `exit code 3` → a `Retry` button with `hx-post="/api/tasks/<id>/run"`, and the run status `run #<R> failed: exit code 3`. `stopped` → `run #<R> stopped`. `succeeded` → `run #<R> succeeded`. `failed` with error NULL → `run #<R> failed` (Q8).
- [ ] AC16: a run error of `<script>alert(1)</script>` → the page contains `&lt;script&gt;alert(1)&lt;/script&gt;` and no `<script>alert`.
- [ ] AC17: a review · human_review task and a done task, each with a `succeeded` latest run → no Run, Stop, or Retry button, and the run status is shown. A review task whose latest run is `running` → Stop is shown (Q5).
- [ ] AC18: an uncommitted factory, or `auth status` answering `{"authMethod":"console"}` → Run (backlog task) and Retry (stalled task) have `disabled`. For the factory case, the page's text contains AC11's detail. A Stop button is never disabled (Q4, Q6).
- [ ] AC19: a task with a run R → a `<details id="run-log">` with no `open` attribute and with `data-run="<R>"`, placed after `#live` closes, not inside it. The page's script contains `/api/runs/` and `/log?after=`. A task with no runs has no `id="run-log"` (Q10).
- [ ] AC20: `worktree_path` W and a latest run that isn't `running`, with `session_id` S → the text contains `cd <shlex.quote(W)> && claude --resume <shlex.quote(S)>`. With W containing a space, the path shows single-quoted. With the latest run `running`, the command is absent and the text contains `Stop the run to take over.`. With no run, or `worktree_path` NULL, neither one appears (Q9).

Existing tests
- [ ] AC21: `uv run pytest -q` passes as a whole. The 004 tests whose exact card text now includes the Backlog `Run` button are updated to expect it: `test_stage_text` (AC11) and `test_no_rounds_no_chips` (AC16) in `tests/test_board.py`. Nothing else changes meaning. 004's `test_run_next_disabled` keeps passing: its project `/code/api` isn't a repo, so the factory is `none`.

## Files
- `src/claude_factories/app.py`:
  - Split the `auth status` parsing out of `subscription_auth`. One function returns the parsed dict when the exit code is 0 and `authMethod == "claude.ai"`, and `None` otherwise. `subscription_auth` becomes `… is not None`, so `run_task` behaves the same.
  - A cached `claude_login()` for pages, which is the only new state:
    - It returns `Claude: Pro ✓` / `API key — runs disabled` and whether runs are allowed.
    - It runs with the §4.3 stripping that `run_env` does (FCTL_URL doesn't matter here), with cwd `db.data_dir()`.
    - Cache it module-level with a 60 s TTL on `time.monotonic()`.
    - Expose it to templates as a Jinja global, so `base.html` renders it for every page, including the 404 handler's.
  - One helper that gives the factory hint for a state. `run_task`'s two 409 details use it too, and their text doesn't change (012 AC19 and 015 assert it).
  - `local_time` gains a format argument, or there is a second one-line filter, for `HH:MM`.
  - `project_page`: the latest run's `started_at` for each in_progress card, read beside `list_tasks` the way `positions` is. The API's `run` stays `{"id","status"}` (§6.2, 003 AC14). Also the auth and factory flags that disable the buttons.
  - `task_page`: add the latest run's row (id, status, error, session_id, started_at), the factory state and hint (`PAGE_TASK` needs `p.default_branch`), the auth flag, and the takeover string built with `shlex.quote`.
- `src/claude_factories/templates/base.html`:
  - `<p id="claude-auth">` before `{% block content %}`, not inside a `<header>` or `<section>`. 010's `test_live_poll` and the review tests' `header()` slice the first `<header>`.
  - The `.off` red. Minimal CSS for the log box.
- `src/claude_factories/templates/project.html`: the card states (AC6–AC10), an enabled Run next, and the hint (AC11).
- `src/claude_factories/templates/task.html`:
  - Buttons, run status, and the takeover command inside `#live`, so the 3 s poll keeps them current.
  - `#run-log` and its script after `#live`, rendered only when the task has a run, so 010's `</main>\s*</div>\s*</body>` check still holds for a task without one.
- `tests/conftest.py`: an autouse reset of the `claude_login` cache, because tests swap fakes.
- `tests/test_run_ui.py` (new): AC1–AC20. Import `fake`, `project`, `add_task`, and `AUTH_OK` from `test_runs`, as `test_run_control.py` does. AC5 needs a fake that counts its `auth status` calls (append, don't overwrite).
- `tests/test_board.py`: AC21.

Browser behaviour that pytest can't see. ux and ui check these in the browser:
- Each button has `hx-swap="none"`, so the JSON reply is never swapped into the page, and `hx-disabled-elt="this"` (htmx 2.0.11 is vendored), so a double click can't send a second POST.
- Board: on success, `htmx.trigger(#board, "refresh")`. On a 4xx or 5xx, the reply's `detail` goes into the existing `#board-error`.
- Task page: on success, `location.reload()`, so the log panel follows the new run. On refusal, the detail goes into a `role="alert"` next to the buttons.
- The 3 s polls replace the buttons. Pause `#board` and `#live` while a button's request is in flight, for example with `.htmx-request` in their `hx-trigger` conditions. Otherwise the error event fires on a detached element and is lost.
- Log panel:
  - It fetches `GET /api/runs/<R>/log?after=<next>`, starting at 0, and appends each item with `textContent`, never `innerHTML`.
  - It polls every 3 s if the run was `running` when the page loaded. Otherwise it fetches once.
  - The box keeps scrolled to the newest line.

No new dependency (`shlex` and `time` are stdlib). No schema change. No new route.

## Out of scope
- Any change to `/run`, `/run-next`, `/stop`, or `/log`: their checks, responses, or shapes (012, 013).
- `fctl` commands (015 is done).
- Live-updating the badge without a reload, SSE, `claude --bg` / attach, a run queue, and showing the usage-limit reset time (MVP §9 Later).
- A Stop button on board cards. The §8.1 wireframe has none.
- A list of every run on the task page. Only the latest run is shown.
- Disabling Run while another task's run is active (Q12).
- Dashboard tiles. 017 already counts runs.

## Open questions
- Q1: §4.3 says the header shows the plan, but not which cwd the check runs in. Default:
  - Use the same stripped env as runs.
  - Use cwd = the data dir. It's neutral, so no project's `.claude/settings.json` affects it.
- Q2: §8 shows only `Pro`. Default: `Claude: <subscriptionType capitalized> ✓`, so `max` → `Max`. If `subscriptionType` is missing or isn't a string, `Claude: subscription ✓`.
- Q3: docs don't say how often to check. Every page and every 3 s poll renders `base.html`, so checking every time means a `claude` process each poll. Default:
  - Cache the result for 60 s per process. Keep 012's 30 s timeout.
  - Each run's own check stays uncached (§4.3: "before every run").
  - `ponytail:` no lock, so two cold renders may both run the check.
- Q4: docs say "runs disabled" but not what the buttons do. Default:
  - While the badge is red, Run, Run next, and Retry have `disabled`.
  - Stop is never disabled.
  - The server's per-run check still has the final say.
- Q5: docs give "stalled · build" but no rule for when it applies. Default:
  - in_progress with a latest run (highest id) that is `running` → `● running · <stage>`.
  - in_progress with a latest run that isn't `running` (`failed`, `stopped`, or `succeeded`) → `stalled · <stage>` with Retry. That includes 013's stalled · rework after a refused rework spawn.
  - Stage NULL drops ` · <stage>`.
  - in_progress with no runs (a manual drag, or a standalone task after Request changes) → no run UI. A Run button there would turn a standalone task into a factory run.
  - Backlog → Run.
  - Review and Done cards show no run UI. On the task page, Stop still shows while a run is `running`.
- Q6: §3.2 step 4 says Run stays disabled "with that same hint", but nothing covers the `none` state. Default: show `run_task`'s 409 detail for the state (015's ux wording) next to the disabled Run next on the board, and next to Run/Retry on the task page.
- Q7: the wireframe shows `started 10:02`. Default: `HH:MM` in local time, on both the board and the task page.
- Q8: docs don't format "run status". Default: `run #<id> <status>`. A running run adds ` · started HH:MM`. A failed run adds `: <error>` when `error` is set. Jinja escapes it.
- Q9: §4.4 gives the takeover command without saying when to show it. Default:
  - Show it only when the latest run isn't `running`. Joining a live run is Later (§9). While a run is going, show `Stop the run to take over.`.
  - W is the stored absolute `worktree_path`. S is `runs.session_id`, which `finish_run` replaces with the result event's id.
  - Both are `shlex.quote`d, since I paste the line into a shell.
- Q10: §6.2 says the panel polls the JSON log route. §4.1 calls it a fragment. htmx can't render JSON without an extension. Default:
  - A short inline script polls the JSON route that §6.2 names.
  - The panel sits outside `#live`. Inside it, opening the `<details>` would pause the page poll (010 Q10), and each swap would reset the cursor.
  - It follows the run that was latest at page load. A run started elsewhere shows after a reload (`ponytail:` comment).
  - "Tail" means every item from `after=0`, with the box scrolled to the end.
- Q11: §8 says "every page header" but each template has its own `<header>`. Default: one `#claude-auth` line in `base.html` at the top of every page, above each page's own header.
- Q12: docs don't say whether to disable Run while another task's run is active. Default: leave it enabled. The 409 `run #N active` shows in the alert. The board header isn't re-polled, so a disabled state there would go stale.
- Q13: §8 item 4 puts Stop in the task header, and the §8.1 wireframe has none on cards. Default: Stop is on the task page only.
