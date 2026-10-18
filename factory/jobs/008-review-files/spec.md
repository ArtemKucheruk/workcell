# 008-review-files: Review page (Files changed tab, diff, inline comments)

## Goal
Add the Files changed tab to the review page `/tasks/{id}/review?tab=files` (docs/ui.md §8.3). It shows a file tree with +/− per file and the selected round's diff, rendered on the server as one table per file with one row per line. Each line number is an anchor `path:side:line` that opens an inline comment form, and highlight.js colors the code. Inline comments from reviewer agents and from me show up under the line they're on.

## Implements
- `docs/ui.md §8 item 5`: the diff is rendered on the server as a table with one row per line and the anchor `path:side:line`, and highlight.js colors it. Clicking a line number opens an inline comment form. The round selector picks the round whose diff is shown.
- `docs/ui.md §8.3`: the Files changed wireframe. A `Conversation | Files changed N` tab bar, a left file tree (`app/` → `limits.py +42`), a file header (`app/limits.py  (new)  +42 −0`), hunk header rows (`@@ -41,7 +41,9 @@ def login():`), old and new line-number columns, and an inline comment box under the line.
- `docs/MVP.md §3.5`: Files changed shows the file tree with +/− per file and a unified diff. Clicking a line number adds an inline comment, and reviewer agents' inline comments show up in the same place.
- `docs/MVP.md §10 assumption 12`: reviewer agents' inline comments render like mine.
- `docs/data-model-and-api.md §5.1`: reads `round_files` (`path`, `old_path`, `change`, `binary`, `additions`, `deletions`, `patch`) in rowid order, and `comments` with `path`, `line`, and `side`.
- `docs/data-model-and-api.md §6.3`: an inline comment is a comment with `round`, `author`, `path`, `line`, and `side`, written through 006's `post_comment()`.
- `docs/data-model-and-api.md §6.4`: the route `/tasks/{id}/review?round=&tab=files`.
- `docs/MVP.md §4.2, §4.5`: the vendored highlight.js colors code, and every code line is escaped. Comment bodies go through the existing `markdown` filter (raw HTML off). The comment form posts with htmx, so it carries `X-Requested-By: fctl`.

## Acceptance criteria

Unless a criterion says otherwise, "the sample round" is round 1 of a factory task (`worktree_path` and `branch` set), submitted through `POST /api/tasks/{id}/rounds` with `base_sha` `abc1234` and this patch (`␣` is a space, and every line ends in `\n`):
```
diff --git a/app/auth.py b/app/auth.py
index 1111111..2222222 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -41,3 +41,3 @@ def login():
␣    user = authenticate(form)
-    if not user:
+    if not user and limiter.hit(client_key(request)):
␣        return deny()
@@ -60,2 +60,3 @@ def logout():
␣    session.clear()
+    audit("logout")
␣    return ok()
diff --git a/app/limits.py b/app/limits.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/app/limits.py
@@ -0,0 +1,2 @@
+def client_key(request):
+    return request.client.host
\ No newline at end of file
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..4444444
Binary files /dev/null and b/logo.png differ
diff --git a/old_name b/new_name
similarity index 100%
rename from old_name
rename to new_name
diff --git a/tests/test_limits.py b/tests/test_limits.py
deleted file mode 100644
index 5555555..0000000
--- a/tests/test_limits.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def test_old():
-    assert True
```
"The files tab" means `GET /tasks/<id>/review?tab=files`. URLs in criteria are compared after parsing with `urllib.parse`, so parameter order and percent-encoding don't matter.

