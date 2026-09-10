# Charter: Dashboard

**Covers**: `src/gator_command/scripts/gator-dashboard.py`, `src/gator_command/scripts/dashboard/helpers.py`, `src/gator_command/scripts/dashboard/updates.py`, `src/gator_command/scripts/dashboard/snapshot.py`, `src/gator_command/scripts/dashboard/data.py`, `src/gator_command/scripts/dashboard/content_policy.py`, `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.css`, `src/gator_command/scripts/dashboard/dashboard.js`, `src/gator_command/scripts/dashboard/views/fleet.js`, `src/gator_command/scripts/dashboard/views/history.js`, `src/gator_command/scripts/dashboard/views/audit.js`, `src/gator_command/scripts/dashboard/views/repo.js`, `src/gator_command/scripts/dashboard/views/updates.js`, `src/gator_command/scripts/dashboard/views/settings.js`

## Owns

The Gator governance dashboard — a local HTTP server plus browser frontend that renders fleet governance health from CLI JSON outputs:

- `gator-dashboard.py` owns the HTTP server, startup globals, settings management, and browser launch. It is a **thin renderer** — no governance logic lives here. Dual-mode architecture: Repo mode (default) shows simplified repo list and settings; Command Post mode shows full fleet/audit surface. Mode stored in gitignored `dashboard-settings.json`.
- `dashboard/helpers.py` owns shared constants (`SCRIPTS_DIR`, `DASHBOARD_DIR`, `COMMAND_POST_ROOT`) and utility functions (`run_json`, `run_text`, `git_run`) used by both `gator-dashboard.py` and extracted dashboard modules. Prevents circular imports between modules.
- `dashboard/updates.py` owns self-update operations for the gator-command install via pipx: `check_for_updates` (compares the installed version to PyPI latest — read-only), `upgrade_and_restart` (spawns a detached helper that runs `pipx upgrade gator-command` then relaunches the dashboard), `restart_server` (process restart via os.execv).
- `dashboard/snapshot.py` owns self-contained offline HTML generation (`build_snapshot`). Reads dashboard assets, inlines CSS and JS, embeds Tier 1 data as `window.DASHBOARD_DATA`. Uses lambda replacement in `re.sub` to avoid backslash misinterpretation from JavaScript content.
- `dashboard/content_policy.py` (**B1 Slice 1, v2.13.0**) owns the shared content-transport policy consumed by every file-serving endpoint: allowlist extensions (`_ALLOWED_TEXT_EXTS_SOURCE`, `_ALLOWED_TEXT_EXTS_GOVERNANCE`, `_ALLOWED_RAW_ASSET_EXTS`), denylist constants (`_DENIED_DIR_SEGMENTS`, `_DENIED_HIDDEN_PREFIXES`, `_DENIED_BASENAME_SUFFIXES`, `_DENIED_EXACT_BASENAMES` — all pre-`casefold`ed for fold-once comparison), `_MIME_MAP` (asserted at import-time to cover every allowlist entry — no `application/octet-stream` fallback for allowed extensions), the `_text_exts_for(namespace_root)` helper, and the E1 canonical `_serialize_listing_entry` used by both live and historical `/files` responses. This module is pure policy: no I/O, no subprocess, no branching on runtime state — just constants and predicates. Consumers (walker, `is_browsable`, response handlers) import from here so discovery and serving agree by construction.
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
Routes incoming HTTP requests. **v2.13.0 B1 Slice 2 restructure**: the four content-transport endpoints (`/files`, `/file/`, `/raw/`, `/history/<file>`) are now dispatched via a parse-once table at the top of the method — `_parse_request(self)` runs EXACTLY ONCE, then `req.endpoint in {"files","file","raw","history"}` selects the corresponding `_handle_X(req)` method. Legacy branches below the dispatch continue to read `path` and `self.path` unchanged.
- **Parse-once dispatch (top of body)** — `_parse_request(self)` → `_dispatch_parse_error(perr)` on failure OR handler dispatch on `req.endpoint in {"files","file","raw","history"}`. `req.endpoint == "other"` falls through to legacy branches.
- `GET /` / `/index.html` → `dashboard.html` served via `_send_dashboard_html()` (with debug meta injection when enabled)
- `GET /api/__gator_debug/registry_state` → live `_REGISTRY_REPOS` JSON, gated on `GATOR_DASHBOARD_DEBUG=1` (404 when unset). Read-only. See `_send_dashboard_html()` and TRIPWIRE (debug seam) below.
- `GET /api/data` → `fast_data` JSON (Tier 1, or standalone payload)
- `GET /api/refresh` → starts background Tier 1 re-collection, returns `{"status":"refreshing"}`
- `GET /api/audit/sessions` → `_handle_audit_sessions()` (Enterprise-only lazy aggregation)
- `GET /api/repo/<name>/history` (repo-scope, no logical path) → legacy 50-commit list from `_get_repo_history()`
- `GET /api/repo/<name>/search?q=...` → `_search_repo_files()`
- `GET /api/repo/<name>/check` → dry-run gator-update JSON
- `GET /api/repo/<name>/commits` → `git log --format=%H%n%h%n%ai%n%s -50`
- `GET /api/repo/<name>/files[?version=<sha>]` → **`_handle_files(req)`** (Slice 2). Live path uses `_iter_scanner_files` + `_contained_repo_path` + `is_browsable`; historical path uses `git ls-tree` + `_reparse_ls_tree_entry`. Both mint entries via `_serialize_listing_entry` (errata E1 single-source wire schema).
- `GET /api/repo/<name>/file/<logical>[?version=<sha>]` → **`_handle_file(req)`** (Slice 2). JSON envelope always — success and error. `content_type` field advertises `text/plain` or `image/svg+xml`.
- `GET /api/repo/<name>/raw/<logical>[?version=<sha>]` → **`_handle_raw(req)`** (Slice 2). Bytes response via `apply_response_headers`; errors via `_raw_error_from_req` → `_raw_error_direct` (no `send_error` delegation). **v2.13.0 B2 Slice 1**: when the resolved MIME is `text/html*`, an additional `Content-Security-Policy` header (`_B2_CSP_EMBEDDED` or `_B2_CSP_EXTERNAL` — selected by request `Sec-Fetch-Dest` == `iframe`) and unconditional `Vary: Sec-Fetch-Dest` are emitted via the dedicated `apply_html_csp_headers` seam. `apply_response_headers` stays byte-exact preserved from B1.
- `GET /api/repo/<name>/history/<logical>` → **`_handle_history(req)`** (Slice 2). `?version=` REJECTED (400) — `/history/<file>` has one contract. Namespace containment via `_contained_namespace_root(for_history_only=True)` so deleted files still return their commits.
- `GET /api/updates/check` → PyPI update check
- `GET /api/repo/<name>` (Tier 2 fallback) → runs `gator-repo-status --path <resolved_path>` (lazy). Resolves name→path from registry for standalone compatibility.
- `GET /api/repos/discover` → `_handle_repo_discover()`
- `GET /<any>` → static file from `dashboard/` via `_send_file()`. MIME map covers `.html`, `.css`, `.js`, `.jpg`, `.jpeg`, `.png`, `.svg`; unknown extensions fall back to `application/octet-stream`.
Filesystem: `dashboard/` (R), subprocess for Tier 2 + B1 handlers
! Tier 2 timeout is 30s per repo. On timeout or error, returns `{"error":"..."}` — the Repo view JS handles the degraded state.
! **Parse-once TRIPWIRE (B1, v2.13.0)**: `_parse_request` runs EXACTLY ONCE per request from the top of `do_GET`. B1-owned handlers (`_handle_files`, `_handle_file`, `_handle_raw`, `_handle_history`) MUST NOT invoke `_parse_request(` or read `self.path` — they receive `req` as an argument. A source grep for `_parse_request(` or `self.path` inside these four methods is a contract violation.
! **Transport-headers TRIPWIRE (B1, v2.13.0)**: every B1-owned response (raw or JSON, success or error) carries `X-Content-Type-Options: nosniff` unconditionally. JSON responses use exact `Content-Type: application/json; charset=utf-8` via `_send_json`. Any response that consumed `?version=` carries `Cache-Control: no-store` — via `_send_json(cache_control="no-store")`, `_send_json_error(cache_control="no-store")`, `_raw_error_direct(..., version_present=True)`, or `apply_response_headers(cache_control="no-store")`. `/file` errors ALWAYS use `_send_json_error`; `/raw` errors ALWAYS use `_raw_error_from_req` — NEVER `send_error` (which would emit HTML with no cache header and no nosniff).
! **Discovery-serving symmetry TRIPWIRE (B1, v2.13.0)**: every `/files` entry — live OR historical — MUST round-trip to a 200 via `/file/<path>` or `/raw/<path>`. Live scanner passes each candidate through `_canonical_logical_for` → `parse_logical_path` → `is_browsable` → `_contained_repo_path`; historical path uses `_reparse_ls_tree_entry` (the same `parse_logical_path` + `is_browsable` predicate). If either fails, the entry is silently omitted — never listed. Reparse points (Windows junctions, mount points, symlinks) are rejected before descent by `_iter_scanner_files`; the belt-and-suspenders `_contained_repo_path` runs on every survivor.
! **Governance-root aliasing TRIPWIRE (B1, v2.13.0)**: `/file/source/.gator/mission.md` and `/file/source/gator-command/README.md` MUST return 404. `is_browsable` (namespace_root == "" case) rejects `.gator/` and `gator-command/` top-level segments; `_iter_scanner_files` prunes the same segments before descent. `.gator/` and `gator-command/` documents have EXACTLY ONE canonical URL — the implicit `.gator/` form for governance, `gator-command/…` for the secondary namespace, `source/…` for repo code only.
! **Historical symmetry TRIPWIRE (B1, v2.13.0)**: `/files?version=<sha>` iterates `_HISTORICAL_NAMESPACES = (".gator", "gator-command", "")`. Each raw `git ls-tree -r --name-only` entry goes through `_reparse_ls_tree_entry(entry, ns)` which composes the canonical logical path via `_ns_prefix_for(ns)` and re-parses through `parse_logical_path` + `is_browsable`. A Git tree cannot list a path that the matching `/file?version=` or `/raw?version=` would reject.
! **Platform-symmetry TRIPWIRE (B1 Slice 3, v2.13.0)**: parser rejections on POSIX-legal-but-Win32-illegal filenames MUST return **400** from `/file/source/<name>` — the split between 400 (parser said no) and 404 (target absent) matters. Windows can't create these names natively, so the POSIX pins in `test_content_transport_slice3.py` exercise them on Linux/macOS: `source/CON.txt`, `source/foo:bar.py`, `source/name.py.`, control-char names. Windows-only pin creates a directory junction into `.gator/` via `mklink /J` and asserts NEITHER the junction NOR its descendants appear in `/files` — `_is_reparse_point` rejects reparse-tag directories before descent because `rglob`/`is_symlink()` silently traverses junctions on Windows.
! **In-repo reparse-point alias TRIPWIRE (2026-09-09 Codex F1)**: `_contained_repo_path` walks the UNRESOLVED path components from the namespace base to the target, rejecting any component that is a reparse point (Windows junction, mount point, POSIX symlink, other reparse tag) via `_is_reparse_point`. This closes a policy alias the two-resolve containment check alone would miss: a symlink like `<repo>/source/public → <repo>/.gator/sessions/_active` stays INSIDE the repo, so the resolved-target containment check passes; the walker was already reject-all-reparse on discovery, but a GUESSED direct URL for the alias would authorize via `is_browsable("", "public/token.json", "raw")` (`.json` is allowed source-text) and the resolved target would leak protected content. The unresolved-component walk catches the alias BEFORE resolve. Live-request TRIPWIRE: every `_contained_repo_path` call MUST walk the unresolved components and reject on the first `_is_reparse_point` hit. Pinned by `test_raw_rejects_in_repo_junction_alias` (Windows) and `test_raw_rejects_in_repo_symlink_alias` + `test_file_rejects_in_repo_symlink_alias` (POSIX).
! **Python 3.9 compat TRIPWIRE for `_is_reparse_point` (2026-09-09 Codex F1 re-review)**: `pyproject.toml` declares `requires-python = ">=3.9"`. `pathlib.Path.stat(follow_symlinks=)` was added in Python 3.10 — calling it on a `Path` under 3.9 raises `TypeError` (not caught by the surrounding `except OSError` clause), which would crash every live `/file`, `/raw`, and `/files` handler on the declared floor. The fix: `_is_reparse_point` gates the DirEntry-native `entry.stat(follow_symlinks=False)` behind `isinstance(entry_or_path, os.DirEntry)` (DirEntry.stat has that kwarg since 3.6), and routes `pathlib.Path` / str inputs through `os.stat(os.fspath(x), follow_symlinks=False)` (a 3.3+ API). Pinned by two source-grep + functional pins: `test_reparse_check_uses_python_3_9_compatible_stat` (source-grep — asserts the `isinstance(..., os.DirEntry)` gate exists) and `test_reparse_check_uses_os_stat_for_path_inputs` (functional — records `os.stat` calls during a `_is_reparse_point(Path)` invocation and asserts the 3.3+ `os.stat(..., follow_symlinks=False)` shape was used, proving the Path branch does not depend on the 3.10+ kwarg).
! **Error-taxonomy TRIPWIRE (2026-09-09 Codex F3)**: live-read handlers MUST catch `FileNotFoundError` and `PermissionError` before the general `OSError` branch and return **404** (not 500 with the exception text). A concurrently-removed or unreadable target would otherwise be distinguishable from the ordinary 404 path — a permission/existence oracle. Applies to both `_handle_file` (JSON envelope 404) and `_handle_raw` (raw HTML 404 via `_raw_error_from_req`). Order matters: `PermissionError` is an `OSError` subclass, so a bare `OSError` first would swallow the 404 taxonomy. Deterministically pinned by cross-platform in-process tests that inject a faulty target through the `_contained_repo_path` seam (Mock with `is_file() → True`, `read_bytes()` raising the target exception): `test_file_permission_error_branch_returns_404`, `test_file_file_not_found_branch_returns_404`, `test_file_general_oserror_stays_500`, `test_raw_permission_error_branch_returns_404`, `test_raw_file_not_found_branch_returns_404`, `test_raw_general_oserror_stays_500` — these hit the actual `except` branches on ANY platform, ANY Python version (filesystem-state-based pins cannot reach `FileNotFoundError` at read time because containment resolve catches it first, and POSIX `chmod 0` can be bypassed by a privileged reader; the in-process pins avoid both limitations). Supplementary POSIX-only functional pins `test_file_unreadable_target_returns_404_on_posix` / `test_raw_unreadable_target_returns_404_on_posix` (`chmod 0` pattern) and containment-path pins `test_{file,raw}_missing_target_returns_404_via_containment` remain as belt-and-suspenders coverage. `test_read_exception_clause_names_both_error_classes` source-greps the order-matters invariant.
! **Uniform `no-store` on version-consuming responses TRIPWIRE (2026-09-09 Codex F2 tightening)**: EVERY response that consumed a `version` key — including contract-shape rejections like `/history/<file>?version=…` — carries `Cache-Control: no-store`. The `parse_qs` normalization at parser step 0.5 catches both literal `version` and percent-encoded `%76ersion` spellings, so the flag is set correctly BEFORE the handler decides whether to reject. Pinned by `test_history_rejects_version_key` (literal) and `test_history_rejects_percent_encoded_version_key` (percent-encoded).
! **B2 CSP seam TRIPWIRE (Slice 1, v2.13.0, 2026-09-10)**: B2's CSP headers are emitted ONLY via `apply_html_csp_headers(handler, *, external)`. This helper is called ONLY from `_handle_raw` when the resolved MIME starts with `text/html`, AFTER `apply_response_headers` and BEFORE `end_headers`. `apply_response_headers` MUST stay byte-exact identical to its B1 shape (the four B1 headers Content-Type, Content-Length, `X-Content-Type-Options: nosniff`, and optional `Cache-Control`). B2 is ADDITIVE-ONLY on top of B1's response header set; it does not modify `apply_response_headers`, `_send_json`, `_send_json_error`, or any of the raw-error helpers. The single seam design keeps B1's transport surface (three-round Codex-reviewed) byte-frozen, isolates B2's audit surface to one function + one conditional in `_handle_raw`, and makes the coordination point between B1 and B2 review-visible. Widening the seam requires an explicit security decision. Pinned by Slice 3 `test_apply_response_headers_unchanged_by_b2` (source-grep byte-diff guard) and by the CSP-header-emission integration pins.
! **B2 `Sec-Fetch-Dest` context routing TRIPWIRE (Slice 1, v2.13.0)**: the switch between the embedded CSP (`_B2_CSP_EMBEDDED`) and the external CSP (`_B2_CSP_EXTERNAL`, with leading `sandbox allow-scripts;`) is driven by the request's `Sec-Fetch-Dest` header. Value `iframe` → embedded; any other value OR the header being absent → external (safer default per r1 §3.2; a non-browser client such as curl gets the sandbox header rather than a null-origin-less top-level document). `apply_html_csp_headers` emits `Vary: Sec-Fetch-Dest` UNCONDITIONALLY on every HTML response — intermediaries cache based on the response Vary contract, not the request shape, so omitting it on the fallback response would let a cached fallback be served later to an iframe-context request and vice versa. Pinned by Slice 3 `test_html_response_vary_header` (embedded + external both assert the header) and `test_html_response_missing_sec_fetch_dest_gets_external_csp` (curl-shape fallback → external CSP).
! **B2 CSP-`'unsafe-eval'` non-permission TRIPWIRE (Slice 1, v2.13.0 — r14 §M1 + r6 §M1 audit contract)**: `_B2_CSP_DIRECTIVES` in `gator-dashboard.py` sets `script-src 'unsafe-inline'` — NOT `'unsafe-inline' 'unsafe-eval'`. The `'unsafe-eval'` gate remains closed. Shipped HTML blueprints MUST NOT contain `Function(...)`, `eval(...)`, or string-valued `setTimeout`/`setInterval`/`setImmediate`/Wasm-compile calls; the fast-matrix audit `tests/test_shipped_template_audit.py::test_no_shipped_template_uses_dynamic_code_execution` walks every file at `.gator/blueprints/*.html` and `src/gator_command/templates/gator-starter/blueprints/*.html` for the three-pattern set (`\bFunction\s*\(`, `\beval\s*\(`, `\bset(?:Timeout|Interval|Immediate)\s*\(\s*['"]`). `document.write(...)` is NOT audited — it belongs to the `'unsafe-inline'` policy family, not the `'unsafe-eval'` gate; adding it here would mislabel the guarded gate. Indirect-eval bypasses (`(0, eval)`, `[]["constructor"]…`, `Reflect.apply(Function, …)`, aliased identifiers) are out of scope; the shipped-template corpus is small and editorially controlled — code review is the intended catch. The regex-coverage self-test `test_dynamic_code_regex_matches_all_documented_patterns` pins the pattern shape (12 positive + 4 negative fixtures); `test_out_of_scope_bypasses_documented` pins the out-of-scope inventory so future contributors adding a bypass family also update the audit prose.
! **B2 CSP-L3 directive-name TRIPWIRE (Slice 1, v2.13.0 — r14 taxonomy)**: assertions on `effectiveDirective` MUST match the directive defined by the applicable CSP algorithm, per violation type:
  - **Element/attribute checks** (`<link>`, `<style>`, `<script>` elements, inline styles/scripts): report specific `-elem`/`-attr` directives (`style-src-elem`, `style-src-attr`, `script-src-elem`, `script-src-attr`). Fallback policy lookup does not change the reported name — a style request always reports `style-src-elem`, regardless of whether the enforcing policy came from `style-src-elem`, `style-src`, or `default-src`.
  - **Fetch/resource-load checks** (`<img>`, `<font>`, `<audio>`, `<video>`, `fetch()`, XHR, EventSource, `<form action>`): report their specific name (`img-src`, `font-src`, `media-src`, `connect-src`, `form-action`).
  - **String-compilation and Wasm-compilation checks** — JS-eval sinks (`eval()`, `Function(...)`, string-valued `setTimeout`/`setInterval`/`setImmediate`) and Wasm sinks (`new WebAssembly.Module(bytes)`, `WebAssembly.compile(bytes)`, `WebAssembly.compileStreaming(response)`, `WebAssembly.instantiate(bytes, imports)`, `WebAssembly.instantiateStreaming(response, imports)` — `instantiate` on a pre-compiled `WebAssembly.Module` is NOT a compilation sink and is not blocked): `effectiveDirective` and `violatedDirective` both report `script-src`. To distinguish JS-eval from Wasm-eval in an assertion, read `blockedURI`: `'eval'` for JS, `'wasm-eval'` for Wasm. Never assert `effectiveDirective == 'wasm-eval'` — that value never appears in the directive field.
  Rule: match the directive the applicable CSP algorithm defines — don't reason from policy lookup. References: [W3C CSP Level 3 §6.8 Directive Algorithms](https://www.w3.org/TR/CSP3/#directive-algorithms), [§4.4.1 String Compilation](https://www.w3.org/TR/CSP3/#can-compile-strings), [§4.5.1 WebAssembly Compilation](https://www.w3.org/TR/CSP3/#can-compile-wasm), [§6.1.10 script-src](https://www.w3.org/TR/CSP3/#directive-script-src).

