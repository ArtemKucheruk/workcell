CREATE TABLE IF NOT EXISTS workspaces (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY,
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,              -- main checkout, absolute
  remote_url TEXT,
  default_branch TEXT NOT NULL,           -- worktrees branch from here
  test_cmd TEXT,                          -- used in templates and the run allowlist
  factory_version INTEGER,                -- NULL = factory never written
  created_at TEXT NOT NULL,
  context_md TEXT NOT NULL DEFAULT '',    -- stack and conventions, atop fctl show; db.init() adds it to old DBs
  factory_mark TEXT,                      -- factory/board.json's and backlog.md's mtime and size at the last sync
  factory_error TEXT);                    -- that sync's refusal, NULL when it worked; db.init() adds both

CREATE TABLE IF NOT EXISTS tasks (
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
  import_key TEXT UNIQUE);                -- 031: factory:<job id> of an imported bootstrap job; db.init() adds it to old DBs

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  session_id TEXT NOT NULL,               -- passed as --session-id; enables takeover
  pid INTEGER,
  status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','stopped')),
  exit_code INTEGER, error TEXT,
  log_path TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(status) WHERE status = 'running';  -- one run at a time, globally (Pro limits)

CREATE TABLE IF NOT EXISTS rounds (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  n INTEGER NOT NULL,                     -- 1, 2, 3… per task
  trigger TEXT NOT NULL CHECK (trigger IN ('initial','agent','human')),
  base_sha TEXT NOT NULL,                 -- diff is always against this commit
  build_md TEXT,                          -- builder notes for this round
  created_at TEXT NOT NULL,
  UNIQUE (task_id, n));

CREATE TABLE IF NOT EXISTS round_files (
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  path TEXT NOT NULL, old_path TEXT,      -- old_path set on rename
  change TEXT NOT NULL CHECK (change IN ('added','modified','deleted','renamed')),
  binary INTEGER NOT NULL DEFAULT 0,
  additions INTEGER NOT NULL, deletions INTEGER NOT NULL,
  patch TEXT NOT NULL,                    -- this file's section of the unified diff
  PRIMARY KEY (round_id, path));          -- round totals = SUM over this table

CREATE TABLE IF NOT EXISTS verdicts (
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  reviewer TEXT NOT NULL CHECK (reviewer IN ('security','ux','ui','code')),
  verdict TEXT NOT NULL CHECK (verdict IN ('PASS','CHANGES')),
  body_md TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (round_id, reviewer));      -- re-posting overwrites (safe on retry)

CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  author TEXT NOT NULL,                   -- 'me' or a reviewer name
  path TEXT, line INTEGER, side TEXT CHECK (side IN ('old','new')),  -- all NULL = conversation comment
  body_md TEXT NOT NULL, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  actor TEXT NOT NULL CHECK (actor IN ('approver','me')),
  decision TEXT NOT NULL CHECK (decision IN ('APPROVE','ESCALATE','CHANGES_REQUESTED')),
  body_md TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS events (                     -- status/stage history
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  actor TEXT NOT NULL,                    -- 'me', 'app', 'orchestrator'
  from_status TEXT, to_status TEXT, stage TEXT, note TEXT,
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS transcripts (  -- 030: a run's copied Claude Code transcripts
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

CREATE TABLE IF NOT EXISTS factories (    -- 051: a project's named factory designs; IF NOT EXISTS covers old DBs
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  graph TEXT NOT NULL,                    -- the compact JSON of docs/data-model-and-api.md §6.1's <Graph>
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS factories_name ON factories(project_id, name);

CREATE TABLE IF NOT EXISTS claude_accounts (  -- 056: Claude logins, each its own CLAUDE_CONFIG_DIR; runs use the active one
  id INTEGER PRIMARY KEY,
  config_dir TEXT NOT NULL UNIQUE,        -- absolute
  active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
  created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_account ON claude_accounts(active) WHERE active = 1;  -- at most one

CREATE TABLE IF NOT EXISTS context_items (  -- 057: a project's context cards and groups; IF NOT EXISTS covers old DBs
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
