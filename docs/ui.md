# Claude Factories — UI

Part of the [MVP design](MVP.md). Section numbers continue from it.

## 8. UI
The UI is a React SPA served by the frontend server (§4.1). Each page loads its view-model
from `/api/pages/*` (§6.4). Markdown arrives pre-rendered by the backend as `*_html` fields,
with raw HTML off, so the SPA has no markdown library. highlight.js comes from npm. Live
parts poll every 3 s with fetch. Light and dark follow the system setting. Every page header
links to the fctl reference (item 7) and shows the login runs will use, from
`GET /api/auth` (`claude auth status`): `Claude: Pro ✓` when it is a subscription, or a red
`API key — runs disabled` otherwise.

1. **Dashboard** (`/`)
   - Tiles: tasks per status, waiting on me (`human_review`), escalated, running now, done
     this week, and runs this week.
   - A table of open tasks per workspace → project, by status.
   - Rounds per task for tasks done in the last 30 days: average, max, and the list.
   - Each tile links to a filtered list.
2. **Workspace** (`/workspaces/{id}`): one row per project with name, path, counts per
   status, factory state (none / uncommitted / ready), and last activity. **+ Workspace**
   creates one, and a project's page can move it to another workspace.
3. **Project board** (`/projects/{id}`): kanban (wireframe below). The header has **Code**,
   factory state or **Create factory**, **+ New task**, and **Run next**. Cards move between
   columns by drag and drop (native HTML5, no library). Clicking a card opens the task detail.
   Below the columns, a collapsed **Project context** section edits the project's context
   (`GET`/`PUT /api/projects/{id}/context`): a textarea, a live UTF-8 byte count against the
   16 KB cap (`over the limit` disables Save), and **Save**. It loads when first opened, so
   the 3 s poll never touches a draft. A rendered preview of `context_html` is a follow-up.
   After **+ New task**, **Import** takes a task bundle (a `.zip` from **Export**) from a file
   input, disabled until a file is chosen, and posts it raw to `POST /api/projects/{id}/import`.
   Below the toolbar, `Imported #12 <title>` links to the task, or the refusal's detail shows.
4. **Task detail** (`/tasks/{id}`)
   - Header: title, status · stage, branch, Review, Run / Stop / Retry, run status. Next to
     Review, **Export** downloads the task bundle (`GET /api/tasks/{id}/export`, a plain
     `<a download>`), and an **Include transcripts** checkbox adds them, labelled with the
     warning that they can hold paths, env, and secrets.
   - Spec (rendered markdown).
   - Rounds: build notes (collapsible), 4 chips that open the verdict, and +/−.
   - Agents per round: one row per transcript of that round, with its name (else agent type,
     else `agent`) linking to its transcript, model, turns, tokens
     (`in 1,234 · cache 56,789 · out 2,345`), and duration (`4m 12s`). Transcripts with no
     round (the orchestrator, the spec-writer, the reviewers, the approver) are listed under
     **Other agents** after Rounds, each with its `run #`.
   - The approver's decision.
   - Status history (`events`).
   - Run log tail (collapsed).
   - "Take over in terminal" command.
   - A link to Review.
5. **Code review** (`/tasks/{id}/review`): GitHub-style (wireframes below).
   - Round selector, defaulting to latest. The diff is a table built from the backend's diff
     rows, with one row per line and anchor `path:side:line`, and highlight.js colors it.
   - Clicking a line number opens an inline comment form.
   - **Approve** and **Request changes** are enabled only in `review`. A summary box is
     required for Request changes.
6. **Project code** (`/projects/{id}/code`)
   - Left: a file tree from `git ls-files` of the main checkout.
   - The landing view renders `README.md`.
   - Clicking a file opens a highlighted view with line numbers. Binary files and files
     over 1 MB show "not shown". The header shows the current branch.
7. **fctl reference** (`/docs/fctl`)
   - Linked from every page header. A table of contents is built from its headings.
   - One anchored section per §7.2 command: synopsis, arguments and flags, stdin, output,
     exit codes and errors, who calls it (me, a skill, or which agent), and an example.
   - Install (`uv tool install`, `fctl setup`), `FCTL_URL` and `FCTL_HOME`, and using
     `fctl` with Docker (§4.6).
   - Its content comes from `GET /api/docs/fctl` (§6.4).
