# Charter: Dashboard

**Covers**: `src/gator_command/scripts/gator-dashboard.py`, `src/gator_command/scripts/dashboard/helpers.py`, `src/gator_command/scripts/dashboard/updates.py`, `src/gator_command/scripts/dashboard/snapshot.py`, `src/gator_command/scripts/dashboard/data.py`, `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.css`, `src/gator_command/scripts/dashboard/dashboard.js`, `src/gator_command/scripts/dashboard/views/fleet.js`, `src/gator_command/scripts/dashboard/views/history.js`, `src/gator_command/scripts/dashboard/views/audit.js`, `src/gator_command/scripts/dashboard/views/repo.js`, `src/gator_command/scripts/dashboard/views/updates.js`, `src/gator_command/scripts/dashboard/views/settings.js`, `src/gator_command/scripts/dashboard/views/blueprint.js`, `src/gator_command/scripts/dashboard/blueprint/l1-data.json`, `src/gator_command/scripts/dashboard/blueprint/l1-positions.json`

## Owns

The Gator governance dashboard — a local HTTP server plus browser frontend that renders fleet governance health from CLI JSON outputs:

- `gator-dashboard.py` owns the HTTP server, startup globals, settings management, and browser launch. It is a **thin renderer** — no governance logic lives here. Dual-mode architecture: Repo mode (default) shows simplified repo list and settings; Command Post mode shows full fleet/audit surface. Mode stored in gitignored `dashboard-settings.json`.
- `dashboard/helpers.py` owns shared constants (`SCRIPTS_DIR`, `DASHBOARD_DIR`, `COMMAND_POST_ROOT`) and utility functions (`run_json`, `run_text`, `git_run`) used by both `gator-dashboard.py` and extracted dashboard modules. Prevents circular imports between modules.
- `dashboard/updates.py` owns self-update operations for the gator-command install via pipx: `check_for_updates` (compares the installed version to PyPI latest — read-only), `upgrade_and_restart` (spawns a detached helper that runs `pipx upgrade gator-command` then relaunches the dashboard), `restart_server` (process restart via os.execv).
- `dashboard/snapshot.py` owns self-contained offline HTML generation (`build_snapshot`). Reads dashboard assets, inlines CSS and JS, embeds Tier 1 data as `window.DASHBOARD_DATA`. Uses lambda replacement in `re.sub` to avoid backslash misinterpretation from JavaScript content.
- `dashboard/data.py` owns data collection and transformation: registry loading (`load_registry_repos`), standalone collection (`collect_standalone_data`), repo path resolution (`resolve_repo_path`), git history (`get_repo_history`), audit session resolution (`resolve_audit_sessions`), search (`parse_search_query`, `search_repo_files`), and repo key injection (`inject_repo_keys`).
- `dashboard/` also owns all frontend assets: HTML shell, CSS, JS view modules, and static images (`gator-logo.png` sidebar brand, `favicon.png` browser tab). No framework, no build step, no CDN dependencies. The shell uses a Fly.io-style sidebar layout with grouped navigation (Overview, Workspace, Knowledge), a topbar with title/subtitle/refresh, and a routed content area. The sidebar brand area displays the sleek-profile gator logo (`<img id="brand-logo">`) instead of text. `gator-logo.png` is RGBA 500×500 with a transparent background (white silhouette over transparency); do NOT ship a version with an opaque background — the sidebar bg is `#1e1e2e`, not pure black, so opaque-black logos show a visible rectangular halo. **Extraction recipe** for a new asset from a white-on-black source: linear-stretch the luminance-as-alpha channel (below luminance 60 → fully transparent, above 200 → fully opaque, linear ramp between). Direct luminance-as-alpha without the threshold produces a subtle dark rectangle on the sidebar bg because "dark-but-not-black" source pixels map to low-but-nonzero alpha. `favicon.png` is 32×32 RGB (opaque black square, gator profile in white) — the black square IS the design at favicon scale, so no transparency processing is needed. Browser tab title is `<title>Gator</title>` (short — the favicon carries the brand, the title just says what it is). Referenced from `dashboard.html` via `<link rel="icon" type="image/png" href="favicon.png?v=<N>">` — the `?v=<N>` query string is a cache-buster convention: bump `N` (currently `v=3`, 2026-08-09) whenever `favicon.png` bytes change so users on a cached prior CLI version don't get stuck displaying the old icon. Same trick applies to any future asset whose contents change but URL doesn't.
- Fleet view: per-repo health status, charter count, last commit, drift badge, policy sync badge, per-repo update button. Policy sync summary card shows current/stale/needs-action counts.
- History view: recent commits from `git log` with rich descriptions, agent/architect badges from trailers. Pure git — no session or snippet dependency. Replaces Audit in the Gator Individual product. Data source: `GET /api/repo/<name>/history`.
- Audit view (**enterprise-only**, excluded from public wheel): governed commits, significance distribution, session coverage, override events, session summary table (lazy-loaded from `/api/audit/sessions`) with expandable rows showing commits, files touched, notes. Fleet toggle button switches between single-repo and fleet view.
- Repo view: charter coverage %, stale charters, policy link panel (state/authority/source/cached timestamp from Tier 1 fleet data), recent trailer history, override events, recent sessions panel with drill-down modal (lazy-loaded per repo via `/api/repo/<name>`).
- Updates view: self-update for the local gator-command install — checks PyPI for a newer version and upgrades via `pipx upgrade`.
- Snapshot mode: self-contained offline HTML via `--snapshot`.

## Does Not Own

- Governance logic — all business logic stays in CLI scripts (`gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`, `gator-repo-status.py`). The dashboard only renders their JSON.
- Per-repo data computation — that is `gator-repo-status.py` (see fleet-intelligence charter).
- Fleet data collection — that is `gator-fleet-report.py` and `gator-drift.py`.
- Audit data collection — that is `gator-audit.py`.
- Deployment to governed repos — the dashboard is a **command-post tool** and is never shipped by the Gator installer to fleet repos.
- Enforcement config ownership — `.gator/config.json` is repo-local and canonical; dashboard reads and edits it but does not own it.

---

### run_json(script_name, *extra_args, timeout=90)
File: `src/gator_command/scripts/dashboard/helpers.py`
Runs a sibling script with `--json`. Returns parsed dict or `{"error": "..."}` on any failure mode (timeout, bad JSON, missing script, non-zero exit).
Filesystem: none (subprocess call)
<- `collect_standalone_data()`, `DashboardHandler.do_GET()` (Tier 2)
! Uses `sys.executable` for the Python interpreter — never a bare `python` call. Required for Windows compatibility and venv correctness.

