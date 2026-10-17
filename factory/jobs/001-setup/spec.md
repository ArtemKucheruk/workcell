# 001-setup: Project setup (fctl package, serve, schema, safety)

## Goal
Create the Python project that every later job builds on. It's an installable `claude_factories`
package with a `fctl` console script. `fctl serve` starts the FastAPI app on 127.0.0.1. At
startup the app creates the data dir and applies the full §5.1 schema in WAL mode. The app
also has a base Jinja layout with vendored htmx and highlight.js, and the §4.5 Host and
`X-Requested-By` checks. The stdlib-only CLI module gets the HTTP client that later `fctl`
commands will use. The test harness isolates every test in a temp `FCTL_HOME` with a fake
`claude` on PATH.

## Implements
- `docs/MVP.md §3.0`: the package installs with `uv tool install <repo>` and puts `fctl` on PATH. `fctl serve` is the one command, with data in `~/.claude-factories/`.
- `docs/MVP.md §4.1`: one `fctl serve` process. `factory.db` lives in the data dir.
- `docs/MVP.md §4.2`: the stack (Python 3.12, uv, FastAPI, uvicorn, stdlib sqlite3 in WAL mode, one `schema.sql` run at startup, Jinja2 + htmx, vendored highlight.js, stdlib-only CLI).
- `docs/MVP.md §4.4`: the `FCTL_URL` variable that tells `fctl` where the app is.
- `docs/MVP.md §4.5`: bind 127.0.0.1 only. `Host` must be `127.0.0.1` or `localhost`. Mutating requests need `X-Requested-By: fctl`, and both `fctl` and htmx send it. (The markdown, path-containment, and 413 rules belong to later jobs.)
- `docs/MVP.md §10 assumption 9`: port 4545.
- `docs/data-model-and-api.md §5.1`: every table and the `one_active_run` index, unchanged.
- `docs/data-model-and-api.md §6` (intro): JSON over `http://127.0.0.1:4545`, and mutating calls need the header.
- `docs/claude-code.md §7.2`: `fctl serve [--port 4545]` only.
- `docs/ui.md §8`: light and dark follow the system setting (base layout only).

## Acceptance criteria

Package and CLI
- [ ] AC1: run the `fctl` console script with `--help` → exit 0, and stdout names the `serve` command.
- [ ] AC2: run `fctl` with no command → exit 2, usage on stderr.
- [ ] AC3: `import claude_factories.cli` in a fresh interpreter (subprocess) → the only modules it adds to `sys.modules` are in `sys.stdlib_module_names` or under `claude_factories`. No fastapi, starlette, uvicorn, jinja2, or pydantic.

`fctl serve`
- [ ] AC4: `fctl serve` (with `uvicorn.run` monkeypatched) → `uvicorn.run` is called once with `host="127.0.0.1"` and `port=4545`.
- [ ] AC5: `fctl serve --port 5000` → `uvicorn.run` gets `port=5000`, and host is still `127.0.0.1`.
- [ ] AC6: `fctl serve --host 0.0.0.0` → exit 2 (there is no host option), and `uvicorn.run` is never called.
- [ ] AC7: `fctl serve` prints `Claude Factories → http://127.0.0.1:<port> (data: <data dir>)` to stdout before it calls `uvicorn.run` (Q6).

Data dir and schema
- [ ] AC8: with `FCTL_HOME=<tmp>/new` (not yet created), the app starts → `<tmp>/new/factory.db` exists.
- [ ] AC9: with `FCTL_HOME` unset and `HOME=<tmp>`, the data dir resolves to `<tmp>/.claude-factories`.
- [ ] AC10: after startup, `sqlite_master` has the tables `workspaces`, `projects`, `tasks`, `runs`, `rounds`, `round_files`, `verdicts`, `comments`, `decisions`, `events` and the index `one_active_run`.
- [ ] AC11: after startup, `PRAGMA journal_mode` on `factory.db` → `wal`.
- [ ] AC12: start the app, insert a `workspaces` row, start the app again on the same `FCTL_HOME` → the second startup succeeds and the row is still there.
- [ ] AC13: insert two `runs` rows with `status='running'` → the second raises `sqlite3.IntegrityError` (the §5.1 constraint holds).
- [ ] AC14: on a connection from the app's db helper, insert a `projects` row with a `workspace_id` that doesn't exist → `sqlite3.IntegrityError` (foreign keys on, Q3).

