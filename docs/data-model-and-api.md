# Claude Factories — Data model & API

Part of the [MVP design](MVP.md). Section numbers continue from it.

## 5. Data model

### 5.1 Tables (SQLite)
```sql
CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);

CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,              -- main checkout, absolute
  remote_url TEXT,
  default_branch TEXT NOT NULL,           -- worktrees branch from here
  test_cmd TEXT,                          -- used in templates and the run allowlist
  factory_version INTEGER,                -- NULL = factory never written
  created_at TEXT NOT NULL,
  context_md TEXT NOT NULL DEFAULT '');   -- project context: stack and conventions, atop fctl show

CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,                 -- global, shown as #12
  project_id INTEGER NOT NULL REFERENCES projects(id),
  title TEXT NOT NULL,
  description_md TEXT NOT NULL DEFAULT '',
  spec_md TEXT,                           -- spec-writer output
  status TEXT NOT NULL CHECK (status IN ('backlog','in_progress','review','done')),
  stage TEXT CHECK (stage IN ('spec','build','agent_review','approval','rework','human_review','escalated')),
  position REAL NOT NULL,                 -- order within column; Run next = lowest backlog
  branch TEXT, worktree_path TEXT,        -- NULL for standalone (/factory-submit) tasks
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT,
  import_key TEXT UNIQUE);                -- factory:<job id> for a job fctl import-factory brought in, else NULL

CREATE TABLE runs (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  session_id TEXT NOT NULL,               -- passed as --session-id; enables takeover
  pid INTEGER,
  status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','stopped')),
  exit_code INTEGER, error TEXT,
  log_path TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT);
CREATE UNIQUE INDEX one_active_run ON runs(status) WHERE status = 'running';  -- one run at a time, globally (Pro limits)

CREATE TABLE rounds (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  n INTEGER NOT NULL,                     -- 1, 2, 3… per task
  trigger TEXT NOT NULL CHECK (trigger IN ('initial','agent','human')),
  base_sha TEXT NOT NULL,                 -- diff is always against this commit
  build_md TEXT,                          -- builder notes for this round
  created_at TEXT NOT NULL,
  UNIQUE (task_id, n));

CREATE TABLE round_files (
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  path TEXT NOT NULL, old_path TEXT,      -- old_path set on rename
  change TEXT NOT NULL CHECK (change IN ('added','modified','deleted','renamed')),
  binary INTEGER NOT NULL DEFAULT 0,
  additions INTEGER NOT NULL, deletions INTEGER NOT NULL,
  patch TEXT NOT NULL,                    -- this file's section of the unified diff
  PRIMARY KEY (round_id, path));          -- round totals = SUM over this table

CREATE TABLE verdicts (
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  reviewer TEXT NOT NULL CHECK (reviewer IN ('security','ux','ui','code')),
  verdict TEXT NOT NULL CHECK (verdict IN ('PASS','CHANGES')),
  body_md TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (round_id, reviewer));      -- re-posting overwrites (safe on retry)

CREATE TABLE comments (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  author TEXT NOT NULL,                   -- 'me' or a reviewer name
  path TEXT, line INTEGER, side TEXT CHECK (side IN ('old','new')),  -- all NULL = conversation comment
  body_md TEXT NOT NULL, created_at TEXT NOT NULL);

CREATE TABLE decisions (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  actor TEXT NOT NULL CHECK (actor IN ('approver','me')),
  decision TEXT NOT NULL CHECK (decision IN ('APPROVE','ESCALATE','CHANGES_REQUESTED')),
  body_md TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);

CREATE TABLE events (                     -- status/stage history
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  actor TEXT NOT NULL,                    -- 'me', 'app', 'orchestrator'
  from_status TEXT, to_status TEXT, stage TEXT, note TEXT,
  created_at TEXT NOT NULL);

CREATE TABLE transcripts (                -- a run's Claude Code transcripts, copied when it ends (§4.4)
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES runs(id),
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  agent_type TEXT,                        -- 'orchestrator' for the run's own session, else the agent type
  name TEXT,                              -- a teammate's name, e.g. builder-12
  round INTEGER,                          -- n from "Job|Task <id>, round <n>." in its first prompt
  path TEXT NOT NULL,                     -- the copy, relative to FCTL_HOME/transcripts/
  model TEXT,
  turns INTEGER NOT NULL,
  input_tokens INTEGER NOT NULL, cache_read_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
  started_at TEXT, ended_at TEXT,
  UNIQUE (run_id, path));                 -- a re-copy updates the row
```
Relations: workspace 1–n project 1–n task. A task has 1–n runs and 1–n rounds. A run has 0–n
transcripts. A round has
1–n files, 0–4 verdicts, and 0–n comments. A task has 0–n decisions and 0–n events. The
review page's timeline is a union of events, rounds, verdicts, decisions, and comments,
ordered by `created_at`.

