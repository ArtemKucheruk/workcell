# Troubleshooting

What a failure means and what to do. In a factory run you can't fix the environment: report the
exact message and stop. In an interactive session, tell the user the message and the fix; change
things only on their word.

## Messages every command can print

| Message | Meaning | Do |
|---|---|---|
| `fctl: can't reach http://127.0.0.1:4545 — is "fctl serve" running?` | Nothing answers at `FCTL_URL`. | Ask the user to start the app (`fctl serve`, `fctl service start`, or `docker compose up -d`). Don't start it yourself. If they run it on another port, set `FCTL_URL`. |
| `fctl: 403 Host must be 127.0.0.1 or localhost` | `FCTL_URL` names another host. | Use `http://127.0.0.1:<port>`. |
| `fctl: 403 X-Requested-By: fctl header required` | A write reached the API without `fctl` (curl, a script). | Use the `fctl` command. |
| `fctl: not inside a git repository: <cwd>` | The command works on the current repo. | Run it from inside the repo (any subdirectory or worktree works). |
| `fctl: 404 no project at <path>; in that repo, run fctl connect --workspace <name>, or if the checkout moved, change the path on the project's Settings page` | The repo isn't connected, or its checkout moved since it was. | `/factory-connect <workspace>`; after a move, ask the user to change the path on the project's Settings page instead, which keeps its tasks. |
| `fctl: 404 Not Found` | Unknown task id, usually. | Check the id with the user, or on the board. |
| `fctl: 422 [...]` (a JSON list) | Request validation failed, e.g. `--line 0`. | Fix the argument. |
| exit `2` with a usage line | Bad command, argument, or flag combination; nothing was sent. | Read the usage line; `fctl <command> --help`. |

## A Bash call was denied in a run

A run has `--permission-prompts none`: whatever isn't allowed is denied at once, and no one can
approve it. Find which case it is:

| Denial | Cause | Do |
|---|---|---|
| `fctl spec/submit/verdict/decide … <<'EOF'` with a long text | Over the ~10,000-character limit the permission check can parse ("Parser aborted (timeout, resource limit, or over-length)"). | Write the text to `.fctl/<name>.md` with the Write tool, then `fctl <cmd> … < .fctl/<name>.md`. |
| A heredoc with `{"` in it | Read as "brace with quote character (expansion obfuscation)". | Same: post from a file. |
| `fctl run`, `fctl approve`, `fctl rework`, `fctl task …`, `fctl seed`, `fctl serve` | Not on the allowlist, by design. | Don't. These are the user's. |
| `git add/commit/push/checkout/reset/merge/rebase/stash/switch` | Git writes are denied. | Don't. `fctl submit` captures the tree as it is. |
| The test command spelled differently, or another tool (`npm audit`, `semgrep`) | Only the project's test command's parts are allowed, plus the repo's `.claude/settings.json`. | Run the test command exactly as given. For a missing tool, say which one you didn't run. |
| Edit or Write under `.claude/` | See below. | |

The orchestrator stops and reports on a denial. Asking another agent to do the same thing a
different way only launders a denied action.

### Edits under `.claude/` are denied

Writes to `.claude/agents/*`, `.claude/skills/*`, and settings need interactive approval, which a
headless run doesn't have. More rounds can't fix it.

- Spec-writer: name it under Open questions.
- Builder: build and submit the rest; list the `.claude/` change under Open questions with the
  exact edit.
- Interactive session: tell the user the task needs that edit by hand, or make it yourself if they
  ask.

## The spec-writer's spec never got posted

The run stops at the spec step with `_No spec yet._`, often after a denied heredoc. The full spec
is usually still in the run's log. Interactive session, with the user's OK:

