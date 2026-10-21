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

Components come from Preline UI: the free `preline` npm package (MIT, with Preline's Fair Use
License beside it), never Preline Pro. Vite bundles it into `dist/`, so it loads from no CDN.
`index.css` imports its Tailwind variants, `main.jsx` loads its JS plugins once, and they
re-initialise after each route change and each data load. Its markup is restyled onto the
nine tokens, with none of Preline's theme CSS, palette, or class-based dark mode, so light and
dark stay the app's. The first component taken from it is the file tree of items 5 and 6:
Preline Tree View's rows, folder and file icons, `+/−` toggles, and guide lines. React opens and
closes its directories, each one a disclosure button with `aria-expanded`, and a closed
directory's entries leave the Tab order.

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

The task, review, code, and transcript pages open with one breadcrumb, a
`<nav aria-label="Breadcrumb">` reading `workspace › project › #id › page`: the workspace
links to `/workspaces/{id}`, the project to `/projects/{id}`, and `#id` to `/tasks/{id}`. The
last item is the current page, as plain text: `#12` on the task page, `Review` on the review
page, the agent's label on the transcript page, and `Code` on the code page, which has no
`#id`. The `›` separators are hidden from screen readers. Its names come from the page's own
view-model, as the project and workspace are now. The other pages have no breadcrumb: the
sidebar and the project header cover them.

Loading, failures, times, and motion are the same on every page:
- While a page's first view-model loads, it shows a skeleton: pulsing `line` blocks shaped and
  sized like the top of the page that replaces them, in the page's own grid and spacing, so
  nothing jumps when it arrives. It is one `role="status"` that screen readers hear as
  `Loading…`, with no headings, links, or buttons. Reloads (after an action, on a new round,
  file, or **Show all**) keep the last view until the new one arrives. A failed first load is
  the red alert.
- On the pages polled every 3 s (Board, Task detail, Reviews), a failed poll over a page that
  has loaded leaves the page as it was and shows a muted `Offline — retrying` banner, fixed at
  the bottom of the content column, without the error's detail. It is a polite status, shown
  once while the failures last, and the next good poll removes it. A 404 is still the
  not-found page, and refusals of actions stay red alerts.
- Last activity, a running run's start, the status history, and the review timeline read as
  relative times: `just now`, `5m ago`, `3h ago`, then by calendar day `yesterday` and `4d ago`,
  and the date (`2026-10-13`) from a week back. The full local `YYYY-MM-DD HH:MM` is in the
  `title`, and the ISO time in `<time dateTime>`. They are worked out as the page renders, so
  the 3 s polls keep them current. Every other time is the absolute `YYYY-MM-DD HH:MM`.
- **Run**, **Retry**, **Run next**, **Stop**, **Comment**, **Submit review**, and **Log in**
  show a small spinner over their label while their request is pending, at the same size.
- Motion: only `opacity` and `transform` transition, for 150 ms at most: the sidebar's project
  chevron turning, the dragged card's dim, and popovers and the offline banner fading in. Under
  `prefers-reduced-motion` nothing moves: transitions are off, and the skeleton's pulse, the
  running dot, and the spinner hold still.

1. **Dashboard** (`/`)
   - First, **Needs you**: the escalated tasks, then the ones waiting on me (`human_review`),
     each newest first. A row shows `#id title` linking to `/tasks/{id}/review`, its
     `escalated` or `waiting on you` pill, the project linking to its board, `round N` (left
     out when the task has no rounds), and the age since the task last changed (`5m`, `3h`,
     `2d`). An escalated row keeps the red left bar. With none, it says `Nothing needs you.`
     It ignores `?show=`.
   - Tiles in two groups, each under a small `muted` label. **Attention**: waiting on me,
     escalated, and running now. A count above 0 colors the tile's count and border,
     `danger` for escalated and `accent` for the other two; at 0 they stay `fg` and `line`.
     **Throughput**: done this week, runs this week, then tasks per status (Backlog, In
     progress, Review, Done). Each count is large, and its label `muted`.
   - Each tile links to a filtered list, shown after the tiles. A listed task's Status is
     its status pill and stage, and a running run's is `● running`; ended runs say how they
     ended.
   - A table of open tasks per workspace → project, by status. It sits in its own box that
     scrolls sideways when the table is wider than the screen.
   - Rounds per task for tasks done in the last 30 days: average and max, with one small
     inline-SVG bar per task beside them, oldest left, its height rounds / max, in `accent`,
     and the list.
2. **Workspace** (`/workspaces/{id}`): one row per project with name, path, counts per
   status, factory state (none / uncommitted / ready), and last activity as a relative time
   (`3h ago`). **+ Workspace** creates one. For each project, its Settings page (item 12) moves
   it to another workspace.
