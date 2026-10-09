# Implementation: #56 Loop Create/History workspaces — Checkpoint 3 (Participant recovery)

## Executive Summary

- **What changed:** the bare "Copy Draftor/Reviewer prompt" buttons are replaced by a labelled **Participant recovery** disclosure. It holds fixed guidance, the credential warning, and a per-role need line next to each existing copy button. It opens by itself only when a role needs recovery.
- **Key decision:** the need comes only from facts the browser already has: `status.roles[r].joined` and the allowlisted liveness `state`. A joined role with no watcher (`not_registered`) is never flagged (#52 guard, mutation-checked).
- **Main risk:** zero-mutation polling and existing copy-flow pins. Both are covered: the recovery region is mutation-free across polls, and the existing copy-race tests pass after a change from a visible to an attached wait.
- **Verified:** the checkpoint Verify command passes (117 tests). The final-approval suites also pass: `tests/test_dashboard_ui` 436 passed / 11 skipped, and the rest of `tests` 2082 passed / 11 skipped / 2 xfailed.

## Implementation Summary

- **`views/loop.js`:**
  - **`renderPromptSection(terminal, root, snap)`.** For a terminal loop it empties the region (no `.loop-prompt-copy`, B19 kept) and clears `snap.recovery`. For a live loop it builds, once per snapshot (the prompts fingerprint stays `live`/`terminal`):
    - `<details class="loop-recovery" id="loop-recovery">` with summary "Participant recovery";
    - `.loop-recovery-guidance`: "Use these prompts only to start a new participant session or reconnect one that dropped. Do not paste a prompt into a session that has already joined.";
    - `.loop-recovery-warning`, the existing credential warning text;
    - one `.loop-recovery-row[data-role]` per role, holding the role name, `.loop-recovery-need[data-need]` and the existing `button.loop-prompt-copy[data-role]` wired to the unchanged `copyPrompt()`.

    A summary click sets `data-user-toggled`. It then sets `snap.recovery = {needKey: null}`.
  - **`recoveryNeed(role, joined, livenessState)`** (pure):
    - not joined → "Has not joined yet.";
    - joined and `stale` → "Watcher is stale — reconnect if the session dropped.";
    - joined and `released` → "Watcher exited after a notification — reconnect if the session closed.";
    - anything else (connected, `not_registered`, closed, unknown, liveness unavailable or 404) → `null`, shown as "Joined — no action needed".
  - **`applyRecovery(snap)`:**
    - It reads `snap.statusRoles` (stored by `renderSelectedLoop`) and `snap.liveness.lastView`.
    - Through `setText` it writes the need text, prefixed "⚠ " when there is a need. It writes `data-need` only when it differs.
    - It computes a need key. When the key changes it clears `data-user-toggled` and sets `open` to "any need", writing only if it differs. When the key is unchanged it touches nothing, so a manual toggle holds until the need set changes.
  - **Call sites:** `renderSelectedLoop()` (after the prompts patch) and the end of `applyLiveness()`'s main path.
  - **Snapshot:** `buildLoopSkeleton()` gains `statusRoles` and `recovery`.
- **`dashboard.css`:**
  - `.loop-recovery`: summary weight, guidance and warning text, flex rows that wrap on narrow screens.
  - `.loop-recovery-need[data-need="1"]` is bold. Together with the ⚠ glyph, the need is never shown by colour alone.
  - The unused `.loop-prompt-section` rules (desktop and narrow) were removed.
- **Unchanged:** `copyPrompt()` and its fallback, `promptEpoch`, token non-persistence, the handoff cards, liveness, Re-notify, tokens, stages and polling ownership.

## Charter Updates

- `.gator/charters/scripts-dashboard-ui.md`, Loop workspace:
  - **"Live vs history"** now names "the Participant recovery disclosure" instead of "prompt copy section".
  - **New tripwire, Participant recovery (#56).** It covers the structure and fixed text, that copying is unchanged, the `recoveryNeed` table with a **TRIPWIRE (#52)** that a joined role with no watcher is never flagged, the `applyRecovery` call sites, the write-on-difference discipline, the need-key open/close rule with the user-toggle hold, and the zero-mutation pin.
- **Checked against the code:** `renderPromptSection`, `recoveryNeed`, `applyRecovery`, `snap.statusRoles`, `#loop-recovery`, `.loop-recovery-row`, `.loop-recovery-need[data-need]` and `data-user-toggled` match the staged diff.
- `.gator/commit_draft.md` gains a Checkpoint 3 entry.

## Verification

- **Focused tests:** `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py -k "recovery or terminal_loop_read_only or prompts or inflight or copy" -q` → **15 passed**. The new tests:
  - `test_recovery_hidden_for_healthy_joined[connected|not_registered]`: the disclosure is closed, both rows read "Joined — no action needed" (`data-need="0"`), and both copy buttons exist but are not visible.
  - `test_recovery_opens_for_need[not_joined|stale|released]`: the disclosure opens with "⚠ <need>" (`data-need="1"`, bold), the other role reads no action, and the guidance and warning are present. A real click on Copy writes the stubbed prompt to the clipboard, and the only POST is `/prompt`.
  - `test_recovery_user_toggle_survives_poll`: the user closes the disclosure, it stays closed across more than two polls with the same need set, reopens when the need set changes, and closes when the needs clear.
  - `test_recovery_poll_mutation_free`: a MutationObserver on `#loop-region-prompts` sees zero mutations across more than two identical polls, and the disclosure node stays connected.
- **Updated tests:** `test_live_workspace_inflight_copy_blocked_by_terminal` and the poll-sequence copy-race test now wait for `.loop-prompt-copy` with `state="attached"` (the button is inside a closed disclosure); their assertions are unchanged. B18 (two copy buttons), B19 (terminal: zero) and the extend test (prompts back after terminal → live) pass unchanged.
- **Mutation check:** making `recoveryNeed` flag `not_registered` fails `test_recovery_hidden_for_healthy_joined[not_registered]`. The code was restored afterwards.
- **Checkpoint Verify:** `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py tests/test_dashboard_ui/test_loop_liveness_ui.py -q` → **117 passed**.
- **Final-approval suites** (run once, this being the last checkpoint):
  - `python -m pytest tests/test_dashboard_ui -q` → **436 passed, 11 skipped**;
  - `python -m pytest tests -q --ignore=tests/test_dashboard_ui` → **2082 passed, 11 skipped, 2 xfailed**.

  Together these cover all of `tests`.
- **Staged-tree note:** unchanged from earlier checkpoints. The pre-existing `.gator/session-snippets/2026-10-09-…json` stays staged as designed. `.gator/.gator-version`, `.gator/runtime-pin.json` and an older untracked session snippet are outside the candidate.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp3 (3 of 3) — Participant recovery |
| Checkpoint base tree | `0724a1c2fce6de67a87fe6bcbe34176ffe768309` |
| Generation | 3 |
| Staged tree (candidate) | `16d2b3b3b143ccacfdfbe5893abe5fd25c87a137` |
| Changed paths in this checkpoint | 5 (M 5) |
| Loop base HEAD | `34a9d0e417d431853181de99088547a9fce86698` |
| Loop base tree | `7e01b49b16a02cb832fd21eda069d58736482b40` |
| Current HEAD | `34a9d0e417d431853181de99088547a9fce86698` (dev) |
| Changed paths vs loop base (cumulative) | 13 |
| Unstaged / untracked residue | 3 other + 99 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 0724a1c2fce6de67a87fe6bcbe34176ffe768309 16d2b3b3b143ccacfdfbe5893abe5fd25c87a137
```

Cumulative context (approved checkpoints plus this one): `git diff 7e01b49b16a02cb832fd21eda069d58736482b40 16d2b3b3b143ccacfdfbe5893abe5fd25c87a137`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.css  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/views/loop.js  [revisits an earlier checkpoint]
M tests/test_dashboard_ui/test_loop_workspace.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 99 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
