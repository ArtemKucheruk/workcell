# 011-factory-templates: Create factory (templates, API, board button)

## Goal
Ship the app's factory templates: the `/factory` orchestrator skill and the 7 agents. They are adapted from this repo's `.claude/` so that all state goes through `fctl` and the app instead of `factory/` files and git. `POST /api/projects/{id}/factory` renders them with the project's name, test command, and default branch, and writes the 8 files into `<repo>/.claude/`. Existing files are skipped unless `overwrite` is set. It returns the written and skipped lists plus the commit hint. The project board gets a **Create factory** button with an Overwrite tickbox, and the result shows in the header.

## Implements
- `docs/MVP.md §3.2` steps 1–3: Board → Create factory, render with name, test command, and default branch, then write `.claude/skills/factory/SKILL.md` and `.claude/agents/*.md` (8 files). Skip and list existing files unless Overwrite is ticked. Show the written files and `git add .claude/skills/factory .claude/agents && git commit -m "Add factory"`. Step 4's Run gating is already in 012. The hint next to a disabled Run is 014's.
- `docs/data-model-and-api.md §6.1`: `POST /api/projects/{id}/factory` → `{"overwrite":false}` ← 200 `{"written":[…],"skipped":[…],"commit_hint":"…"}`.
- `docs/data-model-and-api.md §5.1`: `projects.test_cmd` ("used in templates") and `projects.factory_version` ("NULL = factory never written") (Q9). No schema change.
- `docs/claude-code.md §7.1`: the 8 target paths, and the models (opus for spec-writer, builder, review-security, and approver; sonnet for review-ux, review-ui, and review-code) (Q2).
- `docs/claude-code.md §7.3`: the SKILL.md excerpt (steps 1–7, the rework line, `Test command for this repo: {{ test_cmd }}`), review-security as the agent pattern (`fctl show`, `fctl diff`, one `fctl verdict`, optional `fctl comment`, "Do not edit code. Write nothing else."), and the builder rules (work only in the cwd, run the test command against the criteria, end every round with `fctl submit <id> <<'EOF' … EOF`, never commit).
- `docs/claude-code.md §7.2` and `§7.5`: which agent posts with which `fctl` command. Only the orchestrator runs `fctl stage`. Every other agent posts only its own record.
- `docs/MVP.md §4.3` "Changes vs FACTORY.md": no merge, no commits, no `board.json` or `jobs/*`, stages only through `fctl stage`, and one entry point, `/factory <id>`, that continues from the task's current stage.
- `docs/MVP.md §3.4` and `§3.6` step 3: the loop the skill runs, and rework through a fresh `builder-<id>` reading `fctl show <id> --feedback`.
- `docs/MVP.md §4.4`: the templates use only commands on the run's allowlist. Agents never call `fctl approve`, `run`, or `rework`.
- `docs/ui.md §8 item 3`: the board header shows "factory state or **Create factory**" (Q10).
- `docs/MVP.md §4.5`: both new mutating routes sit behind the existing middleware. Writes stay inside the project root (Q8).

## Acceptance criteria

Setup, unless a criterion says otherwise: the `repo` fixture is connected with name `api-server`, workspace `personal`, `default_branch` `main`, and `test_cmd` `make check`. Requests carry `X-Requested-By: fctl`.

