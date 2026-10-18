# Round 2
## Changes
- src/claude_factories/app.py `find_project`: the 404 detail is now `no project at <path>; in that repo, run fctl connect --workspace <name>`. `fctl task add`, `run next`, and `submit --new` all show it. The `no project at …` prefix the factory-submit skill matches is kept.
- src/claude_factories/app.py `run_task`: an unknown task now gets the detail `no task #<id>`, so `fctl run 999` prints `fctl: 404 no task #999`. `run-next` goes through the same function.
- src/claude_factories/app.py `run_task`: the factory 409 now names the next step. If the factory is only on disk: `factory isn't committed on main: on main, run git add .claude/skills/factory .claude/agents && git commit -m "Add factory"` (reuses `COMMIT_HINT`). If there's no factory: `… : Create factory on the project board, then commit it on main`.
- src/claude_factories/cli.py `task_add`: the `Added` line is printed with `flush=True`, so a refused run's stderr comes after it even when stdout is a pipe (ux nit).
- src/claude_factories/global_skills/factory-connect/SKILL.md: before running `fctl connect`, show the chosen test command and the file it came from, since runs execute it (security nit).
- src/claude_factories/global_skills/factory-submit/SKILL.md: no line of the description or build notes may be exactly `EOF` (security nit).
- tests/test_projects.py `test_find_project_unknown` (002 AC11), tests/test_runs.py `test_refused_without_factory` (012 AC19): expected details updated to the new text. tests/test_runs.py `test_unknown_task_and_missing_header` (012 AC24) now also asserts `{"detail": "no task #999"}`. tests/test_cli.py is unchanged since round 1.

## Criteria → tests
- AC1 → tests/test_cli.py::test_setup_writes_skills
- AC2 → tests/test_cli.py::test_setup_output
- AC3 → tests/test_cli.py::test_setup_is_offline
- AC4 → tests/test_cli.py::test_setup_connect_skill
- AC5 → tests/test_cli.py::test_setup_submit_skill
- AC6 → tests/test_cli.py::test_setup_overwrites_only_skill_md
- AC7 → tests/test_cli.py::test_setup_cant_write
- AC8 → tests/test_cli.py::test_run_task
- AC9 → tests/test_cli.py::test_run_task_outside_repo
- AC10 → tests/test_cli.py::test_run_next
- AC11 → tests/test_cli.py::test_run_next_outside_repo
- AC12 → tests/test_cli.py::test_run_next_empty_backlog
- AC13 → tests/test_cli.py::test_run_refused
- AC14 → tests/test_cli.py::test_run_usage_errors
- AC15 → tests/test_cli.py::test_task_add_run
- AC16 → tests/test_cli.py::test_task_add_run_refused
- AC17 → tests/test_cli.py::test_task_add_without_run (+ 003's test_task_add* unchanged)
- AC18 → full `uv run pytest -q`, incl. tests/test_cli.py::test_cli_imports_only_stdlib

## Review findings
- ux · `no project at …` names no next step → fixed with a server-side detail (`find_project`). It isn't a CLI hint because AC17 and the spec require 003's `test_task_add_unconnected` and the existing `test_submit_new_unconnected` to pass unchanged, and both pin fctl's exact stderr. The server-side fix follows the existing `create_factory` 409 (`no test command: in the repo, run fctl connect …`). It changes 002's pinned detail in test_projects AC11.
- ux · `fctl run 999` → `404 Not Found` → fixed in `run_task` (`no task #999`). Not changed: the other bare `one_or_404` calls the reviewer listed (app.py `get_task`, `round_or_404`, `task_context`). 007's test_review AC3 pins `/api/tasks/999` → `{"detail": "Not Found"}`, and `round_or_404`'s bare 404 is 005 Q7 / 006 Q1. Those belong to other jobs, and agents call them, not me. I didn't change the default in the shared `one_or_404` either: it can't name the entity, and it would break the pinned 404.
- ux · factory 409 gives no next step → fixed with two messages, one per factory state: on disk gets the commit command, none gets Create factory first. The `factory isn't committed on <branch>` prefix is kept. Changes 012's pinned AC19 text.
- ux nit · stdout/stderr order when piped → fixed (`flush=True`).
- ux nit · favicon 404, Run next button disabled → not fixed: outside 015 (the app shell; 014's button).
- security nit · test command comes from repo files → fixed: the skill shows the command and its source before connecting.
- security nit · a line that is exactly `EOF` ends the heredoc early → fixed: the skill forbids it for both heredocs.
- code nit · `usage_error=p.error` is indirect → kept: it's how `submit` already does it.
- code nit · extra skill notes beyond the spec → kept, as flagged in round 1.

## Open questions
- Q1–Q11 → same defaults as round 1.
- Q12 (new) → error hints live in the server's `detail`, since that's the one place all fctl callers share and the CLI's stderr format is pinned. If you'd rather keep earlier jobs' details untouched, revert the three app.py messages: the CLI and skills don't depend on them.

## Test output
```

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
564 passed, 1 warning in 67.40s (0:01:07)
```
