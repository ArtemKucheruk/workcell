VERDICT: PASS

No blocking findings. Checked against the spec, docs/MVP.md §4.3–§4.5, and the security checklist.

## Checked
- §4.5 bind: `cli.py:serve` hardcodes `uvicorn.run(app, host="127.0.0.1", ...)`. There is no `--host` option (AC6 test), and `uvicorn.run()` doesn't read `UVICORN_*` env vars. OK.
- §4.5 Host: `app.py:local_safety` runs on every request, `/static` included. I probed it at the ASGI level: no Host, empty Host, `[::1]`, `localhost.`, and `evil.example` on `/static` all get 403, and `LOCALHOST:4545` gets 200. It fails closed. OK.
- §4.5 X-Requested-By: the value must be exactly `fctl` on every method except GET/HEAD/OPTIONS. Lowercase `post` is rejected, and so is the value `FCTL`. There's no CORS middleware, so a cross-origin preflight gets 405 and no `Access-Control-*` headers. htmx sends the header through `hx-headers` on `<body>`. OK.
- Jinja: Starlette's `Jinja2Templates` uses `select_autoescape()`, so autoescape is on for `.html`. No `|safe` or `Markup` anywhere. Nothing untrusted is rendered yet. OK.
- Static: `StaticFiles` has `follow_symlink=False` by default, and `/static/../app.py` returns 404. OK.
- Subprocess: none in `src/`. Tests pass argument lists only, with no `shell=True` or `os.system`. OK.
- SQL: `schema.sql` is a package file run through `executescript`. The PRAGMAs are constants, and the tests use `?` parameters. OK.
- Secrets and logs: nothing is logged except the banner (port and data dir). OK.
- Supply chain: all 25 `uv.lock` packages come from `https://pypi.org/simple`. htmx and highlight.js are vendored and served same-origin. No CDN.
- §4.3 env stripping and auth check, §4.4 allow/deny lists, markdown raw-HTML-off, path containment, and 413: out of scope for this job (spec "Out of scope"). The diff doesn't touch them.

## Nits (non-blocking)
- src/claude_factories/cli.py:28 — `urllib.request.urlopen` goes through `ProxyHandler`, so if `HTTP_PROXY` is set without a `NO_PROXY` covering 127.0.0.1, every `fctl` call (specs, diffs, verdicts) goes to that proxy instead of the local app. I confirmed this with a local fake proxy: `api("GET", "/api/secret")` with `FCTL_URL=http://127.0.0.1:1` was answered by the proxy. Corporate shells and sandboxed agent Bash often set these variables. — Fix: open requests through a module-level `urllib.request.build_opener(urllib.request.ProxyHandler({}))` and call its `.open(req)`. Optionally add one test that sets `HTTP_PROXY` and checks that the request still reaches `FCTL_URL`.
- src/claude_factories/app.py:24 — FastAPI's defaults leave `/docs`, `/redoc`, and `/openapi.json` on. The Swagger and ReDoc pages load JS from cdn.jsdelivr.net without SRI. That JS runs in the app's own origin, so it can send same-origin requests with `X-Requested-By: fctl`. This bypasses the vendoring rule whenever the page is opened. — Fix: `FastAPI(..., docs_url=None, redoc_url=None)`, and `openapi_url=None` too if the schema isn't needed.
- src/claude_factories/db.py:23 — the data dir is created with the default umask (Q10 chose this), so `factory.db` with all specs and diffs is world-readable on a multi-user host. — Fix if you want it: `mkdir(mode=0o700, ...)` for new dirs only. The spec explicitly deferred this, so it isn't a defect.
