# 016-code-page: Project code page: file tree, README landing, file viewer

## Goal
Add the read-only project code page `/projects/{id}/code`. It lists the main checkout's
tracked files from `git ls-files` as a tree on the left. With no `path` it renders the
root `README.md` as markdown with raw HTML off. With `?path=` it shows that file escaped,
highlighted, with line numbers, or "not shown" when the file is binary or over 1 MB. The
header shows the checkout's current branch. Only tracked files that resolve inside the
project root can ever be read (§4.5).

## Implements
- `docs/ui.md §8 item 6`: the tree from `git ls-files` of the main checkout, the README.md landing, the highlighted viewer with line numbers, "not shown" for binary files and files over 1 MB, and the current branch in the header.
- `docs/data-model-and-api.md §6.4`: the HTML route `/projects/{id}/code?path=`.
- `docs/MVP.md §4.5`: README markdown rendered with raw HTML off, the code viewer escaping everything, and paths resolved inside the project root only (no `..`, no symlinks pointing outside).
- `docs/MVP.md §4.1` (App → git): the page lists files and reads the branch by running `git` as a subprocess with argument lists, never shell strings.
- `docs/MVP.md §9`: "project code page with README landing" is MVP. Branch and worktree browsing is Later.

## Acceptance criteria
Fixture: a project connected (`POST /api/projects/connect`) at the `repo` fixture with tracked `README.md`, `src/app.py`, and `docs/guide.md` committed, plus an untracked `notes.txt` and a gitignored `.env` on disk.

- [ ] AC1: `GET /projects/{id}/code` → 200. The tree has one link `/projects/{id}/code?path=<file>` for each `git ls-files` entry (`README.md`, `src/app.py`, `docs/guide.md`, `.gitignore`), and none for `notes.txt` or `.env`.
- [ ] AC2: the landing (no `path`, and also `path=`) renders `README.md` containing `# Hello` as `<h1>Hello</h1>`.
- [ ] AC3: a `README.md` line `<script>alert(1)</script>` on the landing appears escaped (`&lt;script&gt;`), and the body has no `<script>alert(1)` (raw HTML off).
- [ ] AC4: a repo with tracked files but no `README.md` → 200, the tree is shown, and the main column says `No README.md in this project.` (Q6).
- [ ] AC5: a repo with no tracked files (the bare `repo` fixture) → 200 with `No tracked files.` and no tree links (Q8).
- [ ] AC6: `?path=src/app.py` with 3 lines → 200. Each line's text is shown, and the gutter shows line numbers 1, 2, 3 and no 4 (Q9).
- [ ] AC7: `?path=src/app.py` containing `x = "<b>&</b>"` → the body has `&lt;b&gt;&amp;&lt;/b&gt;` and no raw `<b>&</b>`.
- [ ] AC8: the code block of `src/app.py` carries the language `py` (from the lowercase extension). A tracked `Makefile` carries no language (Q9).
- [ ] AC9: a tracked file with a NUL byte in its first 8000 bytes → 200 with `Binary file not shown.`, and none of its text in the body (Q4).
- [ ] AC10: a tracked text file of 1048577 bytes → 200 with `File over 1 MB not shown.`, and its content isn't in the body. A file of exactly 1048576 bytes is shown (Q5).
- [ ] AC11: a tracked file with non-UTF-8 bytes (for example latin-1 `caf\xe9`) and no NUL → 200, shown with U+FFFD in place of the bad bytes, not a 500 (Q4).
- [ ] AC12: the header shows the project name linking to `/projects/{id}` and the current branch: `main` on the fixture, and `feature-x` after `git checkout -b feature-x`. With a detached HEAD it shows `detached HEAD` (Q7).
- [ ] AC13: `?path=../secret.txt`, where `secret.txt` sits next to the repo with known content → 404 HTML error page, and the content isn't in the body (Q2).
- [ ] AC14: `?path=<absolute path of secret.txt>`, `?path=notes.txt` (untracked), `?path=.env` (ignored), `?path=.git/config`, and `?path=src` (a directory) → 404 each (Q2).
- [ ] AC15: a tracked symlink `leak` → `<tmp>/secret.txt` (outside the repo) is listed in the tree. `?path=leak` → 200 with `Not shown: points outside the project.`, and the secret content isn't in the body (Q3).
- [ ] AC16: a tracked `README.md` that is a symlink to `<tmp>/secret.txt` → the landing doesn't render the secret content and says `Not shown: points outside the project.` (Q3, Q6).
- [ ] AC17: a tracked symlink `alias.py` → `src/app.py` (inside the repo) → `?path=alias.py` shows `src/app.py`'s content (Q3).
- [ ] AC18: a tracked file named `a b#c&d.txt` → following its tree link's `href` returns 200 showing that file's content.
- [ ] AC19: `?path=src/app.py` → the `src/` directory's `<details>` is `open`, `docs/`'s is not, and the `app.py` link has `aria-current="page"` (Q8).
- [ ] AC20: `GET /projects/999/code` → 404 HTML error page.
- [ ] AC21: a project whose path doesn't exist or isn't a git repo → 200 page with a `role="alert"` message that names the path, and no tree (Q10).

