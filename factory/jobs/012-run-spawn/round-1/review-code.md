VERDICT: PASS
347 passed, 1 warning in 51.89s

No defects. app.py Runs section matches spec Q1-Q13 and §4.3/§4.4; stdlib only, no new deps, no schema change; tests/test_runs.py covers AC1-AC27 with a temp FCTL_HOME and a fake claude on PATH, and the assertions match each criterion.

## Nits (non-blocking)
- src/claude_factories/app.py (worktree): the exclude file is rewritten under no lock; fine for one run at a time.
- build.md notes a stray branch after an AC21 failure and a thread-death hole; both are out of spec scope.
