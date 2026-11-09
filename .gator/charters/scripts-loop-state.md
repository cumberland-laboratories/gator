# Charter: Loop State

**Covers**: `src/gator_command/scripts/loop/__init__.py`, `src/gator_command/scripts/loop/session.py`, `src/gator_command/scripts/loop/state_machine.py`, `src/gator_command/scripts/loop/events.py`

## Owns

The governed planning loop — a CLI-mediated debate between two AI models (draftor, reviewer) with role tokens, turn-taking, bounded iteration, Architect oversight of long turns (attention notices for attention-mode loops; hard turn timeouts for legacy loops only), and durable session residue.

- `session.py` owns the fixed-artifact verifier, governed input reading and planning provenance, session CRUD, token generation/resolution (with secret nonce), platform-aware file locking, atomic writes, turn tracking, and loop ID generation
- `state_machine.py` owns state categorization (active/paused/terminal), action validation, and all state transitions, indexed by loop mode through the single `STAGES` table (planning; coding)
- `events.py` owns event emission (append to events.jsonl), event tailing, and human-readable formatting

## Does Not Own

- Code implementation loop (this is planning-phase only)
- Submit handlers, artifact validation and the CLI; see [Loop Commands](scripts-loop-commands.md).
- Loop creation, hosting, attention, liveness and the Codex launcher; see [Loop Lifecycle and Hosting](scripts-loop-host.md).

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

### attention_mode(session)
File: `src/gator_command/scripts/loop/session.py`
The ONLY gate for attention-interval semantics. It is true when `contract.attention_interval` is an int ≥ 1, never a bool. Non-dict sessions and contracts give False. Nothing is inferred from dates, versions or field presence, and legacy sessions keep their recorded hard-timeout behavior.
<- `state_machine._begin_turn()` / `_end_turn()`

### create_session(feature, loop_id, max_rounds, turn_timeout, mode="planning", coding=None, brief=None)
File: `src/gator_command/scripts/loop/session.py`
Builds the initial session dict including empty `decisions: []` ledger. Does not write to disk.
- Planning sessions keep `"mode": "planning-only"` and stage `plan_drafting`. They also carry `"contract": {"context_evidence": 1}`, the migration boundary: only flagged sessions get Context Checked enforcement; sessions created before the flag existed never do.
- `brief`: top-level brief metadata when a brief was supplied. The key is absent otherwise, so no-brief sessions are unchanged.
- **Attention interval:** every NEW session (planning and coding) carries `contract.attention_interval: 1`, so planning has `{context_evidence: 1, attention_interval: 1}` and coding has `{attention_interval: 1}`. Context Checked stays planning-only because its gate reads only `context_evidence`.
  - **Initial turn:** flagged sessions start with `turn_deadline: null`, `turn_started_at` (ISO UTC, the per-turn attention key) and `attention_notified_turn: null`.
  - **Interval storage:** `turn_timeout_seconds` stores the Architect attention interval (default `DEFAULT_ATTENTION_INTERVAL = 300`).
- **Coding checkpoints:** NEW planning sessions also carry `contract.coding_checkpoints: CHECKPOINT_CONTRACT` (1). This flag is the draft-gate migration boundary for `## Coding Checkpoints`; coding sessions never carry it.
  - **Legacy:** unflagged sessions keep their historical hard-timeout shape.
- **Executive summary:** NEW planning AND coding sessions carry `contract.executive_summary: EXECUTIVE_SUMMARY_CONTRACT` (1). It is the migration boundary for the one-paragraph `## Executive Summary` and its event projection; a coding loop gets it at its own creation, whatever its source loop had. New planning sessions are therefore `{attention_interval, executive_summary, context_evidence, coding_checkpoints}` and coding sessions `{attention_interval, executive_summary}`.
- Coding sessions' `coding` block gains `source_brief` (metadata or null) and `source_brief_decision` (`kept` / `dropped` / `none_available`).
- Coding sessions carry `"mode": "coding"`, stage `implementation_drafting` (Draftor), `plan_status: "implementation"`, `current.implementation`, and the required `coding` binding `{source_loop_id, plan_sha256, base_head, base_tree, generations: [], approval: null}`.
- A coding session without its binding, or an unknown mode, raises ValueError.
Filesystem: none
<- `host.init_loop()`, `host._init_coding_loop()`