3. **Project board** (`/projects/{id}`): kanban (wireframe below). The header is the project
   header plus **+ New task**, **Run next**, and the hint for why runs are off. **+ New task**
   opens its form in a native popover, which Esc or a click outside closes, and a created task
   closes it. Clicking a card opens the task detail.
   - Cards move by drag and drop (native HTML5, no library). While a card is dragged it dims,
     the column under the pointer gets an `accent` ring, and an `accent` line marks the gap the
     drop takes. No line shows where the drop would leave the card where it is.
   - Each card also has a **Move** menu, a native popover: the other three columns, then **Up**
     and **Down** on Backlog cards (no Up on the top card, no Down on the bottom one). A column
     puts the card at its bottom; Up and Down move it one place, so Backlog reorders without
     dragging. The menu sends the same `PATCH /api/tasks/{id}` as a drop (§6.2), and focus
     comes back to the card's **Move** button after the board reloads.
   - A move, by menu or drop, is announced in a visually hidden `aria-live` status region
     (`Moved #14 Export CSV to Review.`). A refusal, such as the 409 while a run is active,
     shows in the board's alert instead. The alert holds only refusals of Run, Retry, Run next,
     and moves: the next of these empties it as it starts, and polls leave it alone.
   - From `md` up each column's card list scrolls on its own under its heading. Below `md` the
     columns stack and the page scrolls.
4. **Task detail** (`/tasks/{id}`)
   - Header: the breadcrumb, then the title row: the title, Run / Stop / Retry, the run
     status (`run #N <status>`, and for a running run its start as a relative time:
     `run #41 running · started 5m ago`), and beside Run or Retry the hint for why runs are
     off. The row wraps on narrow screens. Under it, the status line: the status pill and
     stage, branch, Review, and an **Export** button.
   - **Export** opens a native popover holding an **Include transcripts** checkbox,
     labelled with the warning that they can hold paths, env, and secrets, and a
     **Download** link to the task bundle (`GET /api/tasks/{id}/export`, a plain
     `<a download>`, with `?transcripts=1` while the box is ticked). Esc or a click outside
     closes it, and a download leaves it open.
   - Spec (rendered markdown).
   - Rounds: build notes (collapsible), 4 chips that open the verdict, and +/−.
   - Agents per round: one row per transcript of that round, with its name (else agent type,
     else `agent`) linking to its transcript, model, turns, tokens
     (`in 1,234 · cache 56,789 · out 2,345`), and duration (`4m 12s`). Transcripts with no
     round (the orchestrator, the spec-writer, the reviewers, the approver) are listed under
     **Other agents** after Rounds, each with its `run #`.
   - The approver's decision.
   - Status history (`events`): each entry's relative time, then its label
     (`5m ago created · backlog`).
   - Run log tail (collapsed).
   - "Take over in terminal" command.
   - A link to Review.
5. **Code review** (`/tasks/{id}/review`): GitHub-style (wireframes below).
   - Round selector, defaulting to latest. The diff is a table built from the backend's diff
     rows, with one row per line and anchor `path:side:line`, and highlight.js colors it.
   - Clicking a line number opens an inline comment form.
   - Files changed has the file tree (§8.3) beside the diffs: each file links to its diff and
     shows its `+A −D`. Every directory starts open, and its `+/−` toggle collapses it.
   - The breadcrumb, then the title row with **Review changes**, which opens a native
     popover: a **Summary** box, an **Approve** / **Request changes** radio with neither
     picked, and **Submit review**. **Review changes** is enabled only in `review` with at
     least one round. **Submit review** stays disabled until a choice is picked, and for
     Request changes until the summary has text. The summary goes with either choice:
     Approve sends it as its `body_md`, blank or not. A success closes and resets the
     popover; a refusal shows its detail inside it and keeps what was typed.
   - On a done task, **Commit it yourself** shows the commit commands (§3.7) with a **Copy**
     button. It writes them with `navigator.clipboard` and then reads `Copied`. Without the
     clipboard, or when the write fails, it selects the commands' text and says to press
     Ctrl+C (⌘C on a Mac).
6. **Project code** (`/projects/{id}/code`)
   - The breadcrumb `workspace › project › Code` above the project header, both from the
     code view-model's project.
   - Left: the file tree (wireframe §8.6) of `git ls-files` in the main checkout. The
     directories of the file shown open, and the file is marked as the current page. Every
     other directory starts closed, and its `+/−` toggle opens it. Opening another file opens
     its directories and leaves the ones I opened or closed as they were.
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
   - Header: the breadcrumb, whose `#id` links to the task, then the agent's label,
     `run #N`, model, turns, tokens, duration, and **Download raw**
     (`GET /api/transcripts/{id}/raw`).
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
│       [Move] [Run]  │ │ (● running) agent_review   │ │ (waiting on you)           │ │ 1 round     │
├─────────────────────┤ │ r1 sec ✓ ux ✓ ui · code ✗  │ │ r2 sec ✓ ux ✓ ui ✓ code ✓  │ │     [Move]  │
│ #15 Dark mode       │ │ started 5m ago             │ │ +126 −9                    │ ├─────────────┤
│       [Move] [Run]  │ │                    [Move]  │ │                    [Move]  │ │ #8 Login UX │
├─────────────────────┤ └────────────────────────────┘ ├────────────────────────────┤ │ 3 rounds    │
│ #16 Rename env vars │                                │▌#11 Webhooks               │ │     [Move]  │
│       [Move] [Run]  │                                │▌(escalated)                │ └─────────────┘
└─────────────────────┘                                │▌r2 sec ✗ ux ✓ ui ✓ code ✓  │
                                                       │▌+88 −4                     │
                                                       │▌                   [Move]  │
                                                       └────────────────────────────┘
