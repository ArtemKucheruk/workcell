VERDICT: PASS

No blocking findings. The round 1 CHANGES finding is fixed: a Request changes refused after the decision now swaps in the header and disables the form.

Walked in the browser (headless, server on a temp FCTL_HOME, no `claude` on PATH):
- Review page, Request changes with a summary, auth refused: the header swapped to "In progress · rework", Summary and both buttons disabled, alert reads "not on subscription auth". DB: one CHANGES_REQUESTED decision, task in_progress · rework, no runs row.
- Review page, Request changes while run #7 is active: alert reads "run #7 active", no decision, page unchanged. The pre-write refusal still shows the plain alert.

Checked through curl and the CLI:
- Stop without X-Requested-By → 403 `X-Requested-By: fctl header required`.
- Stop on a running row with pid NULL → 200 `{"id":7,"status":"stopped"}`. Stop again → 409 `run #7 is not running`. Unknown run → 404 `run #999 not found`.
- Log on the spec fixture: whole file → next 8 with the six AC12 items; `?after=3` → next 8 with the last four items (matches AC13).
- Log `?after=-1` → 422. Log for a run with no log file → 200 `{"next":0,"lines":[]}`.
- `fctl rework 1 again` (task not in review) → stderr `fctl: 409 #1 is not in review`, exit 1, stdout empty. `fctl rework 1 ""` → stderr `fctl: 422 body_md must not be blank`, exit 1. `fctl rework 999 x` → stderr `fctl: 404 Not Found`, exit 1.
- Server log has no 500s or tracebacks.

## Nits (non-blocking)
- `fctl rework 999 x` prints `fctl: 404 Not Found`, and the task 404s from 009's `decide_review` / `request_changes` still say only "Not Found". Naming the task (`task #999 not found`) would match the run routes. Left out of scope in round 2, so this is a follow-up, not a blocker.
- `?after=-1` returns FastAPI's raw validation list as the detail. AC17 only asks for 422, so this is fine.
- The refusal alert gives no next step, as round 1 noted. Spec text, so fine.
- The spec says no template change, but review.html gained `{{ refused }}`. The build notes justify it, and it is empty on every other render.
