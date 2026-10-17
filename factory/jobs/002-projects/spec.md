# 002-projects: Projects (connect, workspaces, factory state, pages)

## Goal
Register local git repos as projects grouped into workspaces. `fctl connect` runs inside a repo,
or any worktree or subdirectory of it. It collects the main checkout's path, name, remote, and
default branch and upserts the project through `POST /api/projects/connect`. The API also lists
workspaces and finds a project by path, with its factory state (none / uncommitted / ready).
The workspace page lists the projects. `+ Workspace` creates a workspace, and a minimal project
page moves a project to another workspace.

## Implements
- `docs/MVP.md §2`: a Workspace is a named group of projects. A Project is one local git repo, identified by its main checkout path.
- `docs/MVP.md §3.1`: steps 3–4. Collect path, name (directory name), remote (`git remote get-url origin`), and default branch (`origin/HEAD`, falling back to the current branch). Print `Connected <name> (<workspace>) → <url>`. A rerun updates the project, and an unknown workspace is created on the spot.
- `docs/MVP.md §3.2 step 4`: "committed" means `git cat-file -e <default_branch>:.claude/skills/factory/SKILL.md` succeeds.
- `docs/MVP.md §4.5`: the new mutating routes sit behind the existing Host and `X-Requested-By` middleware. No middleware change.
- `docs/MVP.md §10 assumption 11`: `git` is on PATH.
- `docs/data-model-and-api.md §5.1`: `workspaces` and `projects` rows, unchanged schema. `tasks` is read only, for the per-status counts.
- `docs/data-model-and-api.md §6.1`: `GET /api/workspaces`, `POST /api/projects/connect`, `GET /api/projects?path=`. Not `POST /api/projects/{id}/factory`.
- `docs/data-model-and-api.md §6.4`: the HTML routes `/workspaces/{id}` and `/projects/{id}` (a stub, see Q11).
- `docs/claude-code.md §7.2`: `fctl connect --workspace W [--test-cmd C]`.
- `docs/claude-code.md §7.4 step 1`: the main repo comes from `git rev-parse --path-format=absolute --git-common-dir`, so connecting works the same from a worktree.
- `docs/ui.md §8 item 2`: the workspace page. One row per project with name, path, counts per status, factory state, and last activity. `+ Workspace`, and moving a project from its page. Light and dark follow the system (§8 intro).

## Acceptance criteria

`GET /api/workspaces`
- [ ] AC1: empty DB → 200 `[]`.
- [ ] AC2: workspaces `work` (1 project), `personal` (2), and `empty` (0) → 200 `[{"id":…,"name":"empty","projects":0},{"id":…,"name":"personal","projects":2},{"id":…,"name":"work","projects":1}]`, ordered by name (Q9).

`POST /api/projects/connect`
- [ ] AC3: the §6.1 body with an unknown workspace → 200 `{"id":<id>,"created":true,"url":"http://127.0.0.1:4545/projects/<id>"}` (Q7). The workspace gets one `workspaces` row. The project gets one `projects` row holding `path`, `name`, `remote_url`, `default_branch`, and `test_cmd` as sent, that workspace's id, `factory_version` NULL, and `created_at` set (Q14).
- [ ] AC4: a second project connected to an existing workspace → no new `workspaces` row, and both projects have the same `workspace_id`.
- [ ] AC5: a rerun with the same `path` and a new `name`, `remote_url`, `default_branch`, and `test_cmd` → 200 with the same `id` and `"created":false`. There is still exactly one `projects` row, and it holds the new values.
- [ ] AC6: a rerun with `"test_cmd": null` → the stored `test_cmd` stays (Q4).
- [ ] AC7: a rerun with a different `workspace` → the project's `workspace_id` is that workspace, which is created if it's unknown (Q4).
- [ ] AC8: `"workspace": " personal "` → the project joins the workspace named `personal` (Q5).
- [ ] AC9: one invalid field per request: relative `path`, blank `workspace`, blank `name`, empty `default_branch`, or a `default_branch` starting with `-` → 422 with a string `detail` (Q5), and no `workspaces` or `projects` row is written.

