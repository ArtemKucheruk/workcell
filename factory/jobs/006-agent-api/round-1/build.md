# Round 1
## Changes
- src/claude_factories/app.py: `round_or_404(task_id, n)` pulled out of `round_diff` (n or `latest`, 005's 404 details, unknown task's bare 404 first); the diff route now uses it, unchanged behavior. New `PUT /api/tasks/{id}/rounds/{n}/verdicts/{reviewer}` (`INSERT OR REPLACE` on the `(round_id, reviewer)` key, `complete` counted in the same transaction), `POST /api/tasks/{id}/comments` (pairing/side/blank checks, then the path must be in the round's `round_files`), `POST /api/tasks/{id}/decision` (actor `approver`, latest round, always a new row), and `GET /api/tasks/{id}/context` (`?round=` / `?feedback=1`, 422 on both). Pydantic bodies `VerdictBody`, `CommentBody`, `DecisionBody`. One renderer, `context_md`, builds the Q5/Q6 block list. `Reviewer` Literal added and `REVIEWERS = get_args(Reviewer)` so the tuple isn't repeated; `NOSNIFF` header dict shared by the diff and context routes. None of the write routes touch `tasks` or `events`.
- src/claude_factories/cli.py: `show`, `spec`, `stage`, `verdict`, `comment`, `decide`, `round` subcommands on top of `api()` and `stdin_text()`; own `REVIEWERS`, `STAGES`, `DECISIONS` tuples for argparse `choices` (no import of app.py); `show`'s `--round`/`--feedback` in a mutually exclusive group; `comment` takes a required `<reviewer>` positional (Q11) and always sends `round: latest`, `side: new`.
- tests/test_agent_api.py: new, AC1–AC28.
- tests/test_cli.py: `server` handler also answers PUT and PATCH; 005's `Terminal` stand-in hoisted from inside `test_submit_skips_terminal_stdin` to module level so AC31/AC36/AC39 reuse it (that test's body and assertions are otherwise unchanged); AC29–AC39 appended.
- tests/conftest.py: untouched (the two test files share no new helper).

## Criteria → tests
- AC1 → tests/test_agent_api.py::test_verdict_on_latest
- AC2 → tests/test_agent_api.py::test_verdict_complete_counts
- AC3 → tests/test_agent_api.py::test_verdict_overwrites
- AC4 → tests/test_agent_api.py::test_verdict_on_round_number
- AC5 → tests/test_agent_api.py::test_verdict_body_optional
- AC6 → tests/test_agent_api.py::test_verdict_rejected
- AC7 → tests/test_agent_api.py::test_verdict_missing_round
- AC8 → tests/test_agent_api.py::test_verdict_any_task
- AC9 → tests/test_agent_api.py::test_comment_inline
- AC10 → tests/test_agent_api.py::test_comment_conversation
- AC11 → tests/test_agent_api.py::test_comment_on_round_number
- AC12 → tests/test_agent_api.py::test_comment_rejected
- AC13 → tests/test_agent_api.py::test_comment_missing_round
- AC14 → tests/test_agent_api.py::test_decision_approve
- AC15 → tests/test_agent_api.py::test_decision_body_optional
- AC16 → tests/test_agent_api.py::test_decision_appends
- AC17 → tests/test_agent_api.py::test_decision_rejected
- AC18 → tests/test_agent_api.py::test_decision_missing_round
- AC19 → tests/test_agent_api.py::test_writes_leave_task_unchanged
- AC20 → tests/test_agent_api.py::test_writes_need_fctl_header
- AC21 → tests/test_agent_api.py::test_context_one_round
- AC22 → tests/test_agent_api.py::test_context_everything
- AC23 → tests/test_agent_api.py::test_context_latest
- AC24 → tests/test_agent_api.py::test_context_decisions
- AC25 → tests/test_agent_api.py::test_context_fresh_task
- AC26 → tests/test_agent_api.py::test_context_feedback
- AC27 → tests/test_agent_api.py::test_context_no_feedback
- AC28 → tests/test_agent_api.py::test_context_errors
- AC29 → tests/test_cli.py::test_show
- AC30 → tests/test_cli.py::test_spec
- AC31 → tests/test_cli.py::test_spec_empty
- AC32 → tests/test_cli.py::test_stage
- AC33 → tests/test_cli.py::test_verdict
- AC34 → tests/test_cli.py::test_comment
- AC35 → tests/test_cli.py::test_decide
- AC36 → tests/test_cli.py::test_agent_commands_skip_terminal_stdin
- AC37 → tests/test_cli.py::test_round
- AC38 → tests/test_cli.py::test_round_without_rounds
- AC39 → tests/test_cli.py::test_agent_usage_errors

## Open questions
- Q1 → default used: one `round_or_404` for diff, verdict, comment, decision (always `latest`), and context; unknown task's bare 404 first.
- Q2 → default used: path takes `n` or `latest`, `body_md` defaults to `''`, re-post replaces verdict/body/created_at, `complete` = rows on that round / 4, no status/stage/run checks, no task or events writes.
- Q3 → default used. Unspecified 422 texts picked: `path and line go together`, `side needs a path`. `line` is also capped below 2**63 so an oversized number is a 422, not a SQLite OverflowError 500. Body-shape 422s run before the round lookup; the path-in-round 422 after it.
- Q4 → default used: `APPROVE`/`ESCALATE` only, actor `approver`, latest round, every POST a new row, no 4/4 precondition.
- Q5 → default used, exactly as listed; `## Spec` shows `_No spec yet._` only when `spec_md` is NULL (an empty string gives a bare heading).
- Q6 → default used: my latest CHANGES_REQUESTED by id; only my comments on that decision's round.
- Q7 → default used: `feedback` is a FastAPI bool query param, so `?round=1&feedback=0` is allowed; both true → 422 checked before the task lookup.
- Q8 → default used, formats as listed.
- Q9 → default used; `--line` is an int but not checked ≥ 1 in the CLI (the server's 422 covers it).
- Q10 → default used.
- Q11 → default used: `fctl comment <id> <reviewer> --path P --line L`.

## Test output
```
.......................                                                  [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/006-agent-api/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
311 passed, 1 warning in 41.21s
```