### _send_dashboard_html(self)
File: `src/gator_command/scripts/gator-dashboard.py`
Peer of `_send_file` that serves `dashboard.html` with optional debug-meta injection. Reads the HTML as text, checks `os.environ.get("GATOR_DASHBOARD_DEBUG")` per request; when `"1"`, injects `<meta name="gator-debug" content="1">` into `<head>` via a single `str.replace("</head>", ..., 1)`. Encodes to UTF-8 and writes with `Content-Type: text/html; charset=utf-8`. Catches `ConnectionAbortedError` / `ConnectionResetError` / `BrokenPipeError` on write to match `_send_file`.
Filesystem: `dashboard/dashboard.html` (R)
<- `do_GET()` root route
! **Debug seam TRIPWIRE** (v2.13.0): the env-var check is PER-REQUEST, not startup-cached. This is load-bearing — the test harness selects debug on/off by setting `GATOR_DASHBOARD_DEBUG` in each child's spawn env, and a startup cache would freeze it. In production the env var is absent and no meta is injected; the `<meta name="gator-debug">` gate in `dashboard/views/repo.js` then closes `window.__gator_debug`. The endpoint `/api/__gator_debug/registry_state` uses the same env-var gate and returns 404 when unset — the endpoint DOES NOT EXIST in production.

