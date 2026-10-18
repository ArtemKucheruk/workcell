VERDICT: PASS

Checked in headless Chromium against a running server (`fctl serve`) with a seeded fixture repo, project 1 (tracked README.md with raw `<script>`, src/app.py, docs/guide.md, .gitignore, latin.txt, notes.txt) plus an empty repo (project 2) and a non-repo path (project 3):

- Landing (`/projects/1/code`): tree on the left, README rendered as markdown with the `<script>` shown as escaped text, branch `main` in the header, `docs/` and `src/` collapsed. Matches §8 item 6. Light and dark both follow the system setting (`set-color-scheme`).
- File view (`?path=src/app.py`): highlighted Python, `<b>&</b>` escaped, gutter 1/2/3, `aria-current` on the shown file, `src/` open and `docs/` closed. Light and dark both correct, no console messages.
- Empty repo: `No tracked files.` in the muted style, no tree, header still shows the branch.
- Non-repo path: `role="alert"` message naming the path and git's first stderr line, no tree.
- `?path=../secret.txt`: 404 HTML error page, no content.
- Unknown project `/projects/999/code`: 404 page `Project #999 not found`.
- Keyboard: Tab moves focus to a tree link with a visible focus ring, in light mode.
- Only system colors are used (Canvas, GrayText, existing hljs theme CSS); no new hard-coded colors. No frontend build; highlight.js and the existing static assets are vendored under `static/`. The code page has no live parts, so no 3 s polling is required.

## Nits (non-blocking)
- src/claude_factories/templates/base.html — the first load of a page has a `favicon.ico` 404 console error because base.html has no icon link. This is shared by every page and pre-existing, not from this job; the code page itself logs no errors on later navigations. Fix (optional): add an inline `<link rel="icon" href="data:,">` in base.html.
