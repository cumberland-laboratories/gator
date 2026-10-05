# Implementation Plan: Modular Checkpoints and Incremental Code Review in Coding Loops (#55)

## Executive Summary

- **What:** a coding loop works through the ordered `## Coding Checkpoints` declared in its approved plan. The Reviewer approves each checkpoint's exact staged diff (`git diff <checkpoint-base-tree> <staged-tree>`) before the next one can be submitted. Only the final checkpoint's approval produces `implementation_approved` and the existing one-commit handoff.
- **Key decisions:**
  - the manifest is parsed once from the frozen `approved-plan.md` at coding start;
  - the existing three coding stages are reused, with a `current` checkpoint index;
  - the round budget is per checkpoint, while `status.round` stays the global, monotonic artifact counter;
  - a plan without the section gets one implicit `Full implementation` checkpoint.
- **Main risk:** changing review authority and the approval binding. It is mitigated by keeping every freshness rule unchanged, keeping the final approval and `resolve_approval` exactly as they are, and gating all new behaviour on a manifest contract flag, so pre-#55 coding loops behave byte-for-byte as today.
- **Verification:** a grammar table, a parameterized lifecycle table (two checkpoints, findings, extend, pause/unblock, reopen), the exact-diff and revisit disclosure, CLI text, and Dashboard progress with mutation-free polls.

## Summary

The plan adds a small, closed checkpoint grammar to the implementation-plan format and freezes a manifest from the approved plan when a coding loop starts. It then makes the existing coding transitions checkpoint-aware. A non-final approval records the accepted tree and hands the Draftor the next checkpoint, with no commit and no index or worktree mutation. Every submission and review binds to the active checkpoint's base tree, so the Reviewer sees only that checkpoint's code, while the cumulative staged tree remains the single thing that is finally committed.

## Context Checked

