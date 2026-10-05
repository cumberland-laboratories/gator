# Review: Coding Loop with Diff-Aware Implementation Review (#41)

## Executive Summary

- **Verdict: REVISE.** The mode separation, Git-owned binding data, and one-normal-commit boundary follow the sketch well.
- Two lifecycle rules are incomplete: a normal successful commit would be reported as stale, and a changed candidate after approval has no permitted way back into review.
- The Git snapshot contract needs one precise base-aware interface and an explicit policy for hook-managed paths; otherwise different consumers can bind different candidates.
- These are contained design corrections. The plan's module count and proposed test categories are proportionate once the lifecycle contract is fixed.

## Verdict

**REVISE**

## Findings

1. **High — post-approval normal commits are indistinguishable from stale approvals.**
   - **Location:** Changes 4, Dashboard; Assumptions/Risks ("approval is terminal").
   - **Issue:** Approval binds both the staged-tree OID and `reviewed_head`. The normal commit explicitly required by the workflow changes `HEAD`, so the proposed terminal-status snapshot will label a successfully committed approved tree as `STALE`. The Dashboard handoff therefore turns into a false failure state.
   - **Suggestion:** Specify a post-approval resolution state in the snapshot/status contract. For example, if `HEAD^{tree}` equals `reviewed_tree`, record/display the resulting ordinary commit as a successful handoff; reserve `STALE` for an uncommitted candidate whose staged tree or pre-commit HEAD no longer matches. Define detached-HEAD behavior and a nonmatching commit explicitly.

2. **High — the plan requires a re-review path after approval but supplies no legal transition.**
   - **Location:** Summary, Change 4, and Assumptions/Risks.
   - **Issue:** The sketch requires code changed after approval to return to implementation review. The plan makes `implementation_approved` terminal, while the existing `extend` action only revives `max_rounds_exceeded`; it then says the Architect uses `extend` to reopen approval. That cannot work under the current state-machine contract.
   - **Suggestion:** Choose and specify one bounded recovery mechanism: an Architect-only `reopen` transition from `implementation_approved` to `implementation_revision`, or a clearly defined successor coding loop. Include its audit event, role/round behavior, stale-approval invalidation, Dashboard affordance, and tests. Do not reuse `extend` unless its eligibility and semantics are deliberately expanded.

3. **Medium — the Git snapshot interface is underspecified and internally inconsistent.**
   - **Location:** Change 2.
   - **Issue:** `snapshot(repo_root)` has no `base_head` input, yet the listed changed-path command depends on `<base>`. Consumers also need an explicit distinction between repository root, Git worktree root, and the captured base/current HEAD values to avoid a worktree or branch movement producing inconsistent facts.
   - **Suggestion:** Define a single typed snapshot input/output contract, e.g. `snapshot(worktree_root, base_head)`, and document each field's command and failure behavior. Use the captured `base_head` for changed paths and persist exactly the returned raw facts.

4. **Medium — excluding hook-managed paths from the binding weakens the stated tree-authority invariant without a defined replacement.**
   - **Location:** Assumptions/Risks (hook-managed `.gator/` files).
   - **Issue:** The plan says the exact staged tree is authoritative, then proposes excluding paths from stale comparison. That can approve a different tree from the tree the Reviewer inspected, and it does not say whether the artifact, changed-path display, or approval record uses raw or filtered values.
   - **Suggestion:** Keep the raw staged-tree OID and raw changed paths authoritative. Either capture the candidate after the relevant hooks have produced their files, or define a narrowly scoped, independently tested normalization policy with separate raw and normalized identifiers. The MVP should prefer the former if possible.

5. **Medium — guarded successor validation needs an explicit integrity and failure contract.**
   - **Location:** Approach question 2 and Changes 1/3.
   - **Issue:** `--from-loop` is correctly limited to an approved planning loop, but the plan does not state how the source loop ID is validated, how missing/corrupt `plan.current.md` is handled, or when the immutable copy and digest are written relative to session creation.
   - **Suggestion:** Validate a canonical local loop ID and source session mode/stage under the source read/lock discipline; copy then hash the approved plan before publishing the new coding session. Fail atomically with a clear error if any source invariant fails. Add rejection tests for non-approved, coding-mode, missing-plan, and digest-mismatch cases.

## Scope Check

The plan stays within the approved sketch: optional coding mode, Git-tree-bound review, Dashboard visibility, and a manual ordinary commit. It correctly excludes per-round commits, a Gator commit wrapper, and a CI/merge-queue expansion. The requested revisions clarify the specified lifecycle rather than extending scope.

## Test Guidance

Retain the proposed regression, helper, CLI, recovery, and Dashboard coverage. Add focused end-to-end cases for: (1) approved tree followed by the intended ordinary commit, which is displayed as successful rather than stale; (2) an uncommitted post-approval tree/HEAD change followed by the selected reopen/successor route; and (3) raw versus any normalized hook-managed binding facts. The worktree/conflict cases are worthwhile only if `gitsnap` promises those environments in this MVP; otherwise explicitly reject them and test those errors.
