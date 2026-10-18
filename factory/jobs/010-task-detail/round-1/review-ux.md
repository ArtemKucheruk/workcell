VERDICT: PASS

No blocking findings. The §3 flows that touch this job work in the browser and in the terminal: a board card opens `/tasks/<id>`, the header and Review link work, the verdict chip opens its popover and Esc closes it, and a `fctl decide` shows up in the page through the 3 s poll.

## Nits (non-blocking)
- factory/jobs/010-task-detail/round-1/review-ux.md (outside the diff) — `fctl verdict 999 …`, `fctl approve 999` and `fctl show 999` print `fctl: 404 Not Found` with no id or next step, and `GET /api/tasks/999` returns `{"detail":"Not Found"}`. The HTML page reads `Task #999 not found`, which is right. The CLI and API 404 text predates this job and is not changed by it. Fix in a later job: `fctl: task #999 not found` and `"Task #999 not found"` in the API.
- src/claude_factories/templates/task.html:128 — the Q10 poll pause (`hx-trigger` filter on `:popover-open`) was not re-run here. The attribute is present, and the popover stayed open until Esc. Nothing else was observed.
- Open popover covers the round row's chips (native popover placement, visible in the screenshot). Acceptable for the default popover; no change needed.

## Checked
- `fctl connect` / `task add` / `submit --new` / `submit <id>` / `verdict` / `decide` / `stage`: exit 0 with the expected one-line output, and the Review URL is printed.
- Browser on `/tasks/2`: title escaped, description rendered, `Round 1 initial sec ✗ ux ✓ ui ✓ code · +1 −0`, a blank-body chip is a plain span, `no agent review` on the standalone round, `Build notes` collapsed, approver section appears on poll, history labels correct, escalated header red.
- `/tasks/999` in browser shows `Task #999 not found` with status 404. Review link and `/tasks/2/review` still render 200.
- `pytest -q tests/test_task_page.py tests/test_review.py` in the worktree: 67 passed.
