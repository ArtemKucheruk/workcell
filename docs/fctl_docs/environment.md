# Environment

Where `fctl` runs, what it reads from the environment, and what a factory run lets you do.

## Is fctl there?

```sh
fctl --help              # lists the commands
fctl show --help         # one command's flags
```

`fctl` is installed on the host with `uv tool install --editable <checkout>` (on `PATH` from
`~/.local/bin`). An editable install runs the checkout's code, so a `git pull` updates it. A
non-editable one serves the code it was installed with: a route that exists in the source but
404s under `fctl` usually means that. See [troubleshooting.md](troubleshooting.md#a-command-or-route-that-exists-in-the-source-404s).

`fctl setup` writes the `/factory-connect`, `/factory-submit`, and `fctl` skills to
`~/.claude/skills/` (always `~/.claude`, even with `CLAUDE_CONFIG_DIR` set). The `/factory` skill
and its agents are written into each repo by **Create factory** on the project's Settings page,
not by `fctl`.

## Environment variables

| Variable | Default | Who reads it | What it is |
|---|---|---|---|
| `FCTL_URL` | `http://127.0.0.1:4545` | every command that calls the app | The backend's address; a trailing `/` is dropped. The backend accepts only `Host` `127.0.0.1` or `localhost` (else `403 Host must be 127.0.0.1 or localhost`). A run gets it set to the port the backend listens on. |
| `FCTL_HOME` | `~/.workcell` | `fctl serve`, `fctl seed`, `fctl service` | The data dir: `factory.db`, `runs/<id>.jsonl`, and for `fctl service` its `logs/` and `service.json`. Every other command works through the API and never opens it. |
| `FCTL_BACKEND_PORT`, `FCTL_FRONTEND_PORT` | set per run | agents in a run | Two free loopback ports for this run. If you start the app or any server to try a change, listen on these, never on 4545 or 3000. |
| `CLAUDE_CONFIG_DIR` | unset (`~/.claude`) | Claude Code, the backend | A run gets its Claude account's config dir. Unset it before starting a test backend ([below](#testing-the-app-without-touching-real-data)). |
| `FCTL_IN_DOCKER` | unset | `fctl service` | `1` in the container image; `fctl service` refuses there. |

`fctl` sends `X-Requested-By: fctl` on every call; the backend refuses any write (anything but
`GET`, `HEAD`, `OPTIONS`) without it (`403 X-Requested-By: fctl header required`). Agents use
`fctl`, not curl: it carries the header, resolves the project, captures diffs, and is the only
thing a run's allowlist lets through.

The links `fctl` prints (`→ http://127.0.0.1:4545/tasks/12`) start with `FCTL_URL`, which answers
only `/api/`. For the page, open the same path on the frontend, `http://127.0.0.1:3000`.

## Which commands need a repo

| Needs the current directory inside the connected repo | Takes a global task id, works anywhere |
|---|---|
| `connect`, `context`, `context set`, `import-factory`, `import`, `task add`, `run next`, `submit` (both forms: it diffs the current tree) | `show`, `diff`, `round`, `spec`, `stage`, `verdict`, `comment`, `decide`, `run <id>`, `rework`, `approve`, `export`, `task block`, `task unblock` |

Outside a git repo the first group fails with `fctl: not inside a git repository: <cwd>`.
`fctl submit <id>` diffs **the directory you run it in**, so the builder runs it from its worktree
and `/factory-submit` from the user's tree.

## Stdin

Commands that take markdown read it from stdin: `spec`, `submit`, `verdict`, `comment`, `decide`,
`context set`, and `task add --description -`.

- From a terminal, `fctl` reads nothing (it never waits for Ctrl-D). So stdin must be a pipe, a
  file redirect, or a heredoc.
- Text is sent unchanged.
- `spec`, `context set`, `comment`, and `task add --description` refuse blank text. `submit`,
  `verdict`, and `decide` accept empty text.
- In a heredoc, quote the delimiter (`<<'EOF'`) so the shell expands nothing, and make sure no
  line of the text is exactly `EOF`.

**In a run, never use a heredoc for long text.** Write a file, then redirect:

```sh
# 1. Write tool → .fctl/verdict-security.md   (Read it first if it already exists)
# 2. Bash:
fctl verdict 12 security CHANGES < .fctl/verdict-security.md
```

Claude Code's permission check can't approve a Bash command over about 10,000 characters, and it
also denies some shapes it can't parse safely (for example a heredoc holding `{"` brace-and-quote
sequences, read as expansion obfuscation). A headless run has no approval surface, so a denied
call just fails. Short heredocs are fine for `fctl comment` and for the user's interactive session.

The file names the templates use:

| Agent | File | Command |
|---|---|---|
| spec-writer | `.fctl/spec.md` | `fctl spec <id> < .fctl/spec.md` |
| builder | `.fctl/build.md` | `fctl submit <id> < .fctl/build.md` |
| review-`<slot>` | `.fctl/verdict-<slot>.md` | `fctl verdict <id> <slot> PASS\|CHANGES < .fctl/verdict-<slot>.md` |
| approver | `.fctl/decision.md` | `fctl decide <id> APPROVE\|ESCALATE < .fctl/decision.md` |

`.fctl/` is in the repo's `.git/info/exclude` (the app adds it before the first run, with
`.claude/worktrees/`), so these files never reach a round's diff. The worktree copy skips
`.fctl/`, so old drafts from the main checkout never show up.

## Inside a factory run

The app starts the run like this (from `handlers/runs.py`):