### Architect brief: validate_brief_bytes / brief_bytes_from_text / read_brief_file / brief_meta / verify_brief / read_verified_brief / brief_status_view
File: `src/gator_command/scripts/loop/session.py`
An optional, immutable Markdown brief supplied at loop creation. It is stored as `architect-brief.md`, or, for a carried-forward planning brief in a coding loop, as `source-architect-brief.md`. Sessions record only metadata, `{artifact, sha256, bytes}`.
- **Validation** (`validate_brief_bytes`): UTF-8, non-blank, no NUL, **≤ `MAX_BRIEF_BYTES` = 32,768 bytes**.
  - `brief_bytes_from_text` (Dashboard text): a blank string means no brief, and CRLF/CR are normalized to LF.
  - `read_brief_file` (CLI): a regular file only. Symlinks and **Windows reparse points / junctions** are refused first, before `exists` / `is_file` / `stat` / `open`, using the same `_is_reparse_point` guard as `verify_brief`, so the input and stored-artifact trust boundaries match. Directories are refused, and the size is checked before reading.
- **`verify_brief(loop_dir, ref, expected_name)`** takes a FIXED expected name and never a path from session data. It returns one result string and never content:

  | Result | Meaning |
  |---|---|
  | `absent` | ref is None: neutral, hidden everywhere |
  | `invalid_ref` | present but malformed / wrong-typed, or names a file other than `expected_name` (positional binding) |
  | `unsafe` | symlink, reparse point (`lstat` attribute `0x400`), or escapes the loop dir |
  | `missing` | no regular file |
  | `unreadable` | read error |
  | `mismatch` | size or SHA-256 differs |
  | `ok` | matches |

- **`read_verified_brief`** returns the exact verified bytes (used for carry-forward).
- **`brief_status_view(ref, expected_name)`** is the strict, positionally bound status view: `{artifact, sha256, bytes}` or None. Unknown keys such as `content` or `path` are always dropped.

### Fixed immutable artifacts: FIXED_ARTIFACT_LIMITS / _valid_fixed_ref / verify_fixed_artifact / read_verified_fixed_artifact / fixed_artifact_view
File: `src/gator_command/scripts/loop/session.py`
One generic verifier owns the closed allowlist of fixed artifact names, each name's byte limit, the fixed-path safety checks and the result codes.
- **Allowlist (`FIXED_ARTIFACT_LIMITS`):**

  | Name | Limit |
  |---|---|
  | `architect-brief.md`, `source-architect-brief.md` | `MAX_BRIEF_BYTES` 32 KiB |
  | `architect-plan.md` | `MAX_PLAN_BYTES` 256 KiB |
  | `revision-baseline-plan.md`, `revision-baseline-approval.md` | `MAX_BASELINE_BYTES` 1 MiB |

- **`_valid_fixed_ref`** accepts an allowlisted name, `artifact == expected_name` (positional binding), a 64-hex sha256, and int `bytes` within the name's limit.
- **`verify_fixed_artifact`** returns the same results as `verify_brief` (absent / invalid_ref / unsafe / missing / unreadable / mismatch / ok; neutral `FIXED_*` aliases with identical values). It reads at most `limit + 1` bytes.
- **Other helpers:** `read_verified_fixed_artifact` returns the exact verified bytes; `fixed_artifact_view` is the strict `{artifact, sha256, bytes}` status view.
- **Brief wrappers:** `verify_brief` / `read_verified_brief` / `brief_status_view` are now brief-scoped wrappers. Results for the two brief names are unchanged, and any other name gives `invalid_ref` / `(invalid_ref, None)` / None.
<- `host._write_brief` (via `verify_brief`), `host._write_fixed_artifact`, `cli._plan_source_view`
! Callers pass FIXED name constants only, never a path from session data.

### read_governed_input(path, repo_root, max_bytes, label)
File: `src/gator_command/scripts/loop/session.py`
The trust boundary for Architect-supplied input files (an Architect plan; the sketch of a revision). Rules:
- the file is inside `repo_root`;
- the lexical absolute path equals `resolve(strict=True)` (case-normalized), which refuses symlinked or junction components and short-name aliases;
- the file is not a link or reparse point, and is a regular file of `1..max_bytes` bytes;
- it is read ONCE, and a size or mtime change across the read is refused;
- the content is UTF-8, has no NUL and is not blank.

It returns the exact bytes and raises `ValueError` / `FileNotFoundError`. The ordinary `--sketch` path does not use it (unchanged).

### planning_source(session) / plan_source_ref(session)
File: `src/gator_command/scripts/loop/session.py`
The ONLY way a planning loop's source kind may be read:
- `sketch`: neither block present (ordinary and legacy loops);
- `architect_plan`: a valid `plan_source` block `{kind: "architect", artifact: "architect-plan.md", sha256, bytes}`;
- `revision`: a valid `revision` block `{source_loop_id, baseline: {artifact: "revision-baseline-plan.md", sha256, bytes}, approval: {artifact: "revision-baseline-approval.md", sha256, bytes, source_artifact: "findings.round-N.md"}}`. `revision_refs(session)` returns `(source_loop_id, baseline_ref, approval_ref)`.

