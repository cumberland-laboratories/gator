# Expected Governance Residue

Current Gator installs ignore these hook-state files, and the hooks write
them to the working tree only (they never stage them), so they normally do
not appear in `git status`. This note also covers legacy repositories that
still track them; there the hook writes appear as modifications. Run
`gator update` once: it removes the tracked copies from the Git index
(the files stay on disk), stages that deletion, and lists the paths. Commit
the deletion with the update.

After a successful `git commit` in a Gator-governed repo, `git status` may still show changes in:

- `.gator/commit_draft.md`
- `.gator/whiteboard.md`

This is expected.

## Why it happens

Gator's commit hooks intentionally rotate these files as part of the governance loop:

- `commit_draft.md` is reset to its stub so the next session starts fresh
- `whiteboard.md` is cleared after successful hook processing unless findings need to remain visible

These edits are not unfinished product work. They are post-commit housekeeping performed by the Gator hooks.

## Other hook files you may see

- `.gator/status.json` and `.gator/commit_issues.md` hold the last attempt's check results and lint findings. They are gitignored and never staged.
- If a hook file is staged by accident (for example by `git add -A`), the pre-commit hook removes it from that commit attempt and prints "Removed generated hook files from this commit attempt." A staged *deletion* of a hook file is kept: it is the `gator update` migration.
- Override state (the block, the approval, and the handoff) lives in `.git/gator-override/`. It is outside the working tree, so it never shows up in `git status`. Inspect it with `gator hook override status`.
- The retired v1 override files (`.gator/.override`, `override-request.json`, `override-approved.json`, `.override-meta.json`) are gitignored, and are removed after the next successful commit. Never create or stage them. `.override` blocks the commit.

## How to interpret it

Treat these files differently from ordinary source changes.

If a successful commit just happened and the only modified tracked files are:

- `.gator/commit_draft.md`
- `.gator/whiteboard.md`

then the repo is in an **expected governance residue** state, not a meaningfully dirty worktree.

## What agents should do

- Do not treat this state as evidence that the last commit failed.
- Do not "clean up" these files unless the Architect asks.
- Distinguish governance residue from substantive uncommitted code or docs changes.
- If asked whether the repo is clean, explain that the remaining changes are expected Gator hook residue.

## Why this matters

Without this distinction, agents may:

- misreport repo state
- hesitate unnecessarily before continuing work
- try to revert or overwrite files that the hook system intentionally rotated
- confuse governance housekeeping with unfinished development work

The right model is:

**visually dirty, semantically clean**

for these specific post-commit Gator files.