Base layout and static files
- [ ] AC15: `GET /static/htmx.min.js` and `GET /static/highlight.min.js` → 200 each, and each body is the vendored upstream file. The served bytes equal the file under `static/`.
- [ ] AC16: `GET /` → 200 HTML from a template that extends `base.html`. The page has `<meta name="color-scheme" content="light dark">`, `<script src="/static/htmx.min.js">`, `<script src="/static/highlight.min.js">`, a highlight.js light theme `<link>` with `media="(prefers-color-scheme: light)"`, and a dark theme `<link>` with `media="(prefers-color-scheme: dark)"`.
- [ ] AC17: `GET /` → the `<body>` carries `hx-headers='{"X-Requested-By": "fctl"}'`, so every htmx request sends the header.

Local-safety middleware
- [ ] AC18: `GET /` with `Host` set to `127.0.0.1:4545`, `localhost:4545`, `localhost`, or `127.0.0.1:5000` → 200.
- [ ] AC19: `GET /` with `Host` set to `evil.example`, `localhost.evil.example`, or `127.0.0.1.evil.example` → 403, JSON `{"detail": "Host must be 127.0.0.1 or localhost"}`.
- [ ] AC20: `POST`, `PUT`, `PATCH`, and `DELETE` to `/anything` without `X-Requested-By` → 403, JSON `{"detail": "X-Requested-By: fctl header required"}`.
- [ ] AC21: `POST /anything` with `X-Requested-By: other` → 403, with the same body as AC20.
- [ ] AC22: `POST /anything` with `X-Requested-By: fctl` gets through the middleware → 404, not 403.
- [ ] AC23: `GET /` without `X-Requested-By` → 200 (read requests don't need the header).

`fctl` HTTP client (in `cli.py`, stdlib `urllib` only)
- [ ] AC24: `api("POST", "/api/x", {"a": 1})` → sends one request to `$FCTL_URL/api/x` with `X-Requested-By: fctl`, `Content-Type: application/json`, and body `{"a": 1}`. A `GET` also carries `X-Requested-By: fctl`.
- [ ] AC25: with `FCTL_URL` unset → the request goes to `http://127.0.0.1:4545<path>`.
- [ ] AC26: on a response with `Content-Type: application/json` → `api` returns the parsed JSON. Any other content type → it returns the body as `str`.
- [ ] AC27: on an error status, for example 409 with `{"detail": "run #41 active"}` → `SystemExit` with code 1, and stderr is `fctl: 409 run #41 active`.
- [ ] AC28: with `FCTL_URL` pointing at a closed port on 127.0.0.1 → `SystemExit` with code 1, and stderr is `fctl: can't reach <FCTL_URL> — is "fctl serve" running?`.

Repo and test harness
- [ ] AC29: `.gitignore` lists `.venv/`, `__pycache__/`, `.pytest_cache/`, and `dist/`.
- [ ] AC30: in any test, `FCTL_HOME` is under pytest's `tmp_path`, and `shutil.which("claude")` resolves to the fake `claude` in a temp dir, not the real one (autouse fixture in `tests/conftest.py`).

## Files
- `pyproject.toml`: project `claude-factories`, `requires-python = ">=3.12"`, runtime deps `fastapi`, `uvicorn`, `jinja2`. Dev group `pytest`, `httpx`. `[project.scripts] fctl = "claude_factories.cli:main"`. Build backend per Q1.
- `uv.lock`: generated by uv, committed.
- `.gitignore`
- `src/claude_factories/__init__.py`: empty. It must not import the app (AC3).
- `src/claude_factories/cli.py`: stdlib only. Has `main(argv=None)` with argparse and a `serve` subcommand. `serve` imports `uvicorn` and the app inside the function. Also holds `api(method, path, body=None)`.
- `src/claude_factories/db.py`: stdlib only. Resolves the data dir (`FCTL_HOME`, else `~/.claude-factories`), opens a connection (`foreign_keys=ON`), and applies `schema.sql` in WAL mode.
- `src/claude_factories/schema.sql`: §5.1, with `IF NOT EXISTS` added (Q2).
- `src/claude_factories/app.py`: the FastAPI `app`. Its lifespan creates the data dir and applies the schema. It also holds the safety middleware, the `/static` mount, Jinja2Templates, and `GET /`.
- `src/claude_factories/templates/base.html`, `src/claude_factories/templates/index.html`
- `src/claude_factories/static/htmx.min.js`, `static/highlight.min.js`, `static/github.min.css`, `static/github-dark.min.css`: vendored, unmodified (Q5).
- `tests/conftest.py`: an autouse fixture that sets `FCTL_HOME` to a tmp dir and puts a fake `claude` first on PATH. Also a `client` fixture: `with TestClient(app, base_url="http://127.0.0.1:4545")`. The base URL makes the Host check pass.
- `tests/test_cli.py`, `tests/test_db.py`, `tests/test_app.py`: or fewer files. One test per AC.

## Out of scope
- Every `/api/*` route and every other `fctl` command. Workspaces, projects, and `fctl connect` belong to 002, tasks and `fctl task add` to 003, and so on down the backlog.
- markdown-it-py and markdown rendering (007, 010, 016). Don't add the dependency until a job renders markdown.
- The `Claude: Pro ✓` / `API key — runs disabled` header badge, `claude auth status`, and env stripping (012, 014).
- The `runs/` dir, run logs, and startup cleanup of `running` runs (012, 013).
- The real dashboard at `/` (017). This job's `/` is a placeholder (Q7).
- Path containment and the 5 MB / 413 limit (005, 016).
- Page styling beyond the `color-scheme` meta and the highlight.js themes. No `app.css` yet.
- Schema migrations and versioning.
- `fctl setup` and the global skills (015).

## Open questions
- Q1: docs don't name a build backend. Default: use whatever `uv init --package` generates (src layout, `uv_build` on current uv). It's build-time only and adds no runtime dependency. Make sure `schema.sql`, `templates/`, and `static/` end up in the wheel: run `uv build` once by hand and note the result in build.md. Tests don't build wheels, because that may need the network.
- Q2: §5.1 uses plain `CREATE TABLE`, but the schema runs at every startup. Default: add `IF NOT EXISTS` to every `CREATE TABLE` and `CREATE UNIQUE INDEX`, and change nothing else (columns, types, constraints, comments). No migrations.
- Q3: SQLite ignores `REFERENCES` unless `PRAGMA foreign_keys=ON` is set on each connection. Default: the db helper turns it on for every connection it opens.
- Q4: §4.5 doesn't say whether the Host check covers read requests, and doesn't give a status code. Default: check Host on every request (DNS rebinding reads pages with GET). Compare only the hostname, case-insensitively and ignoring the port. A missing Host is rejected. Both checks answer 403 with the JSON `detail` messages in AC19 and AC20.
- Q5: docs don't pin asset versions. Default: the latest htmx 2.0.x `dist/htmx.min.js` and highlight.js 11.x (`highlight.min.js` common bundle, `styles/github.min.css`, `styles/github-dark.min.css`). Download each once from the official npm/cdnjs release, keep its license header, and record the versions and URLs in build.md. This job doesn't call `hljs.highlightAll()`. The pages that show code wire it up.
- Q6: docs give no `fctl serve` startup line. §3.0's comment says "app on http://127.0.0.1:4545, data in ~/.claude-factories/". Default: print `Claude Factories → http://127.0.0.1:<port> (data: <dir>)`, using the db helper's data-dir resolver. uvicorn's own log lines follow it unchanged.
- Q7: `/` is the dashboard (017), but this job needs a page that renders the layout. Default: `index.html` extends `base.html`, with an `<h1>Claude Factories</h1>` header and the line "No projects yet." 017 replaces it.
- Q8: docs don't decide "mutating" or the client's error output. Default: every method except GET, HEAD, and OPTIONS needs the header. Client errors go to stderr as `fctl: <status> <detail>`. The detail is the JSON `detail` (a string as is, anything else JSON-encoded), or the raw body text when the body isn't JSON. Exit code 1. A connection failure prints the AC28 message, also with exit code 1.
- Q9: docs don't say what the fake `claude` does. Default: a `#!/bin/sh` script that prints nothing and exits 0. Later jobs that spawn `claude` give it behavior. Tests don't override `HOME`, except AC9's test, which uses `monkeypatch`.
- Q10: FCTL_HOME permissions aren't specified. Default: `mkdir(parents=True, exist_ok=True)` with the default umask. Existing dirs are left alone.