Both blocks, or a malformed block, raise `ValueError` (fail closed). The source is never inferred from filenames or the stage. `create_session(..., plan_source=None, revision=None)` stores the blocks, refuses both together, and refuses either on a coding session.

### loop_mode(session)
File: `src/gator_command/scripts/loop/session.py`
The ONLY way loop mode may be read. It returns `"planning"` for a missing `mode` or the legacy `"planning-only"` / `"planning"` values, and `"coding"` for `"coding"`; any other value raises ValueError (fail closed).
<- `state_machine` categorizers and `validate_action`, `host._read_approved_source()`, `cli._mode_of()`
! `create_session()` still WRITES `"planning-only"` for planning loops; never compare `session["mode"]` directly.

### validate_turn_timeout(value) / validate_round_count(value) / _validate_bounded_int(...)
File: `src/gator_command/scripts/loop/session.py`
Single validation paths for Architect-chosen loop integers, both built on `_validate_bounded_int()`: `validate_turn_timeout` returns an int in `TURN_TIMEOUT_MIN..TURN_TIMEOUT_MAX` (30..3600); `validate_round_count` returns an int in `ROUNDS_MIN..ROUNDS_MAX` (1..20, the same bound as Dashboard start `max_rounds`) — used for the per-extension increment. Both raise `ValueError`, reject bool/floats/non-integer strings, and accept plain-integer strings (CLI input). No total round ceiling is enforced.
Filesystem: none
<- turn timeout: `submit.handle_unblock()`, `cli._turn_timeout_arg()`, dashboard `_handle_loop_start()` / `_handle_loop_unblock()`; round count: `submit.handle_extend()`
! CLI `start --turn-timeout` is deliberately NOT routed through this (tests and local tooling use short windows); the Dashboard start and every unblock path are. Default window stays 300s.

### checkpoint_manifest(session) / active_checkpoint(session) / declared_checkpoint(session) / build_checkpoint_manifest(items, source, base_tree)
File: `src/gator_command/scripts/loop/session.py`
- **`checkpoint_manifest`** is the single gate for checkpoint behaviour. It returns `coding.checkpoints` only when the manifest is well-formed (`contract == CHECKPOINT_CONTRACT`, non-empty `items`, in-range int `current`); otherwise it returns None and the session keeps the transitions of a loop without checkpoints.
- **`active_checkpoint`** returns `(index, item, count)`.
- **`declared_checkpoint`** returns the same, but only for `source: "declared"`. The implicit manifest (`IMPLICIT_CHECKPOINT`, one `Full implementation` item for a plan without declared checkpoints) tracks state but keeps the legacy participant surface: `--checkpoint` is optional, and Commit State and Reviewed Candidate render byte-identically. Its base is the loop base, so its checkpoint diff is the loop diff.
- **`checkpoint_summary`** returns the compact counters `{index (1-based), count, id, title, state, findings_round, findings_budget (= max_rounds), generation (latest index or None)}` for a **declared** loop, built from validated primitives. Otherwise it returns None. Every display surface (CLI status, wait, list, and the Dashboard `/loops`) uses it **instead of** `Round X/Y`.
- **`build_checkpoint_manifest`** produces `{contract, source, current: 0, items: [{id, title, scope, verify, state, base_tree, findings_rounds: 0, accepted: null}]}`. The first item is `active` on the given base tree; the rest are `pending` with a null base.

