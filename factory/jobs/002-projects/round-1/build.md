# Round 1
## Changes
- src/claude_factories/db.py: `now()` returns UTC ISO 8601 with a `Z` suffix (Q14).
- src/claude_factories/app.py: `GET /api/workspaces`, `POST /api/projects/connect` (get-or-create workspace, upsert by path, null `test_cmd` keeps the stored one, Q5 validation as 422s with string details), `GET /api/projects?path=`. `factory_state()` runs `git -C <path> cat-file -e <branch>:SKILL.md` as an argument list with a 10 s timeout, then checks the disk. Git failures, a missing path, or a NUL byte count as "not committed". Pages: `/` lists workspaces, `/workspaces/{id}` has per-status counts via `COUNT … FILTER` and last activity = `MAX(created_at, MAX(tasks.updated_at))`, `/projects/{id}` is the Q11 stub. htmx form routes `POST /workspaces` and `POST /projects/{id}/workspace` parse bodies with `urllib.parse.parse_qs` and answer 204 + `HX-Redirect`. A `local_time` Jinja filter renders timestamps. Middleware unchanged.
- src/claude_factories/cli.py: `fctl connect --workspace W [--test-cmd C]`. `main_checkout()` uses `--git-common-dir`: if its basename is `.git`, the main checkout is the parent. Otherwise it falls back to `--show-toplevel`, then applies realpath (Q1). `default_branch()` is `origin/HEAD`, else the main checkout's `branch --show-current`, else exit 1 (Q2). Remote is `remote get-url origin` or null. It reuses `api()` and is stdlib only (`subprocess`).
- src/claude_factories/templates/workspace.html, project.html: new, both extend `base.html`. The workspace page has the table, the empty state, and the `+ Workspace` form (`required` plus `pattern=".*\S.*"`, so a whitespace-only name is also blocked natively). The project page has the `<name> · <workspace link>` heading, the path, and the move `<select>`.
- src/claude_factories/templates/index.html: the workspace list with project counts, or "No projects yet." (Q13).
- src/claude_factories/templates/base.html: a small `<style>` block with the system font, cell padding, `GrayText` for muted text and row borders, and right-aligned counts. No hard-coded colors (Q16).
- tests/conftest.py: the autouse fixture now isolates git (`GIT_CONFIG_GLOBAL` = empty file, `GIT_CONFIG_NOSYSTEM`, author and committer env) (Q17). Added a `git()` helper and a `repo` fixture (`git init -b main` + an empty commit).
- tests/test_projects.py: new, covers the API, factory state, pages, and form routes.
- tests/test_cli.py: `fctl connect` tests that reuse the `server` fixture.

## Criteria → tests
- AC1 → tests/test_projects.py::test_workspaces_empty
- AC2 → tests/test_projects.py::test_workspaces_with_counts_by_name
- AC3 → tests/test_projects.py::test_connect_creates_workspace_and_project
- AC4 → tests/test_projects.py::test_connect_existing_workspace
- AC5 → tests/test_projects.py::test_connect_rerun_updates
- AC6 → tests/test_projects.py::test_connect_null_test_cmd_keeps_stored
- AC7 → tests/test_projects.py::test_connect_rerun_moves_workspace
- AC8 → tests/test_projects.py::test_connect_strips_workspace
- AC9 → tests/test_projects.py::test_connect_invalid_field (5 cases)
- AC10 → tests/test_projects.py::test_find_project_keys
- AC11 → tests/test_projects.py::test_find_project_unknown
- AC12 → tests/test_projects.py::test_factory_ready
- AC13 → tests/test_projects.py::test_factory_uncommitted (untracked, other branch)
- AC14 → tests/test_projects.py::test_factory_none
- AC15 → tests/test_projects.py::test_factory_missing_path
- AC16 → tests/test_projects.py::test_workspace_page
- AC17 → tests/test_projects.py::test_workspace_page_counts
- AC18 → tests/test_projects.py::test_workspace_page_factory_state
- AC19 → tests/test_projects.py::test_workspace_page_last_activity
- AC20 → tests/test_projects.py::test_workspace_page_empty
- AC21 → tests/test_projects.py::test_workspace_page_unknown
- AC22 → tests/test_projects.py::test_workspace_page_has_new_workspace_form
- AC23 → tests/test_projects.py::test_new_workspace
- AC24 → tests/test_projects.py::test_new_workspace_existing_name
- AC25 → tests/test_projects.py::test_new_workspace_blank ("", "   ")
- AC26 → tests/test_projects.py::test_project_page
- AC27 → tests/test_projects.py::test_project_page_unknown
- AC28 → tests/test_projects.py::test_move_project
- AC29 → tests/test_projects.py::test_move_project_invalid (unknown project, unknown workspace, non-integer)
- AC30 → tests/test_projects.py::test_index_lists_workspaces
- AC31 → tests/test_cli.py::test_connect_clone
- AC32 → tests/test_cli.py::test_connect_without_test_cmd
- AC33 → tests/test_cli.py::test_connect_no_origin
- AC34 → tests/test_cli.py::test_connect_from_worktree
- AC35 → tests/test_cli.py::test_connect_from_subdirectory
- AC36 → tests/test_cli.py::test_connect_outside_repo
- AC37 → tests/test_cli.py::test_connect_detached_head
- AC38 → tests/test_cli.py::test_connect_requires_workspace

## Open questions
- Q1–Q17 → used the spec's defaults as written.
- A bare repo where `--show-toplevel` fails → the same `not inside a git repository` error as Q3. A bare repo has no checkout to connect.
- `fctl connect` prints the workspace stripped (`args.workspace.strip()`), the same way the server stores it. The body sends it as given and the server strips it.
- The empty state wraps the command in `<code>`: `No projects yet. Run <code>fctl connect --workspace <name></code> inside a repo.`
- Integers too big for SQLite in ids (`/workspaces/99999999999999999999`, or such a `workspace_id`) raise OverflowError → 500. Left as is: local only, nonsense input, and no data changes.
- A smoke run against a live `fctl serve` from this worktree printed `Connected claude-factories (personal) → …/projects/1`. The project resolved to the main checkout, with `factory: ready`.

## Test output
```
...............                                                          [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/002-projects/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
87 passed, 1 warning in 8.05s
```
