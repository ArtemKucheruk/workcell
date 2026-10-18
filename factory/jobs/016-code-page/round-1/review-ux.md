VERDICT: PASS

Checked in the worktree at `.claude/worktrees/016-code-page` against a fixture repo (tracked README.md with raw HTML, src/app.py with `<b>&</b>`, latin-1 file, binary file, symlink to a file outside the repo, plus untracked and ignored files). Ran `pytest tests/test_code.py`: 25 passed.

Browser (headless, playwright-cli): board **Code** link → `/projects/1/code` → landing shows branch `main`, the tree, and the README with the script tag as literal text. Expanding `src/` and clicking `app.py` shows the highlighted file with gutter 1–3 and escaped `<b>&</b>`. The README link in the tree returns to the landing.

curl: tracked files 200 (landing, `path=`, leak → "Not shown: points outside the project.", blob.bin → "Binary file not shown.", latin.txt shown with U+FFFD, docs/guide.md). 404 for `../secret.txt`, `src`, `.git/config`, `/etc/hosts`, and `/projects/999/code`. Missing path and non-repo directory both return 200 with `role="alert"` naming the path, and no tree.

No findings that block.

## Nits (non-blocking)
- `src/claude_factories/app.py:23` — for a missing path the alert reads `Can't list files in <path>: fatal: cannot change to '<path>': No such file or directory`, which repeats the path. Fine as is; could drop the path from the alert or from git's line.
- Browser console shows a 404 for `/favicon.ico` on the code page. The code page doesn't add a favicon; I didn't check whether other pages do the same.
