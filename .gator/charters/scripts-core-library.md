# Charter: Core Library

**Covers**: `src/gator_command/scripts/gator_core.py`, `src/gator_command/scripts/gator-machine-id.py`, `src/gator_command/scripts/gator_remote.py`, `src/gator_command/scripts/gator-version.py`, `src/gator_command/scripts/gator_runtime.py`

## Owns

The shared infrastructure consumed by every other gator-command script:

- `gator_core.py` owns version resolution, repo discovery, dashboard registry I/O, path normalization, the git() helper, stdout setup, the `import_sibling()` loader, `GATOR_MARK_LINES` / `CURRENT_GENERATION` constants, product-source resolution (`resolve_template_source`, `read_product_source`), repo topology derivation (`get_repo_topology` — always returns "standalone", command-post topology retired), and policy artifact management (`clear_policy_artifacts`). Legacy functions (`find_command_post`, `resolve_thin_link`, `parse_registry`) kept for enterprise/caller compat but no longer called by Individual product code. Template copy synced.
- `gator-machine-id.py` owns the stable machine identity file at `~/.gator/machine-id`. Also usable as a standalone CLI (`--label`, `--json`).
- `gator_remote.py` owns bare-clone cache management for remote fleet scanning: cache key generation, fetch/create lifecycle, and all `git show` / `git ls-tree` / `git log` primitives against bare repos.
- `gator-version.py` is a thin CLI wrapper over `gator_core.get_version()`. No logic of its own.

## Does Not Own

- Vendor-transcript discovery, parsing, or session schema — Enterprise-side since the audit-surface tranche (the `extract-*.py` scripts and `gator-session-common.py` retired 2026-08-13/2026-08-16; see [`scripts-enterprise`](scripts-enterprise.md)).
- CLI argument parsing for any script other than `gator-machine-id.py` and `gator-version.py`.
- Fleet-level report assembly — that belongs in `gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`.

---

### get_version(cwd=None)
File: `src/gator_command/scripts/gator_core.py`
Canonical version resolver for gator-command. Returns version without "v" prefix (e.g. "1.7.1").
Resolution order: pyproject.toml > importlib.metadata > git describe > VERSION file > git rev-parse > "dev".
Filesystem: `pyproject.toml` (R), `.git/` (R), `VERSION` file (R)
<- `gator-version.py`, `gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`, `gator-fleet-intel.py`, `gatorize.py`, `gator-deploy.py`, `gator-update.py`, `dashboard/data.py`, `dashboard/updates.py`, `__init__.py`
-> `_read_pyproject_version()`, `_read_version_file()`, `_find_repo_root()`
! This is the single source of truth for version resolution. All callers must use this function — do not add inline pyproject.toml reading or importlib.metadata calls elsewhere.
! **VERSION file and pyproject.toml must stay byte-consistent on the version field.** Historical drift (root `VERSION` at `1.8.1` while pyproject was at `2.4.5`) was harmless in the normal source-checkout path because the resolver reads pyproject first, but the fallback path (deployed repos without full git history) would silently serve stale numbers. Pre-cutover fix (2026-08-02) synced both to 2.5.0, then 2.5.1 for the actual first monorepo release, then 2.5.2 (silent-partial-commit) and 2.5.3 (recovery release with the actual code), then 2.5.4 (session-hook + migration hardening — closes the fleet-wide silent-no-op class introduced by the `.includes/` split). The drift RECURRED across 2.6.0 → 2.7.0 (three releases bumped pyproject only; VERSION sat at 2.5.4) — caught and re-synced at the 2.8.0 bump (2026-08-16), maintained at the 2.9.0/2.9.1/2.9.2 bumps (2026-08-23, current: **2.9.2** in both files). Both files should be updated together in every version bump commit — CI has no cross-file consistency check for this.

### get_version_short(cwd=None)
File: `src/gator_command/scripts/gator_core.py`
Returns the version number only (e.g. "1.7.1"), stripping git describe suffixes.
Filesystem: same as `get_version()`
<- `gator-version.py --short`
-> `get_version()`