### window.__gator_debug (v2.13.0)
File: `src/gator_command/scripts/dashboard/views/repo.js`
Debug seam on the frontend side of the harness contract. Declared inside the same IIFE as `_treeState` (line 274) so it can read that state without cross-file plumbing. Gated on the presence of `<meta name="gator-debug" content="1">` in the served HTML — the meta tag is injected by `_send_dashboard_html()` only when `GATOR_DASHBOARD_DEBUG=1` is set in the process env. The top-level `window.__gator_debug` object is frozen (no setters, no adding methods, no removing getters). Each getter (currently `sidebar`) BUILDS AND RETURNS A FRESH PLAIN OBJECT per call, populated from `_treeState` (`expandedDirs` as Array, `selectedFile`, `repoName`). The returned snapshot is deliberately NOT frozen — tests spoof-mutate it to prove the getter doesn't hand back a live reference.
<- meta tag injection in `_send_dashboard_html()`
! **Debug seam TRIPWIRE** (v2.13.0): getters MUST build a fresh plain object per call (never hand back a reference to `_treeState` or any of its members). The top-level object is frozen; the snapshots it returns are intentionally mutable so the "snapshot vs live reference" pin can spoof-mutate them. Adding a setter or a mutating method on the top-level object requires explicit review — the harness contract says the browser cannot mutate dashboard state through this seam. Two-side pin: `test_debug_seam_getters_return_snapshots_not_live_refs` proves (a) the getter reflects real `_treeState` (a constant stub would fail this) and (b) mutating the returned snapshot does not affect subsequent calls. In production the meta tag is absent, the `_DEBUG` const is false, and `window.__gator_debug` is `undefined` — pinned by `test_debug_seam_absent_when_env_var_unset`.

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

