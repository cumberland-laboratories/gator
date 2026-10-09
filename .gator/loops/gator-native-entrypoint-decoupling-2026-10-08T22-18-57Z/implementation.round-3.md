# Implementation: Gator-Native Entry Point, Checkpoint 4 (Explicit-Start Adoption)

## Executive Summary

- **What changed:**
  - The Dashboard loop-join prompt names `gator init` and `GATOR_INIT.md`.
  - Every "Revise" surface from the plan's Change 9 inventory is rewritten for the `gator init` → `GATOR_INIT.md` contract: README, three docs, and seven starter procedures/reference notes plus their byte-identical dogfood copies.
  - The CHANGELOG `[Unreleased]` entry carries migration notes.
- **Key decision:** vendor files are described as optional and repository-owned, with a suggested one-line `gator init` pointer. Historical blocks are "no longer refreshed", never "managed".
- **Durability:** the new `tests/test_native_file_guidance.py` fails on seven retired-claim patterns across all maintained surfaces. It was verified red on the known hits before the revision and green after.
- **Verification:** the final broad suite `python -m pytest tests -q` gives **2452 passed, 22 skipped, 2 xfailed** (20m36s).

## Implementation Summary

- **`src/gator_command/scripts/gator-dashboard.py`** (`_handle_loop_prompt`): after the fixed status line, every draftor/reviewer prompt appends "New to Gator in this repo? Run `gator init` first; its handoff names GATOR_INIT.md and the loop protocol." This is additive; the brief and planning-source pointers are unchanged. Pointer only, with no content and no time language.
- **Inventory re-run** (same `grep -rIE` scope and pattern as Change 9): the only hit not in the plan's tables is `GATOR_INIT.md` itself (4 lines). That is the new canonical document and is **preserve**; the guard checks it and it passes. The `.gator/.includes/` hits match the template list plus the four dogfood-only notes already classified **preserve**.
- **Revised:**
  - **`README.md`:** install "what it does" now says `.gator/` + `GATOR_INIT.md` and that sessions start with `gator init`. The `*.local.md` line now says Gator only gitignores them. A new "does not create, edit, back up, or repair CLAUDE.md/AGENTS.md/GEMINI.md" bullet with the pointer suggestion is added. The update paragraph is rewritten, including historical blocks staying byte-identical.
  - **`docs/how-to-use-gator.md`:**
    - The repo tree shows native files as "optional, yours" and `.includes/GATOR_INIT.md`.
    - "Working with a Team" lists three surfaces: Gator governance in `.gator/`, team vendor files and `*.local.md`.
    - The Dashboard Update and terminal update paragraphs no longer mention managed blocks or backups.
  - **`docs/architecture.md`:** the tree gains `GATOR_INIT.md` and native files become optional and repository-owned. Multi-Model Architecture: any model runs `gator init` → `GATOR_INIT.md` → constitution → charters.
  - **`docs/custom-skills-and-team-workflow.md`:**
    - The native-files section is replaced: "Nothing", the `gator init`/`GATOR_INIT.md` start, a one-line pointer example, and historical-block guidance.
    - The two managed-block and backup screenshot TODOs are removed; the tracked-vs-local TODO stays.
    - Precedence, team-shared skills, best practices, the recovery scenario ("still has an old GATOR:BEGIN block"), the clean-slate wording and See Also are rewritten.
  - **Starter templates, with dogfood copies byte-identical:**
    - `enforcer-review.md` and `enforcer-configuration.md`: the "primary-agent entrypoint" claims are replaced by "the repository's own CLAUDE.md/AGENTS.md (if present) may frame the model as primary agent". The enforcer-role guidance is unchanged.
    - `concierge-responses.md`: the "My CLAUDE.md is really long" answer is rewritten around `gator init`, Gator never appending, the optional pointer and historical blocks. The AGENTS.md, enforcer and "Gatorize" lines are reworded.
    - `local-agent-skills.md`: the pattern, surfaces, precedence and See Also are rewritten for repository-owned native files.
    - `what-gator-requires-from-a-model.md`: "honor the entry point" becomes run `gator init` / follow `GATOR_INIT.md`, and the layered structure is updated.
    - `gator-version-drift.md`: "modified managed blocks" is dropped. Class A gains `GATOR_INIT.md`, and native files are explicitly not Class A.
    - `knowledge-capture.md`: the vendor-file section suggests a `gator init` pointer.
  - **`CHANGELOG.md` `[Unreleased]`:** Added / Changed / Removed / Migration notes. The notes say nothing is deleted, blocks are frozen and lose on conflict, run `gator update` to add `GATOR_INIT.md`, leftover backup files are the user's, and adapters are not included.
- **Preserved, per the plan:** `docs/supporting-research.md`, `docs/what-is-navigation-coding.md`, the generic "entry point" false positives, the dogfood-only positioning notes and the existing CHANGELOG history.

