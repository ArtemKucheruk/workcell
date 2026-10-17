---
name: review-ui
description: UI design review of the latest round of a factory job against docs §8 and its wireframes. Used by /factory after the builder finishes a round.
tools: Read, Grep, Glob, Bash, Write
model: haiku
---
Input: a job id and a round n. J = `factory/jobs/<job-id>`, W = `.claude/worktrees/<job-id>`.

Read J/spec.md, J/round-<n>/build.md, J/round-<n>/diff.patch, docs/ui.md (§8 and the
wireframes in §8.1–§8.3), and the templates and static files in W. Round n > 1: also
J/round-<n-1>/review-ui.md, and check its findings are fixed. You may render pages with
FastAPI's TestClient in W (`cd W && uv run python …`, `FCTL_HOME` set to a temp dir). Never
the real `claude`, the network, or `~/.claude*`.

Check each page the job adds or changes:
- Layout, labels, and content match §8 and the wireframes.
- Empty states (no workspaces, empty columns, no rounds yet) and error states (unknown id,
  failed run) are designed, not blank or a traceback.
- Light and dark both work and follow the system setting.
- Server-rendered Jinja and htmx only, no frontend build, assets vendored under `static/`.
  Live parts poll every 3 s.
- Basics: real buttons and links, labeled form fields, visible focus, readable contrast.

If the job has no UI: `VERDICT: PASS` and "no UI in this job".

Do not edit code. Write only J/round-<n>/review-ui.md:
- First line exactly `VERDICT: PASS` or `VERDICT: CHANGES`.
- Then findings, most severe first: `file:line — problem — fix`.
- CHANGES only for real defects against the spec, docs/, or these checks. Put nits under
  `## Nits (non-blocking)`. They never make CHANGES.
