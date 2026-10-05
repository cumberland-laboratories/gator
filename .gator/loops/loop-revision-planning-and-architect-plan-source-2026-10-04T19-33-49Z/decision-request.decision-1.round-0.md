# Decision Request: Unrelated uncommitted work overlaps the #51 candidate files

## Decision Needed

How should the Draftor isolate the #51 implementation from separate, unfinished work that is already uncommitted in the same files? The staged tree is the reviewed and approved candidate, so this must be settled before any file is edited or staged.

## Context

`git status` at loop start (HEAD `c1a5d4d`, "Bump to 2.21.0") shows uncommitted modifications that belong to a different change. That change is the "Loop timeline cards are link-only" follow-on to #45, plus a new untracked `.gator/procedures/writing-implementation-plans.md` and a planning-guidance bullet that points to it. It is described in the `[Unreleased]` CHANGELOG entry and the modified UI charter.

These files carry that work **and** must also be edited by the approved #51 plan:

| File | Pending unrelated change | #51 needs to edit it |
|---|---|---|
| `src/gator_command/scripts/dashboard/views/loop.js` | timeline link-only (+/- 83 lines) | create form, controls, inspector, coding region |
| `src/gator_command/scripts/dashboard/dashboard.css` | timeline summary styles removed | `.loop-card-source` |
| `.gator/charters/scripts-dashboard-ui.md` | timeline and summary tripwires rewritten | create form, revision action, inspector |
| `.gator/.includes/reference-notes/loop-artifact-formats.md` and the template copy | new "writing-implementation-plans" bullet | Revision Sketch template |
| `CHANGELOG.md` | `[Unreleased]` timeline entry | #51 entry |
| `.gator/commit_draft.md` | draft for the timeline change | #51 draft |

Also modified, but not touched by #51: `tests/test_dashboard_ui/test_loop_workspace.py`, `.gator/inbox.md`, `.gitignore`, `.gator/.gator-version`, `.gator/runtime-pin.json`.

Interactive partial staging (`git add -p`) is not available in this environment. Staging a whole file would put the timeline change into the #51 candidate, and the Reviewer would be reviewing, and the commit would contain, two unrelated features.

## Options Considered

1. **Commit the timeline follow-on first** (Architect or its own session), then resume. The #51 base becomes that commit, and the candidate contains only #51. This is the cleanest review and history. It needs the loop's Git base to be current: the base was captured at loop start (`c1a5d4d`). A new commit moves HEAD, and the candidate diff is computed against the captured `base_tree`, so the Reviewer's `git diff <base_tree> <staged_tree>` would then include the timeline commit too. The Architect would need to restart this coding loop from the same approved plan, so a new base is captured after that commit.
2. **Stash the timeline work, implement #51 on the clean tree, then unstash after the #51 commit.** This keeps the current base valid. Reapplying the stash may conflict in `loop.js`, the UI charter and the CHANGELOG, which the Architect or a later session resolves.
3. **Fold the timeline change into this candidate.** No setup is needed, but the Reviewer reviews unrelated work outside the approved plan, which breaks the sketch scope boundary. Not recommended.
4. **The Draftor builds a #51-only index without interactive staging** (`git apply --cached` of #51-only hunks for the overlapping files). This is possible but fragile, error-prone across six shared files, and it leaves a working tree that differs from the candidate in reviewed files. Not recommended.

## Recommendation

**Option 2 (stash), done by the Architect or with the Architect's explicit authorization.** It keeps this loop's captured base valid, gives a #51-only candidate, and needs no loop restart. Option 1 is equally clean if the Architect would rather land the timeline change first; it needs a restarted coding loop.

The Draftor will not stash, commit or discard the Architect's uncommitted work without explicit direction.

## Consequence of Delay

The loop stays blocked. No files have been edited and nothing is staged.