### HTML file support (v2.4.5, updated v2.13.0 B1)
`.html` and `.htm` files are visible in the Dashboard file browser and served as `text/html`. Applies to `.gator/` scans (filesystem walker AND version ls-tree walker). Source-repo scans included `.html` via the shipped `_SRC_EXT`; **v2.13.0 B1 Slice 1** replaces both extension sets with the shared allowlist in `dashboard/content_policy.py` (`_ALLOWED_TEXT_EXTS_SOURCE`/`_ALLOWED_TEXT_EXTS_GOVERNANCE`/`_ALLOWED_RAW_ASSET_EXTS`); `/raw` now serves ONLY allowlisted extensions and their MIME comes from `_MIME_MAP`. There is NO `application/octet-stream` fallback for allowed extensions at runtime — an import-time assertion in `content_policy` guarantees every allowlist entry has a MIME entry.

Clicks on HTML files route through `loadFile()` in `views/repo.js`, which detects `.html?$` and calls `window.open(rawUrl, "_blank", "noopener")` instead of routing through the markdown renderer. The content pane shows a "Opened X in a new tab" message.
! Auto-load code paths (Docs first-file, Repo default-file pick) MUST skip HTML files — `window.open()` outside a user gesture is popup-blocked. `loadFile()` itself does not know if it was called from a click vs. an auto-load, so the filtering lives at the call sites (docsFiles find, defaultFile pick).
! **v2.13.0 B1 Slice 2**: `/raw/` now supports `?version=<sha>` via `resolve_version_ref` + `git_show_at_ref`. A history-restored HTML click can request the historical bytes; frontend behavior on the click is unchanged (still `window.open(rawUrl, "_blank", "noopener")`).
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
CLI entry point. Args: `--port`, `--no-open`, `--snapshot`, `--repo <name>`. Collects Tier 1 data, binds `HTTPServer`, prints Ready protocol line, opens browser. `--port 0` binds to a kernel-assigned port directly (skipping `find_free_port`, which returns its input value on 0 not the assigned port); non-zero uses `find_free_port(args.port)` scanning 8420–8429. `actual_port = server.server_address[1]` reads the real port back after bind.
Filesystem: none
<- CLI
! Port conflict: non-zero path tries `args.port` through +9, then raises with a clear error. If `--repo` is given, opens browser directly to `/?repo=<name>`.
! **Ready protocol TRIPWIRE** (v2.13.0): prints `Ready on http://127.0.0.1:<port>/` at column 0 (no leading whitespace) AFTER bind and BEFORE `serve_forever`, with `flush=True`. The `127.0.0.1` literal + trailing slash + column-0 shape is a PUBLIC interface consumed by the dashboard-ui test harness and any external tooling that boots the dashboard. Do not indent this line, do not swap `127.0.0.1` for `localhost`, do not drop the trailing slash. Human-oriented lines (`  Ctrl+C to stop`) keep their 2-space indent — the Ready line's shape is intentionally distinct.
! **`--no-open --repo NAME` visibility** (v2.13.0): when `args.repo` is set, print an indented `  Open: <base_url>/?repo=<name>` line AFTER the Ready line. Preserves the r6 pre-Plan-A behavior where an operator combining `--no-open` with `--repo` sees the repo-scoped URL they need to paste. The Ready line MUST stay `base_url` (public protocol); the repo-scoped URL is human UX on its own line. Pinned by `test_dashboard_repo_flag_prints_open_url_after_ready`.