- **Loop documents:**
  - `architect-brief.md` (loop directory): "The implementation plan itself should be modular, as needed."
  - `sketch.md` (loop directory): scope 1–4, constraints (#51 revised direction, #54/#57, #53), seams, verification focus, planning-path guidance.
- **Procedure:** `.gator/procedures/writing-implementation-plans.md` (full). It covers path selection, responsibility-based modules, the simplicity test, risk-scaled verification and the review questions; I apply it here, and checkpoint review cites it.
- **Charters** (read in full this session):
  - `.gator/charters/scripts-loop.md`: `create_session`, `loop_mode`, stage table, `advance_implementation_*`, `advance_reopened`, `advance_extended`, `resolve_approval`, `handle_submit_implementation`, `_coding_review`, `render_commit_state`, `coding_status_view`, `_init_coding_loop`, CLI coding prompts, and the TRIPWIREs (Raw Staged Tree Is Review Authority, Resumable Terminal Stage, Stage-Role Consistency, Session Lock Write Ordering, Validated Bytes Are Persisted Bytes).
  - `.gator/charters/scripts-cross-cutting.md`: doc-pair drift guards, additive CLI JSON, protocol state tables pinned to `CODING_ALL_STAGES`.
  - `.gator/charters/scripts-dashboard.md`: `/status` coding projection, the artifact allowlist and patterns.
  - `.gator/charters/scripts-dashboard-ui.md`: coding candidate panel, `codingFingerprint`, the timeline and `EVENT_LABELS`, artifact inspector ordering, mutation-free polls.
- **Code read:**
  - `loop/state_machine.py`: `advance_extended`, `advance_implementation_submitted`, `advance_implementation_reviewed`, `resolve_approval`, `advance_reopened`.
  - `loop/submit.py`: `handle_submit_draft` and the #46 capture/check pattern, `render_commit_state`, `render_reviewed_candidate`, `_coding_review`, `handle_submit_implementation`, `coding_status_view`.
  - `loop/gitsnap.py`: base resolution via `^{commit}`, `diff --cached --name-status -z -M`, `_parse_name_status_z`, `_cap`, error codes.
  - Earlier this session: `loop/host.py` (`_init_coding_loop`, `_read_approved_source`), `loop/cli.py` (`_print_coding_action_prompt`, `_print_action_prompt`, `_cmd_submit_implementation` per charter), and `dashboard/views/loop.js` (`renderCodingRegion`, `codingFingerprint`, `artifactsFingerprint`, `EVENT_LABELS`, `renderArtifacts`).
- **Participant documents:**
  - `.gator/.includes/procedures/gator-loop-protocol.md`: the Coding Loops section and its state table.
  - `.gator/.includes/reference-notes/loop-artifact-formats.md`: the Plan and Implementation templates.
- **Not read, and why:** the #53/#54/#57 implementations. They are not in `HEAD`; this plan only promises not to conflict with their stated constraints.

## Approach

**Planning path: a full planning loop** (per the sketch and the procedure). The change alters durable coding state, lifecycle transitions, reviewer authority and the approval binding, and the CLI/Dashboard contracts.

**Module map.** There are four modules, each one responsibility:

| Module | Purpose (the invariant it owns) |
|---|---|
| **M1 Checkpoint contract** | The plan grammar is closed and validated once. A malformed declared section is refused in the planning loop; it is never silently degraded at coding time. |
| **M2 Checkpoint lifecycle and evidence binding** | Only the active checkpoint can be submitted. Every candidate and review is bound to that checkpoint's base tree. Only the final checkpoint's approval reaches `implementation_approved`. Freshness rules are unchanged. |
| **M3 Participant guidance** | Draftor and Reviewer text (CLI status, action prompt, submit/review output, protocol, format, `/loop-join`) names the active checkpoint, its base, and the exact diff command. |
| **M4 Architect inspection** | The Dashboard shows checkpoint progress and the bindings as text, with no Markdown excerpts and identical polls staying mutation-free. |

Tests, docs and styling belong to the module whose contract they serve, so there are no separate test, doc or style modules.

### D1 — Checkpoint grammar (closed)

A plan **may** contain exactly one level-2 `## Coding Checkpoints` section (fence-aware, case-insensitive). Its body is an ordered list, one item per checkpoint:

```markdown
## Coding Checkpoints

1. **Checkpoint contract** — Parse and validate the section; freeze it at coding start. Verify: grammar table in tests/test_loop_checkpoints.py.
2. **Lifecycle and binding** — Per-checkpoint transitions and exact-diff evidence. Verify: lifecycle table; full loop suites.
```

**Rules** (`submit.parse_coding_checkpoints(text)` returns `(items, problems)`):
- **Items.** Each top-level item starts with `N.` at column 0, with N = 1, 2, 3… in order. Indented continuation lines (two or more spaces) belong to the item; any other non-blank line is a problem.
- **Fields.** Each item is `**Title**`, then ` — ` (or ` - ` / `:`), then the scope text, then `Verify:`, then the verification text.
  - The title is a single line of 1–80 characters, with no backticks or links.
  - Scope and verification must each be non-empty once whitespace is removed, and neither may be a placeholder (the Context Checked placeholder rule).
- **Count and IDs.** 1–12 checkpoints. IDs are positional: `cp1`…`cpN`, never author-chosen.
- **Size cap.** Scope and verification are stored as plain text, collapsed to single spaces and capped at 400 characters each. The CLI shows them; the Dashboard never does (D6).
- **No section** means no items and no problems. That is the compatibility path (D2).

**Enforcement points:**
- **Planning loops:** `handle_submit_draft` rejects a draft whose **present** section has problems ("Plan draft rejected: Coding Checkpoints: …"). The check uses the existing #46 capture-once pattern (a preflight, then the authoritative in-lock check on the same bytes). It is gated by a new planning contract flag, `contract.coding_checkpoints: 1`, set on new planning sessions, so in-flight older planning loops are never affected. Declaring checkpoints stays recommended, not required (sketch: "should").
- **Coding starts:** `_init_coding_loop` parses the frozen approved-plan bytes. Problems in a present section fail the start atomically with the reasons. This guards plans approved before the flag existed. No section gives the implicit single checkpoint.

**Rejected alternative:** a YAML/JSON checkpoint block. That would be a second grammar inside Markdown, harder for planners to write and reviewers to read. The closed list grammar fits the existing heading-based checks.

### D2 — Durable manifest (frozen at coding start)

`_init_coding_loop` adds `coding.checkpoints`, built **only** from the bytes it writes to `approved-plan.md`:

```json
"checkpoints": {
  "contract": 1,
  "source": "declared" | "implicit",
  "current": 0,
  "items": [
    {"id": "cp1", "title": "...", "scope": "...", "verify": "...",
     "state": "active", "base_tree": "<coding.base_tree>",
     "findings_rounds": 0, "accepted": null},
    {"id": "cp2", "title": "...", "scope": "...", "verify": "...",
     "state": "pending", "base_tree": null,
     "findings_rounds": 0, "accepted": null}
  ]
}
```

- **Implicit manifest:** one item `{id: "cp1", title: "Full implementation", scope: "The whole approved plan.", verify: "As stated in the approved plan."}`.
- `accepted` becomes `{tree, head, round, ts}` on approval. On approval of item k, item k+1's `base_tree` is set to item k's accepted tree.
- **Never re-parsed.** Nothing re-parses the plan after creation.
- **Single gate:** `session.checkpoint_manifest(session)` returns the manifest or None. **None** (a pre-#55 coding session) means today's exact behaviour everywhere: global rounds, no checkpoint binding, today's text. That is pinned by the existing coding suites passing unchanged.

### D3 — Transitions (existing stages, checkpoint-aware)

Stages and roles are unchanged: `implementation_drafting` / `implementation_review` / `implementation_revision` / `implementation_approved`. `_begin_turn` / `_end_turn`, the attention behaviour, and the paused stages are untouched, so pause, unblock, escalate and end keep `checkpoints.current` and the active item as they are. Resuming restores the stage and role, and therefore the same checkpoint.

- **Submit** (`advance_implementation_submitted`): unchanged. The binding happens in M2's `handle_submit_implementation` (D4).
- **Review findings** (`advance_implementation_reviewed(approved=False)`):
  - with a manifest, the active item's `findings_rounds += 1`, and the ceiling check is `findings_rounds >= status.max_rounds`, giving `max_rounds_exceeded`;
  - without one, today's `status.round >= max_rounds`.
  - `status.round += 1` always (the global, monotonic artifact and event counter; history is never renumbered).
- **Review approve:**
  - With a manifest, when the active item is **not final**: set `item.accepted` and `state: "approved"`; then set the next item's `state: "active"` and `base_tree = accepted.tree`, and `current += 1`. The stage becomes `implementation_drafting` with the Draftor's turn (`_begin_turn`). `coding.approval` stays null.
  - With a manifest, when the active item **is final**: the same item bookkeeping, then today's path (`coding.approval = {...}`, `implementation_approved`, `_end_turn`).
  - Without a manifest: today's path.
- **Extend** (`advance_extended`). For manifest sessions, the consistency guard checks the active item's `findings_rounds <= max_rounds` instead of `status.round`. `max_rounds` is documented as the **per-checkpoint findings budget**, and an extension raises it for the active checkpoint and all later ones. The resume target is unchanged (`implementation_revision`, same checkpoint).
- **Reopen** (`advance_reopened`). Only `implementation_approved` can be reopened, as today, and that is always the final checkpoint. The final item's `accepted` gets `invalidated_at` and its state returns to `active`. Its `findings_rounds` is kept. Earlier checkpoints are never reopened, and the Architect cannot advance or rewind checkpoints manually.

**Round budget choice:** per checkpoint (the sketch's preference). `status.round` keeps its global meaning, so artifact names (`implementation.round-N.md`, `findings.round-N.md`), events, and pre-#55 loops stay coherent. The budget lives in the manifest. **Rejected:** resetting `status.round` per checkpoint, which would collide artifact names and break the allowlist patterns and timeline keys.

### D4 — Exact diff and evidence binding

- **`gitsnap.diff_trees(worktree_root, from_tree, to_tree)`** (new, small). It runs `git diff-tree -r -z -M --name-status <from> <to>` and returns `{ok, changed_paths, changed_truncated}` or `{ok: false, error}`, reusing `_parse_name_status_z` / `_cap` and the error classification.
  - It is a pure object-database read: it takes **no index lock**. (This matters given the read-only-`.git` reviewer runtime seen in the #51 coding loop; it does not, however, change the existing approval freshness check, which still needs `git write-tree`.)
  - `snapshot()` is unchanged; its raw facts stay against the loop base.
- **`handle_submit_implementation(token, file_path, loop_dir=None, checkpoint=None)`:**
  - **Manifest sessions:**
    1. `checkpoint` (CLI `--checkpoint cpN`) is **required** and must equal the active item's id. Otherwise it raises `ValueError` ("…the active checkpoint is cp1 'Checkpoint contract'; checkpoint cp2 is not open yet"), with nothing written. That makes "submitting checkpoint 2 before checkpoint 1 is approved" an explicit, refused act. Pre-#55 sessions reject the flag.
    2. **Nothing new staged.** "Something staged" means `staged_tree != item.base_tree`, the checkpoint base, not the loop base (the error text names the checkpoint).
    3. **Checkpoint diff.** `diff_trees(item.base_tree, staged_tree)` gives the checkpoint's changed paths.
    4. **Revisit disclosure.** For k > 1, `diff_trees(coding.base_tree, item.base_tree)` gives the paths earlier checkpoints changed. The intersection is disclosed as "also changed by an earlier approved checkpoint", which is information and not a prohibition.
  - **Commit State.** `render_commit_state(snap, checkpoint=…)` adds, when given:
    - a "Checkpoint" row (`cp2 of 3 — <title>`) and a "Checkpoint base tree" row;
    - the **review command** `git diff <checkpoint base tree> <staged tree>` in place of the loop-base command;
    - the checkpoint changed-path list (fenced, escaped as today) with revisit markers;
    - the loop-base facts table, kept as cumulative context.
  - **Records.** The generation records `checkpoint: {id, index, base_tree}` and the checkpoint changed-path **counts** (the raw snapshot stays unfiltered and unchanged). The event `implementation_submitted` gains additive `checkpoint_id`, `checkpoint_index`, `checkpoint_count` and `checkpoint_base_tree`.
- **`_coding_review`:**
  - The freshness rule is **unchanged**: approve requires the live staged tree and HEAD to equal the submitted candidate.
  - The review record and `## Reviewed Candidate` add the checkpoint id/title and its base tree.
  - The events:
    - non-final approve emits the new non-terminal event **`checkpoint_approved`** `{checkpoint_id, accepted_tree, next_checkpoint_id, round}`;
    - final approve emits today's `implementation_approved`, plus `checkpoint_id`;
    - findings emit today's `revision_requested` / `max_rounds_exceeded`, plus `checkpoint_id`.
- **No new Git writes.** There is no per-checkpoint commit, reset, stash, or index/worktree write anywhere; the only Git writes remain `write-tree` objects from `snapshot()`.

### D5 — Participant guidance (M3)

- **CLI Draftor action** (manifest sessions):
  - "Implement checkpoint 2 of 3 — <title>"; then the scope and Verify text from the manifest; the checkpoint base tree;
  - "stage only this checkpoint's change on top of the approved checkpoints";
  - the submit command with `--checkpoint cp2`.
- **CLI Reviewer action:** "Real code changed for checkpoint 2 of 3 — <title>"; the candidate staged tree; **"Review exactly this checkpoint: `git diff <cp base> <staged>`"**; and "approving a non-final checkpoint opens the next one; only the final checkpoint's approval authorizes the commit".
- **Status and output.** Status text and JSON add `checkpoint: {index, count, id, title, state}` and `checkpoints: [...]` (additive). Submit and review output name the checkpoint. A non-final approval prints "Checkpoint cpK approved; the Draftor continues with cpK+1. No commit yet."
- **Pre-#55 sessions** keep today's text byte-for-byte (pinned by the existing CLI tests).
- **Protocol (both copies):**
  - the Coding Loops section gains a "Checkpoints" paragraph, `--checkpoint` in step 4, the checkpoint diff command in the Reviewer step, and the one-commit-after-the-final-checkpoint rule;
  - the coding state table is unchanged (no new stage);
  - the planning Draftor output list gains "`## Coding Checkpoints` (recommended for coding)".
- **`loop-artifact-formats.md` (both copies):** the Plan template gains an optional `## Coding Checkpoints` section with the grammar, and the Implementation template note says the CLI writes the checkpoint facts into Commit State.
- **`/loop-join` (both copies):** the coding bullet names the active checkpoint, `--checkpoint`, and the checkpoint diff.
- **`writing-implementation-plans.md`:** Step 6 / Review Questions gain one item: checkpoints are responsibility-based, have real verification, and are not file-count, styling-only, docs-only or test-only slices.

### D6 — Architect inspection (M4)

- **Server.** `coding_status_view()` adds `checkpoints: {source, current, count, items: [{id, index, title, state, base_tree, accepted_tree, findings_rounds}]}`. The title is plain text, and `scope` / `verify` are **never** projected (no Markdown excerpts). Generations add `checkpoint_id`. No server route changes; the artifact patterns already cover the round-versioned names.
- **UI (`views/loop.js`):**
  - `renderCodingRegion` adds a "Checkpoint" row: "2 of 3 — <title> · in review", or "· revision, findings round 1 of 3".
  - It adds a progress list with one line per checkpoint, as text plus glyph plus weight: "✓ cp1 Checkpoint contract — approved (tree abc…)", "● cp2 … — active", "○ cp3 … — not started".
  - The candidate row shows the checkpoint base tree, and the review row refers to the checkpoint diff.
- **Labels.** `EVENT_LABELS.checkpoint_approved = "Checkpoint approved"`. Timeline cards and `implementation.round-N.md` artifact labels add "(cpK)" from the event's `checkpoint_id`; labels never come from parsing artifacts.
- **Fingerprints.** `codingFingerprint` includes the projected `checkpoints`, and `artifactsFingerprint` includes the checkpoint ids from events, so identical polls stay mutation-free.
- **CSS.** A local `.loop-checkpoint-list` rule only.

## Changes

Ordered by dependency (M1, then M2, then M3 and M4).

### M1. Checkpoint contract
- `loop/submit.py`: new `parse_coding_checkpoints(text)` (uses `_h2_titles` / `_section_body` / `_meaningful_section`-style placeholder logic; returns items + problems) and `_check_coding_checkpoints(captured)`. `handle_submit_draft` calls it in preflight and in-lock for sessions with `contract.coding_checkpoints`.
- `loop/session.py`: `create_session` adds `contract.coding_checkpoints = 1` for new planning sessions; a `CHECKPOINT_CONTRACT` constant.
- Docs: the `loop-artifact-formats.md` pair (Plan template section) and the `writing-implementation-plans.md` review item.
- Charter: `scripts-loop.md` (`parse_coding_checkpoints`, the `handle_submit_draft` gate, the `create_session` flag).

### M2. Lifecycle and evidence binding
- `loop/gitsnap.py`: `diff_trees()`.
- `loop/host.py`: `_init_coding_loop` parses the approved-plan bytes and builds the manifest (implicit when absent; a present-but-malformed section gives an atomic `ValueError`).
- `loop/session.py`: `checkpoint_manifest(session)` and `active_checkpoint(session)`.
- `loop/state_machine.py`: manifest-aware branches in `advance_implementation_reviewed` (non-final approve → next checkpoint; per-checkpoint findings budget), `advance_extended` (guard), `advance_reopened` (final item reactivated).
- `loop/submit.py`: `handle_submit_implementation(..., checkpoint=None)` binding, the `render_commit_state(snap, checkpoint=None)` checkpoint block, `_coding_review` checkpoint fields and events, `render_reviewed_candidate` checkpoint rows.
- `loop/events.py`: `format_event` label for `checkpoint_approved` (not in `TERMINAL_EVENTS`).
- Charters: `scripts-loop.md` (manifest schema, transitions, `diff_trees`, binding, events, and a TRIPWIRE "Checkpoint approval never commits; only the final checkpoint authorizes the commit").

### M3. Participant guidance
- `loop/cli.py`:
  - `submit-implementation --checkpoint`;
  - `_print_coding_action_prompt` checkpoint text (Draftor / Reviewer);
  - status text and JSON `checkpoint` / `checkpoints`;
  - submit and review output lines.
- Docs: the protocol pair, the `loop-artifact-formats.md` pair (Implementation note), the `/loop-join` pair.
- Charters: `scripts-loop.md` (CLI entries, cross-vendor docs note), `scripts-cross-cutting.md` (additive JSON keys and event type; doc-pair coverage).

### M4. Architect inspection
- `loop/submit.py`: the `coding_status_view` `checkpoints` projection and generation `checkpoint_id`. This lives with M4 because it exists only for the Dashboard.
- `dashboard/views/loop.js`: the coding-region checkpoint row and list, the event label, the artifact and timeline checkpoint suffix, and the fingerprints.
- `dashboard/dashboard.css`: `.loop-checkpoint-list`.
- Charters: `scripts-dashboard.md` (status projection), `scripts-dashboard-ui.md` (coding region, labels, fingerprints).

## Coding Checkpoints

1. **Checkpoint contract** — The closed `## Coding Checkpoints` grammar, its parser, and the planning-loop draft gate behind `contract.coding_checkpoints`, with the plan-format and plan-writing documentation. Verify: the parser grammar table and the submit-draft gate tests in `tests/test_loop_checkpoints.py`; `tests/test_loop_context_evidence.py` unchanged.
2. **Lifecycle and evidence binding** — Manifest freezing at coding start, checkpoint-aware transitions (per-checkpoint findings budget, extend, reopen), `diff_trees`, `--checkpoint` binding, the checkpoint Commit State and review records, and the `checkpoint_approved` event. Verify: the lifecycle and binding tables in `tests/test_loop_checkpoints.py`; existing `tests/test_loop_coding_*.py` and `tests/test_loop_gitsnap.py` unchanged.
3. **Participant guidance** — Checkpoint-aware CLI action, status, submit and review text and JSON, plus the protocol and `/loop-join` pairs. Verify: the CLI text tests in `tests/test_loop_checkpoints.py`; drift guards in `tests/test_loop.py` and `tests/test_loop_context_evidence.py`.
4. **Architect inspection** — The Dashboard checkpoint projection, coding-region progress, and the timeline and artifact checkpoint labels. Verify: `tests/test_dashboard_loop_coding.py` additions and `tests/test_dashboard_ui/test_loop_coding_ui.py` additions, then the full Dashboard UI suite once.

## Dependencies and Ordering

- **Order:** M1 (the parser), then M2 (which needs the parser at coding start), then M3 and M4.
- **Parallel:** M3 and M4 both depend only on M2's session and event fields, so they can proceed in parallel.
- **Charters** are updated right after each file edit (constitution step 5). The CHANGELOG and `commit_draft.md` come after the final checkpoint's tests pass.

## Assumptions, Risks, and Required Architect Decisions

**Non-blocking assumptions (reversible):**
- **A1:** `max_rounds` means the **per-checkpoint findings budget** for manifest loops. An extension raises it for the active checkpoint and all later ones.
- **A2:** `--checkpoint cpN` is required on `submit-implementation` for manifest loops. That turns "submitting the wrong checkpoint" into an explicit refusal rather than a silent mis-binding.
- **A3:** Declaring checkpoints is recommended, not required. Plans without them get the implicit single checkpoint, so short plans stay simple.
- **A4:** Grammar limits are 1–12 checkpoints, titles of at most 80 characters, and scope/verify capped at 400 characters each.
- **A5:** Reopen applies only to the final checkpoint. Earlier checkpoints are never reopened; their concerns go into a later checkpoint or a revision planning loop.
- **A6:** A planning-loop draft with a malformed **present** section is refused only for new planning sessions (`contract.coding_checkpoints`). Older approved plans are still checked once at coding start.

**Risks:**
- **Approval authority.** A non-final approval must never authorize a commit. Mitigation: `coding.approval` is written only for the final checkpoint, and `resolve_approval` and the one-commit handoff are untouched. A TRIPWIRE plus a test checks that a non-final approval leaves `coding.approval` null and produces no Git ref, index or worktree change.
- **Wrong base.** A later checkpoint could be bound to the wrong base. Mitigation: the base is set only from the previous item's `accepted.tree` inside the same locked transition, and findings never change it (tested).
- **Diff reverts earlier work.** A Draftor could unstage earlier approved work in a later checkpoint. That is visible as reverted paths in the checkpoint diff against its base, which is reviewable, and the final approval still binds the exact cumulative tree. There is no new prohibition.
- **Index-lock permissions.** The reviewer runtime still needs `.git` write access for the approval freshness check. That is unchanged by this plan, and it is the open issue raised in the #51 coding loop.

**Blocking decisions:** none.

## Testing

One new module test file, `tests/test_loop_checkpoints.py`. It reuses the `test_loop_coding_mode` fixtures and the `test_loop_coding_submit` staging helpers. Each group proves one invariant:

1. **Grammar (M1):** one parameterized table.
   - Valid: 1, 2 and 12 items; continuation lines; dash and colon separators; a fenced example ignored.
   - Invalid: duplicate section, gaps or out-of-order numbers, missing title, missing `Verify:`, placeholder scope, 13 items, an over-long title, stray non-item text.
   - It checks exact items and problem text.
2. **Draft gate (M1):** a flagged planning session rejects a malformed present section atomically and accepts a plan with none. An unflagged (legacy) session is never checked. Uses the #46 swap-safe path.
3. **Manifest freeze (M2):**
   - declared → items with `cp1` active, base = loop base tree;
   - no section → implicit `Full implementation`;
   - malformed approved plan → atomic start refusal;
   - editing the source loop's plan after start does not change the manifest.
4. **Lifecycle table (M2), parameterized steps over a two-checkpoint loop:**
   - `--checkpoint cp2` before cp1 is approved is refused, and an absent `--checkpoint` is refused;
   - submit cp1, then findings: same checkpoint, base unchanged, `findings_rounds = 1`;
   - resubmit, then approve: `checkpoint_approved`, stage `implementation_drafting`, cp2 base = cp1 accepted tree, `coding.approval` null, and Git HEAD, refs and index unchanged;
   - submit cp2, then approve: `implementation_approved`, and `resolve_approval` is `pending`;
   - per-checkpoint budget: cp1 at its ceiling gives `max_rounds_exceeded`; extend resumes the same checkpoint;
   - pause, unblock and escalate preserve the checkpoint and role;
   - reopen reactivates only the final checkpoint.
5. **Exact diff and revisit (M2):** cp2's Commit State review command is `git diff <cp1 accepted tree> <staged>`. Its changed-path list excludes cp1-only files and marks a cp1 file that cp2 changes again. The test also checks that `diff_trees` takes no index lock (it runs with `.git/index` read-only on POSIX; skipped on Windows).
6. **Compatibility (M2/M3):** a pre-#55 coding session (no manifest) is pinned by the existing suites unchanged. One focused test checks that `--checkpoint` is rejected for it and its status text is byte-identical.
7. **CLI text (M3):** a parameterized pair for the Draftor and Reviewer action text, checking the checkpoint name, the scope/Verify lines, the exact diff command and the `--checkpoint` submit command. Status JSON `checkpoint` / `checkpoints` keys.
8. **Server (M4):** `tests/test_dashboard_loop_coding.py` gets one test: the projection carries ids, titles, states and trees, and never `scope` / `verify`.
9. **UI (M4):** `tests/test_dashboard_ui/test_loop_coding_ui.py` gets one parameterized test covering the progress text, glyph and state per item (not colour), the `checkpoint_approved` timeline label, and the artifact "(cpK)" suffix, plus one mutation-free-poll test with a checkpoint payload. The existing stale-response guards cover polling.

**Regression:** the existing loop suites, `tests/test_dashboard_loop*.py`, the doc drift guards, then the full Dashboard UI suite once at the end.

## Charter Impact

- **`.gator/charters/scripts-loop.md`:**
  - new entries: `parse_coding_checkpoints`, `checkpoint_manifest` / `active_checkpoint`, `diff_trees`, and the `checkpoint_approved` event;
  - updated: `create_session` (the flag), `handle_submit_draft` (the gate), `_init_coding_loop` (manifest), `advance_implementation_reviewed` / `advance_extended` / `advance_reopened` (checkpoint branches), `handle_submit_implementation` (`--checkpoint`, binding), `render_commit_state` / `render_reviewed_candidate`, `_coding_review`, `coding_status_view`, the CLI coding prompts and status;
  - new TRIPWIRE: **"Checkpoint approval never commits"** (only the final checkpoint writes `coding.approval`; bases come only from the previous accepted tree; no Git mutation per checkpoint);
  - Cross-Vendor Orientation: the doc-pair updates.
- **`.gator/charters/scripts-cross-cutting.md`:** the additive status JSON keys, the `checkpoint_approved` event type (non-terminal; consumers must tolerate it), and the doc-pair coverage note.
- **`.gator/charters/scripts-dashboard.md`:** the `coding.checkpoints` projection (title only; never scope or verify).
- **`.gator/charters/scripts-dashboard-ui.md`:** the coding-region checkpoint row and list, the event label, the artifact and timeline checkpoint suffix, and the fingerprint additions.
- **`.gator/charters/INDEX.md`:** no change.
