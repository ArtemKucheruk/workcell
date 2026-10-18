# 015-cli-and-skills: fctl setup, run, and task add --run

## Goal
`fctl setup` installs the two global Claude Code skills, `/factory-connect` and
`/factory-submit`, into `~/.claude/skills/`. It works offline. `fctl run <id>`, `fctl run next`, and
`fctl task add "…" --run` start factory runs from the terminal through the run endpoints that
012 already built. After this job, a repo can be connected and run end to end without the
file-based loop.

## Implements
- `docs/MVP.md §3.0`: `fctl setup` is the one-time step that writes `~/.claude/skills/factory-connect` and `~/.claude/skills/factory-submit`.
- `docs/claude-code.md §7.1`: the two skill files are `~/.claude/skills/factory-connect/SKILL.md` and `~/.claude/skills/factory-submit/SKILL.md`, and `fctl setup` installs them.
- `docs/MVP.md §3.1`: what `/factory-connect <workspace>` tells Claude to do. Claude inspects the repo for its test command, runs `fctl connect --workspace W --test-cmd C`, and shows the `Connected … → URL` line.
- `docs/MVP.md §3.8` + `docs/claude-code.md §7.4`: what `/factory-submit` tells Claude to do. Claude writes a title and description from the diff and the conversation, then runs `fctl submit --new --title T <<'EOF' … EOF` and shows `Review #N: …`. A later `/factory-submit` on the same change runs `fctl submit <id>` with build notes and creates the next round.
- `docs/claude-code.md §7.2`: the `fctl setup`, `fctl task add "title" [--run]`, and `fctl run <id>` / `fctl run next` rows. The FACTORY.md mapping applies: `/factory <feature>` becomes `fctl task add "…" --run`, and `/factory next` becomes `fctl run next`.
- `docs/data-model-and-api.md §6.2`: the `POST /api/tasks/{id}/run` (202 `{run_id, session_id, worktree}`) and `POST /api/projects/{id}/run-next` (202 `{task_id, run_id}`, 404 if the backlog is empty) calls and their replies. The server already implements both (012).

## Acceptance criteria
Tests run `cli.main([...])` against the recording `server` fixture in `tests/test_cli.py`, with
`HOME` set to a temp dir. `<HOME>` below is that dir, and `<URL>` is `FCTL_URL`.

`fctl setup`
- [ ] AC1: `fctl setup` with no `<HOME>/.claude` directory → exit 0. Both `<HOME>/.claude/skills/factory-connect/SKILL.md` and `<HOME>/.claude/skills/factory-submit/SKILL.md` exist afterwards, with their parent dirs created.
- [ ] AC2: `fctl setup` stdout → exactly `Wrote <HOME>/.claude/skills/factory-connect/SKILL.md\nWrote <HOME>/.claude/skills/factory-submit/SKILL.md\n` (Q3).
- [ ] AC3: `fctl setup` sends no HTTP request → with `FCTL_URL` pointing at a closed port it still exits 0, and the `server` fixture records no requests.
- [ ] AC4: the written factory-connect `SKILL.md` → starts with a `---` frontmatter block holding `name: factory-connect` and a non-empty `description:`. Its body contains `$ARGUMENTS`, `fctl connect --workspace`, and `--test-cmd`.
- [ ] AC5: the written factory-submit `SKILL.md` → frontmatter holds `name: factory-submit` and a non-empty `description:`. Its body contains `fctl submit --new --title`, `fctl submit <id> <<'EOF'`, and a quoted heredoc `<<'EOF'` for the description.
- [ ] AC6: run `fctl setup`, edit `factory-connect/SKILL.md`, and add `factory-connect/notes.md`, then run `fctl setup` again → `SKILL.md` is byte-identical to its first-run content, and `notes.md` is untouched (Q2).
- [ ] AC7: `<HOME>/.claude/skills` is a regular file → exit 1. Stderr starts with `fctl: can't write <HOME>/.claude/skills/factory-connect/SKILL.md: ` and contains no traceback (Q4).

