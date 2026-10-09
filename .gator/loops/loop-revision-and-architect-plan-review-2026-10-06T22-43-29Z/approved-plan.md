# Implementation Plan: #51 — Revision Planning and Reviewer-Gated Architect Plans

## Executive Summary

- **Two new ways to start an ordinary planning loop**, both ending in a Reviewer-approved plan:
  - `start --sketch S --revise-from <approved planning loop>` copies the source's approved plan and approving review as immutable, digest-pinned baseline files;
  - `start --plan-file P [--sketch S]` captures an **Architect-originated, unapproved** plan, validated exactly like a Draftor draft, and creates the loop at `plan_review` for the Reviewer.
- **Key decision:** provenance is two explicit, mutually exclusive session blocks (`plan_source`, `revision`). It is read only through one accessor, `planning_source()`, and verified by one generic fixed-name verifier. That verifier owns a closed allowlist and per-name size limits; the brief functions become brief-only wrappers. No new stage, no fabricated Draftor turn, no route from an Architect plan to coding.
- **Main risk:** this touches durable schema, an input trust boundary and two creation surfaces (CLI and Dashboard). It is mitigated by one host-side operation shared by both surfaces, atomic rollback, and reuse of `_check_plan_draft`.
- **Verification:** focused host/CLI tests per checkpoint; Dashboard API and UI tests at checkpoint 3; the broad loop and Dashboard suite once at final approval.

## Summary

The plan adds two planning-loop entry paths to the existing creation seam, `host.init_loop()`. Neither weakens the meaning of "approved implementation plan".

- **Architect-originated plan:** a repository-contained plan file is validated with the same checks as `handle_submit_draft`. It is captured immutably, and the loop starts at `plan_review` with the Reviewer owning the first turn. Findings hand the plan to the Draftor in `plan_revision`, as for any plan.
- **Revision planning:** an approved planning loop's plan and approving review are copied as immutable, digest-pinned baseline files under that source's session lock. A new Draftor-led planning loop is then created with a revision sketch, and the source loop is never written.

CLI, participant prompts, Dashboard creation and inspection, and the protocol docs all show the provenance in plain words.

## Revision Notes (round 1)

- **Finding 1 (High), fixed-artifact verifier boundary: accepted.** The current `verify_brief()` refuses any name outside `BRIEF_NAMES` (`invalid_ref`). It also reads at most `MAX_BRIEF_BYTES + 1` (32 KiB), so a plan-sized artifact could never verify; an alias would be wrong on both counts. The plan now specifies a generic verifier in `session.py`:
  - it owns the allowlist `FIXED_ARTIFACT_LIMITS` (five names, each with its byte limit), the fixed-path safety checks, the size bound and the status codes;
  - `verify_brief`, `read_verified_brief` and `brief_status_view` become brief-scoped wrappers with unchanged results for the brief names;
  - focused tests cover the new names, unknown-name fail-closed, the wrapper restriction and unchanged brief behaviour.

  See "Fixed-artifact verifier" under Approach, Change 1, Change 6 (the baseline size limit) and Testing items 3a–3b.

## Context Checked

- **Loop files:** `sketch.md` for this loop. No Architect brief is listed in `gator loop status`.
- **Procedure:** `.gator/procedures/writing-implementation-plans.md`, including the uncommitted working-tree edit that adds the checkpoint verification ladder (focused checks per checkpoint, the broad suite once at final approval). This plan follows it.
- **Protocol and formats:** `.gator/.includes/procedures/gator-loop-protocol.md` and `.gator/.includes/reference-notes/loop-artifact-formats.md`.
- **Charters:**
  - `.gator/charters/INDEX.md`;
  - `scripts-cross-cutting.md`: CLI/JSON additive rule, drift-guard pins, product-boundary and package rules;
  - `scripts-loop.md`: `init_loop`, `_init_coding_loop`, `_read_approved_source`, `create_session`, `handle_submit_draft`, `context_checked_problems`, `parse_coding_checkpoints`, the brief `verify_brief` / `brief_status_view` pattern, and the TRIPWIREs Validated Bytes Are Persisted Bytes, Architect Brief Is Immutable Residue, Stage-Role Consistency and Role-Based Access Control;
  - `scripts-dashboard.md`: `_handle_loop_start`, `_handle_loop_status` strict views, the artifact allowlist and patterns, and the `/prompt` brief pointer;
  - `scripts-dashboard-ui.md`: loop create form, artifact enumeration, incremental fingerprints.
