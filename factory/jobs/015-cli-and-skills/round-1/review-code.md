VERDICT: PASS
564 passed, 1 warning in 66.65s (0:01:06)

No blocking findings. All AC1-AC18 have passing tests that assert the criterion (checked against the test bodies, not only build.md). cli.py imports only the stdlib (adds `pathlib`). No new dependencies. The autouse fixture sets a temp HOME, FCTL_HOME and a fake claude. The diff has no unrequested code: `project_at` is a small shared helper the spec allows.

## Nits (non-blocking)
- src/claude_factories/cli.py (`run`, `args.usage_error`) — `set_defaults(usage_error=p.error)` is slightly indirect — fine as is.
- Both skills carry an extra `can't reach …` / `HEAD has no commit yet` note beyond the spec; build.md flags it, and it is harmless.
