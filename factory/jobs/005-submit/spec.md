# 005-submit: Rounds (submit API, round files, fctl submit and diff)

## Goal
Record review rounds. `POST /api/tasks/{id}/rounds`, and `POST /api/projects/{id}/tasks` with `submit`,
store a round with its number, trigger, base commit, and build notes. Each round's patch is split into
one `round_files` row per file, with the change type, the rename source, a binary flag, and +/− counts.
A standalone submit puts the task in review · human_review. `fctl submit` captures tracked and
untracked changes through a temp index without touching the real one. `fctl diff` and
`GET …/rounds/{n|latest}/diff` return a round's full patch.

## Implements
- `docs/data-model-and-api.md §6.3`: `POST /api/tasks/{id}/rounds` (body `base_sha`, `build_md`, `patch`; the `round`, `files_changed`, `additions`, `deletions`, `url` response) and `GET /api/tasks/{id}/rounds/{n|latest}/diff` as `text/x-diff`.
- `docs/data-model-and-api.md §6.2`: the optional `submit` on `POST /api/projects/{id}/tasks`, which creates round 1 and puts the task straight in review.
- `docs/data-model-and-api.md §5.1`: writes to `rounds` (`n` per task, `trigger`, `base_sha`, `build_md`) and `round_files` (`path`, `old_path` on rename, `change`, `binary`, `additions`, `deletions`, `patch`; round totals = SUM over the table). No schema change.
- `docs/data-model-and-api.md §5.2`: `human_review` → `review`, set by the app on a standalone submit, with an `events` row.
- `docs/claude-code.md §7.2`: `fctl submit --new --title T` (stdin: description), `fctl submit <id>` (stdin: build notes), and `fctl diff <id> [--round N]`.
- `docs/claude-code.md §7.4`: step 1 (project from `--git-common-dir` + `GET /api/projects?path=`), step 2 (the temp-index capture), step 3 (the request), the 201 response, the CLI line `Review #17: 3 files, +38 −2 → …`, and a later `fctl submit 17` that creates round 2 of a standalone task.
- `docs/claude-code.md §7.5`: the `/factory-submit` row (→ review · human_review). Builders never change status: they post only their own round.
- `docs/MVP.md §2` (Round) and `§10 assumption 5`: rounds are numbered 1, 2, 3… per task and never reset, and each snapshot is the full diff against the base.
- `docs/MVP.md §3.6 step 3`: the round after my Request changes has trigger `human`.
- `docs/MVP.md §4.5`: patches over 5 MB are rejected with `413`. The new mutating routes sit behind the existing middleware.

## Acceptance criteria

Patch split into `round_files`, through `POST /api/tasks/{id}/rounds`. Patches are produced in a temp repo with the §7.4 capture, unless the criterion says otherwise.
- [ ] AC1: `a.py` with 1 line changed, `c.py` added with 2 lines, and `b.py` deleted with 4 lines → three rows: (`a.py`, modified, +1 −1), (`b.py`, deleted, +0 −4), (`c.py`, added, +2 −0). Each has `old_path` NULL and `binary` 0, and its `patch` starts with `diff --git a/<path> b/<path>`. Joined in insertion order, the three patches equal the submitted patch (Q6).
- [ ] AC2: `old.py` (10 lines) moved to `new.py` with 1 line changed → (`new.py`, renamed, `old_path` `old.py`, +1 −1). `x.txt` moved to `y.txt` unchanged → (`y.txt`, renamed, `old_path` `x.txt`, +0 −0).
- [ ] AC3: an added file `img.bin` whose bytes include NUL → (`img.bin`, added, `binary` 1, +0 −0).
- [ ] AC4: a committed `run.sh` with only its mode changed (`chmod +x`) → (`run.sh`, modified, +0 −0).
- [ ] AC5: added files `my notes.txt` and `say "hi".txt` → the paths are exactly `my notes.txt` (no trailing tab) and `say "hi".txt` (unquoted) (Q6).
- [ ] AC6: a committed line `-- old` replaced by `++ new` → +1 −1. Hunk lines that look like `---`/`+++` headers are counted (Q6).
- [ ] AC7: a committed regular file `link` replaced by a symlink → exactly one row (`link`, modified, +1 −1), whose `patch` holds both of git's sections for it (Q6).

