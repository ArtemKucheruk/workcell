VERDICT: PASS

No blocking findings. Checked against docs/MVP.md §4.3–§4.5:

- §4.5 header: `fctl run <id>`, `fctl run next`, and `task add --run` all POST through `api()` (src/claude_factories/cli.py:31–56), which always sends `X-Requested-By: fctl`. `FCTL_URL` still defaults to `http://127.0.0.1:4545`. No server, Host, markdown, path, or 413 code changed.
- Subprocesses: the diff adds none. `run next` reuses `main_checkout()` → `_git()`, which takes an argument list. No `shell=True` and no `os.system`.
- URL building: the `run` target must be `next` or `isdecimal()`, and it goes into the path as `int` (cli.py:138–140). Anything else hits `p.error` before any request is sent. The project and task ids come from the local server's JSON.
- §4.3: the run env, the `claude auth status` check, and `--bare` are untouched (app.py isn't in the diff). The CLI only calls 012's endpoints, which still enforce them on the server.
- §4.4: the allowlist and denylist (app.py:437–443) are unchanged and match the doc. They don't allow `fctl run` or `fctl task`, so agents still can't start runs, including through the new `task add --run`. No shipped factory template grants a broad `fctl` permission. The global skills add no `allowed-tools` (Q8), so every `fctl` call they lead to still needs my approval in my own session. Both skills tell Claude never to commit, stage, or run git write commands.
- `fctl setup` writes only to the fixed paths `Path.home()/.claude/skills/{factory-connect,factory-submit}/SKILL.md`, with no user input in the path. It sends no HTTP and logs no secrets. tests/conftest.py now points `HOME` at a temp dir for every test, so the suite can't write the real `~/.claude`.
- No SQL and no logging in the diff.

## Nits (non-blocking)
- src/claude_factories/global_skills/factory-connect/SKILL.md:12–21 — the test command is read from repo files (README, CI config, package.json), and a cloned repo controls those. That string becomes `projects.test_cmd`, which runs get to execute. Today I approve the `fctl connect` call by hand, so I do see it. Fix (optional): have step 2 tell Claude to show the chosen command and say where it came from before running `fctl connect`.
- src/claude_factories/global_skills/factory-submit/SKILL.md:171–173 — the quoted heredoc `<<'EOF'` stops early if the generated description has a line that is exactly `EOF`, and the shell would then run the lines after it. The spec (AC5) and docs require this form, and I approve the call by hand, so it isn't a defect. Fix (optional): add a line telling Claude to keep any line that is exactly `EOF` out of the text.
