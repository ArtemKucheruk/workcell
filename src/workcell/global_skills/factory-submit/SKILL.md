---
name: factory-submit
description: Send this working tree's changes to Workcell for review, as a new task straight in Review or as the next round of one already submitted. Use as "/factory-submit", or "/factory-submit <task-id>" for a new round.
---

# /factory-submit $ARGUMENTS

Submit the changes in this working tree to Workcell for my review.

Never stage, commit, or stash. fctl captures the tree, tracked and untracked files alike,
through a temp index and leaves the real one untouched.

1. Read the changes: `git status`, `git diff HEAD`, and every untracked file `git status`
   lists. Untracked files are submitted too, unless .gitignore'd. Read this conversation for
   why the change was made.
2. New review or next round?
   - `$ARGUMENTS` is a task id N, or earlier in this session fctl printed `Review #N` for this
     same change → the next round of task N: step 4.
   - Otherwise → a new review: step 3.
3. New review. Write a short title, e.g. `Fix open redirect after login`, and a markdown
   description: what changed, why, and which tests you ran with what result, e.g.
   `pytest -q (48 passed)`. Ran none → say so. Pass the description in a quoted heredoc, so
   the shell expands nothing in it. No line of the text may be exactly `EOF`: that ends the
   heredoc early.
   ```
   fctl submit --new --title "<title>" <<'EOF'
   <description>
   EOF
   ```
   Show me the `Review #N: …` line it prints.
4. Next round of task N. Write build notes: what changed since the last round, why, and which
   tests you ran with what result. The heredoc rule of step 3 applies. Then run, with N as
   `<id>`:
   ```
   fctl submit <id> <<'EOF'
   <build notes>
   EOF
   ```
   Show me the `Round <n> of #<id>: …` line it prints.

If fctl fails:
- `404 no project at <path>` → this repo isn't connected. Suggest `/factory-connect <workspace>`,
  then `/factory-submit` again.
- `can't reach … — is "fctl serve" running?` → ask me to start `fctl serve`. Don't start it
  yourself.
- `HEAD has no commit yet` → tell me; the repo needs one commit first. Don't make it yourself.
