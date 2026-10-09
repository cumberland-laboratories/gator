# Review: #56 Clear Loop Create, Active, and History Workspaces

## Executive Summary

- **Verdict:** REVISE.
- The plan maps the requested Create/History split, visible mode labels, and recovery disclosure to the right existing Dashboard seams.
- The mode projection correctly avoids feature-name inference and uses an additive list field to retain the legacy distinction.
- The browser-history design is not ready: loop-local entries are added to the browser's global history, but their listener is removed when the user leaves the Loop view, so Back/Forward cannot reliably restore the recorded state.
- Revise the plan to assign cross-view history ownership and cover the sequence that leaves Loop before using Back/Forward.

## Verdict

REVISE — the proposed UI behavior is well scoped, but its Back/Forward mechanism needs an explicit, Dashboard-wide lifecycle before implementation can safely proceed.

## Findings

### Finding 1: Loop-local browser history has no owner after leaving the Loop view

**Severity**: High

**Location**: Approach, “Loop-local navigation” / Change 2 / `test_loop_back_forward`.

**Issue**: The plan calls `history.pushState()` for Loop interactions, then registers `popstate` only while the Loop view is mounted and removes that listener in `teardownLoopView()`. `dashboard.js` has no browser-history router or `popstate` handler. If the user makes Loop selections, navigates to Fleet or Commits, and presses Back, the browser can land on a stored `gatorLoop` state while no code restores the Loop view. The visible view therefore remains the later non-Loop view instead of restoring the requested Loop tab/card. This is more than the stated “extra presses” limitation; it leaves global history entries without an active owner and does not satisfy the sketch's Back/Forward requirement.

**Suggestion**: Revise the design so `dashboard.js` owns browser history and `popstate` for all Dashboard views, with a state shape that identifies the primary view/repository plus optional Loop-local state; or define an equivalent shell-level delegation contract that remounts Loop before invoking its restore routine. Specify how Loop contributes state without overwriting other Dashboard state, how the handler avoids new `pushState` calls during restoration, and how teardown removes only Loop-local resources rather than the sole history router. Add an end-to-end test for: select a historical loop, leave to Commits (or Fleet), press Back to restore the historical Loop selection, then Forward to restore the later view. Preserve the existing no-token rule in every state object.

## Scope Check

The plan stays within the sketch's Dashboard-only scope: it preserves token, stage, liveness, and checkpoint semantics; retains the active workspace and terminal evidence; and renames only the global commit-history label. Its Context Checked section is credible: it names the required Dashboard UI/server and loop charters plus the relevant source and tests. The three checkpoints are responsibility-based and independently reviewable. The navigation checkpoint needs the revision above before it can be considered verifiable.

## What Looks Good

- `mode_legacy` is an appropriately small additive list projection, while the status view can retain its raw mode for the central normalization function.
- The recovery rule explicitly protects joined `not_registered` participants, which honors the #52 constraint.
- The plan keeps terminal loops out of recovery controls and preserves artifact rendering in the Loop workspace.
