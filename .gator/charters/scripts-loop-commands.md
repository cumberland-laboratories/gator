# Charter: Loop Commands

**Covers**: `src/gator_command/scripts/loop/submit.py`, `src/gator_command/scripts/loop/cli.py`, `src/gator_command/scripts/loop/gitsnap.py`, `src/gator_command/scripts/gator-loop.py`

## Owns

What participants and the Architect do in a loop: the submit and Architect handlers, artifact validation, the `gator loop` CLI, and the Git evidence coding loops capture. The session model and transitions are in [Loop State](scripts-loop-state.md).

- `submit.py` owns the ten submit handlers: submit-draft, submit-implementation (coding), submit-review, escalate, unblock, extend, reopen, pause, interject, end; plus the coding implementation-artifact helpers (required headings, the CLI-owned Commit State section)
- `cli.py` owns argparse subcommand routing for all 17 loop subcommands (start [--mode planning|coding, --from-loop], status, submit-draft, submit-implementation, submit-review, escalate, pause, interject, end, unblock, extend, reopen, wait, participant {watch,status}, tail, codex [--dry-run, --home], list)
- `gitsnap.py` owns the coding-loop Git snapshot: `snapshot(worktree_root, base_head, approved_head=None)` -> raw, unfiltered Git facts (HEAD, trees, staged-tree OID, changed paths vs base, unstaged/untracked residue, and with `approved_head` the `approval_history` first-parent-successor fact), plus one named derived value, `governed_index_identity`, or an explicit error code. Read-only toward refs, index, and worktree
- `gator-loop.py` is the thin entry script dispatched by `src/gator_command/cli.py`

## Does Not Own

- Git commits of session residue (always human/agent-initiated)
- Session storage, tokens, locks and state transitions; see [Loop State](scripts-loop-state.md).
- Loop creation, hosting, attention, liveness and the Codex launcher; see [Loop Lifecycle and Hosting](scripts-loop-host.md).

---

### handle_submit_draft(token, file_path)
File: `src/gator_command/scripts/loop/submit.py`
Resolves token, validates file, acquires lock, validates action, writes the artifact to `plan.round-N.md` then `plan.current.md`, appends turn, updates `current.draft` with turn reference dict, advances to `plan_review`, emits event.
Filesystem: source file (R, once), `.gator/loops/<loop-id>/plan.round-N.md` and `plan.current.md` (W)
<- `cli._cmd_submit_draft()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `_plan_contract_flags()`, `_check_plan_draft()`, `append_turn()`, `advance_draft_submitted()`
! `current.draft` stores `{turn_id, summary, artifact_path}`, not a bare string.
! **Context evidence.** The source file is read **once** into a captured byte buffer before the lock.
  - **Flagged sessions** (`contract.context_evidence` is an int ≥ 1, never a bool): a preflight check on the captured bytes gives an early error. A preflight session-read failure is ignored, never misreported. The **in-lock check is authoritative**: decode as UTF-8, run `context_checked_problems`, then write **those exact bytes** with `_write_artifact_bytes`. There is no second read and no path copy, so a file swapped after capture is never persisted. Rejection raises `ValueError("Plan draft rejected: …")` before any write or state change, which is atomic. This covers first drafts and revisions.
  - **Unflagged (legacy) sessions** keep `_copy_artifact` byte-for-byte, unchanged.
  - **Checkpoints:** `_plan_contract_flags(session)` returns `(context_evidence, coding_checkpoints)`; either flag (int ≥ 1, never bool) routes through the same capture-once path. `_check_plan_draft` runs every flagged check on the same decoded text and raises one `Plan draft rejected: ...` error listing all problems; checkpoint problems are prefixed `Coding Checkpoints: ` and a missing section quotes `ONE_CHECKPOINT_EXAMPLE`. Legacy sessions are never checkpoint-checked at draft time (their plans are re-checked when a coding loop starts).
  - Coding loops never call this (implementation submissions have their own headings).
  - **Executive summary:** `_executive_summary_required(session)` (int ≥ 1, never bool) also routes through the capture-once path; the summary check is NOT part of `_check_plan_draft`, so Architect-originated plans (`host.py`) need none. The preflight and the authoritative in-lock check run `_summary_or_raise` on the same decoded bytes, and `draft_submitted` gains `executive_summary`.

### executive_summary_problems(text) / _executive_summary_required(session) / _summary_or_raise(text, kind)
File: `src/gator_command/scripts/loop/submit.py`
Closed grammar for the participant's `## Executive Summary`. Returns `(summary, problems)`: exactly one VISIBLE level-2 heading, found by its own `_es_visible_sections(text)` (HTML comments removed first, an unterminated comment hides the rest; a fence closes only on the same character with at least the opener's length, so a shorter or different inner fence never exposes a heading); that section's body lines; one paragraph (no blank line between text lines); no line starting with a list marker (`-`, `*`, `+`, `N.`, `N)`), `#`, `|`, `>` or a fence; not a placeholder (`_PLACEHOLDER_BODIES` after stripping non-alphanumerics, so `...` counts); 1 to `EXECUTIVE_SUMMARY_MAX` (1,200) Unicode code points (`len()`) after whitespace collapse; the Timeline counts the same unit. The summary is the collapsed text. Problems are repair instructions, never a quality score. `_summary_or_raise` raises `ValueError("<kind> rejected: Executive Summary: ...")`. `_decode_or_raise` gives `"<kind> must be UTF-8 text"`.
! Text after the paragraph with no new level-2 heading belongs to the section and is rejected; a section must end at the next `## ` heading.
! A heading inside an HTML comment or a fenced example neither satisfies nor duplicates the section, so text a reader cannot see never becomes Timeline evidence. The scan is local to this parser; the shared `_h2_titles` / `_section_body` used by Context Checked and Commit State are unchanged. Normalization is for extraction only; the captured bytes are stored unchanged.
! The shipped plan, findings, approval and implementation templates must pass it (drift-guarded in `tests/test_loop_context_evidence.py`).