`GET /api/projects?path=` and factory state
- [ ] AC10: the path of a connected project → 200 with exactly the keys `id`, `name`, `default_branch`, `factory`.
- [ ] AC11: a path that isn't connected → 404 `{"detail":"no project at <path>"}` (Q8).
- [ ] AC12: a real repo with `.claude/skills/factory/SKILL.md` committed on `default_branch` → `"factory":"ready"`.
- [ ] AC13: the file is in the main checkout but not committed on `default_branch` (untracked, or committed only on another branch) → `"factory":"uncommitted"` (Q6).
- [ ] AC14: the file is neither on disk nor on `default_branch` → `"factory":"none"`.
- [ ] AC15: the project's path no longer exists → 200 with `"factory":"none"`, not 500.

Workspace page `/workspaces/{id}`
- [ ] AC16: → 200 HTML from a template that extends `base.html`. The heading is the workspace name, there's a link to `/`, and there's one table row per project ordered by name (Q12). Each row has the name linking to `/projects/<id>`, the path, the four status counts, the factory state, and last activity.
- [ ] AC17: `tasks` rows inserted directly (project A: 2 backlog, 1 review, 1 done; project B: 1 backlog) → A's row shows Backlog 2, In progress 0, Review 1, Done 1. B's tasks aren't counted in A's row.
- [ ] AC18: a project whose SKILL.md is committed and one with no factory → their rows show `ready` and `none`.
- [ ] AC19: last activity is the latest of the project's `created_at` and its tasks' `updated_at`, rendered as in Q12.
- [ ] AC20: a workspace with no projects → 200, no table, and the empty-state text from Q12.
- [ ] AC21: `GET /workspaces/999` → 404.
- [ ] AC22: the page has the `+ Workspace` form: `hx-post="/workspaces"`, a text input `name` with `required`, and a button labeled `+ Workspace`.

`+ Workspace` (Q10)
- [ ] AC23: `POST /workspaces` with form field `name=work` and `X-Requested-By: fctl` → 204 with `HX-Redirect: /workspaces/<new id>`, and a `workspaces` row named `work` exists.
- [ ] AC24: posting a name that already exists → 204 with `HX-Redirect` to the existing workspace's id. No new row.
- [ ] AC25: an empty or whitespace-only `name` → 422, and no row is written.

Project page `/projects/{id}` and moving (Q10, Q11)
- [ ] AC26: → 200 HTML with the heading `<name> · <workspace name>`, where the workspace name links to `/workspaces/<workspace id>`. The page shows the path and has a form `hx-post="/projects/<id>/workspace"` with a `<select name="workspace_id">` that lists every workspace, the current one `selected`.
- [ ] AC27: `GET /projects/999` → 404.
- [ ] AC28: `POST /projects/<id>/workspace` with `workspace_id=<other id>` → 204 with `HX-Redirect: /projects/<id>`. The project's `workspace_id` is now the other one: the other workspace's page lists the project and the old one doesn't.
- [ ] AC29: an unknown project id or an unknown `workspace_id` → 404. A non-integer `workspace_id` → 422. In each case the project's `workspace_id` is unchanged.

Index `/` (Q13)
- [ ] AC30: with workspaces → each one is listed as `<a href="/workspaces/<id>">name</a>` with its project count. With none → the page still says "No projects yet."

