# Charter: Gatorize Installer

**Covers**: `src/gator_command/scripts/gatorize.py`, `src/gator_command/scripts/gatorize/*.py`

## Owns

- Cross-platform installation and upgrade of Gator governance into a target repository.
- Scenario detection, template overlay, initial layout, managed agent-entry blocks, Git ignore rules, and dashboard registration.
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
! Overlay does not delete unknown user files.

### install_hooks(target)
File: src/gator_command/scripts/gatorize.py
Install managed Git-hook wrappers through the canonical updater helper.
Filesystem: managed hook path and Git config (RW)
<- installer common tail
-> `gator-update.install_git_hooks()`
! Installer and updater use one hook implementation so health checks cannot drift from fresh installs.

### ensure_repo_gitignore(repo_root)
File: src/gator_command/scripts/gatorize.py
Converge required machine-local and sensitive Gator ignore entries without removing user rules.
Filesystem: `.gitignore` (RW)
<- every successful install/upgrade scenario
! Append only missing canonical entries; preserve comments, ordering, and unrelated patterns.

### write_gator_version(gator_dir, action)
File: src/gator_command/scripts/gatorize.py
Write installed generation/version metadata after a successful action.
Filesystem: `.gator/.gator-version` (W)
<- installer common tail
! Metadata describes completed state; do not stamp before the corresponding install step succeeds.

### find_managed_block() / classify_managed_block()
File: src/gator_command/scripts/gatorize/managed_block.py
Parse the single Gator sentinel region and classify absent, clean, modified, corrupted, legacy, or foreign state.
<- installer, updater, managed-state repair
! Multiple/misaligned sentinels are corrupted state, never permission to replace the whole file.

### render_managed_region() / render_entry_content()
File: src/gator_command/scripts/gatorize/entry_points.py
Render vendor-specific entry instructions from one managed baseline. Includes loop-join paragraph with `gator loop wait` handoff and escalate-first ordering.
<- install, update, state repair
! Preserve the `GATOR:BEGIN` / `GATOR:END` boundary and keep cross-vendor semantics equivalent. Loop-join content pinned by `TestWaitHandoffAlignment` in `tests/test_loop.py`.

### action_install_entry_points() / upgrade_legacy_entry_point()
File: src/gator_command/scripts/gatorize.py
Create or upgrade CLAUDE.md, AGENTS.md, and GEMINI.md without overwriting content outside the managed region.
Filesystem: root agent entry files (RW), backups for legacy/modified replacement (W)
<- installer `main()`
! Foreign and corrupted content is not silently replaced. Back up any user-bearing file before transformation.
! `*.local.md` is machine-personal and never managed.

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
-> scenario actions, hooks, entry points, registry
! Operate on the current branch; the retired `gator-install` branch workflow does not return.
! Noninteractive `--yes` changes prompting, not safety classification or corruption handling.

## Before Changing This Module

- Exercise every install scenario and dirty-tree gate.
- Verify user content, foreign entry files, and existing vendor commands survive.
- Check v2 layout plus user-visible scaffolding placement.
- Run installer, layout, entry-point, hooks, registry, and install-cycle tests.

## Connections

-> [Repo Update](scripts-repo-update.md) - shared hook and managed-block behavior
-> [Layout Resolver](scripts-layout.md) - initial directory placement
-> [Managed State](scripts-managed-state.md) - post-install classification and repair
-> [Session Capture](scripts-session-capture.md) - installed vendor hook targets
-> [Core Library](scripts-core-library.md) - registry and template resolution