### context_checked_problems(text)
File: `src/gator_command/scripts/loop/submit.py`
Structural check of a plan's `## Context Checked`. It returns a list of reasons (`[]` = ok).
- Exactly one level-2 heading, case-insensitive, found by the fence-aware `_h2_titles` scan. Fenced examples never count, and `###` is not the section.
- The body (to the next unfenced `##`) must be non-empty once HTML comments and blank lines are removed.
- The body must not be only a placeholder: after reducing to `[a-z0-9]`, `none` / `na` / `nothing` / `tbd` / `todo` / empty (e.g. `-`) are rejected.
- `None — <reason>` (any separator plus a reason) is accepted.
- Adequacy is the Reviewer's judgment, never checked here.
! The shipped plan template in `loop-artifact-formats.md` must contain exactly one section that passes this check (drift-guarded in `tests/test_loop_context_evidence.py`).

### parse_coding_checkpoints(text) / coding_checkpoints_problems(text, required)
File: `src/gator_command/scripts/loop/submit.py`
Closed grammar for a plan's `## Coding Checkpoints`. `parse_coding_checkpoints` returns `(present, items, problems)`; items are `{id, title, scope, verify}` with positional ids `cp1..cpN`.
- Exactly one level-2 heading (fence-aware `_h2_titles`); the body runs to the next unfenced `##`. HTML comments, blank lines and fenced blocks in the body are ignored.
- Items: `N. **Title** — scope. Verify: verification.` at column 0, numbered 1..N with no gaps; `—`, `-` or `:` after the title; continuation lines indented two spaces. Any other text is a problem.
- 1–`CHECKPOINT_MAX_ITEMS` (12) items. Titles are 1–80 chars of plain text (no backticks/markup) and never path-shaped (`[/\\]` or a trailing `.ext`). Scope and verification are whitespace-collapsed, non-placeholder, and capped at `CHECKPOINT_TEXT_MAX` (400) chars.
- `coding_checkpoints_problems(text, required)`: an absent section is a problem only when `required`.
- Whether checkpoints are responsibility-based is the Reviewer's judgment, never checked here.
! The shipped plan template's checkpoint section must parse valid (drift-guarded in `tests/test_loop_checkpoints.py`).

### handle_submit_review(token, file_path, approve)
File: `src/gator_command/scripts/loop/submit.py`
Same pattern as draft. Copies to `findings.current.md`. Branches on `--approve`: terminal or revision. Before the lock: if `approve` is False, reads the first 500 bytes (decoded with `errors="replace"` for safety) and checks for an actual `## Verdict` heading followed by `ESCALATE` (regex, case-insensitive). If matched, emits a stderr warning after the successful submission. This is a soft guard — does not block the submission and cannot raise on non-UTF-8 input.
**Executive summary (flagged planning sessions):** the review is read ONCE before the lock (preflight `_summary_or_raise`, which also requires UTF-8), re-checked authoritatively in the lock, and **those bytes** are written with `_write_artifact_bytes` to `findings.round-N.md` and `findings.current.md`. The one emitted event (`revision_requested` / `plan_approved` / `max_rounds_exceeded`) gains the Reviewer's own `executive_summary`. Legacy sessions keep the path copy and accept non-UTF-8 findings. Rejection is before any write or state change.
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
**Recipient:** a decision response (message and artifact) is addressed to the escalating role (`request.role`), which may not be the resumed turn owner. Another unblock message is addressed to the resumed role. Without a message or file, an unread Architect message is kept. The response artifact name is computed before `advance_unblocked()`, and the file is copied after it.
Response contract: a whitespace-only message is treated as absent. When a pending decision exists (escalation), one of message / file / `no_response=True` is required, else `ValueError` before any mutation. `no_response` is mutually exclusive with message/file and rejected when nothing is pending. `response.kind` ∈ `message`, `artifact`, `message_and_artifact`, `deliberate_empty`. Model-facing `architect_message` is the message, or `ARTIFACT_ONLY_RESPONSE_SUMMARY` for file-only, or `DELIBERATE_EMPTY_RESPONSE_SUMMARY` for the explicit empty choice — never silently blank for a resolved decision. An ordinary pause (no pending decision) still unblocks with no response.
**Attention mode:** for `attention_mode` sessions, a non-None `turn_timeout` raises `ValueError(ATTENTION_TIMEOUT_REFUSAL)` inside the lock before any mutation, because no participant window exists to change. Legacy turn window: optional `turn_timeout` is validated via `validate_turn_timeout()` before the lock; inside the lock it is written to `status.turn_timeout_seconds` BEFORE `advance_unblocked()` computes the fresh deadline, so both this turn and all later transitions use it. Omitted keeps the stored window. The `loop_unblocked` event carries `turn_timeout_seconds` always, plus `previous_turn_timeout_seconds` and a detail suffix when changed, and `response_kind` alongside `decision_id` when a decision was resolved.
Filesystem: `.gator/loops/<loop-id>/decision-response.decision-*.md` (W, when file_path provided), session mutation
<- `cli._cmd_unblock()`, dashboard `_handle_loop_unblock()`
-> `resolve_token()`, `validate_turn_timeout()`, `with_session_lock()`, `validate_unblock()`, `advance_unblocked()`, `append_turn()`, `_copy_artifact()` (when file_path provided)
! All validation that can fail runs before `advance_unblocked()`/`_copy_artifact()`; a raise inside the lock skips the save, so a rejected unblock leaves session.json, events, and the stored timeout untouched.

### handle_submit_implementation(token, file_path, loop_dir=None, checkpoint=None)
File: `src/gator_command/scripts/loop/submit.py`
Coding Draftor submission. Returns `(loop_id, role, loop_dir, generation)`.

**Before the lock:** the file must exist, be UTF-8 and non-empty, and contain the required level-2 headings (`IMPLEMENTATION_HEADINGS`: Executive Summary, Implementation Summary, Charter Updates, Verification, Commit State). Missing headings are listed in the ValueError. **Exactly one** level-2 `Commit State` heading may exist outside fences (`commit_state_heading_count`). A duplicate is rejected, so no author-controlled competing state block can sit next to the CLI-captured one; a Commit State example inside a code fence is allowed.

