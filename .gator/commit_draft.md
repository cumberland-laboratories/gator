---
message: "Loop: participant liveness bridge — background watcher, Dashboard liveness view, Architect Re-notify (#36)"
change-type: feature
significance: high
decision-tags: [loop, liveness, dashboard, security, governance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Add implementation plan for the loop participant liveness bridge (#36 remainder): `.gator/vault/artifacts/2026-09-29-loop-participant-liveness-bridge-implementation-plan.md` (rev 1, for plan review; no code changes).
- Revise the liveness plan to rev 2 per the whiteboard P1 finding: add D2a (the supervised background-watcher receiver contract, with Claude Code background tasks as the first supervisor and Codex deferred to a follow-on issue); add the registration lifecycle (active/released/closed); align `watch` exit codes with `wait`; add a supervised end-to-end lifecycle test (M3/M4) and receiver-contract docs (M6). Resolution noted on the whiteboard.
- Revise the liveness plan to rev 3 per the whiteboard re-review: add the M0 vendor spike and release gate (a version-pinned manual proof that Claude Code background Bash re-invokes an idle agent); demote Claude Code to a candidate supervisor until M0 passes; narrow the claim to an open session with an idle agent; pre-decide the experimental-adapter fallback; make the M5/M6 vendor copy conditional on M0.
- Run the M0 vendor spike and record it at `.gator/vault/artifacts/2026-09-29-liveness-m0-vendor-spike.md`: it passes on Claude Code 2.1.283 on Windows 10. A background Bash exit re-invoked the idle agent about 3 s later with no user input; the output is delivered as a file path. The negative control is still pending. D2a is updated with the result and the M2 single-JSON-line stdout requirement.
- #36 M1: add `src/gator_command/scripts/loop/liveness.py`, the private per-worktree participant-liveness store at `$(git rev-parse --git-path gator-loop-liveness)/<loop_id>.json`. It provides:
  - a strict schema allowlist that also recursively rejects token-shaped strings;
  - atomic writes that are LF-only, retry on Windows `PermissionError`, and never leave a temp file behind;
  - lock-free `read()` for observers, and a `with_lock()` mutation path with a leaf lock that quarantines corrupt files instead of deleting them;
  - `resolve_store_dir()`, which returns `None` when the store is unavailable;
  - the pure helpers `state_key()` (the idempotency key), `classify()` (connected / stale / released / closed / expired / not registered), `prune()` (retention) and `redact()` / `sanitize_text()`.
- Add `tests/test_loop_liveness_store.py` (76 tests).
- Add `scripts/loop/liveness.py` to pyproject package-data.
- Charters: `scripts-loop.md` (Covers, Owns, the LivenessStore/validator/helper entries, a new TRIPWIRE "Liveness Store Is a Leaf Lock and Never Authority"); `scripts-cross-cutting.md` (explicit package-data rule; per-worktree Git-private state).
- #36 M1 review fix (whiteboard P2): corrupt-file quarantine now retries the rename and reports failure. If the original cannot be preserved, `with_lock()` raises `LivenessUnavailableError` without running the mutation, so a corrupt file is never overwritten. Lock-free `read()` returns `None` (`last_error="unavailable"`) on a transient `OSError`. Documented that all-pending notifications may exceed the per-role cap. Added 5 tests (81 total); the P2 regression was verified to fail against the pre-fix code.
- #36 M2: participant API in `loop/liveness.py`: `authenticate()` (redacted errors; architect token rejected), `open_store()`, `register` / `heartbeat` / `poll` / `ack` / `release` (token plus registration id on every call; `hmac.compare_digest`; `SupersededError`), `own_status()`, `public_notification()`, and the D2a receiver `run_watch()`.
  - The generation is monotonic across all role history, so a registration dropped by retention is never reused.
  - `poll` redelivers pending records to a new generation.
  - `ack` is limited to records delivered to the current generation.
  - `project()` is an M2 no-op stub that M3 replaces.
- New CLI `gator loop participant watch --token T --max-seconds N [--poll-seconds S] [--adapter-label L] [--json]` and `participant status`.
  - Exit codes: 0 turn_ready, 2 architect_block/terminal, 3 still_waiting, 4 superseded, 1 error, 130 interrupted (SIGTERM mapped to Ctrl+C).
  - `--json` prints exactly one JSON line with empty stderr. Output never contains the token or the registration id.
- Added `tests/test_loop_liveness_cli.py` (33 tests, including real-subprocess CLI contract tests).
- `scripts-loop.md`: 14 subcommands, plus new entries for the participant API, `run_watch` and the CLI handlers.
- #36 M2 review fix (whiteboard P2): `closed` registrations are one-way. The new `RegistrationClosedError` rejects heartbeat/poll/ack/release on a current closed registration without writing, and only a fresh `register()` supersedes it. `run_watch` reports a mid-watch close as exit 2 `terminal`. Added 2 regression tests (verified to fail on the pre-fix code).
- #36 M3: real D5 projection in `loop/liveness.py`: `project()`, `_apply_projection()`, `project_for_host()`, `open_host_store()` and the pure `renotify_eligibility()`.
  - It snapshots `session.json` without the session lock (a torn read returns `retry`), then applies the rules under the liveness leaf lock:
    - expire pending records from older generations;
    - one `turn-ready` per (next_role, state_key), recorded even for an unregistered role;
    - `architect-block` and `terminal` records only for registered, non-closed roles;
    - close a registration that was already told for this terminal generation, so a late watcher exits 2 immediately;
    - set/clear `terminal_observed_at` (clearing covers #39 extensions);
    - then prune. It saves only on change, and deletes the sidecar when the loop dir is gone or after 7 days terminal.
  - It never reopens a closed registration and never writes loop state.
- `loop/host.py`: `watch_loop()` runs a guarded projection after each event batch and before a terminal return, retries `retry`/`error` on the next tick, and never raises (`_open_liveness_store`, `_project_liveness`).
- New tests:
  - `tests/test_loop_liveness_projection.py` (24): rules on real transitions, idempotency, lock order both ways, torn read, host failure isolation (timeout still enforced), restart recovery, retention, eligibility.
  - `tests/test_loop_liveness_lifecycle.py` (2, real detached subprocesses under a test supervisor): launcher exits, turn_ready exit 0 / released, relaunch, terminal exit 2 / closed, an immediate terminal exit on a further launch, a killed watcher goes stale and becomes Re-notify-eligible when its turn arrives, and no loop-state writes.
- Adapted the M2 in-process tests to stub projection and to seed with the real state_key; the subprocess still-waiting test now uses the reviewer.
- `scripts-loop.md`: `watch_loop` hook, a clarified Host Write Authority tripwire (loop-state writes only), and the `project` and `renotify_eligibility` entries.
- #36 M4 Dashboard: GET `/api/repo-by-key/<key>/loops/<id>/liveness` and POST `.../renotify`.
  - The GET uses the explicit allowlist serializer `liveness.observer_view()` with `no-store`. It never writes, and it degrades to `available: false` (`unavailable` / `retry`) or flags `corrupt` / `session_unreadable`.
  - Re-notify uses the anti-CSRF header, validates role and reason, and appends one `created_by: "architect"` record plus an audit entry under the liveness leaf lock only. It returns 409 with a reason code when ineligible, 429 when rate-limited (10 s per loop and role; a refusal does not consume the slot), and 503 when unavailable. It never writes loop state.
  - At startup, `_sweep_liveness()` runs the new `liveness.sweep()` retention pass, which is best-effort and never affects adoption.
- `liveness.py`: `observer_view()`, `renotify()`, `sweep()`. Lock-free `read()` now retries transient Windows read denials before degrading; found via a flaky E2E read that collided with a watcher write.
- Tests:
  - new `tests/test_dashboard_loop_liveness.py` (22): every state, the allowlist and secret exclusion, the degraded modes, the corrupt file left untouched, 403/400/404/409/429/503, no loop writes, `/status` and `/events` unchanged, the participant routes carrying no liveness data, the startup sweep, and a supervised lifecycle through the endpoint (connected, released, connected, closed; killed leads to stale and eligible);
  - one new store read-retry test.
- Charters: `scripts-dashboard.md` (the liveness and renotify handlers, `_sweep_liveness`); `scripts-loop.md` (`observer_view` / `renotify` / `sweep`, read retry).
- #36 M4 review fix (whiteboard P1): both liveness routes (the GET view and the POST Re-notify) now require Architect authority through the standard `_resolve_architect_token()` plus a nonce check that the stored token resolves to the `architect` role. A missing, malformed or architect-less token store gives 404; a wrong nonce gives 403. Every denial is `no-store` and writes nothing: no sidecar write and no rate-limit slot. The shared resolver is hardened: a malformed or non-object `.tokens.json` returns 404 instead of an unhandled 500 (this also covers the pause/interject/unblock/end/extend routes), and it gains a `cache_control` passthrough. Added 12 regression tests; the Re-notify cases were verified to fail on the pre-fix code.
- #36 M5 Dashboard UI: added a "Participant watchers" panel (`#loop-region-liveness`) to the loop view in `dashboard/views/loop.js`, with `fetchLiveness`, `postRenotify`, `refreshLiveness`, `applyLiveness` and an inline Re-notify reason form.
  - The panel is built once per selection and patched field by field; values are written only when they differ, and times are absolute data values rather than wall-clock relative text. Identical polls and repeated denials cause zero DOM mutations.
  - Each state is shown as text plus a glyph plus weight/style (colorblind-safe).
  - The Re-notify button appears only when the role is eligible, and a typed reason survives polling. Posts send the anti-CSRF header and `no-store`, with sent/refused notices in `#loop-region-notice`.
  - Degraded and denied modes are handled, and the fixed "not proof of work" footnote is included.
- `dashboard.css`: liveness styles.
- Added `tests/test_dashboard_ui/test_loop_liveness_ui.py` (8 Playwright tests).
- Found by the existing #38 test `test_identical_polls_do_not_touch_main_panel`: repeated `hidden` assignments caused attribute mutations; fixed with `setHidden()`.
- `scripts-dashboard-ui.md`: liveness panel contract.
- #36 M6 documentation/protocol:
  - `procedures/gator-loop-protocol.md` (both byte-identical copies): an optional background-watcher paragraph in Step 1 with the exit/relaunch table, Claude Code as the supported runtime (open session, 2.1.283), bounded `wait` required elsewhere, and the no-auto-submit / no-resume / ack-means-received boundaries; a quick-reference line.
  - `/loop-join` (`.claude/commands/` plus the template copy): the Claude Code background launch line and how to read the result.
  - New `reference-notes/loop-participant-watcher.md` (both copies): the supervisor/watcher/agent contract, exit table, JSON keys, semantics, storage and privacy, and the adapter extension point. It is added to both `gator_layout.py` shipped-defaults lists.
  - The vendor-neutral entry paragraph (`render_entry_content()`) is deliberately unchanged, because it is shared across vendors.
- CHANGELOG `[Unreleased]`: the #36 entry and the resolver hardening.
- Compatibility test `test_wait_unchanged_without_registration`: bounded `wait` keeps exits 0/3/2 and never creates the sidecar.
- Charters: `scripts-loop.md` (Cross-Vendor Orientation), `scripts-layout.md` (keep both layout copies in sync).
- Pre-commit SQL-003 false positive ("truncate" in a docstring): reworded the `sanitize_text()` docstring to "shorten"; no behavior change.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
