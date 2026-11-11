# Charter: Gatorize Installer

**Covers**: `src/gator_command/scripts/gatorize.py`, `src/gator_command/scripts/gatorize/*.py`

## Owns

- Cross-platform installation and upgrade of Gator governance into a target repository.
- Scenario detection, template overlay, initial layout (including the shipped `GATOR_INIT.md` entry document), Git ignore rules, and dashboard registration.
- Explicit migration from legacy Memex content.
- Initial vendor-hook settings merge.

## Does Not Own

- Overlay updates after installation; see [`scripts-repo-update.md`](scripts-repo-update.md).
- Runtime hook dispatch and boot display; see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md).
- Session payload parsing; see [`scripts-session-capture.md`](scripts-session-capture.md).
- Shipped template content or layout classification.

---

### detect_scenario(target) / detect_generation(target)
File: src/gator_command/scripts/gatorize.py
Classify fresh directory, clean Git repo, existing Gator install, legacy Memex, or dual-presence state.
Filesystem: target repo and governance markers (R)
<- installer `main()`
! Ambiguous or destructive transitions require an explicit choice; detection itself is read-only.

### action_git_init(target)
File: src/gator_command/scripts/gatorize.py
Initialize Git only for the installer scenario that requires it.
<- installer `main()`
-> Git
! Gatorize never substitutes for Git initialization when the target scenario did not authorize it.

### action_install_gator(target)
File: src/gator_command/scripts/gatorize.py
Install shipped content using the current layout and preserve user-owned governance content.
Filesystem: target `.gator/` (W)
<- installer `main()` and Memex morph
-> template resolver, `copy_tree_overlay()`
! Shipped content lands under `.gator/.includes/` on v2; user-visible scaffolding remains at `.gator/` root.
! Shipped root files copied here are `constitution.md`, `gator-start-up.md` and `GATOR_INIT.md` (the `gator init` handoff document). Keep this tuple aligned with `gator_layout.SHIPPED_ROOT_FILES` and `gator-update.TEMPLATE_FILES`.
! Overlay does not delete unknown user files.

### install_hooks(target)
File: src/gator_command/scripts/gatorize.py
Install managed Git-hook wrappers through the canonical updater helper.
Filesystem: managed hook path and Git config (RW)
<- installer common tail
-> `gator-update.install_git_hooks()`
! Installer and updater use one hook implementation so health checks cannot drift from fresh installs.

