# Charter: Core Library

**Covers**: `src/gator_command/scripts/gator_core.py`, `src/gator_command/scripts/gator-session-common.py`, `src/gator_command/scripts/gator-machine-id.py`, `src/gator_command/scripts/gator_remote.py`, `src/gator_command/scripts/gator-version.py`, `src/gator_command/scripts/gator_runtime.py`

## Owns

The shared infrastructure consumed by every other gator-command script:

- `gator_core.py` owns version resolution, repo discovery, dashboard registry I/O, path normalization, the git() helper, stdout setup, the `import_sibling()` loader, `GATOR_MARK_LINES` / `CURRENT_GENERATION` constants, product-source resolution (`resolve_template_source`, `read_product_source`), repo topology derivation (`get_repo_topology` — always returns "standalone", command-post topology retired), and policy artifact management (`clear_policy_artifacts`). Legacy functions (`find_command_post`, `resolve_thin_link`, `parse_registry`) kept for enterprise/caller compat but no longer called by Individual product code. Template copy synced.
- `gator-session-common.py` owns the normalized session schema: machine identity, redaction engine, intelligence extraction, row_key generation, transcript path construction, and the canonical summary formatters that all vendor extractors must call.
- `gator-machine-id.py` owns the stable machine identity file at `~/.gator/machine-id`. Also usable as a standalone CLI (`--label`, `--json`).
- `gator_remote.py` owns bare-clone cache management for remote fleet scanning: cache key generation, fetch/create lifecycle, and all `git show` / `git ls-tree` / `git log` primitives against bare repos.
- `gator-version.py` is a thin CLI wrapper over `gator_core.get_version()`. No logic of its own.

## Does Not Own

- Vendor-specific session extraction (each `extract-*.py` script owns its own format).
- CLI argument parsing for any script other than `gator-machine-id.py` and `gator-version.py`.
- Fleet-level report assembly — that belongs in `gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`.
- Summary formatting for the legacy memex CLI — that is `PrettyFormatter` in `legacy/memex_formatters.py`.

---

### get_version(cwd=None)
File: `src/gator_command/scripts/gator_core.py`
Canonical version resolver for gator-command. Returns version without "v" prefix (e.g. "1.7.1").
Resolution order: pyproject.toml > importlib.metadata > git describe > VERSION file > git rev-parse > "dev".
Filesystem: `pyproject.toml` (R), `.git/` (R), `VERSION` file (R)
<- `gator-version.py`, `gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`, `gator-fleet-intel.py`, `gatorize.py`, `gator-deploy.py`, `gator-update.py`, `dashboard/data.py`, `dashboard/updates.py`, `__init__.py`
-> `_read_pyproject_version()`, `_read_version_file()`, `_find_repo_root()`
! This is the single source of truth for version resolution. All callers must use this function — do not add inline pyproject.toml reading or importlib.metadata calls elsewhere.
! **VERSION file and pyproject.toml must stay byte-consistent on the version field.** Historical drift (root `VERSION` at `1.8.1` while pyproject was at `2.4.5`) was harmless in the normal source-checkout path because the resolver reads pyproject first, but the fallback path (deployed repos without full git history) would silently serve stale numbers. Pre-cutover fix (2026-08-02) synced both to 2.5.0, then 2.5.1 for the actual first monorepo release, then 2.5.2 (silent-partial-commit) and 2.5.3 (recovery release with the actual code), then 2.5.4 (session-hook + migration hardening — closes the fleet-wide silent-no-op class introduced by the `.includes/` split). Both files should be updated together in every version bump commit — CI has no cross-file consistency check for this.

### get_version_short(cwd=None)
File: `src/gator_command/scripts/gator_core.py`
Returns the version number only (e.g. "1.7.1"), stripping git describe suffixes.
Filesystem: same as `get_version()`
<- `gator-version.py --short`
-> `get_version()`

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
<- `gator-audit.py` (to load fleet-report, drift, sessions, session-common at runtime)
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

### get_machine_identity()
File: `src/gator_command/scripts/gator-session-common.py` (legacy) + `src/gator_command/scripts/gator_session_reader.py` (Phase 3F canonical for surviving callers)
Returns `{id, hostname, label}` for the current machine. Creates `~/.gator/machine-id` on first call. Byte-identical copies exist in both files during the Phase 3→4 window.
Filesystem: `~/.gator/machine-id` (R, W on creation)
<- **reader copy**: `gator-audit.py` (via `reader_mod.get_machine_identity()`). **session-common copy**: internal callers `format_summary_markdown()` L282 + `format_session_summary_dict()` L344 (which are called by the Phase-4-deferred `extract-codex-sessions.py` + `extract-gemini-sessions.py`).
-> `gator-machine-id.py`'s storage format
! Duplicated across two files during Phase 3→4 per plan §5 decision 2(b). Rationale: retargeting session-common's internal callers to the reader would require an `import_sibling` from the retiring file, which is architecturally backward. Cleaner to keep both copies until Phase 4 sweeps session-common with the Codex/Gemini extractors. Both copies must stay in sync; either edit both together or fold the extractors' formatter dependency onto the reader in Phase 4.

