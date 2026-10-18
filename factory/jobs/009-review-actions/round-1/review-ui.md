VERDICT: CHANGES

- src/claude_factories/templates/review.html:29-40 and src/claude_factories/templates/base.html:44 — The action buttons don't match the docs/ui.md §8.2 wireframe, which puts `[Request changes]  [Approve]` on the title row, top right, beside `#12 …`. Here the `.review-actions` row sits under the meta line as a stacked column. The Summary textarea takes the full width, and `align-items: end` pushes Approve to the bottom right, next to the textarea, so it doesn't line up with Request changes (screenshot: round-1 check, task #1 review page, light and dark). The row reads as broken, not as the wireframe. Fix: put both buttons in a flex row beside the `<h1>` (for example, wrap the h1 and a `.review-actions` div in a `display:flex; justify-content:space-between; align-items:center` header row). Keep the Summary textarea and its label in the Request changes form, in its own row under the title, and align the two buttons on one baseline. The rest of the header (meta line, tabs) stays as it is.

## Checked and OK
- Conversation and Files changed tabs both show the header with Summary, Request changes, and Approve. Round 1 and round 2 show the same controls.
- Disabled: Backlog task #2 and review task #4 with no rounds show the textarea and both buttons disabled. Task #6 (in_progress) is not part of the check.
- Enabled: review tasks with rounds (#1, #3 escalated, #5 factory, #8) have the textarea and both buttons enabled.
- Blank summary: whitespace only `"   "` gets past the `required` check and returns 422. The form's `.form-error` shows `body_md must not be blank` inline.
- Valid summary: Request changes returns to the review page with the status `In progress · rework`. The controls are disabled again, and the timeline shows `me CHANGES_REQUESTED · round 2`.
- Approve (task #5, factory): the page redirects. Status is `Done`, and `section#commit` shows the 4 hint lines in a bordered, horizontally scrolling `<pre>`. The commit section sits above the tabs.
- Unknown id `/tasks/9999/review`: 404 page "Task #9999 not found", with a link back to Claude Factories.
- Light and dark both follow the system setting (color-scheme switch). Labels, buttons, the diff, and the commit block are readable in both.
- Keyboard: `Tab` reaches Request changes with a visible focus ring in light and dark. The Summary textarea has an associated `<label>` ("Summary").
- Live polling: the review page doesn't poll, and the job adds none.
- Console on the job's pages: no errors from the job. The only error is the favicon 404 described in the nits below.

## Nits (non-blocking)
- src/claude_factories/templates/base.html:7 — Every page logs `Failed to load resource: 404 /favicon.ico`. This predates the job. Fix if you like: add `<link rel="icon" href="data:,">` to the head.
- src/claude_factories/templates/review.html:37 — The disabled Approve button is faint in light mode. Disabled controls are exempt from the contrast rule, so this is only a note.
