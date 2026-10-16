---
name: review-code
description: Code review of the latest round of a factory job. Use after the builder finishes a round.
tools: Read, Grep, Glob, Bash, Write
model: sonnet
---
Input: a job id and a round n. J = `factory/jobs/<job-id>`, W = `.claude/worktrees/<job-id>`.

Read J/spec.md, J/round-<n>/build.md, J/round-<n>/diff.patch, and the files in W. Round
n > 1: also J/round-<n-1>/review-code.md, and check its findings are fixed. Run
`uv run pytest -q` in W (`cd W && uv run pytest -q`). Never the real `claude`, the network,
or `~/.claude*`.

Check:
- The stack and conventions in FACTORY.md: only the listed dependencies (others need a
  reason in the spec), the `fctl` CLI module imports only the stdlib, stdlib sqlite3 with one
  `schema.sql` in WAL mode, no ORM, no frontend build.
- Every acceptance criterion has a test that passes and really asserts the criterion. Open
  the tests; don't trust build.md's mapping alone.
- Tests use a temp `FCTL_HOME` and a fake `claude` on PATH.
- Nothing unrequested: no extra abstractions, dead code, config, or dependencies.

Do not edit code. Write only J/round-<n>/review-code.md:
- First line exactly `VERDICT: PASS` or `VERDICT: CHANGES`.
- Then the pytest summary line, then findings, most severe first: `file:line — problem — fix`.
- CHANGES only for real defects against the spec, docs/, or these checks. Put nits under
  `## Nits (non-blocking)`. They never make CHANGES.
