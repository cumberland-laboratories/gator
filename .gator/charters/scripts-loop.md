# Charter: Gator Loop

**Covers**: `src/gator_command/scripts/loop/__init__.py`, `src/gator_command/scripts/loop/session.py`, `src/gator_command/scripts/loop/events.py`, `src/gator_command/scripts/loop/state_machine.py`, `src/gator_command/scripts/loop/submit.py`, `src/gator_command/scripts/loop/host.py`, `src/gator_command/scripts/loop/cli.py`, `src/gator_command/scripts/gator-loop.py`

## Owns

The governed planning loop — a CLI-mediated debate between two AI models (draftor, reviewer) with role tokens, turn-taking, bounded iteration, timeout enforcement, and durable session residue.

- `session.py` owns session CRUD, token generation/resolution (with secret nonce), platform-aware file locking, atomic writes, turn tracking, and loop ID generation
- `state_machine.py` owns state categorization (active/paused/terminal), action validation, and all state transitions
- `events.py` owns event emission (append to events.jsonl), event tailing, and human-readable formatting
- `submit.py` owns the four submit handlers: submit-draft, submit-review, escalate, unblock
- `host.py` owns loop initialization (`gator loop start`) and the watch loop with timeout enforcement
- `cli.py` owns argparse subcommand routing for all 8 loop commands
- `gator-loop.py` is the thin entry script dispatched by `src/gator_command/cli.py`

## Does Not Own

- Dashboard integration (future phase)
- Auto-launching of agent sessions
- Code implementation loop (this is planning-phase only)
- Git commits of session residue (always human/agent-initiated)

---

### make_token(loop_id, role)
File: `src/gator_command/scripts/loop/session.py`
Generates a role token with secret nonce. Returns (token_string, nonce).
Filesystem: none (pure computation)
<- `host.start_loop()`
! Token format: `glp_<base64url(loop_id:role:nonce)>`. Nonce is 8 hex chars from `secrets.token_hex(4)`. Nonce stored only in gitignored `.tokens.json` — never in committed session state.

### resolve_token(token)
File: `src/gator_command/scripts/loop/session.py`
Decodes token and validates nonce against `.tokens.json`. Returns (loop_id, role, loop_dir).
Filesystem: `.gator/loops/<loop-id>/.tokens.json` (R)
<- `submit.handle_submit_draft()`, `submit.handle_submit_review()`, `submit.handle_escalate()`, `cli._cmd_status()`
-> `find_gator_root()`
! Raises ValueError on invalid/tampered tokens. Nonce validation prevents token reconstruction from committed data.

### create_session(feature, loop_id, max_rounds, turn_timeout)
File: `src/gator_command/scripts/loop/session.py`
Builds the initial session dict. Does not write to disk.
Filesystem: none
<- `host.start_loop()`

### load_session(loop_dir) / save_session(loop_dir, session)
File: `src/gator_command/scripts/loop/session.py`
Read/write session.json. Save uses atomic temp+rename. Sets read-only (444) on POSIX after write.
Filesystem: `.gator/loops/<loop-id>/session.json` (RW)
<- all loop modules
! Atomic rename prevents partial reads by the host's non-locking read path.

### with_session_lock(loop_dir, fn)
File: `src/gator_command/scripts/loop/session.py`
Acquires exclusive file lock, loads session, calls fn(session), saves + emits event, releases lock. Write ordering: session.json saved BEFORE event appended to events.jsonl, both inside lock.
Filesystem: `.gator/loops/<loop-id>/session.lock` (RW), `session.json` (RW), `events.jsonl` (W)
<- `submit.handle_submit_draft()`, `submit.handle_submit_review()`, `submit.handle_escalate()`, `submit.handle_unblock()`, `host._try_enforce_timeout()`
-> `load_session()`, `save_session()`, `events.emit_event()`
! Platform-aware: `fcntl.flock` on POSIX, `msvcrt.locking` on Windows. fn(session) returns (mutated_session, event_dict) or None to skip.

