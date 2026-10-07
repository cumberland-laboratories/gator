# Charter: Gator Loop

**Covers**: `src/gator_command/scripts/loop/__init__.py`, `src/gator_command/scripts/loop/session.py`, `src/gator_command/scripts/loop/events.py`, `src/gator_command/scripts/loop/state_machine.py`, `src/gator_command/scripts/loop/submit.py`, `src/gator_command/scripts/loop/host.py`, `src/gator_command/scripts/loop/cli.py`, `src/gator_command/scripts/loop/liveness.py`, `src/gator_command/scripts/loop/gitsnap.py`, `src/gator_command/scripts/gator-loop.py`

## Owns

The governed planning loop — a CLI-mediated debate between two AI models (draftor, reviewer) with role tokens, turn-taking, bounded iteration, Architect oversight of long turns (attention notices for attention-mode loops, #47; hard turn timeouts for legacy loops only), and durable session residue.

- `session.py` owns the fixed-artifact verifier, governed input reading and planning provenance (#51), session CRUD, token generation/resolution (with secret nonce), platform-aware file locking, atomic writes, turn tracking, and loop ID generation
- `state_machine.py` owns state categorization (active/paused/terminal), action validation, and all state transitions, indexed by loop mode through the single `STAGES` table (planning; coding #41)
- `events.py` owns event emission (append to events.jsonl), event tailing, and human-readable formatting
- `submit.py` owns the ten submit handlers: submit-draft, submit-implementation (coding, #41), submit-review, escalate, unblock, extend, reopen (#41), pause, interject, end; plus the coding implementation-artifact helpers (required headings, the CLI-owned Commit State section)
- `host.py` owns loop initialization (`init_loop()` and `start_loop()`), the single-active guard for extension (`extend_loop()`), the watch loop (attention recording for attention-mode loops, #47; legacy timeout enforcement otherwise), platform-aware file locking (`host.lock`, `start.lock`, plus retrying watcher attachment), and active-loop scanning
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

### attention_mode(session) (#47)
File: `src/gator_command/scripts/loop/session.py`
The ONLY gate for attention-interval semantics. It is true when `contract.attention_interval` is an int ≥ 1, never a bool. Non-dict sessions and contracts give False. Nothing is inferred from dates, versions or field presence, and legacy sessions keep their recorded hard-timeout behavior.
<- `state_machine._begin_turn()` / `_end_turn()`

### create_session(feature, loop_id, max_rounds, turn_timeout, mode="planning", coding=None, brief=None)
File: `src/gator_command/scripts/loop/session.py`
Builds the initial session dict including empty `decisions: []` ledger. Does not write to disk.
- Planning sessions keep `"mode": "planning-only"` and stage `plan_drafting`. Since #46 they also carry `"contract": {"context_evidence": 1}`, the migration boundary: only flagged sessions get Context Checked enforcement, and sessions created earlier never do.
- `brief` (#43): top-level brief metadata when a brief was supplied. The key is absent otherwise, so no-brief sessions are unchanged.
- **#47 attention interval:** every NEW session (planning and coding) carries `contract.attention_interval: 1`, so planning has `{context_evidence: 1, attention_interval: 1}` and coding has `{attention_interval: 1}`. Context Checked stays planning-only because its gate reads only `context_evidence`.
  - **Initial turn:** flagged sessions start with `turn_deadline: null`, `turn_started_at` (ISO UTC, the per-turn attention key) and `attention_notified_turn: null`.
  - **Interval storage:** `turn_timeout_seconds` stores the Architect attention interval (default `DEFAULT_ATTENTION_INTERVAL = 300`).
- **#55 coding checkpoints:** NEW planning sessions also carry `contract.coding_checkpoints: CHECKPOINT_CONTRACT` (1). This flag is the draft-gate migration boundary for `## Coding Checkpoints`; coding sessions never carry it.
  - **Legacy:** unflagged sessions keep their historical hard-timeout shape.
- Coding sessions' `coding` block gains `source_brief` (metadata or null) and `source_brief_decision` (`kept` / `dropped` / `none_available`).
- Coding sessions (#41) carry `"mode": "coding"`, stage `implementation_drafting` (Draftor), `plan_status: "implementation"`, `current.implementation`, and the required `coding` binding `{source_loop_id, plan_sha256, base_head, base_tree, generations: [], approval: null}`.
- A coding session without its binding, or an unknown mode, raises ValueError.
Filesystem: none
<- `host.init_loop()`, `host._init_coding_loop()`

### Architect brief (#43): validate_brief_bytes / brief_bytes_from_text / read_brief_file / brief_meta / verify_brief / read_verified_brief / brief_status_view
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

### Fixed immutable artifacts (#51): FIXED_ARTIFACT_LIMITS / _valid_fixed_ref / verify_fixed_artifact / read_verified_fixed_artifact / fixed_artifact_view
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

### read_governed_input(path, repo_root, max_bytes, label) (#51)
File: `src/gator_command/scripts/loop/session.py`
The trust boundary for Architect-supplied input files (an Architect plan; the revision sketch in checkpoint 2). Rules:
- the file is inside `repo_root`;
- the lexical absolute path equals `resolve(strict=True)` (case-normalized), which refuses symlinked or junction components and short-name aliases;
- the file is not a link or reparse point, and is a regular file of `1..max_bytes` bytes;
- it is read ONCE, and a size or mtime change across the read is refused;
- the content is UTF-8, has no NUL and is not blank.

It returns the exact bytes and raises `ValueError` / `FileNotFoundError`. The ordinary `--sketch` path does not use it (unchanged).

### planning_source(session) / plan_source_ref(session) (#51)
File: `src/gator_command/scripts/loop/session.py`
The ONLY way a planning loop's source kind may be read:
- `sketch`: neither block present (ordinary and legacy loops);
- `architect_plan`: a valid `plan_source` block `{kind: "architect", artifact: "architect-plan.md", sha256, bytes}`;
- `revision`: a valid `revision` block `{source_loop_id, baseline: {artifact: "revision-baseline-plan.md", sha256, bytes}, approval: {artifact: "revision-baseline-approval.md", sha256, bytes, source_artifact: "findings.round-N.md"}}`. `revision_refs(session)` returns `(source_loop_id, baseline_ref, approval_ref)`.

Both blocks, or a malformed block, raise `ValueError` (fail closed). The source is never inferred from filenames or the stage. `create_session(..., plan_source=None, revision=None)` stores the blocks, refuses both together, and refuses either on a coding session.

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

### checkpoint_manifest(session) / active_checkpoint(session) / declared_checkpoint(session) / build_checkpoint_manifest(items, source, base_tree) (#55)
File: `src/gator_command/scripts/loop/session.py`
- **`checkpoint_manifest`** is the single gate for checkpoint behaviour. It returns `coding.checkpoints` only when the manifest is well-formed (`contract == CHECKPOINT_CONTRACT`, non-empty `items`, in-range int `current`); otherwise it returns None and the session keeps the pre-#55 transitions.
- **`active_checkpoint`** returns `(index, item, count)`.
- **`declared_checkpoint`** returns the same, but only for `source: "declared"`. The implicit manifest (`IMPLICIT_CHECKPOINT`, one `Full implementation` item for a pre-#55 plan) tracks state but keeps the legacy participant surface: `--checkpoint` is optional, and Commit State and Reviewed Candidate render byte-identically. Its base is the loop base, so its checkpoint diff is the loop diff.
- **`checkpoint_summary`** (M3/M4) returns the compact counters `{index (1-based), count, id, title, state, findings_round, findings_budget (= max_rounds), generation (latest index or None)}` for a **declared** loop, built from validated primitives. Otherwise it returns None. Every display surface (CLI status, wait, list, and the Dashboard `/loops`) uses it **instead of** `Round X/Y`.
- **`build_checkpoint_manifest`** produces `{contract, source, current: 0, items: [{id, title, scope, verify, state, base_tree, findings_rounds: 0, accepted: null}]}`. The first item is `active` on the given base tree; the rest are `pending` with a null base.

### load_session(loop_dir) / save_session(loop_dir, session)
File: `src/gator_command/scripts/loop/session.py`
Read/write session.json. Save uses atomic temp+rename. Sets read-only (444) on POSIX after write.
Filesystem: `.gator/loops/<loop-id>/session.json` (RW)
! **Test hygiene:** loop files (`session.json`, plan, findings and implementation artifacts, briefs) are read-only on POSIX, and `_make_readonly` is a no-op on Windows. A test that tampers with one directly must call `_make_writable(path)` (or `os.chmod`) first. A miss passes on Windows and fails only on the POSIX CI legs, as `test_corrupt_session_json_retries` did at 2.19.0.
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

### _begin_turn(session, turn_timeout) / _end_turn(session) (#47)
File: `src/gator_command/scripts/loop/state_machine.py`
The single place every transition starts or ends an active turn.
- `_begin_turn`, called by draft/review revise, unblock, extend, implementation submit/revise and reopen:
  - **flagged:** `turn_deadline = None` and a fresh `turn_started_at`;
  - **legacy:** `turn_deadline = _deadline_from_now(turn_timeout)`, byte-for-byte as before.
- `_end_turn`, called by approve, max rounds, escalate, pause, end and the legacy timeout: clears `turn_deadline`; flagged sessions also clear `turn_started_at`.
- Interject touches neither.
- A new turn always gets a new `turn_started_at`, so each turn has an independent attention key.
! Never set `turn_deadline` for a flagged session: the legacy enforcement path keys on it (#47 defense in depth).

### enter_architect_plan_review(session, turn_timeout) (#51)
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

### _suspend(session, stage, pause_reason=None) / _clear_suspension(status) (#53)
File: `src/gator_command/scripts/loop/state_machine.py`
The single suspend path and the single clear path.
- **`_suspend`** requires an active loop and a paused target stage (otherwise `ValueError`, before mutation). It saves `resume_stage` / `resume_next_role`, sets `suspended_at` (ISO UTC) and `pause_reason` (a pause only, else None), sets `next_role = None` and `blocked = True`, and ends the turn. It never changes `architect_message` (it only ensures the key exists).
- **`_clear_suspension`** nulls `resume_*`, `suspended_at` and `pause_reason`. It is used by unblock, extend, reopen and end.
<- `advance_escalated()`, `advance_paused_by_architect()`; clear <- `advance_unblocked()`, `advance_extended()`, `advance_reopened()`, `advance_ended_by_architect()`

### _set_architect_message(status, message, recipient, artifact=None, decision_id=None) / _clear_architect_message(status) / _consume_architect_message(status, role) (#53)
File: `src/gator_command/scripts/loop/state_machine.py`
The model-facing Architect message is recipient-scoped: `architect_message`, `architect_response_artifact`, `architect_message_for` (`draftor` / `reviewer` / None) and `architect_message_decision` always move together. `architect_message_decision` is set only by the unblock that resolves that decision (`advance_unblocked(..., decision_id=)`); every other message write resets it, so a later pause or interjection message never inherits an old decision label.
- **Recipients:** interject goes to the turn owner; an unblock that resolves a decision goes to `request.role`; any other unblock message goes to the resumed role; extend and reopen go to the resumed Draftor.
- **`_consume_architect_message(status, role)`** runs on every non-terminal model submission. It clears the message only when it is addressed to `role`, or is unscoped (None: the pre-#53 rule).
- **Terminal transitions** (approve, max rounds) clear the message unconditionally.
- A newer Architect message (interject or unblock with a message) replaces an older one; there is one slot.

### advance_escalated(session, reason)
File: `src/gator_command/scripts/loop/state_machine.py`
Any active -> `blocked_on_architect` via `_suspend()`; sets `architect_action_required`.
Filesystem: none (mutates session dict)
<- `submit.handle_escalate()`

### advance_unblocked(session, stage, next_role, turn_timeout, message=None, recipient=None, artifact=None)
File: `src/gator_command/scripts/loop/state_machine.py`
Paused -> restored active state. Validates stage-role consistency. Receives the already-selected interval/timeout (the caller owns CLI/HTTP policy and persisting any changed legacy window; attention-mode loops refuse a change, #47) and starts a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode, #47: no deadline) or a fresh deadline (legacy).
- **#53 messages:** with a message or artifact, it stores them for `recipient`, or the resumed role when `recipient` is None. Without either, it **keeps** any unread message.
- **Legacy pause:** a session paused before #53 has no `suspended_at` key. It keeps the old behaviour (the message is cleared), so its old pause reason, which was stored in `architect_message`, is never re-shown.
- It always calls `_clear_suspension()`.
Filesystem: none (mutates session dict)
<- `submit.handle_unblock()`
! Stage-role validation comes from the session's mode table (`stages_for(session)`): the target must be an active stage of THIS mode, owned by `role_by_stage` (planning: `plan_drafting` / `plan_revision` → draftor, `plan_review` → reviewer; coding: `implementation_drafting` / `implementation_revision` → draftor, `implementation_review` → reviewer). A cross-mode target or a mismatched role raises ValueError.

### advance_extended(session, rounds, turn_timeout, message=None)
File: `src/gator_command/scripts/loop/state_machine.py`
`max_rounds_exceeded` -> the mode table's `extension_resume_stage` (`plan_revision` for planning, `implementation_revision` for coding #41; next_role from `role_by_stage`, the Draftor) with `max_rounds += rounds`. Preserves `round`, `current`, `turns`, `decisions`, `unresolved_findings`. Resets `plan_status="revision"`, `blocked=False`, `architect_action_required=False`, the suspension fields (`_clear_suspension`), and `architect_response_artifact`; sets `architect_message=message` for the Draftor (`_set_architect_message`, #53) and starts a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode, #47: no deadline) or a fresh deadline (legacy). Returns `(previous_max_rounds, new_max_rounds)`.
Filesystem: none (mutates session dict)
<- `submit.handle_extend()` (#39)
! All guards run before any mutation: source stage must be exactly `EXTENDABLE_STAGE`; `rounds` a positive int (bool rejected); `round <= max_rounds`. For checkpoint loops (#55) that guard is instead the active item's `findings_rounds <= max_rounds`, because `status.round` is informational there and may exceed `max_rounds`. Violations raise ValueError. Input range policy (1..20) belongs to the caller.

### advance_turn_timed_out(session, timed_out_role)
File: `src/gator_command/scripts/loop/state_machine.py`
Any active -> `turn_timed_out` (terminal).
Filesystem: none (mutates session dict)
<- `host._try_enforce_timeout()`

### advance_implementation_submitted(session, turn_timeout)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only (#41): `implementation_drafting` / `implementation_revision` -> `implementation_review` (Reviewer) with a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode, #47: no deadline) or a fresh deadline (legacy). It clears `architect_message` and the response artifact. A non-coding loop or another stage raises ValueError. The caller records the candidate generation.
Filesystem: none (mutates session dict)
<- `submit.handle_submit_implementation()`

### advance_implementation_reviewed(session, approved, turn_timeout, approval=None)
File: `src/gator_command/scripts/loop/state_machine.py`
Coding only (#41), from `implementation_review`:
- **Approved:** goes to `implementation_approved` (terminal; resumable only via reopen) and stores `coding.approval = {tree, head, round, generation, ts}`, which is required.
- **Findings:** `round += 1`. At the ceiling the loop goes to `max_rounds_exceeded` (extendable, #39); otherwise to `implementation_revision` (Draftor).
- **Checkpoint loops (#55):**
  - **Approval of a non-final checkpoint** sets the active item's `accepted = {tree, head, generation, ts}` and `state = "approved"`, activates the next item with `base_tree = accepted.tree`, does `current += 1`, and returns to `implementation_drafting` (Draftor, fresh turn). **`coding.approval` is not touched.**
  - **The final checkpoint's approval** records `accepted` and then takes the ordinary approved path.
  - **Findings** also do `findings_rounds += 1` on the active item, and the ceiling is `findings_rounds >= max_rounds`, the per-checkpoint budget.

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
Coding only (#41): `implementation_approved` -> `implementation_revision` (Draftor) with a fresh active turn via `_begin_turn()`: a fresh `turn_started_at` (attention-mode, #47: no deadline) or a fresh deadline (legacy). It keeps `round`, marks `coding.approval.invalidated_at`, and sets `architect_message`. The next submission is named by its generation, so it never overwrites the approved round's artifacts. The old docstring's "round + 1" claim was never true and is corrected (#55). In checkpoint loops the final item, which is always the active one at approval, is set back to `active` with `accepted.invalidated_at`; earlier checkpoints are never reopened. A non-coding loop or any other stage raises ValueError before mutation.
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
Resolves token, validates file, acquires lock, validates action, writes the artifact to `plan.round-N.md` then `plan.current.md`, appends turn, updates `current.draft` with turn reference dict, advances to `plan_review`, emits event.
Filesystem: source file (R, once), `.gator/loops/<loop-id>/plan.round-N.md` and `plan.current.md` (W)
<- `cli._cmd_submit_draft()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `_plan_contract_flags()`, `_check_plan_draft()`, `append_turn()`, `advance_draft_submitted()`
! `current.draft` stores `{turn_id, summary, artifact_path}`, not a bare string.
! **Context evidence (#46).** The source file is read **once** into a captured byte buffer before the lock.
  - **Flagged sessions** (`contract.context_evidence` is an int ≥ 1, never a bool): a preflight check on the captured bytes gives an early error. A preflight session-read failure is ignored, never misreported. The **in-lock check is authoritative**: decode as UTF-8, run `context_checked_problems`, then write **those exact bytes** with `_write_artifact_bytes`. There is no second read and no path copy, so a file swapped after capture is never persisted. Rejection raises `ValueError("Plan draft rejected: …")` before any write or state change, which is atomic. This covers first drafts and revisions.
  - **Unflagged (legacy) sessions** keep `_copy_artifact` byte-for-byte, unchanged.
  - **#55:** `_plan_contract_flags(session)` returns `(context_evidence, coding_checkpoints)`; either flag (int ≥ 1, never bool) routes through the same capture-once path. `_check_plan_draft` runs every flagged check on the same decoded text and raises one `Plan draft rejected: ...` error listing all problems; checkpoint problems are prefixed `Coding Checkpoints: ` and a missing section quotes `ONE_CHECKPOINT_EXAMPLE`. Legacy sessions are never checkpoint-checked at draft time (their plans are re-checked when a coding loop starts, M2).
  - Coding loops never call this (implementation submissions have their own headings).

### context_checked_problems(text)
File: `src/gator_command/scripts/loop/submit.py`
Structural check of a plan's `## Context Checked` (#46). It returns a list of reasons (`[]` = ok).
- Exactly one level-2 heading, case-insensitive, found by the fence-aware `_h2_titles` scan. Fenced examples never count, and `###` is not the section.
- The body (to the next unfenced `##`) must be non-empty once HTML comments and blank lines are removed.
- The body must not be only a placeholder: after reducing to `[a-z0-9]`, `none` / `na` / `nothing` / `tbd` / `todo` / empty (e.g. `-`) are rejected.
- `None — <reason>` (any separator plus a reason) is accepted.
- Adequacy is the Reviewer's judgment, never checked here.
! The shipped plan template in `loop-artifact-formats.md` must contain exactly one section that passes this check (drift-guarded in `tests/test_loop_context_evidence.py`).

### parse_coding_checkpoints(text) / coding_checkpoints_problems(text, required)
File: `src/gator_command/scripts/loop/submit.py`
Closed grammar for a plan's `## Coding Checkpoints` (#55). `parse_coding_checkpoints` returns `(present, items, problems)`; items are `{id, title, scope, verify}` with positional ids `cp1..cpN`.
- Exactly one level-2 heading (fence-aware `_h2_titles`); the body runs to the next unfenced `##`. HTML comments, blank lines and fenced blocks in the body are ignored.
- Items: `N. **Title** — scope. Verify: verification.` at column 0, numbered 1..N with no gaps; `—`, `-` or `:` after the title; continuation lines indented two spaces. Any other text is a problem.
- 1–`CHECKPOINT_MAX_ITEMS` (12) items. Titles are 1–80 chars of plain text (no backticks/markup) and never path-shaped (`[/\\]` or a trailing `.ext`). Scope and verification are whitespace-collapsed, non-placeholder, and capped at `CHECKPOINT_TEXT_MAX` (400) chars.
- `coding_checkpoints_problems(text, required)`: an absent section is a problem only when `required`.
- Whether checkpoints are responsibility-based is the Reviewer's judgment, never checked here.
! The shipped plan template's checkpoint section must parse valid (drift-guarded in `tests/test_loop_checkpoints.py`).

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
**#53 recipient:** a decision response (message and artifact) is addressed to the escalating role (`request.role`), which may not be the resumed turn owner. Another unblock message is addressed to the resumed role. Without a message or file, an unread Architect message is kept. The response artifact name is computed before `advance_unblocked()`, and the file is copied after it.
Response contract: a whitespace-only message is treated as absent. When a pending decision exists (escalation), one of message / file / `no_response=True` is required, else `ValueError` before any mutation. `no_response` is mutually exclusive with message/file and rejected when nothing is pending. `response.kind` ∈ `message`, `artifact`, `message_and_artifact`, `deliberate_empty`. Model-facing `architect_message` is the message, or `ARTIFACT_ONLY_RESPONSE_SUMMARY` for file-only, or `DELIBERATE_EMPTY_RESPONSE_SUMMARY` for the explicit empty choice — never silently blank for a resolved decision. An ordinary pause (no pending decision) still unblocks with no response.
**#47:** for `attention_mode` sessions, a non-None `turn_timeout` raises `ValueError(ATTENTION_TIMEOUT_REFUSAL)` inside the lock before any mutation, because no participant window exists to change. Legacy turn window: optional `turn_timeout` is validated via `validate_turn_timeout()` before the lock; inside the lock it is written to `status.turn_timeout_seconds` BEFORE `advance_unblocked()` computes the fresh deadline, so both this turn and all later transitions use it. Omitted keeps the stored window. The `loop_unblocked` event carries `turn_timeout_seconds` always, plus `previous_turn_timeout_seconds` and a detail suffix when changed, and `response_kind` alongside `decision_id` when a decision was resolved.
Filesystem: `.gator/loops/<loop-id>/decision-response.decision-*.md` (W, when file_path provided), session mutation
<- `cli._cmd_unblock()`, dashboard `_handle_loop_unblock()`
-> `resolve_token()`, `validate_turn_timeout()`, `with_session_lock()`, `validate_unblock()`, `advance_unblocked()`, `append_turn()`, `_copy_artifact()` (when file_path provided)
! All validation that can fail runs before `advance_unblocked()`/`_copy_artifact()`; a raise inside the lock skips the save, so a rejected unblock leaves session.json, events, and the stored timeout untouched.

### handle_submit_implementation(token, file_path, loop_dir=None, checkpoint=None)
File: `src/gator_command/scripts/loop/submit.py`
Coding Draftor submission (#41). Returns `(loop_id, role, loop_dir, generation)`.

**Before the lock:** the file must exist, be UTF-8 and non-empty, and contain the required level-2 headings (`IMPLEMENTATION_HEADINGS`: Executive Summary, Implementation Summary, Charter Updates, Verification, Commit State). Missing headings are listed in the ValueError. **Exactly one** level-2 `Commit State` heading may exist outside fences (`commit_state_heading_count`). A duplicate is rejected, so no author-controlled competing state block can sit next to the CLI-captured one; a Commit State example inside a code fence is allowed.

**Under the session lock:**
1. `validate_action(..., "submit_implementation")`.
2. **Checkpoint binding (#55).**
   - A manifest loop requires `checkpoint == active.id`; the error names the active checkpoint. The only exception is an implicit manifest, which may omit the flag.
   - A session without a manifest rejects `checkpoint` outright.
3. `gitsnap.snapshot(repo_root, coding.base_head)`, which must be `ok` (otherwise ValueError naming the error code).
4. Something must be staged (otherwise "Nothing is staged…"):
   - pre-#55 and implicit loops require `staged_tree != base_tree`;
   - declared loops require `staged_tree != active.base_tree`.
   For declared loops, `gitsnap.diff_trees(active.base_tree, staged)` gives the checkpoint diff. For k > 1, the paths that `diff_trees(coding.base_tree, active.base_tree)` also touched are marked as revisited (information, not a prohibition).
5. **Generation `g = len(coding.generations)`** names the artifacts. The Commit State section is replaced by `render_commit_state(snap, checkpoint=…)` (`replace_commit_state`) and written as `implementation.round-<g>.md` plus `implementation.current.md` (read-only, LF).
6. Bookkeeping:
   - mark the Draftor joined;
   - append an `implementation` turn and set `current.implementation`;
   - append the generation `{round, generation, submitted_at, artifact_path, snapshot[, checkpoint: {id, index, base_tree, changed_count, revisited_count}]}`, where the snapshot is RAW and persisted unchanged.
7. `advance_implementation_submitted()`.
8. Emit `implementation_submitted` with `staged_tree`, `current_head`, `changed_count`, `unstaged_count` (raw), `residue_other_count`, `residue_loop_count` and `generation`. Declared loops add `checkpoint_id`, `checkpoint_index`, `checkpoint_count` and `checkpoint_base_tree`.

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
- **`render_commit_state(snap, checkpoint=None)` (#55):** with a declared checkpoint view, `_render_checkpoint_commit_state` adds:
  - Checkpoint, checkpoint base tree and Generation rows;
  - the review command `git diff <checkpoint base> <staged>`;
  - the checkpoint path list with `[revisits an earlier checkpoint]` markers;
  - the loop-base facts and the cumulative diff command as context.
  Titles go through `_cell` (pipe-escaped). Without a checkpoint view the output is **byte-identical** to the pre-#55 rendering.
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
- **Records:** the review is stored on the generation (`generation.review`, with `generation` and, for declared loops, `checkpoint: {id, index, count, title, base_tree}`). The approval is stored as `{tree, head, round, generation, ts}` via `advance_implementation_reviewed()`.
- **Naming (#55, all coding loops):** the review writes `findings.round-<g>.md`, where `g = len(generations) - 1` is the generation it reviews (always the latest), never `status.round`.
- **Reviewed Candidate (declared loops only):** gains Checkpoint, checkpoint base tree and Generation rows. Legacy output is unchanged.
- **Events** carry `generation`. Declared loops add `checkpoint_id`, and `findings_round` on findings:
  - `implementation_approved` (terminal);
  - `checkpoint_approved` (#55, **non-terminal**: non-final approval, with `accepted_tree` and `next_checkpoint_id`);
  - `max_rounds_exceeded`;
  - `revision_requested` (notes a changed candidate).
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
Architect command. Pauses a running loop from any active state. Saves resume state. Distinct from model escalation (`paused_by_architect` vs `blocked_on_architect`). #53: the message is stored as `status.pause_reason`, never as `architect_message`.
Filesystem: none (session mutation only)
<- `cli._cmd_pause()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_paused_by_architect()`, `append_turn()`

### handle_interject(token, message)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Injects guidance without pausing. It stores the message in `architect_message`, addressed to the current turn owner (#53), with no state change and no deadline change. The recipient's next submission clears it.
Filesystem: none (session mutation only)
<- `cli._cmd_interject()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_interjected()`, `append_turn()`

### handle_end(token, reason)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Terminates the loop prematurely from any non-terminal state and sets the `ended_by_architect` terminal state.
- **#53, pending request:** a request still pending at end is resolved as `response = {message: reason, artifact_path: null, kind: CANCELLED_BY_END ("cancelled_by_end"), ts}`, and the event gains additive `decision_id`.
- **#53, suspended loop:** ending a suspended loop clears its suspension fields.
Filesystem: none (session mutation only)
<- `cli._cmd_end()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_ended_by_architect()`, `append_turn()`

---

### init_loop(feature, sketch_path, max_rounds, turn_timeout, repo_root=None, mode="planning", from_loop=None, brief_path=None, brief_text=None, source_brief=None)
File: `src/gator_command/scripts/loop/host.py`
**Brief (#43):** at most one of `brief_path` (CLI) or `brief_text` (Dashboard) is accepted, and it is validated before any directory is created (`_resolve_brief_input`). `_write_brief` writes the bytes, makes the file read-only (POSIX; on Windows the digest is the enforcement), re-verifies, and returns the metadata. The `loop_started` event records `brief_sha256` / `brief_bytes`, never content. **Planning starts are now atomic as well:** any failure after the directory exists removes it (`_remove_partial_loop`). `source_brief` is rejected on planning starts. `mode="coding"` (#41) delegates to `_init_coding_loop()`; then `sketch_path` must be None and `from_loop` is required. Planning requires `sketch_path` and rejects `from_loop`. Planning: creates loop on disk without entering the watch loop. Creates directory, copies sketch, generates three tokens (draftor, reviewer, architect), writes session + initial event. Returns `(loop_id, loop_dir)`. When `repo_root` is provided, uses it directly instead of calling `find_gator_root()` — enables dashboard reuse without filesystem discovery.
Filesystem: `.gator/loops/<loop-id>/` (W, creates), sketch file (R)
<- `start_loop()`, dashboard `_handle_loop_start()`
-> `create_session()`, `save_session()`, `make_token()`, `save_tokens()`, `emit_event()`, `ensure_loops_gitignore()`

### _init_architect_plan_loop(feature, plan_path, sketch_path, max_rounds, turn_timeout, repo_root, brief_bytes=None) / _write_fixed_artifact(loop_dir, name, data) / _write_checked_bytes(loop_dir, name, data, sha) (#51)
File: `src/gator_command/scripts/loop/host.py`
`init_loop(..., plan_path=…)` and `start_loop(..., plan_path=…)` route here. `plan_path` with `mode="coding"` is refused before anything is written. The sketch is optional. Atomic order:
1. `read_governed_input` (`MAX_PLAN_BYTES`);
2. `submit._check_plan_draft(bytes, True, True)`: the SAME check as a Draftor draft, on the bytes that are persisted;
3. the optional sketch is checked;
4. the loop dir is created; `architect-plan.md` is written by `_write_fixed_artifact` (read-only, then `verify_fixed_artifact` must return ok); `plan.round-0.md` and `plan.current.md` are written by `_write_checked_bytes` (re-read and SHA-compared); then the optional `sketch.md` and brief;
5. tokens; then `create_session(plan_source=…)`, one Architect turn `{type: "initial_plan", artifact_path: "plan.round-0.md"}`, `current.draft`, `enter_architect_plan_review`, save;
6. events `loop_started` (with `plan_source_kind`, `plan_sha256`, `plan_bytes`) then `architect_plan_submitted` `{role: architect, round: 0, artifact_path: "plan.round-0.md"}`.

Any failure removes the directory. No Draftor turn is fabricated, and the Draftor stays unjoined. The start banner adds a `Plan source:` line.

### _init_revision_loop(feature, sketch_path, revise_from, max_rounds, turn_timeout, repo_root, brief_bytes=None) / _read_revision_source(source_dir, revise_from) / _read_source_file(source_dir, name, what) / _require_source_dir(source_dir, loop_id) (#51)
File: `src/gator_command/scripts/loop/host.py`
`init_loop(..., revise_from=…)` and `start_loop(..., revise_from=…)` route here. `--plan-file` together with `--revise-from`, `revise_from` with coding mode, and `revise_from` without a sketch are all refused before anything is written. Atomic order:
1. the canonical source id shape (`_SOURCE_LOOP_ID_RE`, no `..`), and the source dir and session must be present. `_require_source_dir` first refuses a source dir that is a symlink **or a reparse point** (a Windows junction is not a symlink), with "Source loop must not be a symlink or reparse point: <id>". It runs before `session.json` or any artifact is opened, and the error never names the redirected target;
2. the revision sketch through `read_governed_input` (`MAX_PLAN_BYTES`);
3. `_read_revision_source` under the source's `with_session_lock` (a **read-only** callback):
   - `loop_id` equals the requested id, the mode is planning and the stage is `plan_approved`;
   - **approval:** the LAST turn is the Reviewer's `plan_review` turn with summary `"Plan approved"` and a `findings.round-N.md` artifact that is byte-equal to `findings.current.md`;
   - **plan:** `plan.current.md` is byte-equal to the artifact of the latest `plan_draft` (Draftor) or `initial_plan` (Architect) turn;
   - each file must be regular, non-link, non-empty and at most `MAX_BASELINE_BYTES` (`_read_source_file`);
4. the dir is created: `sketch.md` (the exact sketch bytes, SHA-checked), then `revision-baseline-plan.md` and `revision-baseline-approval.md` via `_write_fixed_artifact`, then the optional brief;
5. tokens; then `create_session(revision=…)` at ordinary `plan_drafting`; `loop_started` with `revision_source_loop_id`, `baseline_sha256`, `approval_sha256` and `approval_source_artifact`.

The source brief is not carried forward. The source loop is never written, and the copies stay authoritative if it is later changed or removed.

### _init_coding_loop(feature, from_loop, max_rounds, turn_timeout, repo_root, brief_bytes=None, source_brief="keep") / _read_approved_source(source_dir, from_loop, source_brief="keep") / _remove_partial_loop(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
The guarded coding successor (#41). Steps, in order:
1. Validate the canonical shape of `from_loop`: `_SOURCE_LOOP_ID_RE` starts AND ends alphanumeric, so a Windows trailing-dot alias is rejected; no `..` / separators. The source must be a real directory with `session.json`: the shared `_require_source_dir` guard refuses a symlinked or reparse-point (junction) source dir before anything in it is opened.
2. Under the source's `with_session_lock` read-only callback, require **`session["loop_id"] == from_loop` exactly**, which rejects Windows trailing-dot and case-variant aliases that resolve to the same directory, so only the canonical id is persisted as `coding.source_loop_id`. Also require `loop_mode == "planning"` (legacy values accepted), stage `plan_approved`, and a non-empty regular `plan.current.md`.
3. **#55 checkpoints (`_plan_checkpoints`).** `_read_approved_source` also returns the source session's `contract.coding_checkpoints` flag, read under the same lock. The approved-plan bytes are parsed once:

   | Source | Section absent | Present, valid | Present, invalid |
   |---|---|---|---|
   | flagged | **refused** (a flagged plan must have been gated) | `declared` | refused with the problems |
   | legacy | `implicit` (`IMPLICIT_CHECKPOINT`) | `declared` | refused with the problems |

   The manifest is frozen into `coding.checkpoints` (cp1 based on the snapshot's `head_tree`) and never re-parsed.
4. Take `gitsnap.snapshot(repo_root)`, which must be ok; this rejects unborn, conflicted, bare and missing-Git cases.
5. Create the loop dir, write `approved-plan.md` (read-only), and re-read it to compare SHA-256 against the source bytes.
6. Only then write tokens, `session.json`, and a `loop_started` event (with `mode`, `source_loop_id`).

Any failure removes the partial directory (`_remove_partial_loop`, read-only tolerant; `onexc` on 3.12+, `onerror` below) and raises one clear error.
**Brief carry-forward (#43 D1; the Architect chooses):** inside the same source-lock read:
- the source has no `brief`: `none_available`, whatever the choice;
- `drop`: `dropped`; the source brief is never opened or verified, so a corrupt one cannot block;
- `keep` (the default): `read_verified_brief(source, ref, BRIEF_FILENAME)` must be `ok`. Otherwise the start is rejected atomically with the integrity state and a `--source-brief drop` hint.

Kept bytes are written as `source-architect-brief.md` (copy-then-verify). `submit.coding_status_view(coding, loop_dir)` projects `source_brief` (strict view), `source_brief_check` and `source_brief_decision` for the Dashboard. An optional new `--brief` is written as the coding loop's own `architect-brief.md`. That gives four arrangements: keep or drop, each with or without a new brief. The decision is recorded in `coding.source_brief_decision` and in the `loop_started` event (plus the source brief sha and size when kept).
Filesystem: source `session.json` / `session.lock` (R, lock), source `plan.current.md` (R), `.gator/loops/<new>/` (W)
! The source session is never written. Callers hold `start.lock` (`start_loop`; the Dashboard start in Module 5); lock order is start.lock, then the source session lock, the same as extend.

### reopen_loop(token, message, loop_dir=None)
File: `src/gator_command/scripts/loop/host.py`
Single-active guard for reopen (#41), mirroring `extend_loop()`: take `start.lock`, refuse if another loop is active (`RuntimeError`), delegate to `submit.handle_reopen()`, and release in `finally`. Does not attach a watcher; the caller applies the host contract.
<- CLI `_cmd_reopen()` (the Dashboard `/reopen` arrives in Module 5)
! Every reopen path must go through this function. Rejections leave the loop byte-unchanged.

### start_loop(feature, sketch_path, max_rounds, turn_timeout, mode="planning", from_loop=None, brief_path=None, source_brief=None)
File: `src/gator_command/scripts/loop/host.py`
CLI entry point for starting a loop. Acquires `start.lock` (cross-process, one active loop per repo), scans for existing active loops, calls `init_loop()`, acquires `host.lock`, releases `start.lock`, enters watch loop. Blocks until terminal.
Filesystem: `.gator/loops/start.lock` (RW), `.gator/loops/<loop-id>/host.lock` (RW)
<- `cli._cmd_start()`
-> `acquire_start_lock()`, `release_start_lock()`, `find_active_loop()`, `init_loop()`, `acquire_host_lock()`, `release_host_lock()`, `watch_loop()`
! `start.lock` held only during the scan-and-init window — released before entering `watch_loop()`. `host.lock` transferred to `watch_loop()`.

### watch_loop(loop_dir, host_lock_fd=None)
File: `src/gator_command/scripts/loop/host.py`
Polls events.jsonl (from offset 0) for new entries, renders log lines, and runs Phase 2 per loop contract: `attention_mode` loops go to `_try_record_attention` (soft and never terminal), and legacy loops get deadline enforcement (`_try_enforce_timeout`). Stays alive through paused states. Exits on a terminal event **only if the session is still terminal** (`_session_is_terminal()`); otherwise the event is rendered as history and watching continues. When `host_lock_fd` is provided, writes diagnostic metadata (PID, loop_id, start time) via `write_host_metadata()`.
Filesystem: `.gator/loops/<loop-id>/events.jsonl` (R), `session.json` (R for the attention/legacy-deadline check + terminal check), `host.lock` (W metadata, when fd provided)
<- `start_loop()`, dashboard `_run_watcher()`
-> `load_session()`, `format_event()`, `format_next_prompt()`, `_try_enforce_timeout()`, `write_host_metadata()`, `_session_is_terminal()`, `_open_liveness_store()` / `_project_liveness()` (-> `liveness.project_for_host()`)
! The host is a READER of loop state during normal operation. Legacy timeout enforcement is the one loop-state write exception. Attention recording (#47) writes only an awareness event and its idempotency marker, never loop state (stage, role, round, turn).
! Liveness projection (#36) runs after each event batch and just before a terminal return; a `retry`/`error` result is retried on the next tick even without new events. It writes only the private liveness sidecar, never raises, and is skipped when the store is unavailable.
! Terminal detection is session-authoritative (#39): a watcher attached after an extension replays the old `max_rounds_exceeded` event and must keep hosting; a watcher that reads the terminal event after an extension already landed also keeps hosting. `_session_is_terminal()` fails safe (unreadable session -> terminal -> exit), preserving the pre-#39 behavior.
! `tail_events()` (`gator loop tail`) is intentionally NOT session-authoritative: a human tail started before an extension ends at the old terminal event.

### acquire_host_lock(loop_dir) / release_host_lock(fd) / _try_host_lock(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Non-blocking exclusive file lock on `host.lock` — proves process ownership of a loop's watcher (attention recording for attention-mode loops, #47; timeout enforcement for legacy loops). `probe_host_state()` reads it authoritatively for the Dashboard. Platform-aware: `msvcrt.locking(LK_NBLCK)` on Windows, `fcntl.flock(LOCK_EX|LOCK_NB)` on POSIX. `_try_host_lock()` is the single attempt that distinguishes `"held"` from `"open failed: ..."`; `acquire_host_lock()` wraps it with the unchanged fd-or-None contract.
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

### _try_record_attention(loop_dir, now=None) / _attention_due(session, now) / _find_attention_event(loop_dir, key) / _ensure_events_newline(path) (#47)
File: `src/gator_command/scripts/loop/host.py`
Records exactly one durable `architect_attention_due` event per active turn of a flagged loop. It never changes stage, role, round or turn, so time never changes loop state.
- **`_attention_due`** is pure and never raises: flagged, active, not paused, a valid **offset-aware** `turn_started_at` and a positive int interval (`turn_timeout_seconds`), with `now ≥ start + interval`. A naive or unparsable timestamp, or an overflowing comparison, means not due (M2-1).
- **`_try_record_attention`** runs inside `with_session_lock`, **event-first, marker-second, with recovery**:
  1. preconditions;
  2. fast path: `attention_notified_turn == turn_started_at` means no write;
  3. recovery: `_find_attention_event` (via the shared `read_all_events`, which skips torn lines) finds a valid event with this `attention_key`, so only the marker is repaired;
  4. otherwise `_ensure_events_newline` terminates any partial last line, `emit_event` appends `{event, attention_key, role, round, stage, interval_seconds, turn_started_at, detail}` (plus `ts` / `loop_id`), and the callback returns `(session, None)`, so the marker is saved AFTER the append.
- **Not atomic, but convergent:** an emit failure means a retry; a save failure after the append means a repair with no duplicate; a torn line is isolated. Racing observers serialize on the session lock.
- **Return value:** True only when it appended.
- **Payload:** no artifact, brief or token content.
Filesystem: `session.json` (RW via lock), `events.jsonl` (R scan, W append via lock)
<- `watch_loop()` Phase 2 (flagged branch; an unlocked pre-check skips the lock when already notified or not due; exceptions are swallowed and the next poll converges)
-> `with_session_lock()`, `read_all_events()`, `emit_event()`
! The pinned tests are in `tests/test_loop_attention.py` (`TestAttentionFaultInjection` a–f, racing observers, the real `watch_loop` thread).

### attention_status_view(session, loop_dir, now=None) (#47 M4)
File: `src/gator_command/scripts/loop/host.py`
The Architect-only Dashboard projection. It returns `None` for legacy sessions, otherwise `{interval_seconds, turn_started_at, notified_turn, notified, due}` built from validated primitives. `notified` is the marker, or a matching event found by `_find_attention_event`; the scan runs only when the marker is missing and the turn is due.
<- dashboard `_handle_loop_status()`
`host` (M5 P2): only in the due-and-not-notified state, `probe(loop_dir)` (default `probe_host_state`) gives `attached` / `none` / `unknown`. A probe exception or bogus value means `unknown`; otherwise `host` is null.

### probe_host_state(loop_dir) (#47 M5 P2)
File: `src/gator_command/scripts/loop/host.py`
Authoritative and non-blocking: one `_try_host_lock` attempt. `held` means `attached`; acquired means `none`, released immediately; open failed means `unknown`. A second handle conflicts with a held lock even in the same process, so the Dashboard's own watcher reads as attached.
! Call only rarely (attention due and not recorded). Holding the probe even briefly could collide with a single-attempt acquirer (start, adoption), which never targets a long-running due turn.

### _try_enforce_timeout(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Acquires session lock, re-reads session, fires timeout only if deadline still expired and state still active. Race-safe: if a submit advanced the state, timeout is silently skipped. **Legacy only (#47):** returns without writing for `attention_mode` sessions, even with a forced deadline (defense in depth).
Filesystem: `session.json` (RW via lock), `events.jsonl` (W via lock)
<- `watch_loop()`
-> `with_session_lock()`, `advance_turn_timed_out()`
! One of the two Host Contract write exceptions, legacy loops only. The other is `_try_record_attention` for attention-mode loops (#47), which writes no loop state. Lock-then-re-read discipline prevents the timeout-vs-submit race.

---

### main(argv)
File: `src/gator_command/scripts/loop/cli.py`
Argparse dispatcher for 16 subcommands: start, status, submit-draft, submit-implementation, submit-review, escalate, pause, interject, end, unblock, extend, reopen, wait, participant, tail, list.
Filesystem: none (delegates to handlers)
<- `gator-loop.py`

### _cmd_status(args)
File: `src/gator_command/scripts/loop/cli.py`
Read-only status display. Role-aware: model view (exit codes 0/1/2, shows `architect_message` and `architect_response_artifact` when set) vs architect supervisor view (exit codes 0/2, shows active role + join states + available commands + pending decisions).

**#53 participant exit contract.**
- **Exit codes:** model `status` exits `2` **only when terminal**. A paused or blocked loop exits `1` (nobody's turn: keep waiting).
- **Text:** `_print_suspension` prints either "Architect hold -- the Architect paused the loop" plus `Reason:`, or "Awaiting Architect decision decision-N (requested by <role>)". It then prints `Resumes with: <role> (<stage>)`, "This is not the end of the loop. You are still a loop participant." and the bounded `wait` command.
- **JSON:** model and Architect JSON gain additive `suspension` (`_suspension_view`): `{kind: architect_hold|architect_decision, resume_stage, resume_role, since, reason (hold only), decision_id / requested_by (decision only)}`, or null when not suspended.
- **Architect view:** the paused text adds `Preserved:`, `Since:` and `Hold reason:`. Architect exit codes are unchanged. Both text and JSON output include `architect_response_artifact` (absolute loop path or null).
Filesystem: `session.json` (R), `.tokens.json` (R via resolve_token)
<- `main()`
-> `resolve_token()`, `load_session()`
! **#53 recipient-scoped message (`_message_for_role` / `_print_architect_message` / `_message_json`):**
  - **Who sees it:** model status and wait show `architect_message` / `architect_response_artifact` only to their recipient, **whether or not it is that role's turn**. An unscoped legacy message keeps the old rule (turn owner only). JSON keys are unchanged; their value is null for a non-recipient.
  - **Text:** the protocol-documented `Architect message:` line is kept. Continuation lines of a multi-line message are indented four spaces.
  - **Decision label:** a line `Architect response to your escalation: decision-N` comes first only when the stored message carries `architect_message_decision`. It is never inferred from turns or `decisions[-1]`.
! JSON output includes `"schema": "gator-loop-status-v1"`. Architect JSON includes `turns`, join states, `decisions`, and `pending_decisions` (entries where `response` is null). Architect text status shows pending decision ID, reason, and artifact path when blocked. Architect never gets exit code 1 (always authorized to act on active loops).
! **#47 participant time silence:** for `attention_mode` loops the model status JSON and wait JSON omit `turn_timeout_seconds` / `turn_deadline` (`_strip_participant_time`), and `_print_turn_window(session)` prints nothing, so participants see no interval, deadline or countdown.
! **#47 Architect view:**
  - JSON gains additive `attention: {interval_seconds, turn_started_at, elapsed_seconds, notified_turn, notified, due}` (`_attention_view`).
  - The active text view prints `Attention interval: N min (Architect notice only)`, `Elapsed this turn`, and either "Attention: due (notice recorded)…no action is required" or "interval passed; no notice recorded yet (is a loop host running?)".
  - The paused view shows the attention interval and omits every `--timeout` hint.
  - Unblock, extend and reopen output use `_print_window_line`.
  - The host-attach wording comes from `_host_duty(loop_dir)`: "records attention notices" for flagged loops, legacy wording unchanged.
  - `start --attention-interval` (preferred) and `--turn-timeout` share `dest=turn_timeout` (default 300). The host banner prints "Attention interval: … (Architect notice only)".
! **#55 counters (`_print_counters`, `_checkpoints_json`).**
  - **Text:** for a declared checkpoint loop, status (model and Architect) and wait print `Checkpoint: K of N -- <title> (findings round r of b)` and `Generation: g` (or `none yet`) **instead of** `Round: X/Y`. Implicit and pre-#55 loops keep `Round: X/Y`.
  - **JSON:** gains additive `checkpoint`, `checkpoints` (`id/index/title/state`, never scope or verify) and `generation`. `round` and `max_rounds` stay for compatibility and are informational.
  - **`list`:** the text Round column shows `cp K/N findings r/b`; JSON items gain `checkpoint_summary`.
  - **Terminal reason:** a checkpoint loop at `max_rounds_exceeded` shows "Findings budget exceeded for checkpoint cpK (r of b)".
! Legacy turn window: model and architect JSON (and wait JSON) carry additive `turn_timeout_seconds` + `turn_deadline`; the acting model's text view prints `Turn window: Ns (deadline ...)` via `_print_turn_window()`. The paused architect view prints the current window and, when a decision is pending, states that a response is required (with the exceptional `--no-response` form); an ordinary pause shows the optional-message form.

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
`gator loop submit-implementation --token <draftor> [--checkpoint <id>] --file <implementation.md>` (#41; `--checkpoint` #55, passed to the handler).
- For a declared checkpoint loop, success prints "Checkpoint cpK submitted (generation g)", the checkpoint changed-path count (plus the revisited count) and the cumulative count. Otherwise:
- On success it prints the round, the full candidate staged-tree OID, the changed-path count, a WARNING line only for residue outside `.gator/loops/`, a loop-residue count line, and the artifact path.
- `PermissionError` prints `Rejected:` and exits 1; `ValueError` / `FileNotFoundError` print `Error:` and exit 1.
- The Reviewer's coding status prints the latest generation's candidate tree and `git diff <base_tree> <staged_tree>`.
- **Declared checkpoint loops (`_print_checkpoint_action_prompt`, #55):**
  - The **Draftor** sees "Implement checkpoint K of N -- title", the Scope, Verify and checkpoint base tree, the "stage only this checkpoint" rule, and the submit command with `--checkpoint <id>`.
  - The **Reviewer** sees "Review real code changed for checkpoint K of N -- title (generation g)", `git diff <checkpoint base> <staged>`, and either "does NOT authorize a commit" (non-final) or the final-checkpoint commit note.
  - **`submit-review`** prints "Checkpoint cpK approved; the Draftor continues with cpK+1. No commit yet." on a non-final approval, and the checkpoint findings round on findings.
  - CLI error and guidance text stays ASCII (`--`), because Windows pipes are cp1252.

### _cmd_reopen(args) / _attach_foreground_watcher(loop_host, loop_dir, what)
File: `src/gator_command/scripts/loop/cli.py`
`gator loop reopen --token <architect> --message "..."` (#41) calls `host.reopen_loop()`; on success it prints the resumed stage, the approval invalidation, the window line (`_print_window_line`: "Attention interval: … (Architect notice only)" for attention-mode loops, #47; "Turn window: Ns" for legacy) and the re-engagement notice. `_attach_foreground_watcher` is the host contract shared with `extend`:
- `attached`: foreground `watch_loop()`;
- `already_hosted`: exit 0;
- `failed`: exit 1. Stderr says the <reopen|extension> is saved, but "attention notices are NOT being recorded" (attention-mode, #47) or "turn timeouts are NOT being enforced" (legacy). The wording comes from `_host_duty(loop_dir)`, as do the already-hosted and Ctrl+C messages.

### _cmd_start(args) / _mode_of(session) / _print_coding_action_prompt(...)
File: `src/gator_command/scripts/loop/cli.py`
- **#51 `start --plan-file PATH`** (`dest=plan_path`): planning only; `--sketch` becomes optional with it.
- **#51 `start --revise-from LOOP_ID`** (`dest=revise_from`): planning only; requires `--sketch` and cannot be combined with `--plan-file`.
  - `_revision_view` / `_print_revision` (status): `Revision of: <id>`, then `Baseline plan:` and `Baseline approval review:` paths with integrity markers. JSON gains `revision: {source_loop_id, baseline: {path, check}, approval: {path, check}}`.
  - The Draftor's first turn says "Draft a full replacement plan…" and lists the baseline, approval and revision sketch paths; earlier source rounds are optional.
- **`_plan_source_view` / `_print_plan_source` / `_plan_source_json`:**
  - **Status (model and Architect):** `Plan source: Architect-originated draft plan -- <architect-plan.md> [OK]` (or an `[!!]` marker), then either `Current plan: Architect-originated draft -- awaiting Reviewer approval (not approved)` while no Draftor `plan_draft` turn exists, or `Plan approved by the Reviewer (originated by the Architect)`.
  - **JSON:** planning loops gain additive `planning_source`; Architect loops gain `plan_source: {path, check, architect_draft_current, approved}`. An invalid block shows `[!!] INVALID PROVENANCE`.
- **`_print_action_prompt`:**
  - the Reviewer is told to "Review the Architect-originated draft plan (unapproved)";
  - the Draftor in `plan_revision` also gets the `Plan:` path and "Submit a full replacement plan";
  - with no `sketch.md`, a "No sketch: … escalate" line.
  - Ordinary loops print exactly as before.
- `start --mode planning|coding [--from-loop ID] [--sketch PATH] [--brief FILE] [--source-brief keep|drop]`: planning requires `--sketch`; coding requires `--from-loop`. `--brief` (#43) is optional in both modes. `--source-brief` is coding-only (exit 1 on planning) and defaults to keep. Argument errors and `RuntimeError` exit 1 with `Error:`.
- Status JSON gains additive `mode` (normalized). Coding text status prints `Mode: coding` and a coding action prompt (approved plan path, `submit-implementation`, review the STAGED tree).
- **Architect brief lines (#43):** `_brief_entries` / `_print_briefs` / `_briefs_json` cover the model and Architect views.
  - Each non-absent position prints a labeled FIXED path plus a marker: `[OK] (required reading)`, `[!!] MISSING`, `[!!] DIGEST MISMATCH`, `[!!] UNREADABLE`, `[!!] INVALID REFERENCE` or `[!!] UNSAFE PATH`. A failed brief adds "do not rely on it", and model roles are also told to escalate.
  - A dropped planning brief prints "Planning brief: not carried forward (Architect's choice at coding start)".
  - `absent` prints nothing, so no-brief loops keep their exact text output.
  - JSON gains `brief` / `source_brief` (`{path, check}`) and `source_brief_decision` only when present.
- Terminal text for `implementation_approved` gives the one-normal-commit handoff.

### _cmd_extend(args) / _round_count_arg(value)
File: `src/gator_command/scripts/loop/cli.py`
Architect `gator loop extend --token --rounds <1-20> --message "..."` (#39). `--rounds` and `--message` are required; `--rounds` uses argparse type `_round_count_arg` -> `session.validate_round_count()` (usage error exit 2 before any write). Calls `host.extend_loop()`; `PermissionError` -> `Rejected:` exit 1, `RuntimeError`/`ValueError`/`FileNotFoundError` -> `Error:` exit 1 (no host step). On success prints old -> new ceiling, resumed stage/role, the window line (attention interval for attention-mode loops, #47; turn window for legacy), and a participant re-engagement notice, then applies the host contract via `host.acquire_host_lock_with_retry()`: `attached` -> foreground `watch_loop()` (Ctrl+C prints that attention recording or, for legacy, timeout enforcement stopped; fd released in `finally`); `already_hosted` -> prints holder detail, exit 0; `failed` -> stderr says the extension is saved but attention notices are not recorded (legacy: timeouts not enforced), exit 1.
<- `main()`
-> `host.extend_loop()`, `host.acquire_host_lock_with_retry()`, `host.watch_loop()`, `host.release_host_lock()`, `session.load_session()`
! Always attaches (no state-only `--no-watch` form): a state-only extension would leave a live-but-unhosted loop with no recovery command, because `extend` rejects once the stage is `plan_revision`.
! Architect status for a `max_rounds_exceeded` loop prints the `extend` command hint; `start`'s banner lists it too.

### _cmd_unblock(args) / _turn_timeout_arg(value)
File: `src/gator_command/scripts/loop/cli.py`
Architect unblock. Forwards `--message`, `--file`, `--timeout` (argparse type `_turn_timeout_arg` → `session.validate_turn_timeout()`, so bad values are usage errors before any write; **legacy loops only**: attention-mode loops refuse it in `handle_unblock`, exit 1 with `Error:`, #47), and `--no-response` to `submit.handle_unblock()`. It prints the resumed stage and the window line (attention interval for attention-mode loops; effective turn window for legacy). `ValueError`/`FileNotFoundError` exit 1 with `Error:`; `PermissionError` exits 1 with `Rejected:`.
<- `main()`
-> `submit.handle_unblock()`, `session.load_session()`

### _cmd_wait(args)
File: `src/gator_command/scripts/loop/cli.py`
Model-role wait. Resolves the token, then calls `_wait_for_actionable()` and renders status-shaped output. Exit codes: `0` actionable, `2` terminal (and invalid token or invalid `--max-seconds`), `3` (`WAIT_EXIT_STILL_WAITING`) bounded deadline passed while another role owns the turn **or the loop is paused/blocked (#53: a suspension never ends a wait)**. Architect token exits 1. JSON gains additive `suspension`; suspended still-waiting text prints the hold/decision and the reissue command.
Filesystem: `session.json` (R), `.tokens.json` (R via resolve_token)
<- `main()`
-> `resolve_token()`, `_wait_for_actionable()`, `_print_action_prompt()`, `_positive_seconds()`
! `--max-seconds` omitted = unbounded (human CLI compatibility). Participant surfaces teach the bounded form `--max-seconds 45`; exit 3 means "reissue the same command", never "leave the loop". Text output prints the exact reissue command; JSON (`gator-loop-status-v1`, additive) adds `wake_reason: "still_waiting"`, `max_seconds`, `waited_seconds`, `reissue_command`. **Legacy loops only:** it also adds `turn_timeout_seconds` / `turn_deadline`, and actionable text output prints the turn window like `status`. Attention-mode loops (#47) omit both fields and print no window (`_strip_participant_time`, `_print_turn_window(session)`). `--max-seconds` is the command's own bounded wait, not a loop deadline.

### _wait_for_actionable(loop_dir, role, poll_interval, load_session, is_terminal, is_paused, max_seconds=None, clock=None, sleep=None)
File: `src/gator_command/scripts/loop/cli.py`
Polls until terminal / this role's turn. Returns `(session, wake_reason)` with wake_reason `terminal`, `already_your_turn`, `became_your_turn`, or `still_waiting` (bounded only). #53: `paused` is no longer a wake reason; a suspended loop keeps the wait going (unbounded waits wait through it). The `is_paused` parameter is kept for call-site compatibility only.
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
Pure helpers. `state_key` is the SHA-256 idempotency key over `round`, `stage`, `next_role`, `len(turns)`, `turn_deadline`, plus `turn_started_at` **only when that key exists** (#47 flagged sessions), so legacy keys hash exactly as before. `attention_notified_turn` is deliberately excluded: recording attention never creates a participant notification. `classify` returns `not_registered` / `connected` / `stale` (active only, > 3 × heartbeat) / `released` / `closed` / `expired` (> 24 h unseen). `prune` applies retention: delete when the loop dir is gone or terminal > 7 days; drop expired registrations; TTL-expire pending `turn-ready` > 24 h; cap 50 notifications per role (pending never dropped — so a role whose records are all pending may exceed 50; pending records still TTL-expire), 10 superseded, 100 audit.

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
The D2a receiver. It registers (heartbeat advertised as `max(15, ceil(poll_seconds))`), polls until a delivery or the deadline, acks every record received in that poll, reports the newest **actionable** one, sets the registration state, and returns `(exit_code, payload)`:
- `0 turn_ready` (released);
- `2 terminal` (closed);
- `3 still_waiting` (released);
- `4 superseded` (no write);
- `1 error` (redacted);
- `130 interrupted` (best-effort release).

**#53:** `architect-block` is not in `_DELIVERY_OUTCOME`. It is acked and the watch continues with the registration still `active` (poll heartbeats it), so a pause or block never releases or ends the watcher. `still_waiting` adds `suspended: true` and the paused `stage` (`_suspension_fields`, one unlocked session read; a failure omits them). `architect_block` remains only as a legacy wake reason in `_render_participant`. A `RegistrationClosedError` mid-watch (closed by the terminal path) returns `2 terminal` with no write. Never loops forever or relaunches itself. `clock`/`sleep` are test seams.

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

### diff_trees(worktree_root, from_tree, to_tree) (#55)
File: `src/gator_command/scripts/loop/gitsnap.py`
`git diff-tree -r -z -M --name-status <from> <to>`. It returns `{"ok": True, changed_paths, changed_truncated}` (the same record shape and `MAX_PATHS` cap as `snapshot`) or `{"ok": False, error, detail}`, and never raises for Git conditions.
Filesystem: Git object database (R only). It takes no index lock and never touches refs, the index or the worktree (pinned).
<- `submit.handle_submit_implementation()` (the checkpoint diff and revisit disclosure)

---

## TRIPWIRE: Architect Brief Is Immutable Residue, Not a Channel (#43)

The Architect brief is written once at loop creation and never edited. (#51: verification goes through `verify_fixed_artifact`'s closed allowlist; the brief wrappers refuse every non-brief name.) Later direction goes through interject, escalate or unblock. Every read of a brief goes through `verify_brief` with the FIXED expected name for its position (`architect-brief.md` / `source-architect-brief.md`), never a path from session data. Status surfaces use only `brief_status_view` (metadata, positionally bound); brief content never appears in session, events, `/status`, or the liveness sidecar. A missing brief is `absent` and neutral, never an alarm.

Violation: trusting `session.brief.artifact` as a path enables traversal or swapped-label reads; passing raw `session.brief` through a generic status allowlist can leak injected content.

## TRIPWIRE: Architect-Originated Plans Are Unapproved Input (#51)

An Architect plan enters a loop ONLY:
- through `read_governed_input` and `_check_plan_draft` on the exact bytes persisted;
- at the existing Reviewer `plan_review` stage;
- recorded as an Architect `initial_plan` turn, never as a Draftor turn.

Writing it never approves it. A coding loop can start only from `plan_approved`, which only the Reviewer reaches. `architect-plan.md` is immutable provenance; `plan.current.md` stays the ordinary mutable current plan.

Violations:
- a privileged or auto-approved Architect plan;
- a direct Architect-plan-to-coding route;
- a fabricated Draftor turn;
- a weaker validator.

## TRIPWIRE: Revision Baselines Are Copies (#51)

A revision loop's authority is its two copied, verified baseline files (`revision-baseline-plan.md`, `revision-baseline-approval.md`), never a live path into the source loop.
- The copies are captured ONLY under the source's session lock in a read-only callback; the source loop is never written, reopened or extended.
- The approving review is identified ONLY from the session's last turn plus the cross-copy equality checks. If they don't hold, the start fails atomically; the evidence is never guessed or quietly omitted.

Violations:
- reading the source loop live after creation;
- writing the source session;
- treating a missing approval as optional.

Pinned by `test_revision_lifecycle` (source byte-immutability, deleted-source integrity) and `test_revision_rejection_is_atomic`.

## TRIPWIRE: Validated Bytes Are Persisted Bytes (#46)

For context-evidence and coding-checkpoint sessions, `handle_submit_draft` persists exactly the buffer it validated inside the session lock. Never re-read the source path or `copy2` it after validation, and never make the preflight authoritative. Only `contract.context_evidence` / `contract.coding_checkpoints` gate enforcement. Never infer it from dates, mode strings, or the presence of a brief: legacy sessions must keep accepting old plans.

Violation: a validate-then-copy-path sequence lets a file swapped between check and write land unvalidated. That is pinned by `TestSwapRace`, which fails under that mutation. Dropping the in-lock check fails `test_in_lock_check_is_authoritative`; for checkpoints, `test_in_lock_gate_is_authoritative` pins the same rule.

## TRIPWIRE: Attention Is Architect Awareness, Never Participant Pressure or State (#47)

For `attention_mode` loops (`contract.attention_interval`, set on every new session), time passing NEVER changes loop state: no stage, role, round or turn change; no pause; no termination; no participant wake-up. The interval (stored in `turn_timeout_seconds`) produces exactly one durable `architect_attention_due` event per turn.
- **The host watcher is the only writer.** `_try_record_attention` writes the event first and the marker second, and recovers if interrupted between them; this is the documented sole exception to "Session Lock Write Ordering".
- **Participants never see time.** Participant status, `wait`, prompts and protocol carry no interval, deadline, countdown or request-more-time flow. Only Architect surfaces (Architect CLI view, Dashboard) show the interval, elapsed time and notice.
- **Host state is never inferred.** The Dashboard's host wording comes only from `probe_host_state`, never from a missing marker.
- **Legacy loops are unchanged.** Unflagged sessions keep their recorded hard-timeout semantics byte-for-byte, and `turn_timed_out` residue is never reinterpreted.

Violation: adding a deadline, a participant-visible window, or a state transition for flagged loops reintroduces the pressure #47 removed. Gating on anything other than `attention_mode` (dates, versions, field presence) breaks legacy loops.

## TRIPWIRE: Source Loop Directories Are Contained (#51 follow-up)

Every path that reads another loop as a source (`_init_coding_loop` for `--from-loop`, and `_init_revision_loop` for `--revise-from`) calls `_require_source_dir` first. It rejects the directory when it is a symlink **or** `_is_reparse_point`, before `session.json` or any artifact is opened. `is_symlink()` alone is not enough on Windows, where a directory junction is a reparse point that `is_symlink()` does not report. The per-file checks in `_read_source_file` cannot catch a redirected directory, because the files behind it are ordinary.

Violation: a junction under `.gator/loops/` redirects source reads outside the governed loops directory. That is pinned by `test_reparse_point_source_dir_is_refused` (both paths, atomic, source session never locked) and `test_symlinked_source_dir_is_refused`.

## TRIPWIRE: Raw Staged Tree Is Review Authority (coding mode, #41)

In coding-mode loops the reviewed and approved candidate is the raw `git write-tree` OID captured by `gitsnap.snapshot()` — never artifact prose and never a filtered or normalized tree. Implementation artifacts describe the candidate; the CLI writes their `## Commit State` facts from the snapshot.

Violation: approving from prose, or from a filtered tree, lets a commit land that differs from what the Reviewer inspected.

## TRIPWIRE: Checkpoint Approval Never Commits (#55)

Only the **final** checkpoint's approval writes `coding.approval`, the one-commit authority read by `resolve_approval`, which is unchanged. A non-final approval records `accepted` on the item and opens the next one. A checkpoint's base comes **only** from the previous item's `accepted.tree`, set in the same locked transition; findings never change it. There is no commit, reset, stash, or index or worktree write per checkpoint.

Violation: writing `coding.approval` on a non-final approval authorizes a partial commit. That is pinned by the transition table (`coding.approval` null, and Git HEAD, index and refs unchanged after `checkpoint_approved`).

## TRIPWIRE: Coding Artifacts Are Named by Generation (#55)

`implementation.round-<g>.md` and `findings.round-<g>.md` use the generation `g`, the index in the append-only `coding.generations`, for **all** coding loops. Never use `status.round`: it does not advance on approval, reopen or checkpoint approval, so it collides and `_write_artifact_text` silently overwrites evidence. Before any reopen, `g` equals `status.round` in legacy loops, so the names are unchanged there.

Violation: the post-reopen resubmission or a later checkpoint overwrites an earlier round's evidence. That is pinned by the transition table's uniqueness and no-overwrite checks, and by `test_legacy_reopen_never_overwrites`.

**D3 transition table (checkpoint loops).** `A` is the active item, `g` the latest generation.

| Transition | Stage → role | Artifacts | `status.round` | `A.findings_rounds` | Manifest | `coding.approval` | Event |
|---|---|---|---|---|---|---|---|
| Submit (`--checkpoint A.id`) | review → Reviewer | `implementation.round-g` | — | — | — | — | `implementation_submitted` |
| Findings | revision → Draftor, or `max_rounds_exceeded` at budget | `findings.round-g` | +1 | +1 | — | — | `revision_requested` / `max_rounds_exceeded` |
| Non-final approve | drafting → Draftor | `findings.round-g` | — | — | `A.accepted`; next active on `A.accepted.tree`; `current += 1` | stays null | `checkpoint_approved` |
| Final approve | `implementation_approved` | `findings.round-g` | — | — | `A.accepted` | set (+`generation`) | `implementation_approved` |
| Extend (guard `A.findings_rounds <= max_rounds`) | revision → Draftor | — | — | — | — | — | `loop_extended` |
| Reopen | revision → Draftor | — (next submit is g+1) | — | kept | last item reactivated, `accepted.invalidated_at` | `invalidated_at` | `loop_reopened` |

Pause, unblock, escalate and end keep `current`, the stage and the role.

## TRIPWIRE: Suspension Preserves the Resume Target and Never Erases Messages (#53)

`resume_stage` / `resume_next_role` / `suspended_at` are non-null **if and only if** the stage is paused. They are set only by `_suspend()` and cleared only by `_clear_suspension()` (unblock, extend, reopen, end).

A pause stores its reason in `pause_reason` and never writes `architect_message`. An unblock without a message keeps an unread message. A model submission consumes only a message addressed to that role (`architect_message_for`). Every decision request ends resolved, by a response or by `cancelled_by_end` at end.

Violations:
- Writing resume fields outside `_suspend` revives a stale target.
- A pause that writes `architect_message` erases an unread interjection or response.
- An unconditional clear on submission lets one role consume the other role's escalation response.

Pinned by `tests/test_loop_suspension.py`.

**Participant side (#53 cp2): suspension is not departure.** Exit `2` means terminal only. Model `status` exits `1` while suspended, `wait` keeps waiting (exit `3` at a bounded deadline), and the watcher acks `architect-block` and stays registered. Making a paused stage a stop signal again (exit `2`, a `paused` wake reason, or a release on `architect-block`) reintroduces the disconnect #53 fixed. Pinned by `test_status_and_wait_keep_participant_in_loop`, `TestRunWatch.test_architect_block_is_acked_and_watch_continues`, `test_watcher_stays_connected_through_suspension` and `test_suspension_cycles_idempotent_across_restarts`.

## TRIPWIRE: Liveness Store Is a Leaf Lock and Never Authority

The liveness lock is a leaf: never acquire the session lock while holding it, and never touch the liveness store inside a `with_session_lock` callback. Snapshot session state unlocked first, then take the liveness lock. The store never holds tokens, nonces, prompts, artifacts, model/provider identity, or session-authoritative fields, and nothing in it may change loop state, deadlines, or `next_role`. It is never written to `events.jsonl`.

Violation: a projection that holds the liveness lock and then waits on the session lock can deadlock against a submit; a store field read as authority lets liveness data drive loop transitions.

## TRIPWIRE: Session Lock Write Ordering

All writers (submit commands, escalate, unblock, and the host's timeout enforcer) must save `session.json` BEFORE appending to `events.jsonl`, both inside the session lock. This guarantees the host's event-tail loop never observes an event whose session state isn't yet durable.

Violation: the host reads a terminal event, loads session.json to print a summary, but sees stale pre-terminal state.

**Sole exception (#47): `architect_attention_due`.** `_try_record_attention` appends this event BEFORE saving its `attention_notified_turn` marker, both inside the session lock. The rule protects events that imply a state change, and this awareness-only event implies none: the marker is idempotency metadata. The inverted order is what makes a crash between the two writes recoverable, because the event is found and the marker repaired. Session-first order would instead lose the event forever behind a marker. No other event may use this exception.

## TRIPWIRE: Token Nonce Separation

Committed `session.json` contains only role names. Secret nonces live only in gitignored `.tokens.json`. Tokens cannot be reconstructed from committed data because the nonce never appears outside `.tokens.json`.

Violation: committing `.tokens.json` or adding nonces to `session.json` makes tokens reconstructable from git history.

## TRIPWIRE: Host Write Authority

The host has exactly ONE loop-state write exception: legacy timeout enforcement. For attention-mode loops (#47) it also appends `architect_attention_due` and saves its `attention_notified_turn` marker, which is awareness metadata, never a stage, role, round or turn change. During normal operation the host is a reader of `events.jsonl` and a renderer to terminal. No other section of code grants the host additional loop-state write paths. (The guarded liveness projection writes only the private Git-path sidecar — never `session.json`, `events.jsonl`, or anything under `.gator/loops/` — see the Liveness Store TRIPWIRE.)

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

Models join a loop via the "gator loop join" instruction in their vendor entry point (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`). The source of truth for this instruction is `render_entry_content()` in `gatorize/entry_points.py` — see [Installer charter](scripts-installer.md). Claude Code also has a `/loop-join` slash command (`templates/gator-starter/commands/loop-join.md`) as a convenience layer. The behavioral protocol is at `procedures/gator-loop-protocol.md`. Artifact format templates are at `reference-notes/loop-artifact-formats.md`. Both files exist as byte-identical pairs between `.gator/.includes/` and `src/.../templates/gator-starter/`; change both copies in the same commit. The participant watcher receiver contract (#36) is at `reference-notes/loop-participant-watcher.md` (same byte-identical pair rule; listed in both `gator_layout.py` shipped-defaults copies). The protocol's `## Suspension Is Not Departure` section (#53) and its Step 1 / Rule 1 / State Machine / Escalation / Quick Reference text state that exit `2` means the loop ended and that a pause or block keeps participants in `wait` or the watcher; the entry renderer, `/loop-join` and the watcher note say the same. The protocol's Step 1 documents the watcher as optional and only for runtimes that re-invoke the agent when a background command exits (Claude Code background Bash, open session, per the M0 spike); `/loop-join` (`.claude/commands/` and the template copy, byte-identical) gives the Claude Code launch line. Coding loops (#41) are documented in the protocol's "Coding Loops (Implementation Review)" section, which has its own state table pinned to `CODING_ALL_STAGES` by `test_protocol_coding_state_table_matches_state_machine`. The planning "State Machine" table stays pinned to `ALL_STAGES`. The implementation template in `loop-artifact-formats.md` is pinned to `submit.IMPLEMENTATION_HEADINGS` by `test_implementation_template_matches_cli_headings`, and `/loop-join` carries the coding steps (both copies byte-identical). The vendor-neutral entry paragraph from `render_entry_content()` deliberately stays on bounded `wait` — it is shared by CLAUDE.md / AGENTS.md / GEMINI.md, and the watcher is not supported for every vendor.

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