### 5.2 Stage → status mapping
The server derives status whenever stage is set. Every change writes an `events` row.

| stage | status | set by |
|---|---|---|
| — | backlog | me (create) |
| — | in_progress | app (run spawned) |
| `spec`, `build`, `agent_review`, `approval` | in_progress | orchestrator |
| `rework` | in_progress | app (my Request changes) |
| `human_review` | review | orchestrator (approver APPROVE), app (standalone submit) |
| `escalated` | review, highlighted | orchestrator (approver ESCALATE) |
| — | done | app (my Approve) |

A manual move on the board sets status and clears stage. It is refused with `409` while a
run is active.

---

## 6. API
JSON over `http://127.0.0.1:4545`. Mutating calls need `X-Requested-By: fctl` (§4.5).
`→` is the request body, `←` the response. `latest` can stand in for a round number.

### 6.1 Workspaces & projects
```
GET  /api/workspaces
← 200 [{"id":2,"name":"personal","projects":3}]

POST /api/workspaces                                              (+ Workspace)
→ {"name":"work"}
← 200 {"id":4,"name":"work"}                                      # an existing name returns its id

PATCH /api/projects/3                                             (move to another workspace)
→ {"workspace_id":4}
← 200 {"id":3,"workspace_id":4}                                   # 404 if either id is unknown

POST /api/projects/connect                                        (fctl connect)
→ {"path":"/Users/artem/code/api-server","workspace":"personal","name":"api-server",
   "remote_url":"git@github.com:artem/api-server.git","default_branch":"main","test_cmd":"pytest -q"}
← 200 {"id":3,"created":true,"url":"http://127.0.0.1:4545/projects/3"}

GET  /api/projects?path=/Users/artem/code/api-server             (fctl resolves cwd → project)
← 200 {"id":3,"name":"api-server","default_branch":"main","factory":"ready"}   # none|uncommitted|ready

POST /api/projects/3/factory                                      (Create factory button)
→ {"overwrite":false}
← 200 {"written":[".claude/skills/factory/SKILL.md",".claude/agents/builder.md", "…"],
       "skipped":[], "commit_hint":"git add .claude/skills/factory .claude/agents && git commit -m \"Add factory\""}

GET  /api/projects/3/context                                      (fctl context, Context page)
← 200 {"context_md":"# Stack\n- Python 3.12\n","context_html":"<h1>Stack</h1>\n<ul>…","bytes":22,"max_bytes":16384}

PUT  /api/projects/3/context                                      (fctl context set, Context page)
→ {"context_md":"# Stack\n- Python 3.12\n"}
← 200 {"context_md":"…","context_html":"…","bytes":22,"max_bytes":16384}
  # 413 {"detail":"context over 16 KB"} over 16384 UTF-8 bytes; "" clears it
  # 404 {"detail":"Project #99 not found"} for an unknown id, on GET too

POST /api/projects/3/import-factory                               (fctl import-factory, /factory approve)
→ {"job":"014-run-ui"}                                            # {} imports every job in factory/board.json
← 200 {"imported":[{"job":"014-run-ui","task_id":12,"created":true,"rounds":1,"transcripts":9}]}
  # 404 unknown project, no factory/board.json, or no such job · 422 bad board.json, job id, or patch
  # 413 a file over 5 MB · 409 the import_key belongs to another project's task

POST /api/projects/3/import                                       (Import, fctl import) → the zip as the raw body
← 200 {"task_id":12,"title":"Rate-limit login endpoint","import_key":"task:12@2026-10-17T10:03:00Z",
       "created":true,"status":"backlog","rounds":2,"transcripts":0}
  # a bundle from GET /api/tasks/{id}/export (§6.2), read like an import-factory job and keyed on import_key:
  # a second import updates that task. done and review land as they are; anything else lands in backlog (§5.2)
  # 413 a body over 50 MB, over 500 MB unpacked, or a file over 5 MB · 422 not a zip, a refused entry, bad task.json
  # 409 the import_key is another project's task, or that task has a run going · 404 unknown project
```

