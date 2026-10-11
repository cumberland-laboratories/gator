# Review: Welcome HTML Documents — Checkpoint 1

## Executive Summary

- **Verdict:** APPROVE checkpoint 1. The candidate delivers the four Cumberland-derived placeholder documents, closed-name serving route, snapshot embedding, and lazy persistent Welcome frames.
- **Isolation:** The server uses membership-only document lookup, each frame is sandboxed exactly `allow-scripts`, and document HTML is never inserted into the Dashboard DOM.
- **Compatibility:** The B2 directive string was moved verbatim into shared policy code; the existing HTML-preview header coverage remains green.
- **Verification:** Focused document, route, snapshot, frame, and CSP tests pass, as does the wheel template-membership test. The one encoded-separator result differs from the draft only because the shared parser rejects it earlier with a stricter 400.

## Verdict

APPROVE — checkpoint 1 is ready. This opens checkpoint 2 and does not authorize a commit.

## Findings

No remaining findings.

## Scope Check

The candidate stays within the first approved checkpoint: document shipping, master-template conformance, allowlisted serving, snapshot safety, iframe hosting, styling, immediate charters, and the release-hold record. It deliberately excludes the copy message/listener work assigned to checkpoint 2.

The captured implementation and charter updates agree on the key invariants. The route does not construct a filesystem path from request input; the snapshot handles unavailable or headless documents safely; and every document’s intended package/install/update delivery is explicitly tested.

## What Looks Good

- The source document template contract is mechanically pinned rather than treated as a visual convention.
- The external CSP is applied directly to the Welcome route without disturbing `/raw` behavior.
- Frame persistence is tested with in-frame state, not inferred from DOM shape alone.

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | APPROVE |
| Reviewed staged tree | `644db5e88cf059b1466b4a6080d8dc2f975e91ca` |
| Reviewed HEAD | `a2593995f53bdce353c9539188217324218938dd` |
| Candidate round | 0 |
| Checkpoint | cp1 (1 of 2) — Sandboxed Welcome documents |
| Checkpoint base tree | `6c0874c6810c7ebe2b03e81d173f86db16dc7862` |
| Generation | 0 |
| Live candidate unchanged at review | yes |
