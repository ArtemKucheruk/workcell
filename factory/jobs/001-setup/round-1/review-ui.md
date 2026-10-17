VERDICT: PASS

Scope is the base layout and a placeholder `GET /`, as the spec says. The real pages (wireframes in §8.1–§8.3) belong to later jobs. I read the templates and checked them against AC16 and AC17. I did not render pages.

- `base.html` has the `color-scheme` meta tag, the light and dark highlight.js theme links with the right `media` queries, and `hx-headers` on `<body>`.
- htmx and highlight.js are vendored under `static/`. There is no build step and no CDN link.
- `index.html` extends `base.html` and shows an empty-state message ("No projects yet.").

## Nits (non-blocking)
- `templates/index.html:3` — "No projects yet." is a placeholder, and the §8 empty state is worded differently. The later dashboard job should replace it.
- `templates/base.html` — there is no `<main>` landmark in the base, no focus styles, and no polling. None are needed until pages with content arrive.
