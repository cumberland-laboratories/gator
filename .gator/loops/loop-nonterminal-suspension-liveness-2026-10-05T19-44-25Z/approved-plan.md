# Implementation Plan: Durable Non-Terminal Suspension and Participant Liveness (#53)

## Executive Summary

- **Problem (audited):** every participant surface treats suspension as departure. `status` and `wait` exit `2` on `paused_by_architect` / `blocked_on_architect`, and the protocol says exit `2` means stop. The watcher exits `2 architect_block` and releases its registration. A pause overwrites (or erases) an unread Architect message. An escalation response can be cleared by the other role's submission before the escalator reads it. The Dashboard's blocked card reads `status.escalation_reason`, which nothing writes, so it never renders.
- **Key decision:** exit `2` comes to mean **terminal only**, everywhere. During suspension, `status` exits `1` ("not your turn, wait"), bounded `wait` keeps waiting and exits `3`, and the watcher acks the block and stays registered.
- **Main risk:** this changes the participant exit-code contract. It is safe for old prompts, which already reissue on `1`/`3`, but the docs, the drift-pinned copies and the entry points must change together.
- **Verification:** three responsibility checkpoints, each with focused parameterized tests: state and resume integrity, participant liveness, and the Architect workspace (Playwright).

## Summary

The plan makes one lifecycle contract explicit: **blocked and paused are distinct governance states, and neither ends a participant's relationship with an active loop.** It reuses the existing seams:

- `state_machine` suspend/resume fields;
- the `decisions[]` ledger;
- liveness `architect-block` records;
- bounded `wait`;
- the Dashboard `/status` projection.

It adds no second suspension store and no new transport. It fixes the audited paths that today turn a suspension into an apparent disconnect, lose Architect messages, or hide the request from the Architect.

## Context Checked

- `architect-brief.md`: none listed. `gator loop status` shows no brief line for this loop.
- `sketch.md` (this loop): scope, required behaviour, design boundaries, checkpoint shape, and test cases.
- `.gator/procedures/writing-implementation-plans.md`: planning path, module and simplicity rules, and test proportionality.
- `.gator/.includes/procedures/gator-loop-protocol.md` and `.gator/.includes/reference-notes/loop-artifact-formats.md`: exit-code text (Step 1, State Machine summary "`status` and `wait` exit `2`") and the plan format.
- `.gator/.includes/reference-notes/loop-participant-watcher.md`: the exit contract (`2 architect_block`, released).
- `.gator/charters/INDEX.md`, `.gator/charters/scripts-cross-cutting.md`: CLI/JSON compatibility rule, `TestWaitHandoffAlignment` / `TestParticipantDocs` / `TestDriftGuards` byte-identity pins, and session-authoritative watcher rule.
- `.gator/charters/scripts-loop.md` (full): `advance_escalated` / `advance_unblocked` / `advance_paused_by_architect` / `advance_ended_by_architect`, `handle_unblock` response contract, `_cmd_status` / `_cmd_wait` / `_wait_for_actionable`, liveness `_apply_projection` / `run_watch` / `classify`, and these TRIPWIREs: Liveness Leaf Lock, Session Lock Write Ordering, Stage-Role Consistency, Escalate Bypasses Turn Check, and Checkpoint (pause/unblock keep `current`).
- `.gator/charters/scripts-dashboard-ui.md` (loop view entries): incremental `patchRegion` fingerprints, controls-survive-polling rule, and the liveness panel.
- `.gator/charters/scripts-installer.md` (`render_entry_content`): "exit 2 = stop" text pinned by `TestWaitHandoffAlignment`.
- Code read:
  - `loop/state_machine.py`: `validate_action`, `_validate_architect_action`, all `advance_*` suspend/resume/end functions, `advance_draft_submitted`, `advance_review_submitted`.
  - `loop/submit.py`: `handle_escalate`, `handle_unblock`, `handle_pause`, `handle_interject`, `handle_end`.
  - `loop/cli.py`: `_cmd_status`, `_cmd_status_architect`, `_cmd_wait`, `_wait_for_actionable`.
  - `loop/liveness.py`: `state_key`, `classify`, `prune`, `_apply_projection`, `project`, `renotify_eligibility`, `observer_view`, `register` / `poll` / `ack` / `release`, `run_watch`.
  - `gator-dashboard.py`: `_handle_loop_status`, `_LOOP_STATUS_ALLOWED_KEYS`, `_handle_loop_pause`, `_handle_loop_unblock`.
  - `dashboard/views/loop.js`: `pendingDecision`, `blockedFingerprint`, `controlsFingerprint`, `renderSelectedLoop`, `renderBlockedCard`, `renderControls`.
  - `gatorize/entry_points.py`: the loop-join paragraph.
