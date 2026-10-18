# Round 1
## Changes
- src/claude_factories/app.py: new `# --- Code page (docs/ui.md §8 item 6) ---` section after `create_factory_form`, before the review code:
  - `git_stdout(root, *args)` runs git with an argument list and `timeout=10`. It catches `TimeoutExpired`, `OSError`, and `ValueError`, and returns stdout, or the first line of stderr (or `git timed out`) (§4.1, Q10).
  - `read_tracked(root, path)` resolves `realpath(root/path)`. If the result is outside `realpath(root)` it returns "points outside the project". If it isn't a regular file (`isfile`) it returns "not a regular file". Otherwise it checks `os.stat` for the 1 MB limit, does a bounded read, checks for a NUL in the first 8000 bytes, handles the empty file, decodes UTF-8 with `errors="replace"`, and counts lines on `\r\n?|\n` with no extra line for a final ending (Q3, Q4, Q5, Q9). An `OSError` such as permission denied becomes a `Not shown: <strerror>.` note instead of a 500.
  - `GET /projects/{project_id}/code?path=` works like this:
    - Unknown project → `one_or_404`.
    - `git ls-files -z` failure → 200 with the alert.
    - Names are decoded with `errors="replace"`. Only names that round-trip back to the same bytes can be viewed (Q4).
    - A `path` that isn't in that set → 404 `<path> is not a tracked file in <project>`. This check runs before any filesystem call (Q2).
    - Otherwise the page shows README.md or the file. `branch --show-current` gives the branch, or `detached HEAD` when it prints nothing (Q7). The language comes from the lowercase extension, using the same expression as `review_files`. I copied that expression instead of extracting it, so the review lines that 009 is editing stay untouched.
  - It reuses `one_or_404`, `file_tree()`, and the `markdown` filter.
- src/claude_factories/templates/code.html: new page that extends `base.html`. The header has a home link, `<h1>` with a project link · Code, and `Branch <code>…</code>`. The body uses `.files-layout` with `#file-tree`: each directory is a `<details>` that is `open` only if it holds the shown file, and the shown file's link has `aria-current="page"` (Q8). Links use `?path={{ path | urlencode }}`. The main column shows one of these:
  - a note
  - the README as markdown (landing)
  - the file: a gutter `<pre aria-hidden>` beside one `<pre><code data-lang>`, highlighted by the 008 rule (`hljs.getLanguage`, no auto-detection)
- src/claude_factories/templates/base.html: CSS under `/* Code page (docs/ui.md §8 item 6) */`. It adds the `.code-view` flex row and a sticky gutter (system colors `Canvas`/`GrayText` only). `code` inherits the `pre`'s font so the line numbers line up. It overrides hljs's `pre code.hljs` padding, which would otherwise shift the code under the gutter. The tree gets a pointer cursor and bold for the current file.
- tests/test_code.py: new, one test per AC. It uses the `repo`, `client`, `git`, `write`, and `commit` helpers from conftest, and `H`, `header`, `not_found_page`, and `text` from test_review.

## Criteria → tests
- AC1 → tests/test_code.py::test_tree_lists_tracked_files
- AC2 → tests/test_code.py::test_landing_renders_readme (no `path`, and `path=`)
- AC3 → tests/test_code.py::test_readme_raw_html_off
- AC4 → tests/test_code.py::test_no_readme
- AC5 → tests/test_code.py::test_no_tracked_files
- AC6 → tests/test_code.py::test_line_numbers (`\n`, `\r\n` with no final ending, and lone `\r`)
- AC7 → tests/test_code.py::test_code_escaped
- AC8 → tests/test_code.py::test_language_from_extension
- AC9 → tests/test_code.py::test_binary_not_shown
- AC10 → tests/test_code.py::test_size_limit
- AC11 → tests/test_code.py::test_non_utf8_replaced
- AC12 → tests/test_code.py::test_header_branch
- AC13 → tests/test_code.py::test_dotdot_404
- AC14 → tests/test_code.py::test_untracked_paths_404
- AC15 → tests/test_code.py::test_symlink_outside
- AC16 → tests/test_code.py::test_readme_symlink_outside
- AC17 → tests/test_code.py::test_symlink_inside
- AC18 → tests/test_code.py::test_odd_name_link
- AC19 → tests/test_code.py::test_tree_open_and_current
- AC20 → tests/test_code.py::test_unknown_project_404
- AC21 → tests/test_code.py::test_git_failure_alert (path missing, and a directory that isn't a repo)

## Open questions
- Q1–Q10 → the spec's defaults, as written. Three choices it left open:
  - When `git ls-files` fails, a request with `?path=` also gets the 200 alert page, not a 404. Membership can't be checked, and the alert is the useful message.
  - A tracked symlink to a file inside the root, including one under `.git/`, is followed (§4.5 only forbids leaving the root).
  - The README's own `# Hello` renders as a second `<h1>` under the page's `<h1>` (project · Code). The landing heads it with `<h2><code>README.md</code></h2>`.
- Not tested (the spec has no AC for it): a non-UTF-8 name listed with U+FFFD whose link gets a 404 (Q4). APFS refuses such names on disk, so I checked it once by hand: I put the entry in the index with `git update-index --cacheinfo`, the name was listed, and its link returned 404. The throwaway test was then deleted.

## Test output
```
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/016-code-page/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
478 passed, 1 warning in 54.47s
```