`POST /api/tasks/{id}/rounds`
- [ ] AC8: a task with round 1 and the body `{"base_sha":<40-hex sha>,"build_md":"Token bucket …","patch":<patch>}` → 201 with exactly `{"round":2,"files_changed":<row count>,"additions":<sum>,"deletions":<sum>,"url":"http://127.0.0.1:4545/tasks/<id>/review?round=2"}`. The new `rounds` row has `n` 2, and `base_sha` and `build_md` as sent.
- [ ] AC9: a body without `build_md` → 201, and the row's `build_md` is NULL (Q4).
- [ ] AC10: the first round on a task without rounds → `n` 1, `trigger` initial (Q1).
- [ ] AC11: round 1 has no decision, or only an `approver` ESCALATE → round 2's `trigger` is agent (Q1).
- [ ] AC12: a decision by `me` with CHANGES_REQUESTED on round 1, inserted by SQL → round 2's `trigger` is human, and the next round 3 is agent (Q1).
- [ ] AC13: a standalone task (`worktree_path` NULL) in in_progress · rework at position 3.0 → afterwards it is review · human_review at position 3.0, with one new `events` row (actor `app`, in_progress → review, stage human_review). The same task already in review · human_review → no new `events` row (Q2).
- [ ] AC14: a task with `worktree_path` set, in in_progress · build → status and stage unchanged, and no `events` row (Q2).
- [ ] AC15: an unknown task id → 404, and no `rounds` or `round_files` row is written.
- [ ] AC16: each of these bodies → 422, and no `rounds` or `round_files` row: `base_sha` missing, `base_sha` `"HEAD"`, `"-c"`, or `"abc"`; `patch` missing; `patch` `"hello\n"`; `patch` `"diff --git nonsense\n"` (Q4).
- [ ] AC17: `patch` `""` or `"\n"` → 422 `{"detail":"no changes to submit"}` (Q4).
- [ ] AC18: a well-formed patch of 5,242,881 UTF-8 bytes → 413 `{"detail":"patch over 5 MB"}`, and nothing is written. One of exactly 5,242,880 bytes → 201 (Q5).

`POST /api/projects/{id}/tasks` with `submit`
- [ ] AC19: `{"title":"Fix open redirect after login","description_md":"`next` was …","submit":{"base_sha":<sha>,"patch":<AC1's patch>}}` → 201 with exactly `{"task_id":<id>,"round":1,"files_changed":3,"additions":3,"deletions":5,"url":"http://127.0.0.1:4545/tasks/<id>/review"}`.
- [ ] AC20: the task row has status review, stage human_review, `branch` and `worktree_path` NULL, and the description as sent. With review tasks at 2.0 and 7.0 and a backlog task at 20.0 in the project, its `position` is 8.0. In a project with no review tasks it is 1.0 (Q3).
- [ ] AC21: its `rounds` row has `n` 1, `trigger` initial, `base_sha` as sent, and `build_md` NULL. Its `round_files` rows are AC1's three (Q3).
- [ ] AC22: exactly one `events` row for the task: actor `app`, `from_status` NULL, `to_status` review, stage human_review (Q3).
- [ ] AC23: `submit` with patch `""`, or a title `"  "` → 422, and no `tasks`, `rounds`, `round_files`, or `events` row is written.
- [ ] AC24: `submit` with a patch over 5,242,880 bytes → 413, and no row is written (Q5).

`GET /api/tasks/{id}/rounds/{n|latest}/diff`
- [ ] AC25: a task with rounds 1 and 2 → `/rounds/1/diff` returns round 1's patch and `/rounds/latest/diff` returns round 2's. Both are 200, the content type starts with `text/x-diff`, and the body equals the submitted patch byte for byte, including `\r\n` hunk lines and non-ASCII text such as `naïve` (Q7).
- [ ] AC26: a task without rounds, with `latest` → 404 `{"detail":"#<id> has no rounds"}`. `/rounds/9/diff` or `/rounds/abc/diff` → 404 `{"detail":"#<id> has no round 9"}` (or `abc`). An unknown task → 404 (Q7).

