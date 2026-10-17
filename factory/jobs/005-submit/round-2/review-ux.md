VERDICT: PASS

Round 2 only changes server validation (malformed or unsafe patch paths now give 422 instead of 500) and adds a `nosniff` header on the diff response. The CLI output and flows are the same as round 1, which I checked end to end. The round 2 tests for the bad-body cases and the diff bytes pass (15 passed).

Round 1 findings: both were nits, and both are intentionally unchanged per the spec.

## Nits (non-blocking)
- `fctl submit 99` for an unknown task prints `fctl: 404 Not Found`. The spec calls for the bare 404. A message such as "task #99 not found" would be clearer later.
- The 422 for a bad `base_sha` is FastAPI's raw validation list, not a short message.
