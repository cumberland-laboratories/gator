# Expected Governance Residue

After a successful `git commit` in a Gator-governed repo, `git status` may still show changes in:

- `.gator/commit_draft.md`
- `.gator/whiteboard.md`

This is expected.

## Why it happens

Gator's commit hooks intentionally rotate these files as part of the governance loop:

- `commit_draft.md` is reset to its stub so the next session starts fresh
- `whiteboard.md` is cleared after successful hook processing unless findings need to remain visible

These edits are not unfinished product work. They are post-commit housekeeping performed by the Gator hooks.

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