`fctl submit` (`cli.main([...])` in a temp repo, against the recording `server` fixture in `tests/test_cli.py`, with `sys.stdin` replaced by `io.StringIO`)
- [ ] AC27: the repo has `a.py` modified, `c.py` untracked, and `debug.log` ignored by a committed `.gitignore`. The replies are `GET` → project 3 and `POST` → §7.4's 201. With stdin `Fixed it.\n`, `fctl submit --new --title "Fix open redirect after login"` sends exactly `GET /api/projects?path=<realpath of the repo>`, then `POST /api/projects/3/tasks` with body exactly `{"title":"Fix open redirect after login","description_md":"Fixed it.\n","submit":{"base_sha":<git rev-parse HEAD>,"patch":<patch>}}`. The patch has a section for `a.py` and a `new file mode` section for `c.py`, and none for `debug.log`.
- [ ] AC28: with a staged change to `a.py` and an untracked `c.py` before the submit → `git status --porcelain` is identical afterwards (`a.py` still staged, `c.py` still untracked), and both files are in the sent patch.
- [ ] AC29: the POST answers `{"task_id":17,"round":1,"files_changed":3,"additions":38,"deletions":2,"url":"http://127.0.0.1:4545/tasks/17/review"}` → stdout is exactly `Review #17: 3 files, +38 −2 → http://127.0.0.1:4545/tasks/17/review\n`. With `files_changed` 1, it reads `Review #17: 1 file, …` (Q10).
- [ ] AC30: in a worktree at `<repo>/.claude/worktrees/x` whose HEAD has a commit the main checkout lacks, with `a.py` modified there and stdin `notes\n` → `fctl submit 12` sends exactly one request, `POST /api/tasks/12/rounds`, with body exactly `{"base_sha":<the worktree's HEAD>,"build_md":"notes\n","patch":<patch>}`. The patch holds the worktree's `a.py` change (Q8).
- [ ] AC31: the POST answers `{"round":2,"files_changed":4,"additions":126,"deletions":9,"url":"http://127.0.0.1:4545/tasks/12/review?round=2"}` → stdout is exactly `Round 2 of #12: 4 files, +126 −9 → http://127.0.0.1:4545/tasks/12/review?round=2\n` (Q10).
- [ ] AC32: run from `<repo>/src/pkg` with `a.py` at the repo root modified → the patch contains `diff --git a/a.py b/a.py`. The capture covers the whole tree, with root-relative paths (Q8).
- [ ] AC33: a committed file with CRLF line endings, with one line changed → the sent patch contains `-old\r\n` and `+new\r\n` (Q8).
- [ ] AC34: the repo config sets `diff.noprefix=true`, `diff.mnemonicPrefix=true`, and `color.diff=always`, and a new file is named `naïve.txt` → the patch contains `diff --git a/naïve.txt b/naïve.txt` and `+++ b/naïve.txt`, and no ESC (`\x1b`) character (Q8).
- [ ] AC35: stdin is a terminal (a stand-in whose `isatty()` returns True and whose `read()` fails the test) → `--new` sends `"description_md":""` and `submit 12` sends `"build_md":""` (Q9).
- [ ] AC36: `fctl submit`, `fctl submit 12 --new --title T`, `fctl submit --new`, `fctl submit 12 --title T`, and `fctl submit abc` → exit 2, stderr starting with `usage: fctl submit`, and no request (Q11).
- [ ] AC37: `fctl submit --new --title T` and `fctl submit 12` outside any git repo → exit 1, stderr `fctl: not inside a git repository: <cwd>`, and no request.
- [ ] AC38: in a repo with no commits and one untracked file, `fctl submit 12` → exit 1, stderr `fctl: HEAD has no commit yet; commit once before submitting`, and no request (Q11).
- [ ] AC39: the project GET answers 404 `{"detail":"no project at <path>"}` → `fctl submit --new --title T` exits 1 with stderr `fctl: 404 no project at <path>`, and only that GET was sent.

`fctl diff`
- [ ] AC40: the reply is `text/x-diff` with body `diff --git a/x b/x\n…` → `fctl diff 12` sends one `GET /api/tasks/12/rounds/latest/diff`, and stdout equals the body exactly, with no newline added (Q10).
- [ ] AC41: `fctl diff 12 --round 2` → `GET /api/tasks/12/rounds/2/diff`.