Tabs (Q4)
- [ ] AC1: a task with the sample round → after the header, a `<nav class="tabs">` with exactly two links, `Conversation` → `/tasks/<id>/review?round=1` and `Files changed 5` → `/tasks/<id>/review?round=1&tab=files`. Without `tab`, only `Conversation` has `aria-current="page"`. With `tab=files`, only `Files changed 5` has it.
- [ ] AC2: the files tab → 200 with no `description`, `rounds`, `approver`, or `timeline` section and no `<textarea`. No `tab`, and `tab=conversation` or `tab=xyz`, → the Conversation page, with no `id="file-tree"` and no `diff-table`. 007's tests keep passing unchanged.
- [ ] AC3: on the files tab, the header's round `<form method="get">` holds `<input type="hidden" name="tab" value="files">`. On Conversation it holds no `tab` input.
- [ ] AC4: a task with no rounds → `tab=files` is 200, the tabs read `Conversation` and `Files changed 0` with links that have no `round` parameter, and the tab body reads `No rounds yet.`
- [ ] AC5: rounds 1 (the sample round) and 2 (one file, `b.py`) → `?tab=files` shows only `b.py`, and `?round=1&tab=files` shows the sample round's five files. `?round=99&tab=files` → the 404 page.

File tree (Q6)
- [ ] AC6: the files tab has a `<nav id="file-tree">` built from nested `<ul>`s. Its entries read, in order: `app/`, `auth.py +2 −1`, `limits.py +2 −0`, `logo.png +0 −0`, `new_name +0 −0`, `tests/`, `test_limits.py +0 −2`. `auth.py` and `limits.py` are inside the `<li>` of `app/`, and `test_limits.py` is inside the `<li>` of `tests/`. The minus is U+2212.
- [ ] AC7: each file entry is a link to `#file:<path>`, for example `#file:app/auth.py`, and the page has exactly one element with `id="file:<path>"` for each of the five files, in patch order.

File sections (Q5)
- [ ] AC8: the text of each file's header, tags stripped and whitespace collapsed, reads: `app/auth.py +2 −1`, `app/limits.py (new) +2 −0`, `logo.png (new) +0 −0`, `new_name (renamed from old_name) +0 −0`, and `tests/test_limits.py (deleted) +0 −2`.
- [ ] AC9: each file has one `<table class="diff-table">`. A line row has four cells: old number, new number, sign, and code. Its code cell keeps the line's leading whitespace and drops the sign. A `hunk` row is one cell with `colspan="4"`. The `diff --git`, `index`, `---`, and `+++` lines are not rows. For `app/auth.py`, the rows are, in order (row class | old | new | sign | code text; `·` is an empty cell):
  ```
  hunk | @@ -41,3 +41,3 @@ def login():
  ctx  | 41 | 41 | · | "    user = authenticate(form)"
  del  | 42 | ·  | - | "    if not user:"
  add  | ·  | 42 | + | "    if not user and limiter.hit(client_key(request)):"
  ctx  | 43 | 43 | · | "        return deny()"
  hunk | @@ -60,2 +60,3 @@ def logout():
  ctx  | 60 | 60 | · | "    session.clear()"
  add  | ·  | 61 | + | "    audit(\"logout\")"
  ctx  | 61 | 62 | · | "    return ok()"
  ```
- [ ] AC10: `app/limits.py`'s rows are `hunk`, `add` with new number 1, `add` with new number 2, then a `note` row with the text `\ No newline at end of file`, which has no line numbers and no anchor.
- [ ] AC11: `logo.png`'s table has one `note` row, `Binary file not shown.`, and `new_name`'s has one `note` row, `No content changes.` Neither has a line row.
- [ ] AC12: a round whose file `win.txt` has the patch line `+new\r` (a CRLF file) → that row's code cell text is exactly `new`, with no `\r` in the cell.
- [ ] AC13: a round adding `x.html` with the line `+<script>alert(1)</script>` → its code cell holds `&lt;script&gt;alert(1)&lt;/script&gt;`, and the page has no `<script>alert`. A round adding a file named `<b>.txt` (the `diff --git a/<b>.txt b/<b>.txt` header, `new file mode`, `+++ b/<b>.txt`) → the page has no raw `<b>` tag, and the tree entry, the file header, and the `id="file:…"` attribute are all escaped.