### load_session(loop_dir) / save_session(loop_dir, session)
File: `src/gator_command/scripts/loop/session.py`
Read/write session.json. Save uses atomic temp+rename. Sets read-only (444) on POSIX after write.
Filesystem: `.gator/loops/<loop-id>/session.json` (RW)
! **Test hygiene:** loop files (`session.json`, plan, findings and implementation artifacts, briefs) are read-only on POSIX, and `_make_readonly` is a no-op on Windows. A test that tampers with one directly must call `_make_writable(path)` (or `os.chmod`) first. A miss passes on Windows and fails only on the POSIX CI legs, as `test_corrupt_session_json_retries` did at 2.19.0.
<- all loop modules
-> `_retry_sharing()`
! Atomic rename prevents partial reads by the host's non-locking read path.
! **Windows sharing violations, `_retry_sharing(fn, path)` / `_is_sharing_violation()` / `SessionBusyError`.** On Windows, `os.replace()` onto `session.json` fails with `PermissionError` (winerror 5, `ERROR_ACCESS_DENIED`) while any reader has the file open. An open can also fail with winerror 32 during a replace.
  - **Retry:** the save's replace and the load's read retry only these two winerrors, up to `SHARING_RETRY_ATTEMPTS` (10) times, with backoff starting at 0.01 s, doubling, and capped at 0.2 s (about 1.2 s worst case).
  - **When retries run out:** `SessionBusyError` (an `OSError` with errno `EBUSY`, deliberately **not** a `PermissionError`) means nothing was written, the old file is intact, and the temp file was removed.
  - **Read-side variant:** an `open()` during a replace fails with `PermissionError` errno `EACCES` and no `winerror`, because the C runtime sets only `errno`. On Windows that also counts as transient. Trade-off: a genuine Windows ACL denial on `session.json` surfaces as `SessionBusyError` after the retry window, instead of immediately as `PermissionError`.
  - **POSIX is unchanged:** it never sets `winerror`, and the `EACCES` rule applies on Windows only.
  - **Never** fall back to writing `session.json` in place; the replace is the atomicity guarantee.
  - **Limit:** readers that re-open the file with no pause at all can starve a save past the window. Measured: four zero-gap readers left 95 of 100 saves busy on this machine, and four readers at 1 ms gaps starved a save on Windows CI py3.9 (slower runner), while 1 ms gaps left none locally. The regression test therefore uses two readers at 10 ms. Every real reader polls (the Dashboard every 3 s). A new reader must not read `session.json` in a tight loop.
  - **Locks:** the retry holds no lock of its own. A save retries inside the session lock its caller already holds (and inside `start.lock` for extend/reopen), never inside a Dashboard state lock or the liveness lock.
  - **Callers:** a non-locking reader that catches `OSError` (host watcher, `wait`) simply polls again. The Dashboard maps errno `EBUSY` to 503 "loop is busy; retry" (`_LOOP_LOCK_BUSY_ERRNOS`).
  - **Pinned by** `tests/test_loop_session_sharing.py`.

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

### validate_action(session, role, action)
File: `src/gator_command/scripts/loop/state_machine.py`
Checks terminal, blocked, role, stage, and turn ownership. Returns (allowed, reason).
- Model rules are mode-indexed (`_MODEL_ACTION_RULES_BY_MODE`):
  - planning: `submit_draft` / `submit_review` / `escalate`;
  - coding: `submit_implementation` (Draftor, `implementation_drafting` / `implementation_revision`), `submit_review` (Reviewer, `implementation_review`), `escalate`.

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

### _begin_turn(session, turn_timeout) / _end_turn(session)
File: `src/gator_command/scripts/loop/state_machine.py`
The single place every transition starts or ends an active turn.
- `_begin_turn`, called by draft/review revise, unblock, extend, implementation submit/revise and reopen:
  - **flagged:** `turn_deadline = None` and a fresh `turn_started_at`;
  - **legacy:** `turn_deadline = _deadline_from_now(turn_timeout)`, byte-for-byte as before.
- `_end_turn`, called by approve, max rounds, escalate, pause, end and the legacy timeout: clears `turn_deadline`; flagged sessions also clear `turn_started_at`.
- Interject touches neither.
- A new turn always gets a new `turn_started_at`, so each turn has an independent attention key.
! Never set `turn_deadline` for a flagged session: the legacy enforcement path keys on it (defense in depth).

### enter_architect_plan_review(session, turn_timeout)
File: `src/gator_command/scripts/loop/state_machine.py`
A fresh planning session (`plan_drafting`, round 0, at most the one Architect turn) enters the EXISTING `plan_review` stage, with the owner from `role_by_stage` (the Reviewer), `plan_status = in_review` and `_begin_turn()`. There is no new stage. Approval leads to `plan_approved` and findings to Draftor `plan_revision` through the ordinary transitions. Anything else raises `ValueError`.
<- `host._init_architect_plan_loop()`

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

### _suspend(session, stage, pause_reason=None) / _clear_suspension(status)
File: `src/gator_command/scripts/loop/state_machine.py`
The single suspend path and the single clear path.
- **`_suspend`** requires an active loop and a paused target stage (otherwise `ValueError`, before mutation). It saves `resume_stage` / `resume_next_role`, sets `suspended_at` (ISO UTC) and `pause_reason` (a pause only, else None), sets `next_role = None` and `blocked = True`, and ends the turn. It never changes `architect_message` (it only ensures the key exists).
- **`_clear_suspension`** nulls `resume_*`, `suspended_at` and `pause_reason`. It is used by unblock, extend, reopen and end.
<- `advance_escalated()`, `advance_paused_by_architect()`; clear <- `advance_unblocked()`, `advance_extended()`, `advance_reopened()`, `advance_ended_by_architect()`