## Files
- `src/claude_factories/app.py`:
  - the two new routes, and an optional `submit` on `TaskBody`/`create_task`;
  - one Pydantic model for the rounds body and for `submit`;
  - a `split_patch(patch)` function (Q6);
  - one helper that checks the patch, works out `n` and the trigger, and inserts the round and its files inside the caller's `BEGIN IMMEDIATE` transaction. Both routes use it.

  The `+ New task` form route keeps calling `create_task` and keeps working. Without `submit`, 003's behavior and tests are unchanged.
- `src/claude_factories/cli.py`: the `submit` and `diff` subcommands, a capture function (temp index, output read as bytes, Q8), and the stdin read (Q9). Stdlib only, so 001's AC3 keeps passing. It reuses `main_checkout()` and `api()`.
- `tests/test_rounds.py`: new. The API and parser criteria. Patches come from real git in the `repo` fixture, and decisions are inserted by SQL.
- `tests/test_cli.py`: the `fctl submit` and `fctl diff` criteria, against the existing `server` fixture.
- `tests/conftest.py`: only for helpers that both test files share.

No schema change and no new dependencies.

## Out of scope
- `GET /api/tasks/{id}/context` and `fctl show`. The verdict, comment, and decision endpoints with `fctl verdict`, `comment`, `decide`, `spec`, `stage`, and `round` (006).
- The review page that the returned `url` points to; it 404s until 007. "no agent review" chips for standalone tasks (007). Rendering per-file patches in Files changed (008).
- Approve and Request changes (009), which write the CHANGES_REQUESTED decisions that the trigger rule reads. Tests insert those decisions by SQL.
- Setting `branch`/`worktree_path`, spawning runs, and the `.claude/worktrees/` exclude (012). The `/factory-submit` skill and `fctl setup` (015).
- Board or page changes. A standalone task appears on the board through the existing list API.
- `--binary` patches, interdiff, editing or deleting rounds, size limits on `build_md` or the description, and checking that `fctl submit <id>` runs inside the task's project.

## Open questions
- Q1: §5.1 lists the triggers initial / agent / human, and §3.6 calls the round after my Request changes `human`, but the body carries no trigger and nothing says how the server tells them apart. Default:
  - round 1 → `initial`;
  - a `decisions` row by `me` with CHANGES_REQUESTED on round n−1 → `human`;
  - anything else → `agent`.

  The task's stage can't decide it, because the orchestrator sets `build` before the rework builder submits (§7.3 template).
- Q2: §5.2 has the app set human_review on a standalone submit, and §7.4 has `fctl submit 17` create round 2 of a standalone task after Request changes. Docs don't say how the server knows a task is standalone, or what a later round does to its status. Default:
  - A task whose `worktree_path` is NULL is standalone (the schema comment; 012 sets the column when a run creates the worktree).
  - Every round on a standalone task sets review · human_review, from any status including done. `done_at` is cleared as in 003 Q6, `position` is kept, and `updated_at` is bumped. An `events` row (actor `app`) is written only if status or stage changed (003 Q2).
  - A round on a task with a worktree never changes its status or stage (§7.5).
  - No status or running run blocks a submit, since the builder submits during its own run.
- Q3: §6.2 and §7.4 show the request and the response, but not the rows. Default:
  - One transaction creates the task (review · human_review, `branch` and `worktree_path` NULL) and round 1 (`initial`). Any 4xx writes nothing.
  - `position` is 1 + the highest position among the project's review tasks, or 1.0 if there are none. This is 003 Q8's rule applied to Review.
  - One `events` row: actor `app` (the "set by" column in §5.2), from NULL to review, stage human_review. There is no separate backlog event.
  - The response has exactly §7.4's keys (`task_id`, not `id`).
  - Round 1's `build_md` stays NULL: §7.4's `submit` has no build notes, and the description already holds the text.
