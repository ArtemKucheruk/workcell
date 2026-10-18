VERDICT: PASS

Checked against spec.md (AC1–AC25), docs/MVP.md §3.2 and §4.4, and docs/claude-code.md §7.2 and §7.4, with the worktree at .claude/worktrees/011-factory-templates and FCTL_HOME in a temp dir. I ran a local server on port 4601 (port 4545 was already in use by another process, which I left alone) and exercised the flows:
- JSON API: 403 without X-Requested-By, 404 for an unknown project, 200 with the 8 written paths and the commit hint on a fresh repo, 200 with all skipped on a rerun, 409 for a missing test command, 409 for a symlink that escapes the repo (nothing written outside it), 409 `is not a directory` for a deleted path.
- Form route and board: the header shows the Create factory form in state none; posting without the header gives 403; a fresh post lists "Wrote 8 files" and the hint; a rerun lists "Skipped 8 existing files"; overwrite=on writes all 8; the no-test-command case returns a 200 fragment with `role="alert"`.
- After running the hinted `git add` and `git commit`, the state is `ready`, and `git status` is clean.
- Rendered files contain no template leftovers, and `make check` appears in builder.md, review-code.md, and SKILL.md.
- Every `fctl` subcommand and argument in the templates matches cli.py (`show --round/--feedback`, `stage` choices, `verdict`/`comment` reviewer choices, `decide`, `round`).
- `pytest tests/test_factory.py tests/test_board.py`: 62 passed.

## Nits (non-blocking)
- W/src/claude_factories/app.py:263 — unknown project gives `{"detail":"Not Found"}` (JSON) and `<p role="alert">Not Found</p>` (form), which doesn't say what went wrong. This matches the existing one_or_404 convention used by other routes, so it isn't a regression. Fix if wanted: pass a message such as "no project 999" to the 404.
- W/src/claude_factories/app.py:998–1005 — `create_factory_form` is `async def` but calls the blocking `create_factory` (file writes and sqlite). Harmless for a single-user local app. Fix if it matters: run it with `run_in_threadpool`.
- The header's `Factory: none` span doesn't update after a create until the page is reloaded. This is accepted in Q10, so nothing to change.