`fctl run`
- [ ] AC8: `fctl run 12` with the server replying 202 `{"run_id":41,"session_id":"s","worktree":".claude/worktrees/12-x"}` → exactly one request, `POST /api/tasks/12/run` with no body. Stdout is `Run #41 on #12 → <URL>/tasks/12\n` (Q9).
- [ ] AC9: `fctl run 12` run from a directory outside any git repo (`GIT_CEILING_DIRECTORIES` set) → still sends `POST /api/tasks/12/run` and exits 0. A task id needs no repo.
- [ ] AC10: `fctl run next` inside a connected repo, with replies `{"id":3,…}` then 202 `{"task_id":14,"run_id":42}` → requests are `GET /api/projects?path=<realpath of main checkout>`, then `POST /api/projects/3/run-next` with no body. Stdout is `Run #42 on #14 → <URL>/tasks/14\n` (Q10).
- [ ] AC11: `fctl run next` outside a git repo → exit 1 with stderr `fctl: not inside a git repository: <cwd>\n`, and no requests.
- [ ] AC12: `fctl run next` when run-next replies 404 `{"detail":"backlog is empty"}` → exit 1 with stderr `fctl: 404 backlog is empty\n`.
- [ ] AC13: `fctl run 12` when the server replies 409 `{"detail":"run #41 active"}` → exit 1 with stderr `fctl: 409 run #41 active\n` and empty stdout.
- [ ] AC14: `fctl run` and `fctl run abc` → exit 2 with stderr starting `usage: fctl run`, and no requests.

`fctl task add --run`
- [ ] AC15: `fctl task add "T" --run` inside a connected repo → 3 requests in order: `GET /api/projects?path=…`, `POST /api/projects/3/tasks` with `{"title":"T"}`, and `POST /api/tasks/12/run` with no body. Stdout is `Added #12 to api → <URL>/projects/3\nRun #41 on #12 → <URL>/tasks/12\n`.
- [ ] AC16: `fctl task add "T" --run` when the run POST replies 409 `{"detail":"not on subscription auth"}` → exit 1. Stdout is still `Added #12 to api → <URL>/projects/3\n`, and stderr is `fctl: 409 not on subscription auth\n` (Q11).
- [ ] AC17: `fctl task add "T"` without `--run` → still exactly the 2 requests and the one `Added` line. 003's `test_task_add*` tests pass unchanged.

General
- [ ] AC18: `uv run pytest -q` passes. That includes 001's `test_cli_imports_only_stdlib`: `cli.py` still imports only the stdlib.

## Files
- `src/claude_factories/cli.py`:
  - A `setup` subcommand. It copies the two shipped `SKILL.md` files into `Path.home() / ".claude" / "skills" / <name> / "SKILL.md"` with `mkdir(parents=True, exist_ok=True)`. It catches `OSError` and calls `_fail`.
  - A `run` subcommand with one positional `target`, which is a task id or `next`. Anything else calls `p.error`. `next` reuses `main_checkout()` and the `GET /api/projects?path=` lookup from `task_add`.
  - `--run` on `task add`. One small helper prints the `Run #… on #… → …` line, shared by `run` and `task add --run`.
  - Stdlib only. Read the skill files relative to the module (`Path(__file__).parent` or `importlib.resources`).
- `src/claude_factories/global_skills/factory-connect/SKILL.md`: frontmatter `name`, `description`. The body is §3.1's flow:
  - `$ARGUMENTS` is the workspace (Q5).
  - Find the one command that runs the whole test suite from the repo root, e.g. from pyproject, package.json, a Makefile, CI config, or the README (Q6).
  - Run `fctl connect --workspace "<workspace>" --test-cmd "<cmd>"`.
  - Show fctl's output line. Rerunning updates the project.