### Dashboard UI test harness (Playwright, v2.13.0)
Files: `tests/test_dashboard_ui/_harness.py` (builder + parser + finalizers + seed), `tests/test_dashboard_ui/conftest.py` (pytest fixtures only — kept narrow so it does not shadow `tests/conftest.py` on sys.path), `tests/test_dashboard_ui/test_harness.py` (§8 pins), `tests/test_dashboard_ui/__init__.py` (package marker so relative imports and per-directory conftest scoping work), `tests/test_dashboard_module_import.py` (py3.9 dashboard-import pin owned by the `fast` matrix).
Playwright + pytest boot fixture for the dashboard. Every session gets a fresh temporary `HOME` and registry, and a fresh `gator-dashboard.py` process bound to a kernel-assigned port. The fixture spawns `sys.executable gator-dashboard.py --no-open --port 0` DIRECTLY — no CLI wrapper — so kill signals hit the actual server, not a grandchild. `_harness.build_dashboard_fleet(...)` is the single public builder; it parses `Ready on http://127.0.0.1:<port>/` from child stdout via a background reader thread + `queue.Queue.get(timeout=...)`. `_harness.seed_repo(fleet_root, name)` owns the base seed shape and calls two module-level extension hooks — `_harness.seed_content_fixtures(repo)` and `_harness.seed_sidebar_fixtures(repo)`, both currently no-op stubs — before the seed commit. Plan B reassigns `seed_content_fixtures`, Plan C reassigns `seed_sidebar_fixtures` (module-level reassignment because `seed_repo` re-looks-up the names at call time). Session-scoped `dashboard_fleet` yields 2 accessible seeded repos (`alpha`, `beta`) + 15 inaccessible scratch entries (`missing-XX`) plus a URL and a `home` Path. `dashboard_fleet_mutable` is a function-scoped variant. `dashboard_fleet_debug_off` boots without `GATOR_DASHBOARD_DEBUG=1` for the seam-absence pins. `dashboard_module` (session-scoped) uses `spec_from_file_location` to load the hyphenated script under alias `gator_dashboard_test` for unit tests that monkeypatch dashboard internals. `dashboard_fleet_lifecycle_probe` drives the SAME `_harness.build_dashboard_fleet` other fixtures consume, using a `lifecycle_observer` dict seam to expose reader-thread + pipe handles, and asserts thread exit + pipe closure in its own teardown after driving the generator to completion.
Filesystem: parent-side `read_bytes()` + `stat()` of the real `~/.gator/dashboard-repos.json` for opaque fingerprinting only (see registry-isolation TRIPWIRE below); child-side reads/writes limited to the tmp home planted in `HOME`/`USERPROFILE`.
<- pytest collection via `tests/test_dashboard_ui/`
! **Registry-isolation TRIPWIRE** (v2.13.0): the dashboard CHILD MUST NEVER read or write the operator's real `~/.gator/dashboard-repos.json` — the child is prevented structurally by pointing `HOME` / `USERPROFILE` at the fixture's tmp dir before spawn. The PARENT harness MAY open the real file for opaque `read_bytes()` + `stat()` fingerprinting only (write-isolation pin `test_harness_registry_is_isolated_from_real_home`), and MUST NEVER parse its contents, MUST NEVER write. Read-isolation is pinned separately by `test_debug_registry_state_matches_seeded_fleet` (asserts `_REGISTRY_REPOS` = complete planted set, not just includes). Any child-side read is a harness bug.
! Direct-script launch (not a CLI wrapper): `subprocess.Popen([sys.executable, script, ...])`. Pinned by `test_direct_script_launch_owns_server_process`, which asserts `psutil.Process(server_pid).children(recursive=True) == []`. A wrapper would create a grandchild layer that could survive `terminate()`; the plan-A design explicitly avoids it.
! Success-path teardown MUST bounded-join both reader threads and close both pipes after `terminate_and_wait`. Pinned by `test_fixture_teardown_joins_reader_threads_and_closes_pipes` (uses `dashboard_fleet_lifecycle_probe` which drives the SAME public builder every other fixture consumes — a cleanup regression in the public builder fails the pin).
! **Post-Popen setup TRIPWIRE**: `build_dashboard_fleet` MUST enter its `try/finally` immediately after successful `Popen` and BEFORE the first observer write. Queue construction, reader-thread starts, observer population (including the initial `proc`/`stdout`/`stderr` writes — a caller may pass a dict subclass whose `__setitem__` raises), and readiness parsing all live INSIDE the try so any failure in them still reaches the finalizer. Pinned by two companions: `test_builder_reaps_child_when_reader_thread_start_raises` (monkeypatch second `spawn_reader_thread` to raise) and `test_builder_reaps_child_when_observer_setitem_raises` (dict-subclass observer whose `__setitem__` raises on the `stdout` key). Handles are None-initialized and cleanup is conditional on `is not None`.
! **Seed extension seam** (Plans B and C): `seed_repo` calls `seed_content_fixtures` and `seed_sidebar_fixtures` before the seed commit. Both are no-op stubs in `_harness.py`. Plans B and C register their real implementations by REASSIGNING the module-level names (e.g. `import _harness; _harness.seed_content_fixtures = ...` from their fixture-loading module). Do NOT change `seed_repo` to import the extensions from consumer modules — the reassignment pattern keeps `_harness.py` free of upward dependencies on plans that haven't shipped yet.