Template content (read from the files that `POST /api/projects/{id}/factory` wrote)
- [ ] AC1: a fresh repo → exactly 8 files appear under `<repo>`: `.claude/skills/factory/SKILL.md` and `.claude/agents/{spec-writer,builder,review-security,review-ux,review-ui,review-code,approver}.md`. Walking `<repo>` outside `.git/` finds no other new file.
- [ ] AC2: each agent file starts with `---` frontmatter. Its `name:` equals the file stem. `model:` is `opus` for spec-writer, builder, review-security, and approver, and `sonnet` for review-ux, review-ui, and review-code (Q2). `tools:` is `Read, Edit, Write, Grep, Glob, Bash` for builder and `Read, Grep, Glob, Bash` for the other six (Q3).
- [ ] AC3: SKILL.md's frontmatter has `name: factory` and a `description:` line, and no `disable-model-invocation` (Q4). Its body contains `$ARGUMENTS`.
- [ ] AC4: SKILL.md contains `fctl stage <id> <s>` for each `<s>` in spec, build, agent_review, approval, human_review, and escalated. It also contains `fctl show <id>`, `fctl show <id> --feedback`, `fctl round <id>`, and `builder-<id>` (§7.3).
- [ ] AC5: each agent posts with its own command. spec-writer has `fctl spec <id>`, and builder has `fctl submit <id>`. review-security, review-ux, review-ui, and review-code have `fctl verdict <id> <r>` and `fctl comment <id> <r>` with `<r>` = security, ux, ui, code. Approver has `fctl decide <id>`. Every agent file has `fctl show <id>`, and the four reviewers and the approver have `fctl diff <id>` (§7.2, §7.3).
- [ ] AC6: a project connected with `default_branch` `develop` → SKILL.md contains `api-server`, `develop`, and `make check`, and builder.md and review-code.md contain `make check`. No file contains `{{`, `}}`, or `{%` (Q5).
- [ ] AC7: every match of the regex `\bfctl ([a-z]+)\b` across the 8 files captures one of show, diff, spec, submit, verdict, comment, decide, stage, or round (§4.4). SKILL.md and builder.md each contain `never commit`, case-insensitive (§7.3).
- [ ] AC8: none of the 8 files contains `board.json`, `factory/jobs`, `FACTORY.md`, `§`, `gh pr`, `git worktree`, `/factory next`, `/factory approve`, `/factory rework`, `/factory resume`, `FCTL_HOME`, or `uv run pytest` (Q1).
- [ ] AC9: `test_cmd` `{{ name }} && echo "<b>&amp;"` → builder.md contains that exact string. It isn't HTML-escaped and isn't evaluated as a template (Q5).

`POST /api/projects/{id}/factory`
- [ ] AC10: a fresh repo with `{"overwrite": false}` → 200 with exactly `{"written": [the 8 paths in Q6 order], "skipped": [], "commit_hint": "git add .claude/skills/factory .claude/agents && git commit -m \"Add factory\""}`.
- [ ] AC11: after AC10, `.claude/agents/builder.md` is edited by hand, then a call with body `{}` → 200 with `written` `[]`, `skipped` the 8 paths in Q6 order, and the same `commit_hint`. Every file's bytes are unchanged, the hand edit included.
- [ ] AC12: only `.claude/agents/builder.md` exists beforehand, holding `custom\n` → `written` has the other 7 in Q6 order, `skipped` is `[".claude/agents/builder.md"]`, and builder.md still holds `custom\n`.
- [ ] AC13: the same setup with `{"overwrite": true}` → `written` has all 8, `skipped` is `[]`, and builder.md is now the template (it contains `fctl submit <id>`).
- [ ] AC14: `GET /api/projects?path=<repo>` reports `factory` `none` before the call and `uncommitted` after it. After running the hint's `git add .claude/skills/factory .claude/agents` and `git commit -m "Add factory"` in the repo (as argument lists), it reports `ready`, and `git status --porcelain` is empty.
- [ ] AC15: `projects.factory_version` is NULL before AC10's call and 1 after it. Where all 8 files were written by hand first, a call (all skipped) leaves it NULL (Q9).
- [ ] AC16: a project connected without `--test-cmd` (NULL), or with `test_cmd` `"   "` → 409 `{"detail": "no test command: in the repo, run fctl connect --workspace personal --test-cmd \"<your test command>\""}`. No `<repo>/.claude` is created (Q7).
- [ ] AC17: the project path was deleted, or is a regular file → 409 `{"detail": "<path> is not a directory"}`. Nothing is created at that path (Q8).
- [ ] AC18: `<repo>/.claude/agents` is a symlink to an empty directory outside the repo → 409 `{"detail": ".claude/agents/spec-writer.md resolves outside the project"}`, with overwrite false and with overwrite true. The outside directory stays empty, and SKILL.md wasn't written either (Q8).
- [ ] AC19: an unknown project → 404. A POST without `X-Requested-By` → 403. Neither writes a file.