## Charter Updates

- **`scripts-dashboard.md`:** a `_handle_loop_prompt` tripwire records the explicit-start pointer line: native agent files no longer teach "gator loop join", so the prompt must not rely on them. Pin: `test_prompt_names_explicit_gator_init_start`.
- No other code changed in this checkpoint (docs and tests only besides the Dashboard prompt), so no other charter applies. The earlier checkpoints' charters already describe the behavior the docs now document.
- **`commit_draft.md`:** a checkpoint 4 bullet is appended and staged.

## Verification

- **Retired-claim guard, red/green:**
  - **Before** revising the docs, `pytest tests/test_native_file_guidance.py` failed 5 of 7 pattern cases. The hits were README l.27/116, how-to l.295, custom-skills l.59/61/114/121, enforcer-review l.78, enforcer-configuration l.97, concierge l.372/400/466 and local-agent-skills l.5.
  - **After:** 14 passed (7 patterns and 7 template↔dogfood pairs).
- `pytest tests/test_dashboard_loop_brief.py -k Prompt`: 3 passed, including the new `test_prompt_names_explicit_gator_init_start` (reviewer role, pointer after the status command, `GATOR_INIT.md` named). The existing `TestPromptHasNoTime` passes in the full run, so the pointer has no time language.
- **Session-opening smoke test** (`TestGatorizeLeavesNativeFilesUntouched::test_repo_without_native_files_gets_none`, extended):
  - It gatorizes a repo with no native files through the real `gatorize.main()`, then runs `gator-init.py --path repo` as a subprocess.
  - It asserts `1. .gator/.includes/GATOR_INIT.md` / `2. .gator/.includes/constitution.md` and that still no native files exist.
  - HOME is redirected; I checked the real `~/.gator/dashboard-repos.json` and no test entries were added.
- **Final broad suite, run once per the plan's verification ladder:** `python -m pytest tests -q -x -p no:cacheprovider` gives **2452 passed, 22 skipped, 2 xfailed in 1236.78s**. The xfails are the pre-existing v1 `active-vendor-session.json` compat tests.
- **Unstaged:** `.gator/.gator-version` and `.gator/runtime-pin.json` (pre-existing pin advance) stay unstaged. The previous session snippet stays staged as residue.
- **Not done, by design:** this repository's own root `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` keep their historical blocks byte-for-byte (plan assumption). Trimming them is the Architect's separate choice.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp4 (4 of 4) — Explicit-start adoption |
| Checkpoint base tree | `118bc7f3fd14ff28ffbfebe6dfbd34f2fe4fdaaf` |
| Generation | 3 |
| Staged tree (candidate) | `aa7d41181d91c6252b79abacd0da94e835d10de7` |
| Changed paths in this checkpoint | 25 (A 1, M 24) |
| Loop base HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` |
| Loop base tree | `ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86` |
| Current HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` (dev) |
| Changed paths vs loop base (cumulative) | 53 |
| Unstaged / untracked residue | 3 other + 59 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 118bc7f3fd14ff28ffbfebe6dfbd34f2fe4fdaaf aa7d41181d91c6252b79abacd0da94e835d10de7
```

Cumulative context (approved checkpoints plus this one): `git diff ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86 aa7d41181d91c6252b79abacd0da94e835d10de7`.

Changed paths in this checkpoint (status, path):

```text
M .gator/.includes/procedures/enforcer-review.md
M .gator/.includes/procedures/gator-version-drift.md
M .gator/.includes/procedures/knowledge-capture.md
M .gator/.includes/reference-notes/concierge-responses.md
M .gator/.includes/reference-notes/enforcer-configuration.md
M .gator/.includes/reference-notes/local-agent-skills.md
M .gator/.includes/reference-notes/what-gator-requires-from-a-model.md
M .gator/charters/scripts-dashboard.md
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M CHANGELOG.md
M README.md
M docs/architecture.md
M docs/custom-skills-and-team-workflow.md
M docs/how-to-use-gator.md
M src/gator_command/scripts/gator-dashboard.py
M src/gator_command/templates/gator-starter/procedures/enforcer-review.md
M src/gator_command/templates/gator-starter/procedures/gator-version-drift.md
M src/gator_command/templates/gator-starter/procedures/knowledge-capture.md
M src/gator_command/templates/gator-starter/reference-notes/concierge-responses.md
M src/gator_command/templates/gator-starter/reference-notes/enforcer-configuration.md
M src/gator_command/templates/gator-starter/reference-notes/local-agent-skills.md
M src/gator_command/templates/gator-starter/reference-notes/what-gator-requires-from-a-model.md
M tests/test_dashboard_loop_brief.py
M tests/test_gatorize.py  [revisits an earlier checkpoint]
A tests/test_native_file_guidance.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 59 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
