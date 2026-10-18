VERDICT: CHANGES

- factory/jobs/013-run-control (app.py:1414-1417, request_changes_form) — when run_task refuses after decide_review (Q12: "not on subscription auth", "factory isn't committed", or a run that started in the gap), the form gets the 409 and the page is not refreshed. Walked in the browser: task #1 in review, subscription auth refused, Request changes → the alert says "not on subscription auth", but the page still reads "Review" with Request changes and Approve enabled. The API shows in_progress · rework with a new CHANGES_REQUESTED decision (decisions went 4 → 5). A second click records another decision. The user has no visible result and a dead-end form. — Keep the 409 detail in .form-error, but make the page show the state the decision moved to (for example, send HX-Refresh with the refused response, or swap the review header), so the page reads "In progress · rework" with the buttons disabled. Re-walk the browser to confirm. A plain request-changes refusal before any write (run active, 409 `run #N active`) is fine: the page stays as it was and the alert shows the detail.

## Nits (non-blocking)
- app.py:126 (one_or_404's default detail) — an unknown task or run gives `404 Not Found`, and `fctl rework 999` prints `fctl: 404 Not Found`. Naming the thing (`run #999 not found`, `task #999 not found`) would say what went wrong. Affects stop_run too (app.py:623).
- `?after=-1` → 422 returns FastAPI's raw list of validation objects. AC17 only asks for 422; a readable message would be nicer.
- `run #N active` and `not on subscription auth` are the spec's exact text (§4.4, AC21) and give no next step. The API body must stay as spec'd; fctl could add a hint on stderr, for example "wait for it to finish or stop it".
- After SIGINT on `fctl serve`, the stopped runs keep `exit_code` NULL, because the server exits before the exit thread writes it. Per Q4 this is by design, and no UI shows it in this job.
- The favicon 404 on every page is pre-existing and not from this job.

## Walked (for the record)
- Browser: review page → Request changes with a summary → page shows "In progress · rework", the form disables, a rework run #4 succeeded with prompt `/factory 1` in the stored worktree and a new session_id.
- Browser: Request changes while run #3 was active → alert "run #3 active", no decision written.
- CLI: `fctl rework 1 "again"` → `#1: in_progress · rework`, exit 0. Refusals (`run #3 active`, `not on subscription auth`) go to stderr, exit 1, stdout empty.
- CLI: `fctl rework` on a standalone task → `#3: in_progress · rework`, no run row.
- API: stop → 200 `{"id":3,"status":"stopped"}`; second stop → 409 `run #3 is not running`; no header → 403; unknown → 404.
- API: Retry after stop and after restart → 202, same worktree.
- Shutdown (SIGINT) stopped run #7 and its `sh` and `sleep 60` group; SIGKILL then restart marked run #8 `failed` with `app restarted`, left the task alone, and sent no signal.
- Log endpoint on the spec's fixture log: `after=0` and `after=3` match AC12 and AC13 exactly.
