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
  factory_error TEXT,                     -- that sync's refusal, NULL when it worked; db.init() adds both
  github_label TEXT,                      -- 108: GitHub issues sync's label, NULL = every open issue; db.init() adds it
  plane_api_url TEXT,                     -- 109: Plane sync's API URL (NULL = https://api.plane.so in the UI only),
  plane_workspace TEXT,                   --   workspace slug,
  plane_project_id TEXT,                  --   project ID,
  plane_api_key TEXT,                     --   API key: plaintext, write-only, never returned, logged, or exported
  plane_mark_done INTEGER NOT NULL DEFAULT 0);  -- 1 = approve marks the item done in Plane; db.init() adds all five

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
  import_key TEXT UNIQUE,                 -- 031: factory:<job id> of an imported bootstrap job, 108: github:<owner>/<repo>#<n> of an issue; db.init() adds it to old DBs
  pr_url TEXT,                            -- 093: the task's GitHub PR (Create PR, or a 031 job's pr); db.init() adds it
  module_id INTEGER REFERENCES modules(id) ON DELETE SET NULL);  -- 112: at most one module, NULL = none; db.init() adds it

CREATE TABLE IF NOT EXISTS modules (      -- 112: a project's units of work, e.g. frontend; IF NOT EXISTS covers old DBs
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- 112 Q2: removed with the project
  name TEXT NOT NULL,                     -- trimmed, 1–40 of [A-Za-z0-9_-] (Q1)
  description_md TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS modules_name ON modules(project_id, name COLLATE NOCASE);  -- unique per project, any case

CREATE TABLE IF NOT EXISTS task_deps (    -- 094: task_id waits on blocked_by_id, a task of its own project; IF NOT EXISTS covers old DBs
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  blocked_by_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,  -- deleting either task drops the link
  PRIMARY KEY (task_id, blocked_by_id));

-- 102: db.init() rebuilds a pre-102 runs table (no kind column) into this one, ids and values kept
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  task_id INTEGER REFERENCES tasks(id),   -- NULL only for an automation run (102)
  session_id TEXT NOT NULL,               -- passed as --session-id; enables takeover
  pid INTEGER,
  status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','stopped')),
  exit_code INTEGER, error TEXT,
  log_path TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT,
  account_id INTEGER REFERENCES claude_accounts(id) ON DELETE SET NULL,  -- 096 Q5: its account, NULL = the active one
  factory_id INTEGER REFERENCES factories(id) ON DELETE SET NULL,  -- 102: the automation; NULL for a task run or once deleted
  kind TEXT NOT NULL DEFAULT 'factory' CHECK (kind IN ('factory','automation')),  -- 102: a task run, or an automation's
  trigger TEXT NOT NULL DEFAULT 'manual' CHECK (trigger IN ('manual','schedule')),  -- 104: schedule for the scheduler's runs
  worktree_path TEXT,                     -- 102 Q4: an automation run's own worktree; a task run uses tasks.worktree_path
  CHECK ((kind = 'factory') = (task_id IS NOT NULL)));
-- 096: one running run per task; settings.max_concurrent_runs caps them all. db.init() drops the old global one_active_run
CREATE UNIQUE INDEX IF NOT EXISTS one_run_per_task ON runs(task_id) WHERE status = 'running';

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
  task_id INTEGER REFERENCES tasks(id),   -- 102: NULL for an automation run's; db.init() rebuilds a NOT NULL one
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
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  -- 101: a workflow runs on board tasks, an automation on the repo; fixed at creation. db.init() adds it
  kind TEXT NOT NULL DEFAULT 'workflow' CHECK (kind IN ('workflow','automation')));
CREATE UNIQUE INDEX IF NOT EXISTS factories_name ON factories(project_id, name);

CREATE TABLE IF NOT EXISTS claude_accounts (  -- 056: Claude logins, each its own CLAUDE_CONFIG_DIR; runs use the active one
  id INTEGER PRIMARY KEY,
  config_dir TEXT NOT NULL UNIQUE,        -- absolute
  active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
  created_at TEXT NOT NULL,
  email TEXT);                            -- 095 Q3: the last successful `claude auth status` email; db.init() adds it
CREATE UNIQUE INDEX IF NOT EXISTS one_active_account ON claude_accounts(active) WHERE active = 1;  -- at most one

CREATE TABLE IF NOT EXISTS usage_snapshots (  -- 095: a run's last rate_limit_event; IF NOT EXISTS covers old DBs
  run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
  account_id INTEGER NOT NULL REFERENCES claude_accounts(id) ON DELETE CASCADE,  -- the run's runs.account_id
  five_hour_utilization REAL NOT NULL, five_hour_resets_at INTEGER NOT NULL, five_hour_status TEXT NOT NULL,
  seven_day_utilization REAL NOT NULL, seven_day_resets_at INTEGER NOT NULL, seven_day_status TEXT NOT NULL,
  status TEXT,                            -- the event's top-level status; NULL when it had none
  overage INTEGER NOT NULL CHECK (overage IN (0, 1)),  -- isUsingOverage
  limited INTEGER NOT NULL CHECK (limited IN (0, 1)),  -- Q6: any event of the run was limited
  recorded_at TEXT NOT NULL);             -- Q7: an account's latest is the greatest, then the highest run_id
CREATE INDEX IF NOT EXISTS usage_snapshots_account ON usage_snapshots(account_id, recorded_at);

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

CREATE TABLE IF NOT EXISTS schedules (   -- 104: an automation's one schedule; IF NOT EXISTS covers old DBs
  id INTEGER PRIMARY KEY,
  factory_id INTEGER NOT NULL UNIQUE REFERENCES factories(id) ON DELETE CASCADE,  -- removed with the automation
  cron TEXT NOT NULL,                     -- 5 fields, read in the server's local time (lib/cron.py)
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),  -- 0 = paused
  account_id INTEGER REFERENCES claude_accounts(id) ON DELETE SET NULL,  -- NULL = Auto
  next_run_at TEXT,                       -- UTC; NULL while paused
  last_run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,  -- the last run it started
  last_skip TEXT, last_skip_at TEXT,      -- the latest skip's reason and time; a started run clears both
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS settings (     -- 096 Q2: the app's one settings row, edited on the Settings page
  id INTEGER PRIMARY KEY CHECK (id = 1),
  max_concurrent_runs INTEGER NOT NULL DEFAULT 2 CHECK (max_concurrent_runs >= 1));  -- the global run cap
INSERT OR IGNORE INTO settings (id) VALUES (1);  -- seeded once, never overwritten (096 AC3)
