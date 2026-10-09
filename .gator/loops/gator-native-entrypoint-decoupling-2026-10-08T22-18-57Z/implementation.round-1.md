# Implementation: Gator-Native Entry Point, Checkpoint 2 (Native-Neutral Install and Update)

## Executive Summary

- **What changed:**
  - `gatorize` no longer installs, refreshes, prompts about, or backs up `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`.
  - `gator update` (both copies) no longer plans or executes entry-point refreshes, and the template copy's inlined managed-block helpers are gone.
- **Key decision:** the `gator-update-v1` JSON keeps `entry_point_actions: []` and `summary.entry_point_actions: 0`, so its keys stay compatible. `entry_points.py` keeps only the renderer and legacy upgrade that `gator state` uses until checkpoint 3.
- **Main risk addressed:** silent mutation of repository-owned files. The new tests run the real `gatorize.main()` under `--yes` with empty stdin, and both update copies as real subprocesses, and they assert exact bytes.
- **Verification:** the neighboring suites pass: 586 tests across gatorize, template_sync, state, managed_block, layout, init, packaging and loop.

## Implementation Summary

- **`src/gator_command/scripts/gatorize.py`:**
  - Removed the `gatorize.entry_points` import (`render_entry_content`, `action_install_entry_points`, re-exported sentinels), the common-tail `action_install_entry_points(...)` call and the now-unused `has_command_post` local.
  - `print_pre_action_summary` (scenario 1 and scenarios 2–5) now says "Leave CLAUDE.md / AGENTS.md / GEMINI.md untouched (repository-owned)" instead of "Install(/refresh) entry-point files".
  - Updated the header `@writes` line and the scenario 3 fall-through comment.
- **`gatorize/entry_points.py`:**
  - Deleted `action_install_entry_points()`: create, refresh, legacy-upgrade, the foreign-file [1]/[2]/[3]/[b]/[x] prompt, `*_ROLLBACK.md` and the cancel hint. Also dropped its unused `shutil`/`sys`/`prompt` imports.
  - Updated the module docstring: it is legacy and serves only `gator state` until checkpoint 3.
  - `render_entry_content()` / `upgrade_legacy_entry_point()` are unchanged.
- **`gatorize/managed_block.py`:** a comment no longer points to the removed installer function (read-only detection now).
- **`gatorize/post_install.py`:** the recovery hint `(.gator/, entry-point files)` becomes `(.gator/)`.
- **`gator-update.py`** (package and starter copies, transformed identically):
  - Removed the Stage 4b import guard (package) or the inlined `GATOR_*` constants, fingerprints, `BlockState`, `find_managed_block` / `classify_managed_block` / `detect_legacy_gator_content` / `render_managed_region` and import guard (template).
  - Removed the `_ENTRY_POINT_META`, `plan_entry_point_updates` and `execute_entry_point_updates` section.
  - `print_plan(plan, dry_run, hooks)` and `print_result(added, updated, unchanged)` lose their entry-point parameters and lines.
  - `print_json_plan(plan, templates_dir, hooks)` emits the constant `entry_point_actions: []` / `0`.
  - `main()` no longer plans or executes entry points, and `made_changes = added > 0 or updated > 0`.
  - No callers outside the two copies existed (grep: only tests).

## Charter Updates

- **`scripts-installer.md`:**
  - Owns: "managed agent-entry blocks" is replaced by the shipped `GATOR_INIT.md`.
  - The `render_entry_content` entry is marked legacy, used by state only.
  - The `action_install_entry_points()` entry is replaced by an `upgrade_legacy_entry_point()` note.
  - New **TRIPWIRE: Native Agent Files Are Repository-Owned** (no create, prompt, backup or edit; summary wording; `.gitignore` `*.local.md` lines unchanged; pin `TestGatorizeLeavesNativeFilesUntouched`).
  - `main()` arrows, the managed_block caller list, the Before-Changing list and Connections are updated.
- **`scripts-repo-update.md`:**
  - Owns no longer lists entry-point execution.
  - The `plan_entry_point_updates() / execute_entry_point_updates()` entry is replaced by **TRIPWIRE: Native Agent Files Are Repository-Owned** (pin `TestUpdateLeavesNativeFilesUntouched`).
  - The `print_json_plan()` note: `entry_point_actions` is always `[]` / `0`.
  - The Before-Changing list and Connections are updated.
- **Checks against the code:**
  - `grep` finds no `entry_point_counts`, `plan_entry_point_updates`, `execute_entry_point_updates`, `_ENTRY_POINT*`, `render_entry_content` or `GATOR_BEGIN` in either `gator-update.py` copy (the transform script asserts this).
  - `action_install_entry_points` no longer exists under `src/`, except a comment fixed in managed_block.