Board (`/projects/{id}`)
- [ ] AC20: factory state `none` → outside `#board`, the header has a `<form>` with `hx-post="/projects/<id>/factory"` and `hx-target="#factory-result"`. The form holds an `<input type="checkbox" name="overwrite">` inside a `<label>` whose text contains `Overwrite`, and a `<button>` whose text is `Create factory`. An element with `id="factory-result"` sits outside `#board`. 004's tests in tests/test_board.py still pass unchanged (Q10).
- [ ] AC21: state `uncommitted` → the form is present. State `ready` → the page has no `hx-post="/projects/<id>/factory"` and no `Create factory` button, and still shows `Factory: ready ✓` (Q10).
- [ ] AC22: `POST /projects/<id>/factory` as a form with no `overwrite` field → 200 with an HTML fragment (no `<html`). With tags stripped and entities unescaped, it lists the 8 written paths and contains the commit hint. The 8 files exist on disk (Q11, Q12).
- [ ] AC23: a second form post with no `overwrite` → the fragment lists the 8 paths as skipped and contains `Overwrite`. A post with `overwrite=on` → it lists the 8 as written, and a hand-edited builder.md is replaced by the template (Q12).
- [ ] AC24: a form post for a project with no test command → 200 with a fragment whose `role="alert"` element holds AC16's detail text. No file is written (Q11).
- [ ] AC25: a form post without `X-Requested-By` → 403, and no file is written.

## Files
- `src/claude_factories/factory_templates/skills/factory/SKILL.md` and `src/claude_factories/factory_templates/agents/{spec-writer,builder,review-security,review-ux,review-ui,review-code,approver}.md`: new, 8 Jinja templates that mirror `.claude/`. Start from this repo's `.claude/` files and from §7.3, and adapt them:
  - Job folders become `fctl show <id>` / `fctl diff <id>` to read and the agent's own `fctl` command to post.
  - The cwd is the worktree the app created.
  - The orchestrator does no git writes, has no commands besides `/factory <id>`, and keeps no board.
  - Write prose so that `fctl` is followed by a subcommand only where a command is meant (AC7).
- `src/claude_factories/app.py`:
  - One tuple of the 8 relative paths (Q6), reusing the existing `SKILL` constant.
  - A `jinja2.Environment` over `factory_templates/` with `autoescape=False`, `keep_trailing_newline=True`, and `undefined=StrictUndefined` (Q5).
  - The commit hint constant.
  - `POST /api/projects/{project_id}/factory`, placed after `find_project`.
  - The form route `POST /projects/{project_id}/factory`, placed after `move_project`. It reads `overwrite` with `form_field()`, calls the same function as the API route, and renders the fragment.
  - Writes use `Path.mkdir(parents=True, exist_ok=True)` and UTF-8 text.
- `src/claude_factories/templates/project.html`: the Create factory form and `#factory-result` in the header. The existing `<span>Factory: …</span>` stays as it is.
- `src/claude_factories/templates/factory_result.html`: new fragment for the result or the error.
- `tests/test_factory.py`: new, with all criteria above. `tests/conftest.py` changes only if a helper gets shared.

No schema change. No new dependency: jinja2 is already a runtime dependency. No CLI change. No pyproject change: uv_build ships every file under the package, as it already does for `schema.sql` and `templates/`. Leave `base.html` alone: 008-review-files is active and edits its style block. Use the existing classes (`toolbar`, `muted`). Don't change this repo's own `.claude/`.

## Out of scope
- The commit hint next to a disabled Run / Run next, and enabling Run (014). The Run gating on `ready` is already 012's.
- A `fctl` command for Create factory (§7.2 has none), and `fctl setup` with the global factory-connect and factory-submit skills (015).
- Committing the files. The app never commits (§3.2, §10 assumption 3).
- Writing the project's `.claude/settings.json` (§4.4 leaves it to the project).
- Template upgrades with a 3-way merge, a configurable reviewer set, and editing the loop in the UI (§9 Later).
- Refreshing the header's `Factory: <state>` live after a create (Q10).
- Running the templates under a real `claude` (tests never call it), and retiring this repo's file-based factory (after 015).

## Open questions
- Q1: this repo's agents cite this repo's docs (`docs/MVP.md §4.5`, `docs/ui.md §8`), `FACTORY.md`, `uv run pytest`, and `FCTL_HOME`, and other projects have none of them. Default: the templates cite no doc file and no § number. The checks become general:
  - security: §7.3's list (injection, missing authz, secret leaks, unsafe input handling), plus shell strings in subprocesses.
  - ux: the task's user-facing flows, CLI output, error messages, and exit codes.
  - ui: pages against the spec and any design docs in the repo, empty and error states, light/dark, and accessibility basics.
  - code: runs `{{ test_cmd }}`, checks that every acceptance criterion has a passing test, and that nothing unrequested was added.
  - spec-writer: reads the task, the repo's own docs if any, and the code in its cwd.
  - Each one keeps its "nothing in this task" PASS line, and the approver keeps its ESCALATE rules.
