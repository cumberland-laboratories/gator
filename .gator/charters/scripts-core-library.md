# Charter: Core Library

**Covers**: `src/gator_command/scripts/gator_core.py`, `src/gator_command/scripts/gator-machine-id.py`, `src/gator_command/scripts/gator_remote.py`, `src/gator_command/scripts/gator-version.py`, `src/gator_command/scripts/gator_runtime.py`, `src/gator_command/templates/gator-starter/scripts/gator_core.py`, `src/gator_command/templates/gator-starter/scripts/gator-version.py`

## Owns

The shared infrastructure consumed by every other gator-command script:

- `gator_core.py` owns version resolution, repo discovery, dashboard registry I/O, path normalization, the git() helper, stdout setup, the `import_sibling()` loader, `GATOR_MARK_LINES` / `CURRENT_GENERATION` constants, product-source resolution (`resolve_template_source`, `read_product_source`), repo topology derivation (`get_repo_topology` — always returns "standalone", command-post topology retired), and policy artifact management (`clear_policy_artifacts`). Legacy functions (`find_command_post`, `resolve_thin_link`, `parse_registry`) kept for enterprise/caller compat but no longer called by Individual product code. Template copy synced.
- `gator-machine-id.py` owns the stable machine identity file at `~/.gator/machine-id`. Also usable as a standalone CLI (`--label`, `--json`).
- `gator_remote.py` owns bare-clone cache management for remote fleet scanning: cache key generation, fetch/create lifecycle, and all `git show` / `git ls-tree` / `git log` primitives against bare repos.
- `gator-version.py` is a thin CLI wrapper over `gator_core.get_version()`. No logic of its own.

## Does Not Own

- Vendor-transcript discovery, parsing, or session schema — Enterprise-side; see [`scripts-enterprise`](scripts-enterprise.md).
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
! **`VERSION` and `pyproject.toml` must carry the same version.** The resolver reads `pyproject.toml` first, so a stale `VERSION` is invisible in a source checkout but is served by the fallback path (deployed repos without full Git history). Update both in every version-bump commit; CI has no cross-file check for this. Current: 2.37.1.

### get_version_short(cwd=None)
File: `src/gator_command/scripts/gator_core.py`
Returns the version number only (e.g. "1.7.1"), stripping git describe suffixes.
Filesystem: same as `get_version()`
<- `gator-version.py --short`
-> `get_version()`

### write_runtime_pin(gator_dir, version=None, runtime_dir=None) / _read_machine_id_value()
File: `src/gator_command/scripts/gator_core.py` (mirrored in the template copy — repo-resident gator-update imports the repo-side gator_core)
Writes `.gator/runtime-pin.json` (schema `gator-runtime-pin-v1`, contract at `contracts/schemas/`): `runtime_version` (arg or `get_version()`), `pinned_at` (UTC Z), `pinned_by_machine` (best-effort `~/.gator/machine-id` `id:` field via `_read_machine_id_value`, None on any failure — never raises), and `manifest` = sha256 of every file under the shipped scripts dir, keyed by posix relpath (`__pycache__` excluded). Returns the pin dict, or None when no shipped scripts dir exists (no file written).
Filesystem: shipped scripts dir (R), `~/.gator/machine-id` (R), `.gator/runtime-pin.json` (W)
<- `gator-update.py::main()` (post-stamp, best-effort), `gatorize.py` v2 install path (post-`write_gator_version`, best-effort)
-> `get_version()`
! `runtime_dir`: callers (both gator-update copies and gatorize) pass the wheel's template scripts dir, so the manifest hashes the bytes actually in force, and wheel files never pass through Git's autocrlf, so the manifest is checkout-stable. Without `runtime_dir` it probes the repo (`.includes/scripts/` first, then `scripts/`), and on-disk bytes can differ by line endings.
! Callers wrap it in try/except: a pin failure must never fail an update or install. Its reader is `resolve_governed_runtime()`.
! The pin is COMMITTED (not gitignored) — it is the from-Git-history proof of which runtime governed each commit.

