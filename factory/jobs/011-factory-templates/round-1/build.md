# Round 1
## Changes
- src/claude_factories/factory_templates/skills/factory/SKILL.md: new. The `/factory <id>` orchestrator, adapted from this repo's SKILL.md and §7.3. It has a "Where to start" table that picks up from the task's current stage (none/spec/build, rework, agent_review, approval, review stages), then loop steps 1–7 with `fctl stage <id> …` for every stage. All four reviewers go out in ONE message, with WAIT FOR ALL on `fctl round <id>` 4/4, a 2-round cap counted from my latest feedback, and the approver's decision read from `fctl show <id> --round <n>`. Rework spawns a fresh `builder-<id>` on `fctl show <id> --feedback`. It does no git writes, keeps no board, has no other commands, and lists the run's allowlist. It renders `{{ name }}`, `{{ default_branch }}`, and `Test command for this repo: {{ test_cmd }}` in the body only.
- src/claude_factories/factory_templates/agents/{spec-writer,builder,review-security,review-ux,review-ui,review-code,approver}.md: new. Each one reads through `fctl show <id>` (the reviewers and the approver also use `fctl diff <id>`) and posts only its own record with `fctl spec`/`submit`/`verdict`+`comment`/`decide` in a heredoc. The checks are generalized per Q1, and each keeps its PASS line for a task with nothing in its area, plus the nits rule and the approver's ESCALATE rules. Models follow Q2 and tools follow Q3. builder.md and review-code.md carry `{{ test_cmd }}`. builder.md says "Never commit" and keeps the `.gitignore` rule because `fctl submit` sends untracked files.
- src/claude_factories/app.py: `FACTORY_FILES` (8 paths in Q6 order, reusing `SKILL`), `FACTORY_TEMPLATES` (a `jinja2.Environment` with autoescape off, keep_trailing_newline, and StrictUndefined), and `COMMIT_HINT`. `create_factory(project_id, overwrite)` checks in this order: 404, blank or NULL test_cmd → 409 (workspace name `shlex.quote`d, so `personal` stays as is), project path not a directory → 409, then any of the 8 realpaths outside the realpath of the root → 409. Only after every check passes does it write. It skips files that pass `os.path.lexists` unless overwrite is set, writes UTF-8 with `mkdir(parents=True, exist_ok=True)`, and sets `factory_version = 1` only when it wrote something. `POST /api/projects/{id}/factory` (after `find_project`) and the form route `POST /projects/{id}/factory` (after `move_project`, catches `HTTPException`, renders the fragment with 200) both call it.
- src/claude_factories/templates/project.html: when the state isn't `ready`, a form next to the unchanged `<span>Factory: …</span>`: `hx-post` and `hx-target="#factory-result"`, an unticked `overwrite` checkbox inside a `<label>`, and a `Create factory` button. A `<div id="factory-result" aria-live="polite">` sits in the header after the toolbar, outside `#board`.
- src/claude_factories/templates/factory_result.html: new fragment. The error shows in `<p role="alert">`. Otherwise it shows "Wrote N files:" and "Skipped N existing files (tick Overwrite to replace them):" (each left out when N is 0) as `<code>` lists, then "Commit them so runs can see the factory:" and the hint in `<pre><code>`. Autoescape is on.
- tests/test_factory.py: new, one test per AC.

## Criteria → tests
- AC1 → tests/test_factory.py::test_exactly_eight_files
- AC2 → tests/test_factory.py::test_agent_frontmatter
- AC3 → tests/test_factory.py::test_skill_frontmatter
- AC4 → tests/test_factory.py::test_skill_commands
- AC5 → tests/test_factory.py::test_agents_post_own_records
- AC6 → tests/test_factory.py::test_values_rendered
- AC7 → tests/test_factory.py::test_only_allowlisted_fctl_commands
- AC8 → tests/test_factory.py::test_no_bootstrap_factory_leftovers
- AC9 → tests/test_factory.py::test_test_cmd_verbatim
- AC10 → tests/test_factory.py::test_create_fresh
- AC11 → tests/test_factory.py::test_existing_files_skipped
- AC12 → tests/test_factory.py::test_one_existing_skipped
- AC13 → tests/test_factory.py::test_overwrite
- AC14 → tests/test_factory.py::test_factory_state_through_commit
- AC15 → tests/test_factory.py::test_factory_version
- AC16 → tests/test_factory.py::test_no_test_cmd (NULL and `"   "`)
- AC17 → tests/test_factory.py::test_path_not_a_directory (deleted and regular file)
- AC18 → tests/test_factory.py::test_symlink_out_refused (overwrite false and true)
- AC19 → tests/test_factory.py::test_unknown_project_and_no_header
- AC20 → tests/test_factory.py::test_create_factory_form (tests/test_board.py unchanged and passing)
- AC21 → tests/test_factory.py::test_form_by_state
- AC22 → tests/test_factory.py::test_form_post_writes
- AC23 → tests/test_factory.py::test_form_post_skips_then_overwrites
- AC24 → tests/test_factory.py::test_form_post_error
- AC25 → tests/test_factory.py::test_form_post_needs_header

## Open questions
- Q1 → no doc file and no § cited anywhere. Each checklist is the general one the spec lists, and each agent keeps its PASS line for a task with nothing in its area (security: "no security surface in this task", ux: "nothing user-facing in this task", ui: "no UI in this task", code: "no code in this task"). The approver keeps its ESCALATE rules.
- Q2 → sonnet for review-ux, review-ui, and review-code. All four reviewers are spawned in one message, with no skip rule.
- Q3 → builder gets `Read, Edit, Write, Grep, Glob, Bash`, and the other six get `Read, Grep, Glob, Bash`. Each non-builder says to use Bash only for `fctl` and `git status`/`git diff` (review-code also runs the test command).
- Q4 → SKILL.md frontmatter has only `name` and `description`.
- Q5 → Jinja2 with autoescape off and StrictUndefined. The values appear only in bodies, never in frontmatter. SKILL.md: "task $ARGUMENTS in {{ name }}", "a branch the app created from {{ default_branch }}", and "Test command for this repo: {{ test_cmd }}".
- Q6 → SKILL.md, then the agents in §7.1 order. `skipped` uses the same order.
- Q7 → a NULL or blank test_cmd → 409 with the workspace name filled in. I passed the name through `shlex.quote` so a name with spaces stays copy-pasteable (`personal` is unchanged).
- Q8 → every check runs before any write. Containment is `Path(realpath(target)).is_relative_to(realpath(root))`, and "exists" is `os.path.lexists`. A write error after the checks is a plain 500.
- Q9 → `factory_version = 1` only when at least one file was written.
- Q10 → the form shows for `none` and `uncommitted`, and `ready` shows only `Factory: ready ✓`. The Overwrite label reads "Overwrite existing files". `#factory-result` is in the header and has `aria-live="polite"` so screen readers announce the result.
- Q11 → a separate form route. Every `HTTPException` from `create_factory` (including a 404 for a deleted project) becomes a 200 fragment with `role="alert"`. The middleware's 403 stays a 403.
- Q12 → the wording as given. I also used the singular for "1 file" and "1 existing file" (the board already does this for "1 round").
- Not in the spec: on a resumed run, the skill's "Where to start" decides build vs agent_review from whether the latest round has verdicts yet (`fctl round <id>` 0/4), and rework vs agent_review from whether a round newer than my feedback's round exists. Both use only data `fctl show`/`fctl round` already print.

## Test output
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
413 passed, 1 warning in 51.64s
```
