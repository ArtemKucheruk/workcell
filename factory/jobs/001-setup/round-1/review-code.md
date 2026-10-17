VERDICT: PASS
41 passed, 1 warning in 3.08s

## Findings
None blocking. Checked:
- Stack: deps are only fastapi, uvicorn, jinja2 (dev: pytest, httpx). `cli.py` and `db.py` are stdlib only (AC3 test checks this in a subprocess). stdlib sqlite3, one `schema.sql`, WAL, no ORM, no build step. markdown-it-py is correctly not added.
- schema.sql differs from docs §5.1 only by `IF NOT EXISTS` on the 10 tables and the index (diffed myself).
- Vendored static file sha256 values match build.md.
- AC1-AC30 each have a test that opens and asserts the criterion (read all three test files). The `serve` tests stub `uvicorn.run` and capture stdout inside the stub, so they really prove banner-before-run.
- conftest autouse fixture uses a temp `FCTL_HOME`, unsets `FCTL_URL`, and puts a fake `claude` first on PATH. AC30 asserts this.
- No dead code, extra config, or unrequested abstractions.

## Nits (non-blocking)
- pyproject.toml:12 and the test deps — Starlette warns that `httpx` is deprecated in favour of `httpx2` for TestClient. FACTORY.md names `httpx`, so keep it for now.
- .python-version is an extra file not listed in the spec. It is harmless, and build.md explains it.
