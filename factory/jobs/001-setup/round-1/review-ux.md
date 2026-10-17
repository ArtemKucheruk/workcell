VERDICT: PASS

Checked CLI --help (exit 0, names serve), no command (exit 2, usage on stderr), serve --host (exit 2), unreachable server (stderr message per AC28, exit 1), Host/header 403 messages, banner format. All match spec; 41 tests pass.

## Nits (non-blocking)
- src/claude_factories/cli.py:60 — `fctl --help` lists subcommands as `{serve}` with no usage line for the missing-command error beyond argparse default — fine for now; revisit when more commands exist.
- Starlette httpx deprecation warning in tests — harmless.