- Q4: §6.3 gives no validation rules. Default:
  - One model, `{base_sha, patch, build_md=None}`, serves both routes.
  - `base_sha` must be 7–64 lowercase hex characters, since it may later become a git argument. Otherwise → 422.
  - A blank `patch` → 422 `no changes to submit` (a clean tree).
  - A `patch` that doesn't start with `diff --git ` → 422 `patch must start with "diff --git"`.
  - A section whose path can't be read → 422.
  - `build_md` is stored as sent.
- Q5: §4.5 says "over 5 MB" without a unit or saying what is measured. Default: a `patch` over 5 × 1024 × 1024 bytes in UTF-8 → 413 `patch over 5 MB`, on both routes, checked before the other patch checks. Only the patch is measured: JSON escaping inflates the request body, so a body limit would reject patches under 5 MB.
- Q6: docs say only "this file's section of the unified diff". Default:
  - Split on `\n` only, not `splitlines()`, which also breaks on `\r`. A section starts at each line beginning with `diff --git ` and runs to the next one, so the sections joined in order give the patch back byte for byte.
  - Change type: `rename from`/`rename to` → renamed (`old_path` from `rename from`); `new file mode` → added; `deleted file mode` → deleted; anything else → modified.
  - Path: taken from `rename to`, else the `+++ b/…` line (`--- a/…` for a deletion) with git's trailing tab removed (git adds one when a name has a space), else the `diff --git a/X b/X` header split at its midpoint. A name in double quotes is C-unquoted and decoded as UTF-8.
  - Binary: a `Binary files … differ` line. Binary files count +0 −0.
  - Counts: lines starting with `+` or `-` after the section's first `@@` line.
  - Two sections for the same path merge into one row: change modified, patches joined, counts summed, binary if either section is. Git splits a file ↔ symlink typechange into a delete and an add.
  - Rows are stored in patch order (rowid).
- Q7: §6.3 names the diff route only. Default:
  - `latest` is the highest `n`.
  - The body is the round's `round_files.patch` joined in rowid order, as `text/x-diff`.
  - A missing round, or an `n` that is neither a positive integer nor `latest` → 404 `#<id> has no round <n>`. `latest` on a task without rounds → `#<id> has no rounds`.
  - An unknown task → the existing bare 404.
- Q8: §7.4 gives the three git commands but not how to keep their output stable. Default:
  - Run them in the cwd, so a worktree's own changes and HEAD are captured. Only the project lookup uses `main_checkout()`.
  - `GIT_INDEX_FILE` points at a file in a `tempfile.TemporaryDirectory`. `base_sha` is `git rev-parse --verify HEAD`.
  - The diff command is `git -c core.quotePath=false diff --cached -M --no-color --no-ext-diff --no-textconv --no-relative --src-prefix=a/ --dst-prefix=b/ HEAD`, so user config can't change the format the server parses.
  - The output is read as bytes and decoded as UTF-8 with `errors="replace"`, which keeps `\r\n`. `text=True` would turn it into `\n`.
  - No `--binary`, matching §7.4's command.
- Q9: §7.2 says the description and build notes come on stdin, but not what happens without a heredoc. Default: read stdin only when it isn't a terminal, and send `""` otherwise, so `fctl submit 12` typed by hand doesn't wait for Ctrl-D. The text is sent unchanged.
- Q10: §7.4 gives the `--new` output line, and docs give none for `submit <id>` or `diff`. Default:
  - `--new` prints `Review #<task_id>: <n> files, +<a> −<d> → <url>` (§7.4).
  - `submit <id>` prints `Round <n> of #<id>: <n> files, +<a> −<d> → <url>`.
  - One file reads `1 file`. `−` is U+2212, as in the docs and on the board.
  - `fctl diff` writes the body as is, with no newline added.
- Q11: docs give no CLI error rules for `submit`. Default:
  - Exactly one of `<id>` or `--new` is given, and `--title` goes only with `--new`. Anything else is an argparse usage error (exit 2) before any git or HTTP call.
  - Outside a repo → the existing `not inside a git repository: <cwd>`.
  - No commit at HEAD → exit 1 `fctl: HEAD has no commit yet; commit once before submitting`.
  - Any other failed git step → exit 1 `fctl: git <subcommand> failed: <git's stderr>`.
  - `fctl submit <id>` doesn't check that the task belongs to the cwd's project: task ids are global, and `GET /api/tasks/{id}` returns no project.
