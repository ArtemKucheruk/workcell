VERDICT: PASS

I ran `fctl serve` and `fctl connect` from the worktree against a temp `FCTL_HOME`, with no real `claude`.

- `fctl connect --workspace personal --test-cmd "pytest -q"` printed `Connected r (personal) → http://127.0.0.1:45991/projects/1` and exited 0, matching the §3.1 format. A rerun with `--workspace " x "` moved the project to workspace `x` and created it on the spot.
- `fctl connect` with no `--workspace` printed usage to stderr and exited 2.
- Outside a git repo it printed `fctl: not inside a git repository: <cwd>` to stderr and exited 1.
- With a detached HEAD and no `origin/HEAD` it printed the Q2 message to stderr and exited 1.
- `GET /api/projects?path=/nope` returned 404 `{"detail":"no project at /nope"}`.
- `/api/workspaces` was ordered by name with project counts.
- The pages `/`, `/workspaces/1` and `/projects/1` returned 200. The empty state, the `+ Workspace` form, and the move `<select>` with the current workspace selected are all as the spec describes.

## Nits (non-blocking)
- src/claude_factories/cli.py:42 — `_git` raises a traceback if `git` isn't on PATH (`FileNotFoundError`). MVP §10 assumes git is present, so this is acceptable. Catching `OSError` and calling `_fail("git not found")` would be friendlier.
- I did not run the htmx form routes (`POST /workspaces`, `POST /projects/{id}/workspace`) or the unreachable-server message against the live server. The tests in `tests/test_projects.py` cover the form routes, and the unreachable-server path is 001's code.
