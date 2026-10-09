# Implementation: Gator-Native Entry Point, Checkpoint 3 (State Boundary and Renderer Retirement)

## Executive Summary

- **What changed:**
  - `gator state` is now schema `gator-state-v2`. `status` reports native agent files for information only (`managed: false`, plus a `historical_gator_block` flag), and `repair` is a no-write compatibility stub.
  - `gatorize/entry_points.py` is deleted, together with the renderer and legacy-upgrade tests that pinned it.
- **Key decision:** historical blocks are reported with neutral wording ("historical Gator block (not refreshed)"). The tests forbid drift, failure or repair vocabulary in the native-file section.
- **Main risk addressed:** the loop handoff tests no longer depend on the renderer or on this repo's live `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`. Those files keep their exact bytes, and the protocol and `/loop-join` stay pinned.
- **Verification:** 688 tests pass across state, managed_block, packaging, loop, gatorize, template_sync, init, layout, loop_context_evidence and loop_attention.

## Implementation Summary

- **`src/gator_command/scripts/gator-state.py`:**
  - `SCHEMA = "gator-state-v2"`, and a new `NATIVE_FILES` tuple.
  - New `describe_native_file()` returns `{filename, present, managed: False, historical_gator_block, local_companion}`. The historical flag is True for any sentinel bytes (well-formed or corrupted) or a legacy fingerprint, using `managed_block.GATOR_BEGIN`/`GATOR_END`/`detect_legacy_gator_content`, read-only.
  - `collect_status()` drops `entry_points` / `entry_point_baseline_kind` and adds `native_files`.
  - `render_status_text()` prints `native agent files (not managed by Gator):` with `absent` / `present` / `present · historical Gator block (not refreshed)`.
  - `repair`: `main_repair()` accepts `filename` / `--dry-run` / `--json` and writes nothing. `render_repair_text/json(dry_run)` print "Nothing to repair…" or `{schema, dry_run, actions: [], native_files: "not-managed", constitution: "repair-deferred-v1", local_companions: "preserved"}`.
  - Removed: `classify_entry_point`, `plan_repair`, `_plan_action_for_state`, `execute_repair`, `_execute_one`, `_fresh_file_content`, `_ENTRY_POINTS` and the unused `shutil` / `read_product_source` / renderer imports.
  - Unchanged: `is_source_repo`, `read_repo_gator_version`, `local_companion_present` (existence only), `check_constitution`, `check_constitution_drift` (still consumed by `gator init`) and the version diagnostic.
- **`gatorize/entry_points.py`:** deleted. Nothing under `src/`, `tests/`, `contracts/` or `enterprise/` imports it; grep found only the state module and tests, both updated.
- **`gatorize/managed_block.py`:** the docstrings now describe read-only parsing of historical blocks. The code is unchanged.
- **`src/gator_command/cli.py`:** the `state` help text changes from "Report or repair managed state" to "Report repo state (constitution drift, native agent files)".
- **Manual run in this repo:** `gator-state.py status` lists all three native files as "present · historical Gator block (not refreshed)" and the constitution as "matches baseline". `repair --json` prints the stub payload. The live root files are untouched.

## Charter Updates

- **`scripts-managed-state.md`:** rewritten for v2.
  - Owns: informational status and the repair stub. A `describe_native_file()` entry is added; the six-state, repair and baseline-kind entries are removed.
  - New TRIPWIRE "Native Agent Files Are Not Managed" (pins `TestStatusV2`, `TestRepairStub`). The Two Baselines TRIPWIRE reduces to the constitution baseline.
  - The `is_source_repo()` entry now matches the code, which probes `gator-command/mission.md`. The old charter text said `.gator/mission.md`; this was pre-existing charter drift, and the code was not changed.
- **`scripts-installer.md`:** removed the `render_managed_region() / render_entry_content()` and `upgrade_legacy_entry_point()` entries. The native-file TRIPWIRE now records that `entry_points.py` is gone and that loop guidance lives only in the protocol, `/loop-join` and `GATOR_INIT.md`. The managed_block caller list now names only `gator state status`.
- **`scripts-cross-cutting.md`:**
  - `TestWaitHandoffAlignment` / `TestExecutiveSummaryProducerPaths` no longer list the renderer or the live native files.
  - The #53 note says the renderer and native regions are retired.
  - New **`gator-state-v2`** compatibility note: update JSON keeps the empty `entry_point_actions` and init gains an additive `session_opening`, so neither bumps.