### collect_standalone_data(registry_repos)
File: `src/gator_command/scripts/dashboard/data.py`
Standalone startup: builds payload from fleet registry, enriching each accessible repo via `run_json("gator-repo-status")`. Returns `{standalone: true, generated_at, repos: [...]}`. No fleet-report, drift, or audit calls. Each repo entry has name, path, remote, accessible flag, plus enrichment fields (branch, charters, hook_status, config, topology, cli_version, etc.) when repo-status succeeds. If enrichment fails, the repo object includes `status_error` with the failure reason instead of silently dropping all enrichment fields.
Filesystem: registry.md (R via `load_registry_repos()`)
<- `main()` (when `find_command_post()` returns None)
! The Fleet subtitle in `dashboard.js` must branch on `state.data.standalone`. In standalone mode, total and accessible counts are derived from `state.data.repos` (count all, filter by `repo.accessible`). In command-post mode, counts come from `state.data.fleet.summary`. Using the wrong path silently produces zero counts.

### Dashboard settings note
File: `src/gator_command/scripts/gator-dashboard.py`
Reads/writes `dashboard-settings.json` (gitignored, next to gator-dashboard.py). Contains mode ("repo" or "command-post") and UI preferences. No repo config — enforcement settings are repo-local. Returns defaults if file missing or corrupt.
Filesystem: `dashboard-settings.json` (RW)
<- `main()`, `do_GET(/api/settings)`, `do_POST(/api/settings)`

### build_snapshot(fast_data)
File: `src/gator_command/scripts/dashboard/snapshot.py`
Produces a self-contained HTML snapshot: inlines CSS and JS, embeds JSON as `window.DASHBOARD_DATA`. No server required to view. Takes Tier 1 data as a parameter (caller is responsible for collection).
Filesystem: `dashboard/` assets (R)
<- `main() --snapshot`
! Writes UTF-8 bytes to `sys.stdout.buffer` to avoid Windows cp1252 encoding errors (the nav brand uses a Unicode glyph).
! Uses `lambda m: replacement` in `re.sub` — never a raw f-string replacement. JavaScript content contains backslashes that `re.sub` would misinterpret as backreferences.

### run_text(script_name, *extra_args, timeout=60)
File: `src/gator_command/scripts/dashboard/helpers.py`
Runs a sibling script without `--json`. Returns `(stdout, stderr, exit_code)` tuple. Used for write actions (e.g. gator-update) that produce human-readable text output.
Filesystem: none (subprocess call)
<- `DashboardHandler.do_POST()`
! Returns `("", error_msg, 1)` on timeout or script not found — never raises.
! Subprocess call uses `encoding="utf-8", errors="replace"` (v2.4.4 fix). Bare `text=True` would crash on non-cp1252 bytes in child-script output on Windows. Same class of bug that hit `gator_core.git()` in the same release — see `scripts-core-library.md` `### git()` tripwire.

### do_GET(self)
File: `src/gator_command/scripts/gator-dashboard.py`
Routes incoming HTTP requests:
- `GET /` → `dashboard.html`
- `GET /api/data` → `fast_data` JSON (Tier 1, or standalone payload)
- `GET /api/settings` → dashboard settings JSON
- `GET /api/refresh` → starts background Tier 1 re-collection, returns `{"status":"refreshing"}`
- `GET /api/repo/<name>` → runs `gator-repo-status --path <resolved_path>` (Tier 2, lazy). Resolves name→path from registry for standalone compatibility.
- `GET /<any>` → static file from `dashboard/` via `_send_file()`. MIME map covers `.html`, `.css`, `.js`, `.jpg`, `.jpeg`, `.png`, `.svg`; unknown extensions fall back to `application/octet-stream`.
Filesystem: `dashboard/` (R), subprocess for Tier 2
! Tier 2 timeout is 30s per repo. On timeout or error, returns `{"error":"..."}` — the Repo view JS handles the degraded state.

### _check_post_auth()
File: `src/gator_command/scripts/gator-dashboard.py`
Anti-CSRF guard for all POST requests. Requires the custom header `X-Gator-Dashboard: 1`. Browsers never send custom headers on simple form POSTs, `<img>` embeds, or navigations. A cross-origin `fetch()` with custom headers triggers a CORS preflight OPTIONS request, which this server does not answer — so the browser blocks the actual POST.
<- `do_POST()` (called before any route handling)
! This is the trust boundary guard. Do NOT weaken it to Origin-only checking — Origin can be absent on some browser form POSTs.
! All JS fetch() calls to POST endpoints must include `headers: { "X-Gator-Dashboard": "1" }`.

### resolve_repo_gatorize(repo_name, registry_repos, fleet_data, run_text_fn=None)
File: `src/gator_command/scripts/dashboard/data.py`
Resolves and runs the repo gatorize action for `POST /api/repo/<name>/gatorize` — the ungoverned-repo install path (Stage 3 fold-in of the retire-gator-install plan, 2026-07-30). Testable without HTTP. Returns `{"status": <http_code>, "data": <response_dict>}`. Resolves path via `resolve_repo_path()` first, then falls back to `fleet_data.repos`. Refuses on already-gatorized repos with HTTP 400 pointing at the Update button. Invokes `run_text("gatorize", "--yes", repo_path, timeout=120)` — non-interactive because the Dashboard cannot answer prompts; `--yes` is honored per-site via `helpers.prompt(auto_yes=)` opt-ins (see `scripts-installer.md`). Longer timeout (120s vs 60s for update) because gatorize does full installs including template copies.
Filesystem: probes `<repo>/.gator/` (R); delegates the write to gatorize via subprocess
<- `DashboardHandler.do_POST()` at `/api/repo/<name>/gatorize`
! `gatorize` is always invoked with `--yes` from this endpoint. If a fleet-repo install ever needs an interactive decision (e.g. Scenario 5 dual memex + gator), gatorize exits 1 with a message telling the user to run it from a terminal. The Dashboard surfaces that error output directly.
! Under `--yes`, gatorize refuses on a dirty working tree with exit 1. Users see the error inline and must commit/stash from a terminal before retrying via the Dashboard.

