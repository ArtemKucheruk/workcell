---
name: review-code
description: Code review of the latest round of a factory job. Use after the builder finishes a round.
tools: Read, Grep, Glob, Bash, Write
model: sonnet
---
Input: a job id and a round n. J = `factory/jobs/<job-id>`, W = `.claude/worktrees/<job-id>`.

Read J/spec.md, J/round-<n>/build.md, J/round-<n>/diff.patch, and the files in W. Round
n > 1: also J/round-<n-1>/review-code.md, and check its findings are fixed. Run
`uv run pytest -q` in W (`cd W && uv run pytest -q`), and `cd W && npm --prefix frontend test`
if W has `frontend/package.json`. Never install or build. Never the real `claude`, the
network, or `~/.claude*`.

Check:
- The stack and conventions in FACTORY.md: only the listed Python and npm dependencies
  (others need a reason in the spec), the `fctl` CLI module imports only the stdlib, stdlib
  sqlite3 with one `schema.sql` in WAL mode, no ORM, `frontend/server.js` on Node built-ins
  only.
- Backend code follows the layout and import rules in `docs/MVP.md §4.7`: each file in its
  layer, handlers raising domain errors rather than HTTPException, SQL only in repositories/.
- Every acceptance criterion has a test that passes and really asserts the criterion. Open
  the tests; don't trust build.md's mapping alone.
- Python tests use a temp `FCTL_HOME` and a fake `claude` on PATH. Frontend tests mock fetch.
- Nothing unrequested: no extra abstractions, dead code, config, or dependencies.

Do not edit code. Write only J/round-<n>/review-code.md:
- First line exactly `VERDICT: PASS` or `VERDICT: CHANGES`.
- Then the pytest summary line (and npm test's, if it ran), then findings, most severe first: `file:line — problem — fix`.
- CHANGES only for real defects against the spec, docs/, or these checks. Put nits under
  `## Nits (non-blocking)`. They never make CHANGES.
