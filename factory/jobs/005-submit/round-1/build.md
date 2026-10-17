# Round 1
## Changes
- src/claude_factories/app.py: `RoundBody` (`base_sha` 7–64 lowercase hex, `patch`, `build_md=None`), shared by `POST /api/tasks/{id}/rounds` and the new optional `TaskBody.submit` (Q4).
- src/claude_factories/app.py: `split_patch()` + `parse_section()` + `unquote()` (Q6). Splits with `re.split(r"(?m)^(?=diff --git )")` (`\n` only), so sections joined give the patch back byte for byte. Path from `rename to`, then `+++ b/…`, then `--- a/…`, then the header split at its midpoint; git's trailing tab dropped, C-quoted names unquoted via `codecs.escape_decode` and decoded as UTF-8. +/− counted after the first `@@`. Same-path sections (file ↔ symlink typechange) merge into one `modified` row.
- src/claude_factories/app.py: `insert_round(conn, task_id, body)`: the one helper both routes use. Checks the size first (413 `patch over 5 MB`, UTF-8 bytes of the patch only, Q5), then blank (422 `no changes to submit`), then split. Works out `n` and the trigger (Q1: initial / human after my CHANGES_REQUESTED on n−1 / agent), and inserts the round and its files inside the caller's `BEGIN IMMEDIATE`, so any 4xx rolls back.
- src/claude_factories/app.py: `POST /api/tasks/{id}/rounds`: 404 on an unknown task. On a standalone task (`worktree_path` NULL) every round sets review · human_review, clears `done_at`, bumps `updated_at`, and keeps `position`. It writes an `app` event only when status or stage changed. A task with a worktree is left alone (Q2). The response `url` has `?round=n`.
- src/claude_factories/app.py: `create_task` takes `request` (for the url) and, with `submit`, creates the task in review · human_review at 1 + max review position (or 1.0), writes one `app` event (NULL → review) and round 1, and returns §7.4's keys. Without `submit`, its behavior is unchanged. The `+ New task` form route now passes `request` through (Q3).
- src/claude_factories/app.py: `GET /api/tasks/{id}/rounds/{n|latest}/diff` returns the patches joined in rowid order as `text/x-diff`. `n` is compared as text, so `abc`, `01`, or a huge number simply 404 with `has no round <n>` (Q7).
- src/claude_factories/app.py: an exception handler for `UnicodeEncodeError` that returns a 422. A JSON `\ud800` escape in `patch`, `build_md`, or a title used to give a 500 (I checked this). It now gives a 422 and the transaction rolls back. This isn't in the spec: it's input checking at a trust boundary, placed once for every route.
- src/claude_factories/cli.py: `capture()` (Q8): `rev-parse --verify HEAD^{commit}`, then read-tree / `add -A` / `diff --cached -M --no-color --no-ext-diff --no-textconv --no-relative --src-prefix=a/ --dst-prefix=b/` with `-c core.quotePath=false`, using `GIT_INDEX_FILE` in a `TemporaryDirectory`. Runs in the cwd, reads output as bytes, and decodes it as UTF-8 with `errors="replace"`. It uses the base sha in read-tree and diff, not `HEAD` again, so they can't drift apart.
- src/claude_factories/cli.py: `fctl submit [<id> | --new --title T]` and `fctl diff <id> [--round N]`. The usage check (Q11) runs first via the subparser's `error`. `main_checkout()` is the repo check for both forms but is only used for the project lookup. stdin is read only when it isn't a TTY (Q9). Output lines are per Q10, with `1 file` and U+2212.
- tests/conftest.py: shared `write()` and `commit()` repo helpers (used by test_rounds and test_cli).
- tests/test_rounds.py: new; AC1–AC26 against real git patches from `cli.capture()`, plus one lone-surrogate test.
- tests/test_cli.py: AC27–AC41 against the existing recording `server` fixture.

## Criteria → tests
- AC1 → tests/test_rounds.py::test_split_modified_deleted_added
- AC2 → tests/test_rounds.py::test_split_renames
- AC3 → tests/test_rounds.py::test_split_binary
- AC4 → tests/test_rounds.py::test_split_mode_change
- AC5 → tests/test_rounds.py::test_split_space_and_quote_names
- AC6 → tests/test_rounds.py::test_split_counts_header_like_lines
- AC7 → tests/test_rounds.py::test_split_typechange_merges
- AC8 → tests/test_rounds.py::test_round_response
- AC9 → tests/test_rounds.py::test_round_without_build_md
- AC10 → tests/test_rounds.py::test_first_round_is_initial
- AC11 → tests/test_rounds.py::test_round_after_agent_is_agent
- AC12 → tests/test_rounds.py::test_round_after_my_changes_requested_is_human
- AC13 → tests/test_rounds.py::test_standalone_round_moves_to_review
- AC14 → tests/test_rounds.py::test_worktree_round_keeps_status
- AC15 → tests/test_rounds.py::test_round_unknown_task
- AC16 → tests/test_rounds.py::test_round_bad_body
- AC17 → tests/test_rounds.py::test_round_empty_patch
- AC18 → tests/test_rounds.py::test_round_patch_size
- AC19 → tests/test_rounds.py::test_submit_new_response
- AC20 → tests/test_rounds.py::test_submit_new_task_row
- AC21 → tests/test_rounds.py::test_submit_new_round
- AC22 → tests/test_rounds.py::test_submit_new_event
- AC23 → tests/test_rounds.py::test_submit_new_rejected
- AC24 → tests/test_rounds.py::test_submit_new_too_big
- AC25 → tests/test_rounds.py::test_diff_returns_patch_bytes
- AC26 → tests/test_rounds.py::test_diff_missing
- AC27 → tests/test_cli.py::test_submit_new_sends_capture
- AC28 → tests/test_cli.py::test_submit_leaves_real_index
- AC29 → tests/test_cli.py::test_submit_new_prints_review
- AC30 → tests/test_cli.py::test_submit_round_from_worktree
- AC31 → tests/test_cli.py::test_submit_round_prints_round
- AC32 → tests/test_cli.py::test_submit_from_subdirectory (also sets `diff.relative=true`, which `--no-relative` must override)
- AC33 → tests/test_cli.py::test_submit_keeps_crlf
- AC34 → tests/test_cli.py::test_submit_ignores_diff_config
- AC35 → tests/test_cli.py::test_submit_skips_terminal_stdin
- AC36 → tests/test_cli.py::test_submit_usage_errors
- AC37 → tests/test_cli.py::test_submit_outside_repo
- AC38 → tests/test_cli.py::test_submit_without_commit
- AC39 → tests/test_cli.py::test_submit_new_unconnected
- AC40 → tests/test_cli.py::test_diff_prints_latest
- AC41 → tests/test_cli.py::test_diff_round_option

## Open questions
- Q1–Q11 → the spec's defaults, as written.
- An unreadable section path → 422 `can't read the file path in: <header, first 200 chars>`. A `+++`/`---` name without the `b/`/`a/` prefix counts as unreadable, because fctl always sends those prefixes.
- When two sections for the same path merge, `old_path` is set to NULL, because the merged row is `modified`.
- On a worktree task, a round doesn't bump `updated_at`. Q2 only asks for the bump on standalone tasks.
- `RoundBody` is the one model for both routes, so a `submit` that carries `build_md` stores it. Q3's NULL holds when `build_md` isn't sent, which is the case for fctl.

## Test output
```
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/005-submit/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
236 passed, 1 warning in 27.58s
```
