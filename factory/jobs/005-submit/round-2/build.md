# Round 2
## Changes
- src/claude_factories/app.py: `unquote()` now catches the `ValueError` that `codecs.escape_decode` raises on malformed C-quoting (a trailing `\`, or a bad `\x`) and returns `""`. Every path branch already turns an empty name into a 422, so these patches now get a 422 instead of a 500.
- src/claude_factories/app.py: new `safe_path()`, called once at the end of `parse_section()`. It refuses a `path`, or a renamed row's `old_path`, that is empty, absolute, has a `..` segment, or contains NUL. These are paths git never writes. The 422 message is now `can't read a safe file path in: <header>`.
- src/claude_factories/app.py: the diff response sends `X-Content-Type-Options: nosniff`.
- tests/test_rounds.py: new `hand_patch()` helper. AC16's parametrize gains 7 bodies: two malformed `+++` quotes, a malformed quoted header (the mode-only fallback), `b/../etc/passwd`, `b//etc/passwd`, a NUL in the name, and `rename from ../x`. AC25 also asserts the `nosniff` header.

## Criteria → tests
- AC1–AC15, AC17–AC41: unchanged from round 1 (see round-1/build.md).
- AC16 → tests/test_rounds.py::test_round_bad_body (now 14 cases)
- AC25 → tests/test_rounds.py::test_diff_returns_patch_bytes (adds the nosniff check)

## Review findings
- security · `unquote()` → `codecs.escape_decode` raises a `ValueError` on malformed quoting, giving a 500 → fixed: caught, returns `""`, which leads to the existing 422. Two `+++` cases and one header-fallback case are in AC16.
- security (nit) · paths git never produces (`../`, leading `/`, NUL) were stored → fixed: `safe_path()` gives a 422 for `path` and for a rename's `old_path`. 4 cases are in AC16.
- security (nit) · the `text/x-diff` response had no `nosniff` → fixed: header added and asserted in AC25.
- security (nit) · `codecs.escape_decode` is an undocumented internal → kept. With the `ValueError` handled, its failure mode is covered, and a hand-written octal decoder would be more code than the risk calls for. The reviewer marked this optional once the `ValueError` was fixed.
- code (nit) · the `UnicodeEncodeError` handler isn't in the spec → kept. The reviewer called it acceptable, and without it a JSON `\ud800` gives a 500.
- code (nit) · `api()` decodes non-JSON bodies strictly → not changed. The server always sends UTF-8 (the patch is stored as `str` and encoded on the way out), so the strict decode is unreachable.
- ux (nit) · `fctl submit 99` prints `fctl: 404 Not Found` → not changed. Spec Q7 and AC15 call for the existing bare 404. A friendlier message would change the API, which is for a later job.
- ux (nit) · a bad `base_sha` 422 is FastAPI's validation list → not changed. AC16 asks only for a 422, and it matches how the other routes' validation errors look.

## Open questions
- Same as round 1. New: renamed rows check `old_path` too; other rows have `old_path` NULL by construction.

## Test output
```
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/artem/personalProjects/claude-factories/.claude/worktrees/005-submit/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
243 passed, 1 warning in 27.92s
```