- **Deferred to checkpoint 3, by plan:** `scripts-managed-state.md` still mentions a Stage 4b refresh in its baseline TRIPWIRE and Connections.
- **`commit_draft.md`:** a checkpoint 2 bullet is appended and staged.

## Verification

- `python -m pytest tests/test_gatorize.py tests/test_template_sync.py tests/test_state.py tests/test_managed_block.py tests/test_layout.py tests/test_init.py tests/test_packaging.py tests/test_loop.py -q`: **586 passed**.
- New tests:
  - **`TestGatorizeLeavesNativeFilesUntouched`** (`tests/test_gatorize.py`):
    - It runs the real `gatorize.main()` (scenario 2, `--yes`) in-process. HOME/USERPROFILE are redirected, `action_register` is stubbed so the real Dashboard registry is untouched, and `sys.stdin` is empty, so any prompt fails the test.
    - It is parameterized over `{foreign CRLF/non-ASCII 150+ lines, sentinel, legacy}` and `{sentinel, corrupted, foreign}`. It asserts exact bytes, that `GATOR_INIT.md` was installed, and that no `*_ROLLBACK.md` or `.pre-gator-update` exists.
    - A no-native-files case asserts none are created.
    - A summary test (scenarios 1 and 2) asserts the "untouched" wording and the absence of "entry-point files".
  - **`TestUpdateLeavesNativeFilesUntouched`** (`tests/test_template_sync.py`):
    - On a repo installed via `action_install_gator` and seeded with a CRLF sentinel `CLAUDE.md`, a legacy `AGENTS.md` and `CLAUDE.local.md`, it runs **each** `gator-update.py` copy as a subprocess (`--path --source`) with HOME redirected.
    - It asserts return code 0, exact bytes, `GEMINI.md` still absent (the retired refresh would have created it), no backup siblings and no "Entry-point" output.
    - I checked manually that both copies run the full update path, including the overlay, hooks and runtime pin.
  - **`TestJSONSchemaParity`**, rewritten and parameterized over both copies: `schema == gator-update-v1`, `entry_point_actions == []`, summary `0`, and the same keys in both copies.
- **Removed, with their subject:**
  - `tests/test_update_entry_points.py` (Stage 4b plan/execute);
  - the `test_template_sync.py` behavioral-parity and AST-equivalence layers (the inlined helpers are gone);
  - `test_entry_points_prompt_declares_auto_yes_1` and `TestEntryPointsCancelHint` in `test_gatorize.py` (the installer prompt is gone).
- **Repointed:** the renderer unit tests in `test_gatorize.py` now import `gatorize.entry_points` directly, because gatorize no longer re-exports it. They are retired with the renderer in checkpoint 3.
- **Known gaps:** the broad `pytest tests -q` run is deferred to final approval.
- **Unstaged:** `.gator/.gator-version` and `.gator/runtime-pin.json` are pre-existing, unrelated runtime-pin advancement and stay unstaged. The previous commit's session snippet remains staged as expected residue.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 4) — Native-neutral install and update |
| Checkpoint base tree | `d304c066a327ae7035165778814a8f9f3f3489d9` |
| Generation | 1 |
| Staged tree (candidate) | `6bd881b0d6040570f759a54384b9fd8cde70b2ba` |
| Changed paths in this checkpoint | 12 (D 1, M 11) |
| Loop base HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` |
| Loop base tree | `ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86` |
| Current HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` (dev) |
| Changed paths vs loop base (cumulative) | 24 |
| Unstaged / untracked residue | 3 other + 55 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff d304c066a327ae7035165778814a8f9f3f3489d9 6bd881b0d6040570f759a54384b9fd8cde70b2ba
```

Cumulative context (approved checkpoints plus this one): `git diff ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86 6bd881b0d6040570f759a54384b9fd8cde70b2ba`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-installer.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-repo-update.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/gator-update.py  [revisits an earlier checkpoint]
M src/gator_command/scripts/gatorize.py  [revisits an earlier checkpoint]
M src/gator_command/scripts/gatorize/entry_points.py
M src/gator_command/scripts/gatorize/managed_block.py
M src/gator_command/scripts/gatorize/post_install.py
M src/gator_command/templates/gator-starter/scripts/gator-update.py  [revisits an earlier checkpoint]
M tests/test_gatorize.py  [revisits an earlier checkpoint]
M tests/test_template_sync.py
D tests/test_update_entry_points.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 55 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
