# Review: Coding Loop with Diff-Aware Implementation Review (#41) — Revision 1

## Executive Summary

- **Verdict: REVISE.** Revision 1 fully addresses the prior approval-resolution, reopen semantics, snapshot contract, raw-tree, and source-integrity findings.
- The new `reopen` transition must also revive the host/watch lifecycle; a session-only mutation after terminal approval cannot deliver a new Draftor turn.
- Coding mode must treat absent legacy `session.mode` as `planning`, or existing approved planning loops cannot be used as successors despite the stated compatibility goal.
- With those two details made explicit and tested, the plan is ready to implement. The six-module shape and test scope remain appropriate.

## Verdict

**REVISE**

## Findings

1. **High — reopening a terminal coding loop needs host/watcher reactivation, not only a session transition.**
   - **Location:** Change 1, `handle_reopen`; Change 5, POST `/reopen`.
   - **Issue:** `implementation_approved` is terminal, so the loop host/watch process will already have exited. Calling a session-level `handle_reopen` can set `implementation_revision`, but no active host necessarily remains to observe timeouts, watchers, or turn delivery. Existing `extend` has a host-level lifecycle wrapper and single-active-loop guard for precisely this reason.
   - **Suggestion:** Define a host-level `reopen_loop()` counterpart to `extend_loop()`: acquire the start lock, enforce the one-active-loop rule, perform the locked reopen transition, acquire/start the host watcher, and route both CLI and Dashboard through it. Include recovery behavior if host startup fails after transition, plus a test that an approved loop reopened from a fresh process becomes live and can receive the Draftor submission.

2. **Medium — legacy planning sessions need an implicit planning-mode default during source validation.**
   - **Location:** Change 1, Start step 3.
   - **Issue:** The required check says `mode == "planning"`, but all pre-coding-loop session files lack a `mode` key. Such historically approved planning loops would be rejected as sources, contradicting the plan's backwards-compatibility objective and the desired “start from an approved plan loop” workflow.
   - **Suggestion:** Specify and centralize `session.get("mode", "planning")` everywhere mode is read, including guarded-source validation, state categorization/action dispatch, and Dashboard projection. Add a fixture for a mode-less approved legacy session that successfully starts a coding successor.

3. **Medium — state categorization must be mode-aware, not only action validation.**
   - **Location:** Change 1.
   - **Issue:** The current implementation's active/paused/terminal categorization is based on global stage sets. Adding coding stages only to `validate_action()` would leave host timeout handling, status, active-loop detection, and terminal checks unable to recognize coding stages consistently.
   - **Suggestion:** State explicitly that `is_active`, `is_paused`, `is_terminal`, and any stage-to-role/deadline helpers dispatch by normalized mode (or use a mode-indexed transition table), with planning behavior preserved byte-for-byte. Cover coding timeout and active-loop exclusion in tests.

## Scope Check

The revised plan remains inside the sketch: governed coding review bound to the raw staged tree, a manual ordinary commit, and Dashboard visibility. The requested lifecycle wiring and legacy default are necessary to make that approved scope function; they do not add a commit wrapper or unrelated loop feature.

## Test Guidance

Keep the prior end-to-end committed/pending/stale/reopen tests. Add: a reopen invoked after the original host has exited, verified to restart liveness and accept the next Draftor artifact; a failed host-start rollback/recovery case; a mode-less legacy planning source; and coding-stage timeout/one-active-loop coverage.
