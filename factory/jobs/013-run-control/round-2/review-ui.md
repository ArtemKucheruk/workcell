VERDICT: PASS

The only UI change in round 2 is the Request changes form's post-write refusal and the one-line `{{ refused }}` in `templates/review.html`. Round 1's ux CHANGES finding is fixed. Checked in a headless browser against a live `fctl serve` (seeded factory task #1 in review · human_review, fake `claude` returning `{"authMethod":"console"}`):

- Post-write refusal (Request changes, Summary "Make the limit configurable"): the header swaps in as "In progress · rework", the Summary and both buttons are disabled, and the alert reads "not on subscription auth" in red. The DB shows the task at in_progress · rework with one CHANGES_REQUESTED decision and no run row. Same result from the Files tab (`?round=1&tab=files`): the swapped header keeps the round and the hidden `tab=files` input.
- Pre-write refusal (a run active on another task): the alert reads "run #99 active", the header still reads "Review · waiting on you", the buttons stay enabled, and no decision is written.
- Light and dark: both render, following the system setting (`set-color-scheme`). The alert and disabled states read clearly in both.
- Focus: Tab moves to the Conversation tab with a visible focus ring.
- Console: only the pre-existing favicon.ico 404 on every page. No errors from the job's pages.
- Error states: an unknown review page renders the designed "Not found · Claude Factories" page with "Task #999 not found". Not a traceback.
- Live polling: the review page has no polling in this job, so none is required here.

## Nits (non-blocking)
- `templates/review.html` (Request changes form) — after a post-write refusal the typed Summary is dropped, because the header is swapped. The disabled box is empty and the user can't see what they sent. Keep the summary in the swapped header, or leave it as is since the task is now in rework.
- `app.py` `request_changes_form` (the `review_context` swap) — the Timeline and Rounds below the header are not refreshed after the refusal, so the new "in_progress · rework" event shows only after a reload. The header is the spec'd status, so this is fine. A one-line note in the alert would make it clearer.
- `app.py` `request_changes_form` for an unknown task — the alert shows the raw `{"detail":"Not Found"}` text (from 009's `decide_review` path). Round 1's nit. Name the task (`Task #999 not found`) like the review page does.