### resolve_governed_runtime(repo_root, cli_version=None) / _version_tuple(v)
File: `src/gator_command/scripts/gator_core.py` (mirrored in the template copy — the hook orchestrator is repo-resident and imports the repo-side gator_core, so this does not live in the wheel-only `gator_runtime.py`)
Pure decision function — no side effects, no exits; callers own messaging and exit codes. Resolution order: pin present → numeric-tuple version compare (`_version_tuple` honors numeric prefixes, ignores rc/dev suffixes, None on garbage) yielding `current` / `cli-newer` (run, and advise `gator update`) / `refuse` (fail-closed, `core.repositoryformatversion` semantics; the reason includes `pipx upgrade gator-command`); no pin + repo scripts → `repo-scripts`; neither → `ungoverned`. Returns `{"mode", "pin_version", "cli_version", "reason"}`.
Filesystem: `.gator/runtime-pin.json` (R), shipped scripts dirs (existence probe only)
<- `gator-hook.py` (the hook dispatcher, on every hook), template `gator-pre-commit.py::main()` (validate phase, only when `GATOR_RUNTIME_RESOLVER=1`)
-> `get_version()` (when cli_version not passed)
! Malformed or unreadable pin FAILS OPEN to `pin-unreadable` (repo-scripts fallback + repair hint) — a corrupt pin must never brick commits. Contrast with `is_enterprise_active`'s fail-CLOSED: refusing to activate a feature is safe; refusing to commit is not. Both unreadable branches (malformed JSON and an unparseable `runtime_version`) degrade the same way: repo scripts present → `pin-unreadable`; absent → `ungoverned` with an honest no-fallback reason. Pinned by `test_unparseable_version_without_scripts_is_ungoverned`.
! The pin is read with `encoding="utf-8-sig"` (BOM-tolerant; reads plain UTF-8 identically), because PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM and a plain-UTF-8 read would turn a should-refuse pin into a fail-open parse error. Pinned by `test_bom_pin_still_parses_and_refuses`.
! The comparison is VERSION-based, not manifest-based — CRLF/autocrlf makes cross-platform manifest comparison invalid; manifest verification would need Git-blob-hash semantics.