### _set_architect_message(status, message, recipient, artifact=None, decision_id=None) / _clear_architect_message(status) / _consume_architect_message(status, role)
File: `src/gator_command/scripts/loop/state_machine.py`
The model-facing Architect message is recipient-scoped: `architect_message`, `architect_response_artifact`, `architect_message_for` (`draftor` / `reviewer` / None) and `architect_message_decision` always move together. `architect_message_decision` is set only by the unblock that resolves that decision (`advance_unblocked(..., decision_id=)`); every other message write resets it, so a later pause or interjection message never inherits an old decision label.
- **Recipients:** interject goes to the turn owner; an unblock that resolves a decision goes to `request.role`; any other unblock message goes to the resumed role; extend and reopen go to the resumed Draftor.
- **`_consume_architect_message(status, role)`** runs on every non-terminal model submission. It clears the message only when it is addressed to `role`, or is unscoped (None: the rule for sessions from before recipient-scoped messages).
- **Terminal transitions** (approve, max rounds) clear the message unconditionally.
- A newer Architect message (interject or unblock with a message) replaces an older one; there is one slot.

### advance_escalated(session, reason)
File: `src/gator_command/scripts/loop/state_machine.py`
Any active -> `blocked_on_architect` via `_suspend()`; sets `architect_action_required`.
Filesystem: none (mutates session dict)
<- `submit.handle_escalate()`

### advance_unblocked(session, stage, next_role, turn_timeout, message=None, recipient=None, artifact=None)
File: `src/gator_command/scripts/loop/state_machine.py`
Paused -> restored active state. Validates stage-role consistency. Receives the already-selected interval/timeout (the caller owns CLI/HTTP policy and persisting any changed legacy window; attention-mode loops refuse a change) and starts a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode: no deadline) or a fresh deadline (legacy).
- **Messages:** with a message or artifact, it stores them for `recipient`, or the resumed role when `recipient` is None. Without either, it **keeps** any unread message.
- **Legacy pause:** a session paused before suspension fields existed has no `suspended_at` key. It keeps the old behaviour (the message is cleared), so its old pause reason, which was stored in `architect_message`, is never re-shown.
- It always calls `_clear_suspension()`.
Filesystem: none (mutates session dict)
<- `submit.handle_unblock()`
! Stage-role validation comes from the session's mode table (`stages_for(session)`): the target must be an active stage of THIS mode, owned by `role_by_stage` (planning: `plan_drafting` / `plan_revision` → draftor, `plan_review` → reviewer; coding: `implementation_drafting` / `implementation_revision` → draftor, `implementation_review` → reviewer). A cross-mode target or a mismatched role raises ValueError.

### advance_extended(session, rounds, turn_timeout, message=None)
File: `src/gator_command/scripts/loop/state_machine.py`
`max_rounds_exceeded` -> the mode table's `extension_resume_stage` (`plan_revision` for planning, `implementation_revision` for coding; next_role from `role_by_stage`, the Draftor) with `max_rounds += rounds`. Preserves `round`, `current`, `turns`, `decisions`, `unresolved_findings`. Resets `plan_status="revision"`, `blocked=False`, `architect_action_required=False`, the suspension fields (`_clear_suspension`), and `architect_response_artifact`; sets `architect_message=message` for the Draftor (`_set_architect_message`) and starts a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode: no deadline) or a fresh deadline (legacy). Returns `(previous_max_rounds, new_max_rounds)`.
Filesystem: none (mutates session dict)
<- `submit.handle_extend()`
! All guards run before any mutation: source stage must be exactly `EXTENDABLE_STAGE`; `rounds` a positive int (bool rejected); `round <= max_rounds`. For checkpoint loops that guard is instead the active item's `findings_rounds <= max_rounds`, because `status.round` is informational there and may exceed `max_rounds`. Violations raise ValueError. Input range policy (1..20) belongs to the caller.

### advance_turn_timed_out(session, timed_out_role)
File: `src/gator_command/scripts/loop/state_machine.py`
Any active -> `turn_timed_out` (terminal).
Filesystem: none (mutates session dict)
<- `host._try_enforce_timeout()`

### advance_implementation_submitted(session, turn_timeout)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only: `implementation_drafting` / `implementation_revision` -> `implementation_review` (Reviewer) with a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode: no deadline) or a fresh deadline (legacy). It clears `architect_message` and the response artifact. A non-coding loop or another stage raises ValueError. The caller records the candidate generation.
Filesystem: none (mutates session dict)
<- `submit.handle_submit_implementation()`

