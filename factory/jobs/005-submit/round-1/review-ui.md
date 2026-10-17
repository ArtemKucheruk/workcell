VERDICT: PASS

No UI in this job. The diff touches only app.py, cli.py and tests. It adds no templates or static files and no pages, so there is nothing to render. The `+ New task` form route only gains a pass-through of `request`, and its behavior is unchanged.
