# Charter: Gatorize Installer

**Covers**: `src/gator_command/scripts/gatorize.py`, `src/gator_command/scripts/gatorize/*.py`

## Owns

- Cross-platform installation and upgrade of Gator governance into a target repository.
- Scenario detection, template overlay, initial layout (including the shipped `GATOR_INIT.md` entry document), Git ignore rules, and dashboard registration.
- Explicit migration from legacy Memex content.
- The one-time repository vendor cleanup (`gatorize/vendor_cleanup.py`), which `gator update` calls through its `gatorize` sibling import.

## Does Not Own

- Overlay updates after installation; see [`scripts-repo-update.md`](scripts-repo-update.md).
- Runtime hook dispatch and boot display; see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md).
- Session payload parsing; see [`scripts-session-capture.md`](scripts-session-capture.md).
- Gator's session hooks in AI-tool user settings; see [`scripts-machine-integration.md`](scripts-machine-integration.md).
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
! Shipped content lands under `.gator/.includes/` on v2. Scaffolding goes through `_scaffold()`, which asks `gator-update.scaffolding_in_managed_space()` (#109): `_template.md` and the on-demand folders' README/template go to `.includes/<folder>/`, `README.md` stays at the root. `threads/`, `policies/` and `field-guides/` are not created (on demand). Charter `README.md` and `_template.md` are also written to `.includes/charters/`, matching `gator update`'s `CHARTER_TEMPLATE_FILES`.
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
Converge required machine-local, sensitive, and hook-transient Gator ignore entries without removing user rules, then untrack (index only, `git rm --cached`) tracked copies of `TRANSIENT_GATOR_FILES` so the ignore rule takes effect, and return the untracked paths. `TRANSIENT_GATOR_FILES` = the four hook ephemera (`status.json`, `whiteboard.md`, `commit_draft.md`, `commit_issues.md`; equal to `precommit_override.HOOK_EPHEMERA_PATHS`, pinned by `TestTransientMigration` in `tests/test_gatorize.py`) plus the retired v1 override files (#78). The inventory also carries `PERSONAL_GATOR_FILES` (`.gator/inbox.md`, #104: each person's own notes, ignored and untracked through the same migration, in every repository including Enterprise). `transient_inventory()` drops `ENTERPRISE_EVIDENCE_FILES` (`status.json`, `whiteboard.md`) when `gator_core.is_enterprise_active()`: the Enterprise bundled hook still commits status.json and the server records it per commit (plan assumption A1). `tracked_transient_files()` is the read-only prediction (`git ls-files -z`, inventory order). `untrack_transient_files(paths=)` untracks exactly `paths` (the prediction) or, with None, what is tracked now.
Filesystem: `.gitignore` (RW), git index (W: removals only)
<- every successful install/upgrade scenario (gatorize common tail, `gator update` execution with the predicted list); `action_install_gator()` passes `untrack=False` so untracking happens once, in the reported tail
! Append only missing canonical entries; preserve comments, ordering, and unrelated patterns.
! Agent-tool credential files are in the managed set (2.37.1): `.claude/settings.local.json` (Claude Code saves approved commands, credentials included), `.gemini/.env` and `.codex/auth.json`. Ignoring does not untrack an already-committed copy; the pre-commit HYG-002 check flags staging one (see `scripts-precommit.md` → `run_layer1_lint()`). Pinned by `tests/test_agent_credential_files.py`.
! Presence is tested on exact, whitespace-stripped lines (#34). The earlier substring test treated `.gator/.override` as present whenever `.gator/.override-meta.json` was listed.
! Untracking never deletes working-tree files and is a silent no-op outside git or on a Git failure (returns `[]`). The resulting staged deletion is committed by the operator with the rest of the update; the pre-commit hook keeps a staged deletion of these paths (see `scripts-precommit.md`, TRIPWIRE "Hook Evidence Never Enters the Commit").

### transient_untrack_result(paths) / format_transient_untrack(result, predicted=False)
File: src/gator_command/scripts/gatorize.py
The ONE migration result shared by gatorize, `gator update` text, `gator update --result-json` and the Dashboard update response: `{paths, count, message, why}` or None when nothing was untracked (a no-op shows nothing). `message` is "Gator removed N hook-ephemera path(s) from the Git index. The files remain on disk. Git has staged their removal. Commit this migration with the update."; `why` is `TRANSIENT_UNTRACK_WHY`. When the paths include a `PERSONAL_GATOR_FILES` entry (#104) the word is "machine-local" (dry-run header "Machine-local paths to remove…") and `why` is `TRANSIENT_UNTRACK_WHY` (when hook files are also present) followed by `PERSONAL_UNTRACK_WHY`; hook-only results keep the #78 wording exactly. `format_transient_untrack()` renders the terminal lines (the dry-run form says what *would* be removed).
<- gatorize `main()` common tail (after the summary), `gator-update.py`
! Write the wording only here; consumers render these fields and never restate them.

### rescue_personal_inbox(repo_root) / format_inbox_rescue(result) / restore_personal_inbox(repo_root) / PERSONAL_GATOR_FILES / PERSONAL_UNTRACK_WHY
File: src/gator_command/scripts/gatorize.py
When one clone commits the #104 untracking, `git pull` in another clone deletes that clone's unmodified `.gator/inbox.md`. Once per clone it restores the file: if `.gator/inbox.md` is not tracked, does not exist, and `git log -1 --diff-filter=D` finds a deleting commit, it writes the file from that commit's parent. It then records `$(git rev-parse --git-path gator-inbox-checked)`, so a later deliberate deletion is respected. While the inbox is still tracked (not migrated yet) it returns None and writes no marker, so an early check does not use up the restore. Returns the short SHA restored from, or None; never raises.
**#113: the personal inbox is `.gator/inbox.local.md`, a path no commit has ever tracked.** Git treats an ignored file as disposable: checking out a commit that still tracks `.gator/inbox.md` overwrote the personal copy without warning, and moving forward again deleted it. `rescue_personal_inbox()` moves an untracked `.gator/inbox.md` to `inbox.local.md` (`moved`); an identical existing copy wins (`identical`, the legacy file is removed); a different one is never overwritten, and the legacy file becomes `inbox.local.md.from-inbox-md` (then `-2`, `-3`, …; `kept-both`). While the checkout still tracks `inbox.md` it does nothing. `format_inbox_rescue()` is the one human line for its result. The ignore rule `.gator/inbox.local*` covers the personal file and every rescue copy; `.gator/inbox.md` stays ignored. `PERSONAL_GATOR_FILES` also lists `.gator/inbox.local.md`, so a force-added copy is untracked too. `write_stubs()` creates `inbox.local.md`. `restore_personal_inbox()` (the #104 pull restore) now writes `inbox.local.md`, and only when neither file exists. Callers run the rescue first.
! Pinned by `tests/test_personal_inbox.py` → `TestRescueFromOlderCheckouts`, which replays the reported sequence (rescue, checkout of a pre-2.40 branch, checkout forward, merge of the old branch) and also shows the loss without the rescue.
Filesystem: `.gator/inbox.local.md` (W: rescue target, restore only when both inbox files are missing), `.gator/inbox.md` (moved away by the rescue), Git-private marker (W), git (R)
<- `gator update` execution (after the untracking report), `gator init` `main()` via `_restore_personal_inbox()`
! Pinned by `tests/test_personal_inbox.py` (a real clone, untrack, commit, pull).

### plan_scaffold_cleanup(repo_root) / apply_scaffold_cleanup(repo_root, actions) / format_scaffold_cleanup(actions, predicted=False)
File: src/gator_command/scripts/gatorize/scaffold_cleanup.py
The one-time #109 removal of root scaffolding that earlier versions left in a v2 repository: every `.gator/<folder>/_template.md` in `SCAFFOLD_DIRS`, and, in an on-demand folder (`ON_DEMAND_DIRS`) that holds nothing but `README.md` / `_template.md` / `.gitkeep`, those files too, then the empty folder. Read-only plan `[{path, action: "delete", tracked}]` (sorted; `[]` without `.gator/.includes/`, a v1 layout). Apply: tracked → `git rm -q -f` (deletion staged), untracked → unlink; then `rmdir` of empty on-demand folders.
Filesystem: `.gator/<folder>/` scaffolding (W: deletions only), git index (W: removals)
<- `gator update` execution (after `execute_updates()`, so the managed copies exist first), re-exported by `gatorize.py` like the vendor cleanup
! Gator shipped and overwrote these files on every update, so they are removed even when edited; a folder with any other file keeps its README.
! Pinned by `tests/test_scaffold_lazy.py`.

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

`gatorize` never creates, prompts about, backs up, or edits `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, or `*.local.md` (gator-native entry point, 2026-10-08). The retired `gatorize/entry_points.py` (`render_entry_content()`, `upgrade_legacy_entry_point()`, `action_install_entry_points()` with its foreign-file backup-append-overwrite prompt and `*_ROLLBACK.md`) is gone. Loop-join and Executive Summary guidance lives only in the protocol and the `GATOR_INIT.md` pointer (the `/loop-join` command is retired). The pre-action summary states that these files are left untouched. The Gator entry document is `GATOR_INIT.md`, installed by `action_install_gator()`. The `.gitignore` entries for `*.local.md` remain (`ensure_repo_gitignore`) and are behavior-neutral. Pins: `TestGatorizeLeavesNativeFilesUntouched` in `tests/test_gatorize.py`.

## TRIPWIRE: No AI-Tool Files in Repositories

Gator creates and retains no repo-level vendor configuration or command files. `action_install_gator()` writes nothing under `.claude/`, `.codex/` or `.gemini/`: the session hooks live in each AI tool's user-level settings ([`scripts-machine-integration.md`](scripts-machine-integration.md)), and the four Gator slash commands (`init`, `update`, `commit`, `loop-join`) are retired (Architect decision A, 2026-11-11). User-owned vendor files and user entries in them may remain; Gator leaves them alone. The retired `gatorize/vendor_hooks.py` (`install_vendor_hooks()`, repo-scoped merge) and `templates/gator-starter/{commands,vendor-hooks}/` are gone. Pins: `TestNoVendorFilesInRepos` in `tests/test_gatorize.py`.

### plan_vendor_cleanup(repo_root) / apply_vendor_cleanup(repo_root, actions) / format_vendor_cleanup(actions, predicted=False) / RETIRED_COMMANDS / ELIGIBLE_SETTINGS
File: src/gator_command/scripts/gatorize/vendor_cleanup.py
The one-time removal of what earlier Gator versions put into a repository. `plan_vendor_cleanup()` is read-only and returns sorted `{path, action, tracked}`. Settings files come from the closed list `.claude/settings.json`, `.codex/hooks.json`, `.gemini/settings.json`. A file whose only content is Gator's hook entries is `delete`. One that also holds user hooks or settings is `strip`. A file with no Gator entries, or invalid JSON, gets no action. Each command file in `RETIRED_COMMANDS` is `delete` when its line-ending-normalized SHA-256 matches a shipped version; any other content is a `user-owned` note, reported and never applied. `apply_vendor_cleanup()` applies exactly the given delete/strip actions: tracked delete → `git rm -q -f` (deletion staged; `-f` because the plan already found the working copy wholly Gator's); untracked delete → unlink; strip → atomic rewrite, left unstaged. It then removes `.claude/commands/`, `.claude/`, `.codex/`, `.gemini/` if they are empty on disk.
Filesystem: the eligible repo files (RW), Git index (W, deletions only)
<- `gator-update.py` `_run()` via the `gatorize` sibling (see [`scripts-repo-update.md`](scripts-repo-update.md))
-> `machine_integration.strip_managed_entries()`, `_read_json()`, `_atomic_write_json()`, `_Malformed`
! Gator entries are recognized only by the closed grammar `machine_integration.is_gator_hook_command()`. A neighbouring user `gator hook <other verb>` or `.gator/` command is user content, so its file is stripped, never deleted.
! `RETIRED_COMMANDS` holds 36 digests: every version of the four command templates in this repository's history (`git log --all --follow`) and in the pre-monorepo repositories' `*commands/<name>.md` history, computed 2026-11-11. It is a closed historical record; do not add to it.
! `user-owned` notes and stripped files are reported for the user; Gator never stages a file that still holds user content.

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
- Verify user content, native agent files (byte-for-byte), and user-owned vendor files survive; a fresh install creates no `.claude/`, `.codex/` or `.gemini/`.
- Check v2 layout plus user-visible scaffolding placement.
- Run installer, layout, hooks, registry, and install-cycle tests.

## Connections

-> [Repo Update](scripts-repo-update.md) - shared hook behavior and shipped root files
-> [Layout Resolver](scripts-layout.md) - initial directory placement
-> [Managed State](scripts-managed-state.md) - post-install classification and repair
-> [Machine Integration](scripts-machine-integration.md) - where the session hooks live now; the shared hook grammar and stripper
-> [Core Library](scripts-core-library.md) - registry and template resolution