**Executive summary:** `executive_summary_problems(text)` runs on the participant text before the lock (before Commit State is replaced). In a flagged session a problem raises `ValueError("Implementation rejected: Executive Summary: ...")` right after `validate_action`, before the snapshot or any write, and `implementation_submitted` gains `executive_summary`.

**Under the session lock:**
1. `validate_action(..., "submit_implementation")`.
2. **Checkpoint binding.**
   - A manifest loop requires `checkpoint == active.id`; the error names the active checkpoint. The only exception is an implicit manifest, which may omit the flag.
   - A session without a manifest rejects `checkpoint` outright.
3. `gitsnap.snapshot(repo_root, coding.base_head)`, which must be `ok` (otherwise ValueError "Cannot capture the staged candidate: " + `gitsnap.failure_text(snap)`, which names the code and adds the guidance for `git_permission_denied`).
4. Something must be staged (otherwise "Nothing is staged…"):
   - loops without declared checkpoints (legacy and implicit) require `staged_tree != base_tree`;
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
- **`render_commit_state(snap, checkpoint=None)`:** with a declared checkpoint view, `_render_checkpoint_commit_state` adds:
  - Checkpoint, checkpoint base tree and Generation rows;
  - the review command `git diff <checkpoint base> <staged>`;
  - the checkpoint path list with `[revisits an earlier checkpoint]` markers;
  - the loop-base facts and the cumulative diff command as context.
  Titles go through `_cell` (pipe-escaped). Without a checkpoint view the output is **byte-identical** to a loop without checkpoints.
