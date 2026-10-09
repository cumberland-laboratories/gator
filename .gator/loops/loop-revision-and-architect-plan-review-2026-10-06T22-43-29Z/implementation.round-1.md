# Implementation: #51 — Checkpoint 2 (Revision planning from an approved loop)

## Executive Summary

- **Changes:** `gator loop start --sketch S --revise-from <approved planning loop>` creates an ordinary Draftor-led planning loop.
  - Under the source's session lock (read-only), it copies the approved plan and its approving review as immutable, digest-verified baseline files.
  - It records a `revision` provenance block.
- **Key decision:** the approving review is identified only from the session's last turn (Reviewer, `plan_review`, "Plan approved", a `findings.round-N.md` artifact), with two cross-copy equality checks. Nothing is guessed; any mismatch fails atomically with a named reason.
- **Main risk:** source immutability. It is pinned by a byte snapshot of the source directory, and the copies stay valid after the source is deleted.
- **Verified:** 19 new tests pass. The focused loop suites pass: 691 passed, 3 skipped.

## Implementation Summary

**`src/gator_command/scripts/loop/host.py`**
- **`init_loop(..., revise_from=None)`** refuses, before anything is written:
  - `--plan-file` together with `--revise-from`;
  - `revise_from` with coding mode;
  - `revise_from` without a sketch.

  It then routes to `_init_revision_loop`.
- **`_init_revision_loop`:**
  1. canonical source id shape (`_SOURCE_LOOP_ID_RE`, no `..`), and the source dir and session must be present;
  2. the revision sketch through `read_governed_input` (repo-contained, at most 256 KiB);
  3. `_read_revision_source`;
  4. create the dir; `sketch.md` gets the exact sketch bytes (SHA-checked); `revision-baseline-plan.md` and `revision-baseline-approval.md` go through `_write_fixed_artifact` (read-only, verified); then the optional brief;
  5. tokens; then `create_session(revision=…)` at ordinary `plan_drafting`;
  6. `loop_started` with `revision_source_loop_id`, `baseline_sha256`, `approval_sha256` and `approval_source_artifact`.

  Any failure triggers `_remove_partial_loop`.
- **`_read_revision_source`** runs a **read-only** `with_session_lock` callback on the source. It requires:
  - `loop_id` equal to the requested id, planning mode, and stage `plan_approved`;
  - the last turn is the Reviewer's approving `plan_review` with a `findings.round-N.md` artifact, byte-equal to `findings.current.md`;
  - `plan.current.md` byte-equal to the artifact of the latest `plan_draft` (Draftor) or `initial_plan` (Architect) turn. This makes Architect-originated approved loops valid sources.
- **`_read_source_file`:** each file must be regular, non-link, non-empty and at most `MAX_BASELINE_BYTES` (1 MiB), with a named error otherwise.
- **`start_loop(..., revise_from=None)`** passes it through, and the banner shows `Plan source: Revision of <id> …`.

**`src/gator_command/scripts/loop/session.py`**
- `revision_refs(session)` returns `(source_loop_id, baseline_ref, approval_ref)`.
- `planning_source` validates the `baseline` ref through `_ref_only`, consistent with `approval`.

**`src/gator_command/scripts/loop/cli.py`**
- `start --revise-from` (requires `--sketch`; cannot be combined with `--plan-file` or `--mode coding`).
- `_revision_view` / `_print_revision` in model and Architect status:
  - `Revision of: <id>`, then `Baseline plan:` and `Baseline approval review:` paths with `[OK]` / `[!!]` markers, and an escalate note if either fails;
  - JSON gains `revision: {source_loop_id, baseline: {path, check}, approval: {path, check}}`.
- The Draftor's first turn in a revision loop: "Draft a full replacement plan. Read the baseline plan and its approval review, then the revision sketch", plus the three paths and "earlier rounds … optional unless the sketch requires them". Ordinary loops are unchanged.