- Q2: §7.1 and §10 assumption 14 say sonnet for ux, ui, and code, "unchanged from FACTORY.md". This repo's FACTORY.md and `.claude/` have since moved ux and ui to haiku, and the orchestrator skips review-ui when no UI files change. Default: follow docs/. Use sonnet for review-ux, review-ui, and review-code, and spawn all four reviewers in one message (§7.3 step 4), with no skip rule.
- Q3: docs give tools only for review-security (`Read, Grep, Glob, Bash`). Default: builder gets `Read, Edit, Write, Grep, Glob, Bash`. The other six get `Read, Grep, Glob, Bash`, because they need Bash for `fctl` and post through `fctl` rather than writing files (§4.3: files on disk would land in the diff).
- Q4: this repo's SKILL.md sets `disable-model-invocation: true`. §10 open question 1 may switch the prompt to "Use the factory skill on task 12", and that flag would block it. Default: the frontmatter holds only `name: factory` and `description:`, as in §7.3.
- Q5: docs show `{{ test_cmd }}` but don't say where the name and the default branch go, or how values are escaped. Default:
  - Jinja2 with autoescape off, because the output is markdown, not HTML. `StrictUndefined` is on. Values are inserted verbatim and never evaluated as template code.
  - The three values appear only in bodies, never in frontmatter, so a name with `:` can't break the YAML.
  - SKILL.md carries all three, e.g. "task $ARGUMENTS in {{ name }}; the worktree branched from {{ default_branch }}", plus §7.3's `Test command for this repo: {{ test_cmd }}`. builder.md and review-code.md carry `{{ test_cmd }}`.
- Q6: §6.1's `written` example lists SKILL.md and then builder.md, then `…`, so no order is fixed. Default: SKILL.md first, then the agents in §7.1's order: spec-writer, builder, review-security, review-ux, review-ui, review-code, approver. Paths are relative to the repo root with `/`. `skipped` uses the same order.
- Q7: `projects.test_cmd` can be NULL, and docs don't say what the templates render without it. Default: a NULL or blank `test_cmd` → 409 `no test command: in the repo, run fctl connect --workspace <workspace name> --test-cmd "<your test command>"`, with the project's workspace name filled in, and nothing written.
- Q8: §4.5's containment rule covers the code page, not writes. Default: run every check before any write.
  - The project path must be an existing directory, else 409 `<path> is not a directory`.
  - For each of the 8 targets, in Q6 order, `os.path.realpath(target)` must lie inside `os.path.realpath(project path)`. The first one that doesn't → 409 `<relative path> resolves outside the project`.
  - "Exists" means `os.path.lexists`, so a broken symlink is skipped too.
  - A failed write after the checks is a plain 500. Files already written stay.
- Q9: `factory_version` has no reader yet. Default: set it to 1 when a call writes at least one file. A call that writes nothing leaves it as it was.
- Q10: §8 item 3 says "factory state or Create factory", and Overwrite only matters once files exist. Default:
  - Keep `<span>Factory: <state></span>` as it is (004 AC3).
  - When the state isn't `ready`, add a plain form next to the span with the Overwrite checkbox (unticked) and a `Create factory` button, with `hx-target="#factory-result"`.
  - `ready` shows only `Factory: ready ✓`, as in the §8.1 wireframe. Rewriting a committed factory is the Later "template upgrades".
  - `#factory-result` sits in the header, outside `#board`, so the 3 s poll (which swaps only `#board`) keeps the result. The header's state updates on the next page load.
- Q11: htmx posts urlencoded forms, and htmx 2.0 doesn't swap 4xx responses by default. Default: a separate form route, as in 004 Q10. It catches the `HTTPException` from the shared function and answers 200 with the fragment showing the error's `detail` in `<p role="alert">`. The JSON route keeps the real status codes. The 403 from the middleware stays 403.
- Q12: docs don't word the result. Default:
  - `Wrote N files:` and a list of `<code>` paths. Omitted when N is 0.
  - `Skipped N existing files (tick Overwrite to replace them):` and a list. Omitted when N is 0.
  - `Commit them so runs can see the factory:` and the hint in `<pre><code>`, always shown.
  - Jinja autoescape stays on in this HTML fragment.
