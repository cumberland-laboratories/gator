# Review: #80 Checkpoint 3 — Workspace model and session cache

## Executive Summary

- The model/snapshot integration is well scoped, but the cache size boundary is not enforced in bytes as its contract requires.

## Verdict

REVISE

## Findings

### Finding 1: 16 KB cache cap measures characters rather than bytes

**Severity**: Medium

**Location**: `src/gator_command/scripts/dashboard/workspace.js`, `readCache()` and `save()` size checks.

**Issue**: Both checks use JavaScript string `.length` against `MAX_BYTES`. That counts UTF-16 code units, not serialized bytes. Repository names and Loop ids are strings accepted from the registry/state, so non-ASCII content can produce a cache whose encoded or browser-storage size exceeds the documented 16,384-byte ceiling while passing these checks (and the saved JSON can be roughly twice that size in sessionStorage).

**Suggestion**: Measure the serialized JSON with an explicit byte representation (for example `new TextEncoder().encode(text).length`) in both read and write paths, then add a non-ASCII oversized-cache test. Preserve the existing fail-safe behavior when the size boundary is exceeded.

## Scope Check

- Reviewed candidate tree `a699a032fdb345c5a4c8e8d28f5c1e3a5e1b3b44` against `a07f827fda83d56fc70abe9ec95eb740c770a499`.
- The issue is confined to the checkpoint’s new workspace-cache contract.

## What Looks Good

- Cache hydration is deliberately deferred until after shell landing.
- Snapshot inlining and the no-router/no-history model boundary are correctly represented.

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | REVISE |
| Reviewed staged tree | `a699a032fdb345c5a4c8e8d28f5c1e3a5e1b3b44` |
| Reviewed HEAD | `aac105b1618b4a7ea87f37fb6d288da1e1268d12` |
| Candidate round | 0 |
| Checkpoint | cp3 (3 of 5) — Workspace model and session cache |
| Checkpoint base tree | `a07f827fda83d56fc70abe9ec95eb740c770a499` |
| Generation | 2 |
| Live candidate unchanged at review | yes |