### B1 URL parser (`_parse_request(handler)`) (B1 Slice 1, v2.13.0; wired in Slice 2)
File: `src/gator_command/scripts/gator-dashboard.py`
Module-scope function. Single URL-parser at the dispatch boundary. Returns `(Request, None)` on success or `(None, ParseError)` on failure. Steps: (0) `raw_path.rstrip("/") or "/"` — errata E2 exact parity with shipped `do_GET` normalization at line 189-194; (0.5) `parse_qs(raw_query, keep_blank_values=True)` — errata E3 catches percent-encoded version keys; (1) raw structural boundaries via `_WELL_FORMED_PCT_RE`, `_ENCODED_SEP_RE`; (2) exact endpoint shape (`files`, `file`, `raw`, `history` are B1-owned; anything else → `endpoint="other"` for legacy pass-through); (3) decode each surviving component once with `unquote(..., errors="strict")`; (4) reject decoded components still containing `%` (double-encode defense). Populates `Request` dataclass on success, `ParseError` (with `response_kind` from safe raw inspection + `version_present` from the parsed query map) on failure.
Filesystem: none
<- `do_GET` (Slice 2 wired the call site — one invocation immediately after the shipped `path` local).
! ALL failure returns go through the local `_fail(status, message)` closure so `response_kind` and `version_present` are populated uniformly — never use a bare tuple return, never mint a `ParseError` inline. Errata E3 REQUIRES `parse_qs` runs BEFORE any path validation so a malformed path with a version key still triggers `Cache-Control: no-store` downstream.
! Runs exactly ONCE per request (the parse-once invariant). B1-owned handlers accept `req` as an argument; touching `handler.path` after this returns or invoking `_parse_request` a second time is a contract violation. Guarded structurally: the four B1 handlers accept `req` and never call `_parse_request`. The plan's proposed runtime counter test was NOT implemented — enforcement is by code review and the structural handler signature.

