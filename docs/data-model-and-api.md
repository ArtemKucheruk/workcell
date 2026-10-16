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
  created_at TEXT NOT NULL);

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
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT);

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
```
Relations: workspace 1–n project 1–n task. A task has 1–n runs and 1–n rounds. A round has
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

PATCH /api/tasks/12                                               (fctl spec / fctl stage / board drag)
→ {"spec_md":"## Acceptance criteria\n- 6th failed login within 60s → 429\n…"}
→ {"stage":"agent_review"}
→ {"status":"backlog","position":1.5}
← 200 {"id":12,"status":"in_progress","stage":"agent_review"}     # 409 if manual move during a run

POST /api/tasks/12/run                                            (Run, Retry, fctl run 12)
← 202 {"run_id":41,"session_id":"6f1c2e0a-…","worktree":".claude/worktrees/12-rate-limit-login"}
  # 409 if any run is active, auth isn't claude.ai, or the factory isn't committed on default_branch

POST /api/projects/3/run-next                                     (Run next, fctl run next)
← 202 {"task_id":14,"run_id":42}                                  # 404 if backlog empty

POST /api/runs/41/stop
← 200 {"id":41,"status":"stopped"}

GET  /api/runs/41/log?after=120                                   (run log panel, polled)
← 200 {"next":134,"lines":[{"t":"tool","text":"builder-12 · Bash pytest -q"},{"t":"text","text":"…"}]}
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

### 6.4 HTML routes
`/` dashboard · `/workspaces/{id}` · `/projects/{id}` board · `/projects/{id}/code?path=` ·
`/tasks/{id}` · `/tasks/{id}/review?round=&tab=files`
