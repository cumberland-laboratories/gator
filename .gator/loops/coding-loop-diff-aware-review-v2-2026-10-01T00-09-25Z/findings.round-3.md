# Review: Coding Loop with Diff-Aware Implementation Review (#41) — Revision 3

## Executive Summary

- **Verdict: APPROVE.** The plan defines a separate, backward-compatible coding-loop mode with Git facts—not prose—as the review authority.
- It has a complete lifecycle: guarded successor start, bound implementation generations, pending/committed/stale resolution, Architect-only reopen, and mode-aware round-limit extension.
- The manual single-commit handoff remains intact; no commit wrapper, hook bypass, or per-round commit is introduced.
- The six implementation areas and targeted unit, end-to-end, recovery, Dashboard, and planning-regression coverage are proportionate to the feature's risks.

## Verdict

**APPROVE**

## Approval Basis

1. **Scope and compatibility.** Coding mode is explicitly opt-in and can begin only from a verified approved planning loop. `loop_mode()` defaults historical sessions to planning, and the mode-indexed state table preserves existing planning semantics.
2. **Review integrity.** The raw staged-tree OID, current/head tree facts, and raw changed paths are captured by the CLI and persisted per generation. The review/approval check refreshes those facts, preventing prose-only or stale-tree approval.
3. **Commit lifecycle.** Resolution distinguishes a pending candidate from a normal committed approved tree and from a stale candidate. The Architect-only host-level reopen operation supplies the required route back to implementation review without using a Git wrapper.
4. **Operational lifecycle.** Reopen and extension have host/watcher recovery and one-active-loop behavior defined. Coding-mode extension resumes at `implementation_revision`, rather than leaking into planning stages.
5. **Verification.** The plan includes the material failure cases: Git/index conditions, branch/tree changes, reopen after host exit, source validation, legacy sessions, mode-aware timeout/terminal handling, Dashboard authority, and unchanged planning behavior.

## Scope Check

The plan stays within the approved #41 sketch: optional governed implementation review against the candidate tree, clear Dashboard state, and an ordinary post-approval commit by the Draftor. It deliberately excludes per-round commits, a `gator loop commit` workflow, hook bypasses, and general CI/merge-queue functionality.

## Implementation Notes

Implement the mode-indexed state-table helpers before adding coding submissions so every caller shares the same lifecycle classification. Preserve raw Git facts alongside any display formatting, and ensure the final integration tests exercise a fresh process for both reopen and extension watcher adoption.
