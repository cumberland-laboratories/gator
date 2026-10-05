---
date: 2026-10-02
type: implementation-sketch
issue: 45
feature: loop-readable-markdown-excerpts
status: proposed
---

# Sketch: Safe Readable Markdown for Loop Artifact Excerpts (#45)

## Goal

Make the live Loop workspace easier to inspect by rendering common Markdown in
plan, findings, implementation, and Architect-brief excerpts, while retaining
an obvious exact raw representation for audit and debugging. This is a
presentation-only change: loop residue remains byte-for-byte Markdown and the
existing artifact routes remain the source of truth.

## Context

- `.gator/charters/scripts-dashboard-ui.md` — loop workspace uses incremental
  artifact reconciliation, request revisions, `cache: "no-store"`, and today
  escapes artifact content into `<pre>`.
- `.gator/charters/scripts-dashboard.md` — loop artifacts are allowlisted,
  contain untrusted model-authored content, and are served as current plain
  text only after containment/symlink/reparse checks.
- Existing Dashboard Markdown/highlighting conventions should be inspected
  before selecting a renderer or sanitizer.

## Desired behavior

- Render ordinary headings, paragraphs, lists, emphasis, tables, links, and
  fenced code blocks into a compact readable excerpt.
- Keep a clearly labelled **Raw** representation or raw-file action that shows
  the exact fetched text; rendered and raw views must describe the same
  artifact bytes.
- Treat every artifact as hostile. No inline HTML, scripts, event handlers,
  unsafe URL schemes, injected styles, or layout-breaking markup may execute
  or become trusted DOM. External links must have safe target/rel behavior.
- Preserve the existing truncation/expand and incremental-poll characteristics:
  unchanged polls must not reparse, replace, or disturb expanded artifact
  panels; changed mutable artifacts must refresh safely.
- If rendering fails, show escaped plain text rather than an empty panel or a
  failed workspace.

## Likely shape

Keep the server artifact response as plain text. Add a small client-side
rendering seam in the Loop artifact section, ideally reusing an existing
Dashboard-safe Markdown facility if one exists. The seam should take a string
and return safe DOM/HTML under a documented sanitizer policy; raw text remains
available separately and is never reconstructed from rendered DOM.

Avoid making generic repository browsing or Markdown editing part of this
issue. If a new third-party renderer is proposed, the plan should explicitly
address packaging, CSP compatibility, deterministic sanitization, update
burden, and whether a smaller constrained renderer is safer for this local
Dashboard surface.

## Decisions the plan must settle

1. Reuse an existing renderer/sanitizer, add a pinned dependency, or implement
   a deliberately limited renderer — with a security and maintenance rationale.
2. The raw-view interaction and accessibility semantics (clear state, keyboard
   behavior, no ambiguity about which representation is shown).
3. The allowed Markdown/link subset and exact handling of raw HTML, malformed
   Markdown, relative links, `javascript:`/`data:` URLs, and external links.
4. How renderer output fits the current stable artifact nodes and request
   revisions without regressing zero-mutation unchanged polls.
5. Whether rendering happens only after explicit expansion or also for summary
   excerpts, including a bounded strategy for large artifacts.

## Acceptance and test focus

- Unit or browser tests for representative Markdown, tables, nested lists,
  links, and fenced code (including literal `<script>`/HTML-looking code).
- Adversarial tests for HTML tags/attributes, event handlers, unsafe schemes,
  hostile URLs, malformed input, and CSS/layout injection.
- Raw-versus-rendered parity: Raw presents the exact artifact text; rendering
  never changes the residue or artifact endpoint response.
- Incremental tests: unchanged polls cause no DOM mutations/reparse; mutable
  plan/findings changes refresh their rendered and raw representations; an old
  fetch cannot overwrite a newer result.
- Failure and large-artifact tests: escaped-text fallback remains visible and
  truncation/expand stays usable.

## Scope guard

Do not change loop artifact storage, status/event schemas, artifact
authorization, or the general Repository browser. This issue is only the
Loop workspace's safe, readable presentation of already-authorized Markdown.

