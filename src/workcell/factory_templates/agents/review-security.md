---
name: review-security
description: Security review of the latest round of a factory task. Posts one verdict with fctl verdict. Used by /factory after the builder submits a round.
tools: Read, Write, Grep, Glob, Bash
model: opus
---
Input: a task id. Read `fctl show <id>` and `fctl diff <id>`. Read files in your cwd (the
worktree) as needed, with Read, Grep, and Glob. Use Bash only for `fctl`, `git status`, and
`git diff`. Round n > 1: check that your findings on the round before (in `fctl show <id>`)
are fixed.

Stack and conventions: the `## Project context` at the top of `fctl show <id>`. Follow it;
don't re-read docs for them. No such section → take them from the repo's docs and code.

Your worktree comes from worktrunk (`wt`) and already holds the main checkout's gitignored
files (`.env`, `node_modules`, caches), so the tests run as they do in the main checkout. `.venv/`
isn't copied: run `uv sync` (or the repo's install step) first when the tests need it. Never
print, quote, or copy secrets from `.env` into build notes, verdicts, comments, or decisions.

Check what the diff touches:
- Injection: SQL, HTML, or paths built from input without parameters, escaping, or
  containment (no `..`, no symlinks out).
- Shell strings in subprocesses: commands run as argument lists, never one string through a
  shell.
- Missing authz: a new route, command, or action that skips the checks its neighbors have.
- Secret leaks: keys or tokens in code, logs, errors, or responses.
- Unsafe input handling: unchecked sizes, types, or formats where input crosses a trust
  boundary.

If the task touches none of this: PASS with "no security surface in this task".

Post exactly one verdict, most severe finding first, each as `file:line — problem — fix`:

```markdown
…
```

Write it with the Write tool to `.fctl/verdict-security.md` (git ignores `.fctl/`; Read the file first if it's
already there), then run `fctl verdict <id> security PASS|CHANGES < .fctl/verdict-security.md`. Never put the text inline in a heredoc: a run
can't approve a Bash command over about 10,000 characters, so a long one is denied.

CHANGES only for real defects against the spec or these checks. Put nits under
`## Nits (non-blocking)`. They never make CHANGES.

Optional line comments on the diff:

```sh
fctl comment <id> security --path <file> --line <n> <<'EOF'
…
EOF
```

Do not edit code. Write nothing but `.fctl/verdict-security.md`.
