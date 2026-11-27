# Task: write MVP documentation for "Workcell" (working name)

Write design documentation only. Do not write application code, scaffold the project,
or install anything. All output is markdown under `docs/`.

## Read first
- `FACTORY.md`: the current file-based factory (orchestrator skill + subagents +
  board.json + md files). The app replaces that file-based state with an API + database.
  Keep the loop, the agents, and the rules unless this prompt changes them.

## What we're building
A local web app (runs on my machine, single user, no auth) that acts as the control
center for Claude Code work across my projects:

1. It tracks the features I need to ship, per project, grouped into workspaces.
2. It's the backend for the factory. Claude Code agents call the app's API to create
   tasks, move statuses, submit code for review, and post review verdicts. They no
   longer write board.json or md files.
3. It gives me a GitHub-like code review UI. Claude never commits or pushes. I review
   in the app and commit to git/GitHub myself.

### Domain
- **Workspace**: groups projects (e.g. "work", "personal").
- **Project**: one local git repo, connected from Claude Code by a command run inside
  that repo.
- **Task (feature)**: belongs to a project. Status: `backlog → in_progress → review → done`.
  Claude updates the status automatically as the factory moves the task forward. I can
  also move it by hand. Propose how factory stages map to these statuses.
- **Review (the app's "PR")**: a snapshot of a task's code changes. It holds the changed
  files, the diff, +additions/−deletions per file and in total, the review rounds,
  reviewer-agent verdicts and comments, my comments, and my decision.
- **Factory**: the orchestrator and agents from FACTORY.md, installed into a project.
  I create it from the app (e.g. a "Create factory" button on a project), and the app
  writes the skill and agent files into the repo's `.claude/` from templates it keeps.
  I don't set it up by hand.

### Screens
1. **Dashboard**: stats across all workspaces. Show tasks per status, counts per
   workspace/project, reviews waiting on me, escalated (needs-human) tasks, tasks done
   this week, and review rounds per task. Show only what the data actually supports.
2. **Workspace**: list of its projects.
3. **Project board**: kanban with Backlog / In progress / Review / Done columns. Clicking
   a card opens the task detail.
4. **Task detail**: spec, build notes, review rounds with 4 reviewer chips (security, ux,
   ui, code) that fill in as verdicts land, the approver's decision, and the history of
   status changes.
5. **Code review page**, modeled on a GitHub PR:
   - Header: title, status, number of files changed, +N −M.
   - Conversation tab: description, agent reviews, my comments, timeline.
   - Files changed tab: file list/tree with +/− per file, unified diff (split view
     optional), inline line comments.
   - Actions: **Approve** moves the task to done, and I commit myself. **Request changes**
     sends my comments back to the builder as a new round, like `/factory rework`.
6. **Project code page**: the repo's file tree and a file viewer with syntax
   highlighting. The landing view renders the project's README.md as the
   "what this project is" page.

### Claude Code integration
The project ships Claude Code commands/skills that talk to the app's API. At minimum, document:
- **connect**: run inside a repo to register the project with the app (path, name, git
  remote/branch, workspace). Show example usage.
- **factory run / next / rework / approve**: the FACTORY.md commands, reworked so
  their state lives in the app.
- **submit for review**: capture the working-tree diff (including new untracked files) and
  post it to the app as a review. Give a concrete end-to-end example: the command, the
  HTTP request it makes, and what I then see in the app.
- **status updates**: which agent sets which status, and when.

Decide how agents call the app and justify the choice briefly. The options are plain HTTP
(curl) from skills/agents, a small CLI wrapper, or an MCP server. Prefer the simplest one
that works reliably from subagents.

### Changes vs FACTORY.md
- Drop `merge to main`. The approver's APPROVE puts the task in "review", waiting on me.
  My approval in the UI moves it to done. ESCALATE means needs-human and is highlighted.
- Claude makes no commits. The builder works in the working tree or a git worktree
  (recommend one) and never commits or pushes.
- DB rows and the API replace board.json, dashboard.html, and the jobs/* md files.
  Decide whether spec/build/review content also stays on disk or lives only in the DB,
  and justify the choice.
- Decide how a factory run starts. Either (a) I run the slash command in my own Claude
  Code terminal and the app only stores state, or (b) the app spawns headless Claude Code
  itself (`claude -p` / Agent SDK). Recommend one for the MVP and put the other under Later.

## Constraints
- Local only: single user, no auth, no cloud. One command starts it.
- API + DB. Use SQLite unless there's a strong reason not to. Recommend a boring stack and
  justify it in one paragraph.
- MVP means the smallest thing I'd use every day. Everything else goes on the "Later" list,
  not into the MVP design.

## Output
Write `docs/MVP.md`. Split it into a few files under `docs/` only if it grows past ~600
lines. Sections:
1. **Overview**: problem, goals, non-goals.
2. **Concepts & glossary**: workspace, project, task, review, round, factory, agent.
3. **User flows**, step by step: connect a project; create a factory; add a feature; run
   the factory (show the status change at each step); review in the app; request changes;
   approve and commit myself.
4. **Architecture**: components, one ASCII diagram, and how Claude Code, the app, and the
   DB talk to each other.
5. **Data model**: tables, key columns, relations, status enums.
6. **API**: the endpoints agents and the UI need, each with method, path, and a
   request/response example.
7. **Claude Code integration**: the commands/skills/agents to ship, example invocations,
   and what each one calls.
8. **UI**: each screen above with its purpose and key elements, plus ASCII wireframes for
   the board and the review page.
9. **MVP scope vs Later**.
10. **Open questions / assumptions**.

## Before writing
Ask me up to 5 questions, and only where the answer would change the design. For
everything else, pick a sensible default and list it under Assumptions.
