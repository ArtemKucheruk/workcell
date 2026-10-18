VERDICT: PASS

Checked in W (.claude/worktrees/011-factory-templates) with FastAPI TestClient, FCTL_HOME in a temp dir. Board `none`, `uncommitted`, and `ready` states; form post with no field (8 written), repeat (8 skipped, commit hint shown), `overwrite=on` (8 written); unknown project (`role="alert"` "Not Found"); no X-Requested-By (403); no test command (`role="alert"` with the AC16 text, Create factory form still shown). The header keeps `Factory: <state>`, the Code link, + New task, and disabled Run next, matching §8.1. `#factory-result` sits in the header, outside `#board`, so the 3 s poll keeps it. The new markup uses only existing classes and no external assets, and nothing in the job changes base.html or the vendored static files.

## Nits (non-blocking)
- W src/claude_factories/templates/factory_result.html:2 — the error `<p role="alert">` is plain text, unlike the bold `#board-error` on the board — give it a bold style, or reuse `#board-error`'s rule, so an error stands out in both schemes.
- W src/claude_factories/templates/project.html:14 — the form has no accessible name and no visible heading; acceptable for a toolbar, but `aria-label="Create factory"` would help screen-reader users who tab into it.
- W src/claude_factories/templates/project.html:29 — after a successful create, the header's `Factory: none` span stays stale until reload (the spec puts this out of scope, so noted only).
