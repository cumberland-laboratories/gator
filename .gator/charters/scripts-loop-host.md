# Charter: Loop Lifecycle and Hosting

**Covers**: `src/gator_command/scripts/loop/host.py`, `src/gator_command/scripts/loop/liveness.py`, `src/gator_command/scripts/loop/codex_launcher.py`

## Owns

Creating, starting, extending, reopening and watching loops; the host and start locks; Architect attention and legacy timeouts; participant liveness; and the opt-in Codex launcher. The session model and transitions are in [Loop State](scripts-loop-state.md).

- `host.py` owns loop initialization (`init_loop()` and `start_loop()`), the single-active guard for extension (`extend_loop()`), the watch loop (attention recording for attention-mode loops; legacy timeout enforcement otherwise), platform-aware file locking (`host.lock`, `start.lock`, plus retrying watcher attachment), and active-loop scanning
- `liveness.py` owns the private participant-liveness sidecar: the per-worktree store at `$(git rev-parse --git-path gator-loop-liveness)/<loop_id>.json`, its strict schema allowlist, atomic persistence, the leaf lock, and the pure helpers `state_key()` / `classify()` / `prune()` / `redact()`. Operational data only; never loop authority
- `codex_launcher.py` owns the opt-in Codex participant launcher. It prepares a dedicated `CODEX_HOME` with the canonical rule and the Gator-owned `config.toml` block, and keeps and discloses the approvals Codex saves after that rule. Read-only plan versus apply. It has no imports from the loop state modules, so it never affects loop authority

## Does Not Own

- Dashboard server-side logic — the dashboard calls into this module via `init_loop()` and `watch_loop()` but host registry, route dispatch, and HTTP handling belong to the dashboard charter
- Auto-launching of agent sessions, except the explicit, opt-in `gator loop codex` launcher (`codex_launcher.py`). It prepares a dedicated Codex home and starts an interactive Codex session, but never starts, joins, or authorizes a loop, and never handles a token
- Session storage, tokens, locks and state transitions; see [Loop State](scripts-loop-state.md).
- Submit handlers, artifact validation and the CLI; see [Loop Commands](scripts-loop-commands.md).

---

### init_loop(feature, sketch_path, max_rounds, turn_timeout, repo_root=None, mode="planning", from_loop=None, brief_path=None, brief_text=None, source_brief=None)
File: `src/gator_command/scripts/loop/host.py`
**Brief:** at most one of `brief_path` (CLI) or `brief_text` (Dashboard) is accepted, and it is validated before any directory is created (`_resolve_brief_input`). `_write_brief` writes the bytes, makes the file read-only (POSIX; on Windows the digest is the enforcement), re-verifies, and returns the metadata. The `loop_started` event records `brief_sha256` / `brief_bytes`, never content. **Planning starts are now atomic as well:** any failure after the directory exists removes it (`_remove_partial_loop`). `source_brief` is rejected on planning starts. `mode="coding"` delegates to `_init_coding_loop()`; then `sketch_path` must be None and `from_loop` is required. Planning requires `sketch_path` and rejects `from_loop`. Planning: creates loop on disk without entering the watch loop. Creates directory, copies sketch, generates three tokens (draftor, reviewer, architect), writes session + initial event. Returns `(loop_id, loop_dir)`. When `repo_root` is provided, uses it directly instead of calling `find_gator_root()` — enables dashboard reuse without filesystem discovery.
Filesystem: `.gator/loops/<loop-id>/` (W, creates), sketch file (R)
<- `start_loop()`, dashboard `_handle_loop_start()`
-> `create_session()`, `save_session()`, `make_token()`, `save_tokens()`, `emit_event()`, `ensure_loops_gitignore()`

### _init_architect_plan_loop(feature, plan_path, sketch_path, max_rounds, turn_timeout, repo_root, brief_bytes=None) / _write_fixed_artifact(loop_dir, name, data) / _write_checked_bytes(loop_dir, name, data, sha)
File: `src/gator_command/scripts/loop/host.py`
`init_loop(..., plan_path=…)` and `start_loop(..., plan_path=…)` route here. `plan_path` with `mode="coding"` is refused before anything is written. The sketch is optional. Atomic order:
1. `read_governed_input` (`MAX_PLAN_BYTES`);
2. `submit._check_plan_draft(bytes, True, True)`: the SAME check as a Draftor draft, on the bytes that are persisted;
3. the optional sketch is checked;
4. the loop dir is created; `architect-plan.md` is written by `_write_fixed_artifact` (read-only, then `verify_fixed_artifact` must return ok); `plan.round-0.md` and `plan.current.md` are written by `_write_checked_bytes` (re-read and SHA-compared); then the optional `sketch.md` and brief;
5. tokens; then `create_session(plan_source=…)`, one Architect turn `{type: "initial_plan", artifact_path: "plan.round-0.md"}`, `current.draft`, `enter_architect_plan_review`, save;
6. events `loop_started` (with `plan_source_kind`, `plan_sha256`, `plan_bytes`) then `architect_plan_submitted` `{role: architect, round: 0, artifact_path: "plan.round-0.md"}`.

