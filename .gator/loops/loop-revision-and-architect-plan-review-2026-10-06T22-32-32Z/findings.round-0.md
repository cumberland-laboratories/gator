# Review: Revision Planning and Reviewer-Gated Architect Plans

## Executive Summary

- **Verdict:** REVISE; the plan is strong but has one concrete verifier-design gap.
- The lifecycle, provenance blocks, source locking, atomic rollback, role handoff, Dashboard surfaces, and checkpoint boundaries align well with the sketch.
- The proposed fixed-artifact verification currently reuses a helper whose allowlist only accepts the two existing Architect-brief filenames.
- The plan must specify how the new plan/baseline artifact names enter the generic verifier without weakening the existing brief contract.

## Verdict

REVISE

Address Finding 1, then resubmit the plan. The rest of the plan is sufficiently concrete for implementation planning.

## Findings

### Finding 1: Define the fixed-artifact verifier boundary

**Severity**: High

**Location**: Changes 1, 3, 6, and 9; the `verify_fixed_artifact` / `fixed_artifact_view` design

**Issue**: The plan says `verify_fixed_artifact` will be “an alias of `verify_brief`,” but the current `verify_brief()` implementation rejects any `expected_name` not in `BRIEF_NAMES`, and `BRIEF_NAMES` currently contains only `architect-brief.md` and `source-architect-brief.md`. The proposed names `architect-plan.md`, `revision-baseline-plan.md`, and `revision-baseline-approval.md` would therefore return `invalid_ref` rather than verify. The plan also says `brief_status_view` should generalize through the new helper, so an alias is not enough to preserve the existing brief-only allowlist and support the new fixed artifacts.

**Suggestion**: Specify a generic, fixed-name verifier/view with an explicit allowlist containing the existing brief names plus the three new immutable artifact names, while retaining `verify_brief` and `brief_status_view` as brief-scoped compatibility wrappers. State which helper owns the allowlist, fixed-path safety, size bound, and status codes, and add focused tests proving all three new names verify, unknown names fail closed, and existing brief behavior remains unchanged.

## Scope Check

The plan covers both required lifecycle paths, keeps Architect plans unapproved until Reviewer action, preserves source-loop immutability, and addresses CLI, protocol, Dashboard, artifact access, and feature-prefill surfaces. Its `Context Checked` section names the relevant charters, code, prior artifact, protocol, and tests. The three coding checkpoints are responsibility-based and independently verifiable. This finding is within the approved scope and concerns a prerequisite for the stated digest/integrity contract.

## What Looks Good

- The plan explicitly rejects direct Architect-plan-to-coding and fabricated Draftor turns.
- The source-loop lock and byte-equality checks give the revision path a clear evidence boundary.
- The proposed tests cover lifecycle, atomic rejection, tampering, legacy projection, Dashboard API/UI, and drift guards.
