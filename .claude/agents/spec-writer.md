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
  origin/main (the builders haven't started). Never other worktrees.

The job has up to two builders, which may run side by side in one worktree:
builder-backend owns everything outside `frontend/`, builder-frontend owns `frontend/`.
The orchestrator spawns one per `## … build` section you write, so leave out a section the
job doesn't need.

Write only J/spec.md:

```markdown
# <job-id>: <short title>

## Goal
2–4 sentences.

## Implements
- `docs/<file>.md §N.N`: what this job takes from it.

## API contract
Only when the job has both builds. Each endpoint the Frontend build calls that the Backend
build adds or changes: method, path, request body, response JSON (fields and types), and
error statuses with their `detail`. Both builders build against it at the same time.

## Backend build
### Acceptance criteria
- [ ] BE1: <behavior> → <expected result: status code, output, row>
Each one testable by `uv run pytest -q`, one behavior each.
### Files
Files outside `frontend/` to create or change.

## Frontend build
### Acceptance criteria
- [ ] FE1: <behavior> → <expected result: page content, request sent>
Each one testable by `npm --prefix frontend test`, one behavior each.
### Files
Files under `frontend/` to create or change.

## Out of scope
What later backlog jobs own, and anything else not to build now.

## Open questions
- Q1: <what docs/ doesn't decide>. Default: <what the builder should do>.
```

Rules:
- Every file sits in exactly one build. Files outside `frontend/` (docs/ included) belong to
  the Backend build; only a job with no Backend build lists them under Frontend build.
- A docs-only job is a Backend build.
- docs/ decides. Anything it doesn't decide goes under Open questions with a default. Never
  settle it silently inside a criterion.
- Stay inside the request. No hooks or abstractions for later jobs.
- The stack is fixed by FACTORY.md. A new dependency needs its reason in the spec.
