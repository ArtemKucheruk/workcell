# Round 1
## Changes
- src/claude_factories/cli.py: `setup` subcommand copies `global_skills/<name>/SKILL.md` (read via `Path(__file__).parent`) to `Path.home()/.claude/skills/<name>/SKILL.md`, `mkdir(parents=True, exist_ok=True)`, overwrites only `SKILL.md`, prints `Wrote <path>` per file, `OSError` → `_fail("can't write <path>: <strerror>")`. No HTTP.
- src/claude_factories/cli.py: `run <target>` subcommand: a decimal id → `POST /api/tasks/{id}/run` (no repo needed); `next` → `main_checkout()` + project lookup → `POST /api/projects/{id}/run-next`; anything else → `p.error` (exit 2).
- src/claude_factories/cli.py: `task add --run` posts `/api/tasks/{id}/run` after the `Added` line. Shared `print_run(task_id, run_id)` prints `Run #… on #… → <URL>/tasks/<id>`. Factored the `GET /api/projects?path=` lookup into `project_at(main)`, now used by `task add`, `run next`, and `submit --new`.
- src/claude_factories/global_skills/factory-connect/SKILL.md: new. Frontmatter `name`/`description` only (Q8). Body: §3.1 flow, ask for workspace if `$ARGUMENTS` empty (Q5), test-command search and fallback (Q6), `fctl connect --workspace "<workspace>" --test-cmd "<test command>"`, show the `Connected …` line.
- src/claude_factories/global_skills/factory-submit/SKILL.md: new. Body: §7.4 flow, read `git status`/`git diff HEAD`/untracked files plus the conversation, new review vs next round by `$ARGUMENTS` or an earlier `Review #N` (Q7), `fctl submit --new --title "<title>" <<'EOF'` and `fctl submit <id> <<'EOF'`, never stage/commit, `404 no project at …` → suggest `/factory-connect <workspace>`.
- tests/conftest.py: autouse `isolated` also sets `HOME` to `tmp_path/"home"` (created), so no test touches the real `~/.claude`.
- tests/test_cli.py: `import re`, plus 015 tests appended. Existing tests unchanged.

Checked by hand: `uv build --wheel` ships `claude_factories/global_skills/*/SKILL.md`.

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

## Open questions
- Q1 → `Path.home() / ".claude"`; `CLAUDE_CONFIG_DIR` ignored.
- Q2 → `SKILL.md` overwritten every run; other files and other skills untouched.
- Q3 → one `Wrote <absolute path>` line per file, factory-connect first.
- Q4 → stop at first failure, `fctl: can't write <SKILL.md path>: <e.strerror>`, exit 1, no rollback. A missing shipped source file is a broken install and still raises.
- Q5 → skill asks for the workspace name and runs nothing until answered.
- Q6 → skill asks; if none, connect without `--test-cmd` and warn that Create factory needs one.
- Q7 → `$ARGUMENTS` is a task id, or this session printed `Review #N` for this change → `fctl submit <N>`; else `--new --title`.
- Q8 → frontmatter `name` and `description` only.
- Q9 → `Run #<run_id> on #<id> → <FCTL_URL>/tasks/<id>`.
- Q10 → current repo's project via `main_checkout()` + `GET /api/projects?path=`; prints the line with the reply's `task_id`.
- Q11 → `Added` line printed first; run error to stderr, exit 1; task stays in Backlog.
- Extra (not in spec): both skills say to ask me to start `fctl serve` on `can't reach …`, not start it; factory-submit says `HEAD has no commit yet` → tell me, don't commit.

## Test output
```
........................................................................ [ 76%]
........................................................................ [ 89%]
............................................................             [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/015-cli-and-skills/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
564 passed, 1 warning in 66.43s (0:01:06)
```
