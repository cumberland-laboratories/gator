# Charter: Dashboard Server

**Covers**: `src/gator_command/scripts/gator-dashboard.py`, `src/gator_command/scripts/gator-kill.py`, `src/gator_command/scripts/dashboard/*.py`

## Owns

- The loopback HTTP server, route parsing, response headers, and process lifecycle.
- Machine-local dashboard registry reads and per-repository resolution.
- Dashboard data adapters, search, history, session lookup, update/gatorize actions, and offline snapshots.
- Content discovery, logical-path parsing, containment, MIME policy, and HTML CSP selection.

## Does Not Own

- Browser rendering and interaction; see [`scripts-dashboard-ui.md`](scripts-dashboard-ui.md).
- Governance calculations; the server delegates to fleet, audit, repo-status, and lifecycle scripts.
- Canonical registry writes; those remain in `gator_core` under [`scripts-core-library.md`](scripts-core-library.md).
- Enterprise control-plane dashboards.

---

### run_json() / run_text() / git_run()
File: src/gator_command/scripts/dashboard/helpers.py
Run sibling scripts and Git with bounded timeouts and normalized results.
<- server and dashboard data modules
-> subprocess
! Dashboard failures become structured unavailable/error payloads; never substitute another repository's data.

### resolve_discovery_roots() / load_registry_repos() / resolve_repo_path()
File: src/gator_command/scripts/dashboard/data.py
Load the machine registry, retain missing paths for cleanup visibility, and resolve a requested repository by its registry identity.
Filesystem: `~/.gator/dashboard-repos.json` (R)
<- startup and repo-scoped endpoints
-> `gator_core.read_dashboard_registry()`
! A repo-scoped endpoint either resolves the requested repo or returns an explicit empty/error state. It never falls back to the current or Gator source repo.

### collect_standalone_data() / inject_repo_keys()
File: src/gator_command/scripts/dashboard/data.py
Build the Tier-1 dashboard payload and attach stable repository keys used by later API calls.
<- startup and refresh
-> fleet/repo-status scripts, session cache key
! Command-post and standalone modes emit the same consumer-facing repository identity fields.

### get_repo_history() / resolve_audit_sessions()
File: src/gator_command/scripts/dashboard/data.py
Read repository-local Git history and session evidence without moving data between repositories.
<- history and audit endpoints
-> Git, session reader/aggregator
! Missing optional session modules degrade the session panel only.

### parse_search_query() / search_repo_files()
File: src/gator_command/scripts/dashboard/data.py
Parse bounded AND/OR search terms and scan allowed repository documents server-side.
<- search endpoint
-> dashboard content policy
! Search uses the same visibility policy as listing and file reads; it is not a bypass around denied paths or extensions.

### resolve_repo_update() / resolve_repo_gatorize()
File: src/gator_command/scripts/dashboard/data.py
Resolve a registered repo and invoke the explicit lifecycle action requested by the browser.
<- authenticated POST routes
-> `gator update`, `gator gatorize`
! Actions are scoped to the selected registered path and return captured output; path/name input never becomes shell syntax.

### parse_logical_path(logical)
File: src/gator_command/scripts/gator-dashboard.py
Converts the URL-visible logical namespace into a validated namespace root plus disk-relative path.
<- request parser, list/file/raw handlers
-> content-policy constants
! Reject encoded separators, traversal, hidden/denied segments, reserved Windows names, trailing dots/spaces, and ambiguous decoding before filesystem access.

### _parse_request(handler)
File: src/gator_command/scripts/gator-dashboard.py
Parses one request into a typed route/request object and classifies malformed input.
<- `DashboardHandler`
-> `parse_logical_path()`
! Parse once. Handlers consume the parsed request rather than reparsing URL text with route-specific rules.

### _contained_repo_path() / _contained_namespace_root() / _is_reparse_point()
File: src/gator_command/scripts/gator-dashboard.py
Resolve live filesystem targets while rejecting escapes and reparse/symlink traversal.
<- live list/file/raw/search paths
-> filesystem
! Validate unresolved path components before final resolution; a logical in-repo path that resolves into denied content is still denied.
! Missing or permission-denied targets return 404 without becoming an existence oracle; unrelated I/O faults remain server errors.

