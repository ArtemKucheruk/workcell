APPROVE
Built: 8 Jinja templates in src/claude_factories/factory_templates/: the `/factory <id>` SKILL.md and the 7 agents, adapted from this repo's `.claude/` so all state goes through `fctl`. They have no git writes, no board, no job folders, and cite no doc or § number. `create_factory()` in app.py is shared by `POST /api/projects/{id}/factory` (JSON with real status codes) and the form route `POST /projects/{id}/factory` (a 200 fragment, with errors in `role="alert"`). It runs every check (404, test command, is a directory, realpath containment) before any write, skips files that exist (lexists) unless overwrite is set, and sets `factory_version = 1` only when it wrote something. The board header gets a Create factory form with an Overwrite tickbox in states none and uncommitted, and `#factory-result` sits outside `#board`.
Rounds: 1 of 2. All four round-1 reviews (security, ux, ui, code) PASS. No feedback files.
Tests: 413 passed (build.md, re-run by review-code). AC1–AC25 map one-to-one to tests in tests/test_factory.py, and I read each one against its criterion. tests/test_board.py is unchanged.
Docs: no conflict with MVP §3.2, §3.4, §3.6, §4.3–§4.5, data-model §5.1 and §6.1, claude-code §7.1–§7.3 and §7.5, or ui §8 item 3. No schema, dependency, CLI, pyproject, base.html, or `.claude/` change.

## Open questions
Spec questions. The builder used every default:
- Q1 (bootstrap-repo references): no doc file and no § anywhere. The checklists are the general ones from the spec. Each reviewer keeps its PASS line for a task with nothing in its area, and the approver keeps its ESCALATE rules.
- Q2 (models): follows docs/: opus for spec-writer, builder, review-security, and approver, and sonnet for review-ux, review-ui, and review-code. All four reviewers are spawned in one message with no review-ui skip rule. This repo's own `.claude/` (haiku for ux/ui, ui skipped when no UI files change) differs and was left alone.
- Q3 (tools): builder gets `Read, Edit, Write, Grep, Glob, Bash`, and the other six get `Read, Grep, Glob, Bash`. Each non-builder says to use Bash only for `fctl`, `git status`, and `git diff` (review-code also runs the test command).
- Q4 (frontmatter): SKILL.md has only `name: factory` and `description:`, with no `disable-model-invocation`.
- Q5 (rendering): Jinja2 with autoescape off and StrictUndefined. The values appear only in bodies, never in frontmatter, and are inserted verbatim. SKILL.md carries the name, the default branch, and `Test command for this repo: <test_cmd>`. builder.md and review-code.md carry the test command.
- Q6 (order): SKILL.md first, then spec-writer, builder, review-security, review-ux, review-ui, review-code, approver. `skipped` uses the same order.
- Q7 (no test command): NULL or blank → 409 `no test command: in the repo, run fctl connect --workspace <name> --test-cmd "<your test command>"`, and nothing is written. Small addition: the workspace name goes through `shlex.quote`, so a name with spaces is quoted (`personal` is unchanged).
- Q8 (containment): every check runs before any write. The project path must be a directory. Each target's realpath must be inside the root's realpath (`is_relative_to`), and the first one outside → 409. "Exists" means `os.path.lexists`. A failed write after the checks is a plain 500, and files already written stay.
- Q9 (factory_version): set to 1 only when a call writes at least one file.
- Q10 (header): `Factory: <state>` is unchanged. The form shows in none and uncommitted, and ready shows only `Factory: ready ✓`. The label reads "Overwrite existing files". `#factory-result` has `aria-live="polite"`. The state text updates on the next page load.
- Q11 (form errors): a separate form route. Every HTTPException from `create_factory`, a 404 included, becomes a 200 fragment with `<p role="alert">`. The middleware's 403 stays 403.
- Q12 (result wording): as given. Singular forms are added for 1 file ("Wrote 1 file:", "Skipped 1 existing file").

Raised during build or review. None reverses a default or conflicts with docs, and all were left as they are:
- Not in the spec: SKILL.md's "Where to start" table decides, on a resumed run (Retry), between build and agent_review from whether the latest round has verdicts yet, and between rework and agent_review from whether a round newer than my feedback exists. The 2-round cap counts the rounds after the round my latest feedback is on, or all rounds when I left none, so a Retry doesn't reset the budget but a rework does. This mirrors this repo's `/factory resume` and "rounds used" rules.
- security nit: with overwrite, a target that is a symlink to another file inside the repo is written through (a probe replaced `<repo>/Makefile`). Containment holds. Possible fix: `target.unlink()` first when it is a symlink.
- security nit: the form route treats any non-empty `overwrite` value as true (`overwrite=false` overwrites). Only htmx's `on` reaches it in practice. Possible fix: `== "on"`.
- code nit: a template render error partway through leaves a partial write. This is consistent with Q8's plain 500.
- ui/ux nits: the error `<p role="alert">` isn't bold like `#board-error`, the form has no `aria-label`, and an unknown project shows the bare "Not Found" (same as the existing `one_or_404` convention).
