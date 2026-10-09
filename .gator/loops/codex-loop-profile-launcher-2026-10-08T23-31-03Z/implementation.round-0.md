# Implementation: Codex Loop Profile Launcher, Checkpoint 1 (Dedicated Profile Preparation)

## Executive Summary

- **What changed:** new `src/gator_command/scripts/loop/codex_launcher.py`. It covers dedicated-home resolution and validation, the Windows trust key, the canonical rule, a Gator-owned `config.toml` block with fail-closed conflict detection, read-only plan versus apply, and the `--dry-run` preview renderer. It is added to package-data. There is no CLI wiring yet; that is checkpoint 2.
- **Key decision:** there is no TOML library. Gator owns one marker-delimited block that is always last in `config.toml`, keeps every user byte outside it, and fails closed instead of creating duplicate tables. On Python 3.11+, `tomllib` validates the result.
- **Safety properties tested:**
  - nothing is written when preparation refuses;
  - `--dry-run` writes nothing;
  - `RULE_TEXT` is byte-identical to the rule in both reference-note copies;
  - the module imports no loop state modules.
- **Verification:** `pytest tests/test_loop_codex_launcher.py`: 22 passed (all match the plan's `-k "prepar or config or home or dry_run"` filter). `tests/test_packaging.py` passes.

## Implementation Summary

- **Constants:**
  - `RULE_TEXT` / `RULE_BYTES` is the verified five-subcommand rule, LF endings, no BOM.
  - `KNOWN_GENERATED_RULES` holds the CRLF variant, which is normalized.
  - The remaining constants: `RULE_FILE = "default.rules"`, `BLOCK_BEGIN` / `BLOCK_END`, `MANUAL_NOTE`, `VERIFIED_CODEX_VERSION = "0.144.1"` (used in checkpoint 2).
  - `ProfileError` always appends the manual-note pointer.
- **`default_home()`:** `~/.gator/adapters/codex/loop-home`.
- **`validate_home(home, repo_root, env, tempdir=None)`:** it resolves the home and refuses:
  - (inside) `~/.codex`;
  - (inside) the caller's `CODEX_HOME`;
  - inside the repository;
  - under `tempfile.gettempdir()`.
  
  Comparisons use path arithmetic with `os.path.normcase`; nothing is read.
- **`trust_key(repo_root, platform)`:** on Windows, a resolved path with backslashes, `\\?\` stripped and lowercased (the form Codex writes, spike §8.8). Otherwise the resolved path. A `'`, CR or LF raises `ProfileError`.
- **`render_config(existing_text, repo_key, platform)`** (pure):
  - `_split_block` finds exactly one BEGIN/END pair (none is also allowed). Any other marker count or order raises.
  - It parses only Gator's own `[projects.'…']` lines inside the block.
  - `_outside_conflicts` refuses, on Windows, a user `[windows]` table or a `windows.` dotted key, and on any platform a `[projects…]` header containing this repo's key (case-folded on Windows).
  - It regenerates the block at the end: `[windows] sandbox = "elevated"` on Windows, then the union of existing and current trusted keys.
  - It preserves the file's line-ending style and trims only trailing blank lines before the block.
  - `_parse_check` runs `tomllib.loads` when available.
- **`plan_preparation(home, repo_root, platform)`** (read-only): `mkdir`/`keep` for the home and `rules/`; refuse any file in `rules/` other than `default.rules`; rule absent → write; equal → keep; known generated → write (normalize); else refuse. For `config.toml` it drops a leading BOM, requires UTF-8, renders, and plans `keep` when the bytes are identical, otherwise `write`.
- **`apply_preparation(actions)`:** executes exactly the planned actions; a write goes to a `.gator-tmp` sibling followed by `os.replace`.
- **`render_dry_run(actions, home, repo_root, platform)`:** the "nothing is written or launched" header, the home, repo, trust entry, planned actions, rule text, the launch description with the child-only `CODEX_HOME`, and removal guidance.
- **`pyproject.toml`:** `"scripts/loop/codex_launcher.py"` is added to the explicit package-data list.

## Charter Updates

- **`scripts-loop.md`:**
  - **Covers** adds `loop/codex_launcher.py`.
  - **Owns** adds the launcher's responsibility and its no-loop-state-imports property.
  - **Does Not Own:** "Auto-launching of agent sessions" is narrowed to except the explicit, opt-in `gator loop codex` launcher (never starts, joins, or authorizes a loop; never handles a token).
  - Three new entries, with tripwires:
    1. `default_home / validate_home / trust_key`: never read the normal Codex home.
    2. `render_config` and helpers: the fail-closed list; the block stays last; no TOML framework.
    3. `plan_preparation / apply_preparation / render_dry_run`: the rule-ownership ladder; `RULE_TEXT` ↔ reference-note identity; never widen the allow-list; BOM handling.
  - The `cli.py` subcommand count and the `main(argv)` entry change in checkpoint 2, together with the routing.
- **`scripts-cross-cutting.md`:** the Package and License Surface example now names `scripts/loop/codex_launcher.py` alongside `gitsnap.py`.
- **Checks against the code:** each function named in the charter entries exists in the module (grep), and the fail-closed cases listed match `_split_block`, `_outside_conflicts` and the `plan_preparation` refusals one for one.
- **`commit_draft.md`:** frontmatter (`feature`, `notable`) and a checkpoint 1 bullet, staged.

## Verification

- `python -m pytest tests/test_loop_codex_launcher.py tests/test_packaging.py -q`: all pass (22 launcher tests; packaging confirms the new module is listed).
- Tests (`tests/test_loop_codex_launcher.py`):
  - `test_prepare_rule_matches_reference_note` [template, dogfood]: `RULE_TEXT` equals the note's rule block with its 3-space indent removed; no BOM.
  - `test_prepare_fresh_home_writes_only_rule_and_config`: exactly `rules/`, `rules/default.rules` (== `RULE_BYTES`) and `config.toml` (the exact expected block with a lowercase backslash key).
  - `test_prepare_is_idempotent_and_preserves_user_config`:
    - user top-level keys above the block and a `[profiles.p]` table after it are preserved, with the block moved last;
    - a re-plan is all `keep`, and applying it changes no byte;
    - a second repo adds a second trust entry inside the single block.
  - `test_prepare_normalizes_known_generated_rule` (CRLF → LF canonical).
  - `test_prepare_fails_closed_without_writing`: seven parameterized cases (unfamiliar rule, extra rule file, user `[windows]`, `windows.` dotted key, same-repo trust entry in different case, begin without end, duplicate begin). Each raises with the manual-note pointer and leaves the home byte-identical.
  - `test_config_non_windows_has_no_windows_table`, `test_config_refuses_unquotable_repo_path`, and `test_config_strips_bom_and_keeps_line_endings` (CRLF kept).
  - `test_home_validation_refuses`: four parameterized cases (normal `~/.codex` via patched `Path.home`, the caller's `CODEX_HOME`, inside the repo, under the injected temp dir). `test_home_default_is_machine_local_and_accepted`.
  - `test_dry_run_preview_is_read_only`: the home is not created and the repo snapshot is unchanged; the preview contains the home, repo, trust entry, rule pattern, `CODEX_HOME=` and the "nothing is written or launched" header.
  - `test_prepare_module_has_no_loop_state_imports`.
- **Known gaps** (by plan, checkpoint 2): the `execpolicy` proof, Codex resolution, the version and platform checks, launch, CLI routing, the reference-note Quick Setup and the real-Codex integration test.
- **Unstaged:** `.gator/.gator-version` and `.gator/runtime-pin.json` (the earlier pin advance) stay unstaged. The previous commit's session snippet remains staged as expected residue.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 2) — Dedicated profile preparation |
| Checkpoint base tree | `aa7d41181d91c6252b79abacd0da94e835d10de7` |
| Generation | 0 |
| Staged tree (candidate) | `92acce6d70fbb116e197bd8d2792ab64a1b7d6aa` |
| Changed paths in this checkpoint | 7 (A 3, M 4) |
| Loop base HEAD | `7140baf048b0f667ceb1e24fb3ec0b01c9cb78db` |
| Loop base tree | `aa7d41181d91c6252b79abacd0da94e835d10de7` |
| Current HEAD | `7140baf048b0f667ceb1e24fb3ec0b01c9cb78db` (dev) |
| Changed paths vs loop base (cumulative) | 7 |
| Unstaged / untracked residue | 3 other + 71 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff aa7d41181d91c6252b79abacd0da94e835d10de7 92acce6d70fbb116e197bd8d2792ab64a1b7d6aa
```

Cumulative context (approved checkpoints plus this one): `git diff aa7d41181d91c6252b79abacd0da94e835d10de7 92acce6d70fbb116e197bd8d2792ab64a1b7d6aa`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-loop.md
M .gator/commit_draft.md
A .gator/session-snippets/2026-10-08-gator-7140baf048b0f.json
M pyproject.toml
A src/gator_command/scripts/loop/codex_launcher.py
A tests/test_loop_codex_launcher.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 71 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
