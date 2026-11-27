# fctl for Claude agents

`fctl` is the command line of Workcell. Every bit of factory state (tasks, specs, rounds,
verdicts, comments, decisions, stages, project context) lives in the app's database, behind the
backend's HTTP API. `fctl` is the only way an agent reads or writes it. Most commands are a thin
HTTP client of the backend at `FCTL_URL` (default `http://127.0.0.1:4545`); markdown goes in on
stdin and comes out on stdout.

These pages are written for Claude: the agents inside a factory run, and a Claude Code session
working for the user in a connected repo. They say what to run, in what order, what you may and
may not touch, and what to do when a command fails.

## Pages

| Page | Read it when |
|---|---|
| [concepts.md](concepts.md) | You need the model: projects, tasks, status and stage, rounds, verdicts, decisions, feedback, context, blockers, runs, and the exact layout `fctl show` prints. |
| [environment.md](environment.md) | You need to know where you run: env vars, the worktree, `.fctl/`, the run's Bash allowlist, ports, and how to test the app without touching the user's real data. |
| [commands.md](commands.md) | You need one command's synopsis, stdin, output, and errors. Every command is there. |
| [roles.md](roles.md) | You have a role: orchestrator, spec-writer, builder, reviewer, approver, or the user's interactive session. Step-by-step playbooks. |
| [troubleshooting.md](troubleshooting.md) | A command failed, a Bash call was denied, or a run stalled. |

## Which role are you?

| You were started as | Read |
|---|---|
| `/factory <id>` (headless, by the app) | [roles.md § Orchestrator](roles.md#orchestrator-factory-id) |
| `spec-writer` (or `bug-spec-writer`, `security-auditor`, `data-check`, `coverage-planner`) | [roles.md § Spec-writer](roles.md#spec-writer) |
| `builder` / `builder-<id>` | [roles.md § Builder](roles.md#builder) |
| `review-security`, `review-ux`, `review-ui`, `review-code` (or `review-eval`, `review-tests`) | [roles.md § Reviewers](roles.md#reviewers) |
| `approver` | [roles.md § Approver](roles.md#approver) |
| An interactive Claude Code session the user talks to | [roles.md § Interactive session](roles.md#interactive-session-working-for-the-user) |

## Rules every agent keeps

1. **All state goes through `fctl`.** Never call the API with curl, never open `factory.db`,
   never write `factory/board.json` or `factory/backlog.md` to add work. A repo connected to the
   app adds tasks with `fctl task add`.
2. **Post only your own record.** The spec-writer posts the spec, the builder posts rounds, each
   reviewer posts its own verdict, the approver posts a decision. Only the orchestrator runs
   `fctl stage`. Nobody else changes a task's status.
3. **Never write git history.** No `git add`, `commit`, `stash`, `checkout`, `switch`, `reset`,
   `merge`, `rebase`, or `push`. `fctl submit` captures the tree through a temp index; the user
   commits after approving. `git status` and `git diff` are fine.
4. **In a run, markdown goes through a file.** Write it with the Write tool to `.fctl/<name>.md`,
   then `fctl <command> … < .fctl/<name>.md`. A heredoc over about 10,000 characters, or one the
   permission parser can't read, is denied, and a headless run has nobody to approve it.
5. **`fctl approve`, `fctl rework`, and `fctl run` belong to the user.** A run can't call them, so
   it can't approve its own work or start other runs. An interactive session runs them only when
   the user asks for that action.
6. **Read the `fctl: ` line.** Exit `0` is success, `1` prints one `fctl: <reason>` line on
   stderr, `2` is a usage error. Most reasons name the fix. Don't retry a refusal unchanged.
7. **Don't start the backend to get past `can't reach`.** Ask the user to start it
   (`fctl serve`, `fctl service start`, or `docker compose up -d`).
8. **Never print, quote, or copy secrets** from `.env` or other copied ignored files into a spec,
   build notes, verdict, comment, or decision.
9. **Never point a test server at the user's real data.** Testing the app means a temp
   `FCTL_HOME`, your run's own ports, and `env -u CLAUDE_CONFIG_DIR`
   ([environment.md § Testing the app](environment.md#testing-the-app-without-touching-real-data)).

## Source of truth

The full per-command reference, every flag and every error message, is
[`src/workcell/fctl.md`](../../src/workcell/fctl.md). The app serves it at
`/docs/fctl`, and `tests/test_fctl_md.py` checks it against the real parser. `fctl --help` and
`fctl <command> --help` print the live flags. If anything in this folder disagrees with those,
they win. The design behind the commands is in [`docs/claude-code.md` §7](../claude-code.md) and
[`docs/MVP.md` §4.3–4.5](../MVP.md).