Any failure removes the directory. No Draftor turn is fabricated, and the Draftor stays unjoined. The start banner adds a `Plan source:` line.

### _init_revision_loop(feature, sketch_path, revise_from, max_rounds, turn_timeout, repo_root, brief_bytes=None) / _read_revision_source(source_dir, revise_from) / _read_source_file(source_dir, name, what) / _require_source_dir(source_dir, loop_id)
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
The guarded coding successor. Steps, in order:
1. Validate the canonical shape of `from_loop`: `_SOURCE_LOOP_ID_RE` starts AND ends alphanumeric, so a Windows trailing-dot alias is rejected; no `..` / separators. The source must be a real directory with `session.json`: the shared `_require_source_dir` guard refuses a symlinked or reparse-point (junction) source dir before anything in it is opened.
2. Under the source's `with_session_lock` read-only callback, require **`session["loop_id"] == from_loop` exactly**, which rejects Windows trailing-dot and case-variant aliases that resolve to the same directory, so only the canonical id is persisted as `coding.source_loop_id`. Also require `loop_mode == "planning"` (legacy values accepted), stage `plan_approved`, and a non-empty regular `plan.current.md`.
3. **Checkpoints (`_plan_checkpoints`).** `_read_approved_source` also returns the source session's `contract.coding_checkpoints` flag, read under the same lock. The approved-plan bytes are parsed once:

   | Source | Section absent | Present, valid | Present, invalid |
   |---|---|---|---|
   | flagged | **refused** (a flagged plan must have been gated) | `declared` | refused with the problems |
   | legacy | `implicit` (`IMPLICIT_CHECKPOINT`) | `declared` | refused with the problems |

   The manifest is frozen into `coding.checkpoints` (cp1 based on the snapshot's `head_tree`) and never re-parsed.
4. Take `gitsnap.snapshot(repo_root)`, which must be ok; this rejects unborn, conflicted, bare and missing-Git cases. The error is "Cannot capture the Git base for a coding loop: " + `gitsnap.failure_text(snap)`.
5. Create the loop dir, write `approved-plan.md` (read-only), and re-read it to compare SHA-256 against the source bytes.
6. Only then write tokens, `session.json`, and a `loop_started` event (with `mode`, `source_loop_id`).

Any failure removes the partial directory (`_remove_partial_loop`, read-only tolerant; `onexc` on 3.12+, `onerror` below) and raises one clear error.
**Brief carry-forward (the Architect chooses):** inside the same source-lock read:
- the source has no `brief`: `none_available`, whatever the choice;
- `drop`: `dropped`; the source brief is never opened or verified, so a corrupt one cannot block;
- `keep` (the default): `read_verified_brief(source, ref, BRIEF_FILENAME)` must be `ok`. Otherwise the start is rejected atomically with the integrity state and a `--source-brief drop` hint.

Kept bytes are written as `source-architect-brief.md` (copy-then-verify). `submit.coding_status_view(coding, loop_dir)` projects `source_brief` (strict view), `source_brief_check` and `source_brief_decision` for the Dashboard. An optional new `--brief` is written as the coding loop's own `architect-brief.md`. That gives four arrangements: keep or drop, each with or without a new brief. The decision is recorded in `coding.source_brief_decision` and in the `loop_started` event (plus the source brief sha and size when kept).
Filesystem: source `session.json` / `session.lock` (R, lock), source `plan.current.md` (R), `.gator/loops/<new>/` (W)
! The source session is never written. Callers hold `start.lock` (`start_loop`; the Dashboard start in Module 5); lock order is start.lock, then the source session lock, the same as extend.

### reopen_loop(token, message, loop_dir=None)
File: `src/gator_command/scripts/loop/host.py`
Single-active guard for reopen, mirroring `extend_loop()`: take `start.lock`, refuse if another loop is active (`RuntimeError`), delegate to `submit.handle_reopen()`, and release in `finally`. Does not attach a watcher; the caller applies the host contract.
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
! **Prints to the process's `sys.stdout` from its own thread.** In the Dashboard, and in a test process, a watcher can print an event line (`format_event()`: `  [HH:MM:SS] <label>`) at any time. An attention-mode loop does this even with no participant activity, because it appends its own `architect_attention_due`. A test that captures CLI `--json` output must therefore capture only its own thread: use `tests/conftest.py` `own_stdout()`, never a bare `contextlib.redirect_stdout`. Dashboard tests leave such watcher threads running (about 70 after the Dashboard Loop files), and such a leftover thread can leak output into later tests. Pinned by `test_captured_cli_json_ignores_other_threads_output`.
! The host is a READER of loop state during normal operation. Legacy timeout enforcement is the one loop-state write exception. Attention recording writes only an awareness event and its idempotency marker, never loop state (stage, role, round, turn).
! Liveness projection runs after each event batch and just before a terminal return; a `retry`/`error` result is retried on the next tick even without new events. It writes only the private liveness sidecar, never raises, and is skipped when the store is unavailable.
! Terminal detection is session-authoritative: a watcher attached after an extension replays the old `max_rounds_exceeded` event and must keep hosting; a watcher that reads the terminal event after an extension already landed also keeps hosting. `_session_is_terminal()` fails safe (unreadable session -> terminal -> exit).
! `tail_events()` (`gator loop tail`) is intentionally NOT session-authoritative: a human tail started before an extension ends at the old terminal event.

### acquire_host_lock(loop_dir) / release_host_lock(fd) / _try_host_lock(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Non-blocking exclusive file lock on `host.lock` — proves process ownership of a loop's watcher (attention recording for attention-mode loops; timeout enforcement for legacy loops). `probe_host_state()` reads it authoritatively for the Dashboard. Platform-aware: `msvcrt.locking(LK_NBLCK)` on Windows, `fcntl.flock(LOCK_EX|LOCK_NB)` on POSIX. `_try_host_lock()` is the single attempt that distinguishes `"held"` from `"open failed: ..."`; `acquire_host_lock()` wraps it with the unchanged fd-or-None contract.
Filesystem: `.gator/loops/<loop-id>/host.lock` (RW)
<- `start_loop()`, dashboard `_handle_loop_start()`, dashboard `_adopt_orphaned_loops()`
! Returns fd on success, None if already held. OS exclusive lock prevents duplicate watchers cross-process.

### acquire_host_lock_with_retry(loop_dir, attempts=15, delay=0.2, sleep=None) / read_host_metadata(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Watcher attachment for a loop that just became active again. Retries `_try_host_lock()` (~3 s default) so a terminal watcher still releasing its lock can finish. Returns `(fd, state, detail)` with `state` ∈ `HOST_ATTACHED` / `HOST_ALREADY_HOSTED` / `HOST_FAILED`. `read_host_metadata()` is a best-effort, non-locking JSON read of the holder's metadata (often unreadable on Windows while held) used only for the `already_hosted` detail (pid).
Filesystem: `.gator/loops/<loop-id>/host.lock` (RW attempt; R metadata)
<- CLI `_cmd_extend()`, dashboard `_ensure_loop_watcher()`
! `already_hosted` means a live process owns `host.lock` (the OS releases locks of dead processes); callers must NOT start a second watcher. With session-authoritative `watch_loop()`, that holder keeps hosting the extended loop. `failed` (open error) returns immediately without retry. Residual risk: a watcher that decided to exit *before* the extension but takes longer than the retry window to release is misreported as hosted; Dashboard startup adoption is the backstop.

### extend_loop(token, rounds, message, loop_dir=None)
File: `src/gator_command/scripts/loop/host.py`
Single-active-loop guard for extension: resolves the token, takes `start.lock` on the loops base (unavailable -> `RuntimeError`), refuses if `find_active_loop()` returns a *different* loop (`RuntimeError`), then delegates to `submit.handle_extend()` and releases `start.lock` in `finally`. Does not attach a watcher.
Filesystem: `.gator/loops/start.lock` (RW), target session/events via `handle_extend()`
<- CLI `_cmd_extend()`, dashboard `_handle_loop_extend()`
-> `resolve_token()`, `acquire_start_lock()`, `find_active_loop()`, `submit.handle_extend()`, `release_start_lock()`
! Every extension path must go through this function — calling `handle_extend()` directly would bypass the one-active-loop invariant. Rejections leave the target loop byte-unchanged.

### acquire_start_lock(loops_base) / release_start_lock(fd)
File: `src/gator_command/scripts/loop/host.py`
Non-blocking exclusive file lock on `start.lock` — enforces one-active-loop-per-repo during the scan-and-init window (and the scan-and-extend window). Same platform-aware locking as `host.lock`.
Filesystem: `.gator/loops/start.lock` (RW)
<- `start_loop()`, `extend_loop()`, dashboard `_handle_loop_start()`
! Held only during the start or extend sequence. Released before entering `watch_loop()`.

### find_active_loop(loops_base)
File: `src/gator_command/scripts/loop/host.py`
Scans `loops_base` for non-terminal sessions. Returns `loop_id` or None.
Filesystem: `.gator/loops/*/session.json` (R)
<- `start_loop()`, dashboard `_handle_loop_start()`, dashboard `_adopt_orphaned_loops()`
-> `load_session()`, `is_terminal()`
! **Fails closed.** It reads through `load_session()`, with the sharing-violation retry. A `SessionBusyError` counts that loop as **active**, so a transient Windows sharing violation can never hide an active loop from the single-active guard; the start or extend is refused instead. Missing, corrupt or malformed sessions are still skipped. Pinned by `test_find_active_loop_fails_closed_when_session_is_busy`.

### _try_record_attention(loop_dir, now=None) / _attention_due(session, now) / _find_attention_event(loop_dir, key) / _ensure_events_newline(path)
File: `src/gator_command/scripts/loop/host.py`
Records exactly one durable `architect_attention_due` event per active turn of a flagged loop. It never changes stage, role, round or turn, so time never changes loop state.
- **`_attention_due`** is pure and never raises: flagged, active, not paused, a valid **offset-aware** `turn_started_at` and a positive int interval (`turn_timeout_seconds`), with `now ≥ start + interval`. A naive or unparsable timestamp, or an overflowing comparison, means not due.
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

### attention_status_view(session, loop_dir, now=None)
File: `src/gator_command/scripts/loop/host.py`
The Architect-only Dashboard projection. It returns `None` for legacy sessions, otherwise `{interval_seconds, turn_started_at, notified_turn, notified, due}` built from validated primitives. `notified` is the marker, or a matching event found by `_find_attention_event`; the scan runs only when the marker is missing and the turn is due.
<- dashboard `_handle_loop_status()`
`host`: only in the due-and-not-notified state, `probe(loop_dir)` (default `probe_host_state`) gives `attached` / `none` / `unknown`. A probe exception or bogus value means `unknown`; otherwise `host` is null.

### probe_host_state(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Authoritative and non-blocking: one `_try_host_lock` attempt. `held` means `attached`; acquired means `none`, released immediately; open failed means `unknown`. A second handle conflicts with a held lock even in the same process, so the Dashboard's own watcher reads as attached.
! Call only rarely (attention due and not recorded). Holding the probe even briefly could collide with a single-attempt acquirer (start, adoption), which never targets a long-running due turn.

### _try_enforce_timeout(loop_dir)
File: `src/gator_command/scripts/loop/host.py`
Acquires session lock, re-reads session, fires timeout only if deadline still expired and state still active. Race-safe: if a submit advanced the state, timeout is silently skipped. **Legacy only:** returns without writing for `attention_mode` sessions, even with a forced deadline (defense in depth).
Filesystem: `session.json` (RW via lock), `events.jsonl` (W via lock)
<- `watch_loop()`
-> `with_session_lock()`, `advance_turn_timed_out()`
! One of the two Host Contract write exceptions, legacy loops only. The other is `_try_record_attention` for attention-mode loops, which writes no loop state. Lock-then-re-read discipline prevents the timeout-vs-submit race.

### codex_launcher: default_home() / validate_home(home, repo_root, env, tempdir=None) / trust_key(repo_root, platform)
File: `src/gator_command/scripts/loop/codex_launcher.py`
`default_home()` is `~/.gator/adapters/codex/loop-home`. `validate_home` resolves the home and refuses: (inside) the normal Codex home (`~/.codex` or the caller's `CODEX_HOME`), inside the governed repo, and under the temp directory. `trust_key` gives the `[projects.'<key>']` key: on Windows the lowercase backslash form Codex itself writes (spike §8.8, the `\\?\` prefix stripped); otherwise the resolved POSIX path. A `'` or newline in the path is refused.
Filesystem: none (path arithmetic only)
! Never read anything in the normal Codex home; these checks compare paths only.

### codex_launcher: sandbox_temp_root(home) / render_config(existing_text, repo_key, platform, temp_root=None) / _split_block / _outside_conflicts / _parse_check / _without_gator
File: `src/gator_command/scripts/loop/codex_launcher.py`
Pure. It keeps every byte outside the one Gator-owned block (`BLOCK_BEGIN` … `BLOCK_END`) and regenerates the block **at the end** of `config.toml` with the union of its own trusted keys and the current repo, plus `[windows] sandbox = "elevated"` on Windows. **Sandbox temp root:** on Windows, with `temp_root`, the block also holds `[shell_environment_policy.set] TEMP/TMP = '<root>'` and `[sandbox_workspace_write] writable_roots = ['<root>']`, the keys the spike proved (Q1–Q3). `sandbox_temp_root(home)` is `<home-parent>/<home-name>.sandbox-tmp`, a **sibling** of the home: inside the home, test temp paths fall under `CODEX_HOME` and `validate_home` refuses them (spike E2b).
! A validated home does not make its sibling safe (the sibling can itself be the repository). `validate_temp_root(root, home, repo_root, env, tempdir=None)` runs in `main()` right after `validate_home`, before `plan_preparation`. It refuses a symlink or reparse point (`_is_link`: `is_symlink()` or `FILE_ATTRIBUTE_REPARSE_POINT`, per the cross-cutting containment contract). It also refuses any overlap, in either direction, with the repository, the dedicated home, `~/.codex`, the caller's `CODEX_HOME` or the temp directory. Read-only, so a refusal writes nothing.
! Accepted trade-off (spike Q4): `shell_environment_policy` applies to every command, so an approved unsandboxed command also gets the redirected `TEMP`. It runs as the Architect and cannot use folders the sandbox account created there (for example `pytest-of-<user>`). `SANDBOX_TEMP_NOTE` says this in the dry run and before launch. Never add test or Python commands to `RULE_TEXT` to work around it. Retained lines (outside and relocated) keep their own terminators (`splitlines(keepends=True)`, `_terminated`), so mixed CRLF/LF content is not normalised. Only the regenerated block and the joining blank line use the file's dominant ending (CRLF if any is present). **Codex-written tables:** Codex appends its own tables (`[tui…]`, `[hooks.state…]`) at the end of the file, which is inside the block. `_split_block` returns every table section inside the markers that is not `[windows]` or `[projects.'<key>']` (header through the line before the next `_TABLE_HEADER`) verbatim, and `render_config` moves those sections, in order, to just above the block. Evidence: spike artifact `2026-10-27-codex-sandbox-temp-spike.md` (E5/E6: Codex keeps reading and updating relocated tables, with no new hook-trust prompt).
! Fail-closed (`ProfileError`, nothing written) on: malformed or duplicate markers; a key line inside the block before any table header, or any line other than Gator's own (`_GATOR_TABLES` / `_PROJECT_BODY`), a blank or a comment inside a Gator-owned table (ambiguous owner); a user `windows`, `shell_environment_policy` or `sandbox_workspace_write` table or dotted key outside the block (`_GATOR_OWNED_OUTSIDE`), including relocated sections (Windows); a temp root that cannot be a TOML literal; a user `[projects…]` header containing the same trust key; an unquotable key. On Python >= 3.11, `tomllib` must parse the result, the current file must parse, and every setting except the Gator-owned tables (`windows`, `shell_environment_policy`, `sandbox_workspace_write`) and Gator's own `projects` keys must parse to the same value before and after (`_without_gator`). On 3.9/3.10 the header scan is the only guard.
! The block stays last so its table headers cannot capture user top-level keys. Only Gator's own generated `[projects.'…']` lines are parsed. There is no TOML framework.

### codex_launcher: plan_preparation(home, repo_root, platform) / apply_preparation(actions) / render_dry_run(actions, home, repo_root, platform)
File: `src/gator_command/scripts/loop/codex_launcher.py`
`plan_preparation` is read-only. It returns ordered `mkdir` / `write` / `keep` actions for the home, `rules/`, the sandbox temp root (Windows; `sandbox_temp_root`, a sibling of the home), `rules/default.rules` (`RULE_BYTES`) and `config.toml`; the rule action also carries `saved` (the `SavedRule` records, `()` when none). `apply_preparation` executes exactly those actions (temp file + `os.replace`, UTF-8 without a BOM). `render_dry_run` previews the home, repo, trust entry, sandbox temp root with `SANDBOX_TEMP_NOTE`, actions, rule text, the saved approvals (`render_saved_rules`) and launch.
Filesystem: dedicated home (R in plan, W in apply only)
! Rule ownership: an absent file → write; `RULE_BYTES` → keep; a `KNOWN_GENERATED_RULES` form → normalize; `RULE_BYTES` followed by Codex-saved approvals → keep, suffix bytes never rewritten, parsed by `parse_saved_rules`. Anything else (an altered prefix, an older generated form plus a suffix), or any other file in `rules/`, fails closed: Codex may load it and widen the allow-list.

### codex_launcher: parse_saved_rules(suffix, rule_path) / _saved_rule / _safe_pattern / _safe_text / render_saved_rules(saved) / saved_rules_of(actions)
File: `src/gator_command/scripts/loop/codex_launcher.py`
Pure. `parse_saved_rules` reads the bytes after `RULE_BYTES` with `ast.parse` (never evaluated) and accepts only `prefix_rule(...)` calls with keyword literals from `SAVED_RULE_KEYS` (`pattern` and `decision` required; decision in `SAVED_DECISIONS`; pattern a list of strings or string-alternative lists). Comments and blanks are allowed. `_safe_pattern` applies the closed credential display policy to the pattern: `glp_` tokens, `name=value` / flag values / `Name:` headers / `Bearer`/`Basic` values whose name matches `_SENSITIVE`, and URL userinfo show as `<redacted>`. A credential flag that ends a pattern element hides the **whole** next element (one argument, however many words). Inside a string (for example a `powershell -Command` script) a value is hidden only when it is one unquoted word (`_hide`, `_SCRIPT_VALUE`); it keeps its trailing shell separator (`;`, `&`, `|`, `)`), so a following command stays visible. A `Name:` header hides the rest of its element only when it is the element's first word and no separator or quote (`_SCRIPT_BREAK`) follows. `render_saved_rules` gives the disclosure lines (decision + JSON pattern, `SAVED_SANDBOX_NOTE` for any allow, `SAVED_LIMIT_NOTE`). `saved_rules_of` picks `saved` from the planned actions for `main()` and the dry run.
! Fail-closed (`ProfileError`, nothing written): non-UTF-8, a syntax error, any other statement or call, positional/`**`/unknown/duplicate arguments, a non-literal or wrongly typed value, a `Cc`/`Cf` character in any string, a stanza repeating Gator's own pattern, or an unrenderable pattern (the program element would be hidden, a value-taking form ends the stream, a script value is quoted or runs into another command, or a header is followed by a separator or sits mid-script). The message names only the approval's position, never its text.
! The display never prints `justification`, `match` or `not_match`. A secret with no marker cannot be recognised and is shown; `SAVED_LIMIT_NOTE` says so. Python and Starlark lexing differ slightly; `check_policy` runs on the same file, so Codex's own parse failure fails closed.
! `RULE_TEXT` must stay byte-identical to the rule in `reference-notes/codex-routine-participant-profile.md` (pinned by `tests/test_loop_codex_launcher.py`). It is the verified five-subcommand allow-list; never widen it here.
! A BOM on an existing `config.toml` is dropped (Codex expects UTF-8 without a BOM). All other outside bytes are preserved.

### codex_launcher: codex_version(codex, run) / check_policy(codex, rules_path, env, run) / child_env(env, home) / launch(codex, repo_root, env, run)
File: `src/gator_command/scripts/loop/codex_launcher.py`
`check_policy(codex, rules_path, env, run, saved=(), shown_path=None)` runs `codex execpolicy check --rules <rules_path> -- …` for the three `POLICY_PROBES`: `gator loop status` must report `decision == "allow"`; `git write-tree` and `gator loop end` must report `matchedRules == []`. A non-zero exit, non-JSON output or any other result raises `ProfileError` before launch. `main()` passes a temporary copy of `planned_rule_bytes(actions)` (the exact file Codex will load: the kept file or `RULE_BYTES`) and names the real `<home>/rules/default.rules` as `shown_path`. On a failed probe, the local `_matches` names each saved approval whose pattern prefix-matches the probe ("saved approval N of M"), and the message says to remove or narrow it. `_matches` explains only; Codex's result is the authority.
! Codex output is never echoed. `_policy_result` reads only `decision` and `matchedRules[].prefixRuleMatch.{matchedPrefix, decision}`. Both decisions must be in `SAVED_DECISIONS` and each prefix a list of strings; any other shape is "unexpected output (not shown)". Prefixes are shown through `_safe_pattern` (`_shown`). A non-zero exit prints only the probe, the exit code and the manual `codex execpolicy check` command, because Codex parse errors quote the offending source line. An `OSError` names only its type. `child_env` returns a copy of the environment with `CODEX_HOME` set. `launch` runs `[codex]` (an argument list, no shell) with `cwd=repo_root` and returns the exit code. `codex_version` parses `codex --version`; None on failure.
! The probes use literal placeholder arguments (`--token x`); no real token is ever passed, and no command line or environment carries one.
! The probe and launch children receive the dedicated `CODEX_HOME`; the caller's `os.environ` is never mutated.

### codex_launcher: main(args, *, env=None, platform=None, which=shutil.which, run=subprocess.run, cwd=None, tempdir=None)
File: `src/gator_command/scripts/loop/codex_launcher.py`
`gator loop codex` orchestration. Order: governed repo (`find_gator_root`) → Windows-only check → `validate_home` → `validate_temp_root` → `plan_preparation` → (`--dry-run`: print `render_dry_run`, return 0) → `which("codex")` → version (warns, does not refuse, when not `VERIFIED_CODEX_VERSION`) → `check_policy` (on a temporary copy of the planned rule bytes) → `apply_preparation` → trust summary (with the sandbox temp root) + `TRUST_WARNING` + `SANDBOX_TEMP_NOTE` + the saved approvals (`render_saved_rules`) (+ `SIGN_IN_NOTE` when `<home>/auth.json` is absent) → `launch`. It returns Codex's exit code. A non-zero exit with no `auth.json` prints the `codex login` recovery hint naming the resolved `CODEX_HOME`.
<- `cli._cmd_codex`
! Every refusal (`ProfileError`: not governed, non-Windows, bad home, conflict, missing Codex, failed boundary) prints the manual-note pointer and returns 1. Every refusal happens before `apply_preparation`, including a failed boundary check, so a refusal writes nothing to the home. The only write is the temporary probe copy outside it.
! `auth.json` is checked for existence only, never read. Nothing in the normal Codex home is read or written.
! The injected seams (`env`, `platform`, `which`, `run`, `cwd`, `tempdir`) exist for tests. The CLI passes none.

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
Pure helpers. `state_key` is the SHA-256 idempotency key over `round`, `stage`, `next_role`, `len(turns)`, `turn_deadline`, plus `turn_started_at` **only when that key exists** (attention-mode sessions), so legacy keys hash without it. `attention_notified_turn` is deliberately excluded: recording attention never creates a participant notification. `classify` returns `not_registered` / `connected` / `stale` (active only, > 3 × heartbeat) / `released` / `closed` / `expired` (> 24 h unseen). `prune` applies retention: delete when the loop dir is gone or terminal > 7 days; drop expired registrations; TTL-expire pending `turn-ready` > 24 h; cap 50 notifications per role (pending never dropped — so a role whose records are all pending may exceed 50; pending records still TTL-expire), 10 superseded, 100 audit.

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
D5 projection. Snapshots `session.json` WITHOUT the session lock (torn/locked read -> `retry`), then applies the rules under the liveness leaf lock: expire every pending record from an older `state_key` (`state_changed`); active -> one `turn-ready` per (next_role, state_key), recorded even for an unregistered role; paused -> one `architect-block` per registered non-closed role; terminal -> one `terminal` per registered non-closed role, closing a registration that was already told for this generation (so a late watcher exits 2 at once), and set `terminal_observed_at` (cleared again when an extension makes the loop non-terminal). Then `prune()`; saves only when something changed (`unchanged` / `updated`); a vanished loop directory or 7-day terminal retention deletes the sidecar (`deleted`). `project_for_host` is the never-raising wrapper for `watch_loop` (sanitized `last_error`, stderr diagnostic only with `GATOR_DASHBOARD_DEBUG=1`).
! Never reopens a `closed` registration and never writes loop state.

### renotify_eligibility(state, session, role, now=None)
File: `src/gator_command/scripts/loop/liveness.py`
Pure D7 eligibility for an Architect Re-notify -> `(eligible, reason_code)`. Eligible when the role owns the current active turn, or has a pending record and no live watcher (stale / released / not registered / expired). Otherwise `terminal`, `already_acknowledged`, or `not_actionable` (including a pending record a connected watcher will receive). Rate limiting belongs to the Dashboard endpoint.

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

**Suspension:** `architect-block` is not in `_DELIVERY_OUTCOME`. It is acked and the watch continues with the registration still `active` (poll heartbeats it), so a pause or block never releases or ends the watcher. `still_waiting` adds `suspended: true` and the paused `stage` (`_suspension_fields`, one unlocked session read; a failure omits them). `architect_block` remains only as a legacy wake reason in `_render_participant`. A `RegistrationClosedError` mid-watch (closed by the terminal path) returns `2 terminal` with no write. Never loops forever or relaunches itself. `clock`/`sleep` are test seams.

---

## TRIPWIRE: Architect-Originated Plans Are Unapproved Input

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

## TRIPWIRE: Revision Baselines Are Copies

A revision loop's authority is its two copied, verified baseline files (`revision-baseline-plan.md`, `revision-baseline-approval.md`), never a live path into the source loop.
- The copies are captured ONLY under the source's session lock in a read-only callback; the source loop is never written, reopened or extended.
- The approving review is identified ONLY from the session's last turn plus the cross-copy equality checks. If they don't hold, the start fails atomically; the evidence is never guessed or quietly omitted.

Violations:
- reading the source loop live after creation;
- writing the source session;
- treating a missing approval as optional.

Pinned by `test_revision_lifecycle` (source byte-immutability, deleted-source integrity) and `test_revision_rejection_is_atomic`.

## TRIPWIRE: Attention Is Architect Awareness, Never Participant Pressure or State

For `attention_mode` loops (`contract.attention_interval`, set on every new session), time passing NEVER changes loop state: no stage, role, round or turn change; no pause; no termination; no participant wake-up. The interval (stored in `turn_timeout_seconds`) produces exactly one durable `architect_attention_due` event per turn.
- **The host watcher is the only writer.** `_try_record_attention` writes the event first and the marker second, and recovers if interrupted between them; this is the documented sole exception to "Session Lock Write Ordering".
- **Participants never see time.** Participant status, `wait`, prompts and protocol carry no interval, deadline, countdown or request-more-time flow. Only Architect surfaces (Architect CLI view, Dashboard) show the interval, elapsed time and notice.
- **Host state is never inferred.** The Dashboard's host wording comes only from `probe_host_state`, never from a missing marker.
- **Legacy loops are unchanged.** Unflagged sessions keep their recorded hard-timeout semantics byte-for-byte, and `turn_timed_out` residue is never reinterpreted.

Violation: adding a deadline, a participant-visible window, or a state transition for flagged loops reintroduces the time pressure attention mode removes. Gating on anything other than `attention_mode` (dates, versions, field presence) breaks legacy loops.

## TRIPWIRE: Source Loop Directories Are Contained

Every path that reads another loop as a source (`_init_coding_loop` for `--from-loop`, and `_init_revision_loop` for `--revise-from`) calls `_require_source_dir` first. It rejects the directory when it is a symlink **or** `_is_reparse_point`, before `session.json` or any artifact is opened. `is_symlink()` alone is not enough on Windows, where a directory junction is a reparse point that `is_symlink()` does not report. The per-file checks in `_read_source_file` cannot catch a redirected directory, because the files behind it are ordinary.

Violation: a junction under `.gator/loops/` redirects source reads outside the governed loops directory. That is pinned by `test_reparse_point_source_dir_is_refused` (both paths, atomic, source session never locked) and `test_symlinked_source_dir_is_refused`.

## TRIPWIRE: Liveness Store Is a Leaf Lock and Never Authority

The liveness lock is a leaf: never acquire the session lock while holding it, and never touch the liveness store inside a `with_session_lock` callback. Snapshot session state unlocked first, then take the liveness lock. The store never holds tokens, nonces, prompts, artifacts, model/provider identity, or session-authoritative fields, and nothing in it may change loop state, deadlines, or `next_role`. It is never written to `events.jsonl`.

Violation: a projection that holds the liveness lock and then waits on the session lock can deadlock against a submit; a store field read as authority lets liveness data drive loop transitions.

## TRIPWIRE: Host Write Authority

The host has exactly ONE loop-state write exception: legacy timeout enforcement. For attention-mode loops it also appends `architect_attention_due` and saves its `attention_notified_turn` marker, which is awareness metadata, never a stage, role, round or turn change. During normal operation the host is a reader of `events.jsonl` and a renderer to terminal. No other section of code grants the host additional loop-state write paths. (The guarded liveness projection writes only the private Git-path sidecar — never `session.json`, `events.jsonl`, or anything under `.gator/loops/` — see the Liveness Store TRIPWIRE.)

## Before Changing This Module

- Preserve lock ordering, role authorization, and stage/turn invariants.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) -- Package CLI Entry Point (cli.py COMMANDS dict), sys.path import convention
-> [Core Library](scripts-core-library.md) -- `find_gator_root()`, `ensure_utf8_stdout()`, `get_version()`
-> [Dashboard Server](scripts-dashboard.md) -- calls `init_loop()`, `watch_loop()`, `acquire_host_lock()`, `find_active_loop()`, `resolve_token()`, `load_tokens()`
-> [Loop State](scripts-loop-state.md) -- session, tokens, locks and the transitions the host reads and enforces
-> [Loop Commands](scripts-loop-commands.md) -- the CLI and handlers that start, extend and reopen loops here