### 6.2 Tasks & runs
```
GET  /api/projects/3/tasks
← 200 [{"id":12,"title":"Rate-limit login endpoint","status":"review","stage":"human_review",
        "round":2,"verdicts":{"security":"PASS","ux":"PASS","ui":"PASS","code":"PASS"},
        "additions":126,"deletions":9,"run":null}]

POST /api/projects/3/tasks                                        (+ New task, fctl task add)
→ {"title":"Rate-limit login endpoint","description_md":"Max 5 failed logins/min per IP."}
← 201 {"id":12,"status":"backlog"}
  # optional "submit": {...} creates round 1 and puts the task straight in review (§7.4)

GET  /api/tasks/12                                                (fctl round, task page)
← 200 {"id":12,"status":"in_progress","stage":"agent_review","branch":"factory/12-rate-limit-login",
       "rounds":[{"n":1,"trigger":"initial","files":4,"additions":118,"deletions":9,
                  "verdicts":{"security":"CHANGES","ux":"PASS","ui":"pending","code":"PASS"}}],
       "decisions":[],"run":{"id":41,"status":"running"}}

GET  /api/tasks/12/context?round=1 | ?feedback=1                  (fctl show) → text/markdown
← 200 "# #12 Rate-limit login endpoint\n## Spec\n…\n## Round 1 — build notes\n…\n## Verdicts\n…"
  # with no query, a non-blank project context comes first: "## Project context\n…\n\n# #12 …"

PATCH /api/tasks/12                                               (fctl spec / fctl stage / board drag)
→ {"spec_md":"## Acceptance criteria\n- 6th failed login within 60s → 429\n…"}
→ {"stage":"agent_review"}
→ {"status":"backlog","position":1.5}
→ {"title":"Export CSV v2","description_md":"Columns: *id, title*"}                    (board Edit)
← 200 {"id":12,"status":"in_progress","stage":"agent_review"}     # 409 if manual move during a run
  # one group per request; a mix → 422 "send exactly one of: spec_md, stage, status with position, or title
  #   and/or description_md"
  # Edit: title, description_md, or both, in any status and during a run; status and stage stay, so no event
  # the title is trimmed, 422 {"detail":"title must not be blank"} if that leaves nothing; description_md is
  #   stored as sent, "" clears it; null or a non-string → 422 (FastAPI's list detail)

DELETE /api/tasks/12                                              (board Delete)
← 204, empty body
  # one transaction removes the task with its runs, rounds, round_files, verdicts, comments, decisions,
  #   events, and transcripts rows
  # on disk, the worktree, branch, run logs, and transcript copies stay
  # 409 {"detail":"run #41 active"} while a run is running · 404 {"detail":"Task #99 not found"}

POST /api/tasks/12/run                                            (Run, Retry, fctl run 12)
← 202 {"run_id":41,"session_id":"6f1c2e0a-…","worktree":".claude/worktrees/12-rate-limit-login"}
  # 409 if any run is active, auth isn't claude.ai, or the factory isn't committed on default_branch

POST /api/projects/3/run-next                                     (Run next, fctl run next)
← 202 {"task_id":14,"run_id":42}                                  # 404 if backlog empty

POST /api/runs/41/stop
← 200 {"id":41,"status":"stopped"}

GET  /api/runs/41/log?after=120                                   (run log panel, polled)
← 200 {"next":134,"lines":[{"t":"tool","text":"builder-12 · Bash pytest -q"},{"t":"text","text":"…"}]}

GET  /api/tasks/12/transcripts                                    (task page Agents)
← 200 [{"id":5,"run_id":41,"round":1,"agent_type":"builder","name":"builder-12","model":"claude-opus-…",
        "turns":38,"input_tokens":412,"cache_read_tokens":1830211,"output_tokens":20977,
        "started_at":"2026-10-17T10:04:11Z","ended_at":"2026-10-17T10:21:40Z"}]
  # ordered by run_id, started_at, id

GET  /api/transcripts/5[?full=1]                                  (transcript page)
← 200 {…the same fields, "task_id":12, "project_id":3, "project":"api-server", "workspace_id":2,
       "workspace":"personal",
       "messages":[{"role":"assistant","at":"…","blocks":[{"type":"text","text_html":"<p>…</p>"},
                     {"type":"thinking","text":"…"},{"type":"tool_use","name":"Bash","input":"{\n  \"command\": \"pytest -q\"\n}"}]},
                   {"role":"user","at":"…","blocks":[{"type":"tool_result","text":"3 passed","is_error":false,"truncated":false}]}]}
  # without full=1, each tool result is cut at 4096 characters with "truncated":true
  # project and workspace: its task's, as they are now (the breadcrumb); never the copy's path

GET  /api/transcripts/5/raw                                       (Download) → the copied .jsonl as an attachment
← 404 {"detail":"Transcript #99 not found"}

GET  /api/tasks/12/export[?transcripts=1]                         (Export, fctl export) → application/zip
← 200 attachment task-12.zip, every name at its root: task.json, spec.md, decision.md, feedback-<N>.md,
      round-<N>/ with build.md, diff.patch, review-<security|ux|ui|code>.md; transcripts/<run>/<…>.jsonl
  # task.json: import_key, title, description_md, status, stage, events, comments (+ transcripts)
  # transcripts are in only with ?transcripts=1: they can hold paths, env, and secrets
  # each entry's time is its row's created_at · 404 {"detail":"Task #99 not found"}
```

