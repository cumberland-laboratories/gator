# Implementation Plan: Revision Planning from Approved Plans and Architect-Supplied Coding Plans (#51)

## Executive Summary

- **Two new creation paths, sharing one capture core.**
  - A **revision planning loop** (`start --sketch S --revise-from <approved planning loop>`) is an ordinary planning loop. It starts with digest-pinned copies of the source's approved plan and approval review.
  - A **coding loop from an Architect-supplied plan** (`start --mode coding --plan-file P`) copies the file to the neutral `architect-plan.md`.
- **Key decision:** provenance is explicit, positional metadata: a top-level `revision` block for planning and `coding.source_kind` for coding. It is verified only against fixed artifact names and is never inferred from filenames. The source loop is only read, under its own session lock.
- **Main risk:** a large cross-surface change (host, session, CLI, server, Dashboard, protocol docs). It is mitigated by extending the existing atomic `_init_coding_loop` ordering, not by adding a parallel creation flow.
- **Verification:** atomic-failure tests for every rejection, a byte-for-byte source-immutability test, byte-compatibility pins for existing `--from-loop` coding loops, and Dashboard end-to-end checks.

## Summary

The plan extends `loop/host.init_loop()` with two new source kinds. Both reuse the coding successor's existing order: validate, read the bytes once, then snapshot Git (coding only), create the directory, write the fixed artifacts read-only, digest-verify them, and only then create tokens, session and events, with rollback on any failure.

One shared session-layer validator handles every Architect-named file input: repository containment, no links or reparse points, regular file, UTF-8, no NUL, a size cap, and a single read. One shared fixed-name verifier handles every stored source copy.

Status, prompts, CLI text, Dashboard creation and Dashboard inspection all read the same strict projections, so labels never come from artifact names. Existing planning and `--from-loop` coding loops are unchanged.

## Context Checked