Anchors and the comment link (Q1, Q8)
- [ ] AC14: every old or new line number is an `<a>` whose `id` is `<path>:<side>:<n>`. In `app/auth.py`: the `ctx` 41/41 row carries `app/auth.py:old:41` and `app/auth.py:new:41`, the `del` row only `app/auth.py:old:42`, and the `add` row only `app/auth.py:new:42`. `hunk` and `note` rows carry no id.
- [ ] AC15: the href of the `app/auth.py:old:42` link has the path `/tasks/<id>/review`, the query `round=1`, `tab=files`, `path=app/auth.py`, `side=old`, `line=42`, and a fragment that unquotes to `app/auth.py:old:42`.

Highlighting (Q7)
- [ ] AC16: `app/auth.py`'s table has `data-lang="py"`, and `new_name`'s table has no `data-lang`. With `tab=files`, the page has an inline `<script>` that calls `hljs.getLanguage` and `hljs.highlight` and contains neither `highlightAuto` nor `highlightAll`. The Conversation tab has no such script.

Inline comment form (Q1, Q3)
- [ ] AC17: `?round=1&tab=files&path=app/auth.py&side=new&line=42` → exactly one inline `<form hx-post="/tasks/<id>/comments">`, in the `<tr>` right after the row holding `id="app/auth.py:new:42"` (after that line's comments row, if it has one). It holds hidden inputs `round=1`, `path=app/auth.py`, `side=new`, and `line=42`, a `<textarea name="body_md">` with `required` and `autofocus`, a `Comment` button, and a `Cancel` link to `/tasks/<id>/review?round=1&tab=files` with a fragment that unquotes to `app/auth.py:new:42`.
- [ ] AC18: a target that matches no line number in the shown round → 200 and no inline form. That covers `line=99`, `line=x`, `line=042`, `side=both`, `path=nope.py`, and a `path` without `side` or `line`.
- [ ] AC19: `POST /tasks/<id>/comments` with form fields `body_md=Use a bucket`, `round=1`, `path=app/auth.py`, `side=new`, `line=42`, and `X-Requested-By: fctl` → 204 with an `HX-Redirect` whose path is `/tasks/<id>/review`, whose query is `round=1` and `tab=files` only, and whose fragment unquotes to `app/auth.py:new:42`. One `comments` row: author `me`, round 1's `round_id`, path `app/auth.py`, line 42, side `new`, body `Use a bucket`. No `events` row is written, and the task row is unchanged.
- [ ] AC20: with rounds 1 (the sample round) and 2 on the task, an inline post with `round=1` → the row's `round_id` is round 1's, not the latest.
- [ ] AC21: inline posts with `line=abc`, `line=0`, `side=both`, `round=x`, `path` without `line`, `line` without `path`, `path=nope.py`, or a blank `body_md` → 422, and no row is written. `round=9` → 404. No `X-Requested-By` → 403. None of these is a 500.
- [ ] AC22: the 007 conversation box's post (only `body_md`) still writes a conversation comment on the latest round and redirects to `/tasks/<id>/review` (007's AC28 passes unchanged).

Comments in place (Q2)
- [ ] AC23: on the sample round, comments by SQL in this id order: security on `app/auth.py` new 42 `Trusts **XFF**`; me on `app/auth.py` new 42 `Agreed`; ux on `app/auth.py` old 42 `Old line`; code on `app/limits.py` new 99 `Off the diff`; me with no path `General`. On round 2, me on `b.py` new 1 `Later`. Then the files tab with `?round=1`:
  - the `<tr>` right after the row with `id="app/auth.py:new:42"` has class `comments` and holds security's comment, then mine, each with the author in `<strong>` and the body rendered (`<strong>XFF</strong>`);
  - the `<tr>` right after the `app/auth.py:old:42` row holds only ux's comment;
  - the last `<tr>` of `app/limits.py`'s table has class `comments` and holds code's comment, led by `code on line 99 (new)`;
  - `General` and `Later` appear nowhere on the tab.
