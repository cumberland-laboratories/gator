# Implementation: #51 — Checkpoint 1 (Architect-originated plan entry)

## Executive Summary

- **Changes:** `gator loop start --plan-file P [--sketch S]` starts a planning loop from an Architect-supplied plan.
  - The plan is read once through a new governed-input reader and validated by the SAME `_check_plan_draft` as a Draftor draft.
  - It is stored as immutable `architect-plan.md` plus `plan.round-0.md` and `plan.current.md`.
  - The loop starts at the existing `plan_review` stage with the Reviewer acting first, records an Architect `initial_plan` turn, and records no Draftor turn.
- **Key decision:** a generic, closed-allowlist fixed-artifact verifier with per-name limits (the approved plan's round-1 fix). The brief functions are now brief-scoped wrappers with unchanged results.
- **Main risk:** the trust boundary on input paths. Repository containment plus a lexical-equals-resolved check refuses links, junctions and aliases, and every failure is atomic.
- **Verified:** 31 new tests (30 passed, 1 platform skip). The focused loop suites pass: 678 passed, 3 skipped.

## Implementation Summary

**`src/gator_command/scripts/loop/session.py`**
- **Fixed-artifact verifier:**
  - `FIXED_ARTIFACT_LIMITS` covers the two briefs (32 KiB), `architect-plan.md` (256 KiB) and the two revision baselines (1 MiB; their writers arrive in checkpoint 2);
  - `_valid_fixed_ref` (positional binding plus the per-name limit) and `verify_fixed_artifact`, which reads at most `limit + 1` bytes;
  - `read_verified_fixed_artifact` and `fixed_artifact_view`;
  - `FIXED_*` result aliases with the existing values.
- **Brief wrappers:** `verify_brief` / `read_verified_brief` / `brief_status_view` now return `invalid_ref` / `(invalid_ref, None)` / None for any name outside `BRIEF_NAMES`, and delegate otherwise.
- **`read_governed_input(path, repo_root, max_bytes, label)`:**
  - the file is inside the repo, and the lexical absolute path equals `resolve(strict=True)` (case-normalized), which refuses symlinked or junction components and short-name aliases;
  - the final file is not a link or reparse point, and is a regular file;
  - `fstat` checks happen before the read (size `1..max`) and after it (size and mtime unchanged, length equal);
  - the content is UTF-8, has no NUL and is not blank.
- **`planning_source(session)`** returns `sketch` / `architect_plan` / `revision` and fails closed on both blocks or a malformed block. `plan_source_ref` and `_ref_only` are helpers.
- **`create_session(..., plan_source=None, revision=None)`** stores a block and refuses both blocks, or either block on a coding session.

**`src/gator_command/scripts/loop/state_machine.py`**
- `enter_architect_plan_review(session, turn_timeout)`: a fresh planning session (at most the one Architect turn) moves to `plan_review`, owned by the Reviewer per `role_by_stage`, with `_begin_turn`. Anything else raises `ValueError`.

**`src/gator_command/scripts/loop/host.py`**
- `init_loop(..., plan_path=None)` refuses `plan_path` with coding mode before writing anything, and routes to `_init_architect_plan_loop`. Its atomic order:
  1. read the governed input;
  2. `_check_plan_draft(bytes, True, True)`;
  3. check the optional sketch;
  4. create the dir; write `architect-plan.md` through `_write_fixed_artifact` (read-only, verified), and `plan.round-0.md` / `plan.current.md` through `_write_checked_bytes` (SHA-compared); then the optional sketch and brief;
  5. tokens; then `create_session(plan_source=…)`, the Architect `initial_plan` turn, `current.draft` and `enter_architect_plan_review`;
  6. events `loop_started` (`plan_source_kind`, `plan_sha256`, `plan_bytes`) then `architect_plan_submitted` (round 0, `artifact_path: plan.round-0.md`).

  Any failure triggers `_remove_partial_loop`.
- `start_loop(..., plan_path=None)` passes the plan through, and the banner gains a `Plan source:` line.

**`src/gator_command/scripts/loop/cli.py`**
- `start --plan-file` (`dest=plan_path`); `--sketch` is optional with it, and it is refused with `--mode coding`.
- `_plan_source_view` / `_print_plan_source` / `_plan_source_json` feed both model and Architect status:
  - the `Plan source:` line carries an integrity marker;
  - then either `Current plan: Architect-originated draft -- awaiting Reviewer approval (not approved)` (while no Draftor `plan_draft` turn exists) or `Plan approved by the Reviewer (originated by the Architect)`;
  - JSON gains `planning_source` (all planning loops) and `plan_source` (Architect loops).
- `_print_action_prompt`:
  - the Reviewer is told to "Review the Architect-originated draft plan (unapproved)";
  - the Draftor in revision gets the `Plan:` path and "Submit a full replacement plan";
  - with no sketch, a "No sketch: … escalate" line.
  - Ordinary loops are unchanged (pinned).

**Protocol** (`.gator/.includes/procedures/gator-loop-protocol.md` and the starter copy, byte-identical): a new `## Planning Sources` section (the Architect-originated part), and a File Locations row for `architect-plan.md`.

**Not in this checkpoint:** `--revise-from` and its baselines (checkpoint 2); the Dashboard (checkpoint 3).

## Charter Updates

- `.gator/charters/scripts-loop.md`:
  - new entries for the fixed-artifact verifier and the brief wrappers, `read_governed_input`, `planning_source` / `create_session` blocks, `enter_architect_plan_review`, and `_init_architect_plan_loop` / `_write_fixed_artifact` / `_write_checked_bytes`;
  - `_cmd_start` / status / prompt notes;
  - **new TRIPWIRE "Architect-Originated Plans Are Unapproved Input"**;
  - the Brief TRIPWIRE now notes the closed allowlist;
  - Owns line.
- `.gator/charters/scripts-cross-cutting.md`: the additive `plan_source` block, `initial_plan` turn type, `architect_plan_submitted` event (non-terminal, with `artifact_path`), `loop_started` fields, status JSON fields, the `--plan-file` flag, and the protocol pair edit.

## Verification

Per the verification ladder, these are focused checks only. The broad loop and Dashboard suite is deferred to final approval.
- `python -m pytest tests/test_loop_plan_sources.py`: **30 passed, 1 skipped** (file-symlink creation needs privileges on Windows; the directory-junction alias case runs and passes).
  - Verifier: new names verify and tampering gives `mismatch`; over-limit refs and oversize files fail; unknown names fail closed; positional binding.
  - Brief wrappers refuse the plan names.
  - Lifecycle:
    - the Reviewer acts first, with status exit 0 for the Reviewer and 1 for the Draftor;
    - three byte-identical files, digest-recorded, with one Architect turn and no Draftor turn; events `loop_started` then `architect_plan_submitted`;
    - coding is **refused before approval**;
    - findings lead to Draftor `plan_revision` with the Plan path; the revision replaces `plan.current.md` while `architect-plan.md` stays unchanged;
    - approval reports "approved by the Reviewer", and coding is **accepted** with `approved-plan.md` equal to the approved plan.
  - Atomic rejection, parameterized over 10 bad inputs, plus junction alias, coding-mode conflict and active-loop collision: the loop-directory set is unchanged.
  - A tampered provenance file shows `[!!] DIGEST MISMATCH`; `planning_source` fails closed; ordinary loops print no plan-source lines.
- `python -m pytest tests/test_loop.py tests/test_loop_attention.py tests/test_loop_context_evidence.py tests/test_loop_checkpoints.py tests/test_loop_coding_mode.py tests/test_loop_brief.py tests/test_loop_suspension.py tests/test_loop_plan_sources.py -o faulthandler_timeout=120`: **678 passed, 3 skipped** (1:58). This includes the protocol drift guards and the brief suite (brief results unchanged).
- `python -m pytest tests/test_loop_brief.py tests/test_dashboard_loop_brief.py`: 97 passed, 2 skipped. This was run after the verifier change and before the host change.
- **Residue:** this coding loop's directory and the earlier commit's session snippet are untracked and not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 3) — Architect-originated plan entry |
| Checkpoint base tree | `137f6ef8607c6905187f2f1f8968bf8052aed995` |
| Generation | 0 |
| Staged tree (candidate) | `401ed843be28a096fd1de048f52a0b10700e2a42` |
| Changed paths in this checkpoint | 10 (A 1, M 9) |
| Loop base HEAD | `2d6996c33c4b84c29cf172ec38f591a674ce2933` |
| Loop base tree | `137f6ef8607c6905187f2f1f8968bf8052aed995` |
| Current HEAD | `2d6996c33c4b84c29cf172ec38f591a674ce2933` (dev) |
| Changed paths vs loop base (cumulative) | 10 |
| Unstaged / untracked residue | 1 other + 3 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 137f6ef8607c6905187f2f1f8968bf8052aed995 401ed843be28a096fd1de048f52a0b10700e2a42
```

Cumulative context (approved checkpoints plus this one): `git diff 137f6ef8607c6905187f2f1f8968bf8052aed995 401ed843be28a096fd1de048f52a0b10700e2a42`.

Changed paths in this checkpoint (status, path):

```text
M .gator/.includes/procedures/gator-loop-protocol.md
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-loop.md
M .gator/commit_draft.md
M src/gator_command/scripts/loop/cli.py
M src/gator_command/scripts/loop/host.py
M src/gator_command/scripts/loop/session.py
M src/gator_command/scripts/loop/state_machine.py
M src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md
A tests/test_loop_plan_sources.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 3 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