**Protocol** (both copies, byte-identical): the "Planning Sources" revision paragraph (read order, full replacement, honest Context Checked, `[!!]` means escalate), and File Locations rows for the two baseline files.

## Charter Updates

- `.gator/charters/scripts-loop.md`:
  - the `planning_source` `revision` block shape and `revision_refs`;
  - new entry `_init_revision_loop` / `_read_revision_source` / `_read_source_file`;
  - CLI `--revise-from` and the status/prompt notes;
  - **new TRIPWIRE "Revision Baselines Are Copies"**, naming the pinning tests.
- `.gator/charters/scripts-cross-cutting.md`: the checkpoint-2 additive session block, `loop_started` fields, status JSON, flag and protocol rows.

## Verification

Focused checks per the ladder; the broad suite is deferred to final approval.
- `python -m pytest tests/test_loop_plan_sources.py -k revision`: **19 passed**.
  - **Lifecycle,** parameterized over an ordinary approved source and an **Architect-originated** approved source:
    - the session has the `revision` block, `planning_source == "revision"`, and Draftor `plan_drafting`;
    - the baseline files are byte-equal to the source `plan.current.md` and to the approving `findings.round-N.md`;
    - `loop_started` carries the source id and digests;
    - **the source directory is byte-identical before and after**;
    - the Draftor status shows the three paths with `[OK]`, and the JSON checks are `ok`;
    - after the **source directory is deleted**, both checks are still `ok`;
    - the Draftor's draft moves the loop to `plan_review`.
  - **Atomic rejection,** parameterized over 11 cases, each pinned to its reason message: not approved; coding source; non-canonical id (trailing dot); missing source; approval not the last turn; `findings.current.md` mismatch; `plan.current.md` mismatch; sketch outside the repo; no sketch; with `--plan-file`; coding mode. Each case leaves the loop-directory set and the source bytes unchanged.
- `python -m pytest tests/test_loop.py tests/test_loop_attention.py tests/test_loop_context_evidence.py tests/test_loop_checkpoints.py tests/test_loop_coding_mode.py tests/test_loop_brief.py tests/test_loop_suspension.py tests/test_loop_plan_sources.py -o faulthandler_timeout=120`: **691 passed, 3 skipped** (2:07), including the protocol drift guards.
- **Residue:** this loop's directory and the earlier session snippet are untracked and not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 3) — Revision planning from an approved loop |
| Checkpoint base tree | `401ed843be28a096fd1de048f52a0b10700e2a42` |
| Generation | 1 |
| Staged tree (candidate) | `ba55f3a814dc411f181fc291290ffab2a7391bfc` |
| Changed paths in this checkpoint | 9 (M 9) |
| Loop base HEAD | `2d6996c33c4b84c29cf172ec38f591a674ce2933` |
| Loop base tree | `137f6ef8607c6905187f2f1f8968bf8052aed995` |
| Current HEAD | `2d6996c33c4b84c29cf172ec38f591a674ce2933` (dev) |
| Changed paths vs loop base (cumulative) | 10 |
| Unstaged / untracked residue | 1 other + 7 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 401ed843be28a096fd1de048f52a0b10700e2a42 ba55f3a814dc411f181fc291290ffab2a7391bfc
```

Cumulative context (approved checkpoints plus this one): `git diff 137f6ef8607c6905187f2f1f8968bf8052aed995 ba55f3a814dc411f181fc291290ffab2a7391bfc`.

Changed paths in this checkpoint (status, path):

```text
M .gator/.includes/procedures/gator-loop-protocol.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-cross-cutting.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-loop.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/loop/cli.py  [revisits an earlier checkpoint]
M src/gator_command/scripts/loop/host.py  [revisits an earlier checkpoint]
M src/gator_command/scripts/loop/session.py  [revisits an earlier checkpoint]
M src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md  [revisits an earlier checkpoint]
M tests/test_loop_plan_sources.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 7 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
