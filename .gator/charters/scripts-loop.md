# Charter: Gator Loop

**Covers**: `src/gator_command/scripts/loop/__init__.py`, `src/gator_command/scripts/loop/session.py`, `src/gator_command/scripts/loop/events.py`, `src/gator_command/scripts/loop/state_machine.py`, `src/gator_command/scripts/loop/submit.py`, `src/gator_command/scripts/loop/host.py`, `src/gator_command/scripts/loop/cli.py`, `src/gator_command/scripts/loop/liveness.py`, `src/gator_command/scripts/loop/gitsnap.py`, `src/gator_command/scripts/gator-loop.py`

## Owns

The governed planning loop — a CLI-mediated debate between two AI models (draftor, reviewer) with role tokens, turn-taking, bounded iteration, timeout enforcement, and durable session residue.

- `session.py` owns session CRUD, token generation/resolution (with secret nonce), platform-aware file locking, atomic writes, turn tracking, and loop ID generation
- `state_machine.py` owns state categorization (active/paused/terminal), action validation, and all state transitions, indexed by loop mode through the single `STAGES` table (planning; coding #41)
- `events.py` owns event emission (append to events.jsonl), event tailing, and human-readable formatting
- `submit.py` owns the ten submit handlers: submit-draft, submit-implementation (coding, #41), submit-review, escalate, unblock, extend, reopen (#41), pause, interject, end; plus the coding implementation-artifact helpers (required headings, the CLI-owned Commit State section)
- `host.py` owns loop initialization (`init_loop()` and `start_loop()`), the single-active guard for extension (`extend_loop()`), the watch loop with timeout enforcement, platform-aware file locking (`host.lock`, `start.lock`, plus retrying watcher attachment), and active-loop scanning
- `cli.py` owns argparse subcommand routing for all 16 loop subcommands (start [--mode planning|coding, --from-loop], status, submit-draft, submit-implementation, submit-review, escalate, pause, interject, end, unblock, extend, reopen, wait, participant {watch,status}, tail, list)
- `liveness.py` owns the private participant-liveness sidecar (#36): the per-worktree store at `$(git rev-parse --git-path gator-loop-liveness)/<loop_id>.json`, its strict schema allowlist, atomic persistence, the leaf lock, and the pure helpers `state_key()` / `classify()` / `prune()` / `redact()`. Operational data only; never loop authority
- `gitsnap.py` owns the coding-loop Git snapshot (#41): `snapshot(worktree_root, base_head)` -> raw, unfiltered Git facts (HEAD, trees, staged-tree OID, changed paths vs base, unstaged/untracked residue) or an explicit error code. Read-only toward refs, index, and worktree
- `gator-loop.py` is the thin entry script dispatched by `src/gator_command/cli.py`

## Does Not Own

- Dashboard server-side logic — the dashboard calls into this module via `init_loop()` and `watch_loop()` but host registry, route dispatch, and HTTP handling belong to the dashboard charter
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

### resolve_token(token, loop_dir=None)
File: `src/gator_command/scripts/loop/session.py`
Decodes token and validates nonce against `.tokens.json`. Returns (loop_id, role, loop_dir). When `loop_dir` is provided, skips `find_gator_root()` discovery and validates that the token's `loop_id` matches `loop_dir.name`.
Filesystem: `.gator/loops/<loop-id>/.tokens.json` (R)
<- `submit.handle_submit_draft()`, `submit.handle_submit_review()`, `submit.handle_escalate()`, `submit.handle_pause()`, `submit.handle_interject()`, `submit.handle_end()`, `submit.handle_unblock()`, `cli._cmd_status()`, dashboard `_handle_loop_prompt()`
-> `find_gator_root()` (skipped when `loop_dir` provided)
! Raises ValueError on invalid/tampered tokens. Nonce validation prevents token reconstruction from committed data.
! When `loop_dir` provided: validates `loop_dir.name == loop_id` from token — rejects cross-loop token reuse.

### create_session(feature, loop_id, max_rounds, turn_timeout, mode="planning", coding=None)
File: `src/gator_command/scripts/loop/session.py`
Builds the initial session dict including empty `decisions: []` ledger. Does not write to disk.
- Planning sessions are byte-identical to pre-#41 output (`"mode": "planning-only"`, stage `plan_drafting`).
- Coding sessions (#41) carry `"mode": "coding"`, stage `implementation_drafting` (Draftor), `plan_status: "implementation"`, `current.implementation`, and the required `coding` binding `{source_loop_id, plan_sha256, base_head, base_tree, generations: [], approval: null}`.
- A coding session without its binding, or an unknown mode, raises ValueError.
Filesystem: none
<- `host.init_loop()`, `host._init_coding_loop()`

### loop_mode(session)
File: `src/gator_command/scripts/loop/session.py`
The ONLY way loop mode may be read (#41). It returns `"planning"` for a missing `mode` or the legacy `"planning-only"` / `"planning"` values, and `"coding"` for `"coding"`; any other value raises ValueError (fail closed).
<- `state_machine` categorizers and `validate_action`, `host._read_approved_source()`, `cli._mode_of()`
! `create_session()` still WRITES `"planning-only"` for planning loops; never compare `session["mode"]` directly.

### validate_turn_timeout(value) / validate_round_count(value) / _validate_bounded_int(...)
File: `src/gator_command/scripts/loop/session.py`
Single validation paths for Architect-chosen loop integers, both built on `_validate_bounded_int()`: `validate_turn_timeout` returns an int in `TURN_TIMEOUT_MIN..TURN_TIMEOUT_MAX` (30..3600); `validate_round_count` returns an int in `ROUNDS_MIN..ROUNDS_MAX` (1..20, the same bound as Dashboard start `max_rounds`) — used for the per-extension increment (#39). Both raise `ValueError`, reject bool/floats/non-integer strings, and accept plain-integer strings (CLI input). No total round ceiling is enforced.
Filesystem: none
<- turn timeout: `submit.handle_unblock()`, `cli._turn_timeout_arg()`, dashboard `_handle_loop_start()` / `_handle_loop_unblock()`; round count: `submit.handle_extend()`
! CLI `start --turn-timeout` is deliberately NOT routed through this (tests and local tooling use short windows); the Dashboard start and every unblock path are. Default window stays 300s.

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
- Model rules are mode-indexed (`_MODEL_ACTION_RULES_BY_MODE`):
  - planning: `submit_draft` / `submit_review` / `escalate`;
  - coding (#41): `submit_implementation` (Draftor, `implementation_drafting` / `implementation_revision`), `submit_review` (Reviewer, `implementation_review`), `escalate`.

  The other mode's action is rejected with "not valid in a <mode> loop".
- Architect actions include `reopen`, valid only for a coding loop in `REOPENABLE_STAGE` (`implementation_approved`).
Filesystem: none
<- `submit.handle_submit_draft()`, `submit.handle_submit_review()`, `submit.handle_escalate()`, `submit.handle_reopen()`
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
`blocked_on_architect` -> restored active state. Validates stage-role consistency. Receives the already-selected timeout (the caller owns CLI/HTTP policy and persisting any changed window); computes the fresh deadline from it.
Filesystem: none (mutates session dict)
<- `submit.handle_unblock()`
! Stage-role validation comes from the session's mode table (`stages_for(session)`): the target must be an active stage of THIS mode, owned by `role_by_stage` (planning: `plan_drafting` / `plan_revision` → draftor, `plan_review` → reviewer; coding: `implementation_drafting` / `implementation_revision` → draftor, `implementation_review` → reviewer). A cross-mode target or a mismatched role raises ValueError.

### advance_extended(session, rounds, turn_timeout, message=None)
File: `src/gator_command/scripts/loop/state_machine.py`
`max_rounds_exceeded` -> the mode table's `extension_resume_stage` (`plan_revision` for planning, `implementation_revision` for coding #41; next_role from `role_by_stage`, the Draftor) with `max_rounds += rounds`. Preserves `round`, `current`, `turns`, `decisions`, `unresolved_findings`. Resets `plan_status="revision"`, `blocked=False`, `architect_action_required=False`, resume fields, and `architect_response_artifact`; sets `architect_message=message` and a fresh deadline from the given timeout. Returns `(previous_max_rounds, new_max_rounds)`.
Filesystem: none (mutates session dict)
<- `submit.handle_extend()` (#39)
! All guards run before any mutation: source stage must be exactly `EXTENDABLE_STAGE`; `rounds` a positive int (bool rejected); `round <= max_rounds`. Violations raise ValueError. Input range policy (1..20) belongs to the caller.

### advance_turn_timed_out(session, timed_out_role)
File: `src/gator_command/scripts/loop/state_machine.py`
Any active -> `turn_timed_out` (terminal).
Filesystem: none (mutates session dict)
<- `host._try_enforce_timeout()`

### advance_implementation_submitted(session, turn_timeout)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only (#41): `implementation_drafting` / `implementation_revision` -> `implementation_review` (Reviewer) with a fresh deadline. It clears `architect_message` and the response artifact. A non-coding loop or another stage raises ValueError. The caller records the candidate generation.
Filesystem: none (mutates session dict)
<- `submit.handle_submit_implementation()`

### advance_implementation_reviewed(session, approved, turn_timeout, approval=None)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only (#41), from `implementation_review`:
- **Approved:** goes to `implementation_approved` (terminal; resumable only via reopen) and stores `coding.approval = {tree, head, round, ts}`, which is required.
- **Findings:** `round += 1`. At the ceiling the loop goes to `max_rounds_exceeded` (extendable, #39); otherwise to `implementation_revision` (Draftor).

A wrong mode or stage raises ValueError.
<- `submit._coding_review()`

### resolve_approval(approval, snap)
File: `src/gator_command/scripts/loop/state_machine.py`
Pure. Places an approved candidate against live Git facts:

| State | Condition |
|---|---|
| `committed` | HEAD moved and `HEAD^{tree}` equals the approved tree; returns `commit` |
| `pending` | HEAD unchanged and the staged tree unchanged |
| `stale` | anything else, with a reason: `staged_tree_changed`, `head_moved_tree_differs` (a different commit or branch move, including a hook changing committed content), or `detached_mismatch` |
| `unknown` | the snapshot failed; never treated as approved |
| `none` / `invalidated` | no approval, or an approval invalidated by reopen |

<- `cli._approval_resolution()` (status / wait / architect status); the Dashboard arrives in Module 5
! The state strings are machine identifiers. Every display pairs them with explicit text (CLI markers `[OK]` / `[..]` / `[!!]` / `[??]` plus words), never color alone.

### advance_reopened(session, turn_timeout, message=None)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only (#41): `implementation_approved` -> `implementation_revision` (Draftor) with a fresh deadline. It keeps `round`, marks `coding.approval.invalidated_at`, and sets `architect_message`. A non-coding loop or any other stage raises ValueError before mutation.
Filesystem: none (mutates session dict)
<- `submit.handle_reopen()`

### STAGES / stages_for(session)
File: `src/gator_command/scripts/loop/state_machine.py`
The single mode-indexed stage table (#41): `{active, paused, terminal, role_by_stage, initial_stage, extension_resume_stage}` per mode.
- Planning entries are the pre-#41 sets exactly. `ACTIVE_STAGES` / `PAUSED_STAGES` / `TERMINAL_STAGES` and `ALL_STAGES` keep their planning meaning, and the protocol state-table test pins `ALL_STAGES`.
- Coding: `CODING_ACTIVE_STAGES` (`implementation_drafting` / `implementation_review` / `implementation_revision`), the shared paused stages, and `CODING_TERMINAL_STAGES` (`implementation_approved` plus the shared `max_rounds_exceeded` / `turn_timed_out` / `ended_by_architect`).
- `CODING_ALL_STAGES` and `EVERY_STAGE` are the unions.

### is_active(session) / is_paused(session) / is_terminal(session)
File: `src/gator_command/scripts/loop/state_machine.py`
State categorization helpers. They look up `stages_for(session)` (mode-aware, #41); for planning sessions the result is identical to the pre-#41 sets, a table-driven pin. An unknown mode raises ValueError, which callers treat as "do not host / do not enforce".
Filesystem: none
<- `host.watch_loop()`, `host._try_enforce_timeout()`, `host.find_active_loop()`, `cli._cmd_status()`, `liveness._apply_projection()` / `renotify_eligibility()` / `renotify()`, dashboard `_adopt_orphaned_loops()`
! Never test raw stage membership (`stage in ACTIVE_STAGES`) outside `state_machine.py` — it silently ignores coding stages.
! `events.TERMINAL_EVENTS` includes `implementation_approved` (#41). `watch_loop` exits only if the session is still terminal, so a reopened loop keeps hosting.

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
Human-readable formatting. Events: `[HH:MM:SS] label (detail)`. Prompt: next role and stage. `loop_extended` renders as `EXTENDED (<detail>)` and is deliberately NOT in `TERMINAL_EVENTS` (#39).
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
Same pattern as draft. Copies to `findings.current.md`. Branches on `--approve`: terminal or revision. Before the lock: if `approve` is False, reads the first 500 bytes (decoded with `errors="replace"` for safety) and checks for an actual `## Verdict` heading followed by `ESCALATE` (regex, case-insensitive). If matched, emits a stderr warning after the successful submission. This is a soft guard — does not block the submission and cannot raise on non-UTF-8 input.
Filesystem: source file (R), `.gator/loops/<loop-id>/findings.current.md` (W)
<- `cli._cmd_submit_review()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `append_turn()`, `advance_review_submitted()`

### handle_escalate(token, reason, file_path=None)
File: `src/gator_command/scripts/loop/submit.py`
Transitions to `blocked_on_architect`. Requires non-empty reason. Optional `file_path` attaches a structured decision-request artifact: validates file exists and is non-empty, copies to `decision-request.decision-{N}.round-{R}.md` (decision-sequenced to prevent overwrites on repeated same-round escalations), and appends a `decisions[]` entry to session with `id`, `request` (reason, artifact_path, round, role, ts), and `response: null`.
Filesystem: source file (R, optional), `.gator/loops/<loop-id>/decision-request.decision-*.round-*.md` (W, optional), session mutation
<- `cli._cmd_escalate()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `append_turn()`, `advance_escalated()`, `_copy_artifact()` (when file_path provided)
! Either model role may escalate from any active stage, including when it is not its turn — `validate_action()` intentionally skips the turn check for escalate.

### handle_unblock(token, next_role, stage, message, file_path=None, loop_dir=None, turn_timeout=None, no_response=False)
File: `src/gator_command/scripts/loop/submit.py`
Architect command (requires architect token). Restores from `resume_stage`/`resume_next_role` or accepts overrides. Works for both `blocked_on_architect` and `paused_by_architect`. Optional `message` shown in the resuming model's status output; cleared when the model submits. Resolves the most recent pending decision entry (if any): sets `response.message`, `response.artifact_path`, `response.kind`, and `response.ts` so that `pending_decisions` in status accurately reflects only unresolved requests. Optional `file_path` attaches a durable response artifact copied to `decision-response.{decision-id}.md` in the loop directory. File validation (must exist, must be non-empty) runs before lock acquisition; `FileNotFoundError`/`ValueError` on failure. `--file` is rejected with `ValueError` inside the lock (before state advancement) when no pending decision exists — prevents silent discard of a response artifact after an Architect pause.
Response contract: a whitespace-only message is treated as absent. When a pending decision exists (escalation), one of message / file / `no_response=True` is required, else `ValueError` before any mutation. `no_response` is mutually exclusive with message/file and rejected when nothing is pending. `response.kind` ∈ `message`, `artifact`, `message_and_artifact`, `deliberate_empty`. Model-facing `architect_message` is the message, or `ARTIFACT_ONLY_RESPONSE_SUMMARY` for file-only, or `DELIBERATE_EMPTY_RESPONSE_SUMMARY` for the explicit empty choice — never silently blank for a resolved decision. An ordinary pause (no pending decision) still unblocks with no response.
Turn window: optional `turn_timeout` is validated via `validate_turn_timeout()` before the lock; inside the lock it is written to `status.turn_timeout_seconds` BEFORE `advance_unblocked()` computes the fresh deadline, so both this turn and all later transitions use it. Omitted keeps the stored window. The `loop_unblocked` event carries `turn_timeout_seconds` always, plus `previous_turn_timeout_seconds` and a detail suffix when changed, and `response_kind` alongside `decision_id` when a decision was resolved.
Filesystem: `.gator/loops/<loop-id>/decision-response.decision-*.md` (W, when file_path provided), session mutation
<- `cli._cmd_unblock()`, dashboard `_handle_loop_unblock()`
-> `resolve_token()`, `validate_turn_timeout()`, `with_session_lock()`, `validate_unblock()`, `advance_unblocked()`, `append_turn()`, `_copy_artifact()` (when file_path provided)
! All validation that can fail runs before `advance_unblocked()`/`_copy_artifact()`; a raise inside the lock skips the save, so a rejected unblock leaves session.json, events, and the stored timeout untouched.

### handle_submit_implementation(token, file_path, loop_dir=None)
File: `src/gator_command/scripts/loop/submit.py`
Coding Draftor submission (#41). Returns `(loop_id, role, loop_dir, generation)`.

**Before the lock:** the file must exist, be UTF-8 and non-empty, and contain the required level-2 headings (`IMPLEMENTATION_HEADINGS`: Executive Summary, Implementation Summary, Charter Updates, Verification, Commit State). Missing headings are listed in the ValueError. **Exactly one** level-2 `Commit State` heading may exist outside fences (`commit_state_heading_count`). A duplicate is rejected, so no author-controlled competing state block can sit next to the CLI-captured one; a Commit State example inside a code fence is allowed.

**Under the session lock:**
1. `validate_action(..., "submit_implementation")`.
2. `gitsnap.snapshot(repo_root, coding.base_head)`, which must be `ok` (otherwise ValueError naming the error code).
3. `staged_tree != base_tree`, so something must be staged (otherwise "Nothing is staged…").
4. The artifact's Commit State section is replaced by `render_commit_state(snap)` (`replace_commit_state`) and written as `implementation.round-<round>.md` plus `implementation.current.md` (read-only, LF).
5. Bookkeeping:
   - mark the Draftor joined;
   - append an `implementation` turn and set `current.implementation`;
   - append the generation `{round, submitted_at, artifact_path, snapshot}`, where the snapshot is RAW and persisted unchanged.
6. `advance_implementation_submitted()`.
7. Emit `implementation_submitted` with `staged_tree`, `current_head`, `changed_count`, `unstaged_count` (raw), `residue_other_count` and `residue_loop_count`.

Filesystem: `implementation.round-N.md` / `implementation.current.md` (W), `session.json` / `events.jsonl` (W via lock), Git (R; `write-tree` objects via gitsnap)
<- `cli._cmd_submit_implementation()`
! Lock order: session lock, then Git (`gitsnap` runs inside the callback so the binding and the transition are one consistent step). Every rejection leaves session, events, and artifacts unchanged.
! Unstaged residue is disclosed, never blocking. Only the staged tree is the candidate.

### missing_implementation_headings(text) / commit_state_heading_count(text) / render_commit_state(snap) / replace_commit_state(text, block) / split_residue(paths) / coding_status_view(coding)
File: `src/gator_command/scripts/loop/submit.py`
- **Headings:** a case-insensitive, level-2-only check that ignores headings inside fences.
- **`render_commit_state`:** the CLI-owned, authoritative section, containing:
  - a facts table: base HEAD and tree, current HEAD with branch or detached, the staged tree, changed-path counts by status, and the residue split;
  - the exact-candidate review command `git diff <base_tree> <staged_tree>`, which still shows the submitted tree after the index changes;
  - path lists inside `text` fences, with newlines in filenames escaped so no filename can inject a section.
- **`replace_commit_state`:** swaps the Commit State section up to the next unfenced level-2 heading. It also refuses more than one Commit State heading, as a second layer behind the handler's check.
- **`split_residue`:** a **display-only** classification of raw residue into loop residue (`.gator/loops/`, the loop's own always-untracked audit files) and other residue. Only other residue triggers the CLI warning. The persisted snapshot keeps the raw list.
- **`coding_status_view`:** the slim, allowlisted projection of `session["coding"]` that the Dashboard status poll serves: source/plan/base ids, per-generation tree / HEAD / branch, changed counts by status, residue counts, review verdicts, and the approval binding. Never raw path lists.

### handle_submit_review(token, file_path, approve=False, loop_dir=None) — coding path: _coding_review(session, role, loop_dir, source, approve) / render_reviewed_candidate(review)
File: `src/gator_command/scripts/loop/submit.py`
Planning reviews are unchanged. For coding loops (#41), inside the same session lock:
- **Binding:** the review binds to the LATEST generation's submitted candidate (`reviewed_tree` / `reviewed_head`). The Reviewer inspects it with the immutable `git diff <base_tree> <staged_tree>`.
- **Live check:** a fresh `gitsnap` snapshot is taken.
  - **APPROVE is rejected unless the live staged tree AND HEAD still equal the submitted candidate.** If the live snapshot fails, approval is also rejected ("Cannot verify…").
  - **Findings are always accepted**, flagged `candidate_changed` / `live_snapshot_ok`, so the loop can never deadlock in review.
- **Artifact:** it must be UTF-8 and must not author `## Reviewed Candidate`. The CLI appends that section (verdict, reviewed tree / HEAD, round, live-unchanged) to `findings.round-N.md` / `findings.current.md`.
- **Records:** the review is stored on the generation (`generation.review`), and the approval as `{tree, head, round, ts}` via `advance_implementation_reviewed()`.
- **Events:** `implementation_approved` (terminal), `max_rounds_exceeded`, or `revision_requested` (notes a changed candidate).
! Deliberate refinement of the approved plan's "a mismatch rejects the review": only APPROVE is blocked. Findings about the submitted (immutable) tree stay valid, and blocking them would leave no legal actor in `implementation_review`.

### handle_extend(token, rounds, message, loop_dir=None)
File: `src/gator_command/scripts/loop/submit.py`
Architect command (#39): the session transaction for continuing a loop that ended at its round limit. Before the lock: `message` required (blank/whitespace -> `ValueError`, stored stripped), `validate_round_count(rounds)` (1..20), `resolve_token()`, non-architect -> `PermissionError`. Inside `with_session_lock`: `validate_action(session, "architect", "extend")` (wrong stage -> `PermissionError`), `advance_extended()` with the stored `turn_timeout_seconds`, `append_turn(architect, "extend", message)`, and one `loop_extended` event `{role: architect, round, rounds_added, previous_max_rounds, max_rounds, stage, next_role, reason, detail}`. Returns `(loop_id, loop_dir, previous_max_rounds, new_max_rounds)`.
Filesystem: session mutation + one event (inside the session lock)
<- `host.extend_loop()` (M3)
-> `validate_round_count()`, `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_extended()`, `append_turn()`
! Transaction only. It does NOT take `start.lock`, scan for other active loops, or attach a watcher — callers must go through `host.extend_loop()` so the single-active-loop guarantee holds. Every rejection leaves `session.json` and `events.jsonl` byte-identical.

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

### init_loop(feature, sketch_path, max_rounds, turn_timeout, repo_root=None, mode="planning", from_loop=None)
File: `src/gator_command/scripts/loop/host.py`
`mode="coding"` (#41) delegates to `_init_coding_loop()`; then `sketch_path` must be None and `from_loop` is required. Planning requires `sketch_path` and rejects `from_loop`. Planning: creates loop on disk without entering the watch loop. Creates directory, copies sketch, generates three tokens (draftor, reviewer, architect), writes session + initial event. Returns `(loop_id, loop_dir)`. When `repo_root` is provided, uses it directly instead of calling `find_gator_root()` — enables dashboard reuse without filesystem discovery.
Filesystem: `.gator/loops/<loop-id>/` (W, creates), sketch file (R)
<- `start_loop()`, dashboard `_handle_loop_start()`
-> `create_session()`, `save_session()`, `make_token()`, `save_tokens()`, `emit_event()`, `ensure_loops_gitignore()`

### _init_coding_loop(feature, from_loop, max_rounds, turn_timeout, repo_root) / _read_approved_source(source_dir, from_loop) / _remove_partial_loop(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
The guarded coding successor (#41). Steps, in order:
1. Validate the canonical shape of `from_loop`: `_SOURCE_LOOP_ID_RE` starts AND ends alphanumeric, so a Windows trailing-dot alias is rejected; no `..` / separators. The source must be a real directory with `session.json`.
2. Under the source's `with_session_lock` read-only callback, require **`session["loop_id"] == from_loop` exactly**, which rejects Windows trailing-dot and case-variant aliases that resolve to the same directory, so only the canonical id is persisted as `coding.source_loop_id`. Also require `loop_mode == "planning"` (legacy values accepted), stage `plan_approved`, and a non-empty regular `plan.current.md`.
3. Take `gitsnap.snapshot(repo_root)`, which must be ok; this rejects unborn, conflicted, bare and missing-Git cases.
4. Create the loop dir, write `approved-plan.md` (read-only), and re-read it to compare SHA-256 against the source bytes.
5. Only then write tokens, `session.json`, and a `loop_started` event (with `mode`, `source_loop_id`).

Any failure removes the partial directory (`_remove_partial_loop`, read-only tolerant; `onexc` on 3.12+, `onerror` below) and raises one clear error.
Filesystem: source `session.json` / `session.lock` (R, lock), source `plan.current.md` (R), `.gator/loops/<new>/` (W)
! The source session is never written. Callers hold `start.lock` (`start_loop`; the Dashboard start in Module 5); lock order is start.lock, then the source session lock, the same as extend.

### reopen_loop(token, message, loop_dir=None)
File: `src/gator_command/scripts/loop/host.py`
Single-active guard for reopen (#41), mirroring `extend_loop()`: take `start.lock`, refuse if another loop is active (`RuntimeError`), delegate to `submit.handle_reopen()`, and release in `finally`. Does not attach a watcher; the caller applies the host contract.
<- CLI `_cmd_reopen()` (the Dashboard `/reopen` arrives in Module 5)
! Every reopen path must go through this function. Rejections leave the loop byte-unchanged.

### start_loop(feature, sketch_path, max_rounds, turn_timeout, mode="planning", from_loop=None)
File: `src/gator_command/scripts/loop/host.py`
CLI entry point for starting a loop. Acquires `start.lock` (cross-process, one active loop per repo), scans for existing active loops, calls `init_loop()`, acquires `host.lock`, releases `start.lock`, enters watch loop. Blocks until terminal.
Filesystem: `.gator/loops/start.lock` (RW), `.gator/loops/<loop-id>/host.lock` (RW)
<- `cli._cmd_start()`
-> `acquire_start_lock()`, `release_start_lock()`, `find_active_loop()`, `init_loop()`, `acquire_host_lock()`, `release_host_lock()`, `watch_loop()`
! `start.lock` held only during the scan-and-init window — released before entering `watch_loop()`. `host.lock` transferred to `watch_loop()`.

### watch_loop(loop_dir, host_lock_fd=None)
File: `src/gator_command/scripts/loop/host.py`
Polls events.jsonl (from offset 0) for new entries, renders log lines, enforces timeouts. Stays alive through paused states. Exits on a terminal event **only if the session is still terminal** (`_session_is_terminal()`); otherwise the event is rendered as history and watching continues. When `host_lock_fd` is provided, writes diagnostic metadata (PID, loop_id, start time) via `write_host_metadata()`.
Filesystem: `.gator/loops/<loop-id>/events.jsonl` (R), `session.json` (R for deadline + terminal check), `host.lock` (W metadata, when fd provided)
<- `start_loop()`, dashboard `_run_watcher()`
-> `load_session()`, `format_event()`, `format_next_prompt()`, `_try_enforce_timeout()`, `write_host_metadata()`, `_session_is_terminal()`, `_open_liveness_store()` / `_project_liveness()` (-> `liveness.project_for_host()`)
! The host is a READER of loop state during normal operation. Timeout enforcement is the one loop-state write exception.
! Liveness projection (#36) runs after each event batch and just before a terminal return; a `retry`/`error` result is retried on the next tick even without new events. It writes only the private liveness sidecar, never raises, and is skipped when the store is unavailable.
! Terminal detection is session-authoritative (#39): a watcher attached after an extension replays the old `max_rounds_exceeded` event and must keep hosting; a watcher that reads the terminal event after an extension already landed also keeps hosting. `_session_is_terminal()` fails safe (unreadable session -> terminal -> exit), preserving the pre-#39 behavior.
! `tail_events()` (`gator loop tail`) is intentionally NOT session-authoritative: a human tail started before an extension ends at the old terminal event.

### acquire_host_lock(loop_dir) / release_host_lock(fd) / _try_host_lock(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Non-blocking exclusive file lock on `host.lock` — proves process ownership of timeout enforcement for a specific loop. Platform-aware: `msvcrt.locking(LK_NBLCK)` on Windows, `fcntl.flock(LOCK_EX|LOCK_NB)` on POSIX. `_try_host_lock()` is the single attempt that distinguishes `"held"` from `"open failed: ..."`; `acquire_host_lock()` wraps it with the unchanged fd-or-None contract.
Filesystem: `.gator/loops/<loop-id>/host.lock` (RW)
<- `start_loop()`, dashboard `_handle_loop_start()`, dashboard `_adopt_orphaned_loops()`
! Returns fd on success, None if already held. OS exclusive lock prevents duplicate watchers cross-process.

### acquire_host_lock_with_retry(loop_dir, attempts=15, delay=0.2, sleep=None) / read_host_metadata(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Watcher attachment for a loop that just became active again (#39). Retries `_try_host_lock()` (~3 s default) so a terminal watcher still releasing its lock can finish. Returns `(fd, state, detail)` with `state` ∈ `HOST_ATTACHED` / `HOST_ALREADY_HOSTED` / `HOST_FAILED`. `read_host_metadata()` is a best-effort, non-locking JSON read of the holder's metadata (often unreadable on Windows while held) used only for the `already_hosted` detail (pid).
Filesystem: `.gator/loops/<loop-id>/host.lock` (RW attempt; R metadata)
<- CLI `_cmd_extend()` (M4), dashboard `_ensure_loop_watcher()` (M5)
! `already_hosted` means a live process owns `host.lock` (the OS releases locks of dead processes); callers must NOT start a second watcher. With session-authoritative `watch_loop()`, that holder keeps hosting the extended loop. `failed` (open error) returns immediately without retry. Residual risk: a watcher that decided to exit *before* the extension but takes longer than the retry window to release is misreported as hosted; Dashboard startup adoption is the backstop.

### extend_loop(token, rounds, message, loop_dir=None)
File: `src/gator_command/scripts/loop/host.py`
Single-active-loop guard for #39: resolves the token, takes `start.lock` on the loops base (unavailable -> `RuntimeError`), refuses if `find_active_loop()` returns a *different* loop (`RuntimeError`), then delegates to `submit.handle_extend()` and releases `start.lock` in `finally`. Does not attach a watcher.
Filesystem: `.gator/loops/start.lock` (RW), target session/events via `handle_extend()`
<- CLI `_cmd_extend()` (M4), dashboard `_handle_loop_extend()` (M5)
-> `resolve_token()`, `acquire_start_lock()`, `find_active_loop()`, `submit.handle_extend()`, `release_start_lock()`
! Every extension path must go through this function — calling `handle_extend()` directly would bypass the one-active-loop invariant. Rejections leave the target loop byte-unchanged.

### acquire_start_lock(loops_base) / release_start_lock(fd)
File: `src/gator_command/scripts/loop/host.py`
Non-blocking exclusive file lock on `start.lock` — enforces one-active-loop-per-repo during the scan-and-init window (and the scan-and-extend window, #39). Same platform-aware locking as `host.lock`.
Filesystem: `.gator/loops/start.lock` (RW)
<- `start_loop()`, `extend_loop()`, dashboard `_handle_loop_start()`
! Held only during the start or extend sequence. Released before entering `watch_loop()`.

### find_active_loop(loops_base)
File: `src/gator_command/scripts/loop/host.py`
Scans `loops_base` for non-terminal sessions. Returns `loop_id` or None.
Filesystem: `.gator/loops/*/session.json` (R)
<- `start_loop()`, dashboard `_handle_loop_start()`, dashboard `_adopt_orphaned_loops()`
-> `load_session()`, `is_terminal()`

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
Argparse dispatcher for 16 subcommands: start, status, submit-draft, submit-implementation, submit-review, escalate, pause, interject, end, unblock, extend, reopen, wait, participant, tail, list.
Filesystem: none (delegates to handlers)
<- `gator-loop.py`

### _cmd_status(args)
File: `src/gator_command/scripts/loop/cli.py`
Read-only status display. Role-aware: model view (exit codes 0/1/2, shows `architect_message` and `architect_response_artifact` when set) vs architect supervisor view (exit codes 0/2, shows active role + join states + available commands + pending decisions). Both text and JSON output include `architect_response_artifact` (absolute loop path or null).
Filesystem: `session.json` (R), `.tokens.json` (R via resolve_token)
<- `main()`
-> `resolve_token()`, `load_session()`
! JSON output includes `"schema": "gator-loop-status-v1"`. Architect JSON includes `turns`, join states, `decisions`, and `pending_decisions` (entries where `response` is null). Architect text status shows pending decision ID, reason, and artifact path when blocked. Architect never gets exit code 1 (always authorized to act on active loops).
! Turn window: model and architect JSON (and wait JSON) carry additive `turn_timeout_seconds` + `turn_deadline`; the acting model's text view prints `Turn window: Ns (deadline ...)` via `_print_turn_window()`. The paused architect view prints the current window and, when a decision is pending, states that a response is required (with the exceptional `--no-response` form); an ordinary pause shows the optional-message form.

### _approval_resolution(session, loop_dir) / _print_approval_resolution(res, token=None)
File: `src/gator_command/scripts/loop/cli.py`
For an `implementation_approved` coding loop, `status` (model and Architect) and `wait` take a live snapshot and print the `resolve_approval()` result as text plus a marker:
- `[OK] COMMITTED -- handoff complete (commit <oid>)`;
- `[..] PENDING COMMIT -- return to the Draftor session for one normal commit`;
- `[!!] STALE -- <reason>`;
- `[??] UNKNOWN -- never treat this as approved`.

The Architect view adds the `gator loop reopen` hint for stale or unknown. JSON gains additive `approval_resolution` (and `mode` on the Architect view). `submit-review` for coding prints the approved tree and the one-normal-commit handoff, or the reviewed tree plus a resubmit note when the candidate changed.

### _cmd_submit_implementation(args)
File: `src/gator_command/scripts/loop/cli.py`
`gator loop submit-implementation --token <draftor> --file <implementation.md>` (#41).
- On success it prints the round, the full candidate staged-tree OID, the changed-path count, a WARNING line only for residue outside `.gator/loops/`, a loop-residue count line, and the artifact path.
- `PermissionError` prints `Rejected:` and exits 1; `ValueError` / `FileNotFoundError` print `Error:` and exit 1.
- The Reviewer's coding status prints the latest generation's candidate tree and `git diff <base_tree> <staged_tree>`.

### _cmd_reopen(args) / _attach_foreground_watcher(loop_host, loop_dir, what)
File: `src/gator_command/scripts/loop/cli.py`
`gator loop reopen --token <architect> --message "..."` (#41) calls `host.reopen_loop()`; on success it prints the resumed stage, the approval invalidation, the turn window and the re-engagement notice. `_attach_foreground_watcher` is the host contract shared with `extend`:
- `attached`: foreground `watch_loop()`;
- `already_hosted`: exit 0;
- `failed`: stderr says "the <reopen|extension> is saved, but turn timeouts are NOT being enforced", exit 1.

### _cmd_start(args) / _mode_of(session) / _print_coding_action_prompt(...)
File: `src/gator_command/scripts/loop/cli.py`
- `start --mode planning|coding [--from-loop ID] [--sketch PATH]`: planning requires `--sketch`; coding requires `--from-loop`. Argument errors and `RuntimeError` exit 1 with `Error:`.
- Status JSON gains additive `mode` (normalized). Coding text status prints `Mode: coding` and a coding action prompt (approved plan path, `submit-implementation`, review the STAGED tree).
- Terminal text for `implementation_approved` gives the one-normal-commit handoff.

### _cmd_extend(args) / _round_count_arg(value)
File: `src/gator_command/scripts/loop/cli.py`
Architect `gator loop extend --token --rounds <1-20> --message "..."` (#39). `--rounds` and `--message` are required; `--rounds` uses argparse type `_round_count_arg` -> `session.validate_round_count()` (usage error exit 2 before any write). Calls `host.extend_loop()`; `PermissionError` -> `Rejected:` exit 1, `RuntimeError`/`ValueError`/`FileNotFoundError` -> `Error:` exit 1 (no host step). On success prints old -> new ceiling, resumed stage/role, turn window, and a participant re-engagement notice, then applies the host contract via `host.acquire_host_lock_with_retry()`: `attached` -> foreground `watch_loop()` (Ctrl+C prints that enforcement stopped; fd released in `finally`); `already_hosted` -> prints holder detail, exit 0; `failed` -> stderr says the extension is saved but timeouts are NOT enforced, exit 1.
<- `main()`
-> `host.extend_loop()`, `host.acquire_host_lock_with_retry()`, `host.watch_loop()`, `host.release_host_lock()`, `session.load_session()`
! Always attaches (no state-only `--no-watch` form): a state-only extension would leave a live-but-unhosted loop with no recovery command, because `extend` rejects once the stage is `plan_revision`.
! Architect status for a `max_rounds_exceeded` loop prints the `extend` command hint; `start`'s banner lists it too.

### _cmd_unblock(args) / _turn_timeout_arg(value)
File: `src/gator_command/scripts/loop/cli.py`
Architect unblock. Forwards `--message`, `--file`, `--timeout` (argparse type `_turn_timeout_arg` → `session.validate_turn_timeout()`, so bad values are usage errors before any write), and `--no-response` to `submit.handle_unblock()`; prints the resumed stage and effective turn window. `ValueError`/`FileNotFoundError` exit 1 with `Error:`; `PermissionError` exits 1 with `Rejected:`.
<- `main()`
-> `submit.handle_unblock()`, `session.load_session()`

### _cmd_wait(args)
File: `src/gator_command/scripts/loop/cli.py`
Model-role wait. Resolves the token, then calls `_wait_for_actionable()` and renders status-shaped output. Exit codes: `0` actionable, `2` paused/terminal (and invalid token or invalid `--max-seconds`), `3` (`WAIT_EXIT_STILL_WAITING`) bounded deadline passed while another role owns the turn. Architect token exits 1.
Filesystem: `session.json` (R), `.tokens.json` (R via resolve_token)
<- `main()`
-> `resolve_token()`, `_wait_for_actionable()`, `_print_action_prompt()`, `_positive_seconds()`
! `--max-seconds` omitted = unbounded (human CLI compatibility). Participant surfaces teach the bounded form `--max-seconds 45`; exit 3 means "reissue the same command", never "leave the loop". Text output prints the exact reissue command; JSON (`gator-loop-status-v1`, additive) adds `wake_reason: "still_waiting"`, `max_seconds`, `waited_seconds`, `reissue_command`, plus `turn_timeout_seconds` / `turn_deadline`. When actionable, text output prints the turn window like `status`.

### _wait_for_actionable(loop_dir, role, poll_interval, load_session, is_terminal, is_paused, max_seconds=None, clock=None, sleep=None)
File: `src/gator_command/scripts/loop/cli.py`
Polls until terminal / paused / this role's turn. Returns `(session, wake_reason)` with wake_reason `terminal`, `paused`, `already_your_turn`, `became_your_turn`, or `still_waiting` (bounded only).
Filesystem: `session.json` (R)
<- `_cmd_wait()`
! Read-only — never writes session or events. Bounded mode uses a monotonic deadline and caps each sleep at the remaining time, so it cannot overrun by a full poll interval; the session is re-read after the final sleep, so a turn change at the deadline still wins over `still_waiting`. `clock`/`sleep` are injectable test seams.

### LivenessStore(store_dir, loop_id) — read() / with_lock(fn) / delete()
File: `src/gator_command/scripts/loop/liveness.py`
One loop's liveness file (`<loop_id>.json`) plus its leaf lock (`<loop_id>.lock`). `read()` is a lock-free, side-effect-free snapshot for observers; a missing or corrupt file reads as the empty state. A transient read `OSError` makes `read()` return `None` with `last_error = "unavailable"` (observer retries / shows degraded). `with_lock(fn)` is the only mutation path: it loads (quarantining a corrupt file to `<loop_id>.json.corrupt-<ts>` with bounded rename retries, never deleting it, and setting `last_error = "corrupt"`), calls `fn(state) -> (new_state_or_None, value)`, then validates and atomically writes (temp + `os.replace`, bounded retry on Windows `PermissionError`, `newline="\n"`).
Filesystem: `<git-dir>/gator-loop-liveness/<loop_id>.json` (R/W), `<loop_id>.lock`
! If the corrupt file cannot be renamed aside, or the file is unreadable, `with_lock()` raises `LivenessUnavailableError` WITHOUT calling `fn` (`last_error = "quarantine_failed"`) — a mutation must never overwrite the only copy of a corrupt file.
! Store directory comes from `resolve_store_dir(repo_root)` (`git rev-parse --git-path gator-loop-liveness`, per worktree); `None` means delivery unavailable — the loop still runs normally.

### validate_state(state, loop_id=None)
File: `src/gator_command/scripts/loop/liveness.py`
Strict allowlist at every level (top, roles, registration, adapter, notification, superseded, audit), enum and timestamp checks, sanitized-text checks for adapter `label` (≤40) and audit `reason` (≤200), seq uniqueness below `next_seq`, and a recursive rejection of any token-shaped (`glp_…`) string. Raises `LivenessSchemaError`.

### state_key(session) / classify(role_rec, now) / prune(state, now, loop_exists=True) / redact(text) / sanitize_text(text, max_len)
File: `src/gator_command/scripts/loop/liveness.py`
Pure helpers. `state_key` is the SHA-256 idempotency key over `round`, `stage`, `next_role`, `len(turns)`, `turn_deadline`. `classify` returns `not_registered` / `connected` / `stale` (active only, > 3 × heartbeat) / `released` / `closed` / `expired` (> 24 h unseen). `prune` applies retention: delete when the loop dir is gone or terminal > 7 days; drop expired registrations; TTL-expire pending `turn-ready` > 24 h; cap 50 notifications per role (pending never dropped — so a role whose records are all pending may exceed 50; pending records still TTL-expire), 10 superseded, 100 audit.

### authenticate(token, loop_dir=None) / open_store(loop_dir, store_dir=None)
File: `src/gator_command/scripts/loop/liveness.py`
`authenticate` wraps `resolve_token` (errors redacted) and rejects the architect token with `PermissionError`. `open_store` resolves the Git-private store for `<repo>/.gator/loops/<id>`; raises `LivenessUnavailableError` outside a Git worktree. `store_dir` is a test seam.

### register / heartbeat / poll / ack / release (token, registration_id, ...)
File: `src/gator_command/scripts/loop/liveness.py`
Participant API (D3). Every call re-authenticates with the role token AND the opaque `registration_id` (compared with `hmac.compare_digest`); a mismatch raises `SupersededError`. `register` issues a 32-hex id and a generation that is monotonic over all role history (current, superseded, and every delivered/acked generation), supersedes the prior receiver, and returns the id to the caller only. `poll` is a heartbeat and returns pending records not yet delivered to this generation (so a new receiver gets records an old one never acked), stamping `delivered_*`. `ack` stamps `acked_*` only for the current generation and only for a record delivered to it. `release` sets `released` / `closed` with `released_reason`. `closed` is one-way (terminal): heartbeat/poll/ack/release on a current closed registration raise `RegistrationClosedError` without writing; only a fresh `register()` supersedes it.
Filesystem: liveness store (R/W via `with_lock`), `.tokens.json` (R via resolve_token). Never `session.json` / `events.jsonl` writes.
-> `project()` (called outside the liveness lock by register/poll; failures swallowed into `last_error = "projection_failed"`)
! Ack means "received" — never read, complied, or submitted.

### project(loop_dir, store, now=None) / _apply_projection(state, session, now) / project_for_host(loop_dir, store) / open_host_store(loop_dir)
File: `src/gator_command/scripts/loop/liveness.py`
D5 projection. Snapshots `session.json` WITHOUT the session lock (torn/locked read -> `retry`), then applies the rules under the liveness leaf lock: expire every pending record from an older `state_key` (`state_changed`); active -> one `turn-ready` per (next_role, state_key), recorded even for an unregistered role; paused -> one `architect-block` per registered non-closed role; terminal -> one `terminal` per registered non-closed role, closing a registration that was already told for this generation (so a late watcher exits 2 at once), and set `terminal_observed_at` (cleared again when a #39 extension makes the loop non-terminal). Then `prune()`; saves only when something changed (`unchanged` / `updated`); a vanished loop directory or 7-day terminal retention deletes the sidecar (`deleted`). `project_for_host` is the never-raising wrapper for `watch_loop` (sanitized `last_error`, stderr diagnostic only with `GATOR_DASHBOARD_DEBUG=1`).
! Never reopens a `closed` registration and never writes loop state.

### renotify_eligibility(state, session, role, now=None)
File: `src/gator_command/scripts/loop/liveness.py`
Pure D7 eligibility for an Architect Re-notify -> `(eligible, reason_code)`. Eligible when the role owns the current active turn, or has a pending record and no live watcher (stale / released / not registered / expired). Otherwise `terminal`, `already_acknowledged`, or `not_actionable` (including a pending record a connected watcher will receive). Rate limiting belongs to the Dashboard endpoint (M4).

### observer_view(state, session, now=None) / renotify(loop_dir, store, role, reason, now=None) / sweep(repo_root, now=None)
File: `src/gator_command/scripts/loop/liveness.py`
- `observer_view` is the Dashboard's explicit allowlist serializer (`gator-loop-liveness-view-v1`). It maps `expired` to `not_registered`, and reports `session_unreadable` for eligibility when the session is None.
- `renotify` snapshots the session unlocked, then, under the leaf lock only, re-checks `renotify_eligibility` and appends one `created_by: "architect"` record (`turn-ready` for the turn owner, otherwise the kind of the role's newest pending record, with the same `state_key`) plus a sanitized audit entry. It returns `(ok, reason_code, kind)`.
- `sweep` is the best-effort retention pass over every sidecar file in a worktree.
<- Dashboard `_handle_loop_liveness()`, `_handle_loop_renotify()`, `_sweep_liveness()`
! `LivenessStore.read()` retries a transient read `OSError` briefly (the Windows writer `os.replace` window) before returning None.

### own_status(token, ...) / public_notification(n)
File: `src/gator_command/scripts/loop/liveness.py`
Read-only own-role summary (`gator-loop-participant-v1`): classification, generation, last seen, pending count, last notification. Never includes the other role, the registration id, `state_key`, or audit data.

### run_watch(token, max_seconds, poll_seconds=5.0, adapter_label=None, loop_dir=None, store_dir=None, clock=None, sleep=None)
File: `src/gator_command/scripts/loop/liveness.py`
The D2a receiver. Registers (heartbeat advertised as `max(15, ceil(poll_seconds))`), polls until a delivery or the deadline, acks every record received in that poll, reports the newest, sets the registration state, and returns `(exit_code, payload)`: `0 turn_ready` (released), `2 architect_block` (released) / `2 terminal` (closed), `3 still_waiting` (released), `4 superseded` (no write), `1 error` (redacted), `130 interrupted` (best-effort release). A `RegistrationClosedError` mid-watch (closed by the terminal path) returns `2 terminal` with no write. Never loops forever or relaunches itself. `clock`/`sleep` are test seams.

### _cmd_participant_watch(args) / _cmd_participant_status(args) / _render_participant(payload, as_json)
File: `src/gator_command/scripts/loop/cli.py`
`gator loop participant watch --token T --max-seconds N [--poll-seconds S] [--adapter-label L] [--json]` and `gator loop participant status --token T [--json]`. `--max-seconds` is required. `--json` prints exactly one compact JSON line on stdout (the adapter reads the last JSON line of its output file) and nothing on stderr for normal outcomes. SIGTERM is mapped to KeyboardInterrupt so it releases like Ctrl+C. Output never contains the token or registration id.

### snapshot(worktree_root, base_head=None)
File: `src/gator_command/scripts/loop/gitsnap.py`
Returns `{"schema": "gator-loop-gitsnap-v1", "ok": True, worktree_root, current_head, head_tree, detached, branch, staged_tree, base_head, base_tree, changed_paths[{status, path[, old_path]}], changed_truncated, unstaged_paths, unstaged_truncated}`, or `{"ok": False, "error", "detail"}` and never raises for Git conditions.

| Field | Source command |
|---|---|
| `worktree_root` | `rev-parse --show-toplevel` (works for linked worktrees; the per-worktree index is used) |
| `current_head` | `rev-parse --verify HEAD^{commit}` |
| `head_tree` | `rev-parse HEAD^{tree}` |
| `detached` / `branch` | `symbolic-ref -q HEAD` |
| `staged_tree` | `write-tree` |
| `base_tree` | `rev-parse <base>^{tree}`, with `base_head` normalized to a full OID |
| `changed_paths` | `diff --cached --name-status -z -M <base or HEAD>` |
| `unstaged_paths` | the union of `diff --name-only -z` and `ls-files --others --exclude-standard -z` (gitignored files are not residue) |

Error codes:
- `git_unavailable` — reserved for failure to execute Git itself;
- `not_a_repo` — not a repository, a missing path, or a non-directory input (rejected before any Git invocation). A launch failure caused by a bad cwd is classified as `not_a_repo`; any other OS-level launch failure is `git_error`;
- `bare` — a bare repository;
- `unborn` — HEAD has no commit;
- `conflict` — unmerged index entries, checked before `write-tree`;
- `bad_base` — the base commit cannot be resolved;
- `git_busy` — an index-lock failure persists after one retry (0.2 s);
- `git_error` — anything else.

Path lists are capped at `MAX_PATHS` (1000), with truncation counts; the staged-tree OID, not the list, is the binding. `_run` is the test seam.
Filesystem: Git object database (W — tree objects written by `write-tree`, unreferenced until a commit; reclaimed by `git gc`). Refs, index, and worktree are never modified (pinned).
! Facts are RAW. Never filter or normalize paths (for example hook-managed `.gator/` files) out of the binding. The approved #41 plan keeps the raw staged tree authoritative everywhere.

---

## TRIPWIRE: Raw Staged Tree Is Review Authority (coding mode, #41)

In coding-mode loops the reviewed and approved candidate is the raw `git write-tree` OID captured by `gitsnap.snapshot()` — never artifact prose and never a filtered or normalized tree. Implementation artifacts describe the candidate; the CLI writes their `## Commit State` facts from the snapshot.

Violation: approving from prose, or from a filtered tree, lets a commit land that differs from what the Reviewer inspected.

## TRIPWIRE: Liveness Store Is a Leaf Lock and Never Authority

The liveness lock is a leaf: never acquire the session lock while holding it, and never touch the liveness store inside a `with_session_lock` callback. Snapshot session state unlocked first, then take the liveness lock. The store never holds tokens, nonces, prompts, artifacts, model/provider identity, or session-authoritative fields, and nothing in it may change loop state, deadlines, or `next_role`. It is never written to `events.jsonl`.

Violation: a projection that holds the liveness lock and then waits on the session lock can deadlock against a submit; a store field read as authority lets liveness data drive loop transitions.

## TRIPWIRE: Session Lock Write Ordering

All writers (submit commands, escalate, unblock, and the host's timeout enforcer) must save `session.json` BEFORE appending to `events.jsonl`, both inside the session lock. This guarantees the host's event-tail loop never observes an event whose session state isn't yet durable.

Violation: the host reads a terminal event, loads session.json to print a summary, but sees stale pre-terminal state.

## TRIPWIRE: Token Nonce Separation

Committed `session.json` contains only role names. Secret nonces live only in gitignored `.tokens.json`. Tokens cannot be reconstructed from committed data because the nonce never appears outside `.tokens.json`.

Violation: committing `.tokens.json` or adding nonces to `session.json` makes tokens reconstructable from git history.

## TRIPWIRE: Host Write Authority

The host has exactly ONE loop-state write exception: timeout enforcement. During normal operation the host is a reader of `events.jsonl` and a renderer to terminal. No other section of code grants the host additional loop-state write paths. (The guarded liveness projection writes only the private Git-path sidecar — never `session.json`, `events.jsonl`, or anything under `.gator/loops/` — see the Liveness Store TRIPWIRE.)

## TRIPWIRE: Resumable Terminal Stage

`max_rounds_exceeded` is terminal but resumable — only via the Architect `extend` action (`validate_action(..., "extend")` / `advance_extended()`, #39). A coding loop's `implementation_approved` is terminal but resumable — only via the Architect `reopen` action (`host.reopen_loop()` / `advance_reopened()`, #41). `plan_approved`, `turn_timed_out`, and `ended_by_architect` are final and must never be reactivated. Code that treats "terminal" as "never changes again" (watchers, pollers, caches) must re-check the session rather than assume finality.

## TRIPWIRE: Stage-Role Consistency

Each active stage belongs to exactly one role, per the mode table's `role_by_stage`: `plan_drafting` -> draftor, `plan_review` -> reviewer, `plan_revision` -> draftor; coding: `implementation_drafting` -> draftor, `implementation_review` -> reviewer, `implementation_revision` -> draftor. `advance_unblocked()` validates this against the session's own mode. Bypassing the validation creates impossible session states.

## TRIPWIRE: Escalate Bypasses Turn Check

`validate_action()` skips the turn check for `escalate`. Either model role can escalate from any active state. This is intentional — an agent stuck waiting for a submission that will never come needs the ability to break out.

## TRIPWIRE: Role-Based Access Control

Three roles: `draftor`, `reviewer`, `architect`. Each has a token with a secret nonce. `validate_action()` enforces a strict matrix: model actions (submit-draft, submit-review, escalate) reject `architect`, architect actions (pause, interject, end, unblock, extend) reject model roles. This is a structural barrier — models don't have the architect nonce and cannot execute architect commands.

! The architect token is stored in the same `.tokens.json` as model tokens. The protection is that models are not given the token and have no protocol-sanctioned way to obtain it. This is defense-in-depth, not a cryptographic guarantee.

## Pattern: sys.path Import Model

Loop modules use `sys.path.insert(0, LOOP_DIR)` and absolute imports (`from session import ...`) rather than relative imports (`from .session import ...`). This is required because `scripts/` is shipped as package data, not an importable Python sub-package. The CLI runs scripts via subprocess, which has no package context for relative imports.

## Cross-Vendor Orientation

Models join a loop via the "gator loop join" instruction in their vendor entry point (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`). The source of truth for this instruction is `render_entry_content()` in `gatorize/entry_points.py` — see [Installer charter](scripts-installer.md). Claude Code also has a `/loop-join` slash command (`templates/gator-starter/commands/loop-join.md`) as a convenience layer. The behavioral protocol is at `procedures/gator-loop-protocol.md`. Artifact format templates are at `reference-notes/loop-artifact-formats.md`. Both files exist as byte-identical pairs between `.gator/.includes/` and `src/.../templates/gator-starter/`; change both copies in the same commit. The participant watcher receiver contract (#36) is at `reference-notes/loop-participant-watcher.md` (same byte-identical pair rule; listed in both `gator_layout.py` shipped-defaults copies). The protocol's Step 1 documents the watcher as optional and only for runtimes that re-invoke the agent when a background command exits (Claude Code background Bash, open session, per the M0 spike); `/loop-join` (`.claude/commands/` and the template copy, byte-identical) gives the Claude Code launch line. Coding loops (#41) are documented in the protocol's "Coding Loops (Implementation Review)" section, which has its own state table pinned to `CODING_ALL_STAGES` by `test_protocol_coding_state_table_matches_state_machine`. The planning "State Machine" table stays pinned to `ALL_STAGES`. The implementation template in `loop-artifact-formats.md` is pinned to `submit.IMPLEMENTATION_HEADINGS` by `test_implementation_template_matches_cli_headings`, and `/loop-join` carries the coding steps (both copies byte-identical). The vendor-neutral entry paragraph from `render_entry_content()` deliberately stays on bounded `wait` — it is shared by CLAUDE.md / AGENTS.md / GEMINI.md, and the watcher is not supported for every vendor.

The protocol's escalation section classifies uncertainty into non-blocking (state an assumption, proceed) and blocking (Architect-owned, escalate with `--file`). The artifact format's plan template uses "Assumptions, Risks, and Required Architect Decisions" (not "Risks and Open Questions") to reinforce this classification. The findings template documents that an ESCALATE verdict must be accompanied by `gator loop escalate` — `submit-review` alone enters revision, not blocked state.

## Before Changing This Module

- Preserve lock ordering, role authorization, and stage/turn invariants.
- Exercise timeout, pause, escalation, interjection, unblock, and terminal transitions.
- Keep CLI output and the loop protocol aligned.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) -- Package CLI Entry Point (cli.py COMMANDS dict), sys.path import convention
-> [Core Library](scripts-core-library.md) -- `find_gator_root()`, `ensure_utf8_stdout()`, `get_version()`
-> [Installer and Boot](scripts-installer.md) -- `render_entry_content()` cross-vendor orientation, `/loop-join` command template
-> [Dashboard Server](scripts-dashboard.md) -- calls `init_loop()`, `watch_loop()`, `acquire_host_lock()`, `find_active_loop()`, `resolve_token()`, `load_tokens()`
