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

CREATE TABLE factories (                  -- a project's named factory designs (§6.1), edited on the canvas
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  graph TEXT NOT NULL,                    -- the compact JSON of §6.1's <Graph>
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX factories_name ON factories(project_id, name);  -- a name once per project

CREATE TABLE claude_accounts (            -- Claude logins (MVP §4.6), each in its own CLAUDE_CONFIG_DIR
  id INTEGER PRIMARY KEY,
  config_dir TEXT NOT NULL UNIQUE,        -- absolute: ~/.claude for the first, FCTL_HOME/claude-accounts/… if added
  active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
  created_at TEXT NOT NULL);
CREATE UNIQUE INDEX one_active_account ON claude_accounts(active) WHERE active = 1;  -- the one runs use, or none
```
Relations: workspace 1–n project 1–n task. A project has 0–n factories, removed with it (ON DELETE CASCADE).
A task has 1–n runs and 1–n rounds. A run uses the active Claude account's config dir, and no column records
which. A run has 0–n
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

PATCH /api/workspaces/4                                           (sidebar Rename, workspace Settings Save)
→ {"name":"work"}
← 200 {"id":4,"name":"work"}
  # name is trimmed: 422 {"detail":"name must not be blank"}; missing, null, or not a string → 422 FastAPI's list detail
  # 409 {"detail":"workspace work already exists"} when another workspace has that name; its own name → 200
  # 404 {"detail":"Workspace #99 not found"}

DELETE /api/workspaces/4                                          (sidebar Delete, workspace Settings Danger zone)
← 204, empty body
  # 409 {"detail":"workspace personal still holds 2 projects; move or delete them first"}  ("1 project" for one)
  # 404 {"detail":"Workspace #99 not found"}

PATCH /api/projects/3                                             (Settings, sidebar Rename and Move)
→ {"workspace_id":4}                                              (move to another workspace)
→ {"name":"api-server"}
→ {"test_cmd":"pytest -q"}
→ any non-empty subset of {"workspace_id": 4, "name": "api-server", "test_cmd": "pytest -q"}, applied together
← 200 {"id":3,"workspace_id":4,"name":"api-server","test_cmd":"pytest -q"}   # the project after the update
                                                                              # id, workspace_id: int; name: str; test_cmd: str | null
  # name is trimmed: 422 {"detail":"name must not be blank"} if nothing is left
  # test_cmd is trimmed, and blank stores NULL, returned as "test_cmd": null
  # 422 {"detail":"send at least one of: workspace_id, name, test_cmd"} for {} (or only unknown keys)
  # 422 FastAPI's list detail: any of the three sent as null or the wrong type, or workspace_id out of SQLite's range
  # 404 {"detail":"Not Found"} for an unknown project or workspace_id (unchanged), with nothing written
  # allowed in any state, also while a run is going (no 409)
  # fctl connect, rerun in the repo, sets the name back to the directory's, and the test command when it passes one

DELETE /api/projects/3                                            (sidebar Delete, project Settings Danger zone)
← 204, empty body
  # one transaction removes the project, its factories, its tasks, and each task's runs, rounds, round_files,
  #   verdicts, comments, decisions, events, and transcripts rows
  # on disk, the repo, its worktrees and branches, run logs, and transcript copies stay
  # 409 {"detail":"run #41 active"} while one of its tasks has a running run
  # 404 {"detail":"Project #99 not found"}

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

GET  /api/projects/3/factories                                    (Factories list)
← 200 [{"id":7,"name":"default","nodes":10,"created_at":"2026-10-21T08:00:00Z","updated_at":"2026-10-21T09:30:00Z"}]
  # by name, then id; [] with none. nodes = len(graph.nodes), start and conditions included. No graph here.
  # 404 {"detail":"Project #99 not found"}

POST /api/projects/3/factories                                    (+ New factory)
→ {"name":"default"}
← 201 <Factory>, whose graph is the default graph (below), with created_at = updated_at
  # name is trimmed: 422 {"detail":"name must not be blank"}; missing, null, or not a string → 422 FastAPI's list detail
  # 409 {"detail":"factory default already exists"} when this project has a factory by that name (exact match after trim)
  # 404 {"detail":"Project #99 not found"}

GET  /api/factories/7                                             (designer)
← 200 <Factory>
  # 404 {"detail":"Factory #99 not found"}

PUT  /api/factories/7                                             (designer Save, list Rename)
→ {"graph":<Graph>}  |  {"name":"nightly"}  |  both, applied together
← 200 <Factory> after the update; updated_at is now, created_at unchanged
  # 422 {"detail":"send at least one of: name, graph"} for {} or only unknown keys
  # name or graph sent as null or the wrong type → 422 FastAPI's list detail
  # name: trimmed, blank → 422 as POST; 409 {"detail":"factory nightly already exists"} when another factory of the
  #   same project has it; its own name → 200
  # graph: shape errors → 422 FastAPI's list detail, then the rules below → 422 with a string detail
  # every 4xx writes nothing
  # 404 {"detail":"Factory #99 not found"}

DELETE /api/factories/7                                           (list Delete)
← 204, empty body · 404 {"detail":"Factory #99 not found"}

GET  /api/factories/7/files                                       (designer Files)
← 200 [{"path":".claude/skills/factory/SKILL.md","content":"---\nname: factory\n…"},
       {"path":".claude/agents/spec-writer.md","content":"---\nname: spec-writer\n…"}, …]
  # the stored graph compiled (docs/claude-code.md §7.3), never unsaved designer state. path: relative to the
  #   repo root with "/". SKILL.md first, then one file per agent node in node order (reachable or not)
  # 404 {"detail":"Factory #99 not found"}
  # 409 {"detail":"no test command: in the repo, run fctl connect --workspace personal --test-cmd \"<your test command>\""}
  # 422 {"detail":"agent linter needs a description"}, or another compile refusal (§7.3)
  # checked in that order: 404, 409, 422

GET  /api/factories/7/download                                    (Files → Download .zip, a plain link)
← 200 application/zip, Content-Disposition: attachment; filename="api-server-default.zip"
  # the files above as deflated entries, same paths and order; the name is {project slug}-{factory slug}.zip,
  #   both slugged as §7.3 slugs a factory's name, with an empty project slug → project
  # 404 / 409 / 422 as JSON, as above

POST /api/factories/7/write                                       (Files → Write to repo)
→ {"overwrite":false}                                             # {} means false
← 200 {"written":[".claude/skills/factory/SKILL.md", …],"skipped":[…],
       "commit_hint":"git add .claude/skills/factory .claude/agents && git commit -m \"Add factory\""}
  # POST /api/projects/{id}/factory's writer and shape; written and skipped in the files' order, and the hint
  #   names .claude/skills/{factory slug}. It doesn't set factory_version
  # 404, 409 no test command, and 422 compile refusals as above, then the path checks, before any write:
  # 409 {"detail":"/Users/artem/code/api-server is not a directory"}
  # 409 {"detail":".claude/agents/spec-writer.md resolves outside the project"}
  # 409 {"detail":".claude/skills is a symlink"}   (any component from .claude down; Create factory too)

<Factory> = {"id":7,"project_id":3,"project":"api-server","workspace_id":2,"workspace":"personal",
             "name":"default","graph":<Graph>,"created_at":"…","updated_at":"…"}
             # project and workspace: the names as they are now (for the breadcrumb)
```

**Factory graphs.** A factory is a design: it reaches `.claude/` only through Write to repo, and runs use
`.claude/skills/factory/` (docs/MVP.md §3.2). The graph uses React Flow's shape. Only the keys below are stored and returned, and any others (`selected`, `measured`,
`dragging`, an edge's `type` or `targetHandle`, extra `data` keys) are dropped:
```
<Graph> = {"nodes":[<Node>…],"edges":[<Edge>…]}
<Node>  = {"id":"builder","type":"builder","position":{"x":500,"y":0},"data":{…}}
          # id: a non-empty string; position.x, position.y: finite numbers
<Edge>  = {"id":"e3","source":"builder","sourceHandle":null,"target":"review-security"}
          # id, source, target: non-empty strings; sourceHandle: "yes" or "no" when it leaves a condition, else null
          #   (left out = null)

type          data                                                  palette label        card title
start         {}                                                    (none)               Start
spec_writer   <Agent>                                               Spec writer          data.name
builder       <Agent> + "side": "backend" | "frontend" | "both"     Builder              data.name
reviewer      <Agent> + "focus": "security"|"ux"|"ui"|"code"|"custom"  Reviewer          data.name
approver      <Agent>                                               Approver             data.name
custom_agent  <Agent>                                               Custom agent         data.name
all_pass      {}       yes: every verdict on the latest round is PASS   All reviews PASS     All reviews PASS?
any_changes   {}       yes: any verdict on the latest round is CHANGES  Any review CHANGES   Any review CHANGES?
rounds_below  {"n":2}  yes: this run has used fewer than n rounds; n an integer ≥ 1
                                                                    Rounds used < N      Rounds used < 2?
approved      {}       yes: the approver's decision is APPROVE          Decision APPROVE     Decision APPROVE?

<Agent> = {"name":"builder","description":"…","model":"inherit"|"opus"|"sonnet"|"haiku",
           "tools":["Read","Edit"],"prompt":"…markdown…"}        # all five keys required
```
The five agent types are spec_writer, builder, reviewer, approver, and custom_agent. Conditions have two source
handles, `yes` and `no`. Agents have one target and one unnamed source handle, and start has only an unnamed source
handle.

Rules, checked after the shape, in this order. The first rule that fails answers with its 422 detail:
1. The compact UTF-8 JSON of the graph as stored is over 262144 bytes (`MAX_GRAPH`) → `graph over 256 KB`.
2. The start node count isn't 1 → `graph needs exactly one start node, not 2` (or `not 0`).
3. A repeated node id → `two nodes have id builder`. A repeated edge id → `two edges have id e3`.
4. An agent name that doesn't match `^[a-z0-9]+(-[a-z0-9]+)*$` → `agent name "Spec Writer" must be a slug: a-z, 0-9, and single hyphens`.
5. Two agents with the same name → `two agents are named builder`.
6. Each edge, in list order:
   - `edge e3 starts at no node x9`
   - `edge e3 ends at no node x9`
   - `edge e3 leads into start, which takes no input`
   - `edge e3 leaves condition all-pass from neither yes nor no` (a condition source whose sourceHandle is anything but `yes` or `no`, null included)
   - `edge e3 leaves builder from handle yes, but only conditions have handles` (a non-condition source with a non-null sourceHandle)

Anything else is allowed and stored: orphans, cycles, a handle with two edges, a condition missing a branch. What
the compile accepts, and the 422 it answers otherwise, is in `docs/claude-code.md §7.3`.

The default graph has 10 nodes. Node ids are `start`, the agent names, `all-pass`, and `rounds`. Each agent's
`description`, `model`, `tools` (the frontmatter list split on `,`), and `prompt` (the text after the frontmatter,
unrendered, so `{{ test_cmd }}` stays) come from its template in `factory_templates/agents/`. It is laid out left to
right in loop order:
```
start → spec-writer (spec_writer) → builder (builder, side both)
builder → review-security, review-ux, review-ui, review-code (reviewer, focus security / ux / ui / code)
each reviewer → all-pass (all_pass)
all-pass yes → approver (approver)          all-pass no → rounds (rounds_below, n 2)
rounds yes → builder                        rounds no → approver
```
That makes 14 edges.

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
`/workspaces/{id}/settings` · `/projects/{id}` board · `/projects/{id}/code?path=&branch=` ·
`/projects/{id}/reviews?tab=closed` · `/projects/{id}/context` · `/projects/{id}/factories` ·
`/projects/{id}/factories/{fid}` · `/projects/{id}/settings` ·
`/tasks/{id}` · `/tasks/{id}/review?round=&tab=files` · `/transcripts/{id}` · `/agents` ·
`/docs/fctl` · `/settings`. Any other path outside `/api` gets the SPA's not-found page.
`/agents` loads `GET /api/pages/agents`. `/transcripts/{id}` loads `GET /api/transcripts/{id}` (§6.2), and `/workspaces/{id}/settings` loads
`GET /api/pages/workspaces/{id}`, as `/workspaces/{id}` does. `/projects/{id}/factories` loads
`GET /api/projects/{id}/factories` (§6.1), plus `GET /api/pages/projects/{id}` for its header, and the designer at
`/projects/{id}/factories/{fid}` loads `GET /api/factories/{fid}` (§6.1).

Each page loads one view-model from the backend, plus the sidebar's. Markdown fields arrive
rendered as `*_html` (raw HTML off, §4.5). Unknown ids get a JSON 404.
```
GET  /api/auth                                                    (the sidebar's badge)
← 200 {"auth_method":"claude.ai","plan":"pro","runs_enabled":true,"email":"artem@example.com"}
  # the active Claude account, checked in its config dir and cached 60 s; auth_method, plan, and
  #   email are null unless its login is claude.ai
  # no active account → {"auth_method":null,"plan":null,"runs_enabled":false,"email":null}, claude not called

POST /api/auth/login                                              (Settings: + Add account, Log in, Log in again)
→ {"account_id":2}                      log account #2 in again, in its own config dir
→ no body, {}, or {"account_id":null}   a new account, in a fresh dir under FCTL_HOME/claude-accounts/ (0700)
← 200 {"url":"https://claude.ai/oauth/authorize?…","account_id":3}
  # starts `claude auth login --claudeai` (§4.3), stopping a pending one first; account_id is the
  #   account the login is for, the new row's for a new account, which is added once the URL has arrived
  #   and is active only if no account is
  # 404 {"detail":"Claude account #9 not found"}
  # 500 {"detail":"claude auth login printed no sign-in URL: Error: …"} with claude's last line; for a
  #     new account, no row is added and its fresh dir is removed

POST /api/auth/login/code                                         (Settings: Submit code)
→ {"code":"<code>#<state>","account_id":3}                        account_id optional
← 200 {"auth_method":"claude.ai","plan":"pro","runs_enabled":true,"email":"artem@example.com"}
  # the code goes to the pending login's stdin; the 200 is GET /api/auth's body (the active account),
  #   checked afresh
  # 409 {"detail":"no login in progress"}: none is pending, or account_id isn't the pending login's,
  #     which then stays pending
  # 422 {"detail":"Login failed: Invalid code"}: claude refused it; or the code isn't
  #     <code>#<state>, and the login stays pending
  # 500 {"detail":"claude auth login didn't finish"}: no exit within 60 s, so the login is stopped

GET  /api/auth/accounts                                           (Settings: the list, loaded once)
← 200 [{"id":1,"config_dir":"/home/me/.claude","active":true,"signed_in":true,
        "auth_method":"claude.ai","plan":"pro","email":"artem@example.com"},
       {"id":3,"config_dir":"/home/me/.claude-factories/claude-accounts/k3j2h1x9","active":false,
        "signed_in":false,"auth_method":null,"plan":null,"email":null}]
  # every account by id, [] with none; each checked afresh with `claude auth status` in its own
  #   config dir, uncached; signed_in, auth_method, plan, and email follow GET /api/auth's rules for
  #   runs_enabled, auth_method, plan, and email

POST /api/auth/accounts/{id}/activate                             (Settings: Make active)
← 200 {"auth_method":"claude.ai","plan":"max","runs_enabled":true,"email":"me@work.example"}
  # the account runs use from now on; the 200 is GET /api/auth's body, now for it, checked afresh
  # already active: 200, nothing changes · a signed-out account may be made active
  # 404 {"detail":"Claude account #9 not found"}
  # 409 {"detail":"a run is active"}: a run has status running (§4.4), and nothing changes

DELETE /api/auth/accounts/{id}                                    (Settings: Disconnect)
← 204
  # stops a pending login for this account, runs `claude auth logout` (§4.3) in its config dir, deletes
  #   the dir only if it lies inside FCTL_HOME/claude-accounts/ and isn't a symlink (so never ~/.claude),
  #   then the row; deleting the active account leaves none active. The 60 s cache is cleared, after a
  #   failed logout too
  # 404 {"detail":"Claude account #9 not found"}
  # 409 {"detail":"a run is active"}: a run has status running (§4.4), and nothing else happens
  # 500 {"detail":"claude auth logout failed: Error: …"} with claude's last line, or
  #     "claude auth logout exited with code <n>" when it printed nothing
  # 500 {"detail":"claude auth logout didn't start: …"} / "claude auth logout didn't finish" (30 s)
  # 500 {"detail":"can't delete <config_dir>: <reason>"}; on any 500 the row stays

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
GET  /api/pages/projects/{id}/code?path=&branch=  the project {id, name, path, workspace_id, workspace}, also on a
                                                git failure; tree, README or file, branch (the checked-out one),
                                                branches (local names, then origin/<name> with no local twin)
  # ?branch= must be one of branches; the checked-out one (or none) is the working tree, any other is
  #   read from git by its full refname: ls-tree for the tree, cat-file blob for the file
  # 404 {"detail":"nope is not a branch in api-server"} for a branch that isn't listed
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

GET  /api/pages/agents                                            (/agents, polled)
← 200 {"running":[{"id":41,"kind":"factory","task_id":12,"title":"Rate-limit login endpoint",
         "project_id":3,"project":"api-server","stage":"agent_review","round":1,
         "started_at":"2026-10-21T10:04:11Z",
         "agents":[
           {"name":"orchestrator","type":null,"round":null,"running":true,"duration_ms":null,
            "last_tool":"Agent review-code"},
           {"name":"builder-12","type":"builder","round":1,"running":false,"duration_ms":754000,
            "last_tool":"Bash pytest -q"},
           {"name":"review-code","type":"review-code","round":2,"running":true,"duration_ms":null,
            "last_tool":"Bash fctl verdict 12 code PASS"}]}],
       "recent":[{"id":40,"task_id":11,"title":"Webhooks","project_id":3,"project":"api-server",
         "status":"failed","error":"exit code 1","started_at":"2026-10-21T09:40:00Z",
         "ended_at":"2026-10-21T09:52:03Z","transcripts":2}]}
  # read-only, no ids or query, so no error statuses; Stop is POST /api/runs/{id}/stop (§6.2)
  # running: every running run (§4.4 allows one), newest started_at first, then id descending
  #   kind: always "factory" today (scheduled runs, §9 Later) · stage: the task's, or null ·
  #   round: the task's highest rounds.n, or null with no rounds
  # agents: from the run's stream-json log, read as GET /api/runs/{id}/log reads it (complete lines,
  #   anything not a JSON object skipped, no readable file = the orchestrator alone): the orchestrator
  #   first, then one per `Agent` tool_use in log order (no other tool name counts)
  #   name: the Agent input's name, else its subagent_type, else "agent" · type: subagent_type or null ·
  #   round: n from "Job|Task <id>, round <n>." in its prompt, else null
  #   running: until a tool_result answers its tool_use id; the orchestrator always ·
  #   duration_ms: the answering user line's int tool_use_result.totalDurationMs, else null
  #   last_tool: its latest own tool line (parent_tool_use_id = its tool_use id, or null for the
  #   orchestrator), as the run log writes it without the "<who> · " prefix; null with none
  # recent: the last 20 runs that aren't running, ended_at newest first with nulls last, then id
  #   descending; error is null unless failed · transcripts: this run's rows in `transcripts`

GET  /api/docs/fctl                                               (/docs/fctl)
← 200 {"body_html":"<h2 id=\"fctl-serve\">fctl serve</h2>…",
       "headings":[{"id":"fctl-serve","text":"fctl serve","level":2}]}
```
