---
message: "Loop: Architect attention intervals replace participant turn timeouts (#47)"
change-type: feature
significance: high
decision-tags: [loop, attention, timeout, dashboard, governance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Implementation plan for #47 (Architect attention intervals instead of participant timeouts), APPROVED at rev 2 (P1: crash-safe attention recording, with the event first and the marker second, a recovery scan, a newline guard for torn lines, a documented write-ordering exception and fault-injection tests), rev 1, no code changes: `.gator/vault/artifacts/2026-10-03-loop-architect-attention-interval-implementation-plan.md`.
- #47 M1 (the attention-interval contract and turn-start recording; plan rev 2 approved):
  - `session.py`:
    - `ATTENTION_INTERVAL_CONTRACT`, `DEFAULT_ATTENTION_INTERVAL` (300, unchanged) and `attention_mode()`, a strict int ≥ 1, non-bool gate;
    - `create_session` flags every new session (planning `{context_evidence, attention_interval}`, coding `{attention_interval}`) and starts the first turn with `turn_started_at`, no deadline, and `attention_notified_turn: null`.
  - `state_machine.py`: `_begin_turn()` / `_end_turn()` replace the 8 deadline-setting and 8 deadline-clearing sites. Flagged sessions record `turn_started_at` and never a deadline; legacy sessions are byte-identical to before.
  - Tests:
    - new `tests/test_loop_attention.py` (27): the contract shape, a strict predicate, every begin and end transition for planning and coding, interject untouched, and legacy deadline semantics with no attention fields. Mutation-checked: a disabled gate fails 6 tests and a bool-accepting predicate fails 1.
    - Legacy deadline / `unblock --timeout` tests in `test_loop.py` now run against an explicit legacy session (`_legacy`, plus an autouse fixture on `TestUnblockTurnWindow`).
    - Contract-shape pins are updated in `test_loop_context_evidence.py`, `test_loop_brief.py` and `test_loop_coding_mode.py`.
  - Charter: `scripts-loop.md` (`attention_mode`, the create_session contract, `_begin_turn` / `_end_turn`).
- #47 M2 (crash-safe attention emission):
  - `host.py`:
    - `watch_loop` Phase 2 branches on `attention_mode`: flagged loops go to `_try_record_attention` behind an unlocked pre-check, with exceptions swallowed and the next poll converging; legacy loops get unchanged deadline enforcement.
    - `_try_record_attention` writes the event first and the marker second, with a recovery scan (`_find_attention_event` via `read_all_events`) and a torn-line newline guard (`_ensure_events_newline`).
    - `_attention_due` (pure).
    - `_try_enforce_timeout` refuses flagged sessions (defense in depth).
  - `events.py`: the `architect_attention_due` label "ATTENTION" (not terminal).
  - `liveness.py`: `state_key` includes `turn_started_at` only when present, so legacy hashes are unchanged and recording attention never notifies a participant.
  - Tests: `tests/test_loop_attention.py` +24, for 51 total:
    - emission once per turn, stays active, racing observers (4 threads), a new turn giving an independent event, paused or terminal never recording, a minimal payload;
    - fault injection a–f (emit raises; save fails after the append; a crash after the append; a torn trailing line; another turn's key; no writes after convergence);
    - liveness key pins;
    - a real `watch_loop` thread (records once and keeps hosting, survives a recording error, legacy still times out).

    Six mutants were killed: no recovery scan, no newline guard, marker-first ordering, an enforcer ignoring the flag, the liveness key including the marker, and an unconditional liveness key.
  - Existing forced-timeout tests now explicitly use legacy sessions: `TestTimeoutEnforcement` autouse, `_to_stage("turn_timed_out")`, `test_wait_returns_on_terminal`, `set_session(turn_deadline=…)` in the coding tests, and two liveness projection tests.
  - Charter `scripts-loop.md`:
    - the `_try_record_attention` family;
    - the `watch_loop` Phase 2 branching;
    - the enforcer's legacy-only guard;
    - the `state_key` material;
    - the documented sole exception to TRIPWIRE "Session Lock Write Ordering".
- M2 review fix (whiteboard M2-1): `_attention_due` rejects naive (offset-less) timestamps and guards the comparison against `TypeError` / `OverflowError`, so it never raises on malformed status. `TestAttentionMalformedTimestamps` adds 10 tests (unit cases, a recorder no-op, and a real watcher that keeps hosting with no event); removing the guard fails 5 of them.
- #47 M3 (CLI and participant language):
  - `cli.py`:
    - Participant status JSON and wait JSON omit `turn_timeout_seconds` / `turn_deadline`, and `_print_turn_window(session)` prints nothing, for `attention_mode` loops.
    - Architect JSON gains an additive `attention` view. The text view shows the interval, elapsed time and the due/notified state.
    - The paused view drops the `--timeout` hints. Unblock, extend and reopen print the attention interval.
    - The host-attach and Ctrl+C wording is per loop (`_host_duty`).
    - `start --attention-interval` is added, with `--turn-timeout` kept as an alias.
    - Legacy loops are unchanged.
  - `submit.handle_unblock` refuses `turn_timeout` on flagged loops inside the lock, before mutating.
  - `host` banner: "Attention interval".
  - Docs, pairs byte-identical:
    - Protocol: line 17; Rule 7 rewritten as "Work at the pace the artifact needs" (no participant deadline, escalate only for genuine blockers, never to negotiate time, plus a legacy note); Rule 10 and the state-table `turn_timed_out` marked legacy-only; the good/bad participation bullets; the escalation and coding-loop wording.
    - `loop-participant-watcher.md`: `--max-seconds` guidance, and the Re-notify line.
  - Tests:
    - `test_loop_attention.py` +22 (83 total): participant status, wait JSON and text are time-free while legacy is unchanged; Architect JSON and text attention, before and after the notice; unblock `--timeout` refused with no state change; the unblock and paused views; `start` flag, alias and default; doc drift guards.
    - Four mutants killed: the JSON strip disabled, the window line shown, `--timeout` allowed, and the paused hint always legacy.
    - Three `test_loop.py` wording pins are updated for attention loops.
  - Charters: `scripts-loop.md` (`handle_unblock` refusal, participant silence, Architect view); `scripts-cross-cutting.md` (new doc drift pins).
- #47 M4 (Dashboard server):
  - `POST /loops/start` accepts `attention_interval` (preferred) or the `turn_timeout` alias. Both is a 400, and the error names the field.
  - `/status` gains an explicit `attention` projection via the new `host.attention_status_view` (field by field). `notified` is the marker OR a matching event; the event log is scanned only when the turn is due and the marker is missing. Legacy loops have no key.
  - Unblock `timeout` on an attention loop returns a 400 with Dashboard wording (the in-lock refusal; nothing written).
  - Tests: new `tests/test_dashboard_loop_attention.py` (26): start field, alias, default, both, out-of-range; projection shape, notified and legacy absence; view units (not due, due, event-before-marker, no-scan guards, malformed primitives, legacy); unblock refusal leaving bytes unchanged, then a plain unblock; prompts free of time words. Five mutants killed.
  - Charters: `scripts-dashboard.md` (start, status, unblock and prompt contract); `scripts-loop.md` (`attention_status_view`).
- #47 M5 (Dashboard UI):
  - `views/loop.js`:
    - Attention loops show "Elapsed this turn · attention after N min" in place of the countdown, as a text-only patch; legacy loops keep their countdown.
    - A new `attention` notice slot, owned by `setAttentionNotice()`, is written only when its state changes. It gives a text-led ◷ notice (notified, or "no notice recorded yet (is a loop host running?)") with `role=status`, never touches the other slots or open controls, and clears on turn change.
    - A sidebar "◷ attention" marker comes from `/loops` and is kept live for the selected loop.
    - The unblock control has no turn-window field and never posts `timeout` for attention loops.
    - The create form gets the "Architect attention interval" label and hint, and posts `attention_interval`.
  - `dashboard.css`: `.loop-attention-notice` (dashed border, glyph, no error colour), `.loop-card-attention`, `.loop-attention-hint`.
  - `gator-dashboard.py`: `/loops` items gain `attention_notified` (marker-only).
  - Tests:
    - New `tests/test_dashboard_ui/test_loop_attention_ui.py` (9 Playwright): elapsed header; the notice once with zero non-elapsed mutations across identical polls; the unrecorded text; coexistence with an action notice and a half-typed interject; clearing on turn change; the legacy countdown; the sidebar marker; unblock without a timeout field or post; the create form label and `attention_interval`.
    - Six UI mutants killed.
    - `test_dashboard_loop_attention.py` gains a `/loops` `attention_notified` test (27 total).
  - Charters: `scripts-dashboard-ui.md` (the attention UI contract); `scripts-dashboard.md` (the list field).
- M5 review fix (whiteboard P2):
  - The "host not running" wording is now authoritative. New `host.probe_host_state()` makes a single non-blocking `host.lock` attempt: attached, none (released immediately) or unknown.
  - `attention_status_view` adds `host` only in the due-and-not-notified state; it is never probed otherwise.
  - The UI wording follows only that value ("no loop host is running…" / "notice pending…" / a neutral "no notice has been recorded for this turn yet"). Host absence is never inferred from a missing marker.
  - Tests: +8 server (probe none-and-released, held→attached, unopenable→unknown, the view's due states, a probe exception, never probed outside due-unnotified, a bogus value) and +3/+1 UI (the three host states, and a host-change rewrite). Two mutants killed: the UI inferring absence, and probing on every poll.
- #47 M6 (release notes and follow-up):
  - `scripts-loop.md`: a new TRIPWIRE "Attention Is Architect Awareness, Never Participant Pressure or State". It says time never changes the state of flagged loops; there is one event per turn, written only by the host; participants never see time; host state is never inferred; legacy loops are unchanged.
  - `CHANGELOG.md` `[Unreleased]` / Changed: the #47 entry plus upgrade notes. In-flight loops are unaffected, and a host must run to record notices.
  - Follow-up issue #50 (opt-in email/SMS delivery of `architect_attention_due`, with optional mid-loop interval change) is filed under #5.
- M6 review fix (whiteboard P1): older charter entries now distinguish attention-mode and legacy behaviour explicitly, so neither contract reads as unconditional.
  - `scripts-loop.md`:
    - the Owns summary and the `host.py` ownership line;
    - `advance_unblocked`, `advance_extended`, `advance_implementation_submitted` and `advance_reopened`, which now start a fresh turn via `_begin_turn` (flagged: `turn_started_at`, no deadline; legacy: deadline);
    - the `watch_loop` filesystem line;
    - `host.lock` ownership;
    - the enforcer's write-exception note and the Host Contract section (attention writes only awareness metadata);
    - `_cmd_reopen` / `_attach_foreground_watcher`, `_cmd_extend`, `_cmd_unblock` (`--timeout` legacy-only) and `_cmd_wait` (time fields legacy-only).
  - `scripts-dashboard-ui.md`: the generic Unblock entry (the Turn window field is legacy-only), the #38 skeleton enumeration (three notice slots, P2), incremental rendering (header and controls fingerprints, the elapsed patch, `setAttentionNotice`), and the notice slots (three slots, attention owner).
  - `scripts-dashboard.md`: the extend watcher honesty note.
  - `scripts-cross-cutting.md`: the validation authority covers the attention interval, and `--timeout` / `timeout` are legacy-only.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
