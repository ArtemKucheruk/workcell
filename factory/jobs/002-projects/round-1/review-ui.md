VERDICT: PASS

Checked by reading base.html, index.html, workspace.html and project.html against spec Q10-Q16 and docs/ui.md §8 item 2. I did not render the pages.

- Workspace page: table columns, the empty state, `+ Workspace` form and the link to `/` match the spec. Factory state is a plain word, as Q12 says.
- Project page: heading `<name> · <workspace link>`, the path and the labeled move `<select>` match Q11.
- Light and dark: `color-scheme` meta, `GrayText`, and the hljs stylesheets switch on `prefers-color-scheme`. No hard-coded colors.
- Assets are vendored under `static/`. There is no build step. No live parts yet, so no polling is needed.
- The inputs, selects, buttons and links are native elements, so focus rings are visible. The workspace input has an `aria-label`.
- Error states are the JSON 404 from Q15, which the spec accepts.

## Nits (non-blocking)
- workspace.html:32-35, project.html:10-19 — a 422 or 404 from the htmx forms shows nothing, because htmx doesn't swap 4xx responses. Native `required` and `pattern` cover the common case. Consider an `hx-on::response-error` message later.
- workspace.html:18 — long paths widen the table. Add `overflow-wrap:anywhere` to the path cell.
- base.html:15 — the `GrayText` row borders and muted text are fine for contrast, but check them in forced-colors mode.
- index.html has no `+ Workspace` form. That's fine for this job, since 017 owns the dashboard.
