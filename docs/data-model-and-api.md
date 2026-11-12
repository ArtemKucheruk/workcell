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
  context_md TEXT NOT NULL DEFAULT '',    -- project context: stack and conventions, atop fctl show
  factory_mark TEXT,                      -- factory/board.json's and backlog.md's mtime and size at the last sync,
                                          --   NULL when neither file is there
  factory_error TEXT);                    -- that sync's refusal detail, shown on the board; NULL when it worked

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
  import_key TEXT UNIQUE,                 -- factory:<job id> for a job fctl import-factory brought in, else NULL
  pr_url TEXT);                           -- 093: the task's GitHub PR, set by Create PR (§6.3) or an imported
                                          --   job's `pr` that names a /pull/N; NULL until then. db.init() adds it

CREATE TABLE task_deps (                  -- task_id waits on blocked_by_id, a task of the same project
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  blocked_by_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,  -- deleting either task drops the link
  PRIMARY KEY (task_id, blocked_by_id));

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

CREATE TABLE context_items (              -- a project's context cards and groups (§6.1), after context_md in fctl show
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES context_items(id) ON DELETE CASCADE,  -- NULL = top level, else its group
  kind TEXT NOT NULL CHECK (kind IN ('item','group')),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  content_md TEXT NOT NULL DEFAULT '',    -- '' for a group
  source_path TEXT,                       -- the file or folder it was read from, else NULL
  position REAL NOT NULL,                 -- order within its parent's list
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
```
Relations: workspace 1–n project 1–n task. A project has 0–n factories and 0–n context items, removed with it
(ON DELETE CASCADE). A task waits on 0–n tasks of its own project (`task_deps`, no self links, no cycles); it is
**blocked** while any of them isn't `done` and **ready** otherwise. Blocked is worked out on read, never stored, so
a blocker moving to done readies its dependents without writing them. Deleting a task, or its project, drops its
links on both sides. A context item of kind group holds 0–n items one level deep, removed with it.
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
← 200 {"id":3,"name":"api-server","default_branch":"main","factory":"ready"}   # none|uncommitted|legacy|ready

POST /api/projects/3/factory                                      (Create factory button)
→ {"overwrite":false}
← 200 {"written":[".claude/skills/factory/SKILL.md",".claude/agents/builder.md", "…"],
       "skipped":[], "commit_hint":"git add .claude/skills/factory .claude/agents && git commit -m \"Add factory\""}

GET  /api/projects/3/context                                      (fctl context, Context page's pinned card)
← 200 {"context_md":"# Stack\n- Python 3.12\n","context_html":"<h1>Stack</h1>\n<ul>…","bytes":22,"max_bytes":16384}

PUT  /api/projects/3/context                                      (fctl context set, the pinned card's Save)
→ {"context_md":"# Stack\n- Python 3.12\n"}
← 200 {"context_md":"…","context_html":"…","bytes":22,"max_bytes":16384}
  # 413 {"detail":"context over 16 KB"} over 16384 UTF-8 bytes; "" clears it
  # 404 {"detail":"Project #99 not found"} for an unknown id, on GET too
  # the pinned card, "Stack and conventions", has no context_items row; the cards below don't count here

<ContextItem> = {"id":5,"parent_id":null,"kind":"item","title":"API conventions",
                 "description":"Every endpoint returns JSON.","content_md":"# API conventions\n\nEvery endpoint…\n",
                 "content_html":"<h1>API conventions</h1>\n<p>…</p>\n","source_path":null,"position":1.0,
                 "created_at":"2026-10-23T10:00:00Z","updated_at":"2026-10-23T10:00:00Z"}
  # id: int · parent_id: int | null (null = top level; else a group's id) · kind: "item" | "group"
  # title, description: str · content_md: str ("" for a group) · content_html: lib/markdown.render(content_md),
  #   raw HTML off ("" for a group) · source_path: str | null (the file's or folder's path when read from a path)
  # position: number, the order within its parent's list · created_at, updated_at: str (db.now() format)
  # titles and descriptions are stored with each whitespace run as one space, trimmed

GET  /api/projects/3/context/items                                (Context page, loaded once)
← 200 [<ContextItem>…]
  # every card and group of the project, groups' cards included, as one flat list ordered by position, then id;
  #   [] with none. The SPA splits it by parent_id
  # 404 {"detail":"Project #99 not found"}

POST /api/projects/3/context/items                                (+ New card, + New group)
→ {"kind":"item","title":"API conventions","description":"…","content_md":"…","parent_id":null}
  # kind: "item" (default) | "group" · title required · description, content_md default "" · parent_id default null
← 201 <ContextItem>, last in its parent's list (siblings' max position + 1, else 1), source_path null
  # 422 FastAPI's list detail: title missing; kind not item/group; title, description, or content_md null or not a string
  # 422 {"detail":"title must not be blank"}
  # 422 {"detail":"description over 160 characters"}
  # 422 {"detail":"a group has no content"}                     kind group with a non-empty content_md
  # 422 {"detail":"groups are one level deep"}                  kind group with a parent_id
  # 422 {"detail":"parent_id 7 is not a group of this project"} unknown id, an item, or another project's group
  # 413 {"detail":"card over 16 KB"}                            content_md over 16384 UTF-8 bytes (MAX_CONTEXT)
  # 413 {"detail":"project context over 64 KB"}                 context_md plus every card's content_md, in UTF-8
  #     bytes, measured after the write (MAX_CONTEXT_TOTAL)
  # 404 {"detail":"Project #99 not found"}
  # every 4xx writes nothing

POST /api/projects/3/context/items/upload?name=api.md[&parent_id=7]    (Upload files, one request per file)
→ the file's bytes as the raw body (any Content-Type)
← 201 <ContextItem>: kind item, source_path null, title and description derived (below), content_md the body as text
  # 413 {"detail":"card over 16 KB"}                     on Content-Length, else once the stream passes 16384 bytes
  # 422 {"detail":"only .md, .markdown, and .txt files"} name's extension, case-insensitive
  # 422 {"detail":"not UTF-8"}
  # 422 FastAPI's list detail: name missing
  # parent_id, 64 KB, and 404 refusals as POST above; every 4xx writes nothing
  # details carry no file name: the SPA prefixes it. The name never touches the filesystem

POST /api/projects/3/context/items/from-path                      (Add from path)
→ {"path":"/Users/me/notes","parent_id":null}                      # parent_id optional, default null
← 201 [<ContextItem>…]
  # a file → [its card]; a folder → [the group, then one card per *.md / *.markdown / *.txt regular file directly
  #   in it, by name]. The group's title is the folder's name, description "", source_path the folder. Each card's
  #   source_path is its file's path, its title and description derived (below)
  # 422 {"detail":"path must be absolute"}
  # 404 {"detail":"no file or folder at /Users/me/nope"}
  # 422 {"detail":"/Users/me/a.pdf: only .md, .markdown, and .txt files"}  a file path with another extension
  # 422 {"detail":"/Users/me/notes/a.md: not UTF-8"}                         alone or in a folder
  # 413 {"detail":"/Users/me/notes/a.md: card over 16 KB"}                   alone or in a folder
  # 422 {"detail":"/Users/me/notes: no .md, .markdown, or .txt files"}
  # 413 {"detail":"/Users/me/notes: 51 files; the limit is 50"}             counts only the files it would take
  # 422 {"detail":"groups are one level deep"}                               a folder with a parent_id
  # 422 {"detail":"/Users/me/notes/a.md: Permission denied"}                 any other OS error reading it
  # parent_id, 64 KB, and 404 refusals as POST above; one transaction, so every 4xx writes nothing

PATCH /api/context/items/5                                        (Edit, Move to group, Move out of group)
→ any non-empty subset of {"title":"…","description":"…","content_md":"…","parent_id":7|null,"position":1.5}
← 200 <ContextItem> after the update; updated_at now, created_at unchanged
  # parent_id null = top level. A parent_id that changes the parent, sent without position, puts it last in the
  #   new list. The same parent leaves position alone
  # 422 {"detail":"send at least one of: title, description, content_md, parent_id, position"}  {} or only unknown keys
  # 422 FastAPI's list detail: title, description, content_md, or position null or the wrong type, or position NaN or ±inf
  # the title, description, group, parent_id, and 16 KB rules of POST; the 64 KB rule only when content_md is sent,
  #   so a move or rename is never refused for size
  # 404 {"detail":"Context item #99 not found"}
  # every 4xx writes nothing

DELETE /api/context/items/5                                       (Delete)
← 204, empty body; a group's cards go with it (ON DELETE CASCADE). A file a card was read from stays on disk
  # 404 {"detail":"Context item #99 not found"}

POST /api/context/items/5/reload                                  (Reload from path)
← 200 <ContextItem>: content_md (and content_html) read again from source_path; title and description kept;
      updated_at now
  # 422 {"detail":"only a card read from a path can be reloaded"}   source_path null, or a group
  # 404 {"detail":"no file at /Users/me/notes/a.md"}
  # 422 {"detail":"/Users/me/notes/a.md: not UTF-8"}
  # 413 {"detail":"/Users/me/notes/a.md: card over 16 KB"}
  # 413 {"detail":"project context over 64 KB"}
  # 404 {"detail":"Context item #99 not found"}
  # every 4xx writes nothing

POST /api/projects/3/import-factory      (Settings: Sync factory/, fctl import-factory, fctl connect, /factory approve)
→ {"job":"014-run-ui"}                   # that board.json job only; factory/backlog.md isn't read, and skipped is 0
→ {}                                     # sync: every board.json job, then each factory/backlog.md line it doesn't list
← 200 {"imported":[{"job":"014-run-ui","task_id":12,"created":true,"rounds":1,"transcripts":9},
                   {"job":"059-legacy-factory","task_id":70,"created":true,"rounds":0,"transcripts":0}],
       "skipped":2}
  # imported: board.json jobs in board order, then backlog-only lines in file order; each job once
  # a backlog.md line `- [ ] <id>: <text>` (`[x]` done) under `## <heading>` becomes, keyed factory:<id>, a task
  #   titled from the id (`058-backlog-sync` → `Backlog sync`), described `## <heading>\n\n<text>`, in backlog or
  #   done (done_at NULL) at the bottom of its column, with one `app` event. A rerun changes only description_md
  #   and status, and only on a task the app hasn't started (no run, no round, still backlog). Nothing is deleted.
  # skipped: backlog.md checkbox lines (`- [`) with no `<id>:`, another mark, a bad id, or a repeated id
  # a {} that works stores the files' mark and clears projects.factory_error; the board's view-model runs {}
  #   itself when the mark changes (§6.4). It never writes to the repo
  # 404 {"detail":"Project #99 not found"} · {"detail":"no factory/board.json or factory/backlog.md in <path>"} ({})
  #   · {"detail":"no factory/board.json in <path>"} or {"detail":"no job <id> in factory/board.json"} ({"job"})
  # 422 bad board.json, job id, or patch · 413 {"detail":"backlog.md over 5 MB"}, board.json, or a job's file
  # 409 {"detail":"factory:<id> is imported in project #<n>"} · every refusal writes no rows

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

GET  /api/factory-templates                                       (+ New factory's Template radios)
← 200 [{"key":"standard","name":"Standard","description":"Spec, build, then security, UX, UI, …"},
       {"key":"bug-fix",…}, {"key":"security-audit",…}, {"key":"ml-experiment",…}, {"key":"test-coverage",…}]
  # in this order, Standard first; each description is one line. The graphs are listed below

POST /api/projects/3/factories                                    (+ New factory)
→ {"name":"default","template":"bug-fix"}
← 201 <Factory>, whose graph is the template's graph (below), with created_at = updated_at
  # template is optional: left out or null → standard, the default graph
  # name is trimmed: 422 {"detail":"name must not be blank"}; missing, null, or not a string → 422 FastAPI's list detail
  # 422 {"detail":"unknown template nightly: use standard, bug-fix, security-audit, ml-experiment, or test-coverage"};
  #   a template that isn't a string → 422 FastAPI's list detail. Checked after the blank name, before the 404 and 409
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

**Derived titles and descriptions.** An upload or a path read takes a card's title from the source text of the
first level-1 heading (ATX or setext, found from markdown-it-py's tokens, so a `# x` line in a code fence doesn't
count), else the file name as given, extension included. Its description is the first paragraph's source text with
each whitespace run as one space, cut to its first 160 characters with no ellipsis, or `""` with no paragraph.
Reload keeps both, since either may have been edited.

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
That makes 14 edges. It is the `standard` template.

The other templates (088) have fewer than 4 reviewers, so they branch on `any-changes` (any_changes) instead of
`all-pass`. Their agents come from `factory_templates/agents/` the same way, and a name two templates share is the
same file (`docs/claude-code.md §7.3`). Each one ends in the same tail:
```
each reviewer → any-changes (any_changes)
any-changes yes → rounds (rounds_below)     any-changes no → approver (approver)
rounds yes → builder                        rounds no → approver
```
- `bug-fix`: start → bug-spec-writer (spec_writer) → builder (builder, side both) → review-code, review-security
  (reviewer, focus code / security); rounds n 2. 8 nodes, 10 edges.
- `security-audit`: start → security-auditor (spec_writer) → builder → review-security (focus security); rounds n 2.
  7 nodes, 8 edges.
- `ml-experiment`: start → data-check (spec_writer) → builder → review-eval (focus custom); rounds n 3. 7 nodes,
  8 edges.
- `test-coverage`: start → coverage-planner (spec_writer) → builder → review-tests (focus custom); rounds n 2.
  7 nodes, 8 edges.

### 6.2 Tasks & runs
```
GET  /api/projects/3/tasks
← 200 [{"id":12,"title":"Rate-limit login endpoint","status":"review","stage":"human_review",
        "round":2,"verdicts":{"security":"PASS","ux":"PASS","ui":"PASS","code":"PASS"},
        "additions":126,"deletions":9,"run":null,
        "blocked":false,"blocked_by":[{"id":9,"title":"Add Redis","status":"done"}],"blocks":[15]}]
  # every task carries <Deps>' blocked, blocked_by, and blocks (below)

POST /api/projects/3/tasks                                        (+ New task, fctl task add)
→ {"title":"Rate-limit login endpoint","description_md":"Max 5 failed logins/min per IP.","blocked_by":[9]}
← 201 {"id":12,"status":"backlog"}
  # optional "submit": {...} creates round 1 and puts the task straight in review (§7.4)
  # optional "blocked_by": the tasks it waits on, each stored once; one refused as in PUT blocked-by below
  #   (422 "no task #99", "#30 is in another project; …") adds no task

GET  /api/tasks/12                                                (fctl round, task page)
← 200 {"id":12,"status":"in_progress","stage":"agent_review","branch":"factory/12-rate-limit-login",
       "rounds":[{"n":1,"trigger":"initial","files":4,"additions":118,"deletions":9,
                  "verdicts":{"security":"CHANGES","ux":"PASS","ui":"pending","code":"PASS"}}],
       "decisions":[],"run":{"id":41,"status":"running"},"blocked":false,"blocked_by":[],"blocks":[]}

PUT  /api/tasks/15/blocked-by/12                                  (task page Add, fctl task block)
← 200 <Deps> {"id":15,"blocked":true,"blocked_by":[{"id":12,"title":"Rate-limit login endpoint",
              "status":"backlog"}],"blocks":[]}
  # #15 waits on #12 from now on; again is a 200 with the same body and still one row
  # blocked_by: every link as {id, title, status}, done blockers too, by id · blocks: the dependents' ids,
  #   ascending · blocked: true while any blocker's status isn't done; worked out on read, never stored
  # 404 {"detail":"Task #15 not found"}
  # 422 {"detail":"#15 can't wait on itself"} · {"detail":"no task #99"} ·
  #     {"detail":"#30 is in another project; a task waits only on tasks of its own project"} ·
  #     {"detail":"cycle: #15 waits on #12, which waits on #14, which waits on #15"}; none adds a row

DELETE /api/tasks/15/blocked-by/12                                (task page Remove, fctl task unblock)
← 200 <Deps> after the removal
  # 404 {"detail":"Task #15 not found"} · 404 {"detail":"#15 is not blocked by #12"}

GET  /api/tasks/12/context?round=1 | ?feedback=1                  (fctl show) → text/markdown
← 200 "# #12 Rate-limit login endpoint\n## Spec\n…\n## Round 1 — build notes\n…\n## Verdicts\n…"
  # with no query, the project context comes first: "## Project context\n…\n\n### API conventions\n…\n\n# #12 …".
  #   Under the heading, the pinned context_md, then the context cards (§6.1) by position: a top-level card or
  #   group as "### <title>", a group's cards right after it as "#### <title>", each with its content_md. Blank
  #   bodies are left out; with a blank context_md and no cards there is no "## Project context"

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
  # 409 if any run is active, auth isn't claude.ai, or the factory isn't committed on default_branch;
  #   a legacy factory (MVP §3.2 step 4): 409 {"detail":"this repo runs the file-based /factory loop:
  #   Create factory with Overwrite, then commit it on main"}
  # a blocked task, checked after the review/done 409 and before the factory check, for Run, Retry,
  #   Run next, and rework's run alike: 409 {"detail":"#15 is blocked by #12, #14; finish those first or
  #   remove the dependency"}, naming only the blockers that aren't done; no run row, no worktree
  # 099, after the factory check and before auth: the first run makes the worktree with `wt switch --create`,
  #   then every run copies the main checkout's ignored files in with `wt step copy-ignored` (.venv/,
  #   .claude/settings.local.json, and .fctl/ left out; MVP §4.4). 409 "wt (worktrunk) isn't installed: brew
  #   install worktrunk, then run again" · "wt switch failed: <stderr line>" · "wt step copy-ignored failed:
  #   <stderr line>" · "wt <step> timed out" · "wt put the worktree at <path>, expected <path>" · "<path> is
  #   ignored in the main checkout but not on main, so it was left out of the worktree: commit its .gitignore
  #   line on main, then run again" (the copied file is deleted); no run row, and a worktree made before the
  #   refusal stays stored

POST /api/projects/3/run-next                                     (Run next, fctl run next)
← 202 {"task_id":14,"run_id":42}                                  # 404 if backlog empty; 409 as run
  # the top ready backlog card (lowest position, then id), skipping blocked ones; with every card blocked,
  #   409 {"detail":"all backlog tasks are blocked: #15 waits on #12, #14"}: the top card and its open blockers

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

POST /api/tasks/12/pr                                             (Create PR, 093; no fctl command)
← 200 {"number":71,"url":"https://github.com/o/r/pull/71","reused":false}
  # a done factory task: `git add -A` and `git commit -m <title>` in the worktree when it has changes (my
  #   identity, no -c overrides, the title is the whole message), `git push -u origin <branch>` (never forced),
  #   then `gh pr create --repo <owner/repo> --base <default_branch> --head <branch> --title <title> --body …`,
  #   or the branch's open PR (`gh pr list … --state open`), reused: true. pr_url is saved with an event (me,
  #   done → done, note `PR #71 opened`) only when it changes. Task read and writes are separate transactions
  # 404 {"detail":"Task #99 not found"}
  # 409, before any git or gh call: "#12 is not done; approve it first" · "#12 has no branch; commit it
  #     yourself" · "the worktree <path> is gone"
  # 409 "<repo> has no origin remote; add one with git remote add origin …" · "origin isn't on GitHub
  #     (<host>); push and open the PR yourself" (origin read raw with git config, github.com only)
  # 409 "gh is not installed: install GitHub CLI, then run gh auth login" · "gh is not logged in: run gh
  #     auth login. <gh's line>"; under Docker both end " (the backend image has no gh login; create the PR
  #     from your host)"
  # 409 "nothing to commit: #12's branch has no changes beyond main" · "git push was rejected: ! [rejected] …"
  #     · gh pr create's first stderr line (the commit and push stay; pr_url stays NULL)
  # 500 "<git|gh> timed out: <command>": 60 s for local git, 120 s for push, fetch, and gh

GET  /api/tasks/12/pr                                             (the PR line, polled every 10 s while OPEN)
← 200 {"number":71,"url":"https://github.com/o/r/pull/71","state":"OPEN","checks":{"passed":2,"failed":1,"pending":0}}
  # `gh pr view 71 --repo o/r --json number,url,state,statusCheckRollup`; state is OPEN, MERGED, or CLOSED.
  #   checks: SUCCESS/NEUTRAL/SKIPPED passed; FAILURE/ERROR/CANCELLED/TIMED_OUT/ACTION_REQUIRED/STARTUP_FAILURE
  #   failed; anything else (no conclusion yet, PENDING) pending
  # 404 "#12 has no PR" · 409 gh's message, or the gh refusals above

POST /api/tasks/12/pr/merge                                       (Merge PR, 093, after a dialog)
← 200 {"number":71,"state":"MERGED","notes":["Fast-forwarded main to origin/main.",
       "Removed the worktree /code/api/.claude/worktrees/12-rate-limit-login.",
       "Deleted the local branch factory/12-rate-limit-login.","Deleted the remote branch factory/12-rate-limit-login."]}
  # an OPEN PR: `gh pr merge 71 --repo o/r --merge` (MERGE_METHOD), then an event (me, done → done, note
  #   `PR #71 merged`); an already MERGED one skips it. Then `git fetch origin` in the main checkout and
  #   `git merge --ff-only origin/<default>` only when it is on the default branch, `git status --porcelain`
  #   is empty, and HEAD is an ancestor of origin's, else a "Skipped updating main: …" note. Then `wt remove
  #   --foreground --no-delete-branch --no-hooks <branch>` (099), `git branch -d`, and `git push origin --delete`,
  #   none forced: a failed step is a note with wt's or git's line (no `wt` included) ("Worktree already removed.", "Remote branch already deleted."), and the rest still run
  # 409 "#12 is not done; approve it first" · "#12 has no PR; Create PR first" · "PR #71 is closed; reopen
  #     it on GitHub" · the origin and gh refusals above · gh pr merge's message (checks failing, conflicts,
  #     branch protection), with nothing fetched, cleaned up, or recorded
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
`GET /api/projects/{id}/factories` and `GET /api/factory-templates` (§6.1), plus `GET /api/pages/projects/{id}` for
its header, and the designer at
`/projects/{id}/factories/{fid}` loads `GET /api/factories/{fid}` (§6.1). `/projects/{id}/context` loads
`GET /api/projects/{id}/context` for the pinned card and `GET /api/projects/{id}/context/items` for the rest (§6.1),
plus `GET /api/pages/projects/{id}` for its header, once each.

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
                                                factory state and hint, factory_files (059: which of Create
                                                factory's 8 paths exist on disk now, in its order; [] when none),
                                                board cards with stage, branch,
                                                description_md, chips per round, +/−, waiting, escalated, stalled,
                                                blocked, blocked_by, and blocks (as §6.2's task list, 094),
                                                and factory_error (058): first syncs factory/ (§6.1's {}) when
                                                board.json's or backlog.md's mtime or size changed; a refusal is
                                                stored as factory_error, not a failed page, until a file changes.
                                                With Sec-Fetch-Site: cross-site it skips the sync (MVP §4.5)
GET  /api/pages/tasks/{id}                      the task with project_id, project, workspace_id, and workspace (its
                                                project's now), spec_html, rounds, decision, history, the active run
                                                and takeover command, transcripts (as GET /api/tasks/{id}/transcripts);
                                                094: blocked_by and blocks, each [{id, title, status}] by id, and
                                                project_tasks, the project's other tasks as {id, title, status} by
                                                id (the Blocked by section's Add choices); 093: pr (below)
GET  /api/pages/tasks/{id}/review?round=        the same task plus commit_hint; pr; timeline; files with diff rows
                                                carrying side, old/new line, kind, text, and the path:side:line
                                                anchor; inline comments
  # 093: pr is {"url","number","can_create","hint"}, null for a standalone task. number is parsed from url's
  #   /pull/N (null with no url). can_create: a done task with no pr_url whose worktree exists and has
  #   uncommitted changes or commits beyond default_branch. Otherwise hint is "Approve it first.", "The
  #   worktree is gone.", or "Nothing to commit beyond main.", and null once a PR exists. Local git only, never
  #   gh; the PR's state comes from GET /api/tasks/{id}/pr (§6.3). The history's labels end " · <note>" for
  #   an event with a note, e.g. "done · PR #71 opened"
GET  /api/pages/projects/{id}/code?path=&branch=  the project {id, name, path, workspace_id, workspace, web_url}, also on a
                                                git failure; tree, README or file, branch (the checked-out one),
                                                branches (local names, then origin/<name> with no local twin)
  # 090: project.web_url is remote_url as an http(s) browser URL (lib/remote.py: scp-like, ssh://, http(s)://;
  #   credentials, the ssh port, and .git dropped), null for no remote or any other form, also on a git failure;
  #   remote_url itself isn't sent. file_url is ?path= on default_branch (<web_url>/blob/<branch>/<path>, each
  #   segment percent-encoded) for a github.com web_url only; null on the landing, for other hosts, and with error
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