## Files
- `src/claude_factories/app.py`: a new `# --- Code page (docs/ui.md §8 item 6) ---` section with `GET /projects/{project_id}/code` and its helpers. Put it right after `create_factory_form`, before the review code, so it doesn't touch the lines 009-review-actions (running alongside) edits. Reuse `one_or_404`, `file_tree()` (pass `[{"path": p} …]`), `safe_path()` if useful, the `markdown` filter, and `factory_state`'s subprocess pattern (argument list, `timeout`, catch `OSError`/`ValueError`/`TimeoutExpired`).
- `src/claude_factories/templates/code.html`: new. It extends `base.html` and reuses `.files-layout` and `#file-tree`.
- `src/claude_factories/templates/base.html`: only if new CSS is needed (for example the gutter). Put it under a `/* Code page (docs/ui.md §8 item 6) */` comment and use no new hard-coded colors.
- `tests/test_code.py`: new. Use the `repo`, `client`, `git`, `write`, and `commit` helpers from `conftest.py`.

No new dependencies. The board's **Code** link (`project.html`) already points here and stays unchanged.

## Out of scope
- `Claude: Pro ✓` / `API key — runs disabled` in the header (014-run-ui).
- Branch and worktree browsing (docs/MVP.md §9 Later). The page shows only the main checkout.
- Directory pages, raw or download views, line anchors and permalinks, search, blame, and history.
- Rendering `.md` files as markdown when clicked. §8 item 6 says a clicked file opens the highlighted view, and only the landing renders README.md.
- Rewriting relative links and images inside the README.
- Any JSON API for files or the tree (§6 defines none). Editing code (docs/MVP.md §1 non-goals).
- Caching `git ls-files` between requests.
- The dashboard (017), task page (010), and review actions (009).

## Open questions
- Q1: Where does file content come from? §4.1 says the app shells out to "show files", while §4.5's symlink rule only matters for files read from disk. Default: read the file from disk in the main checkout (the working tree, so uncommitted edits show as on disk) at its resolved real path, not `git show HEAD:path`. This matches "`git ls-files` of the main checkout" and the §4.5 containment rule.
- Q2: Which `path` values can be viewed, and what's the response otherwise? Default: only exact entries of `git -C <root> ls-files -z`. Check membership first, before any filesystem call, so `..`, absolute, NUL, untracked, ignored, `.git/`, and directory paths never reach the disk. Each gets 404 through the existing HTML error page (`<path> is not a tracked file in <project>`). Then `os.path.realpath(root/path)` must be inside `os.path.realpath(root)`, as `create_factory` checks.
- Q3: What does a tracked path show if it resolves outside the root, or to something that isn't a regular file (a directory, a submodule, a file deleted from disk but still in the index)? Default: 200 with the tree and `Not shown: points outside the project.` or `Not shown: not a regular file.`, without reading anything. Symlinks that resolve to a regular file inside the root are followed.
- Q4: What counts as binary, and how is text decoded? Default: binary means a NUL byte in the first 8000 bytes (git's own heuristic). Text, and the `ls-files` names, are decoded as UTF-8 with `errors="replace"`. A name that doesn't decode is listed with U+FFFD, and its link gets a 404.
- Q5: Is 1 MB 10^6 bytes or 2^20? Default: `1024 * 1024`, like `MAX_PATCH`'s "5 MB". Size comes from `os.stat` before reading, and over means `> 1048576`. The same rule applies to README.md on the landing.
- Q6: Which README is the landing? Default: exactly a tracked `README.md` at the root, as §8 item 6 names it, under the Q2, Q3, Q4, and Q5 rules. Otherwise show `No README.md in this project.`
- Q7: What does "current branch" show on a detached HEAD? Default: `git -C <root> branch --show-current`, and `detached HEAD` when that prints nothing. On a repo with no commits it prints the unborn branch name, which is fine.
- Q8: What are the tree's shape, order, and empty state? Default: `file_tree()` in `ls-files` order. Each directory is a `<details>` that is `open` only if it holds the shown file, so a big repo lands collapsed to its top level. The shown file's link gets `aria-current="page"`. No tracked files: `No tracked files.`
- Q9: What are the viewer's markup and highlighting? Default: a line-number gutter beside one `<pre><code>` that holds the whole file, so highlight.js colors multi-line strings and comments correctly. The language is the lowercase extension, used only if `hljs.getLanguage` knows it, with no auto-detection (same rule as 008 Q7). A line ends at `\n`, `\r\n`, or a lone `\r` (HTML parsing breaks lines on all three), and a final line ending adds no extra line. An empty file shows `Empty file.`
- Q10: What if git fails (the path is missing, isn't a repo, or git hangs)? Default: 200 page with `role="alert"` `Can't list files in <path>: <first line of git's stderr>` (or `git timed out`), and no tree. This is a page, not a JSON 409, because the 404 handler is the only one that renders HTML.