- `sketch.md` (loop directory): scope A and B, out-of-scope list, seams, the five design questions, module boundaries and verification focus. Status lists no Architect brief for this loop.
- `.gator/charters/scripts-loop.md` (full): `create_session()`, the `loop_mode()` gate, brief helpers (`validate_brief_bytes`, `read_brief_file`, `verify_brief`, `read_verified_brief`, `brief_status_view`), `_init_coding_loop` / `_read_approved_source` / `_remove_partial_loop`, `start_loop` / `start.lock`, `coding_status_view`, `_cmd_start` / `_print_coding_action_prompt` / brief printers, and the TRIPWIREs (Brief Is Immutable Residue, Validated Bytes Are Persisted Bytes, Session Lock Write Ordering, Resumable Terminal Stage: `plan_approved` is final), plus the Cross-Vendor Orientation doc-pair rules.
- `.gator/charters/scripts-cross-cutting.md`: Shipped-Copy Synchronization (`TestDriftGuards` / `TestWaitHandoffAlignment` pairs for the protocol, `loop-artifact-formats.md` and `/loop-join`), CLI JSON additive-field rule (`gator-loop-status-v1`), and the loop-revival `start.lock` rule.
- `.gator/charters/scripts-dashboard.md`: `_handle_loop_start` validation order and the `start.lock` / single-active guard, `_LOOP_STATUS_ALLOWED_KEYS` (brief and coding use dedicated serializers, never the generic allowlist), `_LOOP_ARTIFACT_ALLOWLIST`, `/prompt` pointer-only rule, `sketch_path` containment.
- `.gator/charters/scripts-dashboard-ui.md`: Loop workspace create form (#43 M2a loop-type radio, `_create` state, `loadSourcePicker` / `loadSourceBrief` double stale guard, `updateCreateEnabled`), `briefEntries` / `briefEntryLabel`, `renderArtifacts` ordering, `renderControls` / `controlsFingerprint`, `renderCodingRegion` / `codingFingerprint`, `headerFingerprint`, `artifactsFingerprint`, colour-independent state text.
- `.gator/charters/INDEX.md`: `loop/**` maps to Loop and Cross-Cutting; dashboard Python maps to Server; dashboard JS maps to UI and Server.
- Code read:
  - `loop/host.py`: `init_loop`, `_resolve_brief_input`, `_write_brief`, `_SOURCE_LOOP_ID_RE`, `APPROVED_PLAN_FILENAME`, `_read_approved_source`, `_init_coding_loop`, `_remove_partial_loop`, `start_loop`.
  - `loop/session.py`: brief section, `attention_mode`, `create_session`.
  - `loop/submit.py`: `coding_status_view`; planning `handle_submit_review`, which shows that at `plan_approved` `findings.current.md` is the approval review written in the approving transaction and `current.findings` names it; `_h2_titles`.
  - `loop/cli.py`: `_cmd_start`, `_print_action_prompt`, `_brief_entries`, `_print_briefs`, `_briefs_json`, `_print_coding_action_prompt`, `start` argparse.
  - `gator-dashboard.py`: `_handle_loop_list`, `_LOOP_STATUS_ALLOWED_KEYS`, `_handle_loop_status`, `_LOOP_ARTIFACT_ALLOWLIST` / `_PATTERNS`, `_handle_loop_start`, `_handle_loop_prompt`.
  - `dashboard/views/loop.js`: brief helpers, stage and label tables, `renderLoopSidebar`, `renderCreateWorkspace`, `loadSketchPicker`, `getSketchPath`, `_create` / `updateCreateEnabled` / `setCreateMode` / `loadSourcePicker` / `loadSourceBrief` / `handleCreateSubmit`, `renderOutcomeHeader`, `renderCodingRegion`, `renderArtifacts`.
  - `.claude/commands/loop-join.md`: the coding-loop reading line naming `approved-plan.md`.
- Not read, with the reason: the source loop's earlier rounds, decision documents and briefs. They are not inputs to the creation path.

## Approach

### D1 — Minimal additive session schema

**Planning revision: a new top-level `revision` block.** It is present only on revision loops. It is deliberately not inside `coding`, so mode and stage semantics stay unambiguous.

```json
"revision": {
  "contract": 1,
  "source_loop_id": "<canonical approved planning loop id>",
  "source_feature": "<source session feature, string or null>",
  "source_round": 2,
  "source_review_turn_id": "reviewer-003",
  "source_review_artifact": "findings.round-2.md",
  "source_had_brief": true,
  "plan":   {"artifact": "source-approved-plan.md",  "sha256": "<64 hex>", "bytes": 12345},
  "review": {"artifact": "source-approval-review.md", "sha256": "<64 hex>", "bytes": 2345}
}
```

- `source_review_turn_id` and `source_review_artifact` are copied from the source session's `current.findings.turn_id` and the matching turn's `artifact_path`. They are **identity labels only** and are never opened as paths.
- `source_had_brief` is recorded so status can say "the source had an Architect brief (not carried forward)". No brief bytes are read.
- `create_session(..., revision=None)` adds the block only when it is given. It raises `ValueError` if `revision` is passed with `mode="coding"`.
- The session keeps `mode: "planning-only"` and `contract.context_evidence`. A revision loop is a normal planning loop in every state-machine respect.

**Coding: `coding.source_kind`.**
- New coding sessions always write `source_kind`: `"approved_planning_loop"` (the existing path) or `"architect_plan_file"`.
- `session.coding_source_kind(coding)` is the **only** reader. It returns `"approved_planning_loop"` when the key is **absent**, which covers coding loops created before #51, and `"architect_plan_file"` for that value. Any other value returns `"unknown"`, and every display treats unknown as an integrity failure. The approved-loop kind is never inferred from the presence of `approved-plan.md` or `source_loop_id`.
- Architect-plan sessions store `source_loop_id: null`, `plan_sha256`, `plan_bytes`, `source_brief: null` and `source_brief_decision: "not_applicable"`.
- `SOURCE_BRIEF_DECISIONS` gains `"not_applicable"`; existing values are unchanged.
- The approved-loop path adds only `source_kind`. Its `approved-plan.md`, provenance, events and prompts stay byte-identical apart from that one additive key (pinned in Testing).

**Strict status allowlists.**
- `revision` is never added to `_LOOP_STATUS_ALLOWED_KEYS`.
- New `session.revision_status_view(revision, loop_dir)` returns `{source_loop_id, source_feature, source_round, source_had_brief, plan: {artifact, sha256, bytes}|null, plan_check, review: …|null, review_check}`. The views are positionally bound like `brief_status_view`; the checks are computed with the fixed-name verifier; strings are type-checked (non-str becomes null).
- `submit.coding_status_view()` gains `source_kind`. For `architect_plan_file` it also gains `plan_view` (`{artifact: "architect-plan.md", sha256, bytes}` or null) and `plan_check`. The approved-loop projection is otherwise unchanged.

### D2 — Fixed names and verification helpers

**Constants in `session.py`:**
- `SOURCE_APPROVED_PLAN_FILENAME = "source-approved-plan.md"`
- `SOURCE_APPROVAL_REVIEW_FILENAME = "source-approval-review.md"`
- `ARCHITECT_PLAN_FILENAME = "architect-plan.md"`
- `MAX_PLAN_BYTES = 1_048_576` (1 MiB). This bounds every plan-like input and every source copy.

**Generalize the brief verifier rather than duplicating it.**
- `verify_fixed_artifact(loop_dir, ref, expected_name, max_bytes)` holds today's `verify_brief` body. The allowlist check (`expected_name in FIXED_ARTIFACT_NAMES`, now the brief names plus the three new names) stays inside it.
- `verify_brief(loop_dir, ref, expected_name)` becomes a one-line wrapper with `MAX_BRIEF_BYTES`. Its behaviour and results are identical, and all existing brief tests still pass.
- Likewise `read_verified_fixed_artifact()` and `fixed_artifact_view(ref, expected_name)`, with `brief_status_view` delegating.
- **Positional binding:** each ref must name exactly its position's constant. A `revision.plan` ref whose `artifact` is `"architect-brief.md"` returns `invalid_ref`. No path is ever taken from session metadata.

**Shared input validator (CLI and Dashboard):** `session.read_repo_file(repo_root, path, *, max_bytes, what)`. It returns the validated bytes and raises `ValueError` / `FileNotFoundError`. Steps:
1. Build the absolute path: a relative path joins onto `repo_root` (Dashboard) or the cwd (CLI, the caller passes `Path.cwd() / p`).
2. Refuse `is_symlink()` or `_is_reparse_point()` on the final component **before** any `exists` / `stat` / `open`, the same order as `read_brief_file`.
3. `resolved = abs.resolve(strict=True)`. Missing gives `FileNotFoundError`.
4. Require `repo_root.resolve()` in `resolved.parents`.
5. Require `normcase(normpath(abs)) == normcase(str(resolved))`, so any link or junction in an intermediate directory is refused, not just the last component.
6. Refuse anything under `<repo>/.gator/loops/`. Loop residue reaches a new loop only through `--revise-from` / `--from-loop`, so a planning loop's unapproved plan cannot be passed in as an "Architect-supplied" file, and a source loop's files cannot become a sketch.
7. Require a regular file and `st_size <= max_bytes` before reading.
8. Read `max_bytes + 1` once, then `validate_text_bytes(data, max_bytes, what)`: no NUL, UTF-8, non-blank.

`validate_brief_bytes` becomes `validate_text_bytes(data, MAX_BRIEF_BYTES, "Architect brief")`. Its messages stay identical; pinned by the existing brief tests.

**Writing source copies:** `host._write_fixed_artifact(loop_dir, name, data, max_bytes)` generalizes `_write_brief`. It writes the bytes, makes the file read-only, re-verifies through `verify_fixed_artifact` and returns metadata. `_write_brief` delegates to it.

### D3 — CLI grammar (no overloading of `--from-loop`)

| Start | Arguments | Rejected combinations (exit 1, `Error:`, before any side effect) |
|---|---|---|
| Ordinary planning | `--sketch S [--brief B]` | unchanged |
| **Revision planning** | `--sketch S --revise-from <approved planning loop id> [--brief B]` | `--revise-from` with `--mode coding`; `--revise-from` without `--sketch`; with `--source-brief` |
| Coding from approved loop | `--mode coding --from-loop ID [--source-brief keep\|drop] [--brief B]` | unchanged |
| **Coding from Architect plan** | `--mode coding --plan-file P [--brief B]` | `--plan-file` with `--from-loop` (both); neither of them; `--plan-file` with `--source-brief`; `--plan-file` on planning |

- `_cmd_start` checks these combinations first. `host.init_loop()` re-checks them and raises `ValueError`, because it is the authority shared with the Dashboard.
- Help text names the source kinds: `--plan-file` reads "Architect-supplied implementation plan (Markdown, UTF-8, ≤ 1 MiB). Recorded as Architect-supplied; it is not planning-loop approved."

**`init_loop(..., revise_from=None, plan_file=None, plan_bytes=None)` / `start_loop(...)` pass-through:**
- `plan_file` is the CLI path; `plan_bytes` is pre-validated Dashboard bytes. At most one of them is allowed, and neither with `from_loop`.
- **Revision branch** (planning, `revise_from` set):
  1. Validate `revise_from` with `_SOURCE_LOOP_ID_RE`.
  2. Read the sketch through `read_repo_file(repo_root, sketch, max_bytes=MAX_PLAN_BYTES, what="Revision sketch")`.
  3. Check the revision-sketch structure (D3a).
  4. Capture the source (D3b).
  5. mkdir. Write `sketch.md` from the **validated bytes** (not `copy2`), then `source-approved-plan.md`, `source-approval-review.md`, and the optional `architect-brief.md`, each verified.
  6. Tokens, `create_session(..., revision=…)`, events.
  7. On any failure after mkdir, `_remove_partial_loop`.
- **Ordinary planning** (no `revise_from`) is byte-for-byte unchanged: it still uses `copy2` and the existing checks.

**D3a — Revision sketch structure.** This is how the sketch "explicitly identifies" Baseline, Preserve, Reconsider and Required context. `submit.revision_sketch_problems(text, source_loop_id)` reuses the fence-aware `_h2_titles` and the section-body extraction used by `context_checked_problems`. It requires:
- exactly one level-2 heading each, case-insensitive: `Baseline`, `Preserve`, `Reconsider`, `Required Context`;
- every body non-empty once comments and blank lines are removed, and not a bare placeholder (the same placeholder rule as Context Checked);
- the `Baseline` body containing the exact `source_loop_id` string, so the sketch names the loop it revises and a sketch written for loop A cannot start a revision of loop B.

It returns reasons. The start fails with `ValueError("Revision sketch rejected: …")` before any directory is created.

**D3b — `_capture_approved_planning_source(source_dir, from_loop, want_review, source_brief)`.** This replaces the body of `_read_approved_source`, which becomes a wrapper returning the same tuple, so the coding path is unchanged.
- Under the source's `with_session_lock` read-only callback it runs today's checks: canonical id equals `session.loop_id`, `loop_mode == "planning"`, stage `plan_approved`, and `plan.current.md` a non-symlink, non-empty regular file.
- **New:** `source_dir` is also refused when it is a reparse point, in addition to `is_symlink`. This is a hardening that applies to both paths.
- **New:** each read is capped at `MAX_PLAN_BYTES`; a larger source plan is rejected.
- **For revision** (`want_review=True`) it also requires `current.findings` to be a dict with a `turn_id`, and `findings.current.md` to be a non-symlink, non-reparse, non-empty regular file of at most `MAX_PLAN_BYTES`. That file is the approval review written in the approving transaction. It captures the bytes, the label `source_review_artifact` (from the matching turn's `artifact_path`, a str that matches `^findings\.round-\d+\.md$`, else null), `round`, `feature` and whether `brief` is not None.
- The callback still returns `None`, so **the source session is never written**. Revision never opens or verifies the source brief.

**Lock order** is unchanged: the caller holds `start.lock` (CLI `start_loop` / Dashboard start) and refuses on any active loop; then the source session lock; then the new directory. `plan_approved` stays final. A revision is a new loop, never a reactivation of the source (Resumable Terminal Stage TRIPWIRE).

**Coding from an Architect plan:** `_init_coding_loop` is split into source capture plus a shared creation tail.
1. `plan_bytes = read_repo_file(repo_root, plan_file, max_bytes=MAX_PLAN_BYTES, what="Architect-supplied plan")`, or the Dashboard's pre-validated bytes. Read once.
2. `gitsnap.snapshot(repo_root)` must be ok, exactly as today.
3. mkdir. Write `architect-plan.md` through `_write_fixed_artifact` (copy, read-only, re-read, SHA-256 and size verify).
4. Optional new `architect-brief.md`.
5. `coding = {source_kind: "architect_plan_file", source_loop_id: None, plan_sha256, plan_bytes, base_head, base_tree, generations: [], approval: None, source_brief: None, source_brief_decision: "not_applicable"}`.
6. Tokens, session, a `loop_started` event.
7. Any failure removes the partial directory.

The approved-loop path keeps writing `approved-plan.md` and gains only `coding.source_kind = "approved_planning_loop"`.

### D4 — Briefs for revision loops

- **No automatic carry-forward.** The revision sketch is the new Architect direction, and the CLI has no `--source-brief` for revision (rejected).
- An optional new `--brief` / Dashboard brief is stored as the loop's own `architect-brief.md`, as for any planning loop.
- When the source had a brief, status prints a neutral note: "Source loop had an Architect brief; not carried forward. Read it in the source loop only if the revision sketch requires it."
- Earlier rounds and decision documents get the same rule: not listed as required reading, and recorded only in the new loop's `## Context Checked` when actually read.

### D5 — Status, prompts and events

**CLI status (model and Architect views; text plus additive JSON):**
- **Revision loops**, after the brief lines:
  - `Revision of: <source_loop_id> (round <n>, approved)`
  - `Baseline plan: <loop_dir>/source-approved-plan.md [OK] (required reading)`
  - `Baseline approval review: <loop_dir>/source-approval-review.md [OK] (required reading)`
  - The paths are the fixed names. A non-ok check prints the brief markers (`[!!] DIGEST MISMATCH`, and so on) with "do not rely on it; escalate to the Architect" for model roles.
  - JSON: `revision: {source_loop_id, plan: {path, check}, review: {path, check}, source_had_brief}`.
- **Draftor action text (revision, `plan_drafting`):** "Action: Draft a full replacement plan (not a delta) from the revision sketch and the baseline approved plan." The sketch path, the baseline paths and `submit-draft` follow. Revision rounds use the existing text.
- **Coding, Architect-plan kind:**
  - `_print_coding_action_prompt` prints `Architect-supplied plan: <loop_dir>/architect-plan.md [OK]` (the integrity marker as above) **instead of** `Approved plan:`, plus the line "This plan was supplied by the Architect; it did not pass a planning-loop review."
  - JSON adds `coding_source: {kind, plan: {path, check}}`.
  - Status prints `Plan source: Architect-supplied plan file`.
  - The approved-loop text is byte-identical to today's.
- **Brief helpers:** `_brief_entries` is unchanged for revision (no source brief). For the Architect-plan kind there is no source-brief position, and `not_applicable` prints nothing.

**Dashboard `/prompt` (pointer lines only, never content):**
- revision: "This is a revision planning loop: read the baseline approved plan and its approval review first (status shows the paths)."
- Architect-plan coding: "This coding loop implements an Architect-supplied plan (not planning-loop approved); status shows its path."
- The existing brief line is unchanged.

**Events:** the `loop_started` event gains additive fields.
- **Revision:**
  - fields: `revision_source_loop_id`, `source_plan_sha256` / `source_plan_bytes`, `source_review_sha256` / `source_review_bytes`;
  - detail: "Revision planning loop initialized from <id> (baseline plan sha256 <12>, approval review sha256 <12>)".
- **Architect plan:**
  - fields: `mode: "coding"`, `source_kind: "architect_plan_file"`, `plan_sha256`, `plan_bytes`, and **no** `source_loop_id`;
  - detail: "Coding loop initialized from an Architect-supplied plan (sha256 <12>, base <12>)".
- **Approved-loop coding:** its event adds `source_kind`; its detail is unchanged.
- No content is ever written to events.

### D6 — Dashboard entry points and labels

**Server (`gator-dashboard.py`):**
- **`_handle_loop_start`:**
  - **Planning:** accept optional `revise_from` (non-blank str). Reject it alongside `from_loop`, `plan_path` or `source_brief`, with a 400 before any lock. When present, the sketch goes through `read_repo_file` (via `init_loop`) rather than the existing ad-hoc containment check, which stays for ordinary planning.
  - **Coding:** accept `plan_path` (non-blank str) **or** `from_loop`, exactly one (400 for both or neither). `source_brief` with `plan_path` is a 400. `plan_path` is validated with `read_repo_file(repo_root, …)` **before** `start.lock`, giving an early, honest 400. The validated bytes go to `init_loop(plan_bytes=…)`, so the file is read once.
  - `init_loop` `ValueError` / `FileNotFoundError` stays a 400, with no partial directory.
- **`_handle_loop_status`:**
  - `safe["revision"] = revision_status_view(...)`, only when `session.revision` is a dict;
  - `coding_status_view` carries `source_kind` / `plan_view` / `plan_check`.
- **`_handle_loop_list`:** items gain additive `revision_of` (str or null) and `coding_source_kind` (normalized or null) for sidebar labels.
- **`_LOOP_ARTIFACT_ALLOWLIST`** gains `source-approved-plan.md`, `source-approval-review.md` and `architect-plan.md`.
- **`/prompt`** gets the pointer lines above.

**UI (`views/loop.js`):**
- **Create form, Loop type** becomes three radios:
  - "Planning — draft a plan from a sketch";
  - "Revision planning — revise an approved plan" (new; the sketch picker plus a "Approved planning loop to revise" select reusing `loadSourcePicker`'s approved list, with **no** brief keep/drop control). The hint reads: "The approved plan and its approval review are copied into the new loop as required reading. The source loop is not changed. The sketch needs Baseline, Preserve, Reconsider and Required Context sections, and Baseline must name the source loop.";
  - "Coding — implement a plan", with a **Plan source** radio group:
    - "Approved planning loop" (the existing select and brief control);
    - "Architect-supplied implementation plan" (a path picker reusing `/sketch-sources` + manual entry; hint: "Recorded as Architect-supplied. It is not planning-loop approved. No source brief applies.").
- **Create-form rules:**
  - Choosing the Architect plan hides and removes the source-brief control and bumps `_create.sourceRev`, so an in-flight `loadSourceBrief` cannot write back.
  - `updateCreateEnabled` adds: revision needs an approved source and a sketch, and is blocked while the picker is loading; Architect plan needs a path.
  - The POST body sends exactly the fields for the chosen path.
- **Revision action:** for a selected planning loop at `plan_approved`, `renderControls` renders a **New revision planning loop** button where it currently renders nothing.
  - Clicking it sets `_state.mode = "create"`, `_state.createPreset = {kind: "revision", from: loopId}` and bumps the generation. The create form opens with Revision selected and the source preselected; the preset is cleared once applied.
  - `controlsFingerprint` adds the `plan_approved && mode === "planning"` flag.
  - An active loop elsewhere is still refused by the server (409); the existing "Open active loop" recovery applies.
- **Inspection:**
  - A new `sourceEntries(status)` generalizes `briefEntries`. **Revision** lists, before the sketch, "Baseline — source approved plan (required reading)" and "Baseline — source approval review (required reading)", with a `[!! …]` suffix and no link when the check is not ok or the view is null. The **Architect-plan** coding list starts with "Architect-supplied plan (not planning-loop approved)" instead of `approved-plan.md`.
  - The artifact order becomes:
    - revision: `[briefs…, source-approved-plan.md, source-approval-review.md, sketch.md, plan.current.md, findings.current.md, …]`;
    - Architect-plan coding: `[briefs…, architect-plan.md, implementation.current.md, findings.current.md, …]`.
  - Labels come only from the projection, never from filenames. `isSummaryArtifact` includes the three new names.
  - The header shows "Revision of <source feature> (<source id>)" for revision loops, and `headerFingerprint` adds `revision.source_loop_id`.
  - The outcome header gets the same line for terminal loops.
  - `renderCodingRegion`: its first row becomes "Plan source". It reads "Approved planning loop <id> (sha256 …)", unchanged for that kind, or "Architect-supplied plan file (sha256 …, N bytes) [OK]" / "[!! DIGEST MISMATCH]" (text, never colour). An `unknown` source kind reads "[!! UNKNOWN SOURCE KIND]". `codingFingerprint` adds `source_kind` and `plan_check`.
  - `artifactsFingerprint` adds the revision views and checks plus the coding source kind and check, so identical polls stay mutation-free.
  - Sidebar cards add a muted "revision of <id>" / "Architect plan" text line from the `/loops` fields.

### Protocol and participant documents (byte-identical pairs)

These are participant-facing contract changes, made in both copies of each pair:
- `procedures/gator-loop-protocol.md` (`.gator/.includes/` and `templates/gator-starter/`): a short **Revision Planning Loops** subsection under Step 2. It covers the baseline files as required reading, a full replacement plan (not a delta), no automatic source brief or earlier rounds, and the new loop's Context Checked as the record. The Coding Loops section adds one paragraph: a coding loop may implement `architect-plan.md` (Architect-supplied, not planning-loop approved) instead of `approved-plan.md`, and status names the one that applies.
- `reference-notes/loop-artifact-formats.md` (both copies): a **Revision Sketch** template with the four required sections and a Baseline example naming the source loop id.
- `/loop-join` (`.claude/commands/loop-join.md` and the template copy): extend the Draftor first-turn and coding reading bullets. Revision reads the two baseline files; a coding loop reads `approved-plan.md` **or** `architect-plan.md`, whichever status lists.

No state is added, so the protocol state tables and their pins are unchanged.

## Changes

### 1. Session layer — `src/gator_command/scripts/loop/session.py`
- New constants: `SOURCE_APPROVED_PLAN_FILENAME`, `SOURCE_APPROVAL_REVIEW_FILENAME`, `ARCHITECT_PLAN_FILENAME`, `MAX_PLAN_BYTES`, `FIXED_ARTIFACT_NAMES`, `CODING_SOURCE_KINDS`; `SOURCE_BRIEF_DECISIONS` gains `not_applicable`.
- New functions: `validate_text_bytes()`, `read_repo_file()`, `verify_fixed_artifact()`, `read_verified_fixed_artifact()`, `fixed_artifact_view()`, `coding_source_kind()`, `revision_status_view()`.
- Wrappers with unchanged behaviour: `validate_brief_bytes`, `verify_brief`, `read_verified_brief`, `brief_status_view`.
- `create_session(..., revision=None)`: adds the block; planning only.

### 2. Host — `src/gator_command/scripts/loop/host.py`
- `init_loop(..., revise_from=None, plan_file=None, plan_bytes=None)` with the argument rules above.
- New `_init_revision_planning_loop()`.
- `_capture_approved_planning_source()`, with `_read_approved_source()` kept as a wrapper.
- `_init_coding_loop()` split into source capture and a shared creation tail, so both coding kinds share one atomic sequence.
- `_write_fixed_artifact()`, with `_write_brief` delegating.
- `start_loop(..., revise_from=None, plan_file=None)` pass-through.

### 3. Submit helpers — `src/gator_command/scripts/loop/submit.py`
- New `revision_sketch_problems(text, source_loop_id)`, beside `context_checked_problems`, reusing `_h2_titles` and the body/placeholder helpers.
- `coding_status_view()` gains `source_kind`, `plan_view` and `plan_check`.

### 4. CLI — `src/gator_command/scripts/loop/cli.py`
- `start` gains `--revise-from` and `--plan-file`; `_cmd_start` performs the combination checks.
- New `_revision_entries()` / `_print_revision()` / `_revision_json()`. `_print_action_prompt` gets the revision Draftor text. `_print_coding_action_prompt` branches on `coding_source_kind`.
- Architect status prints the plan-source line, and the JSON additions above.

### 5. Dashboard server — `src/gator_command/scripts/gator-dashboard.py`
- `_handle_loop_start`: `revise_from` and `plan_path`, with exclusivity and validation before the lock.
- `_handle_loop_status`: the `revision` view.
- `_handle_loop_list`: `revision_of` and `coding_source_kind`.
- `_LOOP_ARTIFACT_ALLOWLIST`: the three new names.
- `_handle_loop_prompt`: the pointer lines.

### 6. Dashboard UI — `src/gator_command/scripts/dashboard/views/loop.js` and `dashboard.css`
- **`loop.js`:**
  - create form: three loop types, the coding plan-source group, the revision source select, preset handling;
  - `renderControls`: the revision button; `sourceEntries()`;
  - `renderArtifacts` ordering; header, outcome-header and coding-region rows;
  - fingerprint additions; sidebar labels; `EVENT_LABELS` unchanged (`loop_started` detail carries the text).
- **`dashboard.css`:** reuse the existing `.loop-create-*`, `.loop-brief-note` and `.loop-coding-row` classes; add only `.loop-card-source` (muted text line).

### 7. Participant documents (pairs)
- `.gator/.includes/procedures/gator-loop-protocol.md` and `src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md`.
- `.gator/.includes/reference-notes/loop-artifact-formats.md` and the template copy.
- `.claude/commands/loop-join.md` and `src/gator_command/templates/gator-starter/commands/loop-join.md`.

### 8. Tests (new and extended)
- `tests/test_loop_revision.py` (new), `tests/test_loop_coding_plan_file.py` (new), additions to the existing coding / brief / CLI tests, `tests/test_dashboard_loop_coding.py` (server), `tests/test_dashboard_ui/test_loop_revision_ui.py` (new), and additions to `test_loop_coding_ui.py`. See Testing.

### 9. Release and evidence (last)
- Once behaviour and tests are complete: `commit_draft.md` bullets and frontmatter, plus a CHANGELOG / roadmap note if the release procedure in use calls for one.

## Dependencies and Ordering

1. **Session layer (Change 1)** and its unit tests. The generalized verifiers must pass the existing brief suite unchanged before anything builds on them.
2. **Host plus submit helpers (2, 3)**: revision capture and creation, and the Architect-plan coding source. Includes the atomic-failure and immutability tests.
3. **CLI (4)** and the docs pairs (7) together: the CLI text and the protocol text are pinned by the drift guards.
4. **Dashboard server (5)**, which depends on 1–3.
5. **Dashboard UI (6)**, which depends on 5.
6. Full suites, then release evidence (9).

Charter updates follow each file edit, per constitution step 5. **Parallelizable:** 7 alongside 4; the UI tests alongside the UI changes.

## Assumptions, Risks, and Required Architect Decisions

**Non-blocking assumptions (reversible):**
- **A1:** The approval review is the source's `findings.current.md` at `plan_approved`, cross-checked by a non-null `current.findings`. It is copied under the source session lock in the same read as the plan.
- **A2:** The revision sketch must contain four `##` sections (Baseline, Preserve, Reconsider, Required Context), and Baseline must contain the exact source loop id. This makes "explicitly identify" mechanically checkable. A rejected sketch fails before any side effect with the missing items listed.
- **A3:** `MAX_PLAN_BYTES = 1 MiB` for Architect plan files, revision sketches and source copies. Briefs keep 32 KiB.
- **A4:** Paths under `.gator/loops/` are refused as Architect plans or revision sketches. Loop residue enters new loops only through the explicit source arguments.
- **A5:** Ordinary planning sketches keep their existing, looser CLI read (`copy2`, no containment on the CLI) for byte compatibility. Only revision sketches use `read_repo_file`. Tightening ordinary sketches could be a follow-up.
- **A6:** The source-directory reparse-point refusal also applies to existing `--from-loop` starts, as a hardening. Today they refuse only `is_symlink`.
- **A7:** A revision of a revision is allowed. The source only needs to be an approved planning loop; lineage is the chain of `revision.source_loop_id`.

**Risks:**
- **Breadth:** about ten files across six layers. This is mitigated by the ordering above, one shared validator and verifier, and existing patterns (`_init_coding_loop` ordering, brief projection style).
- **Generalizing the brief verifier** could regress #43. It is mitigated by wrappers with identical signatures and messages, and by running the full brief suite before the dependent steps.
- **Doc-pair drift:** byte-identity tests fail if one copy is missed. Both copies of each pair are edited in one step.
- **Dashboard UI complexity:** the create form gains a third type and a sub-choice. It reuses the existing double stale-guard pattern, and the plan-source switch bumps `sourceRev`.

**Blocking decisions:** none. The sketch's Decisions 1–5 are settled in D1–D6 above.

## Testing

**`tests/test_loop_revision.py` (new):**
- **Happy path:** an approved planning-loop fixture plus a valid revision sketch creates a separate planning loop with:
  - `mode` `planning-only`, `contract.context_evidence`, and stage `plan_drafting`;
  - `revision` metadata matching the source bytes' SHA-256 and size;
  - `source-approved-plan.md` and `source-approval-review.md` byte-equal to the source files and read-only on POSIX;
  - `sketch.md` byte-equal to the validated input;
  - the additive `loop_started` fields.
- **Source immutability:** the source loop's `session.json`, `events.jsonl` and every artifact are hashed before and after: byte-identical, with an unchanged mtime set.
- **Pinned baseline:** after creation, rewriting or deleting the source `plan.current.md`, `findings.current.md` or the whole source directory leaves `status` / `revision_status_view` checks `ok` and the copies unchanged.
- **Atomic rejections**, each leaving no new loop directory and an untouched source:
  - invalid ids (separators, `..`, trailing dot, case variant);
  - a coding source;
  - a non-approved stage (each planning stage);
  - `max_rounds_exceeded`;
  - a missing, empty or symlinked `plan.current.md` / `findings.current.md`;
  - `current.findings` null;
  - a source over `MAX_PLAN_BYTES`;
  - the sketch: outside the repo, symlink, junction (Windows-only skip elsewhere), intermediate-directory link, under `.gator/loops/`, directory, empty, non-UTF-8, NUL, oversize, missing sections, a placeholder body, Baseline naming another loop;
  - `--revise-from` with `--mode coding` or `--source-brief`;
  - a concurrent active loop (start.lock / `find_active_loop`);
  - a digest mismatch injected into `_write_fixed_artifact` (monkeypatch).
- **Positional binding:** a session with `revision.plan.artifact = "architect-brief.md"` gives `invalid_ref`, with no read outside the fixed name.
- **CLI:** `status` text and JSON for model and Architect roles, the Draftor revision action text, and the `[!!]` markers after tampering.

**`tests/test_loop_coding_plan_file.py` (new):**
- **Happy path:** `architect-plan.md` is byte-equal; `coding.source_kind == "architect_plan_file"`, `source_loop_id is None`, `plan_sha256` / `plan_bytes` set, `source_brief_decision == "not_applicable"`, and the Git base and tree are bound. `submit-implementation` / review / approve still work end to end.
- **Atomic rejections:** both or neither of `--from-loop` / `--plan-file`; `--source-brief` with `--plan-file`; `--plan-file` on planning; outside-repo, symlink, junction, intermediate link, `.gator/loops/` path, directory, empty, whitespace-only, non-UTF-8, NUL, a `MAX_PLAN_BYTES + 1` file; Git unborn / conflict; a copy-digest failure; an active-loop collision.
- **Status and prompt:** "Architect-supplied plan" wording and **no** "Approved plan" / `source_loop_id` text.
- **Byte-compatibility pin:** a `--from-loop` coding start produces the same `approved-plan.md`, the same coding block keys plus `source_kind` only, the same event detail, and the same status and prompt text as a recorded fixture.
- **Legacy:** a pre-#51 coding session with no `source_kind` projects as `approved_planning_loop`; an unknown value projects as `unknown` and renders as an integrity failure.

**Existing suites:** `tests/test_loop*.py` (brief, coding, context-evidence and drift-guard tests: `TestDriftGuards`, `TestWaitHandoffAlignment`, `TestParticipantDocs`), plus `tests/test_dashboard_loop_coding.py` and the dashboard server loop tests. Additions there:
- `/loops/start` with `revise_from` / `plan_path` exclusivity, giving 400 before any lock and no directory;
- `/status` `revision` and `coding.source_kind` projections, never through the generic allowlist (pinned: `revision` not in `_LOOP_STATUS_ALLOWED_KEYS`);
- artifact-route allowlist for the three names (and a 404 for an unlisted name);
- `/prompt` pointer lines carrying no content.

**Dashboard UI (Playwright):**
- `tests/test_dashboard_ui/test_loop_revision_ui.py` (new):
  - the approved-loop button opens the preset create form; Revision create posts `revise_from` plus `sketch_path`;
  - the inspector order and labels; the header "Revision of" line; a tampered copy shows `[!! DIGEST MISMATCH]` as text with no link;
  - identical polls cause zero mutations (MutationObserver).
- `test_loop_coding_ui.py` additions:
  - the Plan source switch hides the source-brief control, and a stale `loadSourceBrief` cannot write after the switch;
  - Architect-plan create posts `plan_path` with no `from_loop` / `source_brief`;
  - the coding region "Plan source" row text and integrity marker;
  - the inspector lists `architect-plan.md` with the Architect-supplied label;
  - zero-mutation polls.
- Then the full `tests/test_dashboard_ui` suite.

**Manual:** start one loop of each kind from the CLI and the Dashboard on this repo. Inspect status, prompts and timeline. Confirm the source loop directory hash is unchanged.

## Charter Impact

- **`.gator/charters/scripts-loop.md`:**
  - `create_session` gains the `revision` block and `coding.source_kind`;
  - new entries: fixed-artifact helpers (`verify_fixed_artifact` and others, with the brief helpers as wrappers), `read_repo_file` / `validate_text_bytes`, `coding_source_kind`, `revision_status_view`, `revision_sketch_problems`, `_init_revision_planning_loop`, `_capture_approved_planning_source`, `_write_fixed_artifact`;
  - updated: `init_loop`, `_init_coding_loop` (two source kinds, shared tail), `start_loop`, `_cmd_start` grammar, status and prompt text, `coding_status_view`;
  - **new TRIPWIRE "Source provenance is explicit and positional (#51)":** source kind is never inferred from filenames or ids; every stored copy is verified only at its fixed name; an Architect-supplied plan never claims planning approval; a revision never writes the source loop;
  - update the Architect-brief TRIPWIRE to reference the shared fixed-artifact verifier;
  - Cross-Vendor Orientation notes the new protocol, format and `/loop-join` content.
- **`.gator/charters/scripts-dashboard.md`:** `_handle_loop_start` (the `revise_from` / `plan_path` rules and validation before the lock), `_handle_loop_status` (the `revision` serializer; `revision` never in the generic allowlist), `_handle_loop_list` additive fields, the artifact allowlist additions, `/prompt` pointer lines.
- **`.gator/charters/scripts-dashboard-ui.md`:** create-form loop types and plan-source group, the revision action and preset, `sourceEntries`, artifact ordering and labels, header / outcome / coding-region rows, fingerprint additions, sidebar source labels.
- **`.gator/charters/scripts-cross-cutting.md`:** the Shipped-Copy Synchronization note covers the new protocol, format and `/loop-join` content under the existing drift guards; the CLI JSON note adds the additive `revision` / `coding_source` status fields.
- **`.gator/charters/INDEX.md`:** no change. No new module files are added.
