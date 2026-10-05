# Implementation: Revision Planning from Approved Plans and Architect-Supplied Coding Plans (#51)

## Executive Summary

- **What changed:** two explicit plan sources.
  - `gator loop start --sketch S --revise-from <approved loop>` (and the Dashboard **New revision planning loop** action) creates a new planning loop with digest-pinned `source-approved-plan.md` and `source-approval-review.md`.
  - `--mode coding --plan-file P` (and the Dashboard **Plan source** switch) creates a coding loop from `architect-plan.md`, recorded as `source_kind: architect_plan_file`.
- **Key decision:** provenance is recorded (`session.revision`, `coding.source_kind`) and verified only at fixed names. One validator (`read_repo_file`) guards every Architect-named file. The source loop is only read, under its own session lock.
- **Main risk:** breadth (six layers). It is mitigated by extending the existing atomic `_init_coding_loop` ordering, and by brief helpers that become wrappers with unchanged behaviour.
- **Verified:** 1162 loop and dashboard-server tests and 408 Dashboard UI tests (the full suites), plus the drift guards.

## Implementation Summary

The approved plan's four modules are kept, per the coding-loop Architect brief.

**1. Source validation and immutable capture** (`loop/session.py`, `loop/host.py`)
- `read_repo_file(repo_root, path, *, max_bytes, what)` is the single input boundary, shared by the CLI and the Dashboard. It checks, in order:
  - no symlink or reparse point on the final component, checked before resolve;
  - the resolved file is inside the repo **and** equal to the lexical path, which catches a link or junction in any directory;
  - nothing under `.gator/loops/`;
  - a regular file, with the size checked first, then a single read;
  - `validate_text_bytes` (UTF-8, no NUL, non-blank).
- `verify_fixed_artifact` / `read_verified_fixed_artifact` / `fixed_artifact_view` generalize the #43 brief verifier. `verify_brief`, `read_verified_brief`, `brief_status_view` and `validate_brief_bytes` are now thin wrappers whose results and messages are unchanged; the brief suite passes untouched.
- **Host functions:**
  - `_source_loop_dir` (shared id and directory check; now also refuses a reparse-point source directory);
  - `_capture_approved_planning_source` (locked, read-only), with `_read_approved_source` kept as a wrapper;
  - `_read_source_file` (no links, non-empty, ≤ 1 MiB);
  - `_write_fixed_artifact` (write, read-only, re-verify), which `_write_brief` now delegates to;
  - `_issue_tokens`;
  - `_init_revision_planning_loop`.
- `_init_coding_loop(..., plan_bytes=…)` takes the second source kind and keeps the approved-loop branch byte-identical except for the added `source_kind`.

**2. Session and provenance projection**
- `create_session(revision=…)` is planning only. `coding_source_kind()` is the only reader: absent means approved-loop, unknown is an integrity failure. `revision_status_view()` is built field by field.
- `submit.revision_sketch_problems()` is fence-aware and requires exactly one each of Baseline, Preserve, Reconsider and Required Context, each meaningful, with Baseline containing the source id. It shares `_meaningful_section()` with Context Checked.
- `coding_status_view()` adds `source_kind`, plus `plan_view` / `plan_check` for an Architect plan.
- `loop_started` carries additive provenance fields and never content.

**3. Creation surfaces**
- **CLI.**
  - `start --revise-from` / `--plan-file`. `_cmd_start` refuses bad combinations before any side effect, and `init_loop` re-checks them.
  - Status prints `Revision of:`, `Baseline plan` and `Baseline approval review` with `[OK] (required reading)` or `[!!] …` markers, or `Plan source: Architect-supplied plan file`. JSON gains `revision` / `coding_source`.
  - The Draftor action text says "full replacement plan (not a delta)", or "did not pass a planning-loop review".
- **Dashboard server.**
  - `/loops/start` accepts `revise_from` / `plan_path` with exclusivity 400s before any lock, and runs `read_repo_file` before `start.lock`. Plan bytes are passed through, never re-read, and the revision sketch is joined lexically, never `.resolve()`d first.
  - `/status` adds `revision` through its serializer; it is not in the generic allowlist (pinned).
  - `/loops` adds `revision_of` / `coding_source_kind`, the artifact allowlist gains the three fixed names, and `/prompt` gets pointer lines.
- **Participant documents** (byte-identical pairs): the protocol (Revision planning loops; Architect-supplied plans), `loop-artifact-formats.md` (Revision Sketch template) and `/loop-join`.

**4. Dashboard inspection** (`views/loop.js`, `dashboard.css`)
- **Create form.**
  - It has three loop types. The coding **Plan source** radio switches between approved loop and Architect plan.
  - `setPlanSource()` bumps `sourceRev`, so a late source-brief response cannot write. `loadSourceBrief()` also returns unless the form is in coding mode with the approved source.
  - The POST sends exactly one source's fields.
- **Revision action.** `renderRevisionControl()` appears only for an approved planning loop and applies a one-shot create preset.
- **Inspection.**
  - `codingSourceKind()` mirrors the server normalization, and `sourceEntries()` labels positions from projections only.
  - Non-linked or corrupt positions become text notes.
  - The header shows "Revision of …", and the coding region's first row is "Plan source" with an `[OK]` / `[!! …]` marker.
  - The fingerprints are extended, so identical polls remain mutation-free.

## Charter Updates