### write_runtime_pin(gator_dir, version=None, runtime_dir=None) / _read_machine_id_value()
File: `src/gator_command/scripts/gator_core.py` (mirrored in the template copy — repo-resident gator-update imports the repo-side gator_core)
Runtime-split Phase 1 (roadmap item 19, Variant A ratified 2026-08-18). Writes `.gator/runtime-pin.json` (schema `gator-runtime-pin-v1`, contract at `contracts/schemas/`): `runtime_version` (arg or `get_version()`), `pinned_at` (UTC Z), `pinned_by_machine` (best-effort `~/.gator/machine-id` `id:` field via `_read_machine_id_value`, None on any failure — never raises), and `manifest` = sha256 of every file under the shipped scripts dir (`.includes/scripts/` v2-first, `scripts/` v1 fallback; `__pycache__` excluded), keyed by posix relpath. Returns the pin dict, or None when no shipped scripts dir exists (no file written).
Filesystem: shipped scripts dir (R), `~/.gator/machine-id` (R), `.gator/runtime-pin.json` (W)
<- `gator-update.py::main()` (post-stamp, best-effort), `gatorize.py` v2 install path (post-`write_gator_version`, best-effort)
-> `get_version()`
! Phase 4a (2026-08-19): new `runtime_dir` param — callers (both gator-update copies + gatorize) pass the WHEEL's template scripts dir, so the manifest hashes the bytes actually in force under Variant A. Wheel-sourced manifests are also checkout-stable (wheel files never pass through git's autocrlf), largely retiring the risk-7 caveat for pinned repos; the repo-probe fallback (v2 → v1) remains for standalone pre-Phase-4 runs, where the on-disk-bytes caveat still applies.
! Emission is additive and reader-free until the Phase 2 resolver lands. Callers wrap in try/except — a pin failure must never fail an update or install.
! Pin is COMMITTED (not gitignored) — it is the from-git-history proof of which runtime governed each commit.

### resolve_governed_runtime(repo_root, cli_version=None) / _version_tuple(v)
File: `src/gator_command/scripts/gator_core.py` (mirrored in the template copy — the hook orchestrator is repo-resident and imports the repo-side gator_core; this is a DOCUMENTED DEVIATION from the plan's "natural home is gator_runtime.py": gator_runtime is wheel-only and unavailable to repo scripts)
Runtime-split Phase 2 (Variant A). Pure decision function — no side effects, no exits; callers own messaging/exit codes. Resolution order (plan §4.4): pin present → numeric-tuple version compare (`_version_tuple` honors numeric prefixes, ignores rc/dev suffixes, None on garbage) yielding `current` / `cli-newer` (run + advise `gator update`) / `refuse` (fail-closed, `core.repositoryformatversion` semantics, reason includes `pipx upgrade gator-command`); no pin + repo scripts → `repo-scripts` (pre-split behavior); neither → `ungoverned`. Returns `{"mode", "pin_version", "cli_version", "reason"}`.
Filesystem: `.gator/runtime-pin.json` (R), shipped scripts dirs (existence probe only)
<- template `gator-pre-commit.py::main()` (validate phase, behind `GATOR_RUNTIME_RESOLVER=1` feature flag until Phase 3)
-> `get_version()` (when cli_version not passed)
! Malformed/unreadable pin FAILS OPEN to `pin-unreadable` (repo-scripts fallback + repair hint) — a corrupt pin must never brick commits. Contrast with `is_enterprise_active`'s fail-CLOSED: refusing to activate a feature is safe; refusing to commit is not. BOTH unreadable branches (malformed JSON and unparseable `runtime_version`) follow the same degradation contract: repo scripts present → `pin-unreadable`; absent → `ungoverned` with an honest no-fallback reason (whiteboard 2026-08-19 Finding 1 fix — the version-parse branch originally promised a repo-scripts fallback it couldn't deliver; pin: `test_unparseable_version_without_scripts_is_ungoverned`).
! Pin is read with `encoding="utf-8-sig"` (BOM-tolerant; reads plain UTF-8 identically). Live-caught 2026-08-18: PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM, which under plain utf-8 turned a should-refuse pin into JSONDecodeError → fail-open fallback — a Windows editor could silently disable the version gate. Pin: `test_bom_pin_still_parses_and_refuses`.
! The comparison is VERSION-based, not manifest-based — CRLF/autocrlf makes cross-platform manifest comparison invalid (plan §8 risk 7); manifest verification is future integrity work with git-blob-hash semantics.