- **Code read:**
  - `loop/session.py`: `verify_brief`, `_valid_brief_ref`, `read_verified_brief`, `brief_status_view`, `BRIEF_NAMES`, `MAX_BRIEF_BYTES`, the `BRIEF_*` result constants and `_is_reparse_point` (round 1, for Finding 1);
  - `loop/host.py`: `init_loop`, `_resolve_brief_input`, `_write_brief`, `_read_approved_source`, `_plan_checkpoints`, `_init_coding_loop`, `_remove_partial_loop`, `_SOURCE_LOOP_ID_RE`;
  - `loop/submit.py`: `handle_submit_draft`, `_plan_contract_flags`, `_check_plan_draft`, `_write_artifact_bytes`, planning `handle_submit_review` (approval writes `findings.round-N.md` and `findings.current.md`, appends a reviewer `plan_review` turn "Plan approved", emits `plan_approved` with `artifact_path`);
  - `loop/session.py`: `create_session`;
  - `loop/cli.py`: `_cmd_start`, the `start` parser and `_print_action_prompt`;
  - `gator-dashboard.py`: the `_handle_loop_start` validation outline, `_LOOP_STATUS_ALLOWED_KEYS` and `_LOOP_ARTIFACT_ALLOWLIST` / `_PATTERNS`;
  - `dashboard/views/loop.js`: create-form mode radios, coding source select, `renderArtifacts` fixed name lists.
- **Prior artifacts:** the earlier #51 planning loop's plan (`loop-revision-planning-and-architect-plan-source-2026-10-04T19-22-28Z`, Executive Summary). It routed an Architect plan **directly to coding**, which this sketch forbids, and its coding loop ended by the Architect. The revision-capture idea is reused; the direct-to-coding route is not.

## Approach

**Planning path:** a full planning loop, as the sketch requires. This change touches durable provenance, a planning state entry point, an input trust boundary, and the CLI and Dashboard contracts.

**Module map (three responsibilities = three checkpoints):**

1. **Architect-originated plan entry.**
   - Invariant: an Architect plan enters only as unapproved input that passed the ordinary draft validation, and only at Reviewer `plan_review`.
   - This module owns the shared governed-input reader, the immutable capture, the `plan_source` provenance, the state entry, the CLI flag, participant wording and the protocol text for this source.
2. **Revision planning from an approved loop.**
   - Invariant: the baseline is a verified, immutable copy of exactly the source's approved plan and approving review, captured under the source lock, with the source never written.
   - This module owns the source checks, the copies, the `revision` provenance, the CLI flag, participant wording and the protocol text for this source.
3. **Dashboard creation and inspection.** One server-side operation (`init_loop`) behind both surfaces, plus strict status views, the artifact allowlist, create-form modes, provenance labels, artifact order, the timeline label and the coding-loop feature-name prefill.

**Key design decisions:**

- **Provenance schema (additive, positional).**
  - An Architect loop records `session["plan_source"] = {"kind": "architect", "artifact": "architect-plan.md", "sha256", "bytes"}`.
  - A revision loop records `session["revision"] = {"source_loop_id", "baseline": {"artifact": "revision-baseline-plan.md", "sha256", "bytes"}, "approval": {"artifact": "revision-baseline-approval.md", "sha256", "bytes", "source_artifact": "findings.round-<N>.md"}}`.
  - Neither key is present for ordinary and legacy loops.
  - One accessor, `session.planning_source(session)`, returns `"sketch"`, `"architect_plan"` or `"revision"`, like `loop_mode()`. Both blocks present, or a malformed block, raises `ValueError` (fail closed). No caller tests filenames or stage to infer the source.
