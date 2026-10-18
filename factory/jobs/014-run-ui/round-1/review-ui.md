VERDICT: PASS

No blocking findings. Checked in headless Chromium against the worktree server (fake `claude` on PATH, never the real binary) with seeded tasks in each state:

- Board (`/projects/1`): Backlog `Run`, `● running · build` + `started HH:MM`, `stalled · build` + `Retry`, stage-less `build` card with no run UI, Review and Done cards with no buttons, enabled `Run next ▶`. Matches §8.1 and the wireframe. Light and dark screenshots both correct.
- Board, uncommitted factory (second project): `Run next` and card `Run` disabled, header shows the `uncommitted` hint. Task page (`/tasks/8`) shows the same hint and a disabled `Run`.
- Board, API-key login (`{"authMethod":"console"}`): badge is red `API key — runs disabled` in light and dark, and `Run next`, `Run`, and `Retry` are disabled. Stop is not disabled (checked on `/tasks/2`).
- Task page: running task shows `Stop` and `run #N running · started HH:MM` with `Stop the run to take over.`. Failed task shows `Retry`, `run #N failed: exit code 3`, and the `cd … && claude --resume …` line. Backlog task shows `Run`. Review and done tasks with a succeeded run show no run buttons, only the status.
- Run flow: backlog `Run` → `POST /api/tasks/1/run` 202, board refreshes. `Run next` with an empty backlog → `backlog is empty` in the board alert. `Stop` → `POST /api/runs/6/stop` 200, page reloads to `run #6 stopped` with `Retry` and takeover.
- Run log: `<details id="run-log">` collapsed. Expanding it fetches `/api/runs/2/log?after=0` and shows lines as text. A live run polls `/log?after=` about every 3 s, and the board and task page poll every 3 s. Run error `<script>alert(1)</script>` renders as `&lt;script&gt;…`, with no raw `<script>alert` in the markup.
- Badge: exactly one `#claude-auth` with `Claude: Pro ✓` on `/`, `/workspaces/1`, `/projects/1`, `/projects/1/code`, `/tasks/2`, `/tasks/4/review`, and the 404 at `/tasks/999` (404 page renders cleanly in both schemes).
- Basics: real `<button>`s and links, the run status is in a labeled alert area, keyboard Tab shows the default focus ring, dark mode follows the system setting, and the page console has no errors (only a favicon 404).

## Nits (non-blocking)

- Favicon: every page requests `/favicon.ico` and gets a 404, which the browser logs as a console error. Likely pre-existing across pages. Fix: add a `<link rel="icon" href="data:,">` in `base.html`, or serve an icon.
- Disabled-button contrast in dark mode (`Run`, `Retry`, `Run next` are dim grey on `#111`). That is the browser's disabled style and it is readable, so this is only a note.
- The task page gives no inline reason when `Run` or `Retry` is disabled for the API-key state. The red badge in the header explains it, as the spec allows, so there is nothing to fix.