- **`scripts-loop.md`:**
  - new entries: the fixed-artifact and source helpers, `_init_revision_planning_loop` and its helpers, and `revision_sketch_problems`;
  - updated: `create_session`, `init_loop` source-kind rules, the `_init_coding_loop` restructuring, `start_loop`, the `_cmd_start` grammar and provenance lines, `coding_status_view`, and the Owns line;
  - new **TRIPWIRE: Source Provenance Is Explicit and Positional (#51)**;
  - the Cross-Vendor Orientation now lists the doc-pair additions.
- **`scripts-dashboard.md`:** the `/loops/start` source-kind rules and validation-before-lock, the `revision` status serializer, the list fields, the allowlist names and the `/prompt` pointers.
- **`scripts-dashboard-ui.md`:** create-form loop types and plan source, the revision action and preset, inspection entries and notes, header and coding-region rows, fingerprints, sidebar labels, and the terminal "no controls" exception for the revision action.
- **`scripts-cross-cutting.md`:** the additive `revision` / `coding_source` status keys and `coding.source_kind`, and doc-pair coverage under the existing drift guards.
- **How I checked them against the code:** each entry was written right after its file edit (constitution step 5), and every function name cited exists in the staged files. `INDEX.md` needs no change, because there are no new modules.

## Verification

- **`pytest tests/test_loop*.py tests/test_dashboard_loop*.py tests/test_snapshot.py tests/test_multi_session.py`:** 1162 passed, 10 skipped, 2 xfailed (the pre-existing v1 compat xfails).
- **`pytest tests/test_dashboard_ui`** (full Playwright suite): first run, 404 passed and 4 failed. All four failures were existing pins of "a terminal loop shows no `.loop-ctrl-btn`", which the planned revision action intentionally changes. I narrowed them to `:not(.loop-ctrl-revise)` and added positive pins: the revision action appears only for `plan_approved` planning loops. The rerun of those tests gave 11 passed.
- **New tests** (per the coding brief: parametrized and reused rather than mechanically expanded):
  - `tests/test_loop_source_kinds.py`: 63 passed, 2 skipped. File symlinks need privilege on this Windows host; the junction and intermediate-link cases do run. It has:
    - one 11-case input-boundary table × both entry points (atomic, source tree byte-identical);
    - revision happy path, pinned baseline after source edit and deletion, source and sketch rejection tables, a digest-failure injection, positional binding, CLI text/JSON and tamper markers;
    - Architect-plan happy path and a full submit → approve lifecycle, argument tables, and CLI errors;
    - `source_kind` normalization, an approved-loop compatibility pin, the unknown-kind display, and the active-loop guard for both kinds.
  - `tests/test_dashboard_loop_sources.py`: a 13-case start-rejection table (atomic), revision and Architect-plan end-to-end (status projections, artifacts, prompt pointers carrying no content, list labels), and tamper → `plan_check: mismatch`.
  - `tests/test_dashboard_ui/test_loop_sources_ui.py`: 12 passed. It covers the revision POST shape with no brief control, the Architect-plan POST shape with Create disabled while the path is blank, a stale source-brief response dropped after the switch, the revision action preset, a 4-case inspector table (including tamper and unknown kind), plan-source row markers, and mutation-free polls.
- **Drift guards** (`test_loop.py`, `test_loop_context_evidence.py`, `test_loop_attention.py`, `test_packaging.py`): 453 passed. The pairs are `cmp`-identical.
- **Significance check** (public CLI, cross-module provenance, file-input security boundary). The case against shipping:
  - The Architect-plan path lets a coding loop skip the planning review, which could normalize unreviewed plans.
  - The mitigation is that every surface (status, prompt, header, inspector, event) says "Architect-supplied … not planning-loop approved", `source_loop_id` stays null, and staged-tree review and approval are unchanged.
  - **Compatibility:** pre-#51 coding sessions read as approved-loop sources. New coding loops add `source_kind` (additive in the session, `/status`, the event, and CLI JSON).
  - **Behaviour change:** a source loop directory that is a reparse point is now refused (assumption A6 in the approved plan).
- **Known gaps:**
  - No manual click-through on a live Dashboard; the Playwright coverage is the substitute.
  - POSIX symlink cases ran only as skips here and will run on the POSIX CI legs.

**Notes for the Reviewer (candidate scope):**
- **The diff includes commit `85f1489`.** This loop's captured base is `c1a5d4d`. On the Architect's direction ("Proceed in this loop"), the link-only timeline change was committed as `85f1489` before this implementation, so `git diff <base_tree> <staged_tree>` also shows that already-reviewed commit: its `loop.js`, `dashboard.css` and `test_loop_workspace.py` timeline hunks, `scripts-dashboard-ui.md` timeline text, a one-line `scripts-dashboard.md` note, its CHANGELOG `[Unreleased] ### Changed` entry, and its session snippet. To see only #51, use `git diff 85f1489 <staged_tree>`.
- **Procedure bullet kept out of the candidate.** On the Architect's direction ("Leave it alone"), the uncommitted `writing-implementation-plans.md` procedure bullet in both `loop-artifact-formats.md` copies is **not** staged. Those two files were staged from `HEAD` plus only the #51 Revision Sketch insertion (both copies are the same blob), so the working-tree copies differ from the candidate by that one bullet.
- **Hook-staged snippet.** `.gator/session-snippets/2026-10-04-gator-85f14890913df.json` was staged by the Gator hooks after `85f1489`. It is governance residue that normally travels with the next commit.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Base HEAD | `c1a5d4d824aaf751b0567089ec2099b1cf9b63e4` |
| Base tree | `188613563f005f956a8f89dc4ee85583533382c6` |
| Current HEAD | `85f14890913df187f8dc4255c6526e5d207d8890` (dev) |
| Staged tree (candidate) | `756f50bbcd96c81dac7cf40a13e9bf0a387ad8ef` |
| Changed paths vs base | 26 (A 5, M 21) |
| Unstaged / untracked residue | 950 other + 50 loop residue under `.gator/loops/` + 5059 truncated (none of it is part of the candidate) |

Review exactly this candidate with:

```text
git diff 188613563f005f956a8f89dc4ee85583533382c6 756f50bbcd96c81dac7cf40a13e9bf0a387ad8ef
```

Changed paths (status, path):

```text
M .claude/commands/loop-join.md
M .gator/.includes/procedures/gator-loop-protocol.md
M .gator/.includes/reference-notes/loop-artifact-formats.md
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-dashboard-ui.md
M .gator/charters/scripts-dashboard.md
M .gator/charters/scripts-loop.md
M .gator/commit_draft.md
A .gator/session-snippets/2026-10-04-gator-85f14890913df.json
A .gator/session-snippets/2026-10-04-gator-c1a5d4d824aaf.json
M CHANGELOG.md
M src/gator_command/scripts/dashboard/dashboard.css
M src/gator_command/scripts/dashboard/views/loop.js
M src/gator_command/scripts/gator-dashboard.py
M src/gator_command/scripts/loop/cli.py
M src/gator_command/scripts/loop/host.py
M src/gator_command/scripts/loop/session.py
M src/gator_command/scripts/loop/submit.py
M src/gator_command/templates/gator-starter/commands/loop-join.md
M src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md
M src/gator_command/templates/gator-starter/reference-notes/loop-artifact-formats.md
M tests/test_dashboard_loop_coding.py
A tests/test_dashboard_loop_sources.py
A tests/test_dashboard_ui/test_loop_sources_ui.py
M tests/test_dashboard_ui/test_loop_workspace.py
A tests/test_loop_source_kinds.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/.includes/reference-notes/loop-artifact-formats.md
.gator/artifacts/2026-08-25-blueprints-2-0-implementation-plan.md
.gator/artifacts/2026-08-25-dashboard-concierge-exploration.md
.gator/charters/scripts-charter-tooling.md
.gator/charters/scripts-enterprise-server.md
.gator/charters/scripts-pulse.md
.gator/charters/scripts-repo-update.md
.gator/charters/scripts-session-capture.md
.gator/inbox.md
.gator/runtime-pin.json
.gator/session-snippets/2026-08-23-gator-81d3ae283ba21.json
.gator/session-snippets/2026-09-03-gator-d1368338b3d05.json
.gitignore
.tmppytest-loop-live-race/gator_ui_fleet0/alpha/
.tmppytest-loop-live-race/gator_ui_fleet0/beta/
.tmppytest-loop-live-race/gator_ui_home0/.gator/dashboard-repos.json
.tmppytest-loop-live-race2/gator_ui_fleet0/alpha/
.tmppytest-loop-live-race2/gator_ui_fleet0/beta/
.tmppytest-loop-live-race2/gator_ui_home0/.gator/dashboard-repos.json
.tmppytest-loop-m2-lifecycle/test_architect_cannot_submit_d0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_architect_cannot_submit_d0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_architect_cannot_submit_d0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_architect_cannot_submit_d0/findings.md
.tmppytest-loop-m2-lifecycle/test_architect_cannot_submit_d0/plan.md
.tmppytest-loop-m2-lifecycle/test_architect_in_session_role0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_architect_in_session_role0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_architect_in_session_role0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_architect_in_session_role0/findings.md
.tmppytest-loop-m2-lifecycle/test_architect_in_session_role0/plan.md
.tmppytest-loop-m2-lifecycle/test_architect_json_status_inc0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_architect_json_status_inc0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_architect_json_status_inc0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_architect_json_status_inc0/findings.md
.tmppytest-loop-m2-lifecycle/test_architect_json_status_inc0/plan.md
.tmppytest-loop-m2-lifecycle/test_architect_status_shows_pe0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_architect_status_shows_pe0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m2-lifecycle/test_architect_status_shows_pe0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_architect_status_shows_pe0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_architect_status_shows_pe0/findings.md
.tmppytest-loop-m2-lifecycle/test_architect_status_shows_pe0/plan.md
.tmppytest-loop-m2-lifecycle/test_architect_status_shows_pe0/request.md
.tmppytest-loop-m2-lifecycle/test_architect_token_generated0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_architect_token_generated0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_architect_token_generated0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_architect_token_generated0/findings.md
.tmppytest-loop-m2-lifecycle/test_architect_token_generated0/plan.md
.tmppytest-loop-m2-lifecycle/test_blocked_exit_20/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_blocked_exit_20/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_blocked_exit_20/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_blocked_exit_20/findings.md
.tmppytest-loop-m2-lifecycle/test_blocked_exit_20/plan.md
.tmppytest-loop-m2-lifecycle/test_cli_escalate_bad_file_pri0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_cli_escalate_bad_file_pri0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_cli_escalate_bad_file_pri0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_cli_escalate_bad_file_pri0/findings.md
.tmppytest-loop-m2-lifecycle/test_cli_escalate_bad_file_pri0/plan.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/findings.md
.tmppytest-loop-m2-lifecycle/test_correct_events_after_loop0/plan.md
.tmppytest-loop-m2-lifecycle/test_corrupt_base64_rejected0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_corrupt_base64_rejected0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_corrupt_base64_rejected0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_corrupt_base64_rejected0/findings.md
.tmppytest-loop-m2-lifecycle/test_corrupt_base64_rejected0/plan.md
.tmppytest-loop-m2-lifecycle/test_current_draft_is_turn_ref0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_current_draft_is_turn_ref0/findings.md
.tmppytest-loop-m2-lifecycle/test_current_draft_is_turn_ref0/plan.md
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/findings.md
.tmppytest-loop-m2-lifecycle/test_current_findings_is_turn_0/plan.md
.tmppytest-loop-m2-lifecycle/test_current_reference_stays_c0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_current_reference_stays_c0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_current_reference_stays_c0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_current_reference_stays_c0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_current_reference_stays_c0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_current_reference_stays_c0/findings.md
.tmppytest-loop-m2-lifecycle/test_current_reference_stays_c0/plan.md
.tmppytest-loop-m2-lifecycle/test_current_still_overwritten0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_current_still_overwritten0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_current_still_overwritten0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_current_still_overwritten0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_current_still_overwritten0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_current_still_overwritten0/findings.md
.tmppytest-loop-m2-lifecycle/test_current_still_overwritten0/plan.md
.tmppytest-loop-m2-lifecycle/test_decisions_array_in_fresh_0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_decisions_array_in_fresh_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_decisions_array_in_fresh_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_decisions_array_in_fresh_0/findings.md
.tmppytest-loop-m2-lifecycle/test_decisions_array_in_fresh_0/plan.md
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/findings.md
.tmppytest-loop-m2-lifecycle/test_draft_escalate_unblock_re0/plan.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/findings.md
.tmppytest-loop-m2-lifecycle/test_draft_review_revise_appro0/plan.md
.tmppytest-loop-m2-lifecycle/test_end_emits_terminal_event0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_end_emits_terminal_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_end_emits_terminal_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_end_emits_terminal_event0/findings.md
.tmppytest-loop-m2-lifecycle/test_end_emits_terminal_event0/plan.md
.tmppytest-loop-m2-lifecycle/test_end_from_active0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_end_from_active0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_end_from_active0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_end_from_active0/findings.md
.tmppytest-loop-m2-lifecycle/test_end_from_active0/plan.md
.tmppytest-loop-m2-lifecycle/test_end_from_paused0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_end_from_paused0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_end_from_paused0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_end_from_paused0/findings.md
.tmppytest-loop-m2-lifecycle/test_end_from_paused0/plan.md
.tmppytest-loop-m2-lifecycle/test_end_rejects_already_termi0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_end_rejects_already_termi0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_end_rejects_already_termi0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_end_rejects_already_termi0/findings.md
.tmppytest-loop-m2-lifecycle/test_end_rejects_already_termi0/plan.md
.tmppytest-loop-m2-lifecycle/test_escalate_event_includes_d0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_escalate_event_includes_d0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m2-lifecycle/test_escalate_event_includes_d0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_escalate_event_includes_d0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_escalate_event_includes_d0/findings.md
.tmppytest-loop-m2-lifecycle/test_escalate_event_includes_d0/plan.md
.tmppytest-loop-m2-lifecycle/test_escalate_event_includes_d0/request.md
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_be_non0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_be_non0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_be_non0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_be_non0/empty.md
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_be_non0/findings.md
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_be_non0/plan.md
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_exist0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_exist0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_exist0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_exist0/findings.md
.tmppytest-loop-m2-lifecycle/test_escalate_file_must_exist0/plan.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_copies0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_copies0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_copies0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_copies0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_copies0/decision-request.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_copies0/findings.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_copies0/plan.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/findings.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/off-turn-request.md
.tmppytest-loop-m2-lifecycle/test_escalate_with_file_not_yo0/plan.md
.tmppytest-loop-m2-lifecycle/test_escalate_without_file_bac0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_escalate_without_file_bac0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_escalate_without_file_bac0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_escalate_without_file_bac0/findings.md
.tmppytest-loop-m2-lifecycle/test_escalate_without_file_bac0/plan.md
.tmppytest-loop-m2-lifecycle/test_events_have_timestamp_and0/events.jsonl
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/findings.md
.tmppytest-loop-m2-lifecycle/test_findings_current_referenc0/plan.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/findings.md
.tmppytest-loop-m2-lifecycle/test_full_loop_preserves_all_r0/plan.md
.tmppytest-loop-m2-lifecycle/test_interject_emits_event0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_interject_emits_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_interject_emits_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_interject_emits_event0/findings.md
.tmppytest-loop-m2-lifecycle/test_interject_emits_event0/plan.md
.tmppytest-loop-m2-lifecycle/test_interject_message_cleared0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_interject_message_cleared0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_interject_message_cleared0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_interject_message_cleared0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_interject_message_cleared0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_interject_message_cleared0/findings.md
.tmppytest-loop-m2-lifecycle/test_interject_message_cleared0/plan.md
.tmppytest-loop-m2-lifecycle/test_interject_requires_messag0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_interject_requires_messag0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_interject_requires_messag0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_interject_requires_messag0/findings.md
.tmppytest-loop-m2-lifecycle/test_interject_requires_messag0/plan.md
.tmppytest-loop-m2-lifecycle/test_interject_stores_message0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_interject_stores_message0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_interject_stores_message0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_interject_stores_message0/findings.md
.tmppytest-loop-m2-lifecycle/test_interject_stores_message0/plan.md
.tmppytest-loop-m2-lifecycle/test_make_and_resolve0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_make_and_resolve0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_make_and_resolve0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_make_and_resolve0/findings.md
.tmppytest-loop-m2-lifecycle/test_make_and_resolve0/plan.md
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/findings.md
.tmppytest-loop-m2-lifecycle/test_message_cleared_after_sub0/plan.md
.tmppytest-loop-m2-lifecycle/test_message_in_json_status0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_message_in_json_status0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_message_in_json_status0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_message_in_json_status0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_message_in_json_status0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_message_in_json_status0/findings.md
.tmppytest-loop-m2-lifecycle/test_message_in_json_status0/plan.md
.tmppytest-loop-m2-lifecycle/test_message_in_status_output0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_message_in_status_output0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_message_in_status_output0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_message_in_status_output0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_message_in_status_output0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_message_in_status_output0/findings.md
.tmppytest-loop-m2-lifecycle/test_message_in_status_output0/plan.md
.tmppytest-loop-m2-lifecycle/test_message_in_unblock_event0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_message_in_unblock_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_message_in_unblock_event0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_message_in_unblock_event0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_message_in_unblock_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_message_in_unblock_event0/findings.md
.tmppytest-loop-m2-lifecycle/test_message_in_unblock_event0/plan.md
.tmppytest-loop-m2-lifecycle/test_model_cannot_end0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_model_cannot_end0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_model_cannot_end0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_model_cannot_end0/findings.md
.tmppytest-loop-m2-lifecycle/test_model_cannot_end0/plan.md
.tmppytest-loop-m2-lifecycle/test_model_cannot_pause0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_model_cannot_pause0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_model_cannot_pause0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_model_cannot_pause0/findings.md
.tmppytest-loop-m2-lifecycle/test_model_cannot_pause0/plan.md
.tmppytest-loop-m2-lifecycle/test_model_cannot_unblock0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_model_cannot_unblock0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_model_cannot_unblock0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_model_cannot_unblock0/findings.md
.tmppytest-loop-m2-lifecycle/test_model_cannot_unblock0/plan.md
.tmppytest-loop-m2-lifecycle/test_models_rejected_after_end0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_models_rejected_after_end0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_models_rejected_after_end0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_models_rejected_after_end0/findings.md
.tmppytest-loop-m2-lifecycle/test_models_rejected_after_end0/plan.md
.tmppytest-loop-m2-lifecycle/test_no_timeout_while_paused0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_no_timeout_while_paused0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_no_timeout_while_paused0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_no_timeout_while_paused0/findings.md
.tmppytest-loop-m2-lifecycle/test_no_timeout_while_paused0/plan.md
.tmppytest-loop-m2-lifecycle/test_not_your_turn_exit_10/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_not_your_turn_exit_10/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_not_your_turn_exit_10/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_not_your_turn_exit_10/findings.md
.tmppytest-loop-m2-lifecycle/test_not_your_turn_exit_10/plan.md
.tmppytest-loop-m2-lifecycle/test_pause_emits_event0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_pause_emits_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_pause_emits_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_pause_emits_event0/findings.md
.tmppytest-loop-m2-lifecycle/test_pause_emits_event0/plan.md
.tmppytest-loop-m2-lifecycle/test_pause_from_active0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_pause_from_active0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_pause_from_active0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_pause_from_active0/findings.md
.tmppytest-loop-m2-lifecycle/test_pause_from_active0/plan.md
.tmppytest-loop-m2-lifecycle/test_pause_records_turn0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_pause_records_turn0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_pause_records_turn0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_pause_records_turn0/findings.md
.tmppytest-loop-m2-lifecycle/test_pause_records_turn0/plan.md
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/.gator/loops/test-feature-loop/decision-request.decision-2.round-0.md
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/findings.md
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/plan.md
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/request-a.md
.tmppytest-loop-m2-lifecycle/test_repeated_escalations_same0/request-b.md
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/findings.md
.tmppytest-loop-m2-lifecycle/test_residue_remains_no_commit0/plan.md
.tmppytest-loop-m2-lifecycle/test_reviewer_token0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_reviewer_token0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_reviewer_token0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_reviewer_token0/findings.md
.tmppytest-loop-m2-lifecycle/test_reviewer_token0/plan.md
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/findings.md
.tmppytest-loop-m2-lifecycle/test_round_number_correct0/plan.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/findings.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_findings_0/plan.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_plan_crea0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_round_versioned_plan_crea0/findings.md
.tmppytest-loop-m2-lifecycle/test_round_versioned_plan_crea0/plan.md
.tmppytest-loop-m2-lifecycle/test_roundtrip0/events.jsonl
.tmppytest-loop-m2-lifecycle/test_save_produces_valid_json0/session.json
.tmppytest-loop-m2-lifecycle/test_session_json_has_no_nonce0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_session_json_has_no_nonce0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_session_json_has_no_nonce0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_session_json_has_no_nonce0/findings.md
.tmppytest-loop-m2-lifecycle/test_session_json_has_no_nonce0/plan.md
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/findings.md
.tmppytest-loop-m2-lifecycle/test_start_draft_review_approv0/plan.md
.tmppytest-loop-m2-lifecycle/test_submit_fails_after_timeou0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_submit_fails_after_timeou0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_submit_fails_after_timeou0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_submit_fails_after_timeou0/findings.md
.tmppytest-loop-m2-lifecycle/test_submit_fails_after_timeou0/plan.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/findings.md
.tmppytest-loop-m2-lifecycle/test_three_rounds_triggers_ter0/plan.md
.tmppytest-loop-m2-lifecycle/test_timeout_fires_when_expire0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_timeout_fires_when_expire0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_timeout_fires_when_expire0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_timeout_fires_when_expire0/findings.md
.tmppytest-loop-m2-lifecycle/test_timeout_fires_when_expire0/plan.md
.tmppytest-loop-m2-lifecycle/test_timeout_skipped_after_sub0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_timeout_skipped_after_sub0/findings.md
.tmppytest-loop-m2-lifecycle/test_timeout_skipped_after_sub0/plan.md
.tmppytest-loop-m2-lifecycle/test_token_prefix0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_token_prefix0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_token_prefix0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_token_prefix0/findings.md
.tmppytest-loop-m2-lifecycle/test_token_prefix0/plan.md
.tmppytest-loop-m2-lifecycle/test_tokens_gitignored0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_tokens_gitignored0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_tokens_gitignored0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_tokens_gitignored0/findings.md
.tmppytest-loop-m2-lifecycle/test_tokens_gitignored0/plan.md
.tmppytest-loop-m2-lifecycle/test_turn_artifact_path_versio0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_turn_artifact_path_versio0/findings.md
.tmppytest-loop-m2-lifecycle/test_turn_artifact_path_versio0/plan.md
.tmppytest-loop-m2-lifecycle/test_unblock_after_pause0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_unblock_after_pause0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_unblock_after_pause0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_unblock_after_pause0/findings.md
.tmppytest-loop-m2-lifecycle/test_unblock_after_pause0/plan.md
.tmppytest-loop-m2-lifecycle/test_unblock_resolves_pending_0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_unblock_resolves_pending_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_unblock_resolves_pending_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_unblock_resolves_pending_0/findings.md
.tmppytest-loop-m2-lifecycle/test_unblock_resolves_pending_0/plan.md
.tmppytest-loop-m2-lifecycle/test_unblock_with_message0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_unblock_with_message0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_unblock_with_message0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_unblock_with_message0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_unblock_with_message0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_unblock_with_message0/findings.md
.tmppytest-loop-m2-lifecycle/test_unblock_with_message0/plan.md
.tmppytest-loop-m2-lifecycle/test_unblock_without_message0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_unblock_without_message0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_unblock_without_message0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_unblock_without_message0/findings.md
.tmppytest-loop-m2-lifecycle/test_unblock_without_message0/plan.md
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/findings.md
.tmppytest-loop-m2-lifecycle/test_wait_blocks_then_wakes0/plan.md
.tmppytest-loop-m2-lifecycle/test_wait_does_not_write0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wait_does_not_write0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wait_does_not_write0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wait_does_not_write0/findings.md
.tmppytest-loop-m2-lifecycle/test_wait_does_not_write0/plan.md
.tmppytest-loop-m2-lifecycle/test_wait_json_includes_wake_r0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wait_json_includes_wake_r0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wait_json_includes_wake_r0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wait_json_includes_wake_r0/findings.md
.tmppytest-loop-m2-lifecycle/test_wait_json_includes_wake_r0/plan.md
.tmppytest-loop-m2-lifecycle/test_wait_rejects_architect_to0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wait_rejects_architect_to0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wait_rejects_architect_to0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wait_rejects_architect_to0/findings.md
.tmppytest-loop-m2-lifecycle/test_wait_rejects_architect_to0/plan.md
.tmppytest-loop-m2-lifecycle/test_wait_returns_immediately_0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wait_returns_immediately_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wait_returns_immediately_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wait_returns_immediately_0/findings.md
.tmppytest-loop-m2-lifecycle/test_wait_returns_immediately_0/plan.md
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_pause0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_pause0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_pause0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_pause0/findings.md
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_pause0/plan.md
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_terminal0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_terminal0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_terminal0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_terminal0/findings.md
.tmppytest-loop-m2-lifecycle/test_wait_returns_on_terminal0/plan.md
.tmppytest-loop-m2-lifecycle/test_write_ordering0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_write_ordering0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_write_ordering0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m2-lifecycle/test_write_ordering0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m2-lifecycle/test_write_ordering0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_write_ordering0/findings.md
.tmppytest-loop-m2-lifecycle/test_write_ordering0/plan.md
.tmppytest-loop-m2-lifecycle/test_wrong_nonce_rejected0/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_wrong_nonce_rejected0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_wrong_nonce_rejected0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_wrong_nonce_rejected0/findings.md
.tmppytest-loop-m2-lifecycle/test_wrong_nonce_rejected0/plan.md
.tmppytest-loop-m2-lifecycle/test_your_turn_exit_00/.gator/loops/.gitignore
.tmppytest-loop-m2-lifecycle/test_your_turn_exit_00/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m2-lifecycle/test_your_turn_exit_00/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m2-lifecycle/test_your_turn_exit_00/findings.md
.tmppytest-loop-m2-lifecycle/test_your_turn_exit_00/plan.md
.tmppytest-loop-m3/test_architect_cannot_submit_d0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_architect_cannot_submit_d0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_architect_cannot_submit_d0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_architect_cannot_submit_d0/findings.md
.tmppytest-loop-m3/test_architect_cannot_submit_d0/plan.md
.tmppytest-loop-m3/test_architect_in_session_role0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_architect_in_session_role0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_architect_in_session_role0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_architect_in_session_role0/findings.md
.tmppytest-loop-m3/test_architect_in_session_role0/plan.md
.tmppytest-loop-m3/test_architect_json_status_inc0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_architect_json_status_inc0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_architect_json_status_inc0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_architect_json_status_inc0/findings.md
.tmppytest-loop-m3/test_architect_json_status_inc0/plan.md
.tmppytest-loop-m3/test_architect_status_shows_pe0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_architect_status_shows_pe0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m3/test_architect_status_shows_pe0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_architect_status_shows_pe0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_architect_status_shows_pe0/findings.md
.tmppytest-loop-m3/test_architect_status_shows_pe0/plan.md
.tmppytest-loop-m3/test_architect_status_shows_pe0/request.md
.tmppytest-loop-m3/test_architect_token_generated0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_architect_token_generated0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_architect_token_generated0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_architect_token_generated0/findings.md
.tmppytest-loop-m3/test_architect_token_generated0/plan.md
.tmppytest-loop-m3/test_blocked_exit_20/.gator/loops/.gitignore
.tmppytest-loop-m3/test_blocked_exit_20/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_blocked_exit_20/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_blocked_exit_20/findings.md
.tmppytest-loop-m3/test_blocked_exit_20/plan.md
.tmppytest-loop-m3/test_cli_escalate_bad_file_pri0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_cli_escalate_bad_file_pri0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_cli_escalate_bad_file_pri0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_cli_escalate_bad_file_pri0/findings.md
.tmppytest-loop-m3/test_cli_escalate_bad_file_pri0/plan.md
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m3/test_correct_events_after_loop0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_correct_events_after_loop0/findings.md
.tmppytest-loop-m3/test_correct_events_after_loop0/plan.md
.tmppytest-loop-m3/test_corrupt_base64_rejected0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_corrupt_base64_rejected0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_corrupt_base64_rejected0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_corrupt_base64_rejected0/findings.md
.tmppytest-loop-m3/test_corrupt_base64_rejected0/plan.md
.tmppytest-loop-m3/test_current_draft_is_turn_ref0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_current_draft_is_turn_ref0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_current_draft_is_turn_ref0/findings.md
.tmppytest-loop-m3/test_current_draft_is_turn_ref0/plan.md
.tmppytest-loop-m3/test_current_findings_is_turn_0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_current_findings_is_turn_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_current_findings_is_turn_0/findings.md
.tmppytest-loop-m3/test_current_findings_is_turn_0/plan.md
.tmppytest-loop-m3/test_current_reference_stays_c0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_current_reference_stays_c0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_current_reference_stays_c0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_current_reference_stays_c0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_current_reference_stays_c0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_current_reference_stays_c0/findings.md
.tmppytest-loop-m3/test_current_reference_stays_c0/plan.md
.tmppytest-loop-m3/test_current_still_overwritten0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_current_still_overwritten0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_current_still_overwritten0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_current_still_overwritten0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_current_still_overwritten0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_current_still_overwritten0/findings.md
.tmppytest-loop-m3/test_current_still_overwritten0/plan.md
.tmppytest-loop-m3/test_decisions_array_in_fresh_0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_decisions_array_in_fresh_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_decisions_array_in_fresh_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_decisions_array_in_fresh_0/findings.md
.tmppytest-loop-m3/test_decisions_array_in_fresh_0/plan.md
.tmppytest-loop-m3/test_decisions_survive_to_term0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_decisions_survive_to_term0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_decisions_survive_to_term0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_decisions_survive_to_term0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_decisions_survive_to_term0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_decisions_survive_to_term0/findings.md
.tmppytest-loop-m3/test_decisions_survive_to_term0/plan.md
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/findings.md
.tmppytest-loop-m3/test_draft_escalate_unblock_re0/plan.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_draft_review_revise_appro0/findings.md
.tmppytest-loop-m3/test_draft_review_revise_appro0/plan.md
.tmppytest-loop-m3/test_end_emits_terminal_event0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_end_emits_terminal_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_end_emits_terminal_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_end_emits_terminal_event0/findings.md
.tmppytest-loop-m3/test_end_emits_terminal_event0/plan.md
.tmppytest-loop-m3/test_end_from_active0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_end_from_active0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_end_from_active0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_end_from_active0/findings.md
.tmppytest-loop-m3/test_end_from_active0/plan.md
.tmppytest-loop-m3/test_end_from_paused0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_end_from_paused0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_end_from_paused0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_end_from_paused0/findings.md
.tmppytest-loop-m3/test_end_from_paused0/plan.md
.tmppytest-loop-m3/test_end_rejects_already_termi0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_end_rejects_already_termi0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_end_rejects_already_termi0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_end_rejects_already_termi0/findings.md
.tmppytest-loop-m3/test_end_rejects_already_termi0/plan.md
.tmppytest-loop-m3/test_escalate_event_includes_d0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_escalate_event_includes_d0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m3/test_escalate_event_includes_d0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_escalate_event_includes_d0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_escalate_event_includes_d0/findings.md
.tmppytest-loop-m3/test_escalate_event_includes_d0/plan.md
.tmppytest-loop-m3/test_escalate_event_includes_d0/request.md
.tmppytest-loop-m3/test_escalate_file_must_be_non0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_escalate_file_must_be_non0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_escalate_file_must_be_non0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_escalate_file_must_be_non0/empty.md
.tmppytest-loop-m3/test_escalate_file_must_be_non0/findings.md
.tmppytest-loop-m3/test_escalate_file_must_be_non0/plan.md
.tmppytest-loop-m3/test_escalate_file_must_exist0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_escalate_file_must_exist0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_escalate_file_must_exist0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_escalate_file_must_exist0/findings.md
.tmppytest-loop-m3/test_escalate_file_must_exist0/plan.md
.tmppytest-loop-m3/test_escalate_with_file_copies0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_escalate_with_file_copies0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m3/test_escalate_with_file_copies0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_escalate_with_file_copies0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_escalate_with_file_copies0/decision-request.md
.tmppytest-loop-m3/test_escalate_with_file_copies0/findings.md
.tmppytest-loop-m3/test_escalate_with_file_copies0/plan.md
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/findings.md
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/off-turn-request.md
.tmppytest-loop-m3/test_escalate_with_file_not_yo0/plan.md
.tmppytest-loop-m3/test_escalate_without_file_bac0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_escalate_without_file_bac0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_escalate_without_file_bac0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_escalate_without_file_bac0/findings.md
.tmppytest-loop-m3/test_escalate_without_file_bac0/plan.md
.tmppytest-loop-m3/test_events_have_timestamp_and0/events.jsonl
.tmppytest-loop-m3/test_findings_current_referenc0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_findings_current_referenc0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_findings_current_referenc0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_findings_current_referenc0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_findings_current_referenc0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_findings_current_referenc0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_findings_current_referenc0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_findings_current_referenc0/findings.md
.tmppytest-loop-m3/test_findings_current_referenc0/plan.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/findings.md
.tmppytest-loop-m3/test_full_loop_preserves_all_r0/plan.md
.tmppytest-loop-m3/test_interject_emits_event0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_interject_emits_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_interject_emits_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_interject_emits_event0/findings.md
.tmppytest-loop-m3/test_interject_emits_event0/plan.md
.tmppytest-loop-m3/test_interject_message_cleared0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_interject_message_cleared0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_interject_message_cleared0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_interject_message_cleared0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_interject_message_cleared0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_interject_message_cleared0/findings.md
.tmppytest-loop-m3/test_interject_message_cleared0/plan.md
.tmppytest-loop-m3/test_interject_requires_messag0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_interject_requires_messag0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_interject_requires_messag0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_interject_requires_messag0/findings.md
.tmppytest-loop-m3/test_interject_requires_messag0/plan.md
.tmppytest-loop-m3/test_interject_stores_message0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_interject_stores_message0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_interject_stores_message0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_interject_stores_message0/findings.md
.tmppytest-loop-m3/test_interject_stores_message0/plan.md
.tmppytest-loop-m3/test_make_and_resolve0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_make_and_resolve0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_make_and_resolve0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_make_and_resolve0/findings.md
.tmppytest-loop-m3/test_make_and_resolve0/plan.md
.tmppytest-loop-m3/test_message_cleared_after_sub0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_message_cleared_after_sub0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_message_cleared_after_sub0/findings.md
.tmppytest-loop-m3/test_message_cleared_after_sub0/plan.md
.tmppytest-loop-m3/test_message_in_json_status0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_message_in_json_status0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_message_in_json_status0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_message_in_json_status0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_message_in_json_status0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_message_in_json_status0/findings.md
.tmppytest-loop-m3/test_message_in_json_status0/plan.md
.tmppytest-loop-m3/test_message_in_status_output0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_message_in_status_output0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_message_in_status_output0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_message_in_status_output0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_message_in_status_output0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_message_in_status_output0/findings.md
.tmppytest-loop-m3/test_message_in_status_output0/plan.md
.tmppytest-loop-m3/test_message_in_unblock_event0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_message_in_unblock_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_message_in_unblock_event0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_message_in_unblock_event0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_message_in_unblock_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_message_in_unblock_event0/findings.md
.tmppytest-loop-m3/test_message_in_unblock_event0/plan.md
.tmppytest-loop-m3/test_model_cannot_end0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_model_cannot_end0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_model_cannot_end0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_model_cannot_end0/findings.md
.tmppytest-loop-m3/test_model_cannot_end0/plan.md
.tmppytest-loop-m3/test_model_cannot_pause0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_model_cannot_pause0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_model_cannot_pause0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_model_cannot_pause0/findings.md
.tmppytest-loop-m3/test_model_cannot_pause0/plan.md
.tmppytest-loop-m3/test_model_cannot_unblock0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_model_cannot_unblock0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_model_cannot_unblock0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_model_cannot_unblock0/findings.md
.tmppytest-loop-m3/test_model_cannot_unblock0/plan.md
.tmppytest-loop-m3/test_models_rejected_after_end0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_models_rejected_after_end0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_models_rejected_after_end0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_models_rejected_after_end0/findings.md
.tmppytest-loop-m3/test_models_rejected_after_end0/plan.md
.tmppytest-loop-m3/test_no_timeout_while_paused0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_no_timeout_while_paused0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_no_timeout_while_paused0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_no_timeout_while_paused0/findings.md
.tmppytest-loop-m3/test_no_timeout_while_paused0/plan.md
.tmppytest-loop-m3/test_not_your_turn_exit_10/.gator/loops/.gitignore
.tmppytest-loop-m3/test_not_your_turn_exit_10/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_not_your_turn_exit_10/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_not_your_turn_exit_10/findings.md
.tmppytest-loop-m3/test_not_your_turn_exit_10/plan.md
.tmppytest-loop-m3/test_pause_emits_event0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_pause_emits_event0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_pause_emits_event0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_pause_emits_event0/findings.md
.tmppytest-loop-m3/test_pause_emits_event0/plan.md
.tmppytest-loop-m3/test_pause_from_active0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_pause_from_active0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_pause_from_active0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_pause_from_active0/findings.md
.tmppytest-loop-m3/test_pause_from_active0/plan.md
.tmppytest-loop-m3/test_pause_records_turn0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_pause_records_turn0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_pause_records_turn0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_pause_records_turn0/findings.md
.tmppytest-loop-m3/test_pause_records_turn0/plan.md
.tmppytest-loop-m3/test_repeated_escalations_same0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_repeated_escalations_same0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m3/test_repeated_escalations_same0/.gator/loops/test-feature-loop/decision-request.decision-2.round-0.md
.tmppytest-loop-m3/test_repeated_escalations_same0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_repeated_escalations_same0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_repeated_escalations_same0/findings.md
.tmppytest-loop-m3/test_repeated_escalations_same0/plan.md
.tmppytest-loop-m3/test_repeated_escalations_same0/request-a.md
.tmppytest-loop-m3/test_repeated_escalations_same0/request-b.md
.tmppytest-loop-m3/test_residue_remains_no_commit0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_residue_remains_no_commit0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_residue_remains_no_commit0/findings.md
.tmppytest-loop-m3/test_residue_remains_no_commit0/plan.md
.tmppytest-loop-m3/test_reviewer_token0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_reviewer_token0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_reviewer_token0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_reviewer_token0/findings.md
.tmppytest-loop-m3/test_reviewer_token0/plan.md
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m3/test_round_number_correct0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_round_number_correct0/findings.md
.tmppytest-loop-m3/test_round_number_correct0/plan.md
.tmppytest-loop-m3/test_round_versioned_findings_0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_round_versioned_findings_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_round_versioned_findings_0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_round_versioned_findings_0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_round_versioned_findings_0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_round_versioned_findings_0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_round_versioned_findings_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_round_versioned_findings_0/findings.md
.tmppytest-loop-m3/test_round_versioned_findings_0/plan.md
.tmppytest-loop-m3/test_round_versioned_plan_crea0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_round_versioned_plan_crea0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_round_versioned_plan_crea0/findings.md
.tmppytest-loop-m3/test_round_versioned_plan_crea0/plan.md
.tmppytest-loop-m3/test_roundtrip0/events.jsonl
.tmppytest-loop-m3/test_save_produces_valid_json0/session.json
.tmppytest-loop-m3/test_session_json_has_no_nonce0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_session_json_has_no_nonce0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_session_json_has_no_nonce0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_session_json_has_no_nonce0/findings.md
.tmppytest-loop-m3/test_session_json_has_no_nonce0/plan.md
.tmppytest-loop-m3/test_start_draft_review_approv0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_start_draft_review_approv0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_start_draft_review_approv0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_start_draft_review_approv0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_start_draft_review_approv0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_start_draft_review_approv0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_start_draft_review_approv0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_start_draft_review_approv0/findings.md
.tmppytest-loop-m3/test_start_draft_review_approv0/plan.md
.tmppytest-loop-m3/test_submit_fails_after_timeou0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_submit_fails_after_timeou0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_submit_fails_after_timeou0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_submit_fails_after_timeou0/findings.md
.tmppytest-loop-m3/test_submit_fails_after_timeou0/plan.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/findings.current.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/findings.round-0.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/findings.round-1.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/plan.round-1.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/findings.md
.tmppytest-loop-m3/test_three_rounds_triggers_ter0/plan.md
.tmppytest-loop-m3/test_timeout_fires_when_expire0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_timeout_fires_when_expire0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_timeout_fires_when_expire0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_timeout_fires_when_expire0/findings.md
.tmppytest-loop-m3/test_timeout_fires_when_expire0/plan.md
.tmppytest-loop-m3/test_timeout_skipped_after_sub0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_timeout_skipped_after_sub0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_timeout_skipped_after_sub0/findings.md
.tmppytest-loop-m3/test_timeout_skipped_after_sub0/plan.md
.tmppytest-loop-m3/test_token_prefix0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_token_prefix0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_token_prefix0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_token_prefix0/findings.md
.tmppytest-loop-m3/test_token_prefix0/plan.md
.tmppytest-loop-m3/test_tokens_gitignored0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_tokens_gitignored0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_tokens_gitignored0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_tokens_gitignored0/findings.md
.tmppytest-loop-m3/test_tokens_gitignored0/plan.md
.tmppytest-loop-m3/test_turn_artifact_path_versio0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/plan.current.md
.tmppytest-loop-m3/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/plan.round-0.md
.tmppytest-loop-m3/test_turn_artifact_path_versio0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_turn_artifact_path_versio0/findings.md
.tmppytest-loop-m3/test_turn_artifact_path_versio0/plan.md
.tmppytest-loop-m3/test_unblock_after_pause0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_after_pause0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_after_pause0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_after_pause0/findings.md
.tmppytest-loop-m3/test_unblock_after_pause0/plan.md
.tmppytest-loop-m3/test_unblock_after_pause_no_de0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_after_pause_no_de0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_after_pause_no_de0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_after_pause_no_de0/findings.md
.tmppytest-loop-m3/test_unblock_after_pause_no_de0/plan.md
.tmppytest-loop-m3/test_unblock_event_includes_de0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_event_includes_de0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_event_includes_de0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_event_includes_de0/findings.md
.tmppytest-loop-m3/test_unblock_event_includes_de0/plan.md
.tmppytest-loop-m3/test_unblock_file_must_be_none0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_file_must_be_none0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_file_must_be_none0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_file_must_be_none0/empty.md
.tmppytest-loop-m3/test_unblock_file_must_be_none0/findings.md
.tmppytest-loop-m3/test_unblock_file_must_be_none0/plan.md
.tmppytest-loop-m3/test_unblock_file_must_exist0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_file_must_exist0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_file_must_exist0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_file_must_exist0/findings.md
.tmppytest-loop-m3/test_unblock_file_must_exist0/plan.md
.tmppytest-loop-m3/test_unblock_message_only_no_a0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_message_only_no_a0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_message_only_no_a0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_message_only_no_a0/findings.md
.tmppytest-loop-m3/test_unblock_message_only_no_a0/plan.md
.tmppytest-loop-m3/test_unblock_resolves_pending_0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_resolves_pending_0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_resolves_pending_0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_resolves_pending_0/findings.md
.tmppytest-loop-m3/test_unblock_resolves_pending_0/plan.md
.tmppytest-loop-m3/test_unblock_with_file_creates0/.gator/loops/.gitignore
.tmppytest-loop-m3/test_unblock_with_file_creates0/.gator/loops/test-feature-loop/decision-request.decision-1.round-0.md
.tmppytest-loop-m3/test_unblock_with_file_creates0/.gator/loops/test-feature-loop/decision-response.decision-1.md
.tmppytest-loop-m3/test_unblock_with_file_creates0/.gator/loops/test-feature-loop/events.jsonl
.tmppytest-loop-m3/test_unblock_with_file_creates0/.gator/loops/test-feature-loop/session.json
.tmppytest-loop-m3/test_unblock_with_file_creates0/findings.md
.tmppytest-loop-m3/test_unblock_with_file_creates0/my-request.md
.tmppytest-loop-m3/test_unblock_with_file_creates0/my-response.md
.tmppytest-loop-m3/test_unblock_with_file_creates0/plan.md
... 5059 more (truncated)
```

Loop residue: 50 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
