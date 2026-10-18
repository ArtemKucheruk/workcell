VERDICT: PASS

No blocking findings. Checked in headless Chromium against a scratch FCTL_HOME with four seeded tasks: a factory task with two rounds, approver ESCALATE then APPROVE, and build notes; a backlog task with no spec, rounds, or description; an escalated standalone task whose round has no verdicts and whitespace-only build notes; and an unknown id (999).

- Layout and content match docs/ui.md §8 item 4 and the spec's Q1–Q11 defaults: header with project link, `#id title`, status · stage, `<code>` branch, and Review link; description, spec open, rounds with Review's row, chips, popovers, and collapsed Build notes; approver section; history list.
- Status · stage wording matches AC5: `Review · waiting on you`, red `⚠ NEEDS YOU — escalated`, `Backlog`.
- Empty states are designed: `No description.`, `No spec yet.`, `No rounds yet.`, `No build notes.`, and `no agent review` on the standalone round. The unknown id shows the `Task #999 not found` page, not a traceback.
- Injected `<script>` and `<img onerror>` in title, verdict body, and approver body render as escaped text.
- Chip popover: clicking `sec ✗` opens the `security · CHANGES` popover with the rendered body; Escape closes it; focus returns to the chip.
- Light and dark both follow the system setting. Dark screenshots show readable text, muted text, and the popover border.
- Visible keyboard focus ring on the Review link.
- Live part: the `#live` wrapper has `hx-trigger="every 3s [...]"` with the `details[open]` and `:popover-open` filter. Polls run about every 3 s. With a popover open, no polls ran over 7 s; they resumed after Escape. This is the Q10 ceiling the spec accepts.
- Board card links (`/tasks/1`, `/tasks/2`, `/tasks/3`) are present on `/projects/1`.
- Console: the only error on task pages is the existing favicon 404 (and the 404 for the unknown id, which is the expected response). No console errors from the task page itself.

## Nits (non-blocking)
- The round rows are `<p class="round-row">` with `<span>` and `<button>` children; the empty-state line `No build notes.` is a `<p class="muted">`. Both read fine; no change needed.
- Task 2 (backlog) and task 3 (escalated) use the same `[popover]` styles only when a verdict exists, so their popover styling was not exercised visually. The CSS is shared with task 1, where it renders correctly.