- [ ] AC24: an inline comment whose body is `<img src=x onerror=alert(1)>` → `&lt;img` in its comments row, and no `<img` on the page.
- [ ] AC25: after AC19's post, the files tab for round 1 shows `Use a bucket` in the comments row after `app/auth.py:new:42`.

## Files
- `src/claude_factories/app.py`:
  - A function that turns one `round_files.patch` into display rows: `hunk`, `ctx`, `add`, `del`, and `note`, with old and new line numbers and the line text without its sign or a trailing `\r` (Q5).
  - `review_page` takes `tab`, `path`, `side`, and `line` query parameters, all strings. On `tab=files` it reads the selected round's files in rowid order and that round's inline comments, and builds the tree (Q6). It reuses `round_or_404`, `query`, and `round_summaries`.
  - `add_comment_form` also reads optional `round`, `path`, `side`, and `line` form fields (blank means absent) and passes them to `CommentBody` and `post_comment()`, with author `me`. A pydantic `ValidationError` from building `CommentBody` becomes a 422, not a 500. An inline comment redirects to the files tab anchor. A conversation comment keeps 007's redirect (Q3, Q11).
- `src/claude_factories/templates/review.html`: the tab bar, the hidden `tab` input in the round form, the Files changed body (tree, file sections, comments rows, inline form row, empty states), and the highlight script. The Conversation sections render only on the Conversation tab.
- `src/claude_factories/templates/base.html`: diff rules in the existing `<style>`: a tree column beside the diffs, a monospace table with `white-space: pre`, muted line numbers, horizontal scroll per file, hunk and note rows, comment rows, and a transparent background on `code.hljs` so the theme's background doesn't cover the row colors (Q9).
- `tests/test_review_files.py`: new, with every criterion above. It imports `test_review.py`'s helpers (`project`, `add_task`, `page`, and the rest) and posts patches through `POST /api/tasks/{id}/rounds`.

No schema change, no new route under `/api`, no change to any API response shape, no new static file, and no new dependency.

## Out of scope
- Approve and Request changes buttons, the summary box, my APPROVE / CHANGES_REQUESTED, and the commit commands (009).
- The task page (010) and the project code page's file viewer (016).
- Replies, threads, resolving, editing, or deleting comments; suggestion blocks; split view; interdiff (Later, §9). The wireframe's `[Reply]` button isn't built.
- Showing a round's comments on another round's diff ("outdated" comments) (Q2).
- Collapsing large files or truncating big diffs (Q10). Expanding context lines beyond the hunks.
- Linking timeline items to file anchors, polling on this page (007 Q10), and any CLI change.