### 6.3 Rounds, verdicts, decisions
```
POST /api/tasks/12/rounds                                         (fctl submit 12 — builder)
→ {"base_sha":"9f2c1e4b7d0a","build_md":"Token bucket in app/limits.py …","patch":"diff --git a/…"}
← 201 {"round":2,"files_changed":4,"additions":126,"deletions":9,
       "url":"http://127.0.0.1:4545/tasks/12/review?round=2"}

GET  /api/tasks/12/rounds/latest/diff                             (fctl diff) → text/x-diff
← 200 "diff --git a/app/limits.py b/app/limits.py\nnew file mode 100644\n…"

PUT  /api/tasks/12/rounds/latest/verdicts/security                (fctl verdict)
→ {"verdict":"CHANGES","body_md":"1. app/limits.py:31 trusts X-Forwarded-For …"}
← 200 {"round":1,"reviewer":"security","verdict":"CHANGES","complete":"3/4"}

POST /api/tasks/12/comments                                       (fctl comment, inline UI comment)
→ {"round":"latest","author":"security","path":"app/limits.py","line":31,"side":"new",
   "body_md":"Use request.client.host unless behind a known proxy."}
← 201 {"id":88}

POST /api/tasks/12/decision                                       (fctl decide — approver)
→ {"decision":"APPROVE","body_md":"All 4 PASS on round 2; criteria met; tests green."}
← 201 {"id":7}

POST /api/tasks/12/request-changes                                (Request changes, fctl rework)
→ {"body_md":"Make the limit configurable via settings."}         # inline comments already posted
← 202 {"status":"in_progress","stage":"rework","run_id":43}       # run_id null for standalone tasks

POST /api/tasks/12/approve                                        (Approve, fctl approve)
→ {"body_md":""}
← 200 {"status":"done","commit_hint":"cd .claude/worktrees/12-rate-limit-login && git add -A && …"}
```

### 6.4 SPA routes and page data
The frontend server (§4.1) serves the SPA routes: `/` dashboard · `/workspaces/{id}` ·
`/projects/{id}` board · `/projects/{id}/code?path=` · `/projects/{id}/reviews?tab=closed` ·
`/projects/{id}/context` · `/projects/{id}/settings` · `/tasks/{id}` ·
`/tasks/{id}/review?round=&tab=files` · `/transcripts/{id}` · `/docs/fctl` · `/settings`. Any
other path outside `/api` gets the SPA's not-found page. `/transcripts/{id}` loads
`GET /api/transcripts/{id}` (§6.2).