8. **Transcript** (`/transcripts/{id}`)
   - Header: the agent's label, `run #N`, a link to its task, model, turns, tokens, duration,
     and **Download raw** (`GET /api/transcripts/{id}/raw`).
   - Each message's role and blocks: text as rendered markdown, a tool call's name and its
     input as text, a tool result as text, and thinking in a closed `<details>`.
   - Tool results over 4096 characters arrive cut; **Show all** reloads with `?full=1`.
   - Loaded once, not polled (§6.2 `GET /api/transcripts/{id}`).

### 8.1 Board
```
api-server · personal             [Code]  Factory: ready ✓   [+ New task]  [Run next ▶]
┌ Backlog 3 ──────────┐ ┌ In progress 1 ──────┐ ┌ Review 2 ────────────┐ ┌ Done 5 ─────┐
│ #14 Export CSV      │ │ #13 Audit log       │ │ #12 Rate-limit login │ │ #9 Health   │
│              [Run]  │ │ ● running · review  │ │ waiting on you       │ │ 1 round     │
├─────────────────────┤ │ r1 sec✓ ux✓ ui· co✗ │ │ r2 sec✓ ux✓ ui✓ co✓  │ ├─────────────┤
│ #15 Dark mode       │ │ started 10:02       │ │ +126 −9              │ │ #8 Login UX │
│              [Run]  │ └─────────────────────┘ ├──────────────────────┤ │ 3 rounds    │
├─────────────────────┤                         │▌#11 Webhooks  ⚠ NEEDS│ └─────────────┘
│ #16 Rename env vars │                         │▌YOU — escalated      │
│              [Run]  │                         │▌r2 sec✗ ux✓ ui✓ co✓  │
└─────────────────────┘                         └──────────────────────┘
chips: ✓ PASS  ✗ CHANGES  · pending      escalated cards: red left bar + badge
stalled card: "stalled · build  [Retry]"
```

### 8.2 Review — Conversation
```
#12 Rate-limit login endpoint                          [Request changes]  [Approve]
● Review · waiting on you   factory/12-rate-limit-login   round [2 ▾]   4 files  +126 −9
─ Conversation ─┬─ Files changed 4 ─────────────────────────────────────────────────────
                │
 Description    Max 5 failed logins/min per IP.  (spec ▸)
 ───────────────────────────────────────────────────────────────────────────────────────
 Round 1  initial      sec ✗  ux ✓  ui ✓  code ✓     +118 −9
   security · CHANGES  app/limits.py:31 trusts X-Forwarded-For …          (expand)
 Round 2  agent        sec ✓  ux ✓  ui ✓  code ✓     +126 −9
 Approver · APPROVE    All 4 PASS on round 2; criteria met; tests green.
 ───────────────────────────────────────────────────────────────────────────────────────
 Timeline   10:02 created · 10:03 in_progress · 10:21 round 1 · 10:34 round 2
            10:41 approver APPROVE · 10:41 review
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │ Leave a comment…                                                                   │
 └───────────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Review — Files changed
```
─ Conversation ─┬─ Files changed 4 ─────────────────────────────────────────────────────
 app/            │ app/limits.py  (new)                                         +42 −0
   limits.py +42 │  ─────────────────────────────────────────────────────────────────────
   auth.py  +12−3│      29 + def client_key(request):
   settings +4   │      30 +     # behind proxy only if TRUSTED_PROXY set
 tests/          │      31 +     return request.client.host
   test_lim… +68−6│     ┌ security (round 1): Use request.client.host unless behind… ┐
                 │      │ me: Make the limit configurable via settings.        [Reply]│
                 │      └───────────────────────────────────────────────────────────┘
                 │      32 +
                 │ app/auth.py                                                  +12 −3
                 │  @@ -41,7 +41,9 @@ def login():
                 │  41 41      user = authenticate(form)
                 │  42    -    if not user:
                 │     42 +    if not user and limiter.hit(client_key(request)):
```

