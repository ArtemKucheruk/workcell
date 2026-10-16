# Claude Factories — UI

Part of the [MVP design](MVP.md). Section numbers continue from it.

## 8. UI
Pages are rendered on the server. Light and dark follow the system setting. Live parts poll
every 3 s. Every page header shows the login runs will use, from `claude auth status`:
`Claude: Pro ✓` when it is a subscription, or a red `API key — runs disabled` otherwise.

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
4. **Task detail** (`/tasks/{id}`)
   - Header: title, status · stage, branch, Run / Stop / Retry, run status.
   - Spec (rendered markdown).
   - Rounds: build notes (collapsible), 4 chips that open the verdict, and +/−.
   - The approver's decision.
   - Status history (`events`).
   - Run log tail (collapsed).
   - "Take over in terminal" command.
   - A link to Review.
5. **Code review** (`/tasks/{id}/review`): GitHub-style (wireframes below).
   - Round selector, defaulting to latest. The diff is rendered on the server as a table
     with one row per line and anchor `path:side:line`, and highlight.js colors it.
   - Clicking a line number opens an inline comment form.
   - **Approve** and **Request changes** are enabled only in `review`. A summary box is
     required for Request changes.
6. **Project code** (`/projects/{id}/code`)
   - Left: a file tree from `git ls-files` of the main checkout.
   - The landing view renders `README.md`.
   - Clicking a file opens a highlighted view with line numbers. Binary files and files
     over 1 MB show "not shown". The header shows the current branch.

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

