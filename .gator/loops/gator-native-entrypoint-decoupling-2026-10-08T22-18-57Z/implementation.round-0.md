# Implementation: Gator-Native Entry Point, Checkpoint 1 (Bootstrap Contract and Handoff)

## Executive Summary

- **What changed:**
  - A new shipped `GATOR_INIT.md`, the template copy plus a byte-identical dogfood copy in `.gator/.includes/`.
  - `GATOR_INIT.md` is classified as a shipped root file in both `gator_layout.py` copies, with a new `GatorPaths.bootstrap`.
  - It is placed by fresh install and by `gator update` (both copies).
  - `gator init` names it first in both copies.
- **Key decision:** one helper, `session_opening_reads()`, owns the read order for the text directive and the new additive `--json` `session_opening` block.
- **Legacy safety:** a repo without the file keeps the old two-step handoff plus a `gator update` hint, and `gator init` never creates the file. A v2 repo without it still resolves as v2.
- **Verification:** the focused suites (test_layout, test_init, test_gatorize, test_gator_core) pass: 280 tests. The neighboring update, sync, packaging, session-open and managed-block suites pass: 115 tests.

## Implementation Summary

- **`src/gator_command/templates/gator-starter/GATOR_INIT.md`** (new) and **`.gator/.includes/GATOR_INIT.md`** (byte-identical dogfood copy). The document is ~40 lines in four sections:
  - the start (`gator init`), and the location "next to `constitution.md` and `procedures/`";
  - *Before your first response:* the constitution, then mission/roadmap/inbox, then `gator-start-up.md` for template-only charters;
  - *Joining a loop*, read only with a loop token: the protocol, then `gator loop status`;
  - *Native agent files:* Gator does not create, edit, back up or repair them; local guidance may extend but not override; historical `GATOR:BEGIN/END` blocks are no longer refreshed and lose on conflict.
  - It restates no protocol rules: no wait flags and no Executive Summary text.
- **`gator_layout.py`** (package and starter copies): `"GATOR_INIT.md"` is added to `SHIPPED_ROOT_FILES`. A new `GatorPaths.bootstrap` field is set by `_shipped_file("GATOR_INIT.md")`. `_has_required_includes_content` is unchanged, so legacy v2 repos without the file remain v2.
- **`gatorize.py` `action_install_gator`:** the root-file copy tuple now includes `GATOR_INIT.md`, so it lands in `.gator/.includes/`.
- **`gator-update.py`** (package and starter copies): `TEMPLATE_FILES` includes `GATOR_INIT.md`. `plan_updates` routes it to `shipped_base` (`.includes/` on v2, root on v1), as it does for `constitution.md`.
- **`gator-init.py`** (package and starter copies; the starter copy keeps its pre-existing intentional divergence, the missing drift suffix):
  - New `_rel()` display helper.
  - New **`session_opening_reads(repo_root, paths)`** returns `(bootstrap_rel_or_None, reads)`. The bootstrap is included only when `paths.bootstrap.is_file()`, behind a `getattr`/try guard so it stays non-fatal.
  - `session_opening_directive` is rebuilt on it:
    - with the file present: `1. GATOR_INIT.md`, `2. constitution`, `3. mission · roadmap · inbox`;
    - without it: the legacy `1. constitution`, `2. context`, plus `note: this repo predates .gator's GATOR_INIT.md — \`gator update\` adds it`.
  - New `_session_opening_json()` adds `session_opening: {bootstrap, bootstrap_present, reads}` to `print_json`. This is additive.
  - New source lines use `\u` escapes, matching the file's existing convention.
- **Not in this checkpoint, per the plan:** native-file behavior in gatorize/update/state, the docs, and the Dashboard prompt.

## Charter Updates

- **`scripts-layout.md`:**
  - New `!` tripwire: `GATOR_INIT.md` is a shipped root file in both copies, resolves like `constitution.md`, a flat-root copy on v2 is `mixed`, and it is not part of required-includes validation.
  - `get_gator_paths` documents `bootstrap` (callers test `.is_file()`).
  - The pins point to `TestBootstrapResolution`.
- **`scripts-repo-lifecycle.md`:**
  - New `session_opening_reads()` entry: single source, read-only, never creates.
  - `session_opening_directive()` describes bootstrap-first versus the legacy fallback.
  - `print_boot_sequence() / print_json()` documents the additive `session_opening` and that consumers must tolerate its absence.
- **`scripts-installer.md`:** `action_install_gator` lists the three shipped root files and requires them to stay aligned with `SHIPPED_ROOT_FILES` and `TEMPLATE_FILES`.
- **`scripts-repo-update.md`:** `plan_file_update() / plan_updates()` notes that `TEMPLATE_FILES` includes `GATOR_INIT.md` (added to legacy repos, idempotent).
- **`scripts-cross-cutting.md`:** Shipped-Copy Synchronization records `TestGatorInitDocument` (template↔dogfood byte-identity and the pointer-only content) and `TestSessionOpeningHandoff` (both init copies).
- **Checks against the code:**
  - The function names in the charter entries were grepped and match: `session_opening_reads`, `_session_opening_json`, `session_opening_directive`, `GatorPaths.bootstrap`, `TEMPLATE_FILES`.
  - The installer note matches the edited tuple in `action_install_gator`.
