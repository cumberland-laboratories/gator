# Implementation: Durable Non-Terminal Suspension — Checkpoint 2 (Participant liveness across suspension)

## Executive Summary

- **Changes:**
  - exit `2` from participant `status`, `wait` and `participant watch` now means **the loop ended**, and nothing else;
  - a paused or blocked loop gives `status` exit `1` and keeps `wait` waiting (`3` at a bounded deadline);
  - the watcher acks `architect-block` and stays registered through the suspension;
  - additive `suspension` JSON.
- **Key decision:** implements the approved plan's assumption A1 unchanged. Old participant prompts stay safe, because they already wait on `1` and reissue on `3`.
- **Main risk:** this is a documented contract change, so every participant doc surface was updated in the same checkpoint, and the drift-pinned pairs stay byte-identical.
- **Verified:** 1,238 passed, 8 skipped across the loop, Dashboard-loop, gatorize, entry-point and packaging suites.

## Implementation Summary

**`src/gator_command/scripts/loop/cli.py`**
- `_suspension_view(session)` returns `{kind: architect_hold|architect_decision, resume_stage, resume_role, since, reason (hold only), decision_id, requested_by (decision only)}`, or None. It is built field by field from validated session values.
- **Model `_cmd_status`:**
  - exits `2` only when terminal; a paused or blocked loop exits `1`;
  - text via `_print_suspension`: "Architect hold -- the Architect paused the loop" plus `Reason:`, or "Awaiting Architect decision decision-N (requested by <role>)", then `Resumes with: <role> (<stage>)`, "This is not the end of the loop. You are still a loop participant." and the bounded `wait` command;
  - JSON gains additive `suspension`.
- **Architect `_cmd_status_architect`:** JSON gains `suspension`; the paused text adds `Preserved:`, `Since:` and `Hold reason:`. Architect exit codes are unchanged (plan assumption A3).
- **`_wait_for_actionable`:** `paused` is no longer a wake reason. A suspended loop keeps the wait going, and a bounded wait returns `still_waiting` at its deadline. The `is_paused` parameter is kept for call-site compatibility.
- **`_cmd_wait`:** exits `2` only when terminal; a suspension at the deadline exits `3` with suspension text and the reissue command. JSON gains `suspension`.
- **Watcher text:** `_render_participant` gives suspended `still_waiting` its own wording. `architect_block` is labelled a legacy wake reason, and the `_cmd_participant_watch` docstring exit table is updated.

**`src/gator_command/scripts/loop/liveness.py`**
- `_DELIVERY_OUTCOME` no longer maps `architect-block`.
- `run_watch` acks every record in a poll, but returns only for an actionable one (`turn-ready` or `terminal`, newest wins). After an `architect-block`, it keeps polling, and the registration stays `active` because poll heartbeats it.
- `still_waiting` adds `suspended: true` and `stage` when the loop is suspended (`_suspension_fields`, one unlocked session read; a failure omits them).
- Projection, `state_key`, the notification kinds and the leaf-lock order are unchanged.

**Participant docs and entry points** (pairs kept byte-identical):
- **Protocol** (`.gator/.includes/procedures/gator-loop-protocol.md` and the starter copy):
  - Step 1 `status`, `wait` and watcher exit codes;
  - Rule 1, the State Machine "Paused" summary, Escalation step 1 and the Quick Reference;
  - a new `## Suspension Is Not Departure` section: stay in `wait` or the watcher, resume from status, keep a rejected file, the `Architect response to your escalation` line, and escalate only for Architect-owned decisions.
- **Watcher note** (`loop-participant-watcher.md`, both copies): exit table and JSON keys, plus a "Suspension is not departure" paragraph.
- **`/loop-join`** (`.claude/commands/` and the starter template): exit 1 includes pause/block, `wait` exit 2 means ended, and the watcher line.
- **Entry points:** `gatorize/entry_points.py` `render_entry_content` ("exit 2 means the loop ended. A paused or blocked loop is not the end: status exits 1 and wait keeps waiting, so stay in the bounded wait."), and the identical sentence in the managed regions of the live `CLAUDE.md`, `AGENTS.md` and `GEMINI.md`.

**Tests:**
- **New:**
  - `test_loop_suspension.py::test_status_and_wait_keep_participant_in_loop[paused|blocked]`: `status` exit 1 with `suspension` JSON and text; bounded `wait` exit 3; the resumed role's `wait` exit 0 after unblock; exit 2 after end.
  - `test_loop_liveness_cli.py::TestRunWatch::test_architect_block_is_acked_and_watch_continues`: registration `active` at every poll, `still_waiting` with `suspended` / `stage`, block acked.
  - `test_loop_liveness_lifecycle.py::test_watcher_stays_connected_through_suspension`: a real detached watcher. Pause, then unblock, then the other role submits, all on one generation, then exit 0. Relaunch, escalate (still watching), end, then exit 2 terminal and closed.
  - `test_loop_liveness_projection.py::test_suspension_cycles_idempotent_across_restarts`: pause, then unblock, then pause, with repeated `project`, fresh store instances and `sweep`. That gives exactly `[turn-ready, architect-block, turn-ready, architect-block]`.