1. Make sure no run or other session still drives the task (step 2 of
   [Re-running a stalled task](#re-running-a-stalled-task)).
2. Read the log. It's a read-only `GET`, the one thing `fctl` has no command for:
   `curl -s 'http://127.0.0.1:4545/api/runs/<run-id>/log?after=0'`. The reply is
   `{"next": …, "lines": [{"text": …}, …]}`; the spec is in a fenced `markdown` block.
3. Save it to a file outside the repo (your scratchpad) and post it: `fctl spec <id> < <file>`.
4. `fctl run <id>`: the orchestrator sees a spec and no rounds, and goes straight to build round 1.

## `fctl submit` problems

| Message | Do |
|---|---|
| `fctl: HEAD has no commit yet; commit once before submitting` | The repo needs one commit. Tell the user; don't make it. |
| `fctl: 422 no changes to submit` | Nothing outside `.gitignore` differs from `HEAD`. Check `git status`; maybe the output is in an ignored path. |
| `fctl: 413 patch over 5 MB` | A generated, vendored, or binary file is in the tree. Add it to `.gitignore` (and say so in the notes). |
| `fctl: git <step> failed: …` | git itself failed; the message is git's. |
| `fctl submit: error: give a task id, or --new with --title` | Use exactly one form. |
| `Round 3 of #12` when you expected round 2 | A round was already submitted this round. Don't submit again; report it. |

## Run refusals

`fctl run`, `fctl task add --run`, and `fctl rework` (for its rework run) refuse with a `409`
naming the fix. The common ones:

| Message | Do |
|---|---|
| `run #41 is already running on #12; wait for it or stop it` | Wait, or the user stops it in the app. |
| `2 runs active (…); the limit is 2. Wait, stop one, or raise it in Settings` | The global cap is full. |
| `#15 is blocked by #12, #14; …` / `all backlog tasks are blocked: …` | Finish the blockers, or `fctl task unblock`. |
| `#12 is in review` / `#12 is done` | Nothing to run. A task in review needs the user's approve or rework. |
| `not on subscription auth` | No Claude account signed in to claude.ai. The user signs in under Settings → Claude accounts. |
| `all accounts near their limits: …` | Wait for a reset, or the user picks one with `--account`. |
| `Claude account b@y isn't logged in to claude.ai; …` / `fctl: no Claude account b@y` | Pick another account, or the user logs it in. |
| `factory isn't committed on main: …` / `this repo runs the file-based /factory loop: …` | The factory files aren't ready; the message names the step (usually Create factory, then commit on the default branch). |
| `wt (worktrunk) isn't installed: …`, `wt switch failed: …`, `wt … timed out` | The worktree couldn't be made. `brew install worktrunk`, or fix what wt says. |
| `<file> is ignored in the main checkout but not on main, …` | Commit that `.gitignore` line on the default branch, then run again. |

A rework whose run is refused after the note was recorded keeps the note and the move: fix the
cause, then `fctl run <id>`.

## Re-running a stalled task

A run that died leaves the task's status unchanged; the card shows "stalled" and Retry.

1. Find out why: the run log on the task page, or `fctl service logs backend`.
2. Make sure nothing still drives it: the app's active runs (`fctl service status` lists them, or
   the Agents page) and any other terminal session working on the same task. A second orchestrator
   or builder on one worktree overwrites the first one's work.
3. `fctl run <id>` (or Retry). The orchestrator continues from the stage; it doesn't start over.

A builder that went idle with an API error ("Your computer went to sleep mid-response") is often
still alive with its edits in the worktree. In the session that owns it, SendMessage it to rerun
the tests and submit, instead of spawning a second builder.

## A command or route that exists in the source 404s

The global `fctl` (or the running backend) serves older code than the checkout.

- Check the install is editable: in
  `~/.local/share/uv/tools/workcell/lib/python3.*/site-packages/workcell-*.dist-info/direct_url.json`,
  `"editable": true`. Fix: `uv tool install --editable --reinstall <checkout>`.
- `fctl service status` shows `stale` when a service runs another commit than the default branch:
  `fctl service reload`.
- With Docker, a stale image: `docker compose up --build -d`.

## Real data touched by a test

If a test or review started a backend or `fctl seed` without a temp `FCTL_HOME`, or with the
inherited `CLAUDE_CONFIG_DIR`, say so in your report:

- `FCTL_HOME`: the user's `~/.workcell/factory.db` may have gained the branch's tables
  (schema init runs on open, before any check refuses). Name the tables.
- `CLAUDE_CONFIG_DIR`: `claude auth status` may have run against the user's real login.

Then follow [environment.md § Testing the app](environment.md#testing-the-app-without-touching-real-data)
from then on.
