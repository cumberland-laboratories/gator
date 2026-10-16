# Review: #70 — Windows Dashboard UI flakes, diagnosis and shared readiness

## Executive Summary

- **REVISE.** The plan has a strong diagnostic design, preserves the child-process harness, and correctly avoids timeout/rerun/concurrency speculation.
- It nevertheless schedules Slice 2 before Slice 1 has produced the evidence that the sketch makes a prerequisite; coding checkpoints do not create an evidence-review gate.
- Its stated migration inventory is materially incomplete: the named files contain many additional direct `?repo=`/`.repo-file-item` setup pairs, and other Dashboard UI modules use the same pattern.
- The failure-bundle design needs a defined fixture-lifecycle and failure-phase path, plus a correction to the invalid diagnostic-dictionary composition, before it is safe to implement.

## Verdict

REVISE

The plan is directionally sound but is not ready to implement as written because it crosses the sketch's evidence gate and leaves key diagnostic and migration behavior underspecified.

## Findings

### Finding 1: Slice 2 is scheduled before its required evidence gate

**Severity**: High

**Location**: Executive Summary; Approach; Assumptions, Risks, and Required Architect Decisions; Coding Checkpoints 2–3

**Issue**: The sketch says that the shared rendered-ready helper is introduced *after Slice 1 confirms the broad failure class*. The plan instead implements it in the same coding loop under a non-blocking assumption. A coding-loop checkpoint is an implementation-review boundary, not a Windows-CI observation or an Architect decision gate; “stop after checkpoint 2” has no deterministic trigger and would leave an approved plan authorizing a speculative Slice 2.

**Suggestion**: Limit this plan to Slice 1 and specify the evidence review/next-loop handoff that selects the Slice 2 predicate. Alternatively, obtain an explicit Architect decision to change the sketch's sequence. Do not make the sequencing change an implementer assumption.

### Finding 2: The proposed migration inventory is not complete or mechanically bounded

**Severity**: High

**Location**: Context Checked call-site inventory; Change 6; Coding Checkpoint 3

**Issue**: The plan claims a limited list of repeated setup pairs, but the inspected sources contain substantially more. For example, `test_loop_workspace.py` has direct pairs beyond the four called out (including lines 61, 323, 355, 1004, 1025, 1049, 1064, 1608, 2621, 3015, and 3091), and `test_responsive_shell.py` has existing wrapper helpers plus other direct setup paths. `test_html_preview.py` and `test_syntax_highlight.py` also use the same direct repo-open setup. Leaving the selection as “the coding loop greps the exact list again” shifts a material scope/design decision into implementation and makes the checkpoint unreviewable.

**Suggestion**: Define the migration set now using a precise semantic rule (which direct repo-open setup paths are in scope and which intentionally assert pre-ready/transition state), list all affected helper modules/files, and add a focused static or parameterized regression check if that is the intended no-new-ad-hoc-waits invariant. If only historically failing paths are intended, enumerate them and explain why other matches are excluded.

### Finding 3: Failure-bundle capture has no reliable fixture-order and phase contract

**Severity**: Medium

**Location**: Changes 3–4; Testing “Induced-failure test”

**Issue**: The proposed autouse fixture must both attach listeners before the test and snapshot the page before pytest-playwright tears down the `page`/context. The plan does not state the dependency/finalizer ordering that guarantees this, nor how setup failures (including a Dashboard fleet fixture failure before a usable `page`) are represented. Without that contract, the “next Windows failure” can still lose the page snapshot, browser events, or child output that Slice 1 is meant to preserve.

**Suggestion**: Specify the fixture dependency and teardown order explicitly, record whether setup/call/teardown failed, and define a graceful server-only/no-page bundle for failures before page creation. The induced-failure coverage should exercise at least a call-phase failure and a setup-phase/no-page path, and assert bounded, publish-safe output in both.

### Finding 4: The readiness timeout path is not implementable as written

**Severity**: Medium

**Location**: Change 5, step 3

**Issue**: `browser_diagnostics(page) + server_diagnostics(fleet)` is not valid Python for two dictionaries. More importantly, the plan has not defined the merged schema that will be serialized, so an implementer must make a design choice in the exception path.

**Suggestion**: Define a stable, bounded payload shape such as `{\"browser\": ..., \"server\": ...}` and require the helper to catch the relevant Playwright timeout exception while preserving the original failure as context. Pin that schema in the timeout test.

### Finding 5: Required planning procedure was not applied or recorded

**Severity**: Low

**Location**: Context Checked and Approach

**Issue**: The repository provides `.gator/procedures/writing-implementation-plans.md`, which requires choosing and stating the planning path, module map, simplicity boundary, and focused-versus-broad verification ladder. It is absent from Context Checked and the Approach does not make those decisions explicit. The current checkpoints also put full cross-platform suite execution inside a checkpoint instead of clearly deferring the broad run to final coding-loop approval.

**Suggestion**: Read and cite the procedure, state why a full planning loop is proportionate, describe the responsibility map and simplicity boundary, and adjust the verification ladder so checkpoint checks are focused while the full Dashboard UI suite is the final integrated regression (unless a concrete cross-cutting reason requires it earlier).

## Scope Check

The plan respects the explicit non-goals on timeout increases, reruns, threaded-server changes, and real-harness isolation. Its Context Checked list is credible for the workflow, Dashboard UI contract, harness, fixtures, and several call sites, but incomplete for the repository-required planning procedure and for the full migration surface it proposes to change. The three checkpoints are responsibility-based in title, but checkpoints 2–3 violate the sketch's mandatory evidence sequencing; they cannot be approved as independent increments until the Slice 1 evidence gate is resolved.

## What Looks Good

- Failure-only trace, screenshot, CI upload, bounded output, and synthetic-data constraints align well with Slice 1.
- The plan correctly treats the “132 elements” observation as a hypothesis rather than a confirmed cause.
- The Release Pipeline charter impact and no-timeout-increase stance are appropriately explicit.