## Open questions
- Q1: §8 says clicking a line number "opens an inline comment form" but not how. Default: no extra route and no custom JS. Each line number is a plain link to `/tasks/{id}/review?round=<n>&tab=files&path=<path>&side=<side>&line=<n>#<path>:<side>:<n>`, with query values and the fragment URL-encoded. The page renders the form in a row under the line whose anchor matches `path`, `side`, and `line` exactly as strings. Anything else renders no form, with no error. The form posts with `hx-post` to the existing `POST /tasks/{id}/comments`, since a plain form can't send `X-Requested-By`. The redirect URL drops the `path`/`side`/`line` parameters, so it's a real navigation that closes the form, and the fragment scrolls back to the line. Cancel is a link to the same URL.
- Q2: the wireframe shows `security (round 1): …` and `me: …` under a line, but docs don't say which rounds' comments show on a diff. Line numbers belong to one round's diff. Default: only the shown round's inline comments, matched by `side` and `line` to a row's old or new number (a context row matches either side). Each matched line gets one `comments` row after it, with its comments by id: the author in `<strong>`, then the body through the `markdown` filter. No round label, since every comment shown is on this round. An inline comment whose line isn't in the diff (006 doesn't check lines against hunks) goes in a final `comments` row of its file's table, led by `<author> on line <n> (<side>)`. Conversation comments, and comments on other rounds, show only in the Conversation timeline.
- Q3: docs don't say which round an inline comment attaches to. Default: the round being viewed, sent as a hidden `round` field, because its line numbers are that round's. The conversation box keeps 007's latest round. Author is always `me`.
- Q4: the wireframe has `─ Conversation ─┬─ Files changed 4 ─` but no markup or values for `tab`. Default: `tab=files` shows Files changed, and any other value or none shows Conversation. The tab bar is a `<nav class="tabs">` of two links placed after the header, replacing 007's `<h2>Conversation</h2>`. The current tab has `aria-current="page"`. Both links carry `round=<the shown round's n>`, or no `round` when the task has no rounds. The count is the shown round's file count, 0 without rounds. On Files changed, the round selector keeps `tab=files` through a hidden input.
- Q5: docs give the wireframe rows but no rules for other parts of a patch. Default:
  - The file header is the path, then `(new)` for added, `(deleted)` for deleted, or `(renamed from <old_path>)` for renamed, then `+A −D` from `round_files`. Modified files get no label.
  - Lines before a section's first `@@`, and after any later `diff --git` line until its next `@@`, are header lines and get no row. This covers 005's merged typechange sections.
  - `@@ -a[,b] +c[,d] @@ …` sets the next old and new numbers to `a` and `c` and is a `hunk` row with the whole line as text.
  - Inside a hunk: `+` is add (new number), `-` is del (old number), and `\` is a `note` row with no numbers that doesn't advance them. Any other line, including an empty one, is context (both numbers).
  - One trailing `\r` is dropped from every displayed line. The patch is split on `\n` only, and the empty string after the final `\n` is not a row.
  - A binary file shows one `note` row, `Binary file not shown.`. Any other file with no hunk (a pure rename, a mode change, an empty new file) shows `No content changes.`.
- Q6: the wireframe draws a tree, but docs don't fix its order or anchors. Default: nested `<ul>`s, one `<li>` per directory (`app/`) holding its entries. Every directory appears once, where its first file appears, and files keep patch (rowid) order, which is git's path order. Each file entry is `<name> +A −D`, with both numbers always shown (the wireframe's `+42` is shortened), and links to `#file:<path>`. The file section's id is `file:<path>`, so a root file named `status` or `files` can't clash with the header's ids. The tree sits in a left column with the diffs on the right, as in the wireframe, and stacks above them on narrow screens.
- Q7: docs say highlight.js colors the diff but not how it picks a language. Default: the file's table has `data-lang` set to the lowercased extension after the last `.` in its name, and no attribute without one. A small inline script on the files tab highlights each code cell with `hljs.highlight(text, {language, ignoreIllegals: true})`, only when `hljs.getLanguage(lang)` knows the language. There is no auto-detection. Lines are highlighted one at a time, so a construct that spans lines, such as a multi-line string, may be colored wrong. A `ponytail:` comment on the script names that ceiling.
- Q8: §8 gives the anchor `path:side:line` but not where it goes. Default: on each line-number link, so a context row has two anchors, one per side. The path is used verbatim (escaped by Jinja). A path with a space makes a technically non-conforming id, but browsers still match it from a percent-encoded fragment.
- Q9: 004 limited hard-coded colors to the escalated red. Default: add and del rows get a background each, from `light-dark()` pairs with GitHub's diff colors. These are the only new hard-coded colors, and they keep contrast in both schemes. Hunk and note rows use `GrayText`.
- Q10: a patch can be up to 5 MB, and docs don't say how to show a big one. Default: render every row, with no collapsing. A `ponytail:` comment names the ceiling (a huge diff renders slowly) and the upgrade (collapse files over N lines).
- Q11: 007's form route builds `CommentBody` by hand, so a bad `line`, `side`, or `round` would raise pydantic's `ValidationError` as a 500. Default: catch it and raise a 422 whose `detail` is the error messages, without echoing the input.
