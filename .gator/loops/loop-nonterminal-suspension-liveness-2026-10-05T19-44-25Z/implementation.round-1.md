# Implementation: Durable Non-Terminal Suspension — Checkpoint 1 (Suspension state and resume integrity), revision 1

## Executive Summary

- **Changes:**
  - one validated suspend path (`_suspend`) and one clear path (`_clear_suspension`);
  - a pause stores `pause_reason` and never writes the participant message;
  - Architect messages are recipient-scoped (`architect_message_for`), so pauses, message-less unblocks and the other role's submission never erase them;
  - end resolves a pending request as `cancelled_by_end`.
- **Key decision:** the protocol-documented `Architect message:` line is kept verbatim. The decision id appears on a separate preceding line, so participant prompts keep working.
- **Main risk:** the message routing touches every model-submission transition. Every former unconditional clear is now either a recipient-aware consume (non-terminal) or a full clear (terminal).
- **Verified:** 13 new tests; 1,106 loop/Dashboard-loop tests pass (one pre-existing Windows rename flake disclosed under Verification). Exit codes are unchanged; they belong to checkpoint 2.

## Implementation Summary

**Revision 1: responses to the findings.**
- **Finding 1, residue:** `.gator/session-snippets/2026-10-05-gator-7b5ae7a4415e9.json` has been unstaged. It stays as untracked governance residue for a separate normal commit and is not part of this candidate.
- **Finding 2, stale decision label:** the decision id is now stored with the message as `status.architect_message_decision`.
  - `_set_architect_message(..., decision_id=None)` writes it, so every message write (interject, pause-unblock message, extend, reopen, clear) resets it.
  - Only `handle_unblock` -> `advance_unblocked(..., decision_id=resolved_id)` sets it, and only when that unblock resolves a pending decision.
  - `cli._message_for_role` reads it directly. The inference from the latest unblock turn plus `decisions[-1]` is removed.
  - New regression test `test_later_pause_message_never_inherits_decision_label`: resolve an escalation, pause with a message, then unblock with a new message. The resumed role sees the new message with no decision label, in both the helper output and the status text.


**`src/gator_command/scripts/loop/state_machine.py`**
- **`_suspend(session, stage, pause_reason=None)`:**
  - requires an active loop and a paused target stage (`ValueError` before any mutation);
  - saves `resume_stage` / `resume_next_role`, sets `suspended_at` (ISO UTC) and `pause_reason`, sets `next_role = None` and `blocked = True`, and ends the turn;
  - leaves `architect_message` unchanged, and only ensures the key exists.
- **Callers:** `advance_escalated` and `advance_paused_by_architect` are now thin callers. Escalate keeps `architect_action_required`.
- **`_clear_suspension(status)`:** used by `advance_unblocked`, `advance_extended`, `advance_reopened`, and now `advance_ended_by_architect`. That fixes the stale resume target left by end.
- **Message helpers:** `_set_architect_message`, `_clear_architect_message`, `_consume_architect_message(status, role)`.
  - Non-terminal model transitions consume only their own role's (or an unscoped legacy) message: draft submitted (draftor), review → revision (reviewer), implementation submitted (draftor), and implementation findings and non-final checkpoint approval (reviewer).
  - Terminal transitions (approve, max rounds) clear unconditionally, as before.
- **Recipients:** interject goes to the current turn owner; extend and reopen go to the resumed Draftor.
- **`advance_unblocked(..., message=None, recipient=None, artifact=None)`:**
  - stores the message and artifact for `recipient`, or the resumed role when it is None;
  - **keeps** an unread message when given neither;
  - legacy branch: a session paused before #53 (no `suspended_at` key) clears the message as before, so its old pause reason is not re-shown.

**`src/gator_command/scripts/loop/submit.py`**
- `handle_unblock` addresses a decision response (message and artifact) to `request.role`. The artifact name is computed before `advance_unblocked`, and the file is copied after it. The response contract and the pre-mutation validation are unchanged.
- `handle_end` resolves a pending request as `{message: reason, artifact_path: null, kind: "cancelled_by_end", ts}` (new constant `CANCELLED_BY_END`). The `loop_ended_by_architect` event gains `decision_id`.

