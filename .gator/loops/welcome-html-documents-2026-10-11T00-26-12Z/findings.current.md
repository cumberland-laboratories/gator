# Review: Welcome HTML Documents — Checkpoint 2

## Executive Summary

- Approved the final bounded copy-action checkpoint and the cumulative candidate tree `76a247ddccbce4c27b9f1a4272d2bba9f1b1a8cf`.
- The Dashboard accepts one exact request only from the current mount's connected Start-a-session iframe at opaque origin `"null"`; other senders and shapes have no side effects.
- The Dashboard owns the one-line prompt and clipboard write. Its reply contains only success or a bounded failure reason, never prompt text.
- Independent focused verification passed: 14 copy-path UI tests and 10 welcome-document tests.

## Verdict

Approved for the normal cumulative commit.

## Review Notes

The per-mount listener is correctly removed on remount and self-removes after its root detaches. It additionally validates the current frame identity, `"null"` origin, and an exact three-key plain-object request before invoking the clipboard. The document only reports success after a strict parent reply; timeout, rejection, unavailable Clipboard API, and top-level use select the visible prompt and provide an announced manual fallback.

The adversarial coverage includes page, unrelated, other-topic, stale-frame, bad-version, bad-action, extra-key, array, and string senders, with a positive control. No prompt is accepted from or returned through the protocol. The `unsafe-inline` CSP exception remains limited to the Start-a-session document.

Verification run by reviewer:

```text
python -m pytest tests/test_dashboard_ui/test_welcome_ui.py -k copy  # 14 passed
python -m pytest tests/test_welcome_docs.py                           # 10 passed
```

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | APPROVE |
| Reviewed staged tree | `76a247ddccbce4c27b9f1a4272d2bba9f1b1a8cf` |
| Reviewed HEAD | `a2593995f53bdce353c9539188217324218938dd` |
| Candidate round | 0 |
| Checkpoint | cp2 (2 of 2) — Bounded copy action |
| Checkpoint base tree | `644db5e88cf059b1466b4a6080d8dc2f975e91ca` |
| Generation | 1 |
| Live candidate unchanged at review | yes |
