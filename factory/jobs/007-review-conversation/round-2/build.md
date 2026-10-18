# Round 2
## Changes
- src/claude_factories/app.py:
  - New `page_not_found` handler on Starlette's `HTTPException`. A GET that 404s outside `/api/` now renders `error.html` with status 404 and the exception's detail. Everything else is still handled by FastAPI's `http_exception_handler`, so the JSON API keeps its JSON 404s: every `/api` route, every non-GET request, and every other status. This applies app-wide, so `/projects/999`, `/workspaces/999`, and unknown routes get the same page (ui review).
  - `one_or_404` takes an optional `detail` (default None, which gives the same bare 404 as before). `review_page` passes `Task #<id> not found`. `round_or_404` already gives `#<id> has no round <n>`.
- src/claude_factories/templates/error.html: new. It extends base.html and shows the `Claude Factories` home link in the same top-line spot as the board, and `<h1>{{ detail }}</h1>`, autoescaped.
- tests/test_review.py: AC3 and AC10 now go through a `not_found_page()` helper. It checks for a 404 with `text/html`, the home link, and the `<h1>` message. AC3 also covers `/projects/999` and an unknown route, and checks that `/api/tasks/999` still returns the JSON `{"detail": "Not Found"}`.

## Criteria → tests
- AC1 → tests/test_review.py::test_page_renders
- AC2 → tests/test_review.py::test_title_escaped
- AC3 → tests/test_review.py::test_unknown_task_404
- AC4 → tests/test_review.py::test_project_link
- AC5 → tests/test_review.py::test_status_stage
- AC6 → tests/test_review.py::test_branch
- AC7 → tests/test_review.py::test_round_selector
- AC8 → tests/test_review.py::test_round_param
- AC9 → tests/test_review.py::test_files_changed
- AC10 → tests/test_review.py::test_unknown_round_404
- AC11 → tests/test_review.py::test_no_rounds_header
- AC12 → tests/test_review.py::test_description_markdown
- AC13 → tests/test_review.py::test_empty_description
- AC14 → tests/test_review.py::test_spec_details
- AC15 → tests/test_review.py::test_raw_html_off
- AC16 → tests/test_review.py::test_round_rows
- AC17 → tests/test_review.py::test_chip_titles
- AC18 → tests/test_review.py::test_verdict_bodies
- AC19 → tests/test_review.py::test_no_agent_review
- AC20 → tests/test_review.py::test_no_rounds_section
- AC21 → tests/test_review.py::test_approver_latest
- AC22 → tests/test_review.py::test_no_approver
- AC23 → tests/test_review.py::test_timeline_order
- AC24 → tests/test_review.py::test_timeline_event_labels
- AC25 → tests/test_review.py::test_timeline_ties
- AC26 → tests/test_review.py::test_timeline_bodies
- AC27 → tests/test_review.py::test_comment_form
- AC28 → tests/test_review.py::test_comment_post
- AC29 → tests/test_review.py::test_comment_blank
- AC30 → tests/test_review.py::test_comment_refused
- AC31 → tests/test_review.py::test_comment_in_timeline

## Review findings
- ui · bare JSON 404 on `/tasks/999/review`, `?round=99`, and `?round=abc` (CHANGES) → fixed with an app-wide HTML 404 page for page GETs, carrying the specific message (`Task #999 not found`, `#2 has no round 99`) and a link home. The link goes to the start page, not the project, because an unknown task has no project to link to.
- ui nit · a whitespace-only comment gets a silent 422 → not changed. Q9 accepts this and matches 004's form.
- ui nit · no polling → not changed. Q10 chose no polling on purpose.
- ui/ux nit · ellipsis on `details.verdict summary` → not changed. `summary` is `display: list-item` in Chrome and `block` in Safari. Both are block containers, so `text-overflow` applies. Forcing `display: block` would drop Chrome's disclosure marker.
- ui nit · the textarea has only an `aria-label` → not changed. The wireframe shows a placeholder-only box, and the accessible name is set.
- ux nit · JSON 404s on page routes → fixed (see above).
- ux nit · the `async` comment route calls the sync `post_comment` → not changed. It's the same pattern as `add_task_form`, and a single local user won't notice.
- security nit · markdown images load remote URLs → not changed. §4.5 requires only raw HTML off, and the reviewer pointed this to a later job (`MD.disable("image")`).
- security nit · no size cap on `form_field` bodies → not changed. The code predates this job and is shared by every form route.
- code nit · the status label map is repeated from project.html → not changed. The spec keeps project.html untouched.

## Open questions
- Q1–Q14 → spec defaults, as in round 1.
- New: the error page's only link is home (`/`), where the workspace list leads to the project. A future job can add a back link that depends on context.

## Test output
```
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/007-review-conversation/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
349 passed, 1 warning in 43.87s
```