**`src/gator_command/scripts/loop/cli.py`**
- `_message_for_role` / `_print_architect_message` / `_message_json`:
  - **Visibility:** model `status` and `wait` show the message to its recipient in any stage (active-own-turn, other's turn, still-waiting, paused). An unscoped message keeps the turn-owner rule.
  - **JSON:** keys are unchanged; the value is null for a non-recipient.
  - **Text:** keeps `Architect message:` and indents continuation lines four spaces. It prints `Architect response to your escalation: decision-N` first when the latest Architect turn was the unblock that resolved this role's request.

**Not in this checkpoint:** participant exit codes, `wait` continuation, the watcher, docs (checkpoint 2), and the Dashboard (checkpoint 3).

## Charter Updates

- `.gator/charters/scripts-loop.md`:
  - new entries for `_suspend` / `_clear_suspension` and the message helpers;
  - updated `advance_escalated`, `advance_unblocked`, `advance_extended`, `handle_unblock` (recipient), `handle_pause` (`pause_reason`), `handle_interject` (recipient), `handle_end` (`cancelled_by_end`, clears suspension), and the `_cmd_status` note on recipient-scoped display;
  - new **TRIPWIRE "Suspension Preserves the Resume Target and Never Erases Messages (#53)"**.
- `.gator/charters/scripts-cross-cutting.md`: additive session fields (`suspended_at`, `pause_reason`, `architect_message_for`, `architect_message_decision`), additive `response.kind` `cancelled_by_end` and the event `decision_id`, and the recipient-only population of the participant JSON message keys.
- Checked against the code: every name cited in the charter edits was grepped in the staged files.

## Verification

- `python -m pytest tests/test_loop_suspension.py`: 13 passed (revision 1 adds the stale-label regression test).
  - Transition table: {planning, coding-checkpoint} × {pause, escalate} × {draftor, reviewer turn}. Exact restore, no residual suspension fields, checkpoint `current` kept.
  - Nested suspension refused.
  - Mixed handler sequence:
    - an interjection survives a pause and an unblock;
    - a reviewer escalation during the Draftor's turn delivers its multiline response to the reviewer only;
    - the Draftor's submission does not consume it, and the reviewer status text shows the decision line plus the indented continuation;
    - the reviewer's submission consumes it;
    - pause then end leaves no target.
  - End while blocked records `cancelled_by_end` and the event `decision_id`.
  - Legacy pause compatibility.
- Existing test updated: `tests/test_loop.py::TestArchitectPause::test_pause_from_active` now asserts `pause_reason == "Hold on"` and `architect_message is None`, which is the plan's intended behaviour change.
- `python -m pytest tests/test_loop*.py tests/test_dashboard_loop*.py -v -o faulthandler_timeout=120`: **1106 passed, 8 skipped** in 410.93 s (generation 0).
- Revision 1 full run: 1106 passed, 8 skipped and **1 failed**: `tests/test_loop.py::TestWaitCommand::test_wait_blocks_then_wakes`.
  - **Cause:** `PermissionError: [WinError 5]` on the `session-*.tmp -> session.json` rename. This is a Windows replace race between the test's writer thread and the polling reader, in `save_session`, which this checkpoint does not touch.
  - **Reruns:** `TestWaitCommand` passed 7/7 on five consecutive reruns, and the test also passed in both earlier full runs. I treat it as a pre-existing flake and disclose it here.
  - An earlier identical run stalled with no output for over two hours. I killed it, and the rerun with the faulthandler guard passed cleanly with no test hanging. I treat the stall as an environmental one-off, but I'm disclosing it here.
- **Residue:** the session snippet is no longer staged (Finding 1). The untracked `.gator/loops/<this loop>/` directory is loop residue and is not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 3) — Suspension state and resume integrity |
| Checkpoint base tree | `38b2c495d8c06205e7967ed312278e32ec9b7d45` |
| Generation | 1 |
| Staged tree (candidate) | `67e99a2b3d59ab7a1a2f647908ca55ff2a54d20b` |
| Changed paths in this checkpoint | 8 (A 1, M 7) |
| Loop base HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` |
| Loop base tree | `38b2c495d8c06205e7967ed312278e32ec9b7d45` |
| Current HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` (dev) |
| Changed paths vs loop base (cumulative) | 8 |
| Unstaged / untracked residue | 1 other + 7 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 38b2c495d8c06205e7967ed312278e32ec9b7d45 67e99a2b3d59ab7a1a2f647908ca55ff2a54d20b
```

Cumulative context (approved checkpoints plus this one): `git diff 38b2c495d8c06205e7967ed312278e32ec9b7d45 67e99a2b3d59ab7a1a2f647908ca55ff2a54d20b`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-loop.md
M .gator/commit_draft.md
M src/gator_command/scripts/loop/cli.py
M src/gator_command/scripts/loop/state_machine.py
M src/gator_command/scripts/loop/submit.py
M tests/test_loop.py
A tests/test_loop_suspension.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/session-snippets/2026-10-05-gator-7b5ae7a4415e9.json
```

Loop residue: 7 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
