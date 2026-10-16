# Backlog

`/factory next` runs the first unchecked line. `/factory approve` ticks it. § numbers point into docs/.

- [ ] 001-setup: uv project and package layout; `fctl serve` on 127.0.0.1:4545; data dir `FCTL_HOME` (default `~/.claude-factories`); full `schema.sql` from §5.1 applied at startup in WAL mode; base Jinja layout with vendored htmx and highlight.js; local-safety middleware (§4.5: Host check, `X-Requested-By: fctl` on mutating requests); pytest + TestClient wired to a temp `FCTL_HOME`.
- [ ] 002-projects: workspaces; `GET /api/workspaces`, `POST /api/projects/connect`, `GET /api/projects?path=` (§6.1); `fctl connect` collecting git info and resolving the main repo from inside a worktree (§3.1); workspace page (§8 item 2).
- [ ] 003-tasks-board: task endpoints in §6.2 except run/run-next/stop/log; stage → status mapping and `events` rows (§5.2); manual moves clear stage and are refused during a run; project board (§8.1) with native drag and drop; `fctl task add`.
- [ ] 004-submit: `fctl submit --new` and `fctl submit <id>` with the temp-index capture (§7.4); `POST /api/tasks/{id}/rounds` and task create with `submit`; per-file split and +/− counts into `round_files`; 413 over 5 MB; `fctl diff`; `GET /api/tasks/{id}/context` and `fctl show`.
- [ ] 005-review-page: review page (§8 item 5, §8.2, §8.3): header, round selector, Conversation tab with timeline, Files changed with a server-rendered diff table and highlight.js, inline comments, Approve, Request changes (standalone tasks: no run).
- [ ] 006-agent-api: `fctl spec`, `stage`, `verdict`, `comment`, `decide`, `round` and their endpoints (§6.3, §7.2).
- [ ] 007-task-detail: task page (§8 item 4) without run controls: spec, rounds with reviewer chips, approver decision, status history.
- [ ] 008-factory-templates: Create factory (§3.2, §6.1): SKILL.md and the 7 agent templates from §7.3, rendered per project; skip or overwrite; factory state none / uncommitted / ready.
- [ ] 009-run-manager: run, run-next, stop, and log endpoints (§6.2); worktree creation and `.git/info/exclude`; auth check, env stripping, and the spawn command (§4.3, §4.4); one run at a time; Stop by process group; startup cleanup; Request changes spawns a rework run; run controls, run log, and takeover command on the task page; `Claude: Pro ✓` header.
- [ ] 010-cli-and-skills: `fctl setup` writing `~/.claude/skills/factory-connect` and `factory-submit` (§7.1); `fctl run`, `fctl rework`, `fctl approve` (§7.2).
- [ ] 011-code-page: project code page (§8 item 6): `git ls-files` tree, README landing, highlighted file viewer, path containment (§4.5).
- [ ] 012-dashboard: dashboard (§8 item 1).