### policy_staleness_nudge(gator_dir, now=None, stale_days=None)
File: `src/gator_command/scripts/gator_core.py` (block-mirrored in the template copy)
Returns a one-line staleness nudge for the org-policy channel, or None. Purely LOCAL: `is_enterprise_active(gator_dir)` gate → mtime of `~/.gator/enterprise/org-policies.json` vs threshold (default 7 days; `GATOR_POLICY_STALE_DAYS` env; `stale_days` arg for tests). Never raises (blanket except → None).
<- `gator-init.py` banner (agent-facing surface — the agent reads it at session opening and runs the pull) and `gator-session-open.py` (STDERR only — that script's contract forbids stdout)
-> `is_enterprise_active()`
! NO NETWORK in any session-opening path: freshness failures are visible staleness, never a blown hook timeout or a silent success-looking failure.
! **The wiring is pinned, not just the helper.** The banner call sits behind a blanket except, so a broken call would be swallowed while the helper's own tests stay green. `test_banner_shows_policy_nudge_wiring` (a sentinel through the real `print_boot_sequence` on a minimal v2 repo) and `test_banner_survives_nudge_helper_raising` pin it; any call site guarded by a blanket except needs an end-to-end wiring test. The same test class pins the banner's session-opening directive tail (`test_banner_ends_with_session_opening_directive`, `test_session_opening_directive_resolves_v2_path` — see `scripts-repo-lifecycle.md` for the surface).

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
Canonical presence-detection for the `.gator/enterprise.json` marker. Returns True iff the marker exists AND parses as a JSON **object** AND has `enabled: true` (literal identity check, not truthy). Fail-closed on any other outcome: missing file, unreadable file, malformed JSON, non-object JSON root (e.g. `[]`, `42`, `"foo"`, `true`, `null`), `enabled` absent or non-bool or `false`. Accepts str or Path for the `gator_dir` argument. Reference impl in `contracts/compatibility/test_enterprise_marker.py::_is_enterprise_active` — the production impl MUST stay behaviorally identical; `tests/test_gator_core.py::TestIsEnterpriseActive` pins the semantics, including a parametrized non-object-root sweep. Filesystem: `.gator/enterprise.json` (R).
<- `gator-repo-status.py` (`enterprise_managed`), `gatorize.py`, `policy_staleness_nudge()`; `precommit_local_policy.py` mirrors the same semantics
! Fail-closed by design. Never accept `enabled: "true"` (string), `enabled: 1` (int), or missing `enabled` as activation. If the marker isn't parseable, the answer is "not active" — never "assume active as a courtesy."

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
! Subprocess call uses `encoding="utf-8", errors="replace"` — NOT bare `text=True`. Bare `text=True` decodes with the platform-default locale codec (`cp1252` on Windows), which crashes with `UnicodeDecodeError` on any Git output containing bytes unrepresentable in cp1252 — commit subjects with non-ASCII, author names with diacritics, or trailer content copied from external sources; in the Dashboard the History endpoint then returns "Empty reply from server". Same pattern in `dashboard/helpers.py::git_run` and `dashboard/helpers.py::run_text`. Do NOT use bare `text=True` on any subprocess whose child may emit non-ASCII output.

### override_event_fields(trailers)
File: `src/gator_command/scripts/gator_core.py`
Classify an Architect override from one commit's trailer map. Returns None, or `{override_type, approver, block_id, reason, rules}`. Detects the current `Gator-Override-Approved-By` / `-Block` / `-Reason` / `-Rules` trailers, the older `Gator-Charter-Changed: override-skip` + approver/block form, and a bare legacy `Gator-Override:`. `override_type` is the legacy value, else `charter-skip`, else `lint` (rules only), else `override`.
Filesystem: none
<- `gator-audit._collect_trailer_intelligence()`, `gator-repo-status.get_trailer_data()`
! Single source of override detection for readers; do not key on `Gator-Override:` alone, which the hook never emits. The package copy only — the starter and bundled `gator_core.py` copies are separate files and not byte-pinned.

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
! The Python installer imports `CURRENT_GENERATION` directly. Keep the assignment on one line with no whitespace variation — downstream tooling may parse this line literally.

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

### PREFERENCES_FILE / PREFERENCES_SCHEMA / read_preferences() / _validate_launcher_candidate(path, for_shebang=True)
File: `src/gator_command/scripts/gator_core.py` (mirrored in the template copy — the reader is machine-scoped state and template callers may consult it)
Machine-local unified preferences file at `~/.gator/preferences.json`, schema `gator-preferences-v1`. `read_preferences()` returns a **discriminated result** (`{"state": "absent"}` / `{"state": "malformed", "reason": ...}` / `{"state": "present", "data": {...}}`) so callers can distinguish "no preference set" (safe to fall back) from "user configured something and it's broken" (must be surfaced loudly, never silently ignored); never collapse the two into `Optional[dict]`. BOM-tolerant (`utf-8-sig`). Never raises. `_validate_launcher_candidate(path, for_shebang=True)` returns `(valid, reason)` — checks non-empty, absolute, basename `py.exe`, spaceless (when for_shebang), exists; existence is checked LAST so configuration reasons (basename-mismatch, relative-path, spaced-path) surface even when the file is missing.
Filesystem: `~/.gator/preferences.json` (R), candidate launcher path (R via `os.path.isfile`)
<- `resolve_python_launcher_for_hooks()`
! **Malformed-file case must NEVER fall through to auto-detect.** The resolver's caller (`_hook_shebang`) refuses loudly (`HookShebangUnresolvable`) on any malformed preference file, because falling back to auto-detect is exactly what the user overrode by writing the file. Deviates from `resolve_governed_runtime()`'s fail-OPEN-on-corrupt-pin behavior on purpose — a broken runtime pin must never brick commits, but a broken user preference must never silently defeat the user's own configuration.
! **Wrong-shape sections degrade, never crash.** `read_preferences()` runs `_validate_preferences_shape()` over every documented section and field (python and hooks must be objects, notes/updated_at strings, python.windows_py_launcher a string, python.allow_for_hook_shebang a bool), so a payload like `{"schema": "gator-preferences-v1", "python": []}` returns `malformed` instead of crashing the resolver's `.get()` chain. An empty `python.windows_py_launcher` is also malformed (the schema's `minLength: 1`), never "no launcher configured". Pinned by `test_empty_windows_py_launcher_returns_malformed`.
! `PREFERENCES_FILE` is captured at import time from `Path.home()`. Tests that need to relocate it must monkeypatch the module attribute, not the user's home directory.
! Reader tolerates unknown top-level sections (`hooks:` is reserved; future sections are additive within v1 by construction).
! Operator-facing recovery documentation lives in the shipped procedure `procedures/configure-machine-preferences.md` — when the resolver refuses, the refusal message names that procedure so an operator or agent can recover without the CLI.

