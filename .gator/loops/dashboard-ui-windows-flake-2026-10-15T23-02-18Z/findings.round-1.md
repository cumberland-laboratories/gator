# Review: #70 — Windows Dashboard UI flakes, Slice 1

## Executive Summary

- **REVISE.** The revision correctly limits implementation to Slice 1 and creates a real evidence-review handoff before Slice 2.
- The report-hook design now makes the call-phase capture independent of fixture teardown, and the focused verification ladder is proportionate.
- Two details still prevent the bundle from satisfying the sketch as written: it does not record the selected repository key, and its stated total-size cap conflicts with its component bounds.
- Fixing those two closed-schema details should make the plan ready for approval.

## Verdict

REVISE

The sequencing, fixture-lifecycle, and planning-path findings are resolved. The diagnostic schema must be completed and its publication-size contract made internally consistent.

## Findings

### Finding 1: The snapshot omits the selected repository key required by Slice 1

**Severity**: Medium

**Location**: Change 2, `browser_diagnostics(page)`; Testing `test_browser_diagnostics_reports_view_and_survives_closed_page`

**Issue**: The sketch requires the diagnostic bundle to record the selected repository key. The revised plan records the Repo label text but not the key. The Dashboard keeps that identity in shell state (`activeRepoKey`) and writes it to its shell history state as `repoKey`; the label cannot substitute for it where repository identity matters.

**Suggestion**: Add a read-only `selected_repo_key` field to the fixed page-evaluation schema (for example from the current Gator shell history entry), define its unavailable/null behavior, and pin it in the loaded-Repo snapshot test. This does not require a product-side marker.

### Finding 2: The claimed bundle-size bound is impossible under the proposed component caps

**Severity**: Medium

**Location**: Changes 1–4; Publish safety paragraph; Testing `test_failure_bundle_phases`

**Issue**: The plan says each stdout/stderr tail may consume 16 KB per stream, and event capture allows 100 entries × 500 characters (about 50 KB before JSON overhead). Those fields alone can exceed the claimed “about 60 KB” maximum and the proposed `≤64 KB` test assertion, before browser strings or JSON encoding. The artifact is therefore not bounded as specified and the test could be flaky or force an implementer to choose different limits.

**Suggestion**: Set an explicit whole-bundle byte budget and allocate sub-budgets beneath it (including JSON/UTF-8 overhead), or lower the tails/event limits so their sum fits the asserted cap. Define the deterministic truncation order and test it with maximum-size synthetic console and child-output data.

## Scope Check

The plan now stays within Slice 1 and explicitly defers all readiness-helper and call-site-migration decisions until published evidence can be reviewed. Its Context Checked is credible, the single checkpoint owns one coherent responsibility, and broad regression is correctly deferred to final approval. The two findings are bounded schema/publication-safety corrections, not scope expansion.

## What Looks Good

- The explicit report-phase table is a clear, robust answer to the fixture-order concern.
- The Slice 2/3 handoff now preserves the sketch's decision boundary.
- CI retention, upload gating, and the Release Pipeline charter update remain appropriately constrained.