```sh
cd <repo>/.claude/worktrees/12-rate-limit-login
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_USE_… \
    FCTL_URL=http://127.0.0.1:4545 FCTL_BACKEND_PORT=… FCTL_FRONTEND_PORT=… \
    CLAUDE_CONFIG_DIR=<the run's account> \
claude -p "/factory 12" --session-id … --output-format stream-json --verbose \
  --permission-mode acceptEdits --permission-prompts none \
  --allowedTools <allowlist> --disallowedTools <denylist>
```

### Your working directory

- The cwd is the task's worktree, `<repo>/.claude/worktrees/<id>-<slug>`, on branch
  `factory/<id>-<slug>`, made from the default branch by worktrunk (`wt`). Every agent works
  only there. Never `cd` out of it, and don't edit the main checkout.
- It already holds the main checkout's gitignored files (`.env`, `node_modules`, caches), so the
  tests run as they do there. `.venv/` is **not** copied: run `uv sync` (or the repo's install
  step) first when the tests need it. `.claude/settings.local.json` is not copied either.
- The branch gets no commits. The user commits after Approve.

### What Bash may run

`--permission-prompts none` means anything not allowed is denied at once.

| Allowed | Denied |
|---|---|
| `fctl show`, `fctl diff`, `fctl spec`, `fctl submit`, `fctl verdict`, `fctl comment`, `fctl decide`, `fctl stage`, `fctl round` | `fctl run`, `fctl approve`, `fctl rework`, `fctl task …`, and every other `fctl` command (not on the list) |
| `git status`, `git diff` | `git commit`, `git push`, `git merge`, `git rebase`, `git reset`, `git checkout`, and every other git command |
| each part of the project's test command, as a prefix rule: `uv run pytest -q && npm --prefix frontend ci` allows `Bash(uv run pytest *)` and `Bash(npm --prefix frontend ci *)` | anything else, unless the repo's committed `.claude/settings.json` `permissions.allow` adds it |

- Read, Grep, and Glob read files; they need no Bash. `acceptEdits` lets Edit and Write change
  files in the worktree.
- **Writes under `.claude/` need interactive approval** and are denied in a run. A task whose
  spec edits `.claude/agents/*`, `.claude/skills/*`, or settings can't be built by the builder;
  flag it instead of burning rounds ([troubleshooting.md](troubleshooting.md#edits-under-claude-are-denied)).
- Run the test command as the project gives it (the skill and agent files print it as
  `Test command for this repo: …`). A different spelling of it may not match the rules.
- Audit tools (`npm audit`, `pip-audit`, `semgrep`, …) or an eval command run only if the repo's
  `.claude/settings.json` allows them. Otherwise say which tool you didn't run.

### Secrets

The copied `.env` and other ignored files may hold secrets. Never print, quote, or copy their
values into anything you post. Cite a secret as `file:line`, never its value.

## Testing the app without touching real data

This applies when the repo **is** Workcell (or any task makes you start its backend,
`fctl serve`, or `fctl seed`).

- **Use a temp `FCTL_HOME`.** Opening the database runs the schema init before any command's own
  checks, so even a refused `fctl seed` against the default `~/.workcell` applies the
  worktree's (unmerged) schema to the user's real `factory.db`.
- **Use your run's ports.** `--port $FCTL_BACKEND_PORT`, and point `FCTL_URL` at it. Port 4545 is
  the user's own backend; never bind it, and never bind `0.0.0.0`.
- **Unset `CLAUDE_CONFIG_DIR` and fake `claude`.** A backend started with the inherited
  `CLAUDE_CONFIG_DIR` and the real `claude` on `PATH` runs `claude auth status` against the user's
  real login when anything touches accounts.
- **Run the worktree's code with `uv run fctl`.** The global `fctl` is the user's install, usually an
  editable install of their main checkout, so it runs that code, not your worktree's changes.
- **Don't `export FCTL_URL` at your test server.** Your own `fctl show`, `submit`, `verdict`, and
  `decide` must keep reaching the real backend. Set `FCTL_URL` per command for the test server.
- **Stop it before you finish.**

```sh
home="$(mktemp -d)"                                   # never the default ~/.workcell
FCTL_HOME="$home" uv run fctl seed                    # optional demo data; no HTTP, writes only $home
FCTL_HOME="$home" env -u CLAUDE_CONFIG_DIR PATH="<dir with a fake claude>:$PATH" \
    uv run fctl serve --port "$FCTL_BACKEND_PORT" &
FCTL_URL="http://127.0.0.1:$FCTL_BACKEND_PORT" uv run fctl show 1   # per command, never exported
```

Whether you may start a server at all depends on the run's allowlist: `fctl serve`, `fctl seed`,
and `uv run fctl` aren't on it, so a run can start one only where the repo's settings allow it.
The unit tests (`uv run pytest -q`) already use temp homes and fakes; prefer them.

## Docker

When the app runs with `docker compose up`, the backend container runs `fctl serve --host 0.0.0.0`
and `compose.yaml` publishes it on the host at `127.0.0.1:4545` (the frontend at `127.0.0.1:3000`).
The optional `compose.override.yaml` only changes those host ports, with `ports: !override`. So:

- `fctl` on the host needs no settings (default `FCTL_URL`). If the override changes the backend
  port, set `FCTL_URL=http://127.0.0.1:<port>`.
- Don't run `fctl serve` on the host while compose is up; 4545 is taken.
- The data lives in the `fctl-home` volume (`FCTL_HOME=/data` in the container), not on the host.
- Runs use the image's `fctl`, inside the container.
- `fctl service` refuses; compose already keeps the app running.
- One command inside the container: `docker compose exec backend fctl --help`.
