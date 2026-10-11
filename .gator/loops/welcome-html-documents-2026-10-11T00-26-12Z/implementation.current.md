# Implementation: Welcome HTML Documents — Checkpoint 2 (Bounded copy action)

## Executive Summary

- The Start-a-session document's **Copy session-opening prompt** button sends exactly `{type:"gator-welcome", v:1, action:"copy-session-prompt"}` to the parent.
- The Dashboard accepts it only from the current mount's Start-a-session frame, with a `"null"` origin and that exact shape. It writes its own `SESSION_PROMPT` and replies only to that frame, without the prompt.
- The document shows "Copied" only on a confirmed `ok:true`. A failure, no reply in 1500 ms, or no parent gives an announced manual state with the prompt selected.
- Verified:
  - The real Chromium clipboard works through the iframe-to-parent path (the plan's main risk did not happen).
  - The ignored-message matrix passes, with a positive control.
  - Mutation checks hold.
  - The final-approval suite ran once: 644 passed, 11 skipped.

## Implementation Summary

**Parent:** `src/gator_command/scripts/dashboard/views/welcome.js`.
- New constants `MSG_TYPE`, `COPY_REQUEST`, `COPY_RESULT`, plus module state `copyListener`.
- `isCopyRequest(d)`: a non-null object whose prototype is `Object.prototype`, `Object.keys(d).length === 3`, `type === "gator-welcome"`, `v === 1`, `action === "copy-session-prompt"`.
- `replyCopy(source, ok, reason)`: posts `{type, v:1, action:"copy-session-prompt-result", ok}`, plus `reason` when `ok` is false, to `source` with target origin `"*"`. An opaque origin cannot be named, and the reply carries no secret.
- `handleCopyRequest(source)`: no Clipboard API → `unavailable`; `writeText(SESSION_PROMPT)` rejects → `denied`; success → `ok:true`.
- `bindCopyListener(mountRoot, mountFrames)`: called on every mount right after `frames = {}`.
  - It removes the previous listener.
  - The new listener removes itself if its root is detached.
  - It returns early unless all of these hold: `mountFrames.session` is a connected `IFRAME`; `event.source === frame.contentWindow`; `event.origin === "null"`; `isCopyRequest(event.data)`.
- The module header contract documents the one accepted message.

**Document:** `src/gator_command/templates/gator-starter/docs/start-a-session.html`.
- The master meta CSP changes only `script-src 'none'` to `'unsafe-inline'`.
- A small second `<style>` block, outside the shared `CUMBERLAND-NARRATIVE-STYLE` region (which stays byte-identical), adds `.copy-row` / button / `#copy-status`.
- Markup: `button#copy-session-prompt[type=button]`, `div#copy-status[role=status][aria-live=polite]`. The checkpoint 1 static line becomes `p#copy-manual[hidden]`: "Copy did not work here. Select the prompt above and copy it."
- Inline script:
  - A click clears earlier state. With no parent (`window.parent === window`) it goes straight to the manual state. Otherwise it arms a 1500 ms timer and posts the exact request.
  - The `message` listener acts only while a request is pending, only for `event.source === window.parent`, and only when `isResult()` passes: an exact key set with `ok` boolean, and a string `reason` only when `ok` is false.
  - `ok:true` sets status "Copied", cleared after 2 s.
  - Everything else, and the timeout, gives `showManual()`: `#copy-manual` shown, status "Copy did not work here. Copy the prompt manually.", and the `<pre>` prompt selected with a `Range`.
  - A late reply after the timeout is ignored, so the page never claims an unconfirmed copy.
- The other three documents are unchanged: `script-src 'none'`, no `<script>`.

## Charter Updates

- `scripts-dashboard-ui.md` (Welcome entry):
  - The heading adds `bindCopyListener() / isCopyRequest() / handleCopyRequest() / replyCopy()`.
  - New **Copy action** bullet: the per-mount listener lifecycle, the four acceptance conditions, the reply shape and reasons, the `"*"` target-origin rationale, and the manual fallback living in the document.
  - New **TRIPWIRE (copy protocol)**: only this mount's session frame; the listed rejected senders and shapes cause no write, reply, topic, history, focus or network change; the prompt is never received, sent, logged or exposed through a message; never widen without a new review.
- The `scripts-dashboard.md` `'unsafe-inline'` dependency note from checkpoint 1 already covers the document script, so no change was needed there.
- Checked against code: the condition order and the reply fields in the charter match `bindCopyListener()` / `replyCopy()` line for line.

## Verification

- Focused checks for this checkpoint:
  - `python -m pytest tests/test_dashboard_ui/test_welcome_ui.py -k copy` → 14 passed.
  - `tests/test_welcome_docs.py` → 10 passed.
- `test_welcome_copy_success`: clipboard permissions granted, the in-frame button activated by keyboard (focus, then Enter). The frame status reads "Copied" (`role=status`, `aria-live=polite`), and parent `navigator.clipboard.readText()` equals the exact one-line `SESSION_PROMPT`. No history or storage leak. **This proves real Chromium clipboard writes work through the iframe-to-parent `postMessage` path.**
- `test_welcome_copy_manual_state` × {parent Clipboard API missing, rejects, document opened top-level}: manual line visible, status announced, prompt selected, and no "Copied" after the 1500 ms timeout.
- `test_welcome_copy_ignores_everything_else` × 10: a **control** (an exact request from the current session frame gives exactly one write of `SESSION_PROMPT` and one `ok:true` reply) plus 9 ignored cases, each giving no write, no reply to the sender, unchanged topic, URL and history length, and no request:
  - page `window.postMessage` (non-`"null"` origin);
  - an injected unrelated sandboxed `srcdoc` frame;
  - the mounted `how` frame;
  - a **stale** session frame (the first mount's iframe node re-attached after remounting Welcome);
  - `v:2`;
  - an unknown action;
  - an extra key;
  - an array;
  - a string.
- `test_welcome_docs.py`:
  - Each document's meta CSP equals the master's, with only `script-src` changed and only for the session document. The other three contain no `<script>`.
  - The session document contains the exact three-key request literal, and the prompt appears exactly once (the visible `<pre>`).
- Mutation checks (each restored afterwards):
  - Removing the `event.source` check fails the unrelated-frame, how-frame and stale-frame cases.
  - Removing the three-key count fails the extra-key case.
  - The `"null"`-origin check has no isolated failing case, because every sandboxed frame is opaque and the page case is already stopped by the source check. It stays as a second, independent guard, as the sketch requires.
- Final-approval suite, run once: `python -m pytest tests/test_dashboard_ui tests/test_snapshot.py tests/test_packaging.py tests/test_layout.py tests/test_gatorize.py tests/test_welcome_docs.py` → **644 passed, 11 skipped** (12 min 16 s).
- `commit_draft.md` now carries the checkpoint 2 change log and the significance-check steelman, to be surfaced to the Architect before the commit.
- Not part of the candidate: `.gator/.gator-version` and `.gator/runtime-pin.json` (unstaged version-bump residue) and the loop directories.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 2) — Bounded copy action |
| Checkpoint base tree | `644db5e88cf059b1466b4a6080d8dc2f975e91ca` |
| Generation | 1 |
| Staged tree (candidate) | `76a247ddccbce4c27b9f1a4272d2bba9f1b1a8cf` |
| Changed paths in this checkpoint | 6 (M 6) |
| Loop base HEAD | `a2593995f53bdce353c9539188217324218938dd` |
| Loop base tree | `6c0874c6810c7ebe2b03e81d173f86db16dc7862` |
| Current HEAD | `a2593995f53bdce353c9539188217324218938dd` (dev) |
| Changed paths vs loop base (cumulative) | 21 |
| Unstaged / untracked residue | 2 other + 38 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 644db5e88cf059b1466b4a6080d8dc2f975e91ca 76a247ddccbce4c27b9f1a4272d2bba9f1b1a8cf
```

Cumulative context (approved checkpoints plus this one): `git diff 6c0874c6810c7ebe2b03e81d173f86db16dc7862 76a247ddccbce4c27b9f1a4272d2bba9f1b1a8cf`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/views/welcome.js  [revisits an earlier checkpoint]
M src/gator_command/templates/gator-starter/docs/start-a-session.html  [revisits an earlier checkpoint]
M tests/test_dashboard_ui/test_welcome_ui.py  [revisits an earlier checkpoint]
M tests/test_welcome_docs.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
```

Loop residue: 38 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