`fctl connect` (`cli.main([...])` in a temp repo, against a recording HTTP server like 001's `server` fixture)
- [ ] AC31: in a clone of a local bare repo whose `origin/HEAD` is `origin/trunk`, with the checkout switched to another branch, `fctl connect --workspace personal --test-cmd "pytest -q"` → exactly one `POST /api/projects/connect` with body `{"path":<checkout realpath>,"workspace":"personal","name":<checkout dir name>,"remote_url":<origin url>,"default_branch":"trunk","test_cmd":"pytest -q"}`. Then stdout is `Connected <name> (personal) → <url from the response>` and the command exits 0.
- [ ] AC32: without `--test-cmd` → the body has `"test_cmd": null`.
- [ ] AC33: in a repo with no `origin` remote → `"remote_url": null`, and `default_branch` is the main checkout's current branch (Q2).
- [ ] AC34: run from a worktree at `<repo>/.claude/worktrees/x` on branch `factory/x`, in a repo with no `origin/HEAD` whose main checkout is on `main` → `path` and `name` are the main checkout's, and `default_branch` is `main`, not `factory/x` (Q1, Q2).
- [ ] AC35: run from a subdirectory of the checkout → `path` is the checkout root.
- [ ] AC36: run outside any git repo → exit 1, stderr `fctl: not inside a git repository: <cwd>` (Q3), and no request is sent.
- [ ] AC37: in a repo with no `origin/HEAD` and a detached HEAD in the main checkout → exit 1 with the Q2 message on stderr, and no request is sent.
- [ ] AC38: `fctl connect` without `--workspace` → exit 2, usage on stderr.

## Files
- `src/claude_factories/app.py`: the three `/api` routes, the two form routes (Q10), and the page routes `/workspaces/{id}` and `/projects/{id}`. `/` gets the workspace list. Also a `factory_state(path, default_branch)` helper. Every `git` call is a `subprocess.run([...])` argument list, never a shell string.
- `src/claude_factories/db.py`: a `now()` timestamp helper (Q14).
- `src/claude_factories/cli.py`: the `connect` subcommand and its git helpers, stdlib only (001's AC3 must keep passing). It reuses `api()`.
- `src/claude_factories/templates/workspace.html`, `templates/project.html`: new, both extend `base.html`.
- `src/claude_factories/templates/index.html`: the workspace list (Q13).
- `src/claude_factories/templates/base.html`: a small `<style>` block (Q16).
- `tests/test_projects.py`: the API, factory state, pages, and form routes.
- `tests/test_cli.py`: the `fctl connect` tests, which reuse its `server` fixture.
- `tests/conftest.py`: git isolation (Q17), plus a temp-repo helper if useful.

No new dependencies. Form bodies are parsed with stdlib `urllib.parse` (Q10).

## Out of scope
- `POST /api/projects/{id}/factory`, the Create factory button, templates, `factory_version` writes, and the commit hint (011).
- The project board itself: columns, cards, the header's Code link, factory state, `+ New task`, and Run next (004). This job's `/projects/{id}` is the stub from Q11.
- The task API and `fctl task add` (003). The counts here read `tasks` with plain SQL.
- `fctl submit` and resolving the project from inside it (005), though it will reuse this job's main-checkout resolution.
- The `/factory-connect` skill and `fctl setup` (015).
- The dashboard at `/` (017), the code page (016), and the `Claude: Pro ✓` header (014).
- Renaming or deleting workspaces, deleting projects, JSON endpoints for creating workspaces or moving projects, and a CLI for either.
- markdown-it-py: nothing in this job renders markdown.
- Custom HTML error pages (Q15).

## Open questions
- Q1: §3.1 says the path comes from `--show-toplevel`, but §7.4 and the request use `--git-common-dir`, which works from a worktree. Default: run `git rev-parse --path-format=absolute --git-common-dir` in the cwd. If the result's basename is `.git`, the main checkout is its parent. Otherwise (a bare repo or a separate git dir), fall back to `git rev-parse --show-toplevel`. Apply `os.path.realpath` to the result. Run every later git call with `git -C <main checkout>`.
- Q2: docs don't give the exact commands. Default: `git -C <main> symbolic-ref --short refs/remotes/origin/HEAD`, with the leading `origin/` stripped. If that fails, use `git -C <main> branch --show-current`, which is the main checkout's branch, not the worktree's. If that's empty too (detached HEAD), exit 1 with `fctl: can't tell the default branch: no origin/HEAD and HEAD is detached`. Remote: `git -C <main> remote get-url origin`, and null if that fails.
- Q3: there's no error text for running outside a repo. Default: `fctl: not inside a git repository: <cwd>`, exit 1.
- Q4: "Running it again updates the project" doesn't say which fields. Default: the path is the key, and a rerun overwrites `workspace_id`, `name`, `remote_url`, and `default_branch`. So a rerun moves the project to the named workspace, even if I moved it in the UI. `fctl` always sends all six keys, with `test_cmd` null when `--test-cmd` is omitted. A null `test_cmd` keeps the stored value, so omitting the flag can't clear it. `created_at` never changes.
- Q5: docs don't validate the body. Default: `workspace` and `name` are stripped and must be non-empty. `path` must be absolute (`os.path.isabs`), and the server doesn't check that it exists. `default_branch` must be non-empty and must not start with `-`, because it is passed to `git cat-file` as an argument. Each failure is a 422 whose `detail` is a string naming the problem, for example `path must be absolute`. `fctl` then prints `fctl: 422 path must be absolute`.
- Q6: docs define only "committed" for the factory state. Default: `ready` if `git -C <path> cat-file -e <default_branch>:.claude/skills/factory/SKILL.md` exits 0. Otherwise `uncommitted` if `<path>/.claude/skills/factory/SKILL.md` exists on disk. Otherwise `none`. Any git failure, such as a missing path or not a repo, counts as not committed. `factory_version` isn't consulted, because 011 writes it and hand-written factories (like this repo's) never set it.
- Q7: docs don't say where the `url` host comes from. Default: `str(request.base_url)` + `projects/<id>`. `fctl` prints the same `Connected …` line on a first connect and on a rerun.
- Q8: docs don't say how `?path=` matches. Default: an exact string match on the stored path, with no normalization on the server (`fctl` already sends realpaths). An unknown path → 404 `no project at <path>`. A missing parameter → FastAPI's own 422.
- Q9: docs don't order the workspace list. Default: by name. Workspaces with 0 projects are included.
- Q10: docs give no endpoint for `+ Workspace` or for moving a project. Plain HTML forms can't send `X-Requested-By`, and Starlette's `request.form()` needs python-multipart, which isn't in the stack. Default: two htmx form routes, `POST /workspaces` (field `name`) and `POST /projects/{id}/workspace` (field `workspace_id`). Both read `await request.body()` and parse it with `urllib.parse.parse_qs`. Success is a 204 with `HX-Redirect`. `+ Workspace` with an existing name just redirects to that workspace (get-or-create, the same as connect). The input also has native `required`.
- Q11: §8 item 2 puts "move to another workspace" on the project's page, and `/projects/{id}` is 004's board. Default: this job creates a minimal `project.html` with the `<name> · <workspace>` heading (the §8.1 header format), the path, and the move form. 004 adds the board to that page. The connect `url` then resolves to a real page.
- Q12: the workspace page details aren't decided. Default: project rows are ordered by name. The count columns are headed Backlog, In progress, Review, and Done (the §8.1 column names). Factory state shows as the plain word `none`, `uncommitted`, or `ready`. Last activity is the latest of the project's `created_at` and its tasks' `updated_at`, rendered as `<time datetime="<stored ISO>">YYYY-MM-DD HH:MM</time>` in the server's local time zone (the test computes the expected value with `datetime.fromisoformat(...).astimezone()`). The empty state is `No projects yet. Run fctl connect --workspace <name> inside a repo.` There's no workspace switcher. The page links to `/`, which lists all workspaces (Q13).
- Q13: `/` is a placeholder until 017, and its "No projects yet." would be wrong after a connect. Default: list the workspaces as links with their project counts, and keep "No projects yet." when there are none.
- Q14: docs don't fix a timestamp format. Default: `db.now()` returns UTC ISO 8601 with seconds and a `Z` suffix, for example `2026-10-17T12:22:23Z` (the same as board.json).
- Q15: there's no error-page design. Default: unknown ids raise FastAPI's `HTTPException(404)`, which gives the JSON `{"detail":"Not Found"}` body. No HTML error template.
- Q16: these are the first pages with tables and forms, and there's no stylesheet. Default: a short `<style>` block in `base.html`: system font, table cell padding, and muted secondary text through the `GrayText` system color. Hard-coded colors are not allowed, so light and dark keep following `color-scheme`. No `app.css` file.
- Q17: the tests need real git repos, but the user's global git config (for example `commit.gpgsign`) could break the test commits. Default: the autouse fixture sets `GIT_CONFIG_GLOBAL` to an empty temp file, `GIT_CONFIG_NOSYSTEM=1`, and `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL`. Repos are created with `git init -b main`. "Remotes" are local bare repos on disk, so there are no network calls.
