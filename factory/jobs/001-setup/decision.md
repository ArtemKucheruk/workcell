ESCALATE
Built: the `claude_factories` package. It has the stdlib-only `fctl` CLI (`serve`, plus the urllib `api()` client) and `db.py` (data dir, `foreign_keys=ON`, WAL, and the §5.1 `schema.sql` with only `IF NOT EXISTS` added). The FastAPI app has a lifespan init, the §4.5 Host and `X-Requested-By` middleware, `/static` with vendored htmx 2.0.11 and highlight.js 11.12.0, `base.html`, and a placeholder `/`. There's also the conftest harness.
Rounds: 1 of 2, and all 4 reviews PASS. Tests: 41 passed, 1 warning (Starlette's httpx deprecation). AC1–AC30 each map to a passing test that asserts the criterion. No conflicts with docs/.
You decide: the builder went past the Q8 default. The default says a non-JSON error body is printed as its raw text, so an empty body would print `fctl: 404 ` with a trailing blank. The builder prints the reason phrase instead (`fctl: 404 Not Found`). It also prints the raw body when the JSON has no `detail`, a case the default doesn't cover. No test covers the empty-body path. Accept this, or ask for the literal default.
Not blocking, from the security review: `api()` calls plain `urllib.request.urlopen`. If `HTTP_PROXY` is set and `NO_PROXY` doesn't cover 127.0.0.1, fctl traffic (specs, diffs) goes to the proxy. The reviewer's fix is an opener with `ProxyHandler({})`. Don't take the other nit (turning off `/docs`), because §4.2 relies on FastAPI serving `/docs`.

## Open questions
- Q1 (build backend): `uv_build` from `uv init --package` (uv 0.8.20). The builder ran `uv build --wheel` by hand: the wheel has `schema.sql`, both templates, all 4 static files, and the `fctl` entry point.
- Q2 (schema reruns): `IF NOT EXISTS` added to the 10 `CREATE TABLE` lines and the `one_active_run` index. Nothing else changed (I checked against §5.1).
- Q3 (foreign keys): `db.connect()` sets `PRAGMA foreign_keys = ON` on every connection.
- Q4 (Host check scope): Host is checked on every request, `/static` included. Only the hostname is compared, lowercased, port ignored. A missing Host gets 403. Both checks answer 403 with JSON `detail`.
- Q5 (asset versions): htmx 2.0.11 and the highlight.js 11.12.0 common bundle, plus the `github` and `github-dark` CSS, all from the npm releases via unpkg. sha256s are in build.md. The htmx min file has no upstream license header (it's 0BSD), and the hljs BSD-3 header is kept. No `highlightAll()`.
- Q6 (startup line): `Claude Factories → http://127.0.0.1:<port> (data: <dir>)` from `db.data_dir()`, flushed before `uvicorn.run`.
- Q7 (placeholder `/`): `index.html` extends `base.html`, with `<h1>Claude Factories</h1>` and "No projects yet."
- Q8 (mutating methods, client errors): everything except GET, HEAD, and OPTIONS needs the header. Errors print `fctl: <status> <detail>` to stderr, exit 1. The connection failure prints the AC28 message, exit 1. Past the default: an empty body prints the reason phrase, and JSON without `detail` prints the raw body (see above).
- Q9 (fake `claude`): `#!/bin/sh` + `exit 0`. `HOME` is overridden only in AC9's test. conftest also unsets `FCTL_URL` so tests never reach a real server.
- Q10 (data dir permissions): `mkdir(parents=True, exist_ok=True)` with the default umask. The security review notes `factory.db` is world-readable on a multi-user host, and the spec deferred that.
- New (httpx deprecation warning): kept `httpx` because the spec and FACTORY.md name it. Switching to `httpx2` is a one-line dev-dependency change.
- New (`--port` range): no range check. argparse only checks that it's an int, and uvicorn reports bind errors itself.