- **Fixed-artifact verifier (round 1, Finding 1).** One generic verifier in `session.py` replaces brief-only verification. It is **the single owner** of these rules:
  - **Allowlist and size limit:** `FIXED_ARTIFACT_LIMITS`, a closed mapping of exactly five fixed names to their byte limits:
    - `architect-brief.md` and `source-architect-brief.md`: `MAX_BRIEF_BYTES` (32 KiB, unchanged);
    - `architect-plan.md`: `MAX_PLAN_BYTES` (256 KiB);
    - `revision-baseline-plan.md` and `revision-baseline-approval.md`: `MAX_BASELINE_BYTES` (1 MiB).

    A name outside the mapping is never verified.
  - **`_valid_fixed_ref(ref, expected_name)`:** `ref` is a dict whose `artifact` equals `expected_name` (positional binding), with a 64-hex lowercase `sha256` and an int, non-bool `bytes` in `0..limit[expected_name]`. It is the old `_valid_brief_ref` plus the per-name bound.
  - **`verify_fixed_artifact(loop_dir, ref, expected_name)`:**
    1. `ref is None` gives `absent`;
    2. a name not in the allowlist, or an invalid ref, gives `invalid_ref`;
    3. a symlink, reparse point, or a resolved parent other than the loop dir gives `unsafe`;
    4. no regular file gives `missing`;
    5. a read error gives `unreadable`; the read is capped at `limit + 1` bytes, so an oversize file can never be read in full;
    6. a size or SHA-256 difference gives `mismatch`;
    7. otherwise `ok`.

    The result strings are the existing `BRIEF_*` constants. They gain neutral aliases (`FIXED_OK` etc.) with **identical values**, so status JSON is unchanged.
  - **`read_verified_fixed_artifact(loop_dir, ref, expected_name)`** returns `(result, bytes_or_None)`: the exact verified bytes, read once and capped.
  - **`fixed_artifact_view(ref, expected_name)`** returns `{artifact, sha256, bytes}` only for an allowlisted name with a valid ref, and None otherwise. Unknown keys are always dropped.
  - **Brief-scoped wrappers** keep their names and results:
    - `verify_brief` and `read_verified_brief` return `invalid_ref` (and `None` bytes) for any name outside `BRIEF_NAMES`, and otherwise delegate;
    - `brief_status_view` returns None outside `BRIEF_NAMES`, and otherwise delegates.

    So a plan artifact can never be read through a brief position, and brief behaviour for the two brief names is unchanged. Every current caller passes a brief name.
  - **Metadata never chooses a path:** every caller passes a FIXED `expected_name` constant, never a value from session data.
