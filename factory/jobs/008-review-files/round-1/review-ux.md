VERDICT: PASS

Checked against the round 1 build in W (`.claude/worktrees/008-review-files`) on a temp FCTL_HOME and a scratch repo. The full suite passes (423). Real server run: `fctl submit --new` and `fctl submit <id>` both print the documented format. `?tab=files` returns 200, with tabs, tree, per-file headers, one anchor per line number, CRLF stripped, `<script>` escaped, and `data-lang` set. The inline form renders with the right hidden inputs and Cancel link. Posting returns 204 with HX-Redirect to the files tab anchor, and the comment shows in its row. Missing X-Requested-By gives 403, round 9 gives 404 ("#1 has no round 9"), and a bad line or blank body gives 422. A non-matching line gives no form. The Conversation tab has no file tree, diff table, or highlight script. Round 1 and round 2 files and the default latest-round view are correct.

## Nits (non-blocking)
- `file:line` — the 422 `detail` is pydantic wording, e.g. `line: Input should be a valid integer, unable to parse string as an integer` — readable, but a plainer message such as `line must be a whole number` would match the rest of the UI. Fix: optional, map the message in the ValidationError handler.