- Test inventory (file names only): `tests/test_loop*.py`, `tests/test_loop_liveness_{cli,lifecycle,projection,store}.py`, `tests/test_dashboard_loop_liveness.py`, `tests/test_dashboard_ui/test_loop_{workspace,liveness_ui,refresh_ui}.py`.

## Audit of Current Paths

| Path | Current behaviour | Defect against the sketch |
|---|---|---|
| `advance_escalated` / `advance_paused_by_architect` | Two copies of the save logic for `resume_stage` / `resume_next_role`. Pause also writes `architect_message = message`, which may be `None`. | A pause overwrites, or erases, an unread interjection or decision response. There is no suspension timestamp. The pause reason is only in `architect_message` and turns. |
| `advance_unblocked` | Restores and validates the stage/role pair, then sets `architect_message = message` unconditionally. | An unblock without a message erases a pending message. |
| `advance_ended_by_architect` | Leaves `resume_*` set and leaves a pending decision with `response: null` forever. | Stale resume target. The request is never resolved in evidence. |
| `advance_extended` / `advance_reopened` | Clear `resume_*`. | OK. |
| Model `architect_message` | One unscoped field, shown only to the turn owner, cleared by ANY model submission. | If the escalator is not the turn owner, the turn owner's submission clears the response before the escalator ever sees it. |
| `_cmd_status` (model) | Exits `2` when paused or blocked and prints "Blocked -- waiting for Architect". | The protocol says exit `2` means stop, so the participant leaves the loop. Pause and escalation look the same. |
| `_cmd_wait` / `_wait_for_actionable` | Return `paused`, exit `2`. | The same disconnect. The entry-point text says "exit 2 means paused or ended". |
| `liveness.run_watch` | On `architect-block`: acks, **releases**, exits `2 architect_block`. | The watcher stops on suspension. The Dashboard shows "released". Exit `2` collides with `terminal`. |
| `_apply_projection` | One `architect-block` per registered role per `state_key`; one `turn-ready` per key after unblock. | Idempotent and correct. Kept unchanged. |
| `loop.js renderBlockedCard` | Renders only when `s.blocked && s.escalation_reason`. | `escalation_reason` is never written, so the card **never renders**. Paused has no card at all. |
| `loop.js renderControls` | Single-line `<input type="text">` for unblock, pause and interject. | No multiline response. |

## Approach

**Planning path:** full planning loop. This change touches a public CLI exit-code contract, durable session fields, a lifecycle invariant and a cross-module protocol, as the sketch requires.

**Module map (three responsibilities = three checkpoints):**

1. **Suspension state and resume integrity** (`state_machine.py`, `submit.py`, plus the read side of message routing in `cli.py`).
   - Owns this invariant: `resume_stage` / `resume_next_role` / `suspended_at` are non-null **iff** the stage is paused. One validated suspend path and one validated restore path.
   - Architect messages are recipient-scoped and are never erased by a pause, by an unrelated unblock, or by another role's submission.
   - Every decision request ends resolved, by response or by end.
