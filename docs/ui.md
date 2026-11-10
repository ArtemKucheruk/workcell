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
  `warning` pill shown when above 0), **Context**, **Factories**, and **Settings**, and the current page's
  project opens by itself with its current link marked. **Factories** is also marked in the factory designer.
- Each project row, at its right, and the workspace switcher, beside it, have a `⋯` button
  (`Actions for <project>`, `Actions for workspace <name>`) that opens a native popover menu.
  The project's holds **Rename**, a **Settings** link, a muted `Move to workspace` caption with
  one button per other workspace (both left out when there is none), and, under a divider,
  **Delete** in `danger`. The workspace's holds **Rename**, a **Settings** link (item 13), and,
  under a divider, **Delete**. From `md` up a `⋯` is hidden by opacity only, never `display`, so
  Tab still reaches it: it shows while its row is hovered or holds focus, or while its menu is
  open. Below `md` it always shows.
- **Rename** replaces the project's name, or the workspace `<select>`, with a text field holding
  the name, focused and selected. Enter sends the PATCH (§6.1), even with the name unchanged.
  Esc or leaving the field cancels with no request. A refusal shows its detail beside the field,
  which stays. After a save or Esc, focus is on the row's `⋯`.
- **Move to workspace** sends `PATCH /api/projects/{id}` with the chosen `workspace_id`, then
  focus goes to the workspace `<select>`. A refusal shows its detail in the sidebar.
- **Delete** opens a modal `<dialog>` (§8.4) with **Cancel** first, then **Delete** filled
  `danger` with `surface` text. It is never disabled ahead of time: the server decides, and its
  409 detail shows inside the dialog, which stays open. A deleted project's app goes to
  `/workspaces/{id}`, a deleted workspace's to `/`.
- Bottom: **Dashboard**, **Agents** (item 15), the fctl reference (item 7), and the login runs
  will use, from `GET /api/auth` (`claude auth status`), refreshed every 3 s: `Claude: Pro ✓`
  when it is a subscription, or a red `Not signed in — runs disabled` otherwise. The badge links
  to `/settings` (item 9). **Agents** carries the count of running runs as a filled `accent` pill
  with `surface` text when above 0: the sidebar view-model's `running` counts summed over every
  workspace's projects, the unselected ones too. It updates when the sidebar loads, so it can
  lag until the next navigation.

The sidebar's data comes from `GET /api/pages/sidebar` (§6.4) on load and after each
navigation, and is not polled. A rename or move, from the sidebar or a Settings page, also
reloads it, with no navigation; other pages showing the old name catch up on their next load
or poll. The selected workspace is the current page's project's (or
the `/workspaces/{id}` page's), else the last one shown, kept in `localStorage`, else the
first. Below `md` the sidebar is a `<dialog>` drawer behind a **Menu** button: Esc and the
backdrop close it, and focus returns to the button. The board, review, code, and factory designer
pages use the full width beside it, and the other pages keep a max width.

The project pages (Board, Code, Reviews, Context, the Factories list, Settings) share one project header:
`<name> · <workspace>`, with the workspace linking to `/workspaces/{id}`, then the factory
state: `Factory: ready ✓`, else `Factory: <state>` linking to the project's Settings.

The task, review, code, and transcript pages open with one breadcrumb, a
`<nav aria-label="Breadcrumb">` reading `workspace › project › #id › page`: the workspace
links to `/workspaces/{id}`, the project to `/projects/{id}`, and `#id` to `/tasks/{id}`. The
last item is the current page, as plain text: `#12` on the task page, `Review` on the review
page, the agent's label on the transcript page, and `Code` on the code page, which has no
`#id`. The `›` separators are hidden from screen readers. Its names come from the page's own
view-model, as the project and workspace are now. The factory designer opens with
`workspace › project › Factories › <name>` instead, Factories linking to `/projects/{id}/factories` and the
factory's name the current page. The other pages have no breadcrumb: the sidebar and the project header cover
them.

Loading, failures, times, and motion are the same on every page:
- While a page's first view-model loads, it shows a skeleton: pulsing `line` blocks shaped and
  sized like the top of the page that replaces them, in the page's own grid and spacing, so
  nothing jumps when it arrives. It is one `role="status"` that screen readers hear as
  `Loading…`, with no headings, links, or buttons. Reloads (after an action, on a new round,
  file, or **Show all**) keep the last view until the new one arrives. A failed first load is
  the red alert.
- On the pages polled every 3 s (Board, Task detail, Reviews, Agents), a failed poll over a page that
  has loaded leaves the page as it was and shows a muted `Offline — retrying` banner, fixed at
  the bottom of the content column, without the error's detail. It is a polite status, shown
  once while the failures last, and the next good poll removes it. A 404 is still the
  not-found page, and refusals of actions stay red alerts.
- Last activity, a running run's start, the status history, the review timeline, and a factory's
  last update read as relative times: `just now`, `5m ago`, `3h ago`, then by calendar day `yesterday` and `4d ago`,
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
   it to another workspace. The workspace's own Settings page (item 13, from the sidebar's
   workspace `⋯`) renames or deletes it.