- **Updated:** tests that pinned the old behaviour (`test_blocked_exit_2` → `test_blocked_exit_1`, `test_wait_returns_on_pause` → `test_wait_keeps_waiting_through_pause`, `test_pause_preempts_deadline` → `test_pause_does_not_end_wait`), and the `architect-block` row was dropped from the `TestRunWatch` outcome table.

## Charter Updates

- `.gator/charters/scripts-loop.md`:
  - `_cmd_status`: the #53 participant exit contract, `suspension` JSON and Architect paused text;
  - `_cmd_wait` and `_wait_for_actionable`: exit and wake reasons;
  - `run_watch`: `architect-block` acked, not an exit, and the suspended fields;
  - the suspension TRIPWIRE gains a "Participant side" paragraph naming the pinning tests;
  - the Cross-Vendor Orientation notes the new protocol section and the aligned surfaces.
- `.gator/charters/scripts-cross-cutting.md`: the participant exit-contract meaning change, additive `suspension` in `gator-loop-status-v1`, additive `suspended` / `stage` in `gator-loop-participant-v1`, and the surfaces that change together.
- `.gator/charters/scripts-installer.md`: the `render_entry_content` handoff text.
- Every changed function name was checked against the staged code.

## Verification

- Command: `python -m pytest tests/test_loop*.py tests/test_dashboard_loop*.py tests/test_gatorize.py tests/test_update_entry_points.py tests/test_packaging.py -o faulthandler_timeout=120`.
- Result: **1238 passed, 8 skipped** in 454 s, with no failures. The Windows rename flake from checkpoint 1 did not recur.
- The existing drift guards pass with the updated text: `TestWaitHandoffAlignment`, `TestParticipantDocs`, `TestDriftGuards`, the protocol state-table tests and `TestExecutiveSummaryProducerPaths`.
- **Residue:** `.gator/session-snippets/2026-10-05-gator-7b5ae7a4415e9.json` remains untracked and unstaged (checkpoint 1, finding 1). The loop directory is unstaged loop residue.
- **Known gap (by design, checkpoint 3):** the Dashboard does not yet render the new suspension fields.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 3) — Participant liveness across suspension |
| Checkpoint base tree | `67e99a2b3d59ab7a1a2f647908ca55ff2a54d20b` |
| Generation | 2 |
| Staged tree (candidate) | `85d1b25b5b155c1ab17bb72160f176c4b85cee36` |
| Changed paths in this checkpoint | 21 (M 21) |
| Loop base HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` |
| Loop base tree | `38b2c495d8c06205e7967ed312278e32ec9b7d45` |
| Current HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` (dev) |
| Changed paths vs loop base (cumulative) | 23 |
| Unstaged / untracked residue | 1 other + 9 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 67e99a2b3d59ab7a1a2f647908ca55ff2a54d20b 85d1b25b5b155c1ab17bb72160f176c4b85cee36
```

Cumulative context (approved checkpoints plus this one): `git diff 38b2c495d8c06205e7967ed312278e32ec9b7d45 85d1b25b5b155c1ab17bb72160f176c4b85cee36`.

Changed paths in this checkpoint (status, path):

```text
M .claude/commands/loop-join.md
M .gator/.includes/procedures/gator-loop-protocol.md
M .gator/.includes/reference-notes/loop-participant-watcher.md
M .gator/charters/scripts-cross-cutting.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-installer.md
M .gator/charters/scripts-loop.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M AGENTS.md
M CLAUDE.md
M GEMINI.md
M src/gator_command/scripts/gatorize/entry_points.py
M src/gator_command/scripts/loop/cli.py  [revisits an earlier checkpoint]
M src/gator_command/scripts/loop/liveness.py
M src/gator_command/templates/gator-starter/commands/loop-join.md
M src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md
M src/gator_command/templates/gator-starter/reference-notes/loop-participant-watcher.md
M tests/test_loop.py  [revisits an earlier checkpoint]
M tests/test_loop_liveness_cli.py
M tests/test_loop_liveness_lifecycle.py
M tests/test_loop_liveness_projection.py
M tests/test_loop_suspension.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/session-snippets/2026-10-05-gator-7b5ae7a4415e9.json
```

Loop residue: 9 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
