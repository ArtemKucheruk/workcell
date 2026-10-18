# Round 2
## Changes
- docs/claude-code.md: §7.2's `fctl comment` row is now `fctl comment <id> <reviewer> --path P --line L`, and the §7.3 security template's example is `fctl comment <id> security --path <file> --line <n>`. The docs now match the CLI that Q11 chose. No code changed this round.

## Criteria → tests
Unchanged from round 1:
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

## Review findings
- ux · docs/claude-code.md:35 and :89 still show `fctl comment <id> --path P --line L`, which the CLI rejects → fixed: both lines now include the reviewer positional (Q11).
- ux nit · a Pydantic 422 list prints as raw JSON → not fixed: 005's `test_api_error_detail_fallbacks` (Q8) pins that output (`fctl: 422 [{"loc": "x"}]`), so changing it would break an existing test. An argparse `--line >= 1` check would only cover one field.
- ux nit · an unknown task prints `fctl: 404 Not Found` → not fixed: Q1 asks for the bare 404, and 005's diff route already behaves this way.
- ux nit · `body_md must not be blank` gives no next step → not fixed: Q3 sets the text, and AC36 requires `fctl comment` to send `""` from a terminal, so the CLI can't block it first.
- ux nit · `?round=` (empty) → `#1 has no round ` → not fixed: it's the shared `round_or_404` lookup from 005, it's a 404 that writes nothing, and `fctl show --round` only sends an int.
- security nit · the API accepts `author: "me"` from any fctl-header caller → not fixed: matches Q3/Q11. It's for 012's allowlist review.
- security nits · ANSI escapes are passed through by `fctl show`, and the test helper `count()` builds SQL with an f-string → not fixed: Q5 says to pass text through as is, and the table names in `count()` are constants.
- code nit · `line < 2**63` cap goes beyond the spec → kept: it turns a SQLite OverflowError 500 into a 422 (noted in round 1).

## Open questions
- Q1–Q11 → same defaults as round 1 (see round-1/build.md).

## Test output
```
.......................                                                  [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/006-agent-api/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
311 passed, 1 warning in 41.69s
```