2. **Participant liveness across suspension** (`cli.py` status/wait, `liveness.py` `run_watch`, plus participant-facing docs and entry points).
   - Owns this invariant: **exit `2` = terminal only.** A suspension never makes a participant stop, release, or rejoin. Resume comes from status, not from a pasted prompt.
   - The participant docs travel with this checkpoint because `TestWaitHandoffAlignment` / `TestParticipantDocs` pin them to the behaviour. Splitting them out would create a docs-only pseudo-checkpoint, or leave a checkpoint whose docs contradict its code.
3. **Architect workspace** (`dashboard/views/loop.js`, `dashboard.css`).
   - Distinct blocked and paused presentation built from fields that actually exist, a multiline response, decision/pause history, and incremental and mutation-free polling.
   - No claim that the Dashboard resumed model work.

**Key design decision: exit `2` means terminal only.**
- **Before:** suspension `status` → 1; bounded `wait` keeps polling through suspension → 3 at its deadline; unbounded `wait` keeps waiting through suspension; watcher acks `architect-block` and keeps polling.
- **Backward safety:** participants using the *old* prompt text already treat `1` as "wait" and `3` as "reissue", so they behave correctly under the new semantics with no prompt change.
- **Rejected alternative:** a new exit code (e.g. `4 suspended`) for `status` and `wait`. It adds a code every runtime must learn and keeps "stop" one misread away. It also collides with the watcher's `4 superseded`.
- **Rejected alternative:** keep exit `2` and only reword the docs. Live use shows that agents stop on `2`, and the sketch requires the participant to stay in the wait/watch path.

**Recipient-scoped messages (simplicity boundary).** Add one session field, `status.architect_message_for` (`"draftor"`, `"reviewer"` or `null`):

| Who sets it | Recipient |
|---|---|
| Interject | The current turn owner |
| Unblock resolving a decision | `decision.request.role` (the escalator) |
| Unblock of a pause, with a message | The resumed role |
| Extend / reopen | The resumed Draftor |

Display and clearing follow the same rule: the recipient sees it in `status` / `wait`, and only the recipient's own submission (or a terminal transition) clears it. `null` keeps today's behaviour (turn owner sees it, any submission clears), so in-flight sessions are unchanged. `architect_response_artifact` follows the same recipient.

**No new liveness notification kind (deliberate).** When the escalator is also the resumed turn owner (the common case), the post-unblock `turn-ready` wakes it, and status shows the response. When the escalator is *not* the turn owner, it has no action to take. Its watcher or `wait` continues, and the response is shown in its status on its next check, and in any case at its next turn, because no one else can clear it. A fourth `architect-response` kind would widen the strict liveness allowlist and need its own expiry rules for no actionable gain. This is reversible if the Architect wants an immediate wake.

**Pause reason** moves to `status.pause_reason`. It is no longer `architect_message`, so a pause no longer overwrites participant messages. Participants and the Architect both see it as the hold reason.

**Legacy compatibility:** a session paused before upgrade has no `suspended_at` key. When `advance_unblocked` sees that key absent and stage `paused_by_architect`, it keeps the old "replace `architect_message`" behaviour, so the old pause reason is not later shown as a message.

**Constraints honoured:**
- Interject stays an active-turn path. It is not mixed with suspension.
- Liveness never writes session state. The leaf-lock order is unchanged.
- Ack means received.
- No dispatch, no auto-submit, no auto-retry.
- `#54/#57`, `#37` and `#42` are untouched.

## Changes

Ordered by dependency.