Each page loads one view-model from the backend, plus the sidebar's. Markdown fields arrive
rendered as `*_html` (raw HTML off, §4.5). Unknown ids get a JSON 404.
```
GET  /api/auth                                                    (the sidebar's badge, /settings)
← 200 {"auth_method":"claude.ai","plan":"pro","runs_enabled":true,"email":"artem@example.com"}
  # auth_method, plan, and email are null unless the login is claude.ai

POST /api/auth/login                                              (Settings: Log in with Claude)
← 200 {"url":"https://claude.ai/oauth/authorize?…"}
  # starts `claude auth login --claudeai` (§4.3), stopping a pending one first
  # 500 {"detail":"claude auth login printed no sign-in URL: Error: …"} with claude's last line

POST /api/auth/login/code                                         (Settings: Submit code)
→ {"code":"<code>#<state>"}
← 200 {"auth_method":"claude.ai","plan":"pro","runs_enabled":true,"email":"artem@example.com"}
  # the code goes to the pending login's stdin; the 200 is GET /api/auth's body, checked afresh
  # 409 {"detail":"no login in progress"}
  # 422 {"detail":"Login failed: Invalid code"}: claude refused it; or the code isn't
  #     <code>#<state>, and the login stays pending
  # 500 {"detail":"claude auth login didn't finish"}: no exit within 60 s, so the login is stopped

GET  /api/pages/dashboard                       tiles, the waiting and escalated lists ({id, title, project_id,
                                                project, round, since}, newest since first), open tasks per
                                                workspace → project, rounds per task
GET  /api/pages/workspaces/{id}                 projects with path, counts per status, factory state, last activity
GET  /api/pages/projects/{id}                   the project (path, remote_url, default branch, test_cmd, workspace),
                                                factory state and hint, board cards with stage, branch,
                                                description_md, chips per round, +/−, waiting, escalated, stalled
GET  /api/pages/tasks/{id}                      the task with project_id, project, workspace_id, and workspace (its
                                                project's now), spec_html, rounds, decision, history, the active run
                                                and takeover command, transcripts (as GET /api/tasks/{id}/transcripts)
GET  /api/pages/tasks/{id}/review?round=        the same task plus commit_hint; timeline; files with diff rows carrying
                                                side, old/new line, kind, text, and the path:side:line anchor; inline
                                                comments
GET  /api/pages/projects/{id}/code?path=        the project {id, name, path, workspace_id, workspace}, also on a git
                                                failure; tree, README or file, branch
← 404 {"detail":"Task #99 not found"}

GET  /api/pages/sidebar                                           (every route but the two below)
GET  /api/pages/sidebar?task=12                                   (/tasks/12, /tasks/12/review)
GET  /api/pages/sidebar?transcript=5                              (/transcripts/5)
← 200 {"workspaces":[{"id":2,"name":"personal","projects":[
          {"id":3,"name":"api-server","review":2,"running":1,"escalated":1},
          {"id":7,"name":"web","review":0,"running":0,"escalated":0}]},
        {"id":4,"name":"work","projects":[]}],
       "current":{"workspace_id":2,"project_id":3}}
  # loaded on every page load and navigation, never polled
  # every workspace by name, the empty ones too; projects by name, then id
  # review: tasks at stage human_review or escalated · escalated: at escalated ·
  #   running: tasks with a running run (§5.2)
  # current: the workspace and project of the task (?task=) or of the transcript's task
  #   (?transcript=); null with no query, and null (still 200, never 404) for an unknown id
  # a non-integer id gets the 422; there is no ?project=: the SPA finds it in workspaces

GET  /api/docs/fctl                                               (/docs/fctl)
← 200 {"body_html":"<h2 id=\"fctl-serve\">fctl serve</h2>…",
       "headings":[{"id":"fctl-serve","text":"fctl serve","level":2}]}
```