### is_browsable() / _iter_scanner_files() / _serialize_listing_entry()
File: src/gator_command/scripts/gator-dashboard.py
File: src/gator_command/scripts/dashboard/content_policy.py
Apply one extension/path policy to live and historical listings and canonicalize wire entries.
<- list, search, file, and raw endpoints
! Listing and serving use the same predicate. Adding a file type requires coordinated allowlist and MIME-map changes.

### resolve_version_ref() / git_show_at_ref()
File: src/gator_command/scripts/gator-dashboard.py
Resolve an allowed historical Git object and read content without checking out or mutating the repository.
<- versioned history/file/raw endpoints
-> Git object database
! Historical reads enforce the same logical-path and content policy as live reads.

### apply_response_headers() / apply_html_csp_headers()
File: src/gator_command/scripts/gator-dashboard.py
Emit no-store/security headers and the embedded-versus-external CSP for HTML raw responses.
<- response writers
! HTML CSP forbids dynamic-code evaluation. `Vary: Sec-Fetch-Dest` remains present because iframe and external navigation receive different policies.

### _handle_repo_remove()
File: src/gator_command/scripts/gator-dashboard.py
Remove a single registry entry identified by its exact registered path. Registry-only — no filesystem access to the repo directory.
<- `POST /api/repos/remove` with `{"path": "/abs/path"}` in body
-> `gator_core.remove_dashboard_repo()`
! Identity is the resolved registered path, not the display name. Duplicate display names cannot cause multi-entry removal.
! Cache mutation is synchronous: (1) write registry JSON, (2) filter `_REGISTRY_REPOS`, (3) filter `fast_data["repos"]` — all before the success response.
! Test paths must be resolved through `Path.resolve()` so the `os.path.isabs()` validation passes on both Windows and Linux CI.

### DashboardHandler.do_GET() / DashboardHandler.do_POST()
File: src/gator_command/scripts/gator-dashboard.py
Dispatch API, asset, repository content, update, and lifecycle routes.
<- loopback HTTP server
-> typed request handlers and data adapters
! Every POST calls `_check_post_auth()` before mutation and requires `X-Gator-Dashboard: 1`.
! Do not add permissive CORS. The custom header plus unanswered cross-origin preflight is the local anti-CSRF boundary.
! Debug GET routes return 404 unless `GATOR_DASHBOARD_DEBUG=1` is set for the test process.

### build_snapshot(fast_data)
File: src/gator_command/scripts/dashboard/snapshot.py
Inline dashboard assets and Tier-1 data into a self-contained offline HTML document.
<- `--snapshot`
! Use callable regex replacement for JavaScript/CSS bytes so backslashes are not interpreted as replacement escapes.

### check_for_updates() / upgrade_and_restart() / restart_server()
File: src/gator_command/scripts/dashboard/updates.py
Check PyPI, perform an explicit pipx upgrade in a detached helper, and relaunch the dashboard.
<- update API routes
! Checking is read-only. Upgrade happens only after an authenticated explicit POST and must not strand the response process mid-write.

### main()
File: src/gator_command/scripts/gator-dashboard.py
Load registry/settings, collect initial data, bind loopback, optionally open a browser, or emit a snapshot.
<- `gator dashboard`
-> server, data modules, browser UI
! Bind to loopback only. Keep startup usable when individual repositories are missing or malformed.

### gator kill dashboard
File: src/gator_command/scripts/gator-kill.py
Find and terminate Gator-owned dashboard listeners, with port/all/dry-run scoping.
<- `gator kill dashboard`
! Process matching must identify Gator dashboard ownership; never kill an arbitrary process merely because a common port is occupied.

## Before Changing This Module

- Treat URL parsing, containment, response headers, and POST auth as one security boundary.
- Exercise live and historical paths, Windows name rules, reparse points, and missing targets.
- Preserve structured per-repo empty states.
- Run backend dashboard tests plus the Playwright content-transport suite when wire or HTML behavior changes.

## Connections

-> [Dashboard UI](scripts-dashboard-ui.md) - wire-schema and interaction consumer
-> [Core Library](scripts-core-library.md) - registry, preferences, and runtime helpers
-> [Fleet Intelligence](scripts-fleet-intelligence.md) - governance data producers
-> [Session Archaeology](scripts-session-archaeology.md) - session evidence
-> [Repo Lifecycle](scripts-repo-lifecycle.md) - update/gatorize actions
-> [Cross-Cutting](scripts-cross-cutting.md) - shared schemas and path conventions