### policy_staleness_nudge(gator_dir, now=None, stale_days=None)
File: `src/gator_command/scripts/gator_core.py` (block-mirrored in the template copy)
Runtime-split D6 decision (c), Architect-ratified 2026-08-22. Returns a one-line staleness nudge for the org-policy channel, or None. Purely LOCAL: `is_enterprise_active(gator_dir)` gate → mtime of `~/.gator/enterprise/org-policies.json` vs threshold (default 7 days; `GATOR_POLICY_STALE_DAYS` env; `stale_days` arg for tests). Never raises (blanket except → None).
<- `gator-init.py` banner (agent-facing surface — the agent reads it at session opening and runs the pull) and `gator-session-open.py` (STDERR only — that script's contract forbids stdout)
-> `is_enterprise_active()`
! NO NETWORK in any session-opening path — this is the whole point of D6 (c): freshness failures are visible staleness, never a blown hook timeout or a silent success-looking failure.
! **Wiring pinned, not just the helper** (whiteboard 2026-08-22 r3): the original gator-init banner call referenced an undefined `gator_dir` and its blanket except swallowed the NameError — the agent-facing surface was dead code while the helper's own tests stayed green. Fix: `paths.gator_root`. Pins: `test_banner_shows_policy_nudge_wiring` (sentinel through the real `print_boot_sequence` on a minimal v2 repo) + `test_banner_survives_nudge_helper_raising`. Lesson: any call site guarded by a blanket except needs an end-to-end wiring test. The same test class also pins the banner's session-opening directive tail (`test_banner_ends_with_session_opening_directive`, `test_session_opening_directive_resolves_v2_path` — see `scripts-repo-lifecycle.md` for the surface).

### normalize_path(raw_path)
File: `src/gator_command/scripts/gator_core.py`
Converts MSYS2/Git Bash paths (/c/Users/...) to native Windows (C:/Users/...).
Filesystem: none (pure string transform)
<- `gator-fleet-report.py`, `gator-drift.py`, `gator-fleet-intel.py`, `gator-update.py`
! No-op on non-MSYS2 paths. Always apply before using a registry path as a `Path()` argument on Windows.

### find_command_post(start_path=None) — LEGACY
File: `src/gator_command/scripts/gator_core.py`
Walks up from start_path looking for a directory containing `.gator/mission.md`. **Legacy** — command-post architecture retired. Kept for enterprise script compat (`gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`). No longer called by Individual product code.
Filesystem: repo directories (R)

### find_gator_root(start_path=None)
File: `src/gator_command/scripts/gator_core.py`
Walks up from start_path looking for `.gator/` directory.
Filesystem: repo directories (R)
<- `gator-init.py`, `gator-update.py`
! Use this for scripts that operate from inside a governed fleet repo. Not for command-post scripts.

### is_enterprise_active(gator_dir)
File: `src/gator_command/scripts/gator_core.py`
Canonical presence-detection for the `.gator/enterprise.json` marker. Returns True iff the marker exists AND parses as a JSON **object** AND has `enabled: true` (literal identity check, not truthy). Fail-closed on any other outcome: missing file, unreadable file, malformed JSON, non-object JSON root (e.g. `[]`, `42`, `"foo"`, `true`, `null`), `enabled` absent or non-bool or `false`, wrong-typed `enabled`. Accepts str or Path for the `gator_dir` argument. Reference impl in `contracts/compatibility/test_enterprise_marker.py::_is_enterprise_active` — production impl MUST stay byte-behaviorally identical; `tests/test_gator_core.py::TestIsEnterpriseActive` pins the semantics (12 cases including the 6-way parametrized non-object-root sweep added after Codex Phase 4b review caught a real crash-not-fail-closed bug in both impls). Filesystem: `.gator/enterprise.json` (R).
<- Phase 4c/4d Enterprise-side code paths (marker check before any Enterprise behavior fires)
! Fail-closed by design (Codex Phase 4a Decision-B amendment). Never accept `enabled: "true"` (string), `enabled: 1` (int), or missing `enabled` as activation. If the marker isn't parseable, the answer is "not active" — never "assume active as a courtesy."

### resolve_thin_link(gator_dir) — LEGACY
File: `src/gator_command/scripts/gator_core.py`
Reads `.gator/command-post.md` and resolves the command-post path. **Legacy** — command-post architecture retired. Still called by `gator-update.py` for policy sync (enterprise path only).
Filesystem: `.gator/command-post.md` (R)
<- `gator-update.py`

### read_product_source(gator_dir)
File: `src/gator_command/scripts/gator_core.py`
Reads `.gator/product-source.json` and returns its contents as a dict, or None if missing or corrupt.
Filesystem: `.gator/product-source.json` (R)
<- `resolve_template_source()`, `gator-update.py`

### resolve_template_source(gator_dir, source_override=None)
File: `src/gator_command/scripts/gator_core.py`
Resolves the template source directory for product updates: explicit `--source` override, then `product-source.json`, then thin-link fallback to command post templates.
Filesystem: `.gator/product-source.json` (R), `.gator/command-post.md` (R via `resolve_thin_link`)
<- `gator-update.py`
-> `read_product_source()`, `resolve_thin_link()`

### get_repo_topology(gator_dir)
File: `src/gator_command/scripts/gator_core.py`
Always returns `"standalone"`. Command-post topology ("policy-synced", "inconsistent") is retired. Function kept for call-site compatibility.
Filesystem: none
<- `gator-update.py`, `gator-repo-status.py`, `gator-dashboard.py`
-> `resolve_thin_link()`

### clear_policy_artifacts(gator_dir)
File: `src/gator_command/scripts/gator_core.py`
Removes all policy-source artifacts (command-post.md, governance-source.json, policy-link.json, policy-cache/) to make a repo standalone.
Filesystem: `.gator/command-post.md`, `.gator/governance-source.json`, `.gator/policy-link.json`, `.gator/policy-cache/` (W, deletes)
<- `gator-dashboard.py`

### parse_registry(command_post) — LEGACY
File: `src/gator_command/scripts/gator_core.py`
Parses `gator-command/registry.md` table into a list of repo dicts. **Legacy** — command-post registry retired. Kept for enterprise fleet scripts only.
Filesystem: `gator-command/registry.md` (R)
<- enterprise only: `gator-fleet-report.py`, `gator-drift.py`, `gator-fleet-intel.py`, `gator-audit.py`

### git(*args, cwd=None)
File: `src/gator_command/scripts/gator_core.py`
Runs a git command, returns `(stdout, success)`. Never raises.
Filesystem: git repo (R or W depending on command)
<- `gator-fleet-report.py`, `gator-drift.py`, `gator-fleet-intel.py`, `dashboard/data.py::get_repo_history()`, and many others (this is the general-purpose git wrapper)
! Silent emptiness is not a success signal. Always check the `success` bool. An empty `stdout` with `success=True` means git returned nothing; `success=False` means git failed or timed out.
! Subprocess call uses `encoding="utf-8", errors="replace"` — NOT bare `text=True`. Bare `text=True` decodes with the platform-default locale codec (`cp1252` on Windows), which crashes with `UnicodeDecodeError` on any git output containing bytes unrepresentable in cp1252 — commit subjects with non-ASCII, author names with diacritics, or trailer content copied from external sources. Symptom in the Dashboard: History endpoint returns "Empty reply from server" mid-response because the handler crashes and closes the socket. Fixed in v2.4.4. Same pattern already lives in `dashboard/helpers.py::git_run` and `dashboard/helpers.py::run_text`. Do NOT reintroduce bare `text=True` on any subprocess whose child may emit non-ASCII output.

### import_sibling(name)
File: `src/gator_command/scripts/gator_core.py`
Loads a sibling script by filename (handles hyphens in module names).
Filesystem: `scripts/{name}.py` (R)
<- `gator-audit.py` (to load fleet-report, drift, gator_session_reader, gator-session-aggregator at runtime)
! Returns None if the file doesn't exist. Raises ImportError with diagnostic context if the file exists but fails to load. gator-audit.py catches ImportError per subsystem so one broken dependency doesn't kill the whole audit.

### ensure_utf8_stdout()
File: `src/gator_command/scripts/gator_core.py`
Rewrites sys.stdout with UTF-8 encoding when needed (Windows default is not UTF-8).
Filesystem: none
<- entry point of every CLI script
! Must be called before any print() in entry-point scripts. Not needed in library modules.

### CURRENT_GENERATION / GATOR_MARK_LINES
File: `src/gator_command/scripts/gator_core.py`
`CURRENT_GENERATION = 2` is the single source of truth for the template generation number. `GATOR_MARK_LINES` is the single source of truth for the ASCII gator logo.
<- `gator-drift.py` (reads CURRENT_GENERATION for drift comparison), `gator-init.py` (reads GATOR_MARK_LINES for display)
! The Python installer imports `CURRENT_GENERATION` directly. Keep the assignment on one line with no whitespace variation — downstream tooling (linters, future readers) may parse this line literally. Historical: bash `gatorize.sh` read it via `sed`/grep — that installer chain was retired in v2.4.0 (retire-gator-install Stage 4).

---

### ensure_cache(repo_name, remote_url)
File: `src/gator_command/scripts/gator_remote.py`
Creates or updates a bare clone in `~/.gator/fleet-cache/`. Cache key is `{repo_name}-{url_hash[:8]}.git` to prevent collisions when two remotes share the same registry name.
Filesystem: `~/.gator/fleet-cache/` (RW)
<- `gator-fleet-report.py` (via `scan_repo_remote()`), `gator-drift.py` (via `check_repo_drift_remote()`)
! Migration logic renames legacy `{repo_name}.git` bare clones (no hash) to the new keyed format on first encounter. The URL hash prevents silent sharing between two different remotes with the same name.

### read_gator_state_remote(cache_path, ref=None)
File: `src/gator_command/scripts/gator_remote.py`
Reads `.gator/` governance state from a bare cache using `git show` and `git ls-tree`. Parallel to `read_gator_state()` in `gator-fleet-report.py`.
Filesystem: `~/.gator/fleet-cache/` (R via git commands)
<- `scan_repo_remote()`, `check_repo_drift_remote()` in `gator-drift.py`
! Cannot determine hook installation status remotely — `hooks_installed` is always False for remote scans. `hooks_sources` reflects whether hook source files exist in `.gator/scripts/hooks/` on the remote.

### _resolve_ref(cache_path)
File: `src/gator_command/scripts/gator_remote.py`
Finds the best readable ref in a bare clone: tries `origin/main`, `origin/master`, `origin/dev`, then bare-native `main`, `master`, `dev`, then `HEAD`.
Filesystem: bare clone (R)
<- all remote read functions
! Bare clones from `git clone --bare` store refs as `refs/heads/main`; after `git fetch origin` they also have `refs/remotes/origin/main`. Both are tried. The distinction matters for repos that haven't been fetched recently.

---

### read_dashboard_registry() / write_dashboard_registry() / ensure_dashboard_registry_entry() / add_dashboard_repo() / remove_dashboard_repo()
File: `src/gator_command/scripts/gator_core.py`
Machine-local dashboard repo registry at `~/.gator/dashboard-repos.json`. `ensure_dashboard_registry_entry(repo_path, source)` is the shared helper — returns `{status, detail}` with status `added`, `already_registered`, `unavailable`, or `error`. `add_dashboard_repo()` delegates to it (returns bool). `remove_dashboard_repo()` matches by name or path. Schema: `gator-dashboard-registry-v1`.
<- `gator-init.py` (auto-register on session start), `gatorize.py` (auto-register), `gator-dashboard.py` (--add-repo/--remove-repo, _load_registry_repos fallback)

### gator_runtime.py (module)
File: `src/gator_command/scripts/gator_runtime.py`
Runtime context resolver for Gator. Detects runtime mode (source-checkout, public-clone, installed-package) and resolves scripts dir, templates dir, repo root, and command post root. This is the seam that makes pipx-installed Gator possible — scripts import this instead of doing SCRIPTS_DIR.parent.parent arithmetic.
<- `src/gator_command/cli.py`, and any script that needs context-aware path resolution
! This module must not import gator_core at module level — it may need to resolve paths before gator_core is importable. The gator_core import in get_command_post_root() is deferred.

---

## Before Changing This Module

- `gator_core.py` is imported by every other script. Changes to function signatures, return types, or constants cascade across the entire codebase.
- `CURRENT_GENERATION` is imported by the Python installer and downstream tooling. Keep it on a single `CURRENT_GENERATION = N` line — some readers may still parse it literally. Bash installer chain retired in v2.4.0.
- The bare-clone cache key format (`{name}-{hash8}.git`) has migration logic for legacy caches. If you change the format again, add another migration step.

### resolve_charter_surface(repo_root=None)
File: `src/gator_command/scripts/gator_core.py`
Returns the authoritative charter surface for this repo: mode ("source-command-post" or "governed-repo"), charter_dir, cross_cutting filename, and index_file path. This is the single source of truth for charter resolution — used by the pre-commit hook, enforcer-review, and any future charter-aware tool.
Filesystem: directory existence checks (R)
<- `gator-pre-commit.py`, `enforcer-review.py`
! Two modes only: source-command-post (.gator/charters/, scripts-cross-cutting.md) and governed-repo (.gator/charters/, cross-cutting.md). No other layouts exist. The cross-cutting charter is found by pattern ("cross-cutting" in filename), not hardcoded name.

## Connections

-> [README](README.md) — charter philosophy and notation
-> [scripts-fleet-intelligence](scripts-fleet-intelligence.md) — primary consumers of gator_core and gator_remote
-> [scripts-session-archaeology](scripts-session-archaeology.md) — session reader + aggregator (machine identity's sole owner since the 2026-08-16 sweep)
-> [scripts-cross-cutting](scripts-cross-cutting.md) — resolve_charter_surface is itself a cross-cutting pattern
-> [scripts-repo-lifecycle](scripts-repo-lifecycle.md) — consumers of find_gator_root, resolve_thin_link
