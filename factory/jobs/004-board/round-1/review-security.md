VERDICT: PASS

No blocking findings.

## Checked
- §4.5 CSRF / DNS rebinding: the new `POST /projects/{id}/tasks` (src/claude_factories/app.py:390) goes through the existing `local_safety` middleware (app.py:50). A probe returned 403 for no `X-Requested-By`, for a wrong value, and for `Host: evil.com` on POST and GET. There is no CORS middleware, so a cross-origin page can't get the custom header past preflight. The form inherits `hx-headers` from `<body>`, and the drag `fetch` sets `X-Requested-By: fctl` itself (project.html:168).
- Autoescape: Starlette's `Jinja2Templates(directory=…)` uses `select_autoescape()`, which is on for `.html`. The diff adds no `|safe` and no `Markup`. A probe posted a title, project name, workspace, and path set to `"><img src=x onerror=alert(1)>`, and none of it rendered raw. The chip `title="{{ who }}: {{ verdict }}"` attribute is escaped, and the schema CHECKs limit reviewer, verdict, and stage to fixed values anyway.
- Drag script: `#board-error` is set with `textContent` only, with no `innerHTML`. The PATCH URL uses the server-rendered integer `data-id`, and the body is `JSON.stringify`. The `hx-trigger` filter is a static expression with no user data in it. No user-controlled markup reaches `#board`, so htmx can't pick up injected `hx-*` attributes from a poll swap.
- Markdown: the board never renders `description_md`, so there's no raw-HTML path. The probe confirmed the description doesn't appear on the page.
- SQL: the new `SELECT id, position FROM tasks WHERE project_id = ?` (app.py:380) uses a parameter. `create_task` is reused unchanged and is parameterized too.
- Subprocess: `factory_state` (app.py:97) is reused unchanged. It takes an argument list with a timeout, and `default_branch` is rejected at connect if it starts with `-` (app.py:177).
- §4.3/§4.4 (run env, auth, allow/deny lists, `--bare`), the bind address, code-path containment, and the 5 MB patch limit: this diff doesn't touch them.
- Logs: the diff adds no logging.
- Tests: 178 pass in W.