### resolve_repo_update(repo_name, registry_repos, fleet_data, run_text_fn=None)
File: `src/gator_command/scripts/dashboard/data.py`
Resolves and runs the repo update action for `POST /api/repo/<name>/update`. Testable without HTTP — the endpoint handler is a thin delegate. Returns `{"status": <http_code>, "data": <response_dict>}`. Resolves path via `resolve_repo_path()` (registry first), then falls back to `fleet_data.repos`. Pre-checks the resolved path exists AND contains a `.gator/` dir; ungatorized repos return HTTP 400 pointing at the Gatorize button. Runs `run_text("gator-update", "--path", repo_path, timeout=60)` — never `gatorize`. `run_text_fn` is dependency-injection for tests; production callers omit it.
Filesystem: probes `<repo>/.gator/` (R); delegates the write to gator-update via subprocess
<- `DashboardHandler.do_POST()` at `/api/repo/<name>/update`
! Never call `gatorize` from this endpoint. Silent branch-switch bug (repo landed on `gator-install` branch instead of the user's viewing branch) was fixed in v2.4.0 by swapping to `gator-update`. See plan `2026-07-30-retire-gator-install-branch-implementation-plan.md` (Stage 1).
! `gator-update.py` has no positional path argument — `--path`/`-p` is required. `run_text("gator-update", repo_path, ...)` (without `--path`) is an argparse error.
! **Frontend must SURFACE the failure output, not just mark it** (issue #1 class, fixed 2026-08-23): the backend has always returned the CLI's `output` on failure, but `fleet.js` (`bindUpdateButtons` + `bindGatorizeButtons`) rendered it only as a hover-tooltip on a red `!` — a mixed-layout refusal read as "the Update button does nothing" (field case: cl-strategy). Both handlers now also `alert()` the CLI output (operation name taken from the button label) on error AND on fetch exception. Keep the tooltip; never regress to marker-only.

### _find_session_content(self, repo, source_kind, filename)
File: `src/gator_command/scripts/gator-dashboard.py`
Resolves and reads a session summary file from a local repo. Only `source_kind="local-repo"` is supported (command-post and remote-cache source kinds retired). Resolves repo path via `_resolve_repo_path()` from registry, falls back to `fast_data.repos` list. Returns `(content, None)` on success or `(None, error)` on failure.
Filesystem: `.gator/sessions/` (R)
<- `do_POST()` at `/api/session`
! Filename validated by caller: no `..`, no `/`, must end with `.md`.

### do_POST(self)
File: `src/gator_command/scripts/gator-dashboard.py`
Handles write actions from the browser. Calls `_check_post_auth()` first for anti-CSRF protection.
- `POST /api/repo/<name>/config` → writes to repo's `.gator/config.json` (enforcement level editor). Dashboard is just an editor of the repo-local file.
- `POST /api/repo/<name>/topology` → switches repo between policy-synced and standalone. Standalone clears all policy artifacts via `clear_policy_artifacts()`. Policy-synced regenerates thin link (requires live command post).
! No dashboard-wide mode toggle. Topology is per-repo. Settings view shows three-state topology (policy-synced/standalone/inconsistent) with inconsistent repos flagged as "needs repair."
! Refresh uses `collect_standalone_data()` — the same path as startup. The `/api/refresh` handler re-runs it in a background thread guarded by `_refresh_lock`.
! Fleet view is the repo operations surface: hooks, health, coverage, last commit, update. Policy columns removed — policy governance moves to Audit view.
! `_resolve_repo_path()` normalizes MSYS-style `/c/` paths via `normalize_path()`. All downstream consumers (Tier 2, update, config, topology) depend on this returning a Windows-native path.
! Fleet Update calls `gator-update.py --path <repo_path>` — operates on the current branch in place (no branch switch), template overlay, entry-point managed-block refresh with `.pre-gator-update` backups. Pre-checked: ungatorized repos (no `.gator/` dir) return HTTP 400 pointing at the Gatorize button. Historical `gatorize.py` invocation was retired in v2.4.0 (see plan `2026-07-30-retire-gator-install-branch-implementation-plan.md`) because it silently switched to a `gator-install` branch. `POST /api/repos/register` still invokes `gatorize.py` for the first-install path — that surface is unchanged.
! Fleet table (standalone): Repo, Branch, Enforcement (inline dropdown), Version, Update, (activity). Update button enabled when repo `cli_version` does not match `gator_cli_version` (or version unknown). Fixed-width activity column shows CSS dot-pulse animation during update, `!` with tooltip on failure, clears on success + fleet refresh. Enforcement dropdown shows green checkmark on save (fades after 1.2s via `save-check-fade` animation). Config POST updates cached `fast_data` in-place so page refresh reflects the change without requiring explicit Refresh. Updates view checks PyPI for latest version and upgrades via `pipx upgrade gator-command`. Version resolution delegates to `gator_core.get_version()`. Upgrade button stops the server, spawns a detached helper that runs `pipx upgrade` then relaunches the dashboard — avoids Windows file lock on `gator.exe`. Standalone Fleet and Updates views omit the in-content view-header (topbar provides the title). Repo file browser uses a whitelist for `.gator/` content: top-level files (pulse, mission, roadmap, inbox, issues, patterns, whiteboard) and directories (charters, threads, artifacts, blueprints, vault, field-guides, docs, reference-notes, policies, procedures, loops). File scan includes `.jsonl` alongside `.md` and `.json`. Server-side `_is_denied_path()` blocks serving of `.tokens.json`, `session.lock`, and override internals from both `/file/` and `/raw/` endpoints (403). Sidebar listing also filters denied files. Shipped default template files in procedures/ and reference-notes/ are hidden via `DEFAULT_TEMPLATE_FILES` set — only README, _template, and user-created files show. All other `.gator/` files and dirs are hidden as infrastructure. Repo sidebar uses visual indentation hierarchy: section (12px) > folder header (16px) > file (32px via `.indented` CSS class). All files inside any section get the indented class, not just subdirectory files. VISIBLE_FILES whitelist includes constitution.md. Upgrade helper relaunches via `gator` CLI entry point (survives pipx venv rebuild), uses `CREATE_NO_WINDOW` on Windows.
! GET `/api/repo/<name>/check` — read-only status check: runs `gator-update --dry-run --json --no-policy` for template freshness AND `gator-charter-verify --json` for charter health. Returns combined result with `charter_health.finding_count`. Fleet Charters column updates to show checkmark (0 findings) or warning with hover tooltip listing findings (findings detected). Fleet table columns: Repo, Gator (gen N), Branch, Charters, Last commit, Last updated, Status. Sidebar: Repo tab is a sub-item under Fleet in Overview group (no separate Workspace group).
! Repo view is a markdown file browser: secondary sidebar lists `.gator/` files (`.md` and `.json`), main content renders markdown or JSON as code blocks. Default document: `pulse.md` (if exists), then `mission.md`. Endpoints: `GET /api/repo/<name>/files` (file list), `GET /api/repo/<name>/file/<path>` (file content — URL-decoded, path traversal protected). JS encodes path segments individually to preserve slashes. File browser filters out infrastructure files (constitution, commit_draft, gator-start-up, scripts/) and default template files in procedures/ and reference-notes/ — only shows user-created content. Markdown links to .md files are intercepted and loaded in the browser with relative path resolution. File browser scans both `.gator/` and `gator-command/` (if present) — command-post repos show both knowledge layers. Command post injected via `_inject_command_post()` helper called from `collect_fast_data()` — survives refresh, uses real git branch. File browser filter normalizes `gator-command/` prefix for hiding default template files. Dir values stripped of trailing slashes to prevent double-slash display. File read endpoint includes `last_modified` from `git log -1 --format=%ai`, displayed right-aligned under file header. Repo topbar shows branch name in muted gray. Topbar-left padded to avoid sidebar toggle overlap. Sidebar toggle uses panel icon. File filter only hides templates/deploy in `.gator/` source, shows them for `gator-command/` source. Copy path button next to file header copies repo-relative path. Refresh button (&#8635;) next to copy button re-fetches the current file without reloading the full dashboard or resetting sidebar navigation. Copy content button (clipboard icon) in file header copies raw file content. In-document search input in file header highlights text matches and scrolls to first hit. Cross-document search input in topbar (Repo view only) calls `GET /api/repo/<name>/search?q=<query>` for server-side grep (~0.2s for 400+ files), shows results as clickable cards with context snippets. Uses history.pushState for browser back button support.
- `GET /api/repo/<name>/search?q=<query>` → server-side full-text search across `.gator/` and `gator-command/` files. Supports boolean operators: `term1 AND term2` (both required), `term1 OR term2` (either matches), plain text (exact phrase). Returns `{results: [{path, snippet, match_count}], query}`. Max 50 results, sorted by match count descending. Query must be 2+ chars. Source files (project code) listed under `source/` groups — `source/` prefix resolved to repo root on read. Non-markdown files rendered as code blocks. File sidebar has top-level collapsible sections: `.gator/` (open by default), `gator-command/` (command-post only), `source/` (repo code, collapsed). Markdown `![alt](src)` renders inline images via `GET /api/repo/<name>/raw/<path>` binary endpoint. Relative image paths resolved from current file's directory. Fleet Check Status disabled for command post repo via `is_command_post` flag (matched by path, not just name). Shows "via Updates." Repo file browser has collapsible directory groups — all start collapsed for clean sidebar. Files within directory groups sorted by descending mtime (most recent first). File list API includes `mtime` field from filesystem stat. Priority files (pulse, mission, roadmap, etc.) retain their fixed order at top. Main Gator sidebar is collapsible via hamburger toggle. Repo file sidebar is resizable via drag handle (120px–500px, flex sibling element not inside sidebar innerHTML). `gator-pulse.py` generates strategic operations brief: Top 5 Next Steps, Roadmap Check, Top 5 Priorities, Issues & Blockers, Recent Activity. Check Status plan items are objects with `.action` property (not array index). Pulse Roadmap Check preserves the full original roadmap table (all columns) plus in-progress detail list.
- `GET /api/audit/sessions` → lazy session summary aggregation. Query params: `repo=<path-hash>` (single repo by 12-char path hash), `fleet=true` (all repos), `refresh=true` (force cache regeneration). Handler delegates to `_resolve_audit_sessions()` (testable, module-level). Imports `gator-session-aggregator` via `import_sibling()`. Returns JSON array of `gator-session-summary-v1` payloads. Not part of Tier 1 startup — called on demand when Audit view opens. Registry resolution uses startup-loaded `_REGISTRY_REPOS` — runtime registry changes require dashboard restart. Standalone data includes `repo_key` per repo for JS consumption.
! Audit view session table row/detail DOM IDs use `repo_key-session_id` compound key to prevent collisions when fleet mode shows sessions from multiple repos with the same session_id shape. Fleet toggle is hidden when no repo is selected (no activeRepoKey) — avoids fake toggle that switches label without changing data.
! `_inject_repo_keys()` runs after `_inject_command_post()` in `collect_fast_data()` — ensures every fleet repo entry (including command-post) has `repo_key` for Audit view identity. Both command-post and standalone modes must produce `repo_key` in fleet data. Covered by `TestInjectRepoKeys` (5 tests, including command-post integration path).
- `POST /api/session` → reads raw markdown content of a specific session summary. Request body: `{repo, source_kind, filename}`. Returns `{filename, repo, source_kind, content}`. Validates filename (no path traversal, .md only) and source_kind (must be known value).
- `POST /api/repo/<name>/update` → runs `gator-update --path <repo_path>` on the repo's local path. Returns `{status, output, exit_code}`. Resolves path from registry first, then falls back to fleet data. Handler is a thin delegate to `resolve_repo_update()` in `dashboard.data` (testable, module-level) — parallels the `_resolve_audit_sessions()` pattern.
- `POST /api/repo/<name>/gatorize` → runs `gatorize --yes <repo_path>` on an ungoverned repo. Returns `{status, output, exit_code}`. Handler delegates to `resolve_repo_gatorize()` in `dashboard.data`. Wired to the Fleet-row Gatorize button (fleet.js: `bindGatorizeButtons()` handler, `gatorize-btn` class) — completes the Stage 1 fix by giving ungoverned repos their own endpoint instead of routing through `/update`.
Filesystem: none (delegates to run_text which runs gator-update.py)
<- Fleet view Update button (fleet.js), session evidence modal (dashboard.js)
! Validates repo exists in fast_data and is accessible before running update. Returns 404 if not in registry, 400 if not accessible or path is empty.
! Ungatorized-repo pre-check: if repo path exists but has no `.gator/` dir, returns HTTP 400 with `{"error": "not gatorized — use Gatorize button (Fleet row) instead of Update"}`. Closes the button-mislabeled recovery case where a fleet-row Update click was landing on an ungatorized repo.
! Uses `run_text()` not `run_json()` — gator-update produces human-readable output, not JSON.
! Update output now reports the managed hook destination (`.git/gator-hooks` on Windows, `.git/hooks` elsewhere). The dashboard must treat that output as opaque text and not assume legacy `.git/hooks`.

### Fleet update button
Fleet view shows an "↑ Update" button in the last column for every repo. For accessible repos the button POSTs to `/api/repo/<name>/update` and shows the result inline. For remote-only repos the button is rendered but disabled (`disabled` attribute).
On success: shows "✓ <summary>" extracted by `parseSummaryLine()`, then calls `window.gatorRefreshFleet()` to re-fetch Tier 1 data so the drift/health columns reflect the update.
On failure: shows "✗ Failed" with the error in `title`.
! `window.gatorRefreshFleet` is assigned in `dashboard.js` (exposed from IIFE) before fleet.js event handlers fire. fleet.js must guard with `if (window.gatorRefreshFleet)`.
! The entire Update column (header, cells, buttons) is suppressed in snapshot mode via `isSnapshot = !!window.GATOR_SNAPSHOT`. Snapshot mode is a read-only static report — no write controls should appear.

### parseSummaryLine(output) (fleet.js)
Extracts the most useful single line from gator-update text output for inline display. Priority: "Policy version:" line first, then "Done:" line, then "Already current" (from "Everything is current."), then "Done" fallback.
<- Update button event handler
! Do not change priority order — "Policy version:" is the most informative signal when a bump happened.

### check_for_updates()
File: `src/gator_command/scripts/dashboard/updates.py`
Read-only version check: compares the installed CLI version (via `gator_core.get_version()`) against the latest version published on PyPI. The only network access is a GET to the PyPI JSON API — no repo or `.git/` mutation. Safe for GET.
Returns `{current_version, latest_version, update_available}`.
Filesystem: none (reads installed version + PyPI HTTP GET)
<- `DashboardHandler.do_GET()` at `/api/updates/check`
! `update_available` is true only when both versions are known and differ. Unknown versions render as `"unknown"` and never claim an update.

### upgrade_and_restart()
File: `src/gator_command/scripts/dashboard/updates.py`
Upgrades gator-command via pipx, then relaunches the dashboard. Spawns a fully detached helper process that waits for this dashboard to exit (releasing the `gator.exe` file lock), runs `pipx upgrade gator-command`, writes the result to `~/.gator/upgrade-log.txt`, and relaunches the dashboard. Then exits the current process via `os._exit(0)` so the file lock is released.
Filesystem: `~/.gator/upgrade-log.txt` (W, by the detached helper)
<- `DashboardHandler.do_POST()` at `/api/updates/upgrade` (via background thread)
! Relaunch prefers the `gator` CLI entry point (survives the pipx venv rebuild); falls back to `python gator-dashboard.py` with the original args (plus `--no-open`) when `gator` is not on PATH.
! On Windows the helper is spawned with `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` so it survives the parent exit without a console window.

### Updates view (updates.js)
Self-update control for the local gator-command install. On load — and on the "Check for updates" button — it calls `GET /api/updates/check`, showing the installed version and the latest PyPI version. When an update is available the "Upgrade" button appears; clicking it POSTs to `/api/updates/upgrade`, shows a polling overlay, and reloads once the relaunched server answers `/api/updates/check` again. "Restart Dashboard" button POSTs to `/api/restart` with the same polling overlay. Both write actions send the `X-Gator-Dashboard: 1` header.
! On-load auto-check hits PyPI once (read-only). The "Upgrade" button is the only control that mutates the install.
! Fleet table "Check Status" buttons use `update-btn` class for consistent styling.

### File history dropdown
Gray `▾` arrow next to "Last updated" date. On click, fetches `/api/repo/<name>/history/<path>` (git log for the file, last 50 commits). Dropdown shows hash, timestamp, message. Clicking a commit re-fetches the file at that version via `?version=<hash>`. "Viewing" label shows hash + full timestamp.

### Fleet mode
Dashboard always operates in standalone fleet mode using `~/.gator/dashboard-repos.json` as machine-local registry. `collect_standalone_data()` enriches each repo with `gator-repo-status` (branch, charters, hook_status, config, last_governed_commit, session_summary_count) and adds `gatorized` boolean (`.gator/` directory presence). Command-post mode is retired — no dual-mode branching. CLI: `--add-repo PATH`, `--remove-repo NAME`.

### Fleet "Add Repository"
Fleet view includes an "Add Repository" button (standalone mode only, suppressed in snapshot). Opens a modal with:
- Manual path input with Register button
- Auto-discovered repos from `resolve_discovery_roots()` — shallow scan (direct children only), Git repos only, excludes already-registered repos
- Each discovered repo shows name, path, gatorized/ungoverned status, and Add button

Endpoints:
- `GET /api/repos/discover` — scans discovery roots, returns unregistered Git repos
- `POST /api/repos/register` — validates path is a Git repo, registers via `ensure_dashboard_registry_entry()`, updates in-memory `_REGISTRY_REPOS`

Fleet rows distinguish governed vs ungoverned repos: ungoverned show blue "Gatorize" button, governed show "Update" button, enforcement dropdown shows "-" for ungoverned.
! All POST calls include `X-Gator-Dashboard: 1` header for CSRF protection.
! Registry paths are normalized from MSYS-style `/c/Users/...` to Windows-native on load via `normalize_path()`.

### resolve_discovery_roots()
File: `src/gator_command/scripts/dashboard/data.py`
Returns the list of directory paths to scan for the "Add Repository" modal's auto-discovery. Reads `GATOR_DASHBOARD_DISCOVERY_ROOTS` env var (paths separated by `os.pathsep` — `:` on Unix, `;` on Windows) as an EXCLUSIVE override; when unset, falls back to `DEFAULT_DISCOVERY_ROOTS` (a tuple of home-relative dir names: `code`, `code2`, `projects`, `repos`, `src`, `dev`). Only paths that exist as directories are returned; non-existent entries are filtered silently.
Filesystem: none (reads env + `Path.is_dir()` probes)
<- `DashboardHandler._handle_repo_discover()`
! Env-var override is EXCLUSIVE, not additive — when set, the defaults are NOT unioned in. Motivation: demo mode, screenshot capture, or repos organized outside the default home-relative layout (e.g. `~/work`, `/mnt/repos`) need the ability to say "these paths and only these."
! Empty-string or whitespace-only env var falls back to defaults rather than returning an empty list — protects against accidentally-cleared env vars silently killing discovery.
! Tilde in env-var entries expands per-entry via `Path.expanduser()`.
! Regression guards in `TestResolveDiscoveryRoots` (7 tests) pin: defaults-when-unset, single-path override, multi-path via `os.pathsep`, filtering of non-existent paths, empty-string fallback, whitespace-only fallback, tilde expansion.

### gator kill dashboard [--all | --port N | --dry-run]
File: `src/gator_command/scripts/gator-kill.py`
Kills running Gator Dashboard process(es). Addresses an operational failure mode where stale Dashboard processes accumulate silently during self-upgrade or when the Dashboard is launched detached (no visible terminal). The port scanner grabs 8420-8429 sequentially, so a stale process on 8420 forces fresh launches to higher ports while the user's browser keeps talking to the stale one — env-var overrides don't take effect, in-flight code changes appear ignored, discovery scans yesterday's roots. `gator kill dashboard --all` is the reliable escape hatch.
Cross-platform: Windows uses `wmic` for process listing, `netstat -ano` for port resolution, `taskkill /F` for termination. Unix uses `pgrep -af`, `lsof -nP -i TCP -sTCP:LISTEN`, `os.kill(pid, SIGTERM)`. All subprocess calls have 5-10s timeouts; missing tools degrade gracefully to empty results.
Flags:
- No flag (default): lists running dashboard processes with usage hints — safe default, no killing.
- `--all`: kills every `gator-dashboard.py` process.
- `--port N`: kills only the dashboard on port `N` (must be in range 8420-8429).
- `--dry-run`: with `--all` or `--port`, prints targets without killing.
Filesystem: none (pure process management)
<- CLI (`gator kill dashboard`), demo workspace's `bin/demo-dashboard` wrapper (calls `--all` before spawning a fresh dashboard)
! Nested-subverb shape (`gator kill <target>`) is deliberate — leaves room for `gator kill loop`, `gator kill enforcer`, etc. without CLI restructure. New targets should follow the same three-flag pattern (`--all` / `--<selector>` / `--dry-run`).
! Testable helpers (`_parse_wmic_output`, `_parse_pgrep_output`, `_parse_netstat_windows`, `_parse_lsof_output`, `_is_dashboard`, `_format_proc_line`) are module-level and covered by `TestParseWmicOutput` / `TestParsePgrepOutput` / `TestParseNetstatWindows` / `TestIsDashboard` / `TestFormatProcLine` (21 tests total). Actual process-kill code is NOT unit-tested — the demo workspace's `bin/demo-dashboard` exercises it end-to-end.
! Dashboard port range constant is `DASHBOARD_PORT_RANGE = range(8420, 8430)` — matches the `find_free_port()` scan range in `gator-dashboard.py`. Keep them synchronized if the port range ever moves.
! **Selector semantics at the CLI boundary** — the three CLI flags interact under strict rules, all enforced BEFORE any process discovery runs (Codex remediation):
  - `--all` and `--port N` are mutually exclusive (argparse `add_mutually_exclusive_group`) — passing both exits 2 with the standard argparse "not allowed with" message. Prior behavior silently gave `--port` precedence, so `gator kill dashboard --all --port 8420` would kill only the one on 8420 and leave the others alive. Do NOT reintroduce silent precedence.
  - `--dry-run` requires either `--all` or `--port` — passing `--dry-run` alone exits 2 with an explicit error, not a silent fallthrough to the no-flag "list processes" behavior. Preview intent must have a selector.
  - `--port N` must be inside `DASHBOARD_PORT_RANGE` — a port outside 8420-8429 can never match a dashboard, so passing e.g. `--port 3000` exits 2 with a range error rather than the generic "no dashboard on this port" message. The generic message is reserved for valid-range-but-unoccupied.
  - Regression guards in `TestSelectorSemanticsAtCliBoundary` (8 tests) pin all three rules plus positive cases (`--all --dry-run`, `--port 8420`, `--port 8429` boundaries, no-flags safe default).

### Command-post retirement
Command-post architecture is retired from the dashboard. `_HAS_COMMAND_POST` global removed. `find_command_post()` no longer called at startup. `collect_fast_data()` and `inject_command_post()` — the command-post/Tier-1 collection path — are removed from the dashboard's `data.py` entirely. Fleet view renders through a single code path (no `data.standalone` branching). Settings view removes topology controls — `policy-synced` topology endpoint returns "no longer supported". The old command-post fleet renderer (`bindStatusButtons`, `chartersCell`, `lastCommitCell`, `lastUpdatedCell`) is deleted.

### git_run(*args, cwd)
File: `src/gator_command/scripts/dashboard/helpers.py`
Shared git subprocess helper. Uses `encoding="utf-8"` (not `text=True`) to avoid Windows cp1252 decode crashes on non-ASCII content in git output. Returns `(stdout_or_stderr, ok)`. Defaults to `COMMAND_POST_ROOT` as cwd.
! This is the central git subprocess call for the dashboard. All git history, file version, and update operations flow through it. Imported as `_git_run` in `gator-dashboard.py` for call-site compatibility.

### restart_server()
File: `src/gator_command/scripts/dashboard/updates.py`
Restarts the dashboard server process. Waits 1s for the HTTP response to flush, then replaces the process via `os.execv`. Adds `--no-open` to prevent opening a duplicate browser tab. Imported as `_restart_server` in `gator-dashboard.py`.
<- `DashboardHandler.do_POST()` at `/api/restart` (via background thread)

### run_text(script_name, *extra_args, timeout=60)
File: `src/gator_command/scripts/dashboard/helpers.py`
Runs a sibling script without `--json`. Returns `(stdout, stderr, exit_code)` tuple.
<- `DashboardHandler.do_GET()` (charter-verify)

### Branch history dropdown
Gray `▾` arrow in the repo view header next to the branch name. On click, fetches `/api/repo/<name>/commits` (git log for the repo, last 50 commits). Selecting a commit sets `window._gatorRepoVersion`, reloads the file list via `/api/repo/<name>/files?version=<hash>` (uses `git ls-tree`), and all subsequent file loads use `?version=<hash>` (uses `git show`). "HEAD" option returns to current working state. "Viewing" label shows hash + full timestamp in the header.
! Suppressed entirely in snapshot mode — shows "Updates are not available in snapshot mode."
! All POST calls include `X-Gator-Dashboard: 1` header for CSRF protection.

### showSessionModal(repo, sourceKind, filename) (dashboard.js)
Shared modal for viewing session summary markdown. Creates modal DOM lazily on first call. POSTs to `/api/session` with `{repo, source_kind, filename}` and `X-Gator-Dashboard` header. Renders content as `<pre class="session-markdown">` (monospace, pre-wrap). Close on overlay click, X button, or Escape key.
<- audit.js session evidence table, repo.js recent sessions panel
! No markdown parser — summaries are human-readable as source. `<pre>` is sufficient.
! Suppressed in snapshot mode — View buttons replaced with plain filename text. The table metadata still renders.

### Session evidence table
Renders `data.audit.session_summaries` as a table after the "Sessions by agent" section. Columns: Date, Repo, Vendor, Goal, Decisions, Evidence. Goal truncated to 60 chars. Evidence column shows "View" button (live mode) or plain filename (snapshot mode). Limited to 25 rows.
<- `window.GatorViews.audit()`
! `session_summaries` comes from Tier 1 data (gator-audit.py) and includes `source_kind` for provenance.

### Recent sessions panel
Renders `repoData.recent_session_summaries` as a table after the Override events section. Columns: Date, Vendor, Goal, Decisions, Evidence. Same drill-down pattern as audit view. Same snapshot-mode suppression.
<- `window.GatorViews.repo()`
! Data comes from Tier 2 lazy load (gator-repo-status.py::get_session_summaries). Each item has `source_kind: "local-repo"`. Underlying reader retargeted from `gator-sessions` to `gator_session_reader` in Phase 2A (2026-08-12); parse behavior byte-identical, dashboard payload unchanged.
! The View button always uses the viewed `repoName`, not the summary's frontmatter `repo` field. The file lives in the viewed repo's `.gator/sessions/` regardless of what repo the session was about.

### Policy columns retired
Renders the Policy column cell for a fleet row. Maps policy_link.state to badge: synced=green, behind=amber, diverged=red, no-cache=light, cached=grey, local-only=grey, unknown/unavailable="—".
<- Fleet table row rendering loop
! Badge colors must match the taxonomy in the integration plan. cached gets a grey badge (information preserved), unknown/unavailable get "—" (no information).

### Policy sync summary card retired
A 5th card in the fleet summary card row. Headline value: `policy_current` count. Secondary line: `X stale · Y need cache` from `policy_stale` and `policy_needs_action`. All three counts come from `fleet.summary` (computed by fleet-report from authoritative repos only).
! Non-authoritative repos (cached, local-only) and unknown/unavailable repos are not counted in any summary bucket.

### Repo policy link retired
Renders the Policy link section in the Repo view. Shows state badge, authority label, source type, remote URL, and cached timestamp in a table layout. Adds an action hint for stale/needs-action states.
Data comes from Tier 1 `data.fleet.repos` (no extra API call). Returns empty string if fleetRepo is null.
! The authority label distinguishes "Authoritative" (green) from "Non-authoritative" (muted). This reflects whether the state was verified against the actual source.

### Health badge and summary card "Drifted" definition
Both `repoHealth()` (row-level badge) and `driftedCount` (summary card) must use identical semantics: only `severity === "drift"` counts as Drifted. `severity === "warn"` is "Healthy" in both places — warn findings (missing charters, stale commit_draft, hook-source issues, branch/trailer read failures) are governance hygiene signals, not policy drift. The "Policy drift" column surfaces the full severity for warn-level repos.
! Do NOT map `warn` to "Drifted" in either the badge or the summary card. Draft 3 §Health status table defines "Drifted" as "Hook present AND policy drift detected" — policy drift only.
! The summary card `driftedCount` and the per-row badge must stay in sync. If you change one, change the other.

### Fleet view coverage % column
Fleet-report JSON does not include `charter_coverage_pct` — computing it requires `git ls-files` + `Covers:` declaration parsing (a Tier 2 operation via `gator-repo-status`). The Fleet view shows "—" with charter count in a tooltip. The column header is "Coverage %" (not "Charters"). Clicking the repo name loads the Repo view which fetches and displays the full `charter_coverage_pct` from `gator-repo-status`.
! Do NOT substitute charter count or any proxy metric for `charter_coverage_pct`. The plan locks this definition at Draft 3 §Charter coverage %. Either show the real number or show "—".

### Recent governed commits table
The "Architect" column (formerly "PI") in the recent trailers table reads `t.architect` from repo-status JSON. The field is `Gator-Architect` in new trailers, with `Gator-PI` fallback for historical commits. The column header is "Architect".

### Stale charters panel
`renderStaleCharters()` iterates `item.stale_sources` (files actually newer than the charter) — not `item.covers` (all declared files). `gator-repo-status.py` computes both; the UI must use the narrower list.
! Using `item.covers` would overstate staleness whenever a charter declares multiple files and only one is newer. Always use `stale_sources`.

### Snapshot banner
The snapshot notice lives in `<div id="snapshot-banner">` inside `#main-shell` but outside `#view-slot`. `showView()` clears `#view-slot` but not its siblings — the banner persists across view transitions.
! Do NOT insert the snapshot banner into `#view-slot`. It will be cleared on first paint.

### HTML file support (v2.4.5)
`.html` and `.htm` files are visible in the Dashboard file browser and served as `text/html`. Applies to `.gator/` scans (filesystem walker AND version ls-tree walker). Source-repo scans already included `.html` via `_SRC_EXT`. Raw-endpoint MIME map serves `.html`/`.htm` as `text/html; charset=utf-8`; other extensions still fall back to `application/octet-stream`.

Clicks on HTML files route through `loadFile()` in `views/repo.js`, which detects `.html?$` and calls `window.open(rawUrl, "_blank", "noopener")` instead of routing through the markdown renderer. The content pane shows a "Opened X in a new tab" message.
! Auto-load code paths (Docs first-file, Repo default-file pick) MUST skip HTML files — `window.open()` outside a user gesture is popup-blocked. `loadFile()` itself does not know if it was called from a click vs. an auto-load, so the filtering lives at the call sites (docsFiles find, defaultFile pick).
! Version-pinned HTML is not supported. The `/raw/` endpoint has no `?version=` handler — a history-restored HTML click opens the current file, not the historical version. Consciously accepted: version pinning is for governance artifacts (charters, threads, sessions), not vault reports.
! HTML files in `.gator/vault/` are the intended use case (report artifacts). If HTML shows up in other `.gator/` subdirs it will still list — no whitelist.

### Docs view (dashboard.js → repo.js)
Docs is a top-level sidebar item under the Knowledge group. Requires a repo to be selected (dimmed until a Fleet repo is clicked). Routes to `views.repo()` with `filter="docs"`, which renders files from **both** `.gator/docs/` and repo-root `docs/` (source docs) in a flat alphabetical list. Sidebar header shows "Docs" instead of repo name. Auto-loads the first doc. Uses the same `loadFile()`, `initResizeHandle()`, and markdown renderer as the Repo view.
<- sidebar click handler (dashboard.js)
→ `loadFileList()` in repo.js (filter branch)
! The `filter` parameter is the 5th arg to `GatorViews.repo()`. Only `"docs"` is currently defined. The docs filter early-returns before the normal section rendering — it does not fall through.
! The filter accepts `f.dir === "docs"` OR `f.dir === "source/docs"` (v2.4.5). Prior to v2.4.5 only `.gator/docs/` was matched; this broke on repos that keep docs at the root (this source repo after the shadow-copy cleanup in 57c1c6b). Fleet/user repos with only `.gator/docs/` are unaffected. No whitelist against `PUBLIC_DOCS` — dogfooding in this repo intentionally sees all 27 `docs/*.md` files.

### repo-content sizing (dashboard.css)
The `.repo-content` pane holds the rendered markdown for both Repo and Docs views. It is a flex item inside a horizontal flex container (sidebar + content).
! `min-width: 0` is REQUIRED (v2.4.5 fix). Without it, flex-min-content sizing lets any wide child (natural-size images, long code blocks, wide tables) grow the pane beyond the viewport. The img's inline `max-width: 100%` then reads that expanded parent width and renders at natural size — defeating the shrink-to-fit. `overflow-x: auto` on the pane handles anything that still exceeds width. A safety-net rule `.repo-content img { max-width: 100%; height: auto }` guarantees images respect the content width even if a future markdown-render change drops the inline style.

### Shell layout
The app shell uses `#app-shell` as a flex container with `#sidebar` (fixed 220px, dark) and `#main-shell` (flex: 1). The sidebar has grouped nav items (Overview: Fleet/Repo/History, Knowledge: Docs, System: Updates). The main shell has `#topbar` (title, subtitle, refresh, timestamp) and `#view-slot` (scrollable content). On mobile (<768px), the sidebar collapses to a horizontal strip.
! The sidebar nav uses `.sidebar-item` buttons with `data-view` attributes — same dispatch pattern as the old `.nav-tab` buttons. The `dashboard.js` click handler targets `#sidebar-nav` instead of `#nav-tabs`.
! The Repo sidebar label is set via DOM API (textContent + createElement), NOT innerHTML. The repo name can come from `?repo=` query params — innerHTML would allow XSS injection.

### main()
File: `src/gator_command/scripts/gator-dashboard.py`
CLI entry point. Args: `--port`, `--no-open`, `--snapshot`, `--repo <name>`. Collects Tier 1 data, finds a free port (8420–8429), starts `HTTPServer`, opens browser.
Filesystem: none
<- CLI
! Port conflict: tries 8420 through 8429, then raises with a clear error. If `--repo` is given, opens browser directly to `/?repo=<name>`.

### Blueprints view (v2.11.0 Release A of the Blueprints 2.0 track)
File: `src/gator_command/scripts/dashboard/views/blueprint.js`, `src/gator_command/scripts/dashboard/blueprint/l1-data.json`, `src/gator_command/scripts/dashboard/blueprint/l1-positions.json`
Dashboard-native inspection surface for the human Architect: L1 charter map ported from the vault experiment (`.gator/vault/blueprints/charter-flowchart-high-level.html`) into a real Dashboard view. Sidebar item `Blueprints` in the Knowledge group (dimmed until a repo is active). Endpoint `GET /api/repo/<name>/blueprint?level=1` in `gator-dashboard.py::do_GET`. Data-vs-positions split (`l1-data.json` + `l1-positions.json`): Release B's parser will regenerate the data while positions stay hand-tuned as a repo-local overlay.
Filesystem: `dashboard/blueprint/l1-data.json` (R), `dashboard/blueprint/l1-positions.json` (R)
<- `dashboard.js::showView('blueprint')`, `/api/repo/<name>/blueprint` endpoint
! **Repo scoping (r2 whiteboard finding 2 pin — DO NOT REGRESS)**: the endpoint's Gator-source-repo detection uses on-disk artifact discovery — is `<repo_path>/src/gator_command/scripts/dashboard/blueprint/l1-data.json` present? If yes, return the shipped payload. If no, return `{level, status:"unavailable", reason:"release-b-pending", message:...}` and let the frontend render an information card. **Never fall back to the shipped Gator dataset when the active repo isn't the Gator source** — rendering Gator's charter map under another repo's name teaches users knowingly-wrong data at the per-repo Knowledge seam, which is the exact failure mode the r2 plan revision fixed. Pinned by `tests/test_blueprint_view.py::TestBlueprintEndpointNonGatorRepo`.
! **`status: "unavailable"` overloads two semantically-different conditions** (2026-08-30 post-Release-A whiteboard finding). `reason: "release-b-pending"` is the intentional gate — informational empty-state, "Blueprints for this repo aren't available yet" copy. `reason: "shipped-data-unreadable"` (and any future degradation reason like `parser-error` in Release B+) is a REAL failure — must render as error-state with operator-actionable copy, NOT as a "Release B ships it" teaser (which would falsely promise a fix that reinstalling the current CLI actually needs). Frontend `views/blueprint.js` branches on `reason`; endpoint MUST carry a distinct `reason` and a self-contained `message` field for each condition. Pinned by `tests/test_blueprint_view.py::TestBlueprintEndpointShippedDataUnreadable`.
! **Single-slot invariant** (r2 whiteboard finding 1 pin): every view — including `blueprint` — renders into the shared `#view-slot` at `dashboard.html`. Views register as plain callables `window.GatorViews.<name> = function (data, container, ...)` (see `views/repo.js:521`). There is no `{init, render, cleanup}` object shape and no per-view slot; do not invent one.
! Non-1 level returns HTTP 501 with `{error, reason:"release-b-plus"}`. Release B ships parser-derived L1 for any gatorized repo + can add `level=2..4` handling. Release C+ extends the frontend's rendering path (tooltips, edge-type distinction, snapshot integration).
! Honesty framing: subtitle reads "Level 1: charter map (experimental)" so users see the surface without pretending it's more precise than it is (mixed-type edges, hand-curated Release A data). Codex sketch's "important product rule."
! **Canvas vs stage split** (v2.11.1 hardening): `bp-canvas` is a responsive scrollable frame (`flex: 1 1 auto; min-width: 0; overflow: auto`) and `bp-stage` is the inner fixed-dimension container that carries the authored `width`/`height` from the payload's `canvas` field. Nodes and SVG live inside `bp-stage`; the frame around it grows/shrinks with the available viewport width and scrolls internally when the stage exceeds it. Do NOT put fixed pixel dimensions on `bp-canvas` — pre-fix, that pinned the frame at 1180×880 (the vault-HTML authored size) and pushed the detail panel off-screen at normal browser zoom on <1500px viewports.

---

## Architecture Rule

**Business logic stays in CLI scripts. The dashboard is a thin renderer over JSON outputs.**

This rule is non-negotiable. If you find yourself computing governance state in `gator-dashboard.py` or in any JS file, stop and move that logic to the appropriate CLI script.

Health status in `fleet.js` is derived from `hooks_installed` (fleet-report) and `severity` (drift) — both are explicit governance states produced by CLI scripts. No thresholds, no heuristics in the frontend.

Charter coverage % in `repo.js` comes directly from `gator-repo-status.py`'s `charter_coverage_pct` field — computed from `Covers:` declarations by the CLI script, not re-computed in JS.

## Connections

-> [scripts-fleet-intelligence](scripts-fleet-intelligence.md) — gator-repo-status.py (Tier 2 data), gator-fleet-report.py, gator-drift.py, gator-audit.py (Tier 1 data)
-> [scripts-core-library](scripts-core-library.md) — get_version, sys.executable pattern
-> [Index](INDEX.md)
