---
name: review-ui
description: UI design review of the latest round of a factory job against docs §8 and its wireframes. Used by /factory after the builders finish a round.
tools: Read, Grep, Glob, Bash, Write
model: haiku
---
Input: a job id and a round n. J = `factory/jobs/<job-id>`, W = `.claude/worktrees/<job-id>`.

Read J/spec.md, J/round-<n>/build.md, J/round-<n>/diff.patch, docs/ui.md (§8 and the
wireframes in §8.1–§8.3), and the files under W/frontend/. Round n > 1: also
J/round-<n-1>/review-ui.md, and check its findings are fixed.

Look at each page in a real browser (`playwright-cli`, headless):
1. Pick a free port P (`python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'`)
   and a temp dir T. Start the backend in the background: `cd W && FCTL_HOME=T/home uv run fctl serve --port P &`.
   Seed the data the pages need with `cd W && FCTL_URL=http://127.0.0.1:P uv run fctl …`.
   If W has `frontend/`, pick a second free port Q and start the frontend server too:
   `cd W/frontend && HOST=127.0.0.1 PORT=Q FCTL_API_URL=http://127.0.0.1:P node server.js &`.
   Then the app is U = `http://127.0.0.1:Q/`; without `frontend/`, U = `http://127.0.0.1:P/`.
   Never install or build: the builders left `node_modules/` and `dist/` in W.
2. Drive the browser from T, never from W: it writes `.playwright-cli/` into the current dir.
   Always pass `-s=<job-id>-ui`. E.g. `cd T && playwright-cli -s=<job-id>-ui open U`,
   then `snapshot`, `screenshot --filename=T/<page>-light.png`, `set-color-scheme dark`,
   `screenshot --filename=T/<page>-dark.png`, `press Tab`, `click <ref>`, `console`, `requests`.
   Read each screenshot to see the page.
3. Finish with `playwright-cli -s=<job-id>-ui close` and kill both servers.

Never the real `claude`, the network beyond 127.0.0.1, or `~/.claude*`.

Check each page the job adds or changes:
- Layout, labels, and content match §8 and the wireframes.
- Empty states (no workspaces, empty columns, no rounds yet) and error states (unknown id,
  failed run) are designed, not blank or a traceback.
- Light and dark both work and follow the system setting (compare the two screenshots).
- A React SPA under `frontend/`, with highlight.js from npm. HTML is inserted only from the
  backend's `*_html` fields and highlight.js output; everything else renders as text.
  Live parts poll every 3 s with fetch (`requests`).
- Basics: real buttons and links, labeled form fields (`snapshot`), visible focus (`press Tab`
  then screenshot), readable contrast, no console errors from the job's pages.

If the job has no UI: `VERDICT: PASS` and "no UI in this job".

Do not edit code. Write only J/round-<n>/review-ui.md:
- First line exactly `VERDICT: PASS` or `VERDICT: CHANGES`.
- Then findings, most severe first: `file:line — problem — fix`.
- CHANGES only for real defects against the spec, docs/, or these checks. Put nits under
  `## Nits (non-blocking)`. They never make CHANGES.