### advance_implementation_reviewed(session, approved, turn_timeout, approval=None)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only, from `implementation_review`:
- **Approved:** goes to `implementation_approved` (terminal; resumable only via reopen) and stores `coding.approval = {tree, head, round, generation, ts}`, which is required.
- **Findings:** `round += 1`. At the ceiling the loop goes to `max_rounds_exceeded` (extendable); otherwise to `implementation_revision` (Draftor).
- **Checkpoint loops:**
  - **Approval of a non-final checkpoint** sets the active item's `accepted = {tree, head, generation, ts}` and `state = "approved"`, activates the next item with `base_tree = accepted.tree`, does `current += 1`, and returns to `implementation_drafting` (Draftor, fresh turn). **`coding.approval` is not touched.**
  - **The final checkpoint's approval** records `accepted` and then takes the ordinary approved path.
  - **Findings** also do `findings_rounds += 1` on the active item, and the ceiling is `findings_rounds >= max_rounds`, the per-checkpoint budget.

A wrong mode or stage raises ValueError.
<- `submit._coding_review()`

### resolve_approval(approval, snap)
File: `src/gator_command/scripts/loop/state_machine.py`
Pure. Places an approved candidate against live Git facts, checked in this order:

| Order | Condition | Result |
|---|---|---|
| 1 | no approval / invalidated | `none` / `invalidated` (`reopened`) |
| 2 | snapshot not ok | `unknown`, reason = the snapshot error |
| 3 | HEAD is the approved HEAD | `pending` if the staged tree is the approved tree (governed comparison, see below), else `stale: staged_tree_changed` |
| 4 | HEAD moved and is detached | `stale: detached_mismatch` (history is not consulted; a detached HEAD is never committed) |
| 5 | no `approval_history` dict / history `ok: false` | `unknown: history_unavailable` / `unknown`, reason = its error code |
| 6 | `successor` with the approved tree (governed comparison) | `committed`, `commit` = the successor OID (not the current HEAD) |
| 7 | `successor` with another tree | `stale: head_moved_tree_differs` |
| 8 | `diverged` (any `why`) | `stale: history_diverged` |

**Governed comparison: `same_governed(approved_tree, approved_identity, live_tree, live_identity)`** returns `(same, kind)`. When the approval carries `governed_identity` AND the live fact carries `governed_index_identity` (row 3) or `governed_tree_identity` (rows 6–7), it compares those; otherwise it compares raw tree OIDs exactly as before, so old approvals and old snapshots keep their meaning. The result gains additive `identity: "governed" | "raw"` in rows 3, 6 and 7. Effect: a hook-owned file (status, whiteboard, commit draft, commit issues, lint-allow) staged or left out never makes an approval stale or uncommitted; a source or charter change still does.

The question it answers: did the approved tree become the **immediate first-parent successor** of the approved HEAD? It never searches history for a matching tree, so a hook-altered normal commit stays stale even if a later commit restores the tree. It never reads prose, branch names or timestamps. The result keeps its keys (`approved_tree`, `approved_head`, `current_head`, `head_tree`, `staged_tree`, `detached`, `state`, `reason`, `commit`; additive `identity`) and never echoes `approval_history`.

<- `cli._approval_resolution()` (status / wait / architect status) and the Dashboard `_handle_loop_coding_snapshot()`; both pass `approved_head=approval.head` to one fresh `gitsnap.snapshot()`
! Compatibility: a correction within `gator-loop-status-v1` / `gator-loop-coding-snapshot-v1` with no bump. Committed was always meant to say the normal commit carried the reviewed tree. `head_moved_tree_differs` narrowed to the first successor. `detached_mismatch` widened to every moved detached HEAD (one sitting on the approval commit used to read Committed). `history_diverged` / `history_unavailable` are additive.
! The state strings are machine identifiers. Every display pairs them with explicit text (CLI markers `[OK]` / `[..]` / `[!!]` / `[??]` plus words), never color alone.

### advance_reopened(session, turn_timeout, message=None)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only: `implementation_approved` -> `implementation_revision` (Draftor) with a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode: no deadline) or a fresh deadline (legacy). It keeps `round`, marks `coding.approval.invalidated_at`, and sets `architect_message`. The next submission is named by its generation, so it never overwrites the approved round's artifacts. The old docstring's "round + 1" claim was never true and is corrected. In checkpoint loops the final item, which is always the active one at approval, is set back to `active` with `accepted.invalidated_at`; earlier checkpoints are never reopened. A non-coding loop or any other stage raises ValueError before mutation.
Filesystem: none (mutates session dict)
<- `submit.handle_reopen()`