- **`commit_draft.md`:** frontmatter and a checkpoint 1 change-log bullet, staged.

## Verification

- `python -m pytest tests/test_layout.py tests/test_init.py tests/test_gatorize.py tests/test_gator_core.py -q`: **280 passed**. This includes the existing `test_banner_ends_with_session_opening_directive` and `test_session_opening_directive_resolves_v2_path`, which cover the legacy path unchanged.
- `python -m pytest tests/test_template_sync.py tests/test_update_entry_points.py tests/test_packaging.py tests/test_session_open.py tests/test_managed_block.py -q`: **115 passed**. No regression in update parity or packaging; `GATOR_INIT.md` ships through the existing `templates/**/*` package-data glob.
- New tests:
  - **`TestBootstrapResolution`** (`test_layout.py`):
    - the bootstrap resolves beside the constitution for v1 (`.gator/`) and v2 (`.includes/`), parameterized;
    - v2 without the file stays v2;
    - a flat-root copy on v2 → `mixed`;
    - both layout copies classify it as shipped;
    - `plan_updates`/`execute_updates` with the real templates add it on the first run (`.includes/`, template bytes, nothing at the flat root) and plan `unchanged` on the second.
  - **`TestFreshInstallBootstrap`** (`test_gatorize.py`): `action_install_gator` places the template bytes in `.includes/` and nothing at the flat root.
  - **`TestSessionOpeningHandoff`** (`test_init.py`), parameterized over **both** `gator-init.py` copies:
    - bootstrap-first numbering when present;
    - the legacy order plus the hint when absent, with the file still absent after both the directive and `print_json` (the never-create check);
    - exact `session_opening` JSON.
  - **`TestGatorInitDocument`** (`test_init.py`):
    - the dogfood copy is byte-identical;
    - the document names `gator init`, `constitution.md`, `gator-start-up.md`, `procedures/gator-loop-protocol.md` and `gator loop status`;
    - it does not contain `--max-seconds` or `Executive Summary` (single-source).
- **Manual check:**
  - `python src/gator_command/scripts/gator-init.py` in this repo prints `1. .gator/.includes/GATOR_INIT.md — Gator's entry point for this session`, then the constitution and context lines.
  - `--json` shows the expected `session_opening`.
- **Known gaps:**
  - The broad suite (`pytest tests -q`) is deferred to final approval, per the plan's verification ladder.
- **Candidate residue:**
  - `.gator/session-snippets/2026-10-08-gator-8d5fae77f21b0.json` was already staged before this checkpoint. It is the previous commit's session snippet (expected governance residue swept up by the next commit) and is not part of this change.
  - `.gator/.gator-version` and `.gator/runtime-pin.json` are modified but deliberately left unstaged: they are pre-existing runtime-pin advancement, not part of this change.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 4) — Bootstrap contract and handoff |
| Checkpoint base tree | `ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86` |
| Generation | 0 |
| Staged tree (candidate) | `d304c066a327ae7035165778814a8f9f3f3489d9` |
| Changed paths in this checkpoint | 19 (A 3, M 16) |
| Loop base HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` |
| Loop base tree | `ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86` |
| Current HEAD | `8d5fae77f21b0d11f44c1e294c0dadfb1b6ff621` (dev) |
| Changed paths vs loop base (cumulative) | 19 |
| Unstaged / untracked residue | 3 other + 50 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86 d304c066a327ae7035165778814a8f9f3f3489d9
```

Cumulative context (approved checkpoints plus this one): `git diff ea8a4db34e3e715fedbe9b385b1c8461b5cf3a86 d304c066a327ae7035165778814a8f9f3f3489d9`.

Changed paths in this checkpoint (status, path):

```text
A .gator/.includes/GATOR_INIT.md
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-installer.md
M .gator/charters/scripts-layout.md
M .gator/charters/scripts-repo-lifecycle.md
M .gator/charters/scripts-repo-update.md
M .gator/commit_draft.md
A .gator/session-snippets/2026-10-08-gator-8d5fae77f21b0.json
M src/gator_command/scripts/gator-init.py
M src/gator_command/scripts/gator-update.py
M src/gator_command/scripts/gator_layout.py
M src/gator_command/scripts/gatorize.py
A src/gator_command/templates/gator-starter/GATOR_INIT.md
M src/gator_command/templates/gator-starter/scripts/gator-init.py
M src/gator_command/templates/gator-starter/scripts/gator-update.py
M src/gator_command/templates/gator-starter/scripts/gator_layout.py
M tests/test_gatorize.py
M tests/test_init.py
M tests/test_layout.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 50 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