### 1. Single suspend/restore path (Checkpoint 1)
- File: `src/gator_command/scripts/loop/state_machine.py`
- What:
  - Add `_suspend(session, stage, pause_reason=None)`. It requires `is_active`; sets `resume_stage`, `resume_next_role`, `suspended_at` (ISO UTC) and `pause_reason` (pause only, else `None`); sets stage, `next_role=None` and `blocked=True`; calls `_end_turn`. `advance_escalated` and `advance_paused_by_architect` become thin callers. Escalate keeps `architect_action_required=True`. Pause **no longer touches `architect_message`**.
  - Add `_clear_suspension(status)`, which nulls `resume_*`, `suspended_at` and `pause_reason`. It is used by `advance_unblocked`, `advance_extended`, `advance_reopened`, and **newly** by `advance_ended_by_architect`.
  - `advance_unblocked(..., message=None, recipient=None)` keeps its validation. It sets `architect_message` / `architect_message_for` **only when a message is given**, otherwise it leaves them intact. It keeps the legacy branch above.
  - Add `_consume_architect_message(status, role)`. It clears the message and the response artifact when `architect_message_for in (None, role)`. It replaces the unconditional clears in `advance_draft_submitted`, the `advance_review_submitted` revision path, `advance_implementation_submitted` and the `advance_implementation_reviewed` revision/next-checkpoint paths. Terminal paths (approve, max rounds, end, timeout) clear unconditionally, as today.
  - `advance_interjected(session, message)` also sets `architect_message_for = status.next_role`.
  - `advance_extended` / `advance_reopened` set the recipient to the resumed Draftor.
- Why: one validated path, no stale resume targets, and no lost messages.

### 2. Decision resolution and recipient (Checkpoint 1)
- File: `src/gator_command/scripts/loop/submit.py`
- What:
  - `handle_unblock` passes `recipient = pending[-1]["request"]["role"]` when it resolves a decision. Otherwise it passes the target role. The response contract and pre-mutation validation are unchanged.
  - `handle_pause` stores the reason via `advance_paused_by_architect(pause_reason=…)`. The turn and the `loop_paused` event are unchanged.
  - `handle_end`, when a decision is pending, records `response = {message: reason, artifact_path: null, kind: "cancelled_by_end", ts}`. This is an additive `response.kind` value. The `loop_ended_by_architect` event gains additive `decision_id`.
  - `handle_escalate` is unchanged. Its existing validation already forbids escalation while suspended, so there is never more than one pending decision.

### 3. Recipient-aware message display (Checkpoint 1)
- File: `src/gator_command/scripts/loop/cli.py`
- What:
  - Add `_message_for_role(session, role)`, which returns `(message, artifact)` when `architect_message_for == role`, or when it is `None` and it is `role`'s turn.
  - Model `status` / `wait` text and JSON use it. JSON `architect_message` keeps its key, but is now `null` for a non-recipient.
  - Text prints `Architect message:` (with an `Architect response (decision-N):` label when it resolves a decision) **whether or not it is the recipient's turn**. Multi-line messages print with continuation lines indented by four spaces.

### 4. Participant status/wait through suspension (Checkpoint 2)
- File: `src/gator_command/scripts/loop/cli.py`
- What:
  - `_cmd_status` model view: a paused session exits `1`.
    - Text: `Architect hold -- paused by the Architect` (plus `Reason:`), or `Awaiting Architect decision <id> (requested by <role>)`, then `Resumes with: <role> (<stage>)` and `You are still a loop participant. Wait with:` followed by the bounded wait command.
    - JSON gains additive `suspension: {kind: "architect_hold"|"architect_decision", resume_stage, resume_role, since, reason, decision_id}`, built from validated fields. `reason` applies to a pause only. `decision_id` applies to a block only.
  - `_wait_for_actionable` no longer returns on paused. The wake reasons become `terminal`, `already_your_turn`, `became_your_turn` and `still_waiting`. The `is_paused` parameter stays for call-site compatibility and is used only for rendering.
  - `_cmd_wait` exits `2` only when terminal. A bounded deadline during suspension exits `3` with suspension-specific text ("Loop suspended (...). You are still a loop participant. Reissue the same command now:") and the same additive `suspension` JSON.
  - The architect view gains the same additive `suspension` JSON and prints the preserved role, stage and `since`. Architect exit codes are unchanged (out of scope).

