# Round 1
## Changes
- pyproject.toml, uv.lock: `uv add markdown-it-py` (4.2.0). It's one of FACTORY.md's four runtime deps, and this is the first job that renders markdown.
- src/claude_factories/app.py:
  - A module-level `MD = MarkdownIt("js-default", {"html": False})` and a `markdown` Jinja filter returning `Markup(MD.render(text or ""))`. It's the only place agent text becomes Markup (Q13).
  - `TIMELINE`: one `UNION ALL` query over events, rounds, verdicts (by rowid), decisions, and comments. It builds each label in SQL using Q8's wording and orders by `created_at, kind, id` (§5.1, AC25).
  - `GET /tasks/{task_id}/review` (`round` query aliased, default `latest`). It uses `one_or_404` for the task joined to its project, `round_summaries` for the rows and header, and `round_or_404` to validate `?round=`. The one exception: `latest` on a task with no rounds gives a page with no selector instead of a 404 (AC11). It also runs one verdict-body query grouped by round n, and fetches the approver's latest decision by id (Q7).
  - `POST /tasks/{task_id}/comments`: `form_field("body_md")` → `post_comment(task_id, CommentBody(author="me", …))` → `hx_redirect("/tasks/{id}/review")`. Validation and 404s come from post_comment (Q9).
- src/claude_factories/templates/review.html: new page that extends base.html.
  - Header: project link (Q12), `<h1>#id title`, `#status` with label · stage (escalated in `<strong class="escalated">`), branch `<code>`, a GET round form with `onchange` submit and a `<noscript>` button, and `#files` with `N file(s) changed +A −D`.
  - Sections: `#description` (rendered markdown or `No description.`, plus the collapsed Spec `<details>`), `#rounds` (`round-<n>` blocks with chips, `no agent review` for standalone rounds without verdicts, and verdict `<details>` in reviewer order), `#approver`, and `#timeline` (`<ol>` with `<time datetime>`).
  - Comment form, or `Comments open once a round is submitted.` when there are no rounds.
- src/claude_factories/templates/base.html: review CSS for the meta row, round rows and chips, the one-line ellipsis verdict summary, and the timeline list. The escalated red reuses the existing declaration by adding `#status .escalated` to the `.escalated .badge` selector, so there's no new color literal.
- tests/test_review.py: new, one test per AC. Rows are seeded with SQL, as in test_agent_api.py.

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

## Open questions
- Q1–Q14 → used the spec's defaults as written. Details where the spec left choices open:
  - Chip short names follow the wireframe and AC16 (`sec ux ui code`), not the board's `co`.
  - The status label map is repeated in review.html, the same as project.html's `{% set labels %}`, so project.html stays untouched.
  - The approver block shows `round N` in muted text after `Approver · <DECISION>` (Q7).
  - `form_field` strips the comment body, so leading indentation in a markdown comment is lost. This matches the other form routes.
  - Page headings: `Conversation` (h2), then `Description`, `Rounds`, and `Timeline` (h3).

## Test output
```
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/007-review-conversation/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
349 passed, 1 warning in 42.13s
```
