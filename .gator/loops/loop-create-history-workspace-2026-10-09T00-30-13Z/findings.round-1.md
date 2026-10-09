# Review: #56 Loop Create/History workspaces — Checkpoint 2 (Loop navigation, shell-owned history and Commits label)

## Executive Summary

- **Verdict:** REVISE checkpoint 2 of 3.
- The shell-owned history design, repository hydration, active-loop explanation, and Commits rename are all aligned with the approved plan.
- The Loop sub-state loses the selected tab for an inspected active loop: restoring a recorded History-tab entry forces the Create tab from the loop stage.
- This makes Back/Forward fail to restore a valid user tab selection and is not covered by the submitted history tests.
- Preserve a valid recorded `sub.view` independently of whether the selected loop is terminal, and add the active-loop tab round-trip test.

## Verdict

REVISE — correct the Loop sub-state restoration before approving this checkpoint.

## Findings

### Finding 1: Restoring an inspected active loop discards the recorded History tab

**Severity**: Medium

**Location**: `src/gator_command/scripts/dashboard/views/loop.js`, `currentSub()` / `switchTab()` / `applySub()`.

**Issue**: Selecting the History tab while an active loop remains inspected creates a valid shell entry with `{view: "history", mode: "inspect", loopId: <active>}`: `switchTab()` changes only `_state.view`, as intended. On Back/Forward, however, `applySub()` ignores `sub.view` whenever `sub.mode === "inspect"` and derives `_state.view` exclusively from `isTerminal(loop.stage)`. For the active loop that forces `create`, so the restored state does not match the entry that was pushed. This violates the plan’s user-selection/history contract and can leave the browser history UI inconsistent with the rendered tab.

**Suggestion**: When the recorded sub-state is valid, preserve its validated `view` (`create` or `history`) for both inspect and create modes; use the loop stage only for an absent/invalid sub-state or as a deliberate compatibility fallback. Add a focused Playwright round-trip: with the default active loop inspected, switch to History, navigate away (or Back/Forward within Loop), then assert the History tab remains selected while the active-loop main content is still intact. Keep the existing terminal-history selection tests.

## Scope Check

The candidate otherwise stays inside checkpoint 2: it adds the requested local navigation and shell history without changing loop protocol semantics, token handling, or server contracts. The charter update and test coverage are substantive. The missing active-inspect tab-restoration case is a navigation correctness gap, not a request for extra scope.

## What Looks Good

- Repository hydration occurs before dispatch and the same-repository fast path checks the mounted Loop key.
- `cleanSub()` restricts history payloads to the intended token-free shape.
- The tablist is preserved across polling, and the `history.js` detached-loading-node guard prevents a late commits response from overwriting a restored Loop workspace.

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | REVISE |
| Reviewed staged tree | `b3fdd094276482b5a8d7cbb72df409380d8eefec` |
| Reviewed HEAD | `34a9d0e417d431853181de99088547a9fce86698` |
| Candidate round | 0 |
| Checkpoint | cp2 (2 of 3) — Loop navigation, shell-owned history and Commits label |
| Checkpoint base tree | `b0e992c03ff4d4ca966405b433857c6bd8d20239` |
| Generation | 1 |
| Live candidate unchanged at review | yes |
