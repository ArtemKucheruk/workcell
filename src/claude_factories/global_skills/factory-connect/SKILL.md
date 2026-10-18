---
name: factory-connect
description: Connect the current git repo to Claude Factories as a project in a workspace. Use as "/factory-connect <workspace>". Finds the repo's test command, then runs fctl connect.
---

# /factory-connect $ARGUMENTS

Connect this repo to Claude Factories in the workspace `$ARGUMENTS`. Edit no files and run no
git command that writes.

1. The workspace is `$ARGUMENTS`. If that's empty, ask me for the workspace name and wait.
   Run nothing until I answer.
2. Find the one command that runs the whole test suite from the repo root. Look in
   pyproject.toml, package.json scripts, a Makefile, the CI config (e.g. `.github/workflows/`),
   and the README. Prefer what CI runs, e.g. `uv run pytest -q`, `npm test`, or `make test`.
   Found none → ask me. If I have none either, connect without `--test-cmd` and tell me that
   Create factory will need one. Factory runs execute this command, so before step 3 show it to
   me, with the file you took it from.
3. From the repo, run:
   ```
   fctl connect --workspace "<workspace>" --test-cmd "<test command>"
   ```
   Quote both values for the shell.
4. Show me the line fctl prints, `Connected <name> (<workspace>) → <url>`. Running it again
   updates the project, e.g. with a new test command.

`can't reach … — is "fctl serve" running?` → ask me to start `fctl serve`. Don't start it
yourself.