- **`scripts-loop.md`:** Cross-Vendor Orientation now says participants are oriented by `GATOR_INIT.md`'s loop pointer, not `render_entry_content()`. Connections are updated.
- **`scripts-layout.md`:** the Connections line no longer mentions `entry_points.py`.
- **Checks against the code:** `grep -rn "render_entry_content|entry_points\.py|upgrade_legacy_entry_point|action_install_entry_points" .gator/charters/` leaves only the historical "is gone" statement in the installer TRIPWIRE.
- **`commit_draft.md`:** a checkpoint 3 bullet is appended and staged.

## Verification

- `python -m pytest tests/test_state.py tests/test_managed_block.py tests/test_packaging.py tests/test_loop.py tests/test_gatorize.py tests/test_template_sync.py tests/test_init.py tests/test_layout.py tests/test_loop_context_evidence.py tests/test_loop_attention.py -q`: **688 passed**. This is a superset of the plan's checkpoint 3 command and includes the loop drift guards.
- **`tests/test_state.py`**, rebuilt (39 tests):
  - Kept: source-repo detection, local-companion existence, the version reader, `check_constitution`, the version diagnostic, the source-repo exemption and `check_constitution_drift`.
  - New **`TestStatusV2`**:
    - schema v2 with the retired keys absent;
    - absent files produce the exact normal record;
    - a parameterized team-owned / sentinel / corrupted / legacy case checks `managed False`, the expected `historical_gator_block`, and that the native-file text section contains none of `modified, corrupted, legacy, foreign, drift, repair, missing, unhealthy`.
  - New **`TestRepairStub`**:
    - `repair`, `repair --dry-run`, `repair CLAUDE.md` and `repair --json` run through the real `main()` and exit 0, and the repo-root file bytes are identical before and after;
    - JSON reports `actions: []` and `native_files: "not-managed"`;
    - a guard patches `Path.read_text`/`read_bytes` to fail on any `*.local.md` access during `collect_status()`.
  - **`TestStateCliSurface`**: no `--source` flag, and `collect_status(repo_root)` takes only that argument.
- **`tests/test_loop.py`:** `_participant_surfaces()` and `test_escalate_before_wait_ordering` no longer load `entry_points` or read the root native files. Removed `test_entry_point_rendering_references_wait`, `test_live_entry_points_reference_wait` and `test_entry_point_rendering_mentions_executive_summary`. The protocol pairs, `/loop-join` (template and live) and the artifact-format pins remain. The single-source check for `GATOR_INIT.md` is in `TestGatorInitDocument` (checkpoint 1).
- **`tests/test_gatorize.py`:** removed `TestRenderEntryContentLocalCompanion` and `TestUpgradeLegacyEntryPoint` (their subject is deleted).
- **Packaging:** `test_packaging.py` passes; `scripts/gatorize/**/*` is a glob, so removing the file needs no package-data change.
- **Known gaps:** the broad `pytest tests -q` run is deferred to final approval.
- **Unstaged:** `.gator/.gator-version` and `.gator/runtime-pin.json` (pre-existing pin advance) stay unstaged. The previous session snippet stays staged as residue.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp3 (3 of 4) — State boundary and renderer retirement |
| Checkpoint base tree | `6bd881b0d6040570f759a54384b9fd8cde70b2ba` |
| Generation | 2 |
| Staged tree (candidate) | `118bc7f3fd14ff28ffbfebe6dfbd34f2fe4fdaaf` |
| Changed paths in this checkpoint | 13 (D 1, M 12) |
| Loop base HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` |
| Loop base tree | `ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86` |
| Current HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` (dev) |
| Changed paths vs loop base (cumulative) | 30 |
| Unstaged / untracked residue | 3 other + 57 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 6bd881b0d6040570f759a54384b9fd8cde70b2ba 118bc7f3fd14ff28ffbfebe6dfbd34f2fe4fdaaf
```

Cumulative context (approved checkpoints plus this one): `git diff ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86 118bc7f3fd14ff28ffbfebe6dfbd34f2fe4fdaaf`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-cross-cutting.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-installer.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-layout.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-loop.md
M .gator/charters/scripts-managed-state.md
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/cli.py
M src/gator_command/scripts/gator-state.py
D src/gator_command/scripts/gatorize/entry_points.py  [revisits an earlier checkpoint]
M src/gator_command/scripts/gatorize/managed_block.py  [revisits an earlier checkpoint]
M tests/test_gatorize.py  [revisits an earlier checkpoint]
M tests/test_loop.py
M tests/test_state.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 57 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
