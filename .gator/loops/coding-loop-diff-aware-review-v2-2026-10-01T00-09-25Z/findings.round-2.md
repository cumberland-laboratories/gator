# Review: Coding Loop with Diff-Aware Implementation Review (#41) — Revision 2

## Executive Summary

- **Verdict: REVISE.** The revision now properly restores host liveness on reopen, preserves legacy planning-loop compatibility, and makes state categorization mode-aware.
- One remaining transition is unspecified: the existing `extend` path is planning-specific and would otherwise resume a coding loop at `plan_revision`.
- Define the mode-indexed extension target and cover the resulting coding-loop continuation test.
- This is a contained correction; with it, the plan is implementation-ready.

## Verdict

**REVISE**

## Findings

1. **Medium — max-round extension needs an explicit coding-mode target transition.**
   - **Location:** Assumptions/Risks ("coding-mode `max_rounds_exceeded` stays extendable via the existing #39 `extend`"); Change 1 mode-indexed state table.
   - **Issue:** The existing #39 extension transition is defined for planning as `max_rounds_exceeded -> plan_revision`. The plan says coding mode remains extendable but does not specify a mode-indexed extension target or name the update to the existing extension transition. Without it, extending a coding loop will either enter an invalid planning stage or retain a planning-only hard-code.
   - **Suggestion:** Add an `extension_resume_stage(mode)` entry to the same `STAGES` transition table: `plan_revision` for planning and `implementation_revision` for coding. Have `handle_extend` use it, set the Draftor deadline/role through the mode-aware helpers, and add an end-to-end test that a coding loop at its round limit extends into `implementation_revision` and accepts a new implementation submission.

## Scope Check

The plan remains within the approved coding-loop MVP. This finding only makes the existing promise to reuse #39's bounded continuation behavior valid for the new coding state machine.