### 5. Watcher stays registered through suspension (Checkpoint 2)
- File: `src/gator_command/scripts/loop/liveness.py`
- What:
  - In `run_watch`, a delivered `architect-block` is acked and **does not end the watch**. The registration stays `active` (poll heartbeats it), and polling continues until `turn-ready` (exit `0`), `terminal` (exit `2`, closed) or the deadline.
  - At the deadline it exits `3 still_waiting` (released, as today), with additive `suspended: true` and `stage` when the loop is suspended. That state comes from a one-shot unlocked `load_session`; a read failure omits the fields.
  - `_DELIVERY_OUTCOME` no longer maps `architect-block` to an exit. `architect_block` remains a documented legacy wake reason for older watchers ("relaunch").
  - `_apply_projection`, `state_key`, the notification kinds and the leaf-lock order are unchanged.

### 6. Participant protocol and entry points (Checkpoint 2)
- Files (byte-identical pairs updated together):
  - `.gator/.includes/procedures/gator-loop-protocol.md` and the starter copy;
  - `.gator/.includes/reference-notes/loop-participant-watcher.md` and the starter copy;
  - `.claude/commands/loop-join.md` and `src/gator_command/templates/gator-starter/commands/loop-join.md`;
  - `src/gator_command/scripts/gatorize/entry_points.py` (`render_entry_content`), plus the regenerated managed regions in live `CLAUDE.md`, `AGENTS.md` and `GEMINI.md`.
- What:
  - Step 1 exit codes: `status` exits 0/1/2 with `2 = ended`, and a paused loop is `1`. `wait` exits 0/3/2 with `2 = ended`.
  - The State Machine "Paused" summary line changes to say that `status` exits `1` and `wait` keeps waiting.
  - Add a short "Suspension Is Not Departure" subsection:
    - stay in bounded wait/watch;
    - resume from `status`, never from a pasted prompt;
    - a submission rejected as blocked keeps your file, so wait and resubmit after unblock;
    - read `Architect response (decision-N)` when shown;
    - escalate only for Architect-owned decisions.
  - Watcher exit table: drop `2 architect_block` as a current outcome, and add a note that older watchers may print it, in which case relaunch.
  - Entry paragraph: "exit 2 means the loop ended".
  - No time language is added (the `TestParticipantDocs` rule).

### 7. Architect workspace (Checkpoint 3)
- Files: `src/gator_command/scripts/dashboard/views/loop.js`, `src/gator_command/scripts/dashboard/dashboard.css`
- What:
  - **Suspension card.** Replace `renderBlockedCard` with `renderSuspensionCard`, driven by `s.stage` plus `pendingDecision()` plus the new status fields. `/status` already passes the whole `status` dict and `decisions`; **no server change**.
    - **Blocked:** title "Blocked — awaiting your decision" with a ⏸ glyph and a text label. It shows the requesting role, the request time, the full reason (`textContent`, `white-space: pre-wrap`), a "View decision request" link when there is an artifact, and "Resumes: <role> · <stage>".
    - **Paused:** title "Architect hold (paused)" with a distinct glyph. It shows "Preserved: <role> · <stage>", since, and the reason, and states "No participant response is required." It never uses the escalation wording.
    - The distinction is carried by text, glyph and border style, never by colour alone (Architect is colourblind).
    - `blockedFingerprint` covers stage, `suspended_at`, `pause_reason`, `resume_*`, and pending decision id/ts.
  - **Multiline input.** The shared control input becomes a `<textarea rows="4">` with an associated `<label>`. It keeps the existing `.loop-ctrl-input` class and validation. The unblock label reads "Response to <role> (required)" for a decision. `controlsFingerprint` is unchanged, so typed text survives unchanged polls (existing rule).
  - **Decisions history.** Add a `#loop-region-decisions` region listing every `decisions[]` entry: request (role, time, reason, artifact link) and response (kind label including "Cancelled — loop ended", message, time, artifact link). Text is rendered via `textContent`, and its fingerprint covers ids plus response ts. Pause/resume stay in the timeline (existing `loop_paused` / `loop_unblocked` cards); event detail gets `pre-wrap`.
  - **Post-unblock action notice** (action slot): "Unblocked. <role> resumes at <stage> when its watcher or wait sees the change; the Dashboard does not run model work."
  - **Liveness panel:** when the loop is suspended and a role is `connected`, show "Connected — waiting through the hold" as a text suffix derived from stage. There is no liveness schema change.