3. **Project board** (`/projects/{id}`): kanban (wireframe below). The header is the project
   header plus **+ New task**, **Run next**, and the hint for why runs are off. Under the hint, when
   the view-model's `factory_error` is set (the board's automatic `factory/` sync was refused, §6.4),
   one muted line, `factory/: <factory_error>`, not an alert. **+ New task**
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
   - The Move menu ends with a divider, then **Edit** and **Delete**, on every card. **Edit**
     opens the **+ New task** popover under **+ New task**, labelled `Edit #14`, with Title and
     Description filled from the card and **Save** in place of **Add task**; a poll never refills
     it while it is open, and **+ New task** always opens it empty, in create mode. **Save** sends
     `PATCH /api/tasks/{id}` with `title` and `description_md` (§6.2), closes the popover, reloads
     the board, announces `Saved #14 <title>.`, and puts focus on the card's **Move** button.
     **Delete** opens a modal `<dialog>` (wireframe below); its **Delete** sends
     `DELETE /api/tasks/{id}`, then the board reloads without the card, `Deleted #14 <title>.` is
     announced, and focus goes to **+ New task**. **Cancel** or Esc closes it with no request, and
     focus returns to the card's **Move** button. **Delete** is disabled on a running card, with
     the title `Stop the run to delete this task`; **Edit** never is. A refusal of either shows its
     detail inside the popover or dialog, which stays open with what was typed; the board's alert
     is left alone.
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
   - Run log tail (collapsed; `/tasks/{id}#run-log` opens it and scrolls to it).
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
   - Left: the file tree (wireframe §8.6) of `git ls-files` in the main checkout, or of the
     picked branch's `git ls-tree -r --name-only`. The
     directories of the file shown open, and the file is marked as the current page. Every
     other directory starts closed, and its `+/−` toggle opens it. Opening another file opens
     its directories and leaves the ones I opened or closed as they were.
   - The landing view renders `README.md`.
   - Clicking a file opens a highlighted view with line numbers. Binary files and files
     over 1 MB show "not shown".
   - The header has a **Branch** picker, a native `<select>`: first the checked-out branch (or
     `detached HEAD`), which is the working tree, then the other listed branches (local ones,
     then `origin/<name>` for each origin branch with no local twin). Picking one sets
     `?branch=` and opens that branch's README landing, and file links and `?path=` deep links
     keep `?branch=`. Its files come from `git cat-file blob <ref>:<path>`, with the same landing and
     not-shown rules, and a symlink shows its target path. An unknown `?branch=` is not found.
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
   - A `Claude accounts` section, from `GET /api/auth/accounts`, loaded once and not polled. One
     item per account, in the order received: its email as the title (`Not signed in` without
     one), an outlined `accent` `active` pill on the active one, and Auth method, Plan (`—` when
     signed out), and Folder (its `config_dir`, mono, muted). With none, `No Claude accounts yet.`
   - Each item has **Make active** (inactive items only), **Log in again** (**Log in** when signed
     out), and **Disconnect**. **+ Add account** sits below the list, and below that whether runs
     are enabled: `Runs enabled`, else in `text-danger` `No active account — runs disabled`, or
     `Not signed in with a Claude subscription — runs disabled` when the active one is signed out.
   - **+ Add account**, **Log in**, and **Log in again** post `POST /api/auth/login`, with the
     item's `account_id` (none for a new account), and show **Open the Claude sign-in page**,
     which opens claude.ai in a new tab, and a **Code** field. **Submit code** posts the pasted
     `<code>#<state>` with that `account_id` to `POST /api/auth/login/code`, and on success the
     list reloads and shows `Logged in as <email>`. While a login is pending, its button reads
     **Start over**, which begins a fresh login for the same account.
   - **Make active** posts `POST /api/auth/accounts/{id}/activate` and reloads the list, and focus
     goes to that item's login button. A refusal (a run is active) shows its detail in an alert.
   - **Disconnect** opens a modal `<dialog>` like Delete's (§8.4), titled `Disconnect <email>?`
     (`Disconnect this account?` without an email): `This signs the account out with claude auth
     logout and removes it from the app, with its config folder if the app created it.`, plus
     ` Runs stay disabled until you make another account active.` for the active one. **Cancel**
     comes first and has focus, then **Disconnect** filled `danger`, which sends
     `DELETE /api/auth/accounts/{id}`. A refusal (a run is active, or claude failed) shows its
     detail inside the dialog, which stays open. On success the list reloads, focus goes to
     **+ Add account**, and the sidebar badge follows on its next poll.
   - Subscription login only (§4.3): no API key field.
