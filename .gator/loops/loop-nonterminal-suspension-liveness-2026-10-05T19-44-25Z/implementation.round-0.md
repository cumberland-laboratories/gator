# Implementation: Durable Non-Terminal Suspension — Checkpoint 1 (Suspension state and resume integrity)

## Executive Summary

- **Changes:**
  - one validated suspend path (`_suspend`) and one clear path (`_clear_suspension`);
  - a pause stores `pause_reason` and never writes the participant message;
  - Architect messages are recipient-scoped (`architect_message_for`), so pauses, message-less unblocks and the other role's submission never erase them;
  - end resolves a pending request as `cancelled_by_end`.
- **Key decision:** the protocol-documented `Architect message:` line is kept verbatim. The decision id appears on a separate preceding line, so participant prompts keep working.
- **Main risk:** the message routing touches every model-submission transition. Every former unconditional clear is now either a recipient-aware consume (non-terminal) or a full clear (terminal).
- **Verified:** 12 new tests, and all 1,106 loop/Dashboard-loop tests pass. Exit codes are unchanged; they belong to checkpoint 2.

## Implementation Summary

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
- `.gator/charters/scripts-cross-cutting.md`: additive session fields (`suspended_at`, `pause_reason`, `architect_message_for`), additive `response.kind` `cancelled_by_end` and the event `decision_id`, and the recipient-only population of the participant JSON message keys.
- Checked against the code: every name cited in the charter edits was grepped in the staged files.

## Verification

- `python -m pytest tests/test_loop_suspension.py`: 12 passed.
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
- `python -m pytest tests/test_loop*.py tests/test_dashboard_loop*.py -v -o faulthandler_timeout=120`: **1106 passed, 8 skipped** in 410.93 s.
  - An earlier identical run stalled with no output for over two hours. I killed it, and the rerun with the faulthandler guard passed cleanly with no test hanging. I treat the stall as an environmental one-off, but I'm disclosing it here.
- **Residue disclosure:** the staged tree also contains `.gator/session-snippets/2026-10-05-gator-7b5ae7a4415e9.json`, the snippet the post-commit hook wrote for housekeeping commit `7b5ae7a`. It is governance residue that belongs in the eventual commit, not part of this checkpoint's logic. The untracked `.gator/loops/<this loop>/` directory is loop residue and is not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 3) — Suspension state and resume integrity |
| Checkpoint base tree | `38b2c495d8c06205e7967ed312278e32ec9b7d45` |
| Generation | 0 |
| Staged tree (candidate) | `2b23f68308f7fcea4d0490dcf23ca94148239707` |
| Changed paths in this checkpoint | 9 (A 2, M 7) |
| Loop base HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` |
| Loop base tree | `38b2c495d8c06205e7967ed312278e32ec9b7d45` |
| Current HEAD | `7b5ae7a4415e9f303f4705513a58cf0d14dbe863` (dev) |
| Changed paths vs loop base (cumulative) | 9 |
| Unstaged / untracked residue | 0 other + 3 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 38b2c495d8c06205e7967ed312278e32ec9b7d45 2b23f68308f7fcea4d0490dcf23ca94148239707
```

Cumulative context (approved checkpoints plus this one): `git diff 38b2c495d8c06205e7967ed312278e32ec9b7d45 2b23f68308f7fcea4d0490dcf23ca94148239707`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-loop.md
M .gator/commit_draft.md
A .gator/session-snippets/2026-10-05-gator-7b5ae7a4415e9.json
M src/gator_command/scripts/loop/cli.py
M src/gator_command/scripts/loop/state_machine.py
M src/gator_command/scripts/loop/submit.py
M tests/test_loop.py
A tests/test_loop_suspension.py
```

Unstaged / untracked residue outside the loop directory: none.

Loop residue: 3 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