### B1 logical-path parser (`parse_logical_path(logical)`) (B1 Slice 1, v2.13.0)
File: `src/gator_command/scripts/gator-dashboard.py`
Module-scope function. Takes a decoded URL logical string; returns `LogicalPath(namespace_root, disk_rel, git_rel)` on success or `None` on any reject. Three canonical namespace shapes (`source/…` → `""`; `gator-command/…` → `"gator-command"`; else implicit `.gator` — explicit `.gator/` prefix rejected as ambiguous, all case aliases rejected). Then in order: empty-tail, Win32 drive-relative, backslash, control chars, tilde prefix, empty/dot/dotdot segments, ADS `:` on any segment, Win32 trailing-dot/space on any segment, Windows reserved device on any segment (via `_is_reserved_windows_component` — E5 layered check), cross-platform rooted paths.
Filesystem: none
<- `_handle_files`, `_handle_file`, `_handle_raw`, `_handle_history` (all live), live-scanner emit loop in `_handle_files`, historical `_reparse_ls_tree_entry`.
! Every rejection is silent (returns `None`); the caller is responsible for surfacing 400/404. There is NO existence oracle — a rejected path is indistinguishable from a nonexistent path at the response level.
! Namespace parsing is EXACT-CASE (r3 F1). `Source/…`, `.GATOR/…`, `Gator-Command/…` are all rejected. POSIX namespace roots are case-sensitive and a lenient parser hides input bugs.

### B1 Windows reserved-name check (`_is_reserved_windows_component(candidate)`) (B1 Slice 1, v2.13.0 — errata E5)
File: `src/gator_command/scripts/gator-dashboard.py`
Module-scope function. Two-layer authoritative check for Windows-reserved device names. Layer 1 (PRIMARY): `_WIN_RESERVED_STEMS_EXPLICIT` frozenset lookup on the case-folded stem, with trailing ASCII spaces stripped before the `.split(".", 1)` — errata E5 requires this so `NUL .txt`, `COM1 .md`, `CONIN$ .txt` are caught even when the deprecated stdlib layer is unavailable. Layer 2 (SECONDARY): `PureWindowsPath.is_reserved()` while it still exists (deprecated in Python 3.13, may vanish later). Divergence between the layers (stdlib flags a name the explicit set missed) logs `dashboard.security` `reserved_name_only_in_stdlib` for operator-visible follow-up.
Filesystem: none
<- `parse_logical_path` (called on every segment, both original and trailing-stripped forms).
! Runs UNCONDITIONALLY (not gated on `sys.platform == "win32"`). A Windows-reserved name is refused on any host so a shared cross-platform development fixture cannot smuggle a name that becomes dangerous when the same repo is browsed on Windows.
! `_WIN_RESERVED_STEMS_EXPLICIT` is the PRIMARY production check per r6 durability layering — NOT a test-only fixture. Adding an extension to the allowlist that names a reserved device (unlikely but possible) requires extending this set explicitly.