### STAGES / stages_for(session)
File: `src/gator_command/scripts/loop/state_machine.py`
The single mode-indexed stage table: `{active, paused, terminal, role_by_stage, initial_stage, extension_resume_stage}` per mode.
- Planning entries are exactly the planning-only sets. `ACTIVE_STAGES` / `PAUSED_STAGES` / `TERMINAL_STAGES` and `ALL_STAGES` keep their planning meaning, and the protocol state-table test pins `ALL_STAGES`.
- Coding: `CODING_ACTIVE_STAGES` (`implementation_drafting` / `implementation_review` / `implementation_revision`), the shared paused stages, and `CODING_TERMINAL_STAGES` (`implementation_approved` plus the shared `max_rounds_exceeded` / `turn_timed_out` / `ended_by_architect`).
- `CODING_ALL_STAGES` and `EVERY_STAGE` are the unions.

### is_active(session) / is_paused(session) / is_terminal(session)
File: `src/gator_command/scripts/loop/state_machine.py`
State categorization helpers. They look up `stages_for(session)` (mode-aware); for planning sessions the result is identical to the planning-only sets, a table-driven pin. An unknown mode raises ValueError, which callers treat as "do not host / do not enforce".
Filesystem: none
<- `host.watch_loop()`, `host._try_enforce_timeout()`, `host.find_active_loop()`, `cli._cmd_status()`, `liveness._apply_projection()` / `renotify_eligibility()` / `renotify()`, dashboard `_adopt_orphaned_loops()`
! Never test raw stage membership (`stage in ACTIVE_STAGES`) outside `state_machine.py` — it silently ignores coding stages.
! `events.TERMINAL_EVENTS` includes `implementation_approved`. `watch_loop` exits only if the session is still terminal, so a reopened loop keeps hosting.

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
Human-readable formatting. Events: `[HH:MM:SS] label (detail)`. Prompt: next role and stage. `loop_extended` renders as `EXTENDED (<detail>)` and is deliberately NOT in `TERMINAL_EVENTS`.
Filesystem: none
<- `host.watch_loop()`, `cli._cmd_tail()`

---

## TRIPWIRE: Architect Brief Is Immutable Residue, Not a Channel

