# Review: #56 Clear Loop Create, Active, and History Workspaces

## Executive Summary

- **Verdict:** REVISE.
- Revision 1 correctly moves browser-history ownership into `dashboard.js`, eliminates the view-local `popstate` listener, and adds the required cross-view Back/Forward test path.
- The remaining gap is repository restoration: the state records `repo` and `repoKey`, but the described `showView(view, repo, repoKey, opts)` path does not apply them for a Loop (or Docs) route.
- Without an explicit shell-state hydration step, Back can remount a recorded Loop sub-state against whichever repository is currently active.
- Add repository hydration and a cross-repository history test; then the plan will be ready for implementation.

## Verdict

REVISE — the history architecture is now sound in principle, but the restoration contract must bind the saved Loop state to its saved repository before dispatching the target view.

## Findings

### Finding 1: Popstate restoration does not establish the recorded repository for Loop entries

**Severity**: High

**Location**: Approach, “Shell-owned browser history,” especially the `popstate` branch that calls `showView(view, repo, repoKey, {initialSub: sub})`.

**Issue**: In the current shell, `showView(name, extra, repoKeyOverride)` updates `state.activeRepo` and `state.activeRepoKey` only in its `name === "repo"` branch. Its `loop` branch instead reads the existing `state.activeRepo` / `state.activeRepoKey`. The revision records the desired `repo` and `repoKey`, but does not specify that popstate hydrates those fields before calling `showView` for `view === "loop"`. Therefore, after navigating to a different repository, Back to a Loop entry can fetch and display the saved `loopId` against the wrong active repository (or fail to find it), while also leaving the Repo sidebar label stale.

**Suggestion**: Define one shell helper that restores repository context from a validated history state before any view dispatch, including Loop and Docs: set `state.activeRepo` and `state.activeRepoKey`, update the repo navigation label consistently, and then call `showView` with the Loop `initialSub`. Keep `showView` as a renderer/lifecycle transition, not an implicit partial state-restorer. Cover both same-repository and cross-repository cases: enter a Loop history selection for repository A, navigate to repository B, then Back and assert the Loop APIs, heading, selected card, and shell repository label all refer to A. Keep the no-token assertion over every history state.

## Scope Check

The revised plan remains within the approved Dashboard scope and directly addresses the first review finding. Context and checkpoints remain credible and responsibility-based. This finding only completes the stated shell-owned history contract; it does not request a new endpoint, a loop semantic change, or URL routing.

## What Looks Good

- `GatorShell` gives Loop a narrow sub-state seam without returning global listener ownership to the view.
- The explicit restore guard and no-push restoration path prevent Back/Forward from growing the stack.
- The plan continues to keep history state free of role credentials, prompts, and artifact content.