### append_turn(session, role, turn_type, summary, artifact_path)
File: `src/gator_command/scripts/loop/session.py`
Appends a turn entry with sequential ID (`<role>-<NNN>`).
Filesystem: none (mutates session dict in place)
<- `submit.handle_submit_draft()`, `submit.handle_submit_review()`, `submit.handle_escalate()`

---

### validate_action(session, role, action)
File: `src/gator_command/scripts/loop/state_machine.py`
Checks terminal, blocked, role, stage, and turn ownership. Returns (allowed, reason).
Filesystem: none
<- `submit.handle_submit_draft()`, `submit.handle_submit_review()`, `submit.handle_escalate()`
! Escalate bypasses the turn check — any role can escalate from any active state.

### validate_unblock(session)
File: `src/gator_command/scripts/loop/state_machine.py`
Validates that unblock is only called from `blocked_on_architect`.
Filesystem: none
<- `submit.handle_unblock()`

### advance_draft_submitted(session, turn_timeout)
File: `src/gator_command/scripts/loop/state_machine.py`
Transitions `plan_drafting`/`plan_revision` -> `plan_review`.
Filesystem: none (mutates session dict)
<- `submit.handle_submit_draft()`

### advance_review_submitted(session, approved, findings_count, turn_timeout)
File: `src/gator_command/scripts/loop/state_machine.py`
If approved: -> `plan_approved` (terminal, clears `unresolved_findings`). If findings: increments round, checks max_rounds ceiling.
Filesystem: none (mutates session dict)
<- `submit.handle_submit_review()`
! Approval clears `unresolved_findings` to 0. Max rounds triggers `max_rounds_exceeded` terminal state.

### advance_escalated(session, reason)
File: `src/gator_command/scripts/loop/state_machine.py`
Any active -> `blocked_on_architect`. Saves `resume_stage` and `resume_next_role`.
Filesystem: none (mutates session dict)
<- `submit.handle_escalate()`

### advance_unblocked(session, stage, next_role, turn_timeout)
File: `src/gator_command/scripts/loop/state_machine.py`
`blocked_on_architect` -> restored active state. Validates stage-role consistency.
Filesystem: none (mutates session dict)
<- `submit.handle_unblock()`
! Stage-role validation: `plan_drafting`/`plan_revision` require `draftor`, `plan_review` requires `reviewer`. Mismatches raise ValueError.

### advance_turn_timed_out(session, timed_out_role)
File: `src/gator_command/scripts/loop/state_machine.py`
Any active -> `turn_timed_out` (terminal).
Filesystem: none (mutates session dict)
<- `host._try_enforce_timeout()`

### is_active(session) / is_paused(session) / is_terminal(session)
File: `src/gator_command/scripts/loop/state_machine.py`
State categorization helpers. Active: 3 stages, Paused: 1 (`blocked_on_architect`), Terminal: 3.
Filesystem: none
<- `host.watch_loop()`, `host._try_enforce_timeout()`, `cli._cmd_status()`

---

### emit_event(loop_dir, event_dict)
File: `src/gator_command/scripts/loop/events.py`
Appends a single event to events.jsonl. Auto-populates `ts` and `loop_id`.
Filesystem: `.gator/loops/<loop-id>/events.jsonl` (W append)
<- `session.with_session_lock()` (inside lock), `host.start_loop()` (initial event)
! Sets read-only after write on POSIX. Called inside the session lock during normal operation.

### tail_events(loop_dir, poll_interval)
File: `src/gator_command/scripts/loop/events.py`
Generator that polls events.jsonl for new lines. Yields parsed events. Stops on terminal events.
Filesystem: `.gator/loops/<loop-id>/events.jsonl` (R)
<- `cli._cmd_tail()`

### format_event(event) / format_next_prompt(session)
File: `src/gator_command/scripts/loop/events.py`
Human-readable formatting. Events: `[HH:MM:SS] label (detail)`. Prompt: next role and stage.
Filesystem: none
<- `host.watch_loop()`, `cli._cmd_tail()`

---

