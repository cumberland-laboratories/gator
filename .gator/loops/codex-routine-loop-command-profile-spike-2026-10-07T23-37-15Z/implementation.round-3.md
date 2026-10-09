# Implementation: Codex Routine Loop-Command Profile Spike — Checkpoint 4 (Result packaging)

## Executive Summary

- **What changed:** the Architect chose "Publish as opt-in" (decision-1). The pass branch adds a new reference note, `codex-routine-participant-profile.md`, in both copies, linked from the Goal-mode note and the Loop protocol, plus the two planned copy-guard tests and evidence artifact §9.
- **Key decision:** the note leads with the trust cost (allowed `gator loop` commands and their Git children run outside the Codex sandbox). Its setup uses a dedicated, pre-trusted `CODEX_HOME`, never the normal home, and each step maps to recorded evidence (§9.3).
- **Main risk:** an unplanned but charter-mandated code touch. The `scripts-layout.md` tripwire requires both `gator_layout.py` copies to list every shipped reference note, so both Codex notes were added to the fallback set. `codex-loop-participant.md` (previously uncommitted) is staged for the first time.
- **Verified:** the new test fails on a one-sided copy and passes in the committed state. The planned pytest command passes (69). Layout, attention, gatorize and packaging suites pass (240).

## Implementation Summary

- **Decision:** escalated with a decision request (`gator loop escalate --file`, ledger `decision-1`). The Architect's unblock message was "Publish as opt-in."
- **`reference-notes/codex-routine-participant-profile.md` (new)**, identical in `.gator/.includes/` and `src/gator_command/templates/gator-starter/`. Sections:
  - Purpose, with the verbatim `git_busy … index.lock` failure.
  - Trust Cost, first: the Codex `allow` quote, full user rights, the `PATH` caveat, and what stays sandboxed.
  - Verified Surface: codex-cli 0.144.1 / Windows 10 / Gator 2.23.0. It notes that the TUI was not observed and points to the issue #37 evidence.
  - Setup:
    1. dedicated home outside `%TEMP%`;
    2. `config.toml` with sandbox setting and repository pre-trust;
    3. the exact verified rule;
    4. BOM-free save;
    5. `execpolicy check` expectations;
    6. `codex login`, with a note that the spike copied `auth.json` instead;
    7. launch from one terminal and never persist `CODEX_HOME`.
  - Covered / Not Covered, including a soft statement on compound commands (documentation-based, not tested live).
  - Participant Guidance: read Gator's text, not exit codes; `git_busy` + Permission denied is a host denial, not an escalation or finding; copy tokens exactly.
  - Removal, Fallback, and a five-step Validation Checklist.
- **Links:**
  - `codex-loop-participant.md` §Boundaries adds two sentences pointing to the new note and naming the trust cost;
  - the protocol's runtime paragraph adds one sentence with the same pointer.

  Both pairs were changed in both copies and are byte-identical. The protocol sentence adds no time words (the `TestParticipantDocs` Rule-7 pins still pass).
- **`gator_layout.py` (scripts and template copies):** `codex-loop-participant.md` and `codex-routine-participant-profile.md` were added to `MIXED_DIRECTORY_SHIPPED_DEFAULTS["reference-notes"]`. Without this, the bootstrap fallback would not treat these shipped notes as Gator defaults when classifying a repository's layout. That is the drift class the charter warns about.
- **`tests/test_loop.py` `TestArtifactFormatAlignment`:**
  - `test_starter_copies_match` gains the `codex-loop-participant.md` pair (unconditional);
  - new `test_codex_routine_profile_copies_both_absent_or_identical` returns when both copies are absent, and otherwise asserts both exist (naming the missing side) and are byte-identical.
- **Artifact §9:** decision, publication summary, and the step-to-evidence map.

**Pre-existing work now in the candidate:** the previous session left two uncommitted changes:
- `codex-loop-participant.md` (both copies, untracked);
- the one-sentence protocol Goal-mode pointer (both copies, modified).

This checkpoint must guard and link that note, so both are staged here with the cp4 edits on top. No other pre-existing residue is staged except the expected session snippet.

## Charter Updates

- `.gator/charters/scripts-layout.md`: the reference-notes tripwire ("Keep BOTH `gator_layout.py` copies … in sync when adding a shipped note") now names `codex-loop-participant.md` and `codex-routine-participant-profile.md` (#37 Phase 1). I checked it against both edited `frozenset`s.
- **Cross-Cutting** (`scripts-cross-cutting.md`), read for this checkpoint: its rule is "change all named copies in the same commit" under byte-identity tests. All three doc pairs and both layout copies changed together. `TestArtifactFormatAlignment` is the guard named there and now covers the Codex notes. No cross-cutting text change is needed.
- No change to `scripts-loop.md`. No loop code changed.

## Verification

- **One-sided copy check:** with the starter copy moved away, `pytest tests/test_loop.py::TestArtifactFormatAlignment::test_codex_routine_profile_copies_both_absent_or_identical` gave `1 failed` with `AssertionError: …: live .includes copy exists but shipped copy is missing`. I then restored it; the SHA matches the live copy.
- **Planned command:** `pytest tests/test_loop.py::TestArtifactFormatAlignment tests/test_loop.py::TestWaitHandoffAlignment tests/test_loop_context_evidence.py` gave **69 passed**.
- **Broader, because `gator_layout.py` changed:** `pytest tests/test_layout.py tests/test_loop_attention.py tests/test_gatorize.py tests/test_packaging.py` gave **240 passed**.
- **Byte identity:** `Get-FileHash` shows a match for all three `.includes` ↔ starter pairs (profile note, Goal note, protocol).
- **Note vs evidence:** artifact §9.3 maps each setup step to its section. `codex login` and the no-BOM requirement are marked as not exercised or precautionary.
- **Not run:** the full repository suite, deferred to CI as the plan's verification ladder allows.
- **Cleanup:** the fixture folder `%TEMP%\gator-codex-spike-20261008\` (with token notes and Codex JSON logs) is deleted after this checkpoint is approved.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp4 (4 of 4) — Result packaging |
| Checkpoint base tree | `4694815498825fe3cdb261da492e077ef4089b63` |
| Generation | 3 |
| Staged tree (candidate) | `7a57123a3211e4c10de0b3e932fe6912c9565d22` |
| Changed paths in this checkpoint | 12 (A 4, M 8) |
| Loop base HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` |
| Loop base tree | `101a914d85b07ffd2a1c8fbc6c40748f5862cda8` |
| Current HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` (dev) |
| Changed paths vs loop base (cumulative) | 13 |
| Unstaged / untracked residue | 1 other + 34 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 4694815498825fe3cdb261da492e077ef4089b63 7a57123a3211e4c10de0b3e932fe6912c9565d22
```

Cumulative context (approved checkpoints plus this one): `git diff 101a914d85b07ffd2a1c8fbc6c40748f5862cda8 7a57123a3211e4c10de0b3e932fe6912c9565d22`.

Changed paths in this checkpoint (status, path):

```text
M .gator/.includes/procedures/gator-loop-protocol.md
A .gator/.includes/reference-notes/codex-loop-participant.md
A .gator/.includes/reference-notes/codex-routine-participant-profile.md
M .gator/artifacts/2026-10-08-codex-routine-profile-spike.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-layout.md
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/gator_layout.py
M src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md
A src/gator_command/templates/gator-starter/reference-notes/codex-loop-participant.md
A src/gator_command/templates/gator-starter/reference-notes/codex-routine-participant-profile.md
M src/gator_command/templates/gator-starter/scripts/gator_layout.py
M tests/test_loop.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 34 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
