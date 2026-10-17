VERDICT: PASS

No blocking findings. What the diff touches, and what I checked:

- §4.5 Host and `X-Requested-By`: the middleware is unchanged and covers the three new mutating routes (`POST /api/projects/connect`, `POST /workspaces`, `POST /projects/{id}/workspace`). I probed it with TestClient. With no header, all three return 403. With `Host: evil.com` or `evil.com:4545`, GET and POST both return 403. htmx still sends the header through `hx-headers` on `<body>` in base.html. There is no CORS middleware, so a cross-origin page can't get past the preflight.
- §4.5 bind: `serve` still calls `uvicorn.run(..., host="127.0.0.1")`. Unchanged.
- Jinja autoescape: Starlette builds the env with `select_autoescape()`, which is on for every `.html` template. The new templates have no `|safe` or `Markup`. Probe: a workspace, name, and path set to `"><script>alert(1)</script>` render escaped on `/`, `/workspaces/1`, and `/projects/1`, including the `datetime="…"` attribute. Ids in `href`, `hx-post`, and `HX-Redirect` are always ints.
- Subprocesses: `app.py:81` and `cli.py:49` take argument lists, with no `shell=True` and no `os.system`. `default_branch` is rejected when it starts with `-` (`app.py:128`), and it only reaches git as the prefix of `<branch>:<path>`. `path` must be absolute, so it can't be read as an option to `-C`. Probe: `-x` and `--output=/tmp/pwn` get 422. ` -x` (leading space) is stored but can't parse as a git option. A NUL in the path or branch is caught as ValueError and shows `factory: none`, not a 500. `factory_state` has a 10 s timeout.
- SQL: every query uses `?` parameters. The only literals in the SQL are fixed status strings. The f-string in `app.py:153` builds a JSON error `detail`, not SQL.
- Secrets and logs: nothing new is logged. The CLI prints only the name, the workspace, and the URL the server returned.
- §4.3 and §4.4 (run env, `claude auth status`, `--bare`, allow and deny lists, agents reaching approve, run, or rework): this job doesn't touch them. It spawns no runs and doesn't call `claude`.
- §4.5 markdown, the code-page path checks, and the 413 limit: this job doesn't touch them. `factory_state` only calls `os.path.isfile` on a fixed relative path and never reads file contents.

## Nits (non-blocking)
- src/claude_factories/cli.py:80 — `remote get-url origin` is sent and stored as is, so an HTTPS remote with embedded credentials (`https://user:token@host/…`) puts the token in the SQLite DB. It isn't shown or logged in this job. Fix: drop the userinfo (`urllib.parse.urlsplit`) before sending, or do it on the server.
- src/claude_factories/app.py:144 — `test_cmd` is stored as free text, and the schema notes it feeds the run allowlist. This is fine for this job. Whichever later job uses it must pass it as `Bash(<test_cmd> *)` in an argument list and never as a shell string.
