VERDICT: PASS

Checked: tests/test_board.py passes (34) in the worktree with a temp FCTL_HOME. I read the diff against the spec and docs/ui.md §8.1. Board output (chips `r2 sec✓ ux✓ ui· co✗`, `+126 −9`, `waiting on you`, escalated badge, factory state wording) matches. The new-task form route returns 204 with HX-Redirect and gives 404, 422, and 403 as the spec requires. The 409 text from the drag appears in `#board-error`, and build.md records a real-browser check of it.

## Nits (non-blocking)
- templates/project.html (new-task form) — a 422 from `POST /projects/{id}/tasks` shows nothing to the user, because htmx doesn't swap 4xx. Client-side `required` and `pattern` make this unlikely. Fix later: show the error in `#board-error`, or via `htmx:responseError`.
- The drop into an empty column (position 1.0) was only code-read, not run in a browser. Check it by hand once.
- No keyboard path for moving cards (Q12). The spec accepts this and says it needs a decision from the user.
