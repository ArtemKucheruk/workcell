# Claude Factories — UI

Part of the [MVP design](MVP.md). Section numbers continue from it.

## 8. UI
The UI is a React SPA served by the frontend server (§4.1). Each page loads its view-model
from `/api/pages/*` (§6.4). Markdown arrives pre-rendered by the backend as `*_html` fields,
with raw HTML off, so the SPA has no markdown library. highlight.js comes from npm. Live
parts poll every 3 s with fetch. Light and dark follow the system setting. The theme is nine
color tokens in `frontend/src/index.css`: `surface`, `raised`, `line`, `fg`, `muted`,
`accent`, `success`, `warning`, and `danger`. Each token has a light value and a dark value
that follow the system, and pages style with them (`bg-surface text-muted border-line`), not
with Tailwind's palette. Text is set in IBM Plex Sans; code, diffs, paths, and the run log in
JetBrains Mono. Both are self-hosted (§4.2). The browser tab shows an SVG favicon,
`frontend/public/favicon.svg`.

Task state is drawn as pills, and reviewer verdicts as chips, each from one component, so
every page uses the same words and colors:
- A status is an outlined pill, its border and text in one token: `Backlog` in `muted`,
  `In progress` in `accent`, `Review` in `warning`, and `Done` in `success`.
- A running task shows `● running`, an outlined `accent` pill, on its board card and in the
  dashboard's runs list. Its dot pulses, and holds still under `prefers-reduced-motion`.
- The two states that wait on me are filled pills with `surface` text: `waiting on you` on
  `warning`, and `escalated` on `danger`. An escalated card or Reviews row also keeps the
  red left bar, and the word itself says escalated, so color is never the only sign. Any
  other stage is plain `muted` text after the status pill.
- A verdict chip reads `sec ✓`, `ux ✓`, `ui ·`, or `code ✗`, colored by verdict: PASS in
  `success`, CHANGES in `danger`, pending (and any other verdict, shown as it is) in `muted`.
  Its `title` names the reviewer and the verdict (`security: PASS`).
- Pills and chips use only `muted`, `accent`, `warning`, `success`, `danger`, and `surface`,
  with no opacity tints, and every text-on-background pair they make clears 4.5:1, light and
  dark. The wireframes draw a pill in parentheses, `(Review)`, and a button in brackets.

Every page has a left sidebar (§8.4), one `<nav aria-label="Sidebar">` with no headings:
- Top: the app name linking to `/`, then the `Workspace` switcher (a native `<select>`) and
  **+ New workspace**, which reveals a name field and posts `POST /api/workspaces` (§6.1).
- Then the selected workspace's projects. Each project is a disclosure button that opens
  **Board**, **Code**, **Reviews** (with its count of tasks waiting on me or escalated, a
  `warning` pill shown when above 0), **Context**, and **Settings**, and the current page's project opens
  by itself with its current link marked.
- Bottom: **Dashboard**, the fctl reference (item 7), and the login runs will use, from
  `GET /api/auth` (`claude auth status`), refreshed every 3 s: `Claude: Pro ✓` when it is a
  subscription, or a red `API key — runs disabled` otherwise. The badge links to `/settings`
  (item 9).