pills, drawn ( ): a status is outlined in its token: Backlog muted, In progress accent,
  Review warning, Done success. (● running) is outlined accent; its dot pulses, and holds
  still under prefers-reduced-motion. (waiting on you) is filled warning, (escalated) filled
  danger. Cards show no status pill: the column names it.
escalated cards: red left bar ▌ + (escalated)
chips: ✓ PASS in success, ✗ CHANGES in danger, · pending in muted; title "security: PASS"
stalled card: "stalled · build  [Retry]"
started 5m ago: a running card's start, relative; its title holds the local YYYY-MM-DD HH:MM
[Move]: a popover menu on every card: the other columns, then Up and Down in Backlog. A
  move is announced in a hidden aria-live region; a refusal shows in the board's alert.
while dragging: the card dims, the column under the pointer gets an accent ring, and an
  accent line marks the gap the drop takes (none where the card would stay put)
columns: from md up each card list scrolls on its own under its heading
```

### 8.2 Review — Conversation
```
personal › api-server › #12 › Review
#12 Rate-limit login endpoint                                    [Review changes ▾]
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
 Timeline   2h ago created · 2h ago in_progress · 1h ago round 1 · 1h ago round 2
            1h ago approver APPROVE · 1h ago review
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │ Leave a comment…                                                                   │
 └───────────────────────────────────────────────────────────────────────────────────┘
timeline: relative times (2h ago), each with its local YYYY-MM-DD HH:MM as its title
[Review changes ▾]: a popover under the button
  ┌ Summary ───────────────────────────┐
  │                                    │
  └────────────────────────────────────┘
  ( ) Approve    ( ) Request changes
                        [Submit review]
```

### 8.3 Review — Files changed
```
─ Conversation ─┬─ Files changed 4 ─────────────────────────────────────────────────────
 [−] app/             │ app/limits.py  (new)                                         +42 −0
  │  limits.py +42 −0 │  ─────────────────────────────────────────────────────────────────────
  │  auth.py +12 −3   │      29 + def client_key(request):
  │  settings.py +4 −0│      30 +     # behind proxy only if TRUSTED_PROXY set
 [+] tests/           │      31 +     return request.client.host
                      │      ┌ security (round 1): Use request.client.host unless behind… ┐
                      │      │ me: Make the limit configurable via settings.        [Reply]│
                      │      └───────────────────────────────────────────────────────────┘
                      │      32 +
                      │ app/auth.py                                                  +12 −3
                      │  @@ -41,7 +41,9 @@ def login():
                      │  41 41      user = authenticate(form)
                      │  42    -    if not user:
                      │     42 +    if not user and limiter.hit(client_key(request)):
tree: Preline Tree View's rows on the tokens; [−] is an open directory and [+] a closed one, │ its
  guide line, and a folder or file icon (not drawn) starts each row. Every directory starts open;
  tests/ has been collapsed here. Each file links to its diff, with its +A −D in muted.
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

### 8.6 Code
```
personal › api-server › Code
api-server · personal                                         Factory: ready ✓
Branch main
 README.md            │ app/limits.py
 [−] app/             │ ┌────┬─────────────────────────────────────────────────────┐
  │  auth.py          │ │  1 │ import time                                         │
  │  limits.py        │ │  2 │                                                     │
  │  settings.py      │ │  3 │ WINDOW = 60                                         │
 [+] docs/            │ │  4 │                                                     │
 [+] tests/           │ │  5 │ def client_key(request):                            │
                      │ │  6 │     return request.client.host                      │
                      │ └────┴─────────────────────────────────────────────────────┘
tree: Preline Tree View's rows, as in §8.3. The file shown (app/limits.py) is the current page:
  aria-current, semibold accent on a raised row. Its directories open; the others start closed.
  [+] opens a directory and [−] closes it; another file opens its own and leaves the rest as they were.
viewer: the file's path, then a highlighted view with an aria-hidden gutter of line numbers; binary
  files and files over 1 MB show "not shown". The landing (no ?path=) renders README.md.
```
