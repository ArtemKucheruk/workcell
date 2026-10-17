VERDICT: PASS

Checked end to end with a real `fctl serve` (temp FCTL_HOME) and the CLI in a temp repo.

- `fctl task add "Rate-limit login endpoint"` after connect: stdout `Added #1 to r → http://127.0.0.1:4599/projects/1`, exit 0. This matches spec Q11.
- Unconnected repo: stderr `fctl: 404 no project at <path>`, exit 1.
- Blank title: stderr `fctl: 422 title must not be blank`, exit 1.
- API: an empty PATCH gives 422 with a readable string. A manual move to done gives 200 `{"id","status","stage":null}`. A NaN position gives 422 and not 500. An unknown task gives 404 `Not Found`.
- The §3.3 flow needs no extra steps or flags.

## Nits (non-blocking)
- src/claude_factories/cli.py:`task_add` — an unconnected repo gets no "run fctl connect" hint. The spec leaves this out on purpose (Q11).
- The 404 detail for an unknown task is the generic `Not Found`. It could name the task id.
