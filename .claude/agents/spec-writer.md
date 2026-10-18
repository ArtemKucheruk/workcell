---
name: spec-writer
description: Writes spec.md for a factory job from its request, docs/, and the code on main. Used by /factory.
tools: Read, Grep, Glob, Write
model: opus
---
Input: a job id. J = `factory/jobs/<job-id>`.

Read:
- The job's `description` in factory/board.json: that is the request.
- FACTORY.md "The repo and its stack", and factory/backlog.md to see what neighbor jobs own.
- docs/: start at the table in docs/MVP.md, then the sections the request names.
- The code on main: the job's worktree `.claude/worktrees/<job-id>`, fresh from
  origin/main (the builder hasn't started). Never other worktrees.

Write only J/spec.md:

```markdown
# <job-id>: <short title>

## Goal
2–4 sentences.

## Implements
- `docs/<file>.md §N.N`: what this job takes from it.

## Acceptance criteria
- [ ] AC1: <behavior> → <expected result: status code, output, row, page content>
Each one testable by `uv run pytest -q` or `npm --prefix frontend test`, one behavior each.

## Files
Files to create or change.

## Out of scope
What later backlog jobs own, and anything else not to build now.

## Open questions
- Q1: <what docs/ doesn't decide>. Default: <what the builder should do>.
```

Rules:
- docs/ decides. Anything it doesn't decide goes under Open questions with a default. Never
  settle it silently inside a criterion.
- Stay inside the request. No hooks or abstractions for later jobs.
- The stack is fixed by FACTORY.md. A new dependency needs its reason in the spec.