10. **Reviews** (`/projects/{id}/reviews`, Closed at `?tab=closed`; wireframe §8.5)
    - From the board view-model, polled every 3 s.
    - **Open** is the Review column: escalated, then waiting on you, then the rest.
      **Closed** is the Done column. The tabs show counts, and each tab has an empty state.
    - Each row has `#id title` linking to `/tasks/{id}/review`, its state pill (Open rows
      only), branch, round, verdict chips, and +/−.
11. **Project context** (`/projects/{id}/context`; wireframe §8.9)
    - A grid of context cards, loaded once, not polled: `GET /api/projects/{id}/context` for the
      pinned card and `GET /api/projects/{id}/context/items` for the rest (§6.1). Agents get all of
      them through `fctl show`, in grid order.
    - The pinned card, **Stack and conventions**, comes first. It shows `Pinned` and
      `Agents read it at the top of fctl show.`, and has no `⋯` menu, so it can't be moved or
      deleted. The top-level cards and groups follow in position order, each with its title as a
      button and its description. A group shows its count (`2 cards`, `1 card`, `0 cards`), and a
      card read from a path shows that path in mono, muted. A group's cards appear only inside it.
    - The toolbar: **+ New card**, **+ New group**, **Upload files** (a file input with `multiple`,
      taking `.md`, `.markdown`, and `.txt`, posted one file per request in selection order), and a
      **Path** field with **Add from path**, hinted `An absolute path to a .md, .markdown, or .txt
      file, or a folder of them, on the backend's machine. In Docker, only mounted folders exist.`
      A folder becomes a group holding a card per file.
    - A card's title opens it in a modal `<dialog>`. The pinned card's holds 033's editor: a
      textarea, a live UTF-8 byte count against the 16 KB cap (`over the limit` disables Save), and
      beside it a **Preview** of the saved `context_html`. Any other card's holds Title,
      Description, and Content, with the same byte count and Preview. **Save** sends
      `PUT /api/projects/{id}/context` or `PATCH /api/context/items/{id}`, and a refusal shows
      inside the dialog, which keeps the draft. **+ New card** opens it empty, and **+ New group**
      with only Title and Description. Renaming a card is its Title field.
    - Each other card's `⋯` button opens a native popover menu, like the sidebar's: **Edit**,
      **Reload from path** (cards read from a path only), a muted `Move to group` caption with a
      button per other group, **Move out of group** for a card in a group, and, under a divider,
      **Delete** in `danger`. A group's menu holds **Edit** and **Delete**. Delete opens the
      `DeleteDialog` of §8.4: the files a card was read from stay on disk.
    - A group's title opens it in a modal `<dialog>`: its description, its cards with their `⋯`
      menus, **+ New card**, Upload files, and Add from path, each adding into the group, and
      **Close**.
    - A refused move, reload, upload (`<file name>: <detail>`), or path read shows its detail in
      an alert, the group modal's when it came from there.