- **`replace_commit_state`:** swaps the Commit State section up to the next unfenced level-2 heading. It also refuses more than one Commit State heading, as a second layer behind the handler's check.
- **`split_residue`:** a **display-only** classification of raw residue into loop residue (`.gator/loops/`, the loop's own always-untracked audit files) and other residue. Only other residue triggers the CLI warning. The persisted snapshot keeps the raw list.
- **`coding_status_view`:** the slim, allowlisted projection of `session["coding"]` that the Dashboard status poll serves: source/plan/base ids, per-generation tree / HEAD / branch, changed counts by status, residue counts, review verdicts, and the approval binding. Never raw path lists.

### handle_submit_review(token, file_path, approve=False, loop_dir=None) — coding path: _coding_review(session, role, loop_dir, source, approve) / render_reviewed_candidate(review)
File: `src/gator_command/scripts/loop/submit.py`
Planning reviews are unchanged. For coding loops, inside the same session lock:
- **Binding:** the review binds to the LATEST generation's submitted candidate (`reviewed_tree` / `reviewed_head`). The Reviewer inspects it with the immutable `git diff <base_tree> <staged_tree>`.
- **Live check:** a fresh `gitsnap` snapshot is taken.
  - **APPROVE is rejected unless the live staged tree AND HEAD still equal the submitted candidate.** The tree test is `_same_candidate(submitted, snap)` → `state_machine.same_governed()`: governed identities when both carry one, else raw trees. The review records additive `reviewed_governed_identity`, and the approval record gains `governed_identity` (None for a candidate captured before governed identity existed). If the live snapshot fails, approval is also rejected ("Cannot verify the live candidate before approval: " + `gitsnap.failure_text(snap)`; that adds the guidance sentence for `git_permission_denied`).
  - **Findings are always accepted**, flagged `candidate_changed` / `live_snapshot_ok`, so the loop can never deadlock in review.
- **Executive summary:** in a flagged session `_summary_or_raise(text, "Review")` runs after the Reviewed-Candidate guard and before the snapshot, on the participant text (before the CLI appends Reviewed Candidate). `base_event` carries `executive_summary`, so all four outcomes (`checkpoint_approved`, `implementation_approved`, `revision_requested`, `max_rounds_exceeded`) carry the Reviewer's own text.
- **Artifact:** it must be UTF-8 and must not author `## Reviewed Candidate`. The CLI appends that section (verdict, reviewed tree / HEAD, round, live-unchanged) to `findings.round-N.md` / `findings.current.md`.
- **Records:** the review is stored on the generation (`generation.review`, with `generation` and, for declared loops, `checkpoint: {id, index, count, title, base_tree}`). The approval is stored as `{tree, head, round, generation, ts}` via `advance_implementation_reviewed()`.
- **Naming (all coding loops):** the review writes `findings.round-<g>.md`, where `g = len(generations) - 1` is the generation it reviews (always the latest), never `status.round`.
- **Reviewed Candidate (declared loops only):** gains Checkpoint, checkpoint base tree and Generation rows. Legacy output is unchanged.
- **Events** carry `generation`. Declared loops add `checkpoint_id`, and `findings_round` on findings:
  - `implementation_approved` (terminal);
  - `checkpoint_approved` (**non-terminal**: non-final approval, with `accepted_tree` and `next_checkpoint_id`);
  - `max_rounds_exceeded`;
  - `revision_requested` (notes a changed candidate).
! Deliberate refinement of the approved plan's "a mismatch rejects the review": only APPROVE is blocked. Findings about the submitted (immutable) tree stay valid, and blocking them would leave no legal actor in `implementation_review`.

### handle_extend(token, rounds, message, loop_dir=None)
File: `src/gator_command/scripts/loop/submit.py`
Architect command: the session transaction for continuing a loop that ended at its round limit. Before the lock: `message` required (blank/whitespace -> `ValueError`, stored stripped), `validate_round_count(rounds)` (1..20), `resolve_token()`, non-architect -> `PermissionError`. Inside `with_session_lock`: `validate_action(session, "architect", "extend")` (wrong stage -> `PermissionError`), `advance_extended()` with the stored `turn_timeout_seconds`, `append_turn(architect, "extend", message)`, and one `loop_extended` event `{role: architect, round, rounds_added, previous_max_rounds, max_rounds, stage, next_role, reason, detail}`. Returns `(loop_id, loop_dir, previous_max_rounds, new_max_rounds)`.
Filesystem: session mutation + one event (inside the session lock)
<- `host.extend_loop()`
-> `validate_round_count()`, `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_extended()`, `append_turn()`
! Transaction only. It does NOT take `start.lock`, scan for other active loops, or attach a watcher — callers must go through `host.extend_loop()` so the single-active-loop guarantee holds. Every rejection leaves `session.json` and `events.jsonl` byte-identical.

### handle_pause(token, message)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Pauses a running loop from any active state. Saves resume state. Distinct from model escalation (`paused_by_architect` vs `blocked_on_architect`). The message is stored as `status.pause_reason`, never as `architect_message`.
Filesystem: none (session mutation only)
<- `cli._cmd_pause()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_paused_by_architect()`, `append_turn()`

### handle_interject(token, message)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Injects guidance without pausing. It stores the message in `architect_message`, addressed to the current turn owner, with no state change and no deadline change. The recipient's next submission clears it.
Filesystem: none (session mutation only)
<- `cli._cmd_interject()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_interjected()`, `append_turn()`

### handle_end(token, reason)
File: `src/gator_command/scripts/loop/submit.py`
Architect command. Terminates the loop prematurely from any non-terminal state and sets the `ended_by_architect` terminal state.
- **Pending request:** a request still pending at end is resolved as `response = {message: reason, artifact_path: null, kind: CANCELLED_BY_END ("cancelled_by_end"), ts}`, and the event gains additive `decision_id`.
- **Suspended loop:** ending a suspended loop clears its suspension fields.
Filesystem: none (session mutation only)
<- `cli._cmd_end()`
-> `resolve_token()`, `with_session_lock()`, `validate_action()`, `advance_ended_by_architect()`, `append_turn()`

### main(argv)
File: `src/gator_command/scripts/loop/cli.py`
Argparse dispatcher for 17 subcommands: start, status, submit-draft, submit-implementation, submit-review, escalate, pause, interject, end, unblock, extend, reopen, wait, participant, tail, codex, list. `codex` routes to `_cmd_codex`, which lazily imports `codex_launcher.main` and exits with its code; it has no token argument.
Filesystem: none (delegates to handlers)
<- `gator-loop.py`

### _cmd_status(args)
File: `src/gator_command/scripts/loop/cli.py`
Read-only status display. Role-aware: model view (exit codes 0/1/2, shows `architect_message` and `architect_response_artifact` when set) vs architect supervisor view (exit codes 0/2, shows active role + join states + available commands + pending decisions).

**Participant exit contract.**
- **Exit codes:** model `status` exits `2` **only when terminal**. A paused or blocked loop exits `1` (nobody's turn: keep waiting).
- **Text:** `_print_suspension` prints either "Architect hold -- the Architect paused the loop" plus `Reason:`, or "Awaiting Architect decision decision-N (requested by <role>)". It then prints `Resumes with: <role> (<stage>)`, "This is not the end of the loop. You are still a loop participant." and the bounded `wait` command.
- **JSON:** model and Architect JSON gain additive `suspension` (`_suspension_view`): `{kind: architect_hold|architect_decision, resume_stage, resume_role, since, reason (hold only), decision_id / requested_by (decision only)}`, or null when not suspended.
- **Architect view:** the paused text adds `Preserved:`, `Since:` and `Hold reason:`. Architect exit codes are unchanged. Both text and JSON output include `architect_response_artifact` (absolute loop path or null).
Filesystem: `session.json` (R), `.tokens.json` (R via resolve_token)
<- `main()`
-> `resolve_token()`, `load_session()`
! **Recipient-scoped message (`_message_for_role` / `_print_architect_message` / `_message_json`):**
  - **Who sees it:** model status and wait show `architect_message` / `architect_response_artifact` only to their recipient, **whether or not it is that role's turn**. An unscoped legacy message keeps the old rule (turn owner only). JSON keys are unchanged; their value is null for a non-recipient.
  - **Text:** the protocol-documented `Architect message:` line is kept. Continuation lines of a multi-line message are indented four spaces.
  - **Decision label:** a line `Architect response to your escalation: decision-N` comes first only when the stored message carries `architect_message_decision`. It is never inferred from turns or `decisions[-1]`.
! JSON output includes `"schema": "gator-loop-status-v1"`. Architect JSON includes `turns`, join states, `decisions`, and `pending_decisions` (entries where `response` is null). Architect text status shows pending decision ID, reason, and artifact path when blocked. Architect never gets exit code 1 (always authorized to act on active loops).
! **Participant time silence:** for `attention_mode` loops the model status JSON and wait JSON omit `turn_timeout_seconds` / `turn_deadline` (`_strip_participant_time`), and `_print_turn_window(session)` prints nothing, so participants see no interval, deadline or countdown.
! **Attention mode, Architect view:**
  - JSON gains additive `attention: {interval_seconds, turn_started_at, elapsed_seconds, notified_turn, notified, due}` (`_attention_view`).
  - The active text view prints `Attention interval: N min (Architect notice only)`, `Elapsed this turn`, and either "Attention: due (notice recorded)…no action is required" or "interval passed; no notice recorded yet (is a loop host running?)".
  - The paused view shows the attention interval and omits every `--timeout` hint.
  - Unblock, extend and reopen output use `_print_window_line`.
  - The host-attach wording comes from `_host_duty(loop_dir)`: "records attention notices" for flagged loops, legacy wording unchanged.
  - `start --attention-interval` (preferred) and `--turn-timeout` share `dest=turn_timeout` (default 300). The host banner prints "Attention interval: … (Architect notice only)".
! **Checkpoint counters (`_print_counters`, `_checkpoints_json`).**
  - **Text:** for a declared checkpoint loop, status (model and Architect) and wait print `Checkpoint: K of N -- <title> (findings round r of b)` and `Generation: g` (or `none yet`) **instead of** `Round: X/Y`. Implicit and checkpoint-less loops keep `Round: X/Y`.
  - **JSON:** gains additive `checkpoint`, `checkpoints` (`id/index/title/state`, never scope or verify) and `generation`. `round` and `max_rounds` stay for compatibility and are informational.
  - **`list`:** the text Round column shows `cp K/N findings r/b`; JSON items gain `checkpoint_summary`.
  - **Terminal reason:** a checkpoint loop at `max_rounds_exceeded` shows "Findings budget exceeded for checkpoint cpK (r of b)".
! Legacy turn window: model and architect JSON (and wait JSON) carry additive `turn_timeout_seconds` + `turn_deadline`; the acting model's text view prints `Turn window: Ns (deadline ...)` via `_print_turn_window()`. The paused architect view prints the current window and, when a decision is pending, states that a response is required (with the exceptional `--no-response` form); an ordinary pause shows the optional-message form.

### _approval_resolution(session, loop_dir) / _print_approval_resolution(res, token=None)
File: `src/gator_command/scripts/loop/cli.py`
For an `implementation_approved` coding loop, `status` (model and Architect) and `wait` take a live snapshot, passing `approved_head` = the approval's `head` (`None` for a non-dict approval), and print the `resolve_approval()` result as text plus a marker:
- `[OK] COMMITTED -- handoff complete (commit <oid>)`;
- `[..] PENDING COMMIT -- return to the Draftor session for one normal commit`;
- `[!!] STALE -- <reason>` (text from `_STALE_REASONS`, which `views/loop.js` `STALE_REASON_TEXT` mirrors word for word; an unmapped reason prints raw);
- `[??] UNKNOWN -- never treat this as approved`, plus one indented line with `gitsnap.error_guidance(reason)` when that returns text (`git_permission_denied`). JSON is unchanged; its `reason` already carries the code.

The Architect view adds the `gator loop reopen` hint for stale or unknown. JSON gains additive `approval_resolution` (and `mode` on the Architect view). `submit-review` for coding prints the approved tree and the one-normal-commit handoff, or the reviewed tree plus a resubmit note when the candidate changed.

### _cmd_submit_implementation(args)
File: `src/gator_command/scripts/loop/cli.py`
`gator loop submit-implementation --token <draftor> [--checkpoint <id>] --file <implementation.md>` (`--checkpoint` is passed to the handler).
- For a declared checkpoint loop, success prints "Checkpoint cpK submitted (generation g)", the checkpoint changed-path count (plus the revisited count) and the cumulative count. Otherwise:
- On success it prints the round, the full candidate staged-tree OID, the changed-path count, a WARNING line only for residue outside `.gator/loops/`, a loop-residue count line, and the artifact path.
- `PermissionError` prints `Rejected:` and exits 1; `ValueError` / `FileNotFoundError` print `Error:` and exit 1.
- The Reviewer's coding status prints the latest generation's candidate tree and `git diff <base_tree> <staged_tree>`.
- **Declared checkpoint loops (`_print_checkpoint_action_prompt`):**
  - The **Draftor** sees "Implement checkpoint K of N -- title", the Scope, Verify and checkpoint base tree, the "stage only this checkpoint" rule, and the submit command with `--checkpoint <id>`.
  - The **Reviewer** sees "Review real code changed for checkpoint K of N -- title (generation g)", `git diff <checkpoint base> <staged>`, and either "does NOT authorize a commit" (non-final) or the final-checkpoint commit note.
  - **`submit-review`** prints "Checkpoint cpK approved; the Draftor continues with cpK+1. No commit yet." on a non-final approval, and the checkpoint findings round on findings.
  - CLI error and guidance text stays ASCII (`--`), because Windows pipes are cp1252.

### _cmd_reopen(args) / _attach_foreground_watcher(loop_host, loop_dir, what)
File: `src/gator_command/scripts/loop/cli.py`
`gator loop reopen --token <architect> --message "..."` calls `host.reopen_loop()`; on success it prints the resumed stage, the approval invalidation, the window line (`_print_window_line`: "Attention interval: … (Architect notice only)" for attention-mode loops; "Turn window: Ns" for legacy) and the re-engagement notice. `_attach_foreground_watcher` is the host contract shared with `extend`:
- `attached`: foreground `watch_loop()`;
- `already_hosted`: exit 0;
- `failed`: exit 1. Stderr says the <reopen|extension> is saved, but "attention notices are NOT being recorded" (attention-mode) or "turn timeouts are NOT being enforced" (legacy). The wording comes from `_host_duty(loop_dir)`, as do the already-hosted and Ctrl+C messages.

### _cmd_start(args) / _mode_of(session) / _print_coding_action_prompt(...)
File: `src/gator_command/scripts/loop/cli.py`
- **`start --plan-file PATH`** (`dest=plan_path`): planning only; `--sketch` becomes optional with it.
- **`start --revise-from LOOP_ID`** (`dest=revise_from`): planning only; requires `--sketch` and cannot be combined with `--plan-file`.
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
- `start --mode planning|coding [--from-loop ID] [--sketch PATH] [--brief FILE] [--source-brief keep|drop]`: planning requires `--sketch`; coding requires `--from-loop`. `--brief` is optional in both modes. `--source-brief` is coding-only (exit 1 on planning) and defaults to keep. Argument errors and `RuntimeError` exit 1 with `Error:`.
- Status JSON gains additive `mode` (normalized). Coding text status prints `Mode: coding` and a coding action prompt (approved plan path, `submit-implementation`, review the STAGED tree).
- **Architect brief lines:** `_brief_entries` / `_print_briefs` / `_briefs_json` cover the model and Architect views.
  - Each non-absent position prints a labeled FIXED path plus a marker: `[OK] (required reading)`, `[!!] MISSING`, `[!!] DIGEST MISMATCH`, `[!!] UNREADABLE`, `[!!] INVALID REFERENCE` or `[!!] UNSAFE PATH`. A failed brief adds "do not rely on it", and model roles are also told to escalate.
  - A dropped planning brief prints "Planning brief: not carried forward (Architect's choice at coding start)".
  - `absent` prints nothing, so no-brief loops keep their exact text output.
  - JSON gains `brief` / `source_brief` (`{path, check}`) and `source_brief_decision` only when present.
- Terminal text for `implementation_approved` gives the one-normal-commit handoff.

### _cmd_extend(args) / _round_count_arg(value)
File: `src/gator_command/scripts/loop/cli.py`
Architect `gator loop extend --token --rounds <1-20> --message "..."`. `--rounds` and `--message` are required; `--rounds` uses argparse type `_round_count_arg` -> `session.validate_round_count()` (usage error exit 2 before any write). Calls `host.extend_loop()`; `PermissionError` -> `Rejected:` exit 1, `RuntimeError`/`ValueError`/`FileNotFoundError` -> `Error:` exit 1 (no host step). On success prints old -> new ceiling, resumed stage/role, the window line (attention interval for attention-mode loops; turn window for legacy), and a participant re-engagement notice, then applies the host contract via `host.acquire_host_lock_with_retry()`: `attached` -> foreground `watch_loop()` (Ctrl+C prints that attention recording or, for legacy, timeout enforcement stopped; fd released in `finally`); `already_hosted` -> prints holder detail, exit 0; `failed` -> stderr says the extension is saved but attention notices are not recorded (legacy: timeouts not enforced), exit 1.
<- `main()`
-> `host.extend_loop()`, `host.acquire_host_lock_with_retry()`, `host.watch_loop()`, `host.release_host_lock()`, `session.load_session()`
! Always attaches (no state-only `--no-watch` form): a state-only extension would leave a live-but-unhosted loop with no recovery command, because `extend` rejects once the stage is `plan_revision`.
! Architect status for a `max_rounds_exceeded` loop prints the `extend` command hint; `start`'s banner lists it too.

### _cmd_unblock(args) / _turn_timeout_arg(value)
File: `src/gator_command/scripts/loop/cli.py`
Architect unblock. Forwards `--message`, `--file`, `--timeout` (argparse type `_turn_timeout_arg` → `session.validate_turn_timeout()`, so bad values are usage errors before any write; **legacy loops only**: attention-mode loops refuse it in `handle_unblock`, exit 1 with `Error:`), and `--no-response` to `submit.handle_unblock()`. It prints the resumed stage and the window line (attention interval for attention-mode loops; effective turn window for legacy). `ValueError`/`FileNotFoundError` exit 1 with `Error:`; `PermissionError` exits 1 with `Rejected:`.
<- `main()`
-> `submit.handle_unblock()`, `session.load_session()`

### _cmd_wait(args)
File: `src/gator_command/scripts/loop/cli.py`
Model-role wait. Resolves the token, then calls `_wait_for_actionable()` and renders status-shaped output. Exit codes: `0` actionable, `2` terminal (and invalid token or invalid `--max-seconds`), `3` (`WAIT_EXIT_STILL_WAITING`) bounded deadline passed while another role owns the turn **or the loop is paused/blocked (a suspension never ends a wait)**. Architect token exits 1. JSON carries `suspension`; suspended still-waiting text prints the hold/decision and the reissue command.
Filesystem: `session.json` (R), `.tokens.json` (R via resolve_token)
<- `main()`
-> `resolve_token()`, `_wait_for_actionable()`, `_print_action_prompt()`, `_positive_seconds()`
! `--max-seconds` omitted = unbounded (human CLI compatibility). Participant surfaces teach the bounded form `--max-seconds 360` as a default (`wait` polls every `--poll` 2 s and returns at once when the turn arrives, so a longer bound only cuts reissues; the protocol tells runtimes to set a tool-call limit above the interval) (watcher default 600); an interval the Architect gives the participant wins (protocol "Precedence"); exit 3 means "reissue the same command", never "leave the loop". Text output prints the exact reissue command; JSON (`gator-loop-status-v1`, additive) adds `wake_reason: "still_waiting"`, `max_seconds`, `waited_seconds`, `reissue_command`. **Legacy loops only:** it also adds `turn_timeout_seconds` / `turn_deadline`, and actionable text output prints the turn window like `status`. Attention-mode loops omit both fields and print no window (`_strip_participant_time`, `_print_turn_window(session)`). `--max-seconds` is the command's own bounded wait, not a loop deadline.

### _wait_for_actionable(loop_dir, role, poll_interval, load_session, is_terminal, is_paused, max_seconds=None, clock=None, sleep=None)
File: `src/gator_command/scripts/loop/cli.py`
Polls until terminal / this role's turn. Returns `(session, wake_reason)` with wake_reason `terminal`, `already_your_turn`, `became_your_turn`, or `still_waiting` (bounded only). `paused` is not a wake reason; a suspended loop keeps the wait going (unbounded waits wait through it). The `is_paused` parameter is kept for call-site compatibility only.
Filesystem: `session.json` (R)
<- `_cmd_wait()`
! Read-only — never writes session or events. Bounded mode uses a monotonic deadline and caps each sleep at the remaining time, so it cannot overrun by a full poll interval; the session is re-read after the final sleep, so a turn change at the deadline still wins over `still_waiting`. `clock`/`sleep` are injectable test seams.

### _cmd_participant_watch(args) / _cmd_participant_status(args) / _render_participant(payload, as_json)
File: `src/gator_command/scripts/loop/cli.py`
`gator loop participant watch --token T --max-seconds N [--poll-seconds S] [--adapter-label L] [--json]` and `gator loop participant status --token T [--json]`. `--max-seconds` is required. `--json` prints exactly one compact JSON line on stdout (the adapter reads the last JSON line of its output file) and nothing on stderr for normal outcomes. SIGTERM is mapped to KeyboardInterrupt so it releases like Ctrl+C. Output never contains the token or registration id.

### snapshot(worktree_root, base_head=None, approved_head=None)
File: `src/gator_command/scripts/loop/gitsnap.py`
Returns `{"schema": "gator-loop-gitsnap-v1", "ok": True, worktree_root, current_head, head_tree, detached, branch, staged_tree, governed_index_identity, base_head, base_tree, changed_paths[{status, path[, old_path]}], changed_truncated, unstaged_paths, unstaged_truncated[, approval_history]}`, or `{"ok": False, "error", "detail"}` and never raises for Git conditions.

| Field | Source command |
|---|---|
| `worktree_root` | `rev-parse --show-toplevel` (works for linked worktrees; the per-worktree index is used) |
| `current_head` | `rev-parse --verify HEAD^{commit}` |
| `head_tree` | `rev-parse HEAD^{tree}` |
| `detached` / `branch` | `symbolic-ref -q HEAD` |
| `staged_tree` | `write-tree` |
| `governed_index_identity` | `_governed_index_identity()`: `ls-files --stage -z` → `_governed_digest()`; None on any failure |
| `base_tree` | `rev-parse <base>^{tree}`, with `base_head` normalized to a full OID |
| `changed_paths` | `diff --cached --name-status -z -M <base or HEAD>` |
| `unstaged_paths` | the union of `diff --name-only -z` and `ls-files --others --exclude-standard -z` (gitignored files are not residue) |
| `approval_history` (only when `approved_head` is given) | `_approval_history(root, approved, current_head)`: `rev-parse --verify -q A^{commit}`, `merge-base --is-ancestor A H`, `rev-list --first-parent A..H` (oldest line = successor L), `rev-parse --verify -q L^1`, `rev-parse L^{tree}` |

Error codes:
- `git_unavailable` — reserved for failure to execute Git itself;
- `not_a_repo` — not a repository, a missing path, or a non-directory input (rejected before any Git invocation). A launch failure caused by a bad cwd is classified as `not_a_repo`; any other OS-level launch failure is `git_error`;
- `bare` — a bare repository;
- `unborn` — HEAD has no commit;
- `conflict` — unmerged index entries, checked before `write-tree`;
- `bad_base` — the base commit cannot be resolved;
- `git_permission_denied` — the host denied Git write access on an index-touching snapshot command (`write-tree`, `diff --cached`, `diff --name-only`, the `retry_busy=True` calls): stderr matches a closed, case-insensitive `_PERMISSION_MARKERS` (`permission denied`, `access is denied`, `insufficient permission`). Checked before `_is_busy()` on the first result and on the retried result, so it is reported after exactly one invocation with no sleep, and a later permission failure is never `git_busy`;
- `git_busy` — real index-lock contention: a lock failure without a permission marker persists after one retry (0.2 s);
- `git_error` — anything else.

! The permission check runs only inside `_git(..., retry_busy=True)`. Read-only `rev-parse` / `ls-files` calls keep their own typed results, and a launch-time Python `PermissionError` in `_invoke()` stays `git_unavailable` / `not_a_repo`. No `EPERM` / "operation not permitted" matching (it can mean a non-sandbox ownership problem). A localized Git prints translated text and falls back to `git_busy` / `git_error`.

### error_guidance(code) / failure_text(snap)
File: `src/gator_command/scripts/loop/gitsnap.py`
The single source of each error code's participant-facing explanation. `ERROR_GUIDANCE` maps only `git_permission_denied` -> `PERMISSION_GUIDANCE` (the sandbox execution-permission sentence; it names no vendor). `error_guidance(code)` returns that text or None. `failure_text(snap)` returns `"<error> (<detail>)"`, plus `" -- " + guidance` only when guidance exists, so every other code's message is exactly `"<error> (<detail>)"`. Pure; display text only, never authority.

**`approval_history`** answers one question: what is the immediate first-parent successor of the approved HEAD A on the captured HEAD H's history? Shapes: `{ok: true, status: "same_head"}` (A == H, no Git call); `{ok: true, status: "successor", commit, tree, governed_tree_identity}` (the last from `_governed_tree_identity()`: `ls-tree -r -z --full-tree L` → `_governed_digest()`, None on failure); `{ok: true, status: "diverged", why}` with `why` = `head_missing` (A is not a full lowercase hex OID, or `rev-parse --verify -q` exit 1 with empty stderr), `not_ancestor` (`merge-base --is-ancestor` exit 1), or `not_first_parent` (L's first parent is not A: A came in only through a merge's second parent); or `{ok: false, error, detail}`. It is computed from the snapshot's own `current_head`, so HEAD and history are one observation. Policy (detached, tree match) belongs to `resolve_approval()`, not here.
! Only those two exact exit-1 cases are divergence evidence. Every other non-zero exit (for example 128 `fatal:`), an empty range or a launch failure is `_GitError` -> `{ok: false}`, which resolves `unknown`, never stale or approved. A history failure never fails the snapshot: `snapshot.ok` stays true so the other live facts remain usable.
! A is validated against `_OID_RE` before any Git call, so a session value can never become a Git option. The history probe is pure object-database reads and writes nothing (unlike `write-tree`). `rev-list` output is bounded by the commits since approval, and the `--is-ancestor` pre-check prevents a walk over unrelated history.

Path lists are capped at `MAX_PATHS` (1000), with truncation counts; the staged-tree OID, not the list, is the binding. `_run` is the test seam.
Filesystem: Git object database (W — tree objects written by `write-tree`, unreferenced until a commit; reclaimed by `git gc`). Refs, index, and worktree are never modified (pinned).
! Facts are RAW. Never filter or normalize paths (for example hook-managed `.gator/` files) out of `staged_tree`, `head_tree`, `base_tree`, the path lists or the history `tree`. The raw staged tree stays the review authority (the review diff, Commit State, checkpoint bases, "nothing staged").
! **The one derived value:** `_governed_digest(entries)` = `gov1:` + SHA-256 over `mode SP oid SP path NUL` for every entry sorted by path bytes, skipping `GOVERNED_EXCLUDED_PATHS`. That set equals `precommit_override.HOOK_MANAGED_PATHS` (pinned by `TestGovernedIdentity` in `tests/test_loop_gitsnap.py`). Index and tree produce the same value for the same content (pinned with an `a-b` / `a/c` ordering case). Only approval comparison (`same_governed()`) reads it; it is never a review command or a replacement for `staged_tree`.

### diff_trees(worktree_root, from_tree, to_tree)
File: `src/gator_command/scripts/loop/gitsnap.py`
`git diff-tree -r -z -M --name-status <from> <to>`. It returns `{"ok": True, changed_paths, changed_truncated}` (the same record shape and `MAX_PATHS` cap as `snapshot`) or `{"ok": False, error, detail}`, and never raises for Git conditions.
Filesystem: Git object database (R only). It takes no index lock and never touches refs, the index or the worktree (pinned).
<- `submit.handle_submit_implementation()` (the checkpoint diff and revisit disclosure)

---

## TRIPWIRE: Validated Bytes Are Persisted Bytes

For context-evidence, coding-checkpoint and executive-summary sessions, `handle_submit_draft` persists exactly the buffer it validated inside the session lock; a flagged planning `handle_submit_review` does the same, so a Timeline summary always matches its stored artifact. Never re-read the source path or `copy2` it after validation, and never make the preflight authoritative. Only `contract.context_evidence` / `contract.coding_checkpoints` / `contract.executive_summary` gate enforcement. Never infer it from dates, mode strings, or the presence of a brief: legacy sessions must keep accepting old plans.

Violation: a validate-then-copy-path sequence lets a file swapped between check and write land unvalidated. That is pinned by `TestSwapRace`, which fails under that mutation. Dropping the in-lock check fails `test_in_lock_check_is_authoritative`; for checkpoints, `test_in_lock_gate_is_authoritative` pins the same rule; for planning reviews, `test_planning_review_persists_captured_bytes` (`tests/test_loop_executive_summary.py`).

## TRIPWIRE: Raw Staged Tree Is Review Authority (coding mode)

In coding-mode loops the reviewed candidate is the raw `git write-tree` OID captured by `gitsnap.snapshot()` — never artifact prose and never a filtered or normalized tree. Implementation artifacts describe the candidate; the CLI writes their `## Commit State` facts from the snapshot, and the Reviewer diffs raw trees.

**Approval comparison is governed.** Whether the live index or the first commit after approval still *is* the approved candidate is decided by `state_machine.same_governed()`: the named `governed_index_identity` / `governed_tree_identity` when both sides carry one, else the raw tree. The only paths it ignores are the hook-owned files (`GOVERNED_EXCLUDED_PATHS`), which the commit hook writes or resets and the user never authors as part of the change. Raw trees remain recorded on every snapshot, review and approval.

Violation: approving from prose, or from a tree filtered beyond the hook-owned set, lets a commit land that differs from what the Reviewer inspected. Widening `GOVERNED_EXCLUDED_PATHS` beyond `HOOK_MANAGED_PATHS` is such a violation.

## TRIPWIRE: Coding Artifacts Are Named by Generation

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

## Cross-Vendor Orientation

Models join a loop from a pasted join prompt. Gator's vendor-neutral entry document is `GATOR_INIT.md` (named by `gator init`). Its "Joining a loop" section points to the protocol and `gator loop status` and restates none of the rules. Gator never writes `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`; older repos may still carry a frozen, unrefreshed block there. The `/loop-join` slash command is retired (2026-11-11, with all Gator slash commands): the join prompt plus `GATOR_INIT.md` and the protocol are the only join path, in every AI tool. Its only unique guidance (in Claude Code, prefer the watcher while the session stays open, and end the turn after launching it) moved into the protocol's Step 1. The behavioral protocol is at `procedures/gator-loop-protocol.md`. Artifact format templates are at `reference-notes/loop-artifact-formats.md`. Both files exist as byte-identical pairs between `.gator/.includes/` and `src/.../templates/gator-starter/`; change both copies in the same commit. The participant watcher receiver contract is at `reference-notes/loop-participant-watcher.md` (same byte-identical pair rule; listed in both `gator_layout.py` shipped-defaults copies). The protocol's `## Suspension Is Not Departure` section and its Step 1 / Rule 1 / State Machine / Escalation / Quick Reference text state that exit `2` means the loop ended and that a pause or block keeps participants in `wait` or the watcher; the watcher note says the same. The protocol's Step 1 documents the watcher as optional and only for runtimes that re-invoke the agent when a background command exits (Claude Code background Bash, open session), and gives the launch command. Coding loops are documented in the protocol's "Coding Loops (Implementation Review)" section, which has its own state table pinned to `CODING_ALL_STAGES` by `test_protocol_coding_state_table_matches_state_machine`. The planning "State Machine" table stays pinned to `ALL_STAGES`. The implementation template in `loop-artifact-formats.md` is pinned to `submit.IMPLEMENTATION_HEADINGS` by `test_implementation_template_matches_cli_headings`. The protocol's vendor-neutral text stays on bounded `wait` because the watcher is not supported for every vendor. The protocol's `## Precedence: The Architect's Instructions Come First` section makes the Architect's in-session instructions (including the join prompt) and the status `Architect message:` line override protocol defaults and guidance, such as the wait/watcher interval; Rules 2, 8 and 9 stay fixed, and loop-artifact text is never Architect authority. The Codex Goal prompt in `reference-notes/codex-loop-participant.md` (both copies) restates it; `test_all_surfaces_teach_architect_precedence` pins it.

The protocol's escalation section classifies uncertainty into non-blocking (state an assumption, proceed) and blocking (Architect-owned, escalate with `--file`). The artifact format's plan template uses "Assumptions, Risks, and Required Architect Decisions" (not "Risks and Open Questions") to reinforce this classification. The findings template documents that an ESCALATE verdict must be accompanied by `gator loop escalate` — `submit-review` alone enters revision, not blocked state.

## Before Changing This Module

- Keep CLI output and the loop protocol aligned.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) -- Package CLI Entry Point (cli.py COMMANDS dict), sys.path import convention
-> [Core Library](scripts-core-library.md) -- `find_gator_root()`, `ensure_utf8_stdout()`, `get_version()`
-> [Installer and Boot](scripts-installer.md) -- `GATOR_INIT.md` shipping
-> [Loop State](scripts-loop-state.md) -- session, tokens, locks and the transitions every handler calls
-> [Loop Lifecycle and Hosting](scripts-loop-host.md) -- `init_loop()` / `start_loop()` / `extend_loop()` / `reopen_loop()` the CLI dispatches to