### 8. Charters and commit draft (each checkpoint, alongside its code)
- See Charter Impact.

## Dependencies and Ordering

- **Checkpoint 1 → 2 → 3, strictly.** Checkpoint 2's status text reads the suspension fields from Checkpoint 1. Checkpoint 3 renders the fields and the decision kinds from Checkpoint 1, and its wording matches the protocol from Checkpoint 2.
- **Within Checkpoint 1:** `state_machine` first, then `submit`, then the `cli` display.
- **Within Checkpoint 2:** `cli` and `liveness` in parallel; the docs and entry points last, then a full regeneration check of the drift-pinned copies.
- **No migrations.** New fields are additive. Absent keys mean legacy behaviour.

## Assumptions, Risks, and Required Architect Decisions

- **Non-blocking assumption (A1): exit `2` = terminal only for participants.** A suspended `status` exits `1`; `wait` keeps waiting. This changes a documented participant contract (significance check at commit time). It is reversible by restoring the two exit branches. I recommend it as the only design that satisfies "stay in the bounded wait/watch path" without a new code.
- **Non-blocking assumption (A2): no `architect-response` liveness kind.** The response reaches the escalator through recipient-scoped status. I will add the kind if the Architect wants an immediate wake for a non-turn-owner escalator.
- **Non-blocking assumption (A3): Architect CLI exit codes are unchanged** (paused → `2`). Only participant semantics are in scope.
- **Non-blocking assumption (A4):** `response.kind = "cancelled_by_end"` is additive vocabulary. `TestStructuredDecisionRequests` is extended, not rewritten.
- **Risk:** the drift-pinned copies (protocol, watcher note, `/loop-join`, three entry points). Mitigation: update every pair in Checkpoint 2, and run `TestWaitHandoffAlignment`, `TestParticipantDocs` and `TestDriftGuards`.
- **Risk:** in-flight paused loops at upgrade. Mitigated by the absent-`suspended_at` legacy branch, with one test.
- **Risk:** a watcher running through a long hold holds a registration for up to `--max-seconds`. That is bounded, and exits `3` as today.
- **No blocking Architect decisions.**

## Testing

Focused, parameterized, one group per invariant:

**Checkpoint 1** (new `tests/test_loop_suspension.py`):
1. **Transition table**, parameterized over {planning, coding-checkpoint} × {pause, escalate} × {draftor turn, reviewer turn}. Suspend, then unblock, restores the exact stage and role, the checkpoint `current` is unchanged, and `resume_*` / `suspended_at` / `pause_reason` are null afterwards. Escalate records a decision, and unblock resolves it with the correct recipient.
2. **Mixed sequence.** Interject → pause → unblock (no message) → reviewer escalates during the Draftor's turn → unblock with a multiline response → Draftor submits → end. Asserts:
   - the interjection survives the pause;
   - the response survives the Draftor's submission and is shown to the reviewer only;
   - no stale resume target at any step;
   - end leaves no `resume_*`.
3. **End while blocked** records `cancelled_by_end`; end while paused clears the suspension fields.
4. **Legacy paused session** (no `suspended_at`) unblocks exactly as before.

Rejections leave the session byte-unchanged; this is already pinned, so only extend parameters where needed.

**Checkpoint 2:**
5. **Status/wait suspension**, parameterized over {paused, blocked}:
   - model `status` exits `1` with the `suspension` JSON;
   - bounded `wait` exits `3` during suspension and `0` after unblock for the resumed role;
   - `wait` exits `2` after end (`tests/test_loop.py`, existing wait suite).
6. **Watcher lifecycle** (`tests/test_loop_liveness_lifecycle.py`):
   - (a) watch, then pause, then unblock: one registration and generation throughout, `architect-block` acked, exit `0 turn_ready`;
   - (b) watch, then escalate, then end: exit `2 terminal`, closed;
   - (c) deadline during a hold: exit `3` with `suspended: true`, released.