- **Architect plan: one immutable provenance copy plus normal projections** (the sketch's open decision). The captured bytes are written three times, each with a digest check:
  - `architect-plan.md`: read-only, immutable provenance;
  - `plan.round-0.md`: the versioned artifact, so timeline and artifact semantics match a normal submission;
  - `plan.current.md`: the ordinary current projection, overwritten by a later Draftor revision as usual.

  Only `architect-plan.md` is integrity-checked by status. `plan.current.md` keeps its ordinary mutable role.
- **No fabricated Draftor turn.**
  - The session records one Architect turn, `type: "initial_plan"`, summary "Architect-originated draft plan submitted for Reviewer approval", `artifact_path: "plan.round-0.md"`.
  - `current.draft` points at `plan.current.md`.
  - The Draftor stays `joined: False`.
  - The creation events are `loop_started` (with `plan_source_kind`, `plan_sha256`, `plan_bytes`) and then a new additive, non-terminal `architect_plan_submitted` event `{role: "architect", round: 0, artifact_path: "plan.round-0.md", detail: "Architect-originated draft plan — awaiting Reviewer approval"}`.
- **No new stage.** `state_machine.enter_architect_plan_review(session, turn_timeout)` sets `stage = plan_review`, `next_role = reviewer`, `plan_status = in_review` and calls `_begin_turn`. It validates the mode-table owner (Stage-Role Consistency). Existing transitions do the rest: approval leads to `plan_approved`, and findings lead to `plan_revision` for the Draftor.
- **Validation identical to drafts.** New sessions always carry both contract flags, so the Architect plan is checked with `_check_plan_draft(captured, True, True)`: Context Checked and Coding Checkpoints, the same function and the same bytes that are persisted (Validated Bytes Are Persisted Bytes).
- **Shared governed-input reader.** `session.read_governed_input(path, repo_root, max_bytes, label)` returns the bytes or raises `ValueError` / `FileNotFoundError`. Rules:
  - The path resolves (`strict=True`) inside `repo_root`.
  - The lexical path equals its resolved path, case-normalized on Windows. This refuses symlinked or junction components and short-name aliases.
  - The final file is not a symlink or reparse point (`_is_reparse_point`), and is a regular file.
  - `0 < size ≤ max_bytes`, where `MAX_PLAN_BYTES = 262144` and the revision sketch uses the same cap.
  - It is read once, and must be stable: an `fstat` size and mtime before and after the read must match the bytes length.
  - UTF-8, no NUL, not blank.

  It is used for the Architect plan and the revision sketch. The ordinary `--sketch` path is unchanged (out of scope).
- **Approving-review identification (revision).** Under the source session lock, with a read-only callback:
  - Canonical id (`_SOURCE_LOOP_ID_RE` plus `session.loop_id ==` the requested id), planning mode and `plan_approved`.
  - **Approval:** the last turn must be the reviewer's `plan_review` turn with summary `"Plan approved"` and `artifact_path` matching `^findings\.round-\d+\.md$`. That file must be a regular, non-empty file and **byte-equal** to `findings.current.md`.
  - **Plan:** `plan.current.md` must be **byte-equal** to the artifact of the latest plan-producing turn (`plan_draft` by the Draftor, or `initial_plan` by the Architect).
  - Any mismatch, absence or link fails atomically with a named reason. Planning artifacts carry no stored digests, so this cross-copy check is the strongest available detection. A consistent rewrite of both copies is not detectable (stated as a risk).
- **Mutual exclusion.** `--plan-file` and `--revise-from` cannot be combined. Neither is valid with `--mode coding`, and `--revise-from` requires `--sketch`. `--plan-file` takes an optional `--sketch`; without one, no `sketch.md` is written and prompts say the plan's own scope and any brief govern. These checks run before anything is written.
- **The coding loop is unchanged.** `_read_approved_source` already requires `plan_approved`, so an Architect plan cannot reach coding before Reviewer approval. Approval of either new source kind yields an ordinary eligible source. No coding-loop code changes.
- **Rejected alternatives:**
  - A new `architect_plan_review` stage: it adds state, protocol tables and drift pins for no gain.
  - Overloading `--sketch` or `--from-loop` (the sketch forbids it).
  - Making `architect-plan.md` itself `plan.current.md`: a later Draftor revision must overwrite the current plan without destroying provenance.
  - Live references to source residue instead of copies: the source may change or be deleted.

**Simplicity boundary:**
- No new transport and no new Dashboard server route; the existing `/loops/start` gains fields.
- No notification kinds.
- The prompt and label strings come from one CLI helper and one JS map keyed by `planning_source`.

## Changes

Ordered by dependency.

### 1. Governed input, provenance accessor and views (Checkpoint 1)
- File: `src/gator_command/scripts/loop/session.py`
- What:
  - `read_governed_input()`, `MAX_PLAN_BYTES`;
  - `ARCHITECT_PLAN_FILENAME = "architect-plan.md"`, `REVISION_BASELINE_PLAN = "revision-baseline-plan.md"`, `REVISION_BASELINE_APPROVAL = "revision-baseline-approval.md"`;
  - `planning_source(session)`;
  - the fixed-artifact verifier (round 1): `FIXED_ARTIFACT_LIMITS`, `MAX_BASELINE_BYTES`, `_valid_fixed_ref`, `verify_fixed_artifact`, `read_verified_fixed_artifact`, `fixed_artifact_view`, and the `FIXED_*` result aliases, as specified under Approach;
  - `verify_brief`, `read_verified_brief` and `brief_status_view` rewritten as brief-scoped wrappers over it (results unchanged for the brief names);
  - `host._write_brief` keeps calling `verify_brief`, and new artifacts are written by a sibling `_write_fixed_artifact(loop_dir, name, data)` that verifies with `verify_fixed_artifact`;
  - `create_session(..., plan_source=None, revision=None)` stores the blocks when given, and raises if both are given.
- Why: one closed reader and one accessor, used by every surface.

### 2. State entry (Checkpoint 1)
- File: `src/gator_command/scripts/loop/state_machine.py`
- What: `enter_architect_plan_review(session, turn_timeout)`, planning mode only, valid only from a fresh `plan_drafting` session at round 0 with no turns; otherwise `ValueError`.

### 3. Architect-plan capture (Checkpoint 1)
- File: `src/gator_command/scripts/loop/host.py`
- What:
  - `init_loop(..., plan_path=None, revise_from=None)` checks mutual exclusion up front.
  - `_init_architect_plan_loop(feature, plan_path, sketch_path, ...)`:
    1. read the plan through `read_governed_input`, then `_check_plan_draft(bytes, True, True)`;
    2. read the optional sketch the ordinary way;
    3. **only then** create the loop dir;
    4. write `architect-plan.md` with `_write_fixed_artifact` (read-only, then `verify_fixed_artifact` must return `ok`), and `plan.round-0.md` and `plan.current.md` with `_write_artifact_bytes`, each re-read and SHA-256-compared with the captured digest;
    5. write the optional `sketch.md` and brief;
    6. write tokens;
    7. `create_session(..., plan_source=…)`, append the Architect `initial_plan` turn, set `current.draft`, call `enter_architect_plan_review`, save;
    8. emit `loop_started` and then `architect_plan_submitted`.

    Any failure triggers `_remove_partial_loop`.
  - `start_loop` passes the new arguments through; the start lock and the single-active guard are unchanged.

### 4. CLI and participant wording (Checkpoint 1)
- File: `src/gator_command/scripts/loop/cli.py`
- What:
  - `start --plan-file PATH` with argument checks (not with `--mode coding` or `--revise-from`).
  - `_planning_source_lines(session, loop_dir)` for model and Architect status:
    - `Plan source: Architect-originated draft plan -- architect-plan.md [OK]` (or an `[!!]` marker from `verify_fixed_artifact`);
    - while no Draftor plan has replaced it: `Current plan: Architect-originated draft -- awaiting Reviewer approval (not approved)`;
    - after approval: `Plan approved by the Reviewer (originated by the Architect)`.
  - JSON gains additive `planning_source` and `plan_source: {path, check}`.
  - `_print_action_prompt`:
    - the Reviewer sees "Review the Architect-originated draft plan (unapproved) and submit findings or approve";
    - the Draftor in `plan_revision` also gets the `Plan:` path;
    - with no sketch, prompts say "No sketch: the plan's stated scope and any Architect brief govern; scope changes are Architect-owned (escalate)".
  - The start banner names the source.
  - Text stays ASCII (`--`).

### 5. Protocol text for Architect-originated plans (Checkpoint 1)
- Files: `.gator/.includes/procedures/gator-loop-protocol.md` and the starter copy (byte-identical).
- What: a short "Planning Sources" subsection, Architect-plan part:
  - the Reviewer may own the first turn;
  - the plan is unapproved Architect input, reviewed exactly like a draft;
  - findings go to the Draftor, who submits a full replacement plan;
  - the File Locations table gains `architect-plan.md`.

### 6. Revision capture (Checkpoint 2)
- File: `src/gator_command/scripts/loop/host.py`
- What:
  - `_read_revision_source(source_dir, loop_id)` returns `(plan_bytes, approval_bytes, approval_source_name)` under a read-only `with_session_lock` callback, with the identification rules above. A source plan or approving review larger than `MAX_BASELINE_BYTES` (1 MiB) is refused with a named reason before anything is written, so the baseline copies always fit the verifier's limit.
  - `_init_revision_loop(feature, sketch_path, revise_from, ...)`:
    1. read the revision sketch through `read_governed_input`;
    2. capture the source;
    3. create the dir;
    4. write `sketch.md`, then `revision-baseline-plan.md` and `revision-baseline-approval.md` with `_write_fixed_artifact` (read-only, `verify_fixed_artifact` must return `ok`);
    5. write the optional brief and tokens;
    6. `create_session(..., revision=…)` at ordinary `plan_drafting`;
    7. emit `loop_started` with `revision_source_loop_id` and both digests.

    It never writes the source; any failure triggers rollback.

### 7. CLI and participant wording for revisions (Checkpoint 2)
- File: `src/gator_command/scripts/loop/cli.py`
- What:
  - `start --revise-from LOOP_ID`, which requires `--sketch`.
  - Status lines: `Revision of: <source id>`, `Baseline plan: …revision-baseline-plan.md [OK]` and `Baseline approval review: …revision-baseline-approval.md [OK]`. JSON gains an additive `revision` object.
  - First Draftor turn: "Draft a full replacement plan. Read the baseline plan and its approval review, then the revision sketch", with the three paths. Earlier source rounds are optional unless the sketch requires them.

### 8. Protocol text for revisions (Checkpoint 2)
- Files: both protocol copies (byte-identical).
- What: the "Planning Sources" revision part (read the baseline and approval first; Context Checked records only what was actually consulted), plus File Locations rows for the two baseline files.

### 9. Dashboard server (Checkpoint 3)
- File: `src/gator_command/scripts/gator-dashboard.py`
- What:
  - **`_handle_loop_start`** accepts `plan_path` (repo-relative string) and `revise_from` (loop id string) for planning mode. Type checks happen first. Conflicts get 400: both given, either with `mode: coding`, or `revise_from` without `sketch_path`. With `plan_path`, `sketch_path` is optional. Both are passed to `init_loop`, which is the only validator (containment, format, source integrity); its `ValueError` / `FileNotFoundError` returns 400 with nothing written.
  - **`_handle_loop_status`** adds explicit `planning_source`, `plan_source: {view, check}` and `revision: {source_loop_id, baseline: {view, check}, approval: {view, check}}` through `fixed_artifact_view` / `verify_fixed_artifact`. They are never added via `_LOOP_STATUS_ALLOWED_KEYS`.
  - **`_LOOP_ARTIFACT_ALLOWLIST`** gains the three fixed names.
  - **`/prompt`** adds one pointer line ("This loop revises <id>: read revision-baseline-plan.md and revision-baseline-approval.md first", or "The current plan is an Architect-originated draft awaiting Reviewer approval"), with no content.
  - **`/loops` items** gain additive `feature` (already present) and `planning_source` for the prefill.

### 10. Dashboard UI (Checkpoint 3)
- Files: `src/gator_command/scripts/dashboard/views/loop.js`, `dashboard.css`
- What:
  - **Create form, planning mode,** gets a "Plan source" radio group:
    - From a sketch (default, unchanged);
    - Revise an approved plan: a select of approved planning loops plus the revision sketch path;
    - Architect plan for review: a plan path plus an optional sketch.

    Client checks are convenience only, and the POST body carries exactly the chosen source's fields.
  - **Header line:** "Source: Architect-originated draft — awaiting Reviewer approval" / "Source: Architect-originated, approved by Reviewer" / "Revision of <id>", with a text integrity marker.
  - **`renderArtifacts`** fixed lists, provenance first:
    - Architect: `architect-plan.md` ("Architect-originated draft plan (provenance, unapproved)"), then `sketch.md` when present;
    - Revision: `revision-baseline-plan.md` ("Baseline: approved plan from <id>"), `revision-baseline-approval.md` ("Baseline: approving review"), `sketch.md` ("Revision sketch");
    - then `plan.current.md` and `findings.current.md`.
  - **Timeline:** `EVENT_LABELS.architect_plan_submitted = "Architect plan — awaiting Reviewer"`.
  - **Coding create mode:** selecting an approved source pre-fills an **empty** feature field with the source's feature and stays editable.
  - Fingerprints include the new view fields, so unchanged polls stay mutation-free.

### 11. Charters and commit draft (each checkpoint, alongside its code)
- See Charter Impact.

## Dependencies and Ordering

- **Checkpoint 1 → 2 → 3.**
  - Checkpoint 2 reuses Checkpoint 1's reader, accessor, fixed-artifact helpers and the `initial_plan` turn type, which it must recognize when an approved Architect-originated loop becomes a revision source.
  - Checkpoint 3 renders the fields and calls the `init_loop` arguments from Checkpoints 1–2.
- **Within each checkpoint:** session/state, then host, then CLI, then protocol text.
- **No migrations.** The blocks are additive, and absent blocks mean "sketch".

## Assumptions, Risks, and Required Architect Decisions

- **Assumption A1 (non-blocking): the sketch is optional for Architect-plan loops.** Without one, the plan's stated scope plus any brief govern, and the prompts say so. This is reversible: requiring `--sketch` is a one-line check.
- **Assumption A2 (non-blocking): the revision source's brief is not carried forward.** A new brief may be given with `--brief`.
- **Assumption A3 (non-blocking): `MAX_PLAN_BYTES = 256 KiB`** for Architect plans and revision sketches.
- **Assumption A4 (non-blocking, round 1): `MAX_BASELINE_BYTES = 1 MiB`** for the two revision baseline copies. Ordinary draft submissions are uncapped, so an exceptionally large source plan or review is refused as a revision source with a clear error instead of being truncated or silently unverifiable.
- **Risk:** planning artifacts have no stored digests, so a consistent rewrite of both `findings.round-N.md` and `findings.current.md` (or both plan copies) in a source loop is undetectable. Cross-copy equality plus the session-turn binding detects partial tampering and absence. This is stated, not solved; adding digests to planning submissions is out of scope.
- **Risk:** a legacy approved loop whose approving turn does not match the documented shape (summary `"Plan approved"`, a `findings.round-N.md` artifact) is refused as a revision source with a named reason, not guessed. Every loop created by the current CLI matches.
- **Risk:** path-alias detection on Windows (8.3 short names, case). Mitigated by comparing `os.path.normcase` of the lexical absolute path with `Path.resolve(strict=True)`; any difference is refused.
- **No blocking Architect decisions.**

## Testing

This follows the procedure's verification ladder: focused checks per checkpoint, and the broad suite only at final approval.

**Checkpoint 1** (new `tests/test_loop_plan_sources.py`, about 2 minutes):
1. **Architect-plan lifecycle.** Start with `--plan-file` and check:
   - the session is at `plan_review` with the Reviewer's turn (`status` exits 0 for the Reviewer and 1 for the Draftor);
   - the three plan files are byte-identical and digest-recorded;
   - there is one Architect `initial_plan` turn and no Draftor turn, and the events are `loop_started` then `architect_plan_submitted`;
   - `start --mode coding --from-loop` is **refused** before approval.

   Then findings lead to Draftor `plan_revision` (the prompt shows the Plan path); a Draftor revision replaces `plan.current.md` while `architect-plan.md` stays unchanged; approval leads to `plan_approved`; and a coding start is then **accepted**.
2. **Atomic rejection**, parameterized:
   - the plan is missing, outside the repo, a directory, a symlink or junction (skipped where the OS cannot create one), empty, non-UTF-8, contains NUL, or is over the limit;
   - Context Checked is missing, or Coding Checkpoints are invalid;
   - `--plan-file` is combined with `--revise-from` or with `--mode coding`;
   - another loop is active.

   Each case asserts that the loops directory listing and the start lock are unchanged (no dir, token, session or event).
3a. **Fixed-artifact verifier** (round 1, Finding 1; `tests/test_loop_plan_sources.py`, pure functions on a temp dir):
   - parameterized over the three new names: a written file verifies `ok`, and `fixed_artifact_view` returns exactly `{artifact, sha256, bytes}`;
   - a size of `limit + 1` in the ref, and an oversize file on disk, give `invalid_ref` and `mismatch` respectively, and the capped read never returns more than `limit + 1` bytes;
   - an unknown name (for example `plan.current.md` or `sketch.md`) gives `invalid_ref` from `verify_fixed_artifact` and None from `fixed_artifact_view`;
   - a ref naming a different allowlisted file than the expected position gives `invalid_ref` (positional binding).
3b. **Brief wrappers unchanged and closed:**
   - `verify_brief`, `read_verified_brief` and `brief_status_view` called with a plan artifact name give `invalid_ref` / `(invalid_ref, None)` / None;
   - the existing brief suites (`tests/test_loop_brief.py`, `tests/test_dashboard_loop_brief.py`) pass unchanged, which proves identical brief results.
3. **Integrity and legacy.** A tampered `architect-plan.md` shows `[!!] DIGEST MISMATCH` in status. A session with both blocks makes `planning_source` raise. A legacy session projects as `sketch` with byte-identical status text.
4. **Existing drift guards** (`TestDriftGuards`, `TestParticipantDocs`, `TestWaitHandoffAlignment`) pass with the protocol edit. No new guard classes.

**Checkpoint 2** (same file):
5. **Revision lifecycle**, parameterized over an ordinary approved source and an approved **Architect-originated** source:
   - the new loop is at `plan_drafting` with the baseline copies verified, and the Draftor prompt lists the baseline, the approval and the sketch;
   - the source directory's bytes and `session.json` are unchanged (a full byte snapshot);
   - after the source directory is deleted, status still shows `[OK]` for both baseline files.
6. **Atomic rejection**, parameterized:
   - the source is not approved, is a coding source, has a non-canonical id or does not exist;
   - the approving turn is missing or not the last turn;
   - `findings.round-N.md` differs from `findings.current.md`;
   - `plan.current.md` differs from the latest plan artifact;
   - the revision sketch is outside the repo, or `--sketch` is missing.

**Checkpoint 3:**
7. **Dashboard API** (`tests/test_dashboard_loops.py`):
   - start with `plan_path` and with `revise_from`;
   - the conflict and type 400s, each with no loop created;
   - the status views, which never pass raw blocks, and the `check` values;
   - the three new artifact names are served, while traversal and unknown names are still refused;
   - the `/prompt` pointer lines.
8. **Dashboard UI** (`tests/test_dashboard_ui/test_loop_workspace.py`, focused `-k`):
   - each create-source mode posts exactly its fields;
   - Architect and revision loops show the header source line, the artifact order and labels, and the timeline label;
   - the coding-mode feature prefill fills only an empty field and stays editable;
   - unchanged polls make zero mutations in the new header/artifact fields.

**Final approval (once):** `python -m pytest tests/test_loop*.py tests/test_dashboard_loop*.py tests/test_dashboard_loops.py tests/test_dashboard_ui/ tests/test_snapshot.py tests/test_packaging.py`. No checkpoint needs the broad suite earlier: none changes a cross-cutting contract beyond the additive fields covered by the focused tests.

## Charter Impact

- `scripts-loop.md`:
  - new entries for `read_governed_input`, `planning_source`, the fixed-artifact verifier (`FIXED_ARTIFACT_LIMITS`, `_valid_fixed_ref`, `verify_fixed_artifact`, `read_verified_fixed_artifact`, `fixed_artifact_view`; the brief functions documented as brief-scoped wrappers), `_write_fixed_artifact`, `enter_architect_plan_review`, `_init_architect_plan_loop`, `_read_revision_source` and `_init_revision_loop`;
  - updated `init_loop` / `start_loop` / `create_session` / `_cmd_start` / `_print_action_prompt` / status notes;
  - **new TRIPWIRE "Architect-Originated Plans Are Unapproved Input"**: only via `_check_plan_draft` on the persisted bytes, only at `plan_review`, never a Draftor turn, never coding before Reviewer approval;
  - **new TRIPWIRE "Revision Baselines Are Copies"**: captured under the source lock, verified by fixed name, the source never written, no live references;
  - the Architect Brief TRIPWIRE is updated: verification now goes through `verify_fixed_artifact`'s closed allowlist, and the brief wrappers refuse non-brief names.
- `scripts-cross-cutting.md`:
  - additive session blocks (`plan_source`, `revision`) and turn type `initial_plan`;
  - additive event `architect_plan_submitted` (non-terminal, with `artifact_path`) and `loop_started` fields;
  - additive `gator-loop-status-v1` fields;
  - new `start` flags;
  - the protocol pair edit under the existing drift guards.
- `scripts-dashboard.md`: start fields and conflicts, strict status views, allowlist names, `/prompt` pointers and the `/loops` `planning_source`.
- `scripts-dashboard-ui.md`: create-source modes, the header source line, artifact order and labels, the timeline label and the coding prefill.

## Coding Checkpoints

1. **Architect-originated plan entry** — governed input reader, generic fixed-artifact verifier with brief wrappers, draft-identical validation, immutable architect-plan.md plus round-0/current projections, plan_source accessor, plan_review entry with an Architect initial_plan turn, CLI --plan-file, wording and protocol text.
  Verify: verifier and brief-wrapper tests, Architect-plan lifecycle, atomic-rejection, integrity/legacy tests and doc drift guards.
2. **Revision planning from an approved loop** — source checks under its lock, approving-review and plan identification with cross-copy checks, verified baseline copies, revision provenance, CLI --revise-from, Draftor first-turn wording and protocol text; the source loop is never written.
  Verify: parameterized revision lifecycle (ordinary and Architect-originated sources), source byte-immutability, deleted-source integrity and atomic-rejection tests.
3. **Dashboard creation and inspection of plan sources** — start fields with conflict checks through init_loop, strict status views, artifact allowlist and prompt pointers, create-form source modes, provenance header, artifact order and labels, timeline label, and coding feature prefill.
  Verify: Dashboard API tests and focused loop-workspace UI tests; the broad loop and Dashboard suite runs once at final approval.