12. **Project settings** (`/projects/{id}/settings`)
    - At the top of Repository, one form: **Name** and **Test command** (empty when not set),
      with one **Save** sending both as typed (`PATCH /api/projects/{id}`). A blank test command
      clears it, shown as `not set`. A refusal shows its detail in the form, which keeps what was
      typed. A save also reloads the sidebar.
    - Path, remote, and default branch, read-only, with the note: "Path, remote, and default
      branch come from `fctl connect`. Rerunning it in the repo also resets the name, and the
      test command when it passes one."
    - The factory state with its hint, plus **Create factory** (with *Overwrite*) unless
      ready, and its written and skipped lists and commit hint (§3.2).
    - **Import** takes a task bundle (a `.zip` from **Export**) from a file input, disabled
      until a file is chosen, and posts it raw to `POST /api/projects/{id}/import`.
      `Imported #12 <title>` links to the task, or the refusal's detail shows.
      Below it, a muted line, `The repo's factory/board.json and factory/backlog.md as tasks. The
      board also syncs them when either file changes.`, and **Sync factory/**, which sends
      `POST /api/projects/{id}/import-factory` `{}`, disabled while pending. On 200 a polite live
      region says `Synced factory/: <n> new, <m> updated, <k> skipped` and the page reloads; a
      refusal's detail shows as an alert in the section.
    - **Move** to another workspace (`PATCH /api/projects/{id}`).
    - **Danger zone**, the last section: **Delete project** (filled `danger`) opens the
      sidebar's project delete dialog (§8.4). On 204 the app goes to `/workspaces/{id}`.
    - Loaded once, and reloaded after each of these actions.
13. **Workspace settings** (`/workspaces/{id}/settings`)
    - Loads `GET /api/pages/workspaces/{id}` once, and again after a rename. The sidebar
      selects this workspace. The title reads `<name> · Settings`. No breadcrumb.
    - `h1` the workspace's name, then a **Name** form with **Save**
      (`PATCH /api/workspaces/{id}`). A refusal, such as `workspace work already exists`, shows
      its detail in the form, which keeps the typed name. A save also reloads the sidebar.
    - **Projects**: each project's name, linking to its Settings (where Move and Delete live),
      and its path. With none, `No projects.`
    - **Danger zone**: **Delete workspace** opens the sidebar's workspace delete dialog (§8.4).
      On 204 the app goes to `/`; a workspace that still holds projects gets its 409 inside the
      dialog.
14. **Factories** (`/projects/{id}/factories`, and the designer at `/projects/{id}/factories/{fid}`;
    wireframe §8.7)
    - A factory is a design: a graph of agents and conditions saved in the app
      (`docs/data-model-and-api.md §6.1`). Runs still use the `.claude/` files that Create factory
      or a design's **Write to repo** wrote.
    - The list loads `GET /api/pages/projects/{id}` (the project header) and
      `GET /api/projects/{id}/factories` once each, with no polling, and again after each of its
      actions. The title reads `<project> · Factories`. **+ New factory** sits in the header.
    - Each row: the name, linking to the designer, the node count (`10 nodes`, `1 node`), and
      Updated as a relative time. With none, `No factories yet.`
    - **+ New factory** opens a native popover with a `Name` field and **Create**
      (`POST /api/projects/{id}/factories`). On 201 the designer opens on the default loop. A
      refusal (`factory default already exists`) shows inside the popover, which keeps the typed
      name.
    - **Rename** (`Rename <name>`) works in place, the sidebar's way: Enter sends
      `PUT /api/factories/{fid}` `{"name"}`, Esc or blur cancels, and a refusal shows beside the
      field, which stays. **Delete** (`Delete <name>`) opens the delete dialog titled
      `Delete factory <name>?`: "This removes the factory's design from the app. Files in the
      repo, such as the ones Create factory wrote, stay."
    - The designer loads `GET /api/factories/{fid}` once, with no polling, and is a wide page. A
      factory of another project at this URL is the not-found page. The title reads
      `<name> · <project>`. The breadcrumb, then an `h1` with the name, and at its right a
      `role="status"` reading `Unsaved changes` while unsaved, **Files**, and **Save**.
    - The palette (left) lists **Agents** (Spec writer, Builder, Reviewer, Approver, Custom agent)
      and **Conditions** (All reviews PASS, Any review CHANGES, Rounds used < N, Decision
      APPROVE). An item drags onto the flow, or a click (Enter, Space) adds it at the center. A new
      agent is named after its kind (`spec-writer`, `builder`, `reviewer`, `approver`, `agent`),
      with `-2`, `-3`… until unique, model `inherit`, no tools, and an empty description and
      prompt; a builder gets side `both`, a reviewer focus `custom`, and Rounds used < N gets
      `n` 2. The new node is selected. `«` collapses the palette to a rail.
    - Each node is a card: an icon, its title (the agent's name, or the condition's question with
      `n` filled in), and a one-line summary (`Reviewer · security · sonnet`, `Condition`). A
      condition has a `yes` handle in `success` and a `no` handle in `danger`, each with its word.
      An agent has one input and one output handle; start has only an output. Each edge has a `×`
      at its midpoint (`Delete edge <source> → <target>`). React Flow's delete key removes
      selected nodes and edges; start can't be deleted. Its stock zoom, fit, and lock controls sit
      at the bottom left, over a dotted background.
    - The **Node** panel (right) edits the one selected node: `Name` (`a-z, 0-9, and -`),
      `Description`, `Model` (inherit, opus, sonnet, haiku), `Tools` (comma-separated), and
      `Prompt` (monospace), plus `Side` for a builder and `Focus` for a reviewer. Rounds used < N
      shows `N` (min 1); start and the other conditions say what they do. With none or several
      selected, `Select a node to edit it.` Edits apply to the card at once.
    - Any change to the graph, but not selecting or React Flow's own measuring, makes the page
      unsaved. **Save**, or Ctrl/⌘+S, sends `PUT /api/factories/{fid}` `{"graph"}` with its
      spinner, and is disabled while nothing is unsaved. A refusal (`two agents are named
      builder`) shows as a red alert beside Save, and the graph stays unsaved. Leaving the page
      while unsaved asks the browser to confirm (`beforeunload`); in-app links don't.
    - Below `md` the palette starts collapsed and the Node panel moves under the flow.
    - **Files** opens a wide modal dialog (the delete dialog's kind, about `max-w-5xl`) headed
      `Files`. Each time it opens it sends `GET /api/factories/{fid}/files`, showing a
      `role="status"` `Loading…` meanwhile. The paths list as buttons beside the preview from `md`
      up, and above it below `md`. The first is selected (`aria-current="true"`), and the preview
      shows its content highlighted by highlight.js as markdown. While the page is unsaved, it says
      `Showing the last saved design. Save to include your changes.` At the bottom: **Download
      .zip** (a link to `GET /api/factories/{fid}/download` with `download`), *Overwrite existing
      files*, and **Write to repo** (`POST /api/factories/{fid}/write`), whose 200 shows Create
      factory's result view (item 12, one shared component). A refused GET (`agent linter needs a
      description`) shows as a red alert with no list, link, or Write button; a refused write
      shows as a red alert in the dialog, which keeps its list. **Close** or Esc closes it.
15. **Agents** (`/agents`; wireframe §8.8)
    - Loads `GET /api/pages/agents` (`docs/data-model-and-api.md §6.4`) and polls it every 3 s,
      with the skeleton, the red alert for a failed first load, and the offline banner. The
      title reads `Agents · Claude Factories`. Not a wide page. `h1` `Agents`, then `h2`s
      **Running** and **Recent**.
    - Each running run is a card: its kind (`factory`; scheduled runs join later), `#12 <title>`
      linking to `/tasks/12`, the project linking to `/projects/{id}`, the stage (as the board
      draws it) and `round <n>` (the task's highest round), each left out when null. Then
      `started <relative time>`, `elapsed 5m 12s` (from its start to now, as the task page's
      agent durations read), a **Run log** link to `/tasks/12#run-log`, and **Stop**.
    - **Stop** sends `POST /api/runs/{id}/stop` with its spinner and no confirm, as on the task
      page. A 200 reloads the page at once, before the next poll. A refusal (`run #41 is not
      running`) is a red alert and the page stays; the next successful Stop clears it.
    - Under the card, its agents from the run's log: the orchestrator first, then each spawned
      agent in spawn order. Each shows its name, its type only when it differs from the name, and
      `round <n>` when its prompt names one. A running agent shows the outlined accent
      `● running` pill (the orchestrator always does); a finished one reads `finished · 12m 34s`,
      or `finished` when the log gives no duration. Then its latest tool line (`Bash pytest -q`),
      monospace, muted, one line, or nothing with none.
    - With nothing running, `Nothing running.` under Running.
    - **Recent** lists the last 20 ended runs, latest end first: `run #40`, `#11 <title>` linking
      to `/tasks/11`, the project link, how it ended as plain text (`failed: exit code 1`,
      `succeeded`, or `stopped`), its duration from start to end (`—` with no end), and
      `2 transcripts` (`1 transcript`) linking to `/tasks/11`, where the task page lists them,
      left out at 0. Ended runs carry no agents list. With none, `No runs yet.`

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
[Move]: a popover menu on every card: the other columns, then Up and Down in Backlog, then
  under a divider Edit and Delete (Delete disabled while the card runs). A move is announced
  in a hidden aria-live region; a refusal shows in the board's alert.
Delete dialog (modal; Esc or Cancel closes it):
  ┌ Delete #14 Export CSV? ────────────────────────────────────────────────┐
  │ This removes its runs, rounds and their files, verdicts, comments,     │
  │ decisions, status history, and transcript records from the app. Its    │
  │ worktree, branch, run logs, and copied transcript files stay on disk.  │
  │                                                   [Cancel] [Delete]    │
  └────────────────────────────────────────────────────────────────────────┘
  [Delete] filled danger with surface text; a refusal shows its detail above the buttons
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
┌──────────────────────────┐
│ Claude Factories         │
│ Workspace [personal▾] ⋯  │  ← ⋯: the workspace menu
│ + New workspace          │
│                          │
│ ▾ api-server           ⋯ │  ← ⋯: the project menu
│     Board                │  ← current page: aria-current, accent
│     Code                 │
│     Reviews          (2) │  ← waiting on me or escalated, when above 0: a warning pill
│     Context              │
│     Factories            │
│     Settings             │
│ ▸ web                  ⋯ │
│                          │
│ Dashboard                │
│ Agents               (1) │  ← running runs, when above 0: an accent pill
│ fctl reference           │
│ Claude: Pro ✓            │
└──────────────────────────┘
below md: [☰ Menu] opens the same sidebar as a drawer (<dialog>)
⋯: from md up, opacity 0 until its row is hovered or holds focus, or its menu is open; below md always shown

project ⋯                  workspace ⋯
┌───────────────────┐      ┌────────────┐
│ Rename            │      │ Rename     │
│ Settings          │      │ Settings   │
│ Move to workspace │      │ ────────── │  ← Move to workspace: a muted caption, one button per other workspace
│   work            │      │ Delete     │  ← text-danger
│ ───────────────── │      └────────────┘
│ Delete            │  ← text-danger
└───────────────────┘

Rename in place (Enter saves, Esc or blur cancels)
│ ▾ [api-server______]   ⋯ │  ← the name, focused and selected; the workspace's replaces its <select>
│   name must not be blank │  ← a refusal, beside the field, which stays

┌ Delete project api-server? ─────────────────────────────────────────────┐
│ This removes its tasks, with their runs, rounds and their files,        │
│ verdicts, comments, decisions, status history, and transcript records,  │
│ from the app. The repo, its worktrees and branches, run logs, and       │
│ copied transcript files stay on disk.                                   │
│ run #41 active                          ← a refusal, the dialog stays   │
│                                                     [Cancel] [Delete]   │
└─────────────────────────────────────────────────────────────────────────┘

┌ Delete workspace personal? ─────────────────────────────────────────────┐
│ This removes the workspace from the app. It must hold no projects:      │
│ move or delete them first.                                              │
│                                                     [Cancel] [Delete]   │
└─────────────────────────────────────────────────────────────────────────┘
[Delete]: filled danger, surface text · Cancel comes first and takes focus
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
Branch [main ▾]
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
Branch [main ▾]: a native <select>, the checked-out branch first (the working tree), then the other
  listed branches. Picking one sets ?branch= and opens its README landing; ?path= links keep ?branch=.
```

### 8.7 Factory designer
```
/projects/3/factories
api-server · personal                                   Factory: ready ✓   [+ New factory]
 Name        Nodes       Updated
 default     10 nodes    5m ago        [Rename] [Delete]
 nightly     12 nodes    yesterday     [Rename] [Delete]

/projects/3/factories/7  (wide)
personal › api-server › Factories › default
default                                                Unsaved changes   [Files] [Save]
┌ [« Palette] ────┬─ dotted background ───────────────────────────────┬─ Node ─────────────────┐
│ Agents          │ ┌─────────┐   ┌───────────────┐      ┌───────────┐ │ Name                   │
│  Spec writer    │ │ Start   ●──►● spec-writer   ●──×──►● builder   │ │ [builder_____________] │
│  Builder        │ └─────────┘   │ Spec writer · │      │ Builder · │ │ a-z, 0-9, and -        │
│  Reviewer       │               │ opus          │      │ both ·    │ │ Description [________] │
│  Approver       │               └───────────────┘      │ opus      │ │ Model [opus ▾]         │
│  Custom agent   │                                      └───────────┘ │ Side [both ▾]          │
│ Conditions      │ ┌───────────────────┐ yes ●────► approver          │ Tools [Read, Edit, …]  │
│  All reviews    │ │ All reviews PASS? │                              │ Prompt                 │
│   PASS          │ │ Condition         │ no  ●────► Rounds used < 2?  │ [Input: a task id …  ] │
│  Any review     │ └───────────────────┘                              │                        │
│   CHANGES       │                                                    │                        │
│  Rounds used    │ [+] [−] [fit] [lock]                               │                        │
│   < N           │                                                    │                        │
│  Decision       │                                                    │                        │
│   APPROVE       │                                                    │                        │
└─────────────────┴────────────────────────────────────────────────────┴────────────────────────┘
palette: « collapses it to a rail with »; an item drags onto the canvas, or a click (Enter, Space) adds it at the center
cards: an icon (not drawn), the title, and a one-line summary; ● handles: yes in success, no in danger, each with its word
×: at an edge's midpoint, deletes that edge · [+] [−] [fit] [lock]: React Flow's stock controls
Node: the selected node's data; with none selected, "Select a node to edit it."
[Save]: enabled while unsaved; Ctrl/⌘+S does the same; leaving the page warns while unsaved
below md: the palette starts collapsed and the Node panel goes under the canvas

[Files] → a modal dialog
┌ Files ─────────────────────────────────────────────────────────────────────────── [Close] ┐
│ Showing the last saved design. Save to include your changes.        (only while unsaved)  │
│ ┌──────────────────────────────────┬──────────────────────────────────────────────────┐ │
│ │▌.claude/skills/factory/SKILL.md  │ ---                                              │ │
│ │ .claude/agents/spec-writer.md    │ name: factory                                    │ │
│ │ .claude/agents/builder.md        │ description: Factory orchestrator. …             │ │
│ │ …                                │ ---  (highlight.js, markdown)                    │ │
│ └──────────────────────────────────┴──────────────────────────────────────────────────┘ │
│ [Download .zip]   [ ] Overwrite existing files   [Write to repo]                          │
│ Wrote 8 files: …   Skipped 0 existing files …   git add .claude/skills/factory …          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
list: beside the preview from md up, above it below md; ▌ = the selected path (aria-current)
a refused GET: a red alert instead of the list, link, and Write; a refused write: a red alert, the list stays
```

### 8.8 Agents
```
Agents
Running
┌───────────────────────────────────────────────────────────────────────────────────┐
│ factory  #12 Rate-limit login endpoint   api-server   agent_review · round 1      │
│ started 5m ago · elapsed 5m 12s                                Run log   [Stop]   │
│   orchestrator                        (● running)          Agent review-code      │
│   builder-12   builder     round 1    finished · 12m 34s   Bash pytest -q         │
│   review-code              round 2    (● running)          Bash fctl verdict 12 … │
└───────────────────────────────────────────────────────────────────────────────────┘
Recent
 run #40   #11 Webhooks    api-server   failed: exit code 1   12m 3s   2 transcripts
 run #39   #9 Health       web          succeeded             8m 41s   5 transcripts
 run #38   #10 Audit log   api-server   stopped               1m 2s
nothing running: "Nothing running." under Running, then Recent · no ended runs: "No runs yet."
agents: the orchestrator first, then each spawned agent in spawn order; the type only when it differs from the name
(● running): the outlined accent pill; "finished · <duration>", or "finished" when the log gives no duration
the latest tool line: monospace, muted, one line
Run log → /tasks/12#run-log · N transcripts → /tasks/11, left out at 0 · [Stop] with its spinner; a refusal is a red alert
```

### 8.9 Context
```
/projects/3/context
api-server · personal                                                       Factory: ready ✓
[+ New card] [+ New group]   Upload files [Choose files]   Path [/Users/me/notes______] [Add from path]
An absolute path to a .md, .markdown, or .txt file, or a folder of them, on the backend's machine. …
┌ Stack and conventions ────── Pinned ┐ ┌ API conventions ──────────── ⋯ ┐ ┌ Runbooks ─────────────────── ⋯ ┐
│ Agents read it at the top of fctl   │ │ Every endpoint returns JSON,   │ │ Deploys and rollbacks, step by │
│ show.                               │ │ errors included.               │ │ step.                          │
│                                     │ │                                │ │ 2 cards                        │
└─────────────────────────────────────┘ └────────────────────────────────┘ └────────────────────────────────┘
┌ api-server ────────────────────── ⋯ ┐
│ A small FastAPI service: login, …   │
│ /Users/me/demo/api-server/README.md │
└─────────────────────────────────────┘
grid: the pinned card first, then the top-level cards and groups by position; a title is a button
  that opens the card dialog (a group's, the group modal) · the path under a card read from one: mono, muted
Upload files: a file input, multiple, accept=".md,.markdown,.txt" · [Add from path]: disabled while Path is blank
a refusal: a red alert under the project header, "<file name>: <detail>" for an upload

⋯ → a native popover menu
┌───────────────────┐
│ Edit              │
│ Reload from path  │  cards read from a path only
│ Move to group     │  a muted caption, left out with no group to move to
│   Runbooks        │  one button per group the card isn't in
│ Move out of group │  a card in a group only
├───────────────────┤
│ Delete            │  danger; opens DeleteDialog (§8.4)
└───────────────────┘
a group's ⋯: Edit and Delete only

Runbooks → the group modal, a <dialog>
┌ Runbooks ─────────────────────────────────────────────────────────────────── [Close] ┐
│ Deploys and rollbacks, step by step.                                                 │
│ [+ New card]   Upload files [Choose files]   Path [__________________] [Add from path] │
│ ┌ Deploy ───────────────────── ⋯ ┐ ┌ Roll back ────────────────── ⋯ ┐                  │
│ │ Tag main, wait for CI, then    │ │ Redeploy the previous tag.     │                  │
│ │ roll the tag out.              │ │                                │                  │
│ └────────────────────────────────┘ └────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────────────────┘
no + New group here: groups are one level deep · each add sends the group's id · Esc or Close closes it

API conventions → the card dialog, a <dialog>
┌ Edit API conventions ─────────────────────────────────────────────────────── [Close] ┐
│ Title [API conventions__________________________]                                     │
│ Description [Every endpoint returns JSON, errors included.]                           │
│ Content                                      │ Preview                                │
│ [# API conventions                         ] │ API conventions                        │
│ [                                          ] │ Every endpoint returns JSON, errors    │
│ [Every endpoint returns JSON, errors …     ] │ included.                              │
│ 212 / 16384 bytes                  [Save]    │                                        │
└──────────────────────────────────────────────────────────────────────────────────────┘
+ New card: "New card", empty, no Preview yet · + New group: "New group", Title and Description only
the pinned card: "Stack and conventions" with 033's editor · over 16384 bytes: "over the limit" in danger, Save disabled
a refusal (413 card over 16 KB): inside the dialog, which stays open with what was typed
```