### resolve_python_launcher_for_hooks()
File: `src/gator_command/scripts/gator_core.py` (mirrored in the template copy)
Canonical Windows Python-launcher resolver — the single seam every launcher-consuming site on the machine goes through. Windows only; non-Windows returns `not-applicable` so callers keep the Unix shebang path. Returns a structured dict: `{"status": "resolved" | "degraded" | "not-applicable", "source": "user" | "auto" | "none", "path": <str> | None, "shebang_safe": bool, "reason": <str>, "checked": [{tier, path, outcome}, ...]}`. Never raises. Resolution order: (1) `~/.gator/preferences.json` python.windows_py_launcher — valid → resolved user, invalid or malformed file → degraded user (NEVER fall through), absent or no-python-section → proceed; (2) auto-detect tiers `shutil.which("py")` → `%LOCALAPPDATA%\Programs\Python\Launcher\py.exe` → `C:\Windows\py.exe`, each space-checked; (3) nothing usable → degraded none with the full checked audit trail. The `checked` array is load-bearing for the refusal message (`_hook_shebang` renders it via `_format_shebang_refusal`).
Filesystem: `~/.gator/preferences.json` (R via `read_preferences`), candidate launcher paths (R via `_validate_launcher_candidate`)
<- `gator-update.py::_hook_shebang()` (both copies; the only consumer)
-> `read_preferences()`, `_validate_launcher_candidate()`, `shutil.which`, `os.path.expandvars`, `os.path.isfile`
! **`source == "user" && status == "degraded"` is the invariant**: a broken user-configured preference (malformed JSON or an invalid path) refuses loudly rather than silently falling back to auto-detect. Downstream refusal messages must preserve this distinction.
! Depends on `read_preferences()` keeping absent and malformed apart; if the reader ever changes shape, this resolver's tier-1 dispatch is the load-bearing consumer. It also checks `launcher is None` itself, so an empty string can never slip through as "not configured" even if the reader is bypassed (`test_empty_launcher_refuses_no_fallback_even_if_reader_bypassed`).
! **`python.allow_for_hook_shebang: false`** means "this launcher is valid for other uses but must NOT be baked into the Git hook shebang": the resolver treats an opted-out launcher as if no `python:` section existed and falls through to auto-detect. Default `true` when absent. Pinned by `tests/test_gator_core.py::test_allow_for_hook_shebang_false_falls_through_to_auto`.
! **Validator tests build absolute paths from `tmp_path`.** On Windows Python 3.13 a drive-less rooted path like `/tmp/x` is not absolute, and `C:/...` is not absolute on Linux CI, so tests exercising later validator rules (spaces, exists) compose fixture paths from `tmp_path` or patch `os.path.isabs` (`test_spaced_absolute_returns_spaced_path`, `test_missing_file_returns_file_not_found`). Hook-wrapper tests that need the shebang path but not the resolver internals patch `gator_core.resolve_python_launcher_for_hooks` directly rather than `os.name` (see `test_windows_platform_shebang`).

### gator_runtime.py (module)
File: `src/gator_command/scripts/gator_runtime.py`
Runtime context resolver for Gator. Detects runtime mode (source-checkout, public-clone, installed-package) and resolves scripts dir, templates dir, repo root, and command post root. This is the seam that makes pipx-installed Gator possible — scripts import this instead of doing SCRIPTS_DIR.parent.parent arithmetic.
<- `src/gator_command/cli.py`, and any script that needs context-aware path resolution
! This module must not import gator_core at module level — it may need to resolve paths before gator_core is importable. The gator_core import in get_command_post_root() is deferred.

---

## Before Changing This Module

- `gator_core.py` is imported by every other script. Changes to function signatures, return types, or constants cascade across the entire codebase.
- `CURRENT_GENERATION` is imported by the Python installer and downstream tooling. Keep it on a single `CURRENT_GENERATION = N` line — some readers may parse it literally.
- The bare-clone cache key format (`{name}-{hash8}.git`) has migration logic for legacy caches. If you change the format again, add another migration step.

### resolve_charter_surface(repo_root=None)
File: `src/gator_command/scripts/gator_core.py`
Returns the authoritative charter surface for this repo: mode ("source-command-post" or "governed-repo"), charter_dir, cross_cutting filename, and index_file path. This is the single source of truth for charter resolution — used by the pre-commit hook, enforcer-review, and any future charter-aware tool.
Filesystem: directory existence checks (R)
<- `gator-pre-commit.py`, `enforcer-review.py`
! Two modes only: source-command-post (.gator/charters/, scripts-cross-cutting.md) and governed-repo (.gator/charters/, cross-cutting.md). No other layouts exist. The cross-cutting charter is found by pattern ("cross-cutting" in filename), not hardcoded name.

## Connections

-> [README](README.md) — charter philosophy and notation
-> [scripts-fleet-intelligence](scripts-fleet-intelligence.md) — fleet and drift consumers of gator_core and gator_remote
-> [scripts-audit-intelligence](scripts-audit-intelligence.md) — audit and repo-status consumers
-> [scripts-session-archaeology](scripts-session-archaeology.md) — session reader + aggregator (the sole owner of machine identity reads)
-> [scripts-cross-cutting](scripts-cross-cutting.md) — resolve_charter_surface is itself a cross-cutting pattern
-> [scripts-repo-lifecycle](scripts-repo-lifecycle.md) — consumers of find_gator_root, resolve_thin_link