### handle_submit_draft(token, file_path)
File: `src/gator_command/scripts/loop/submit.py`
Resolves token, validates file, acquires lock, validates action, copies artifact to `plan.current.md`, appends turn, updates `current.draft` with turn reference dict, advances to `plan_review`, emits event.
Filesystem: source file (R), `.gator/loops/<loop-id>/plan.current.md` (W)
<- `cli._cmd_submit_draft()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `append_turn()`, `advance_draft_submitted()`
! `current.draft` stores `{turn_id, summary, artifact_path}`, not a bare string.

### handle_submit_review(token, file_path, approve)
File: `src/gator_command/scripts/loop/submit.py`
Same pattern as draft. Copies to `findings.current.md`. Branches on `--approve`: terminal or revision.
Filesystem: source file (R), `.gator/loops/<loop-id>/findings.current.md` (W)
<- `cli._cmd_submit_review()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `append_turn()`, `advance_review_submitted()`

### handle_escalate(token, reason)
File: `src/gator_command/scripts/loop/submit.py`
Transitions to `blocked_on_architect`. Requires non-empty reason.
Filesystem: none (session mutation only)
<- `cli._cmd_escalate()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `append_turn()`, `advance_escalated()`

### handle_unblock(token, next_role, stage, message)
File: `src/gator_command/scripts/loop/submit.py`
Architect command (requires architect token). Restores from `resume_stage`/`resume_next_role` or accepts overrides. Works for both `blocked_on_architect` and `paused_by_architect`. Optional `message` shown in the resuming model's status output; cleared when the model submits.
Filesystem: none (session mutation only)
<- `cli._cmd_unblock()`
-> `resolve_token()`, `with_session_lock()`, `validate_unblock()`, `advance_unblocked()`, `append_turn()`

### handle_pause(token, message)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Pauses a running loop from any active state. Saves resume state. Distinct from model escalation (`paused_by_architect` vs `blocked_on_architect`).
Filesystem: none (session mutation only)
<- `cli._cmd_pause()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_paused_by_architect()`, `append_turn()`

### handle_interject(token, message)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Injects guidance without pausing — stores message in `architect_message`, no state change, no deadline change. Message cleared on next model submission.
Filesystem: none (session mutation only)
<- `cli._cmd_interject()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_interjected()`, `append_turn()`

### handle_end(token, reason)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Terminates loop prematurely from any non-terminal state. Sets `ended_by_architect` terminal state.
Filesystem: none (session mutation only)
<- `cli._cmd_end()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_ended_by_architect()`, `append_turn()`

---

### start_loop(feature, sketch_path, max_rounds, turn_timeout)
File: `src/gator_command/scripts/loop/host.py`
Initializes loop: creates directory, copies sketch, generates three tokens (draftor, reviewer, architect), writes session + initial event, prints banner, enters watch loop. Blocks until terminal.
Filesystem: `.gator/loops/<loop-id>/` (W, creates), sketch file (R)
<- `cli._cmd_start()`
-> `create_session()`, `save_session()`, `make_token()`, `save_tokens()`, `emit_event()`, `watch_loop()`

### watch_loop(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Polls events.jsonl for new entries, renders log lines, enforces timeouts. Stays alive through paused states. Exits on terminal.
Filesystem: `.gator/loops/<loop-id>/events.jsonl` (R), `session.json` (R for deadline check)
<- `start_loop()`
-> `load_session()`, `format_event()`, `format_next_prompt()`, `_try_enforce_timeout()`
! The host is a READER during normal operation. Timeout enforcement is the one write exception.

### _try_enforce_timeout(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Acquires session lock, re-reads session, fires timeout only if deadline still expired and state still active. Race-safe: if a submit advanced the state, timeout is silently skipped.
Filesystem: `session.json` (RW via lock), `events.jsonl` (W via lock)
<- `watch_loop()`
-> `with_session_lock()`, `advance_turn_timed_out()`
! This is the single Host Contract write exception. Lock-then-re-read discipline prevents the timeout-vs-submit race.

---

### main(argv)
File: `src/gator_command/scripts/loop/cli.py`
Argparse dispatcher for 8 subcommands: start, status, submit-draft, submit-review, escalate, unblock, tail, list.
Filesystem: none (delegates to handlers)
<- `gator-loop.py`

### _cmd_status(args)
File: `src/gator_command/scripts/loop/cli.py`
Read-only status display. Role-aware: model view (exit codes 0/1/2) vs architect supervisor view (exit codes 0/2, shows active role + join states + available commands).
Filesystem: `session.json` (R), `.tokens.json` (R via resolve_token)
<- `main()`
-> `resolve_token()`, `load_session()`
! JSON output includes `"schema": "gator-loop-status-v1"`. Architect JSON includes `turns` and join states. Architect never gets exit code 1 (always authorized to act on active loops).

---

## TRIPWIRE: Session Lock Write Ordering

All writers (submit commands, escalate, unblock, and the host's timeout enforcer) must save `session.json` BEFORE appending to `events.jsonl`, both inside the session lock. This guarantees the host's event-tail loop never observes an event whose session state isn't yet durable.

Violation: the host reads a terminal event, loads session.json to print a summary, but sees stale pre-terminal state.

## TRIPWIRE: Token Nonce Separation

Committed `session.json` contains only role names. Secret nonces live only in gitignored `.tokens.json`. Tokens cannot be reconstructed from committed data because the nonce never appears outside `.tokens.json`.

Violation: committing `.tokens.json` or adding nonces to `session.json` makes tokens reconstructable from git history.

## TRIPWIRE: Host Write Authority

The host has exactly ONE write exception: timeout enforcement. During normal operation the host is a reader of `events.jsonl` and a renderer to terminal. No other section of code grants the host additional write paths.

## TRIPWIRE: Stage-Role Consistency

Each active stage belongs to exactly one role: `plan_drafting` -> draftor, `plan_review` -> reviewer, `plan_revision` -> draftor. `advance_unblocked()` validates this. Bypassing the validation creates impossible session states.

## TRIPWIRE: Escalate Bypasses Turn Check

`validate_action()` skips the turn check for `escalate`. Either model role can escalate from any active state. This is intentional — an agent stuck waiting for a submission that will never come needs the ability to break out.

## TRIPWIRE: Role-Based Access Control

Three roles: `draftor`, `reviewer`, `architect`. Each has a token with a secret nonce. `validate_action()` enforces a strict matrix: model actions (submit-draft, submit-review, escalate) reject `architect`, architect actions (pause, interject, end, unblock) reject model roles. This is a structural barrier — models don't have the architect nonce and cannot execute architect commands.

! The architect token is stored in the same `.tokens.json` as model tokens. The protection is that models are not given the token and have no protocol-sanctioned way to obtain it. This is defense-in-depth, not a cryptographic guarantee. See the [Architect Authority Plan](../artifacts/2026-07-26-architect-loop-authority-plan.md) for the full trust model analysis.

## Pattern: sys.path Import Model

Loop modules use `sys.path.insert(0, LOOP_DIR)` and absolute imports (`from session import ...`) rather than relative imports (`from .session import ...`). This is required because `scripts/` is shipped as package data, not an importable Python sub-package. The CLI runs scripts via subprocess, which has no package context for relative imports.

## Cross-Vendor Orientation

Models join a loop via the "gator loop join" instruction in their vendor entry point (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`). The source of truth for this instruction is `render_entry_content()` in `gatorize/entry_points.py` — see [Installer charter](scripts-installer.md). Claude Code also has a `/loop-join` slash command (`templates/gator-starter/commands/loop-join.md`) as a convenience layer. The behavioral protocol is at `procedures/gator-loop-protocol.md`.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) -- Package CLI Entry Point (cli.py COMMANDS dict), sys.path import convention
-> [Core Library](scripts-core-library.md) -- `find_gator_root()`, `ensure_utf8_stdout()`, `get_version()`
-> [Installer and Boot](scripts-installer.md) -- `render_entry_content()` cross-vendor orientation, `/loop-join` command template
-> [Implementation Plan](../artifacts/2026-07-25-gator-loop-implementation-plan.md) -- full design rationale, resolved design choices