The Architect brief is written once at loop creation and never edited. (Verification goes through `verify_fixed_artifact`'s closed allowlist; the brief wrappers refuse every non-brief name.) Later direction goes through interject, escalate or unblock. Every read of a brief goes through `verify_brief` with the FIXED expected name for its position (`architect-brief.md` / `source-architect-brief.md`), never a path from session data. Status surfaces use only `brief_status_view` (metadata, positionally bound); brief content never appears in session, events, `/status`, or the liveness sidecar. A missing brief is `absent` and neutral, never an alarm.

Violation: trusting `session.brief.artifact` as a path enables traversal or swapped-label reads; passing raw `session.brief` through a generic status allowlist can leak injected content.

## TRIPWIRE: Checkpoint Approval Never Commits

Only the **final** checkpoint's approval writes `coding.approval`, the one-commit authority read by `resolve_approval`, which is unchanged. A non-final approval records `accepted` on the item and opens the next one. A checkpoint's base comes **only** from the previous item's `accepted.tree`, set in the same locked transition; findings never change it. There is no commit, reset, stash, or index or worktree write per checkpoint.

Violation: writing `coding.approval` on a non-final approval authorizes a partial commit. That is pinned by the transition table (`coding.approval` null, and Git HEAD, index and refs unchanged after `checkpoint_approved`).

## TRIPWIRE: Suspension Preserves the Resume Target and Never Erases Messages

`resume_stage` / `resume_next_role` / `suspended_at` are non-null **if and only if** the stage is paused. They are set only by `_suspend()` and cleared only by `_clear_suspension()` (unblock, extend, reopen, end).

A pause stores its reason in `pause_reason` and never writes `architect_message`. An unblock without a message keeps an unread message. A model submission consumes only a message addressed to that role (`architect_message_for`). Every decision request ends resolved, by a response or by `cancelled_by_end` at end.

Violations:
- Writing resume fields outside `_suspend` revives a stale target.
- A pause that writes `architect_message` erases an unread interjection or response.
- An unconditional clear on submission lets one role consume the other role's escalation response.

Pinned by `tests/test_loop_suspension.py`.

**Participant side: suspension is not departure.** Exit `2` means terminal only. Model `status` exits `1` while suspended, `wait` keeps waiting (exit `3` at a bounded deadline), and the watcher acks `architect-block` and stays registered. Making a paused stage a stop signal again (exit `2`, a `paused` wake reason, or a release on `architect-block`) disconnects the participant from a suspended loop. Pinned by `test_status_and_wait_keep_participant_in_loop`, `TestRunWatch.test_architect_block_is_acked_and_watch_continues`, `test_watcher_stays_connected_through_suspension` and `test_suspension_cycles_idempotent_across_restarts`.

## TRIPWIRE: Session Lock Write Ordering

All writers (submit commands, escalate, unblock, and the host's timeout enforcer) must save `session.json` BEFORE appending to `events.jsonl`, both inside the session lock. This guarantees the host's event-tail loop never observes an event whose session state isn't yet durable.

Violation: the host reads a terminal event, loads session.json to print a summary, but sees stale pre-terminal state.

**Sole exception: `architect_attention_due`.** `_try_record_attention` appends this event BEFORE saving its `attention_notified_turn` marker, both inside the session lock. The rule protects events that imply a state change, and this awareness-only event implies none: the marker is idempotency metadata. The inverted order is what makes a crash between the two writes recoverable, because the event is found and the marker repaired. Session-first order would instead lose the event forever behind a marker. No other event may use this exception.

## TRIPWIRE: Machine State Is Not a Loop's Repository

`session.find_gator_root()` skips `~/.gator/` (by location and by its `machine-id` / `dashboard-repos.json` files), like every other copy, so a loop command run outside a governed repository raises `FileNotFoundError` instead of treating the home directory as one. See `scripts-core-library.md` → `find_gator_root()`.

## TRIPWIRE: Token Nonce Separation

Committed `session.json` contains only role names. Secret nonces live only in gitignored `.tokens.json`. Tokens cannot be reconstructed from committed data because the nonce never appears outside `.tokens.json`.

Violation: committing `.tokens.json` or adding nonces to `session.json` makes tokens reconstructable from git history.

## TRIPWIRE: Resumable Terminal Stage

`max_rounds_exceeded` is terminal but resumable — only via the Architect `extend` action (`validate_action(..., "extend")` / `advance_extended()`). A coding loop's `implementation_approved` is terminal but resumable — only via the Architect `reopen` action (`host.reopen_loop()` / `advance_reopened()`). `plan_approved`, `turn_timed_out`, and `ended_by_architect` are final and must never be reactivated. Code that treats "terminal" as "never changes again" (watchers, pollers, caches) must re-check the session rather than assume finality.

## TRIPWIRE: Stage-Role Consistency

Each active stage belongs to exactly one role, per the mode table's `role_by_stage`: `plan_drafting` -> draftor, `plan_review` -> reviewer, `plan_revision` -> draftor; coding: `implementation_drafting` -> draftor, `implementation_review` -> reviewer, `implementation_revision` -> draftor. `advance_unblocked()` validates this against the session's own mode. Bypassing the validation creates impossible session states.

## TRIPWIRE: Escalate Bypasses Turn Check

`validate_action()` skips the turn check for `escalate`. Either model role can escalate from any active state. This is intentional — an agent stuck waiting for a submission that will never come needs the ability to break out.

## TRIPWIRE: Role-Based Access Control

Three roles: `draftor`, `reviewer`, `architect`. Each has a token with a secret nonce. `validate_action()` enforces a strict matrix: model actions (submit-draft, submit-review, escalate) reject `architect`, architect actions (pause, interject, end, unblock, extend) reject model roles. This is a structural barrier — models don't have the architect nonce and cannot execute architect commands.

! The architect token is stored in the same `.tokens.json` as model tokens. The protection is that models are not given the token and have no protocol-sanctioned way to obtain it. This is defense-in-depth, not a cryptographic guarantee.

## Pattern: sys.path Import Model

Loop modules use `sys.path.insert(0, LOOP_DIR)` and absolute imports (`from session import ...`) rather than relative imports (`from .session import ...`). This is required because `scripts/` is shipped as package data, not an importable Python sub-package. The CLI runs scripts via subprocess, which has no package context for relative imports.

## Before Changing This Module

- Preserve lock ordering, role authorization, and stage/turn invariants.
- Exercise timeout, pause, escalation, interjection, unblock, and terminal transitions.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) -- Package CLI Entry Point (cli.py COMMANDS dict), sys.path import convention
-> [Dashboard Server](scripts-dashboard.md) -- calls `init_loop()`, `watch_loop()`, `acquire_host_lock()`, `find_active_loop()`, `resolve_token()`, `load_tokens()`
-> [Loop Commands](scripts-loop-commands.md) -- handlers that call the transitions and session helpers here
-> [Loop Lifecycle and Hosting](scripts-loop-host.md) -- loop creation, the host watcher and liveness, built on this session model
