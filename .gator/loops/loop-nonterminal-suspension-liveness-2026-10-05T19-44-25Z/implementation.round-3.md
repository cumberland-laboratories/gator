# Implementation: Durable Non-Terminal Suspension — Checkpoint 3 (Architect workspace for suspension)

## Executive Summary

- **Changes:**
  - the Dashboard suspension card is rebuilt from fields the loop actually writes. The old blocked card keyed on `status.escalation_reason`, which is never written, so it **never rendered** in real loops;
  - blocked and paused now render distinctly;
  - the response box is a labelled multiline textarea;
  - decision history, a post-unblock notice, and connected-through-the-hold liveness wording.
- **Key decision:** no server change. `/status` already passes `status` and `decisions`, so every view is derived client-side, and fingerprints keep unchanged polls mutation-free.
- **Main risk:** the UI test seed modelled the fictitious field, so it was corrected to the real session shape.
- **Verified:** 650 passed, 17 skipped across the Dashboard UI, snapshot and Dashboard-loop suites.

## Implementation Summary

**`src/gator_command/scripts/dashboard/views/loop.js`**
- **`renderBlockedCard()` (suspension card):** shows for any paused stage and is built only from `stage`, `resume_stage` / `resume_next_role`, `suspended_at`, `pause_reason` and the pending decision's `request` (`reason`, `role`, `ts`, `artifact_path`).
  - **Blocked** (`.loop-blocked-card.loop-decision-card`, `data-kind="architect_decision"`):
    - title "⚑ Blocked — awaiting your decision";
    - `decision-N · requested by <Role> · <date time>`;
    - the full reason in `.loop-blocked-reason` (`escHtml`, CSS `pre-wrap`);
    - the "View decision request" link (same class and behaviour as before);
    - `Resumes: <Role> · <stage>`.
  - **Paused** (`.loop-hold-card`, `data-kind="architect_hold"`): "⏸ Architect hold (paused)", "You paused this loop. No participant response is required.", `Preserved:`, `Since:`, and the reason. It never uses escalation wording.
  - **Telling them apart:** title text, glyph and border style (dashed for a hold), never colour alone.
  - **Fingerprint:** `blockedFingerprint` now covers every field the card reads.
- **`renderDecisionHistory()`** fills the new `#loop-region-decisions` region (fingerprint `decisionsFingerprint`: ids plus response kind/ts). It shows on live and terminal loops and lists each request (id, requesting role, time, reason, "View request") and its resolution.
  - Resolution labels come from `RESPONSE_KIND_LABELS`, including "Cancelled — loop ended" for `cancelled_by_end`; an unknown kind shows "Resolved".
  - Glyphs: ✓ resolved, ○ pending (bold).
  - The response message is shown pre-wrapped, with a "View response" link. Artifact links share `wireArtifactJump()`.
- **Controls:**
  - the input is `<textarea id="loop-ctrl-message" class="loop-ctrl-input" rows="4">`, with `<label for>` plus an `aria-label` fallback;
  - the required unblock label names the escalating role ("Response to Reviewer (required)", "participant" when unknown);
  - `controlsFingerprint` is unchanged, so a typed draft survives polling (the existing rule);
  - on a successful unblock, `showUnblockNotice()` writes the action slot: "Unblocked. <Role> resumes at <stage> when its watcher or wait sees the change. The Dashboard does not run model work."
- **Liveness:** `renderSelectedLoop` sets `snap.suspended`, and `livenessStateText(role, suspended)` appends " — waiting through the hold" to a connected role.

**`src/gator_command/scripts/dashboard/dashboard.css`**
- `.loop-blocked-reason` uses `pre-wrap`.
- `.loop-hold-card` has a dashed 2px border on the page background.
- New suspension meta/note styles, decision-list styles and `.loop-unblock-notice`.
- `textarea.loop-ctrl-input` sizing, and the input area wraps.

**Deliberate deviation from the plan's Change 7:** timeline event detail keeps its single-line ellipsis. The plan suggested `pre-wrap` there, but multi-line messages would make every timeline card tall and break the scan-the-timeline layout. The full multi-line request and response text is instead readable in the new decision history and the suspension card. Pause and unblock remain in the timeline as `PAUSED` / `Unblocked` cards.

**Tests (`tests/test_dashboard_ui/`):**
- **Seed:** `test_loop_seed.py` uses the real blocked-loop shape. `escalation_reason` is removed; the pending decision has a role, ts and a multi-line reason; the status has the resume pair and `suspended_at`. The existing blocked-card tests still pass against it.
- **`test_loop_workspace.py`:**
  - `_route_paused_status` gains `pause_reason` / `extra_decisions` and drops the fictitious field;
  - the escalation-label assertion becomes "Response to Draftor (required)";
  - new `test_blocked_card_shows_request_from_real_fields`, `test_paused_card_is_an_architect_hold` (wording, preserved pair, multi-line reason, dashed border, no escalation wording), `test_textarea_draft_survives_mutation_free_polls` (labelled TEXTAREA, multi-line draft kept, **0 mutations** over two polls across controls, suspension and decision regions) and `test_decision_history_and_unblock_notice` (a cancelled request is readable, the multi-line message is posted, and the notice wording claims no model work).

## Charter Updates

- `.gator/charters/scripts-dashboard-ui.md`:
  - the Live-vs-history line;
  - new bullets for the suspension card, decision history and unblock notice;
  - the multiline-input note;
  - the liveness panel's "waiting through the hold" wording.
- The names were checked against the staged `loop.js`.
- `scripts-dashboard.md` is unchanged: no server change.

## Verification

- `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py -k "blocked or paused or unblock or textarea or decision or poll_does_not or pending_decision"`: 13 passed.
- `python -m pytest tests/test_dashboard_ui/ tests/test_snapshot.py tests/test_dashboard_loop*.py -o faulthandler_timeout=180`: **650 passed, 17 skipped**, 0 failed. This includes the snapshot inlining test for `views/loop.js`.
- `node -e "new Function(...)"` syntax check of `loop.js`: OK.
- **Residue:** the session snippet stays untracked and unstaged; the loop directory is unstaged loop residue.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp3 (3 of 3) — Architect workspace for suspension |
| Checkpoint base tree | `85d1b25b5b155c1ab17bb72160f176c4b85cee36` |
| Generation | 3 |
| Staged tree (candidate) | `e0bd8ff7e78858ec9b0a0d77c113054fad71d429` |
| Changed paths in this checkpoint | 6 (M 6) |
| Loop base HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` |
| Loop base tree | `38b2c495d8c06205e7967ed312278e32ec9b7d45` |
| Current HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` (dev) |
| Changed paths vs loop base (cumulative) | 28 |
| Unstaged / untracked residue | 1 other + 11 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 85d1b25b5b155c1ab17bb72160f176c4b85cee36 e0bd8ff7e78858ec9b0a0d77c113054fad71d429
```

Cumulative context (approved checkpoints plus this one): `git diff 38b2c495d8c06205e7967ed312278e32ec9b7d45 e0bd8ff7e78858ec9b0a0d77c113054fad71d429`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.css
M src/gator_command/scripts/dashboard/views/loop.js
M tests/test_dashboard_ui/test_loop_seed.py
M tests/test_dashboard_ui/test_loop_workspace.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/session-snippets/2026-10-05-gator-7b5ae7a4415e9.json
```

Loop residue: 11 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