- `src/claude_factories/global_skills/factory-submit/SKILL.md`: frontmatter `name`, `description`. The body is §7.4's flow:
  - Read the changes (`git status`, `git diff`, untracked files included) and the conversation.
  - Write a short title, plus a markdown description of what changed, why, and which tests ran with what result.
  - Run `fctl submit --new --title "<title>" <<'EOF' … EOF` and show the `Review #N: …` line.
  - On a change already submitted as task N, run `fctl submit <id> <<'EOF' <build notes> EOF` instead (Q7).
  - Never stage or commit: fctl captures the tree without touching the index.
  - A `404 no project at …` means the repo isn't connected, so suggest `/factory-connect <workspace>`.
  - The files are copied as-is. They hold nothing per-project, so no Jinja.
- `tests/conftest.py`: the autouse `isolated` fixture also sets `HOME` to a temp dir, so no test can touch the real `~/.claude`.
- `tests/test_cli.py`: AC1–AC17, appended in the file's style (`server` fixture, `reply()`, `requests()`, `Terminal`). Existing tests stay unchanged.

No new dependency. `uv_build` already ships non-Python files under `src/claude_factories/`, as `factory_templates/` shows.

## Out of scope
- The run endpoints and their checks: worktree, auth, factory committed, one run at a time (012, done). Stop, run log, Retry, startup cleanup, and rework spawning (013). Run, Run next, Stop, and Retry buttons, plus the `Claude: Pro ✓` header (014).
- Any `fctl stop`, `fctl log`, or `fctl worktree` command. §7.2 has none, and `fctl worktree` is on the Later list (§9).
- Create factory and the per-project `/factory` skill and agents (011).
- An `fctl uninstall`/`--force`, or a command that lists workspaces.
- Changing the run allowlist. Agents still can't call `fctl run` (§4.4, enforced by 012's `--allowedTools`).
- Connecting this repo and retiring `factory/`. That's a manual step after 015, not code.

## Open questions
- Q1: Where `~/.claude` is. docs/ only says `~/.claude/skills/…`, and Claude Code can also be pointed elsewhere with `CLAUDE_CONFIG_DIR`. Default: `Path.home() / ".claude"` (HOME on macOS/Linux). Ignore `CLAUDE_CONFIG_DIR`.
- Q2: What setup does when a skill file already exists. Default: overwrite `SKILL.md` every time. fctl owns these two folders, and re-running `fctl setup` after upgrading fctl should refresh them. Never touch other files in those folders or any other skill.
- Q3: What setup prints. Default: one `Wrote <absolute path>` line per file, factory-connect first, and nothing else.
- Q4: How a failed write is reported. Default: stop at the first failure with `fctl: can't write <path to that SKILL.md>: <e.strerror>` on stderr, exit 1. No rollback of a file already written.
- Q5: `/factory-connect` with no argument. `fctl connect` requires `--workspace`. Default: the skill tells Claude to ask me for the workspace name before running anything.
- Q6: `/factory-connect` when Claude finds no test command. Default: ask me. If I have none, connect without `--test-cmd` and tell me that Create factory will need one, since 011 returns 409 `no test command`.
- Q7: How `/factory-submit` tells a new review from a new round. §7.4 says a second `/factory-submit` runs `fctl submit 17`, but not how Claude knows 17. Default: if `$ARGUMENTS` is a task id, or this session already printed `Review #N` for this change, run `fctl submit <N>` with build notes on stdin. Otherwise run `fctl submit --new --title`.
- Q8: Extra skill frontmatter (`allowed-tools`, `disable-model-invocation`). Default: none. Use only `name` and `description`, like 011's templates. I approve each `fctl` call in my own session.
- Q9: `fctl run <id>` output. Default: `Run #<run_id> on #<id> → <FCTL_URL>/tasks/<id>`. That's the task page, where 014 adds the run log.
- Q10: Which project `fctl run next` uses. §7.2 calls `/api/projects/{id}/run-next` but doesn't say where the id comes from. Default: the current repo's, resolved like `fctl task add`. Print the same `Run #… on #…` line using the reply's `task_id`.
- Q11: `task add --run` when the run is refused. The task was already created, and there's no delete endpoint. Default: the task stays in Backlog and the `Added` line is printed first. The run error goes to stderr with exit 1.