### redact(text, summary_mode=False)
File: `src/gator_command/scripts/gator-session-common.py`
Applies credential and path redaction. `REDACT_ALWAYS` patterns run on all content; `REDACT_SUMMARY` path-anonymization patterns run only in summary mode.
Filesystem: none (pure string transform)
<- `extract_intelligence()`, `format_summary_markdown()`
! Always-redact patterns cover API keys, AWS keys, passwords, private key blocks, Bearer tokens, and DB connection strings with embedded passwords. Do not add summary-only patterns to REDACT_ALWAYS — transcripts keep original paths intentionally.

### extract_intelligence(turns)
File: `src/gator_command/scripts/gator-session-common.py`
Extracts goal, decisions, files_changed, and charters_updated from normalized turns using keyword heuristics.
Filesystem: none
<- `format_summary_markdown()`, `format_session_summary_dict()`
! Decision extraction uses DECISION_SIGNALS keyword matching — a heuristic, not semantic analysis. High false-positive rate for short confirmations ("yes", "proceed"). gator-audit.py adds a second filter layer (`_is_real_decision()`) to reduce noise.

### make_row_key(metadata)
File: `src/gator_command/scripts/gator-session-common.py`
Returns `sha256(session_id + "|" + source_path)[:16]` — the canonical unique key for a session.
Filesystem: none
<- `make_transcript_path()`, `format_session_summary_dict()`, Phase-4-deferred vendor extractors
! The historical duplication in `gator-session-sink.py` retired 2026-08-13 in Phase 3 Commit E (sink deleted with the vendor pipeline). The separator is `|` and the full source_path is used (not just the filename) to handle Gemini's genuine duplicate session IDs across different files. Sole owner post-Phase-3.

### format_summary_markdown(turns, metadata) / format_session_summary_dict(turns, metadata)
File: `src/gator_command/scripts/gator-session-common.py`
Canonical summary formatters. Vendor extractors delegate to these rather than implementing their own.
Filesystem: none
<- `extract-codex-sessions.py`, `extract-gemini-sessions.py` (Phase-4-deferred; `extract-claude-sessions.py` retired 2026-08-13 in Phase 3 Commit E — Enterprise-cli's `transcripts_discovery.py` replaces it for Claude)
-> `get_machine_identity()`, `extract_intelligence()`, `make_transcript_path()`
! These are the ONLY implementations of summary formatting for the surviving Codex/Gemini extractors. Vendor scripts that hand-roll their own frontmatter would diverge from the schema. The schema version is `gator-session-summary-v1`. This file retires in Phase 4 with the Codex+Gemini extractors.

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

### PrettyFormatter / JsonFormatter / get_formatter(fmt) [legacy]
File: `src/gator_command/scripts/legacy/memex_formatters.py`
Terminal (ANSI) and JSON output formatters for the legacy memex CLI. No new development.
Filesystem: none
<- `legacy/memex.py`

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
- The `make_row_key()` formula in `gator-session-common.py` is duplicated in `gator-session-sink.py`. Any change to the hash formula (separator, length, algorithm) must be applied to both files simultaneously or session deduplication will break.
- `CURRENT_GENERATION` is imported by the Python installer and downstream tooling. Keep it on a single `CURRENT_GENERATION = N` line — some readers may still parse it literally. Bash installer chain retired in v2.4.0.
- `format_summary_markdown()` and `format_session_summary_dict()` define the `gator-session-summary-v1` schema. Adding fields is backward-compatible; removing or renaming fields is not. The `architect:` frontmatter field (formerly `pi:`) is read with fallback: `metadata.get("architect", metadata.get("pi", "unknown"))`.
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
-> [scripts-session-archaeology](scripts-session-archaeology.md) — primary consumers of gator-session-common
-> [scripts-cross-cutting](scripts-cross-cutting.md) — resolve_charter_surface is itself a cross-cutting pattern
-> [scripts-repo-lifecycle](scripts-repo-lifecycle.md) — consumers of find_gator_root, resolve_thin_link
-> [scripts-cross-cutting](scripts-cross-cutting.md) — cross-script patterns including the row_key contract
