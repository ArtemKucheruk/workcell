VERDICT: PASS

Checked end to end with a live `fctl serve` and a temp FCTL_HOME. A temp repo was used for the CLI runs.

- `fctl submit --new --title ...` printed `Review #1: 2 files, +2 −0 → http://127.0.0.1:4545/tasks/1/review` and exited 0.
- `fctl submit 1` printed `Round 2 of #1: 2 files, +2 −0 → .../tasks/1/review?round=2` and exited 0.
- `fctl diff 1` and `fctl diff 1 --round 1` printed the patch.
- Errors went to stderr with exit 1 or 2. They covered an unconnected project, a missing round, a repo-less cwd, and usage mistakes.
- A bad `base_sha` gave 422.

## Nits (non-blocking)
- `fctl submit 99` for an unknown task prints `fctl: 404 Not Found`. The spec calls for the bare 404 here. A message such as "task #99 not found" would be clearer later.
- The 422 for a bad `base_sha` is FastAPI's raw validation list, not a short message.