7. **Restart idempotency** (`tests/test_loop_liveness_projection.py`): repeated `project` / `sweep` (a Dashboard restart or sidecar reload) across pause → unblock → pause gives exactly one `architect-block` per suspension and one `turn-ready` per resume. Unregistered roles still fall back to `wait`.
8. **Drift guards:** update the expectations of `TestWaitHandoffAlignment`, `TestParticipantDocs`, `TestDriftGuards` and the protocol-state-table tests for the new exit text. There are no new guard classes.

**Checkpoint 3** (`tests/test_dashboard_ui/test_loop_workspace.py`, Playwright):
9. The blocked card shows the role, time, full multiline reason and artifact link. The paused card shows the hold wording and the preserved role and stage, and never the escalation wording.
10. A textarea draft survives repeated unchanged polls, and those polls are mutation-free (MutationObserver, existing pattern).
11. The decisions history lists a resolved response and a `cancelled_by_end` entry. The post-unblock notice text appears, and it does not claim model work.

**Finish:** run the loop and dashboard suites (`pytest tests/test_loop*.py tests/test_dashboard_loop*.py tests/test_dashboard_ui/test_loop_*.py`), then the full suite once.

## Charter Impact

- `scripts-loop.md`:
  - update `advance_escalated`, `advance_paused_by_architect`, `advance_unblocked`, `advance_ended_by_architect`, `advance_interjected`, `advance_extended` and `advance_reopened`, and the submission advances (message consumption);
  - add `_suspend` / `_clear_suspension` / `_consume_architect_message`;
  - update `handle_unblock`, `handle_pause` and `handle_end` (`cancelled_by_end`);
  - update `_cmd_status` / `_cmd_wait` / `_wait_for_actionable` (exit contract, `suspension` JSON, `_message_for_role`), `run_watch` (block acked, not an exit) and the `D3` note ("Pause, unblock, escalate and end keep `current`");
  - **new TRIPWIRE "Suspension Is Not Departure":** exit `2` is terminal only; resume fields exist iff suspended; pause never writes `architect_message`; messages are recipient-scoped.
- `scripts-cross-cutting.md`: participant exit-code contract change; additive `suspension` in `gator-loop-status-v1` and additive `suspended` / `stage` in `gator-loop-participant-v1` `still_waiting`; additive `response.kind` and the `decision_id` event field; updated pin descriptions.
- `scripts-installer.md`: `render_entry_content` text ("2 = loop ended").
- `scripts-dashboard-ui.md`: suspension card (replaces the blocked-card note), textarea control, decisions region, unblock notice, and liveness suffix.
- `scripts-dashboard.md`: no change (the `/status` allowlist already passes `status` and `decisions`).

## Coding Checkpoints

1. **Suspension state and resume integrity** — single validated suspend/restore path (`_suspend` / `_clear_suspension`), pause reason and suspension timestamp fields, recipient-scoped Architect messages that pauses, unrelated unblocks and the other role's submission never erase, end resolves a pending decision as `cancelled_by_end`, and recipient-aware message display in model status/wait.
  Verify: `tests/test_loop_suspension.py` transition table, mixed sequence, end-while-suspended and legacy-pause tests, plus the existing escalate/unblock/extend/reopen suites.
2. **Participant liveness across suspension** — status exits 1 and wait keeps waiting through pause/block (exit 2 terminal only) with additive `suspension` JSON, the watcher acks `architect-block` and stays registered until turn-ready/terminal/deadline, and the drift-pinned protocol, watcher note, `/loop-join` and entry points describe the new contract.
  Verify: wait/status suspension tests, watcher lifecycle and restart-idempotency tests, and the updated `TestWaitHandoffAlignment` / `TestParticipantDocs` / `TestDriftGuards` guards.
3. **Architect workspace for suspension** — distinct blocked and paused cards from real session fields, multiline response textarea that survives polling, decisions and pause history, post-unblock notice that claims no model work, and the connected-through-hold liveness wording.
  Verify: Playwright loop-workspace tests for card content, textarea preservation with mutation-free polls, decision history and notice text.