### B1 response helpers (Slice 1, v2.13.0; wired in Slice 2)
File: `src/gator_command/scripts/gator-dashboard.py`
Four methods on `DashboardHandler`. `_send_json` extended in place to emit `Content-Type: application/json; charset=utf-8`, `X-Content-Type-Options: nosniff`, and `Cache-Control` from a new keyword arg (defaults to shipped `no-cache`). `_send_json_error(status, message, *, cache_control=None)` — JSON envelope error for `/files`, `/file`, `/history/<file>` and every JSON `/api/repo/*` handler. `_raw_error_direct(status, message, version_present)` — concrete self-contained raw error responder for `/raw`; writes status + headers + body ONCE, no delegation to `send_error`, no dependency on any `_html_error_body` helper (which r5 referenced but never defined; r6 F3 removed it). `_raw_error_from_req(status, message, req)` — thin adapter reading `req.version_present`. `_dispatch_parse_error(perr)` — routes ParseError to JSON or raw responder based on `perr.response_kind`, with `Cache-Control: no-store` when `perr.version_present`.
Filesystem: none
<- `do_GET` pre-dispatch error branch (Slice 2), all four B1 handlers (Slice 2).
! `_send_json` extension is BACKWARDS-COMPATIBLE: no existing call passes `cache_control`, so every shipped consumer keeps the pre-B1 `Cache-Control: no-cache` behavior. The charset and nosniff additions are safe hardening applied uniformly.
! `_raw_error_direct` MUST write the response ONCE. Do not add a `send_error` fallback path — `BaseHTTPRequestHandler.send_error` writes its own status line and headers, and a mixed path would send duplicate status blocks or clobber the version-scoped `Cache-Control: no-store` header.
! `_dispatch_parse_error` is the ONLY code that reads `perr.response_kind`; other consumers pass a `Request` (not a `ParseError`) and route errors via `_send_json_error` or `_raw_error_from_req` directly.

### Content-transport policy (B1 Slice 1, v2.13.0; consumed by Slice 2)
File: `src/gator_command/scripts/dashboard/content_policy.py`
Pure policy layer. Owns the allowlist/denylist frozensets, the extension→MIME map, `_text_exts_for(namespace_root)`, and the E1 canonical `_serialize_listing_entry(namespace_root, disk_rel, name, size, mtime=None)` used by both live and historical `/files` responses. Every string constant that participates in policy comparisons is stored pre-`str.casefold()`ed; runtime callers case-fold input once. Governance namespaces (`.gator` + `gator-command`) share the narrower text allowlist; source (`""`) gets the broader code+prose set.
Filesystem: none
<- `gator-dashboard.py` file-serving handlers (`_handle_files`, `_handle_file`, `_handle_raw`, `_handle_history`) live; live-scanner emit loop in `_handle_files`; historical `git ls-tree` re-parse via `_reparse_ls_tree_entry`.
! An import-time assertion guarantees every allowlist extension has a `_MIME_MAP` entry. If a future edit adds an extension to any allowlist without a MIME entry, module import fails immediately — no `application/octet-stream` fallback for allowed extensions is possible at runtime.
! `_serialize_listing_entry` raises `ValueError` on an unknown `namespace_root`. The namespace enum is closed (`""`, `".gator"`, `"gator-command"`) — silently mislabeling would let a governance path masquerade as source across the security boundary. Do NOT add an `else` fallback that guesses a source label.
! The wire schema this serializer emits (`path`, `source`, `dir` — plus `size`, `mtime` when present) MUST match the shipped shape at `gator-dashboard.py:389-419` (live) and `:446-499` (historical). Frontend consumers at `dashboard/views/repo.js:237-267,307-310,798-824` rely on `source == "repo"` for source files and `path` as the URL round-trip key. A schema drift here silently breaks cross-doc search, file open, and dir grouping in the file browser.

### HTML artifact rendering (v2.12.0 onward — no dedicated view)
File: `src/gator_command/scripts/gator-dashboard.py::do_GET` static-file MIME map + `src/gator_command/scripts/dashboard/data.py` file scanner + `src/gator_command/scripts/dashboard/views/repo.js` file browser
HTML artifacts under `.gator/blueprints/` and `.gator/vault/artifacts/` render through the existing v2.4.5 `.html` support — the per-repo file browser lists them and clicking opens in a new tab via `window.open(rawUrl, "_blank", "noopener")`. No dedicated Blueprints sidebar item, no per-format renderer, no backend endpoint owned here. This is the artifact-first architecture ratified in the v2.12.0 HTML-artifact-protocol plan: Dashboard is a thin browser; the intelligence lives in the artifact.
Filesystem: none owned; browser opens `/raw/<path>` served by the static file handler
<- v2.4.5 `.html` file support (repo file browser click-through)
! **v2.11.0's dedicated Blueprints view was retired in v2.12.0** (per the 2026-09-02 artifact-first sketch). The main-sidebar `Blueprints` item, `views/blueprint.js`, `dashboard/blueprint/l1-*.json`, and `/api/repo/<name>/blueprint` endpoint were all deleted. HTML blueprints now discoverable ONLY via the per-repo file browser. Do not reintroduce a dedicated sidebar item or renderer without a strong product reason — the dashboard-artifact-browser sketch's "keep the main navigation lean" line is authoritative for now.
! Rendering is uniform across all `.html` files (blueprint artifact or not) — no format-specific path. Any `.html` in the repo file browser opens the same way.

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