The sidebar's data comes from `GET /api/pages/sidebar` (§6.4) on load and after each
navigation, and is not polled. The selected workspace is the current page's project's (or
the `/workspaces/{id}` page's), else the last one shown, kept in `localStorage`, else the
first. Below `md` the sidebar is a `<dialog>` drawer behind a **Menu** button: Esc and the
backdrop close it, and focus returns to the button. The board, review, and code pages use
the full width beside it, and the other pages keep a max width.

The project pages (Board, Code, Reviews, Context, Settings) share one project header:
`<name> · <workspace>`, with the workspace linking to `/workspaces/{id}`, then the factory
state: `Factory: ready ✓`, else `Factory: <state>` linking to the project's Settings.

1. **Dashboard** (`/`)
   - Tiles: tasks per status, waiting on me (`human_review`), escalated, running now, done
     this week, and runs this week.
   - A table of open tasks per workspace → project, by status.
   - Rounds per task for tasks done in the last 30 days: average, max, and the list.
   - Each tile links to a filtered list. A listed task's Status is its status pill and
     stage, and a running run's is `● running`; ended runs say how they ended.
2. **Workspace** (`/workspaces/{id}`): one row per project with name, path, counts per
   status, factory state (none / uncommitted / ready), and last activity. **+ Workspace**
   creates one. For each project, its Settings page (item 12) moves it to another workspace.
3. **Project board** (`/projects/{id}`): kanban (wireframe below). The header is the project
   header plus **+ New task**, **Run next**, and the hint for why runs are off. Cards move
   between columns by drag and drop (native HTML5, no library). Clicking a card opens the task
   detail.
4. **Task detail** (`/tasks/{id}`)
   - Header: title, the status pill and stage, branch, Review, Run / Stop / Retry, run
     status. Next to Review, **Export** downloads the task bundle
     (`GET /api/tasks/{id}/export`, a plain `<a download>`), and an **Include transcripts**
     checkbox adds them, labelled with the warning that they can hold paths, env, and
     secrets.
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
   - Linked from the sidebar. A table of contents is built from its headings.
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
9. **Settings** (`/settings`)
   - A **Claude login** section: auth method, plan, account (the claude.ai email), and
     whether runs are enabled, from `GET /api/auth`.
   - **Log in with Claude** (**Log in again** when signed in) posts `POST /api/auth/login`
     and shows **Open the Claude sign-in page**, which opens claude.ai in a new tab, and a
     **Code** field. **Submit code** posts the pasted `<code>#<state>` to
     `POST /api/auth/login/code`, and on success the section shows the new login. The button
     then reads **Start over**, which begins a fresh login.
   - Subscription login only (§4.3): no API key field.
10. **Reviews** (`/projects/{id}/reviews`, Closed at `?tab=closed`; wireframe §8.5)
    - From the board view-model, polled every 3 s.
    - **Open** is the Review column: escalated, then waiting on you, then the rest.
      **Closed** is the Done column. The tabs show counts, and each tab has an empty state.
    - Each row has `#id title` linking to `/tasks/{id}/review`, its state pill (Open rows
      only), branch, round, verdict chips, and +/−.
11. **Project context** (`/projects/{id}/context`)
    - The editor, open on load (`GET`/`PUT /api/projects/{id}/context`): a textarea, a live
      UTF-8 byte count against the 16 KB cap (`over the limit` disables Save), and **Save**.
    - Beside it, a **Preview** of the saved `context_html`, refreshed by each Save.
    - Loaded once, not polled.
12. **Project settings** (`/projects/{id}/settings`)
    - Path, remote, default branch, and test command, read-only.
    - The factory state with its hint, plus **Create factory** (with *Overwrite*) unless
      ready, and its written and skipped lists and commit hint (§3.2).
    - **Import** takes a task bundle (a `.zip` from **Export**) from a file input, disabled
      until a file is chosen, and posts it raw to `POST /api/projects/{id}/import`.
      `Imported #12 <title>` links to the task, or the refusal's detail shows.
    - **Move** to another workspace (`PATCH /api/projects/{id}`).
    - Loaded once, and reloaded after each of these actions.

### 8.1 Board
```
api-server · personal              Factory: ready ✓   [+ New task]  [Run next ▶]
┌ Backlog 3 ──────────┐ ┌ In progress 1 ─────────────┐ ┌ Review 2 ──────────────────┐ ┌ Done 5 ─────┐
│ #14 Export CSV      │ │ #13 Audit log              │ │ #12 Rate-limit login       │ │ #9 Health   │
│              [Run]  │ │ (● running) agent_review   │ │ (waiting on you)           │ │ 1 round     │
├─────────────────────┤ │ r1 sec ✓ ux ✓ ui · code ✗  │ │ r2 sec ✓ ux ✓ ui ✓ code ✓  │ ├─────────────┤
│ #15 Dark mode       │ │ started 10:02              │ │ +126 −9                    │ │ #8 Login UX │
│              [Run]  │ └────────────────────────────┘ ├────────────────────────────┤ │ 3 rounds    │
├─────────────────────┤                                │▌#11 Webhooks               │ └─────────────┘
│ #16 Rename env vars │                                │▌(escalated)                │
│              [Run]  │                                │▌r2 sec ✗ ux ✓ ui ✓ code ✓  │
└─────────────────────┘                                │▌+88 −4                     │
                                                       └────────────────────────────┘
pills, drawn ( ): a status is outlined in its token: Backlog muted, In progress accent,
  Review warning, Done success. (● running) is outlined accent; its dot pulses, and holds
  still under prefers-reduced-motion. (waiting on you) is filled warning, (escalated) filled
  danger. Cards show no status pill: the column names it.
escalated cards: red left bar ▌ + (escalated)
chips: ✓ PASS in success, ✗ CHANGES in danger, · pending in muted; title "security: PASS"
stalled card: "stalled · build  [Retry]"
```

### 8.2 Review — Conversation
```
#12 Rate-limit login endpoint                          [Request changes]  [Approve]
(Review) (waiting on you)   factory/12-rate-limit-login   round [2 ▾]   4 files  +126 −9
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

### 8.4 Sidebar
```
┌──────────────────────┐
│ Claude Factories     │
│ Workspace [personal▾]│
│ + New workspace      │
│                      │
│ ▾ api-server         │
│     Board            │  ← current page: aria-current, accent
│     Code             │
│     Reviews      (2) │  ← waiting on me or escalated, when above 0: a warning pill
│     Context          │
│     Settings         │
│ ▸ web                │
│                      │
│ Dashboard            │
│ fctl reference       │
│ Claude: Pro ✓        │
└──────────────────────┘
below md: [☰ Menu] opens the same sidebar as a drawer (<dialog>)
```

### 8.5 Reviews
```
api-server · personal                                         Factory: ready ✓
─ Open 2 ─┬─ Closed 5 ────────────────────────────────────────────────────────
▌#11 Webhooks                         (escalated)
▌factory/11-webhooks   round 2   sec ✗  ux ✓  ui ✓  code ✓   +88 −4
 #12 Rate-limit login endpoint        (waiting on you)
 factory/12-rate-limit-login   round 2   sec ✓  ux ✓  ui ✓  code ✓   +126 −9
each row links to /tasks/{id}/review · Closed: the Done column, rows without the state pill
```
