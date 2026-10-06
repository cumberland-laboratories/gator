---
message: "Loop: durable non-terminal suspension and participant liveness (#53)"
change-type: feature
significance: notable
decision-tags: [loop, liveness, dashboard, governance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- **Checkpoint 1: suspension state and resume integrity (#53).**
  - **State machine:** `state_machine.py` has one validated suspend path (`_suspend`) and one clear path (`_clear_suspension`). Resume fields exist only while paused, and a suspension records `suspended_at`. A pause stores its reason as `pause_reason` and no longer writes `architect_message`.
  - **Messages:** Architect messages are recipient-scoped (`architect_message_for`), and a decision label is bound to its response message (`architect_message_decision`). An unblock without a message keeps an unread one, and a submission consumes only its own role's message, so an escalation response reaches the escalator even when it is not the resumed turn owner.
  - **End:** `handle_end` resolves a pending request as `cancelled_by_end`.
  - **CLI:** model `status` / `wait` show the message to its recipient, plus an "Architect response to your escalation" line, and indent multi-line messages.
  - **Compatibility:** legacy paused sessions unblock as before.
  - **Tests:** new `tests/test_loop_suspension.py`; `test_pause_from_active` updated for `pause_reason`.
  - **Charters:** `scripts-loop.md` (new helpers and TRIPWIRE) and `scripts-cross-cutting.md` (additive fields).
- **Checkpoint 2: participant liveness across suspension (#53).**
  - **Exit contract:** exit `2` from participant `status` / `wait` / `participant watch` now means the loop ended. A paused or blocked loop gives `status` exit `1` with "Architect hold" or "Awaiting Architect decision" text, and `wait` keeps waiting (`3` at a bounded deadline).
  - **Watcher:** it acks `architect-block` and stays registered through the suspension, and its `still_waiting` output adds `suspended` / `stage`.
  - **JSON:** additive `suspension` in `gator-loop-status-v1`.
  - **Docs:** the protocol (new "Suspension Is Not Departure" section), watcher note, `/loop-join`, `render_entry_content` and the live CLAUDE.md / AGENTS.md / GEMINI.md regions were updated, with byte-identical pairs kept in sync.
  - **Tests:** status/wait suspension, watcher-through-suspension lifecycle and restart-idempotency tests added; old "paused ends the wait" tests updated.
  - **Charters:** `scripts-loop.md`, `scripts-cross-cutting.md`, `scripts-installer.md`.
- **Checkpoint 3: Architect workspace for suspension (#53).**
  - **Cards:** the Dashboard suspension card is rebuilt from real session fields. Before, the blocked card keyed on a never-written `escalation_reason` and never rendered. Blocked shows the decision, requester, time, multi-line reason, request link and resume target; paused shows a distinct "Architect hold" (dashed border, glyph, text) with the preserved role/stage and reason.
  - **Controls:** a labelled multiline textarea that survives mutation-free polls, and a required-response label that names the escalating role.
  - **History and notices:** decision history covers resolved and `cancelled_by_end` requests; a post-unblock notice says who resumes and that the Dashboard does no model work; the liveness panel shows "Connected — waiting through the hold".
  - **Tests:** the blocked-loop UI seed now uses the real session shape; Playwright tests pin card content, hold wording, textarea preservation with zero mutations, decision history and the notice.
  - **Timeline:** pause, unblock, escalation, interjection and end events show their full multi-line detail.
  - **Charter:** `scripts-dashboard-ui.md`.
