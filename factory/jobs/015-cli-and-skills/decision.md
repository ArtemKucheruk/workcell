ESCALATE
Built `fctl setup`, which writes the two global skills to `~/.claude/skills/` without touching the network. Also built `fctl run <id>` / `fctl run next`, `fctl task add --run`, the two shipped `global_skills/*/SKILL.md` files, and a temp `HOME` in conftest. Used 2 of 2 rounds. All round-2 verdicts are PASS. 564 tests passed in both rounds. AC1–AC17 each have a passing test in tests/test_cli.py, and AC18 is the full suite run.
You need to decide Q12. To fix ux findings, round 2 edited `app.py`. That file isn't in the spec's Files list, and the spec marks "the run endpoints and their checks" (012) out of scope. The edits changed 3 server error details: the `find_project` 404 hint, `run_task` returning `no task #<id>`, and the factory 409 split into two messages. Round 2 also rewrote the pinned expectations in earlier jobs' tests: 002 AC11 `test_find_project_unknown`, 012 AC19 `test_refused_without_factory`, and 012 AC24. This doesn't conflict with docs/: data-model-and-api.md §6.2 only gives the 404/409 conditions, not the text. Your choice is to keep it, or revert the 3 messages and 3 test edits. The CLI and skills don't depend on them.
If you keep it, note the gate change at app.py:547–553. It now refuses `uncommitted` and `none` by name instead of `!= "ready"`. That's safe today because `factory_state` (app.py:132–143) returns only those 3 states, but it would let a run through if a 4th state were ever added. Security suggests `if state != "ready":` with the message picked inside. The uncommitted message also says "on main" twice (ux nit).

## Open questions
- Q1 `~/.claude` location → `Path.home() / ".claude"`, `CLAUDE_CONFIG_DIR` ignored.
- Q2 existing skill file → `SKILL.md` overwritten every run. Other files and other skills are left alone.
- Q3 setup output → one `Wrote <absolute path>` line per file, factory-connect first.
- Q4 failed write → stops at the first failure with `fctl: can't write <SKILL.md path>: <strerror>`, exit 1, no rollback. The builder added: a missing shipped source file (broken install) still raises a traceback, because the read is outside the `try`.
- Q5 `/factory-connect` with no argument → the skill asks for the workspace and runs nothing until you answer.
- Q6 no test command found → asks you. If you have none, it connects without `--test-cmd` and warns that Create factory needs one. Round 2 added: it shows the chosen command and the file it came from before connecting.
- Q7 new review vs next round → if `$ARGUMENTS` is a task id, or this session already printed `Review #N` for this change, it runs `fctl submit <N>`. Otherwise it runs `--new --title`. Round 2 added: no line of the text may be exactly `EOF`.
- Q8 skill frontmatter → `name` and `description` only.
- Q9 `fctl run <id>` output → `Run #<run_id> on #<id> → <FCTL_URL>/tasks/<id>`.
- Q10 `run next` project → the current repo's, via `main_checkout()` + `GET /api/projects?path=`. The line uses the reply's `task_id`.
- Q11 refused `task add --run` → the `Added` line prints first (flushed in round 2, so it stays first when piped). The run error goes to stderr with exit 1, and the task stays in Backlog.
- Q12 (new, builder's) where error hints live → in the server's `detail`, which changes 002/012 messages. This is the item to decide above.
- Extras beyond the spec (reviewers accepted them): on `can't reach …`, both skills ask you to start `fctl serve` rather than starting it. factory-submit, on `HEAD has no commit yet`, tells you and doesn't commit.