### ensure_repo_gitignore(repo_root, untrack=True, untrack_paths=None) / transient_inventory(repo_root) / tracked_transient_files(repo_root) / untrack_transient_files(repo_root, paths=None)
File: src/gator_command/scripts/gatorize.py
Converge required machine-local, sensitive, and hook-transient Gator ignore entries without removing user rules, then untrack (index only, `git rm --cached`) tracked copies of `TRANSIENT_GATOR_FILES` so the ignore rule takes effect, and return the untracked paths. `TRANSIENT_GATOR_FILES` = the four hook ephemera (`status.json`, `whiteboard.md`, `commit_draft.md`, `commit_issues.md`; equal to `precommit_override.HOOK_EPHEMERA_PATHS`, pinned by `TestTransientMigration` in `tests/test_gatorize.py`) plus the retired v1 override files (#78). `transient_inventory()` drops `ENTERPRISE_EVIDENCE_FILES` (`status.json`, `whiteboard.md`) when `gator_core.is_enterprise_active()`: the Enterprise bundled hook still commits status.json and the server records it per commit (plan assumption A1). `tracked_transient_files()` is the read-only prediction (`git ls-files -z`, inventory order). `untrack_transient_files(paths=)` untracks exactly `paths` (the prediction) or, with None, what is tracked now.
Filesystem: `.gitignore` (RW), git index (W: removals only)
<- every successful install/upgrade scenario (gatorize common tail, `gator update` execution with the predicted list); `action_install_gator()` passes `untrack=False` so untracking happens once, in the reported tail
! Append only missing canonical entries; preserve comments, ordering, and unrelated patterns.
! Agent-tool credential files are in the managed set (2.37.1): `.claude/settings.local.json` (Claude Code saves approved commands, credentials included), `.gemini/.env` and `.codex/auth.json`. Ignoring does not untrack an already-committed copy; the pre-commit HYG-002 check flags staging one (see `scripts-precommit.md` → `run_layer1_lint()`). Pinned by `tests/test_agent_credential_files.py`.
! Presence is tested on exact, whitespace-stripped lines (#34). The earlier substring test treated `.gator/.override` as present whenever `.gator/.override-meta.json` was listed.
! Untracking never deletes working-tree files and is a silent no-op outside git or on a Git failure (returns `[]`). The resulting staged deletion is committed by the operator with the rest of the update; the pre-commit hook keeps a staged deletion of these paths (see `scripts-precommit.md`, TRIPWIRE "Hook Evidence Never Enters the Commit").

### transient_untrack_result(paths) / format_transient_untrack(result, predicted=False)
File: src/gator_command/scripts/gatorize.py
The ONE migration result shared by gatorize, `gator update` text, `gator update --result-json` and the Dashboard update response: `{paths, count, message, why}` or None when nothing was untracked (a no-op shows nothing). `message` is "Gator removed N hook-ephemera path(s) from the Git index. The files remain on disk. Git has staged their removal. Commit this migration with the update."; `why` is `TRANSIENT_UNTRACK_WHY`. `format_transient_untrack()` renders the terminal lines (the dry-run form says what *would* be removed).
<- gatorize `main()` common tail (after the summary), `gator-update.py`
! Write the wording only here; consumers render these fields and never restate them.

### write_gator_version(gator_dir, action)
File: src/gator_command/scripts/gatorize.py
Write installed generation/version metadata after a successful action.
Filesystem: `.gator/.gator-version` (W)
<- installer common tail
! Metadata describes completed state; do not stamp before the corresponding install step succeeds.

### find_managed_block() / classify_managed_block()
File: src/gator_command/scripts/gatorize/managed_block.py
Parse the single Gator sentinel region and classify absent, clean, modified, corrupted, legacy, or foreign state.
<- `gator state status` (sentinels and legacy fingerprints, read-only); the installer and updater no longer call it
! Multiple/misaligned sentinels are corrupted state, never permission to replace the whole file.

## TRIPWIRE: Native Agent Files Are Repository-Owned

`gatorize` never creates, prompts about, backs up, or edits `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, or `*.local.md` (gator-native entry point, 2026-10-08). The retired `gatorize/entry_points.py` (`render_entry_content()`, `upgrade_legacy_entry_point()`, `action_install_entry_points()` with its foreign-file backup-append-overwrite prompt and `*_ROLLBACK.md`) is gone. Loop-join and Executive Summary guidance lives only in the protocol, `/loop-join` and `GATOR_INIT.md` pointers. The pre-action summary states that these files are left untouched. The Gator entry document is `GATOR_INIT.md`, installed by `action_install_gator()`. The `.gitignore` entries for `*.local.md` remain (`ensure_repo_gitignore`) and are behavior-neutral. Pins: `TestGatorizeLeavesNativeFilesUntouched` in `tests/test_gatorize.py`.

### install_vendor_hooks()
File: src/gator_command/scripts/gatorize/vendor_hooks.py
Merge current Gator session-hook commands into supported vendor settings.
Filesystem: vendor settings (RW)
<- installer common tail
! Preserve unrelated commands and recognize older managed forms to avoid duplicates.

### action_morph_memex()
File: src/gator_command/scripts/gatorize/morph.py
Convert recognized legacy Memex knowledge into Gator-owned surfaces through an explicit morph scenario.
Filesystem: legacy and `.gator/` knowledge trees (RW)
<- installer `main()`
-> normal Gator install actions
! Morph is a migration path, not a reason to create new Memex structures.

## TRIPWIRE: No outbox.md

The outbox was retired with the command post. Gator never creates, reads, or deletes `outbox.md`. The retired `action_install_outbox()` wrote a root stub on every gatorize run through v2.38.0. Copies already in repositories belong to those repositories and are left as they are. Pins: `TestNoOutbox` in `tests/test_gatorize.py`.

### action_register(target, today)
File: src/gator_command/scripts/gatorize/post_install.py
Register the resolved repository path through the canonical machine registry helper.
Filesystem: `~/.gator/dashboard-repos.json` (RW)
<- successful installer common tail
! Registration is idempotent by resolved path and failure does not roll back an otherwise successful repo install.

### main()
File: src/gator_command/scripts/gatorize.py
Resolve templates, show the pre-action summary, gate unsafe working trees, execute one scenario, and run the common post-install tail.
<- `gator gatorize <target>`
-> scenario actions, hooks, registry
! Operate on the current branch; the retired `gator-install` branch workflow does not return.
! Noninteractive `--yes` changes prompting, not safety classification or corruption handling.

## Before Changing This Module

- Exercise every install scenario and dirty-tree gate.
- Verify user content, native agent files (byte-for-byte), and existing vendor commands survive.
- Check v2 layout plus user-visible scaffolding placement.
- Run installer, layout, hooks, registry, and install-cycle tests.

## Connections

-> [Repo Update](scripts-repo-update.md) - shared hook behavior and shipped root files
-> [Layout Resolver](scripts-layout.md) - initial directory placement
-> [Managed State](scripts-managed-state.md) - post-install classification and repair
-> [Session Capture](scripts-session-capture.md) - installed vendor hook targets
-> [Core Library](scripts-core-library.md) - registry and template resolution
