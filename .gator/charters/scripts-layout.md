# Charter: Layout Resolver

**Covers**: `src/gator_command/scripts/gator_layout.py`

## Owns

The single source of truth for `.gator/` path resolution across all layout versions:

- `gator_layout.py` owns layout detection (v1/v2/mixed/invalid), the `GatorPaths` dataclass, content family classification (shipped/user/runtime/mixed), and template-derived shipped file enumeration.

## Does Not Own

- Migration logic (that is `gator-update.py --migrate-layout`, future)
- Template content or installation (that is `gatorize.py` and `gator-update.py`)
- Any script's business logic — this module only resolves paths

---

### resolve_gator_layout(repo_root)
File: `src/gator_command/scripts/gator_layout.py`
Detects layout version from `.gator/` directory state. Returns `"v1"`, `"v2"`, `"mixed"`, or `"invalid"`.
Filesystem: `.gator/` (R), `.gator/.includes/` (R), `.gator/layout-version.json` (R)
<- `get_gator_paths()`
! v1 = no .includes/. v2 = .includes/ + layout-version.json with `{"layout": "v2"}` + required content in .includes/. mixed = both old and new shipped locations (including shipped files at flat root with no .includes/ counterpart). invalid = structure unresolvable, OR v2 claimed but .includes/ is empty/incomplete.
! Mixed detection checks three categories: shipped root files, fully shipped directories, AND shipped files in mixed directories (procedures, charters, blueprints). Any shipped default file at flat root triggers mixed — it does not require the file to also exist in .includes/.
! **`reference-notes/` is a MIXED directory, not fully-shipped (2026-08-23).** `SHIPPED_DIRECTORIES` now holds only `scripts/`; `reference-notes` moved into `MIXED_DIRECTORY_SHIPPED_DEFAULTS` with a per-filename shipped set (bootstrap fallback — `get_shipped_files_for_directory` prefers the live template listing; keep the fallback in sync with `templates/gator-starter/reference-notes/`). WHY: the docs present root `.gator/reference-notes/` as USER content ("cognitive aids and vocabulary"), and the fully-shipped classification made any user-authored note at root resolve the repo as `mixed` — which `gator update` refuses, permanently bricking updates for repos that did the documented thing (field case: cl-strategy, 2026-08-23; a user note committed at root silently killed the Dashboard Update button). Pins: `TestReferenceNotesReclassification` (user-note-at-root = v2; shipped-name-at-root = still mixed; membership assertions).
! **Scaffolding-only exemption** (`_dir_is_scaffolding_only`): a fully-shipped directory at the flat root that contains ONLY `USER_VISIBLE_SCAFFOLDING` (`README.md`, `_template.md`) does NOT trigger mixed. `gator update`/`migrate_layout` intentionally keep scaffolding at the user-visible root, so a scaffolding-only shipped dir is a valid v2 state, not legacy content. A shipped dir with any non-scaffolding file (or subdirectory) at root is still mixed. **Regression guard**: without this, a v2 repo whose `reference-notes/` held only scaffolding was misread as `mixed`, and since the updater refuses mixed while `--migrate-layout` re-creates the same scaffolding, the repo could never be updated again (deadlock, fixed v2.2.1).
! v2 validation (`_has_required_includes_content`): `.includes/scripts/` OR a runtime pin (`.gator/runtime-pin.json` at the gator root) must exist, AND at least one shipped root file (constitution.md or gator-start-up.md). An empty .includes/ with a v2 version marker is invalid, not v2. **Runtime-split Phase 4 (2026-08-19, S1 — the plan's highest-risk seam)**: scripts-absence-with-pin is a VALID v2 state — pinned repos run the machine-side runtime and legitimately carry no repo-resident scripts. Without this relaxation, every post-Phase-4 repo resolved invalid, breaking update/init/state fleet-wide. Both copies (wheel + template) carry the same check; pins in `tests/test_layout.py`.

### get_gator_paths(repo_root)
File: `src/gator_command/scripts/gator_layout.py`
Returns a `GatorPaths` dataclass with all resolved paths for the detected layout. On v1, shipped content resolves to `.gator/` root. On v2, shipped content resolves to `.gator/.includes/`. On mixed, each shipped path is resolved individually: `_shipped_file()` and `_shipped_dir()` check `.includes/` first, fall back to root per-path.
Filesystem: `.gator/` (R), `.gator/.includes/` (R)
<- `gator-init.py`, `gator-pulse.py`, `gator-drift.py`, `gator-fleet-report.py`, `gator-fleet-intel.py`, `gator-repo-status.py`, `gator-charter-lint.py`, `gator-charter-verify.py`, `gator-charter-draft.py`, `gator-enforce.py`, `gator_core.resolve_charter_surface()`
-> `resolve_gator_layout()`
! This is the single source of truth for all `.gator/` path resolution. Mixed-layout fallback is per-path, not per-directory — a mixed repo with `.includes/scripts/` but root `constitution.md` resolves each correctly.

### get_shipped_files_for_directory(dir_name, template_source)
File: `src/gator_command/scripts/gator_layout.py`
Determines which files in a mixed directory are shipped. Prefers template-derived enumeration when available, falls back to `MIXED_DIRECTORY_SHIPPED_DEFAULTS`.
Filesystem: template directory (R, optional)
<- migration logic (future)

### resolve_template_source_for_layout(gator_dir)
File: `src/gator_command/scripts/gator_layout.py`
Reads `product-source.json` to find the template root for migration classification. Returns path or None.
Filesystem: `.gator/product-source.json` (R)
<- migration logic (future)

---

## TRIPWIRE: Layout Resolver Is the Single Path Authority

All scripts that read or write `.gator/` files must use `get_gator_paths()` instead of hardcoding paths like `gator_dir / "constitution.md"`. Direct path construction creates layout-version coupling that breaks on v2 repos.

Exception: `gator_layout.py` itself constructs paths — it is the only module authorized to do so.

## TRIPWIRE: Content Family Classification

The four categories (shipped, user, runtime, mixed) are exhaustive. Every file and directory under `.gator/` must belong to exactly one category. Adding a new `.gator/` file or directory requires classifying it in the constants at the top of `gator_layout.py`.

## TRIPWIRE: User-Visible Scaffolding

`_template.md` and `README.md` in mixed directories (charters, blueprints, procedures) are classified as `USER_VISIBLE_SCAFFOLDING` — they stay at the `.gator/` root on v2 repos, never move to `.includes/`. Agents look for these files when creating new content. Moving them to `.includes/` breaks agent workflows (templates become invisible).

Three code paths must respect this:
1. `gatorize.py` fresh install — puts scaffolding at root, shipped content in `.includes/`
2. `gator-update.py` overlay — routes scaffolding to root, shipped content to `.includes/`
3. `migrate_layout()` — preserves scaffolding at root during v1→v2 migration

`MIXED_DIRECTORY_SHIPPED_DEFAULTS` must NOT include `README.md` or `_template.md`. Those are in `USER_VISIBLE_SCAFFOLDING` instead.

## v1 Deprecation Warning

`get_gator_paths()` emits a one-time stderr warning when it detects a v1 layout, suggesting `gator update --migrate-layout`. The warning is process-scoped (module-level `_v1_warning_emitted` flag) — it fires once per script invocation, not once per call.

## Template Deployment

`gator_layout.py` is deployed to governed repos via `templates/gator-starter/scripts/gator_layout.py`. Fleet-repo scripts (pre-commit hook, enforcer-review, session-open) import it via the same `SCRIPTS_DIR` pattern they use for `gator_core`. Listed in `pyproject.toml` package-data for wheel distribution.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) — layout resolver is a cross-cutting pattern used by 11+ scripts
-> [Core Library](scripts-core-library.md) — `find_gator_root()` used to locate the repo root before calling the resolver
-> [Installer](scripts-installer.md) — `gatorize.py` creates the directory structure that the resolver detects; entry_points.py references are layout-defensive
