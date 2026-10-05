# Implementation Plan: Coding Loop with Diff-Aware Implementation Review (#41)

## Executive Summary

- **What.** Add an optional coding mode, `session.mode = "coding"`, started with `gator loop start --mode coding --from-loop <approved-plan-loop>`. The Draftor stages code and submits `implementation.round-N.md`. The CLI captures the Git facts. The Reviewer reviews the staged tree, and `APPROVE` binds to that exact tree. The Draftor then makes one ordinary commit under the existing hooks.
- **Key decisions.** Staleness is keyed on the staged-tree OID plus HEAD. Unstaged residue is disclosed but does not block. The plan is referenced by source loop ID plus a SHA-256 digest of an immutable copy. The base is captured at loop start.
- **Main risk.** Planning-loop regressions. Mitigation: mode-gated transitions and the unchanged planning test suite.
- **Verification.** Six modules with unit, CLI, recovery and Dashboard tests.

## Summary

Add a coding mode discriminator to the loop session without changing planning semantics. A new `loop/gitsnap.py` captures authoritative Git facts. Implementation submissions and reviews bind to the staged-tree OID. The Dashboard shows the bindings, a stale-review warning, and the final commit handoff. There is no commit wrapper, no hook bypass, and no per-round commits.

## Approach

**Decisions on the sketch's questions:**
1. **Unstaged residue.** It is disclosed, not blocking. The CLI records `unstaged: true|false` plus the paths, and the Dashboard and review artifact show a prominent warning. Only the staged tree is ever the candidate. The Reviewer may still REVISE because of residue.
2. **Plan reference.** Both. At start, the approved `plan.current.md` from the source loop is copied to `approved-plan.md` in the coding loop, and the session records `{source_loop_id, plan_sha256}`.
3. **Base commit.** Captured at coding-loop start as `base_head`. Every snapshot records `current_head`. When `current_head != base_head`, the Dashboard shows "branch moved since start".
4. **Stale condition.** An approval is stale when the current staged-tree OID differs from `reviewed_tree`, or when HEAD differs from `reviewed_head`. Changed paths are derived data, not a separate key.
5. **Starting a coding loop.** It is a guarded successor. `start --mode coding --from-loop <id>` requires the source to be a planning loop in `plan_approved`. There is no free-form coding start in this MVP.

**Architecture.** `state_machine.py` gains `CODING_ACTIVE_STAGES` (`implementation_drafting`, `implementation_review`, `implementation_revision`) and the terminal `implementation_approved`. `validate_action()` dispatches on `session.get("mode", "planning")`. Existing planning functions are untouched.

## Changes

### 1. Mode and schema (state machine)
- File: `src/gator_command/scripts/loop/session.py`, `state_machine.py`
- What: `create_session(..., mode="planning")` writes `mode`. A coding session adds `coding: {source_loop_id, plan_sha256, base_head, generations: []}`. New `advance_impl_submitted()`, `advance_impl_reviewed(approved)`. Stage sets are extended; `is_terminal` includes `implementation_approved`. `max_rounds_exceeded` keeps its #39 extension for coding (the next stage is `implementation_revision`).
- Why: a mode discriminator without mutating planning semantics.

### 2. Git snapshot helper
- File: new `src/gator_command/scripts/loop/gitsnap.py`
- What: `snapshot(repo_root) -> {ok, head, staged_tree, changed_paths, unstaged_paths, error}`. It uses `git rev-parse HEAD` (unborn repos give an error), `git write-tree` (fails on an unmerged index, reported as a `conflict` error), `git diff --cached --name-status <base>`, and `git status --porcelain` for residue. It resolves worktrees with `rev-parse --show-toplevel`. When Git is unavailable it returns `{ok: False, error: "git_unavailable"}`.
- Why: tree authority, failing clearly.

### 3. Implementation submission
- File: `submit.py` (`handle_submit_implementation`), `cli.py` (`submit-implementation`)
- What: validates the artifact headings (Executive Summary, Implementation Summary, Charter Updates, Verification, Commit State). Takes a snapshot, rejecting when `ok` is false or the staged tree equals the base tree (nothing staged). Writes `implementation.round-N.md` and `implementation.current.md`, with the CLI-captured Commit State block inserted or replaced. Appends a generation `{round, staged_tree, head, changed_paths, unstaged_paths}` and emits `implementation_submitted`.
- Why: versioned artifacts and CLI-owned facts.

### 4. Implementation review and staleness
- File: `submit.py` (`handle_submit_review` is mode-aware), `cli.py`
- What: before accepting a review, it takes a fresh snapshot. If the tree or HEAD differs from the latest generation, it rejects with "tree changed since submission; the Draftor must resubmit". Findings record `reviewed_tree` and `reviewed_head`. On APPROVE: `implementation_approved` plus `approval: {tree, head, ts}`. `gator loop status` on an approved coding loop takes a snapshot and prints STALE when it mismatches.
- Why: binding rules and stale detection.

### 5. Dashboard
- File: `gator-dashboard.py` (status allowlist gains `mode` / `coding` bindings), `dashboard/views/loop.js`
- What: a coding header with the round, base/current/reviewed/staged short OIDs, changed-path summary, unstaged warning, verdict, a link to `approved-plan.md`, a stale banner (text plus icon), and an approval handoff card: "Return to the Draftor session for one normal commit". A new GET `/loops/<id>/snapshot` returns a live, read-only, `no-store` stale check.
- Why: visibility.

### 6. Protocol and docs
- File: the protocol pair, `loop-artifact-formats.md` pair (the implementation template), and `/loop-join`
- What: coding-mode participant steps and the commit handoff.

## Dependencies and Ordering

1 → 2 → 3 → 4 → 5 → 6. Module 2 can proceed in parallel with 1.

## Assumptions, Risks, and Required Architect Decisions

- **Non-blocking assumption:** residue discloses rather than blocks (answer 1). This is reversible to blocking with a one-line check.
- **Non-blocking assumption:** approval is terminal (`implementation_approved`). A post-approval change is detected as stale by `status`; the Architect uses `extend` to reopen at `implementation_revision`.
- **Risk:** Windows index locks during a snapshot. Retry once, then report `git_busy`.
- **Risk:** hook-managed `.gator/` files (`commit_draft.md`, `status.json`) change the staged tree during the commit. Mitigation: exclude HOOK_MANAGED_PATHS from the binding, using the #34 `index_tree()` rule for the stale comparison.

## Testing

- **Planning regression:** the existing `tests/test_loop.py` passes unchanged.
- **Unit:** stage transitions per mode, and `gitsnap` in temp repos (clean, staged, unstaged, unborn, conflict, worktree, Git missing).
- **CLI end to end:** clean approval; a tree changed after submission rejects the review; multi-round revision; a post-approval edit shows STALE; restart recovery (a new process reads the generations).
- **Dashboard:** status allowlist, snapshot endpoint, and Playwright tests for the stale banner and handoff card.

## Charter Impact

`scripts-loop.md` (mode, stages, gitsnap, a TRIPWIRE that the tree is authority), `scripts-dashboard.md`, `scripts-dashboard-ui.md`, and the protocol cross-reference.
