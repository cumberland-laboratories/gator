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

### read_welcome_html(name) / WELCOME_DOC_NAMES / WELCOME_DOCS_DIR / _send_welcome_doc(name) / GET /api/welcome/docs/<name>
File: src/gator_command/scripts/dashboard/helpers.py
File: src/gator_command/scripts/gator-dashboard.py
Serve the shipped Gator HTML documents to Welcome, to the repo-independent Docs view (2026-10-13) and to the Loop workspace's Help tab (2026-10-24): the six Welcome topics `gator-overview.html` (named `how-gator-works.html` before 2026-10-11; never released under that name), `what-gator-can-do.html`, `gatorize-a-repo.html`, `start-a-session.html`, `gator-docs.html` and `gator-loop.html` (2026-10-24; `gator-loop.html` is also the Loop Help document), plus the Docs-view documents `charter-formation-process.html` and `charter-schema-v1.html` (`templates/gator-starter/docs/`, which gatorize/update also install into `.gator/docs/` for agents and offline reading). The Docs view reads them from the package through this route, not from the repository; see `scripts-dashboard-ui.md` → `GatorViews.docs`. Each is shown in a Welcome iframe sandboxed exactly `allow-scripts` (see `scripts-dashboard-ui.md`).
Filesystem: `WELCOME_DOCS_DIR / <name>` (R)
<- `DashboardHandler.do_GET()` (`path.startswith(_WELCOME_DOCS_PREFIX)` → `_send_welcome_doc()`), requested by `views/welcome.js`, `views/docs.js` and `views/loop.js` (Help) frames; `build_snapshot()` (`_welcome_docs_for_snapshot()`, all names)
-> `apply_response_headers()` (`text/html; charset=utf-8`, `nosniff`, `Cache-Control: no-cache`) plus `Content-Security-Policy: _B2_CSP_EXTERNAL`
! TRIPWIRE: `WELCOME_DOC_NAMES` is a closed, explicit `frozenset` (ten names since 2026-10-24: the six Welcome topics, the Loop Extras document `gator-loop-extras.html`, and the Docs documents `charter-formation-process.html`, `charter-schema-v1.html` and `code-migrations.html`; never computed from a directory listing). Adding a shipped document means adding its name here; `tests/test_welcome_docs.py` checks that every shipped `.html` is listed. Request input (the path remainder after `/api/welcome/docs/`) is only tested for membership; it never joins onto a filesystem path. Encoded, cased, traversal, extra-segment, `.md`, and unknown names are not members, and the query string is stripped by `do_GET` (an encoded `/` or `\` is already refused with 400 by `_parse_request`). The branch never falls through: a non-member or unreadable file gets a plain-text 404 ("This Welcome document is not available.", `nosniff`), because an iframe shows the body. The route is repository-independent. The old `/api/welcome/how-gator-works` JSON route is gone (default 404).
! The served policy is always `_B2_CSP_EXTERNAL`, not the `/raw` Sec-Fetch-Dest split: the `sandbox allow-scripts` token is a no-op inside the sandboxed iframe and keeps a top-level open opaque-origin. One fixed policy means no `Vary`. `apply_html_csp_headers()` stays `/raw`-only. Each document also carries the Cumberland master's own meta CSP; the two policies intersect.
! **Document content rules (pinned by `tests/test_welcome_docs.py`):** every document is a Cumberland master copy (shared style region byte-identical; page-local rules go after the `CUMBERLAND-NARRATIVE-STYLE:END` marker). Images must be **inline SVG**: the meta and served policies block `<img>`, including `data:` URIs, so a raster mark is traced to a vector and inlined (the overview's Gator mark is a trace of `docs/images/sleek_profile_gator_inverted.png`). **Welcome format** (Architect direction 2026-10-11; `WELCOME_FORMAT` in the test lists the converted documents): no master `doc-head` or Summary; the page opens with its own lead element, then its sections, and ends with the company footer `© 2026 Cumberland Laboratories, Inc.` (the form used in the repository's legal files). `gator-overview.html` opens with the left-aligned `.hero` Gator mark (overview only); `what-gator-can-do.html` opens with a `.lede` sentence, shows an inline-SVG figure (agents → one shared `.gator/` layer → source code), and lists capabilities as `.caps` cards (justified and hyphenated like body paragraphs; `.lede` and `.principle` display lines stay left-aligned), then two `.principle`-led sections: "A home for each system you operate" and "Across a system of repositories" (Figure 2: one agent → four Gatorized repos, each with its own `.gator/`), and last "The Dashboard and the vault" (Figure 3: vault ← agent session → repository, with the read-only Dashboard under both; the vault is **optional**, for files that must never be committed, and is not the normal drafting path). SVG arrowheads are drawn as polygons: the docs test forbids any `url(` reference, including SVG `marker-end`. `gatorize-a-repo.html` opens with a `.lede` (its `.steps` items justified like body paragraphs) and walks Add → Gatorize (⋮ menu) → what Gatorize writes (repo `.gator/`, Git hooks, agent session hooks, `.gitignore`, `~/.gator/`) → first session; it repeats `SESSION_PROMPT`, pinned equal to `welcome.js` by `test_gatorize_page_prompt_matches_dashboard`, so a prompt change must update this page too. `start-a-session.html` is Welcome's first and default tab since 2026-10-15, the page users land on, and opens with `#prompt` (the prompt in `#session-prompt`, wrapped, and the copy button directly under it), then the justified "How a session starts" steps; its copy script and element IDs are unchanged (see `scripts-dashboard-ui.md` → copy protocol). `gator-docs.html` (2026-10-24) opens with a `.lede`, then "What Gator docs are for" (a `.principle` that charters make it possible, and four `.caps` uses: map systems and flows, discuss proposed features with other architects, draw the whole system including infrastructure, and project views for executives). "Examples" shows the request pattern "Create me a Gator doc for …" in an `.ask` card and the request-to-review figure, then seven `.example` cards (`#ex-feature`, `#ex-retry`, `#ex-release`, `#ex-decision`, `#ex-proposal`, `#ex-system`, `#ex-progress`). Each card has an `.ex-label`, an `h3` scenario sentence ("Suppose …": who needs the document and why, set at the imaginary store so "our" in a request never reads as Cumberland Laboratories; Architect direction 2026-10-24), the `.request` line, a realistic inline-SVG visual or table, short prose, and one `.trait` carrying a message about Gator docs (labelled diagrams linked to the source; reviewed and versioned in Git; readable prose; the reason lives with the code; made for working with other architects; drawn from the code, not from memory; easy to share, for example as a Microsoft Teams attachment). Example 6 (`#ex-system`) is a PCI DSS network diagram (16 resources; internet, VPC, public/app/data subnets, PCI zone, separate security account, partner zone; solid arrows for data, dashed for keys, secrets, logs and admin access; an in-SVG legend) inside a `.wide-figure` that scrolls sideways below 860px instead of shrinking the text. Example 7 also has a `.charts` pair of inline-SVG bar charts (failed charges by month with a "new retry logic" marker; work done per goal), single-series in `#0e9aa6` (validated with the dataviz palette script: the page's `--teal-dark` failed its chroma floor), with per-bar `<title>` hover text because the documents run no script. All seven examples take place at an imaginary online store. Example 1 (`#ex-feature`) explains a shipped feature that spans code and infrastructure (product photo uploads: each box tagged CODE or INFRA in words and naming its file, numbered arrows matching a `.steps` list), at the standard of `.gator/blueprints/gator-architecture-overview.html`, the Architect's reference for a Gator doc. "Keep it up to date" gives the request "Is this document up to date? If not, please update it." The page ends with `#style`, "Addendum: Cumberland style HTML communication": every Gator doc uses the Cumberland template built into Gator (`.includes/reference-notes/`), covering reading type, colour coding with a fixed meaning, diagrams drawn into the page, and prose in the style of ASD-STE100 (style only; no compliance claim, per the constitution). It deliberately avoids a taxonomy of document kinds. `gator-loop-extras.html` (2026-10-24) is the Loop workspace's Extras tab (also listed in Docs): a `.lede`, then per-model sections, `#codex` ("Codex (OpenAI)": works well as the Reviewer, then `gator loop codex` steps, the trust-cost callout, and the `/goal` prompt in `pre#codex-goal` with a copy button; the prompt's wait is filled in as `--max-seconds 360`, and only `<token>` stays a placeholder) and `#opus` ("Opus (Anthropic)": works well as the Draftor; joins by pasting the participant prompt, not `/loop-join`, by Architect direction 2026-10-24). It is the second document allowed a script: like `start-a-session.html`, its meta CSP differs from the master's only by `script-src 'unsafe-inline'`, and the script only posts `{type:"gator-loop", v:1, action:"copy-codex-goal"}` to its parent and shows the result (see `scripts-dashboard-ui.md` → Extras copy action). `gator-loop.html` (2026-10-24) is conceptual help: when to use a Loop, the three roles (figure), the planning path and the coding path (figures, `.steps`), the Dashboard tabs and the Architect's controls. It names no CLI command, stage identifier or status vocabulary, because the same document is the Loop Help tab and must not drift with the protocol. Docs-only documents in the same format (not Welcome topics, not served by the Welcome route; shown by the Docs view through `/raw`): `charter-formation-process.html` (Markdown complement `charter-formation-process.md`) and `charter-schema-v1.html` (complement `charter-schema-v1.md`, which `gator-start-up.md` links to). The Markdown complements stay for agents and are not listed in the Docs view. `GATOR_DOCS` in the test covers every shipped document. Page-local classes live after the style-region END marker. Documents not yet converted keep the master structure.

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

### get_repo_history() / _parse_trailer_lines() / _split_description() / resolve_audit_sessions()
File: src/gator_command/scripts/dashboard/data.py
Read repository-local Git history and session evidence without moving data between repositories.
<- history and audit endpoints
-> Git, session reader/aggregator
! Missing optional session modules degrade the session panel only.
! **Commit records (Commits view, 2026-10-19).** `get_repo_history(repo_path, limit)` clamps `limit` to 1–`HISTORY_LIMIT_MAX` (200); a non-integer falls back to 20. It reads `%(trailers:only,unfold)` alongside the existing format.
  - **Fields:** `hash`, `short_hash`, `date`, `author`, `subject`, `body` (unchanged, still including the trailer block), `description`, `trailers`, `agent` and `architect`. All are additive; no existing field changed meaning.
  - **`description`:** `_split_description()` removes only the **final** paragraph, and only when every line of it (after unfolding continuation lines, whitespace-normalised) is one of the trailers Git itself parsed. A prose `Key: value` line is never dropped, and a body without trailers is returned unchanged.
  - **`trailers`:** an ordered list of `{key, value}` (`_parse_trailer_lines()`) for every key starting with `Gator-`, which includes legacy `Gator-PI` and `Gator-Machine-Id`. `Co-Authored-By` and other non-Gator trailers are ignored. The Commits view shows `Gator-Machine-Id` only under "Raw trailers", never in its record (Architect decision 2026-10-19).
  - **`architect`:** falls back to `Gator-PI` when `Gator-Architect` is absent (cross-cutting: readers accept both).
  - Parsing is in Python, not Git's `key_value_separator` option, to avoid a Git version floor.
  - The `/api/repo/<name>/history` route and its heavy-route admission are unchanged.
  - **Pinned by** `tests/test_dashboard_history.py`.

### parse_search_query() / search_documents() / SEARCH_NAMESPACES / SEARCH_EXTS
File: src/gator_command/scripts/dashboard/data.py
Parse bounded AND/OR/phrase search terms and match them against authorized governance documents server-side. Keeps candidates in `SEARCH_NAMESPACES` (`.gator`, `gator-command`) with a case-folded `SEARCH_EXTS` suffix (`.md`, `.json`), reads them in namespace → extension → `normcase` path order, stops after `max_results` (50) matches, then ranks by `match_count`. Each result's `path` is the candidate's canonical logical path.
<- `/api/repo/<name>/search` in `do_GET` (inside `_heavy_work()`), fed by `_iter_live_candidates(repo_path, SEARCH_NAMESPACES)`
-> candidate `target.read_text()`
! Search never discovers paths: its candidates come only from the live-candidate seam, so it applies the listing visibility policy (dot-dirs/files, denied dirs and basenames, `_active`, reparse points) and can only be narrower than listing. `.gator/.includes/**` is therefore not searchable (Architect decision 2026-10-20).
! No existence oracle: a denied, missing or unreadable candidate yields no hit and no error; the route still returns 200.
! `data.py` never imports `gator-dashboard.py`; candidates are duck-typed (`namespace_root`, `disk_rel`, `logical`, `target`).
- **Pinned by** `tests/test_dashboard_ui/test_search_visibility.py`.

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
<- `_contained_repo_path()`: `/file`, `/raw` and other direct-URL paths (live listing uses `_iter_live_candidates()` instead); `_contained_namespace_root()`: `/history`; `_is_reparse_point()`: scanner, seam, and the walk above
-> filesystem
! Validate unresolved path components before final resolution; a logical in-repo path that resolves into denied content is still denied.
! Missing or permission-denied targets return 404 without becoming an existence oracle; unrelated I/O faults remain server errors.

### _iter_live_candidates() / _live_namespace_bases() / _scanner_target() / LiveCandidate
File: src/gator_command/scripts/gator-dashboard.py
One per-request authority for authorized live files: derive the repo root and each namespace root once, walk with the reparse-aware scanner, gate each file's canonical logical path, and prove it with one resolve. Yields `LiveCandidate(namespace_root, disk_rel, logical, entry, target)` in scanner order; no stat, no read.
<- live `/files` (`_handle_files`; `entry.stat()` per candidate, wire schema unchanged); `/search` (`search_documents()` over `SEARCH_NAMESPACES`)
-> `_iter_scanner_files()`, `_canonical_logical_for()`, `parse_logical_path()`, `is_browsable(..., "files")`, `_is_reparse_point()`, `_path_exists()`
! Per-request only: no cache, no cross-request state.
! `_live_namespace_bases()` makes `_contained_repo_path()` step (1)'s checks once per namespace: a non-source namespace root that is a reparse point is skipped (`dashboard.security` warning), an unresolvable root is skipped, and the root must equal or descend from the repo root.
! F2 for scanner-fed paths is **resolve-equality** (Architect decision-1, Option A): `_scanner_target()` returns the strict resolve only if it equals the lexical `base_r / disk_rel`, so any symlink, junction or mount point below the base (even one swapped in after the scan) rejects the candidate. It is valid ONLY for scanner-enumerated paths; direct URLs keep `_contained_repo_path()` and its per-component walk.
! Calls `_iter_scanner_files` through the module global, so the `gated_listing` patch in `tests/test_dashboard_concurrency.py` applies.
- **Pinned by** `tests/test_dashboard_ui/test_live_candidates.py`.

### is_browsable() / _iter_scanner_files() / _serialize_listing_entry()
File: src/gator_command/scripts/gator-dashboard.py
File: src/gator_command/scripts/dashboard/content_policy.py
Apply one extension/path policy to live and historical listings and canonicalize wire entries.
<- `is_browsable()`: `_iter_live_candidates()` (live listing), `_reparse_ls_tree_entry()` (historical listing), file, raw and history endpoints; `_iter_scanner_files()`: `_iter_live_candidates()` only; `_serialize_listing_entry()`: both `/files` branches
! Listing, search and serving use the same predicate (search through the live-candidate seam, then narrowed to `SEARCH_EXTS`). Adding a file type requires coordinated allowlist and MIME-map changes.
- **`HTML_CSP_DIRECTIVES` / `html_csp_meta_policy()` (Welcome HTML documents):** `content_policy.py` holds the one HTML CSP directive string (moved verbatim from `gator-dashboard.py`). `_B2_CSP_DIRECTIVES` aliases it, and `html_csp_meta_policy()` returns it without `frame-ancestors` (ignored in `<meta>`) for the snapshot's Welcome documents. Change the directives here only.
! `_DENIED_EXACT_BASENAMES` covers override internals by their REAL names (#34): `override-request.json` and `override-approved.json` (the v1 hook wrote these undotted), plus the historical dotted aliases `.override-request.json` / `.override-approved.json` / `.override-meta.json` and the retired `.override` bypass. v2 override state lives under `.git/gator-override/`, outside the working tree, so it is never scanned. Pinned by `test_files_never_lists_override_internal` and `test_override_internals_never_served` (both `/file` and `/raw`, 404 — no oracle) in `tests/test_dashboard_ui/test_content_transport_slice2.py`.

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
! The directives come from `content_policy.HTML_CSP_DIRECTIVES` (`_B2_CSP_DIRECTIVES` is an alias); `_B2_CSP_EMBEDDED` / `_B2_CSP_EXTERNAL` header bytes are unchanged and pinned by `tests/test_dashboard_ui/test_html_preview.py`. In-document scripts in shipped HTML (the Welcome Start-a-session copy action) depend on `script-src 'unsafe-inline'`: tightening it breaks them.

### _registry_snapshot() / _registry_publish(records) / _fleet_snapshot() / _fleet_publish(data) / _fleet_without(fleet, resolved_paths) / _fleet_with_repo_config(fleet, repo_name, config) / _STATE_LOCK / _STATE_WRITE_LOCK
File: src/gator_command/scripts/gator-dashboard.py
The single authority for shared Dashboard state (threaded-server plan, checkpoint 1). The registry (`_REGISTRY_REPOS`) and the Fleet object (`DashboardHandler.fast_data`) are published whole and never mutated afterwards. `_registry_snapshot()` returns `tuple(_REGISTRY_REPOS)` and `_fleet_snapshot()` returns the published reference, both under `_STATE_LOCK`. `_registry_publish()` and `_fleet_publish()` rebind the slot under `_STATE_LOCK`, and their callers hold `_STATE_WRITE_LOCK`. `_fleet_without()` and `_fleet_with_repo_config()` are pure builders that return a new dict, with the changed repo entry copied.
<- every registry or Fleet reader (`_adopt_orphaned_loops`, `_resolve_repo_by_key`, the content handlers, the `do_GET` legacy branches, the debug seam, `_handle_repo_discover`, `_find_session_content`, the `do_POST` lifecycle branches, `main()`); writers `_handle_repo_register`, `_handle_repo_remove`, config POST, `/api/refresh` worker, `main()`
! TRIPWIRE: never mutate a published registry record or Fleet object (no `append`, slice assignment, `fast_data[...] =`, or nested `.update`). Build a new value and publish it. Readers take one snapshot at route entry and work from it. A stale snapshot gives an honest error, never a fallback to another repository.
! Lock order: `_STATE_LOCK` is a leaf (reference read or swap only, no I/O). `_STATE_WRITE_LOCK` covers a writer's read-modify-write. Small registry-JSON I/O and `Path.resolve()` are allowed under it. A subprocess, Git, a repository scan, a Loop lock, or `_refresh_lock` are not. Neither is writing an HTTP response: every handler decides its outcome under the lock and sends it after release, including rejections (`_handle_repo_register` 409/500, `_handle_repo_remove` 404). This is pinned by `test_registry_responses_are_sent_outside_the_writer_lock`. Order: write lock, then state lock; never the reverse.
! The slots stay the module global and the class attribute, so tests may still `monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", [...])` or assign `DashboardHandler.fast_data`. The helpers read whatever is bound.
! **Refresh (`GET /api/refresh`) is single-flight.** Admission is one `DashboardHandler._refresh_lock.acquire(blocking=False)` in the request thread; a request never waits on it.
  - The `dashboard-refresh` worker owns the lock and releases it in `finally`. A failed `Thread.start()` releases it and returns 500.
  - The worker collects from a registry snapshot outside every state lock. Under `_STATE_WRITE_LOCK` it then publishes `_fleet_reconciled(data, _registry_snapshot())`, which drops repos removed during the collection, so a refresh never brings back a removed repository.
  - A collection failure is a debug diagnostic, and the old Fleet stays published. Responses are `refreshing` / `already_refreshing`, unchanged.
  - Pinned by `TestRefreshSingleFlight` in `tests/test_dashboard_concurrency.py`.

### _repo_action(repo_path) / _REPO_ACTION_LOCKS / _resolve_action_target(repo_name, registry, fleet) / _still_targeted(path, source) / DashboardHandler._with_repo_action() / _lifecycle_action() / _register_owned() / _remove_owned() / _config_owned() / _topology_owned()
File: src/gator_command/scripts/gator-dashboard.py
Same-repository mutation exclusion (threaded-server plan, checkpoint 2). Register, remove, update, gatorize, config and topology for one resolved path never overlap; different repositories run in parallel.
- `_repo_action` is a context manager over a per-resolved-path `threading.Lock`. The acquire is non-blocking and yields False when busy, and the route then returns 409 `another change is running for this repository`.
- `_resolve_action_target` repeats `data.resolve_repo_update()`'s lookup (registry by name, else an accessible Fleet entry) in the route, so the key is known before any work.
- `_with_repo_action` takes the lock and re-checks with `_still_targeted` against fresh snapshots. If the repository was removed since the route's snapshot, it returns 404 `repo '<name>' not found` with no side effect. Otherwise it runs the body and writes the response while the lock is still held.
- `_lifecycle_action` calls `resolve_repo_update` / `resolve_repo_gatorize` with a one-entry registry holding exactly the locked path, so the subprocess can only touch that repository. With no target, it calls them on the route's snapshots for their usual 400/404 error.
<- `do_POST` register, remove, `/api/repo/<name>/{update,gatorize,config,topology}`
! TRIPWIRE: a same-repository mutation is ordered strictly against remove. It either finishes before the removal, or it is rejected: 409 while one is running, 404 afterwards. No success for a same-path action can be reported after a later remove. Pinned by `TestRemoveVersusSamePath`.
! Lock order: `_repo_action` comes first. `_STATE_WRITE_LOCK` / `_STATE_LOCK` may be taken inside it (register, remove, config publish), never the reverse. `_repo_action` may be held across the update/gatorize subprocess; that is its purpose, and only same-path requests contend.
! Loop routes do not take `_repo_action`. Their authority is the Loop OS locks. Remove is registry-only and never touches `.gator/loops/`.

### _AUDIT_LOCK
File: src/gator_command/scripts/gator-dashboard.py
Serializes `GET /api/audit/sessions` (`_handle_audit_sessions`), because the session aggregator's cache write (`_atomic_write`: unlink, then rename) is not safe for two concurrent writers. The lock is route-local and no other route takes it. The result is computed under the lock, and the response is sent after release.

### _handle_repo_remove()
File: src/gator_command/scripts/gator-dashboard.py
Remove a single registry entry identified by its exact registered path. Registry-only — no filesystem access to the repo directory.
<- `POST /api/repos/remove` with `{"path": "/abs/path"}` in body
-> `gator_core.remove_dashboard_repo()`, `_registry_publish()`, `_fleet_publish(_fleet_without(...))`
! Identity is the resolved registered path, not the display name. Duplicate display names cannot cause multi-entry removal.
! Publication is synchronous and under `_STATE_WRITE_LOCK`: (1) write registry JSON, (2) publish a registry tuple without the path, (3) publish a Fleet copy without it — all before the success response. `_handle_repo_register()` runs its `ensure_dashboard_registry_entry()` read-modify-write and publication under the same lock, so Dashboard registry writes never lose an update. Config POST writes `config.json`, then publishes a `_fleet_with_repo_config()` copy under the lock.
! Test paths must be resolved through `Path.resolve()` so the `os.path.isabs()` validation passes on both Windows and Linux CI.

### _resolve_repo_by_key(repo_key) / _resolve_loop_dir(repo_key, loop_id)
File: src/gator_command/scripts/gator-dashboard.py
Resolve `repo_key` (path-hash) to registered repo path, then validate `loop_id` and return a containment-safe loop directory Path. Single gatekeeper for all loop-file access.
<- loop workspace route handlers
-> `_registry_snapshot()` (one snapshot for both passes), `session_cache_key()` (fallback)
! `loop_id` is user-visible URL input — reject `..`, `/`, `\`, and null bytes before filesystem access.
! Reject reparse points/symlinks on `.gator`, `loops`, and the loop entry using `_is_reparse_point()` (catches POSIX symlinks and Windows junctions). Namespace-root checks run before any loop entry access; loop-entry check split: `is_symlink()` before resolve (catches dangling), `_is_reparse_point()` after existence confirmed (catches junctions).
! Containment is structural: `loops_root_resolved in loop_dir.parents` and `repo_root_resolved in loops_root_resolved.parents` — immune to same-prefix sibling attacks (`loops-escape`).
! List handler skips reparse/symlink entries via `_is_reparse_point()` and refuses to iterate when `.gator` or `loops` is a reparse point.

### _dispatch_loop_get() / _handle_sketch_sources() / _handle_loop_list() / _handle_loop_status() / _handle_loop_events() / _handle_loop_artifact()
File: src/gator_command/scripts/gator-dashboard.py
Route `/api/repo-by-key/<repo_key>/...` GET requests. Dispatches both repo-scoped utility routes (`/sketch-sources`) and loop routes (`/loops/...`). List loops for a repo (sorted by recency, symlinks skipped), return allowlisted session status fields (no tokens, no schema), return the event timeline as a JSON array, serve allowlisted markdown artifacts, or list candidate sketch source files.
<- `do_GET()` via prefix match on `/api/repo-by-key/`
-> `_resolve_repo_by_key()`, `_resolve_loop_dir()`, `loop.session.load_session()`, `loop.events.read_all_events()`
! Read-only. No imports from `submit.py`. No token access. `.tokens.json` and `session.lock` never served.
! **#62:** `/events` passes each event through raw, so a participant submission event's additive `executive_summary` (written by the CLI at submission) reaches the Timeline with no server change, extraction or artifact read. Older events never have it.
! **Sketch sources** (`GET /api/repo-by-key/<key>/sketch-sources`): scans `.gator/artifacts/`, `.gator/threads/`, `.gator/active-threads/` for `.md` files. Returns `{path, name, size, modified}` sorted newest-first. Skips candidate directories that are reparse points/symlinks; excludes hidden files, symlink entries, and reparse-point entries. Uses `_resolve_repo_by_key()` for containment — no user-supplied path component. The `/sketch-sources` route is dispatched inside `_dispatch_loop_get()` before the `/loops` branches.
! Status response uses `_LOOP_STATUS_ALLOWED_KEYS` allowlist — only known-safe fields appear in GET responses. Unknown/future fields are silently dropped.
! **Architect brief (#43):**
  - **Never added to the generic allowlist.** `brief` is never in `_LOOP_STATUS_ALLOWED_KEYS` (pinned), because that set copies values verbatim. Instead `_handle_loop_status` adds `brief = session.brief_status_view(ref, BRIEF_FILENAME)`: a strict, positionally bound `{artifact, sha256, bytes}` or null, with unknown keys such as `content` or `path` dropped. Beside it goes `brief_check = verify_brief(loop_dir, ref, BRIEF_FILENAME)`, with results absent / ok / missing / mismatch / unreadable / invalid_ref / unsafe.
  - **Coding source brief.** `coding_status_view(coding, loop_dir)` adds the same pair for the source brief (`SOURCE_BRIEF_FILENAME`), plus a validated `source_brief_decision` enum.
  - **Never served as content.** Brief content is never in `/status`; it is reachable only through the artifact route, whose allowlist gains `architect-brief.md` and `source-architect-brief.md`.
  - **Join prompt.** `/prompt` appends a pointer line ("An Architect brief exists for this loop: read it first") only when a brief reference exists, and never includes content.
  - **Start.** `POST /loops/start` accepts an optional `brief` string. It is validated before the start lock with `brief_bytes_from_text`; a non-string, NUL, non-UTF-8 or over-32,768-byte brief gets 400. A blank string means no brief. It is passed to `init_loop(brief_text=…)`, and any `ValueError` / `FileNotFoundError` from `init_loop` is now a 400. `init_loop` is atomic, so no partial directory is left.
! **Attention interval (#47 M4):**
  - **Start:** `POST /loops/start` accepts `attention_interval` (preferred) or the legacy `turn_timeout` alias, using the same `_validate_http_turn_timeout` bounds (30..3600, a JSON integer) and default 300. Sending both is a 400. The out-of-range error names the field that was sent.
  - **Status:** for `attention_mode` loops, `_handle_loop_status` adds an explicit `attention` key from `host.attention_status_view(session, loop_dir)`, built field by field and never via the allowlist: `{interval_seconds, turn_started_at, notified_turn, notified, due}`.
    - Malformed primitives become null; a naive timestamp counts as invalid.
    - `notified` is the marker OR a valid matching `architect_attention_due` event, covering the event-before-marker window.
    - `events.jsonl` is read only when the marker is missing and the turn is due, so ordinary polls do no extra reads.
    - Legacy loops have no `attention` key.
    - `host` (M5 P2) is set only when the turn is due and not notified, from `host.probe_host_state(loop_dir)`: a single non-blocking `host.lock` attempt. Held means `attached` (any process, including the Dashboard's own watcher); acquired-and-released means `none`; unopenable means `unknown`. It is null otherwise and never probed on ordinary polls.
  - **Unblock:** `timeout` on an attention loop maps `submit.ATTENTION_TIMEOUT_REFUSAL` (raised in the lock, nothing written) to a 400 with Dashboard wording ("…no participant turn window to change. Unblock without a timeout.").
  - **Prompt:** the `/prompt` join text is pinned free of time language.
  - **List:** `/loops` items gain `attention_notified`, a marker-only check (`attention_notified_turn == turn_started_at`) with no event scan, for the sidebar marker (M5).
! **#55 checkpoint summary.** For a **declared** checkpoint coding loop only, `/loops` items gain `checkpoint_summary: {index, count, findings_round, findings_budget, generation}`.
  - It comes from `loop.session.checkpoint_summary(session)`, copied field by field from validated primitives, as a cheap session read with no artifact, event or Git access.
  - Planning, legacy coding and implicit-manifest items have no `checkpoint_summary`.
  - The item's `round` and `max_rounds` stay for compatibility and are informational for checkpoint loops: `round` may exceed `max_rounds` there, so the sidebar must render the summary instead.
! **Coding-loop start (#43 M2a):** `POST /loops/start` accepts `mode` (`planning` by default, or `coding`).
  - **Coding** requires a string `from_loop`, rejects `sketch_path`, and accepts an optional `source_brief` (`keep` / `drop`) and `brief`. It calls `init_loop(feature, None, …, mode="coding", from_loop=…, brief_text=…, source_brief=…)` under the existing `start.lock` and single-active guard.
  - **The guarded successor is the ONLY source validator:** canonical id, planning mode, `plan_approved`, plan present, Git base, and brief keep/drop integrity, all atomic. Its `ValueError` returns 400 with the message, including the corrupt-source "--source-brief drop" hint.
  - **Other 400s:** an unknown `mode`, a missing or non-string `from_loop`, a bad `source_brief`, or `from_loop` / `source_brief` on a planning start.
  - **The `/loops` list** gains an additive normalized `mode` (`planning` / `coding` / `unknown`) so the UI can offer only approved planning loops.
  - **#56:** each `/loops` item also carries the boolean `mode_legacy` (`"mode" not in session`). Normalization hides the missing-mode case, and the mode badge needs it to show "Planning · legacy". It is computed only from the session key, never from the feature name or artifacts. `/status` is unchanged; it already carries the raw `mode`.
! **#51 planning sources.**
  - **Start:** `POST /loops/start` (planning mode) accepts `plan_path` (Architect-originated draft plan) or `revise_from` (approved planning loop id).
    - Each must be a non-empty string. Both together, either with `mode: coding`, or `revise_from` without `sketch_path` gives 400 with nothing written. `sketch_path` is optional with `plan_path`.
    - `plan_path`, and the sketch of a revision start, are passed as **lexical** absolute paths (`_lexical`, never `resolve()`d), so `init_loop`'s `read_governed_input` still sees any link or alias. `init_loop` is the ONLY content validator, and its `ValueError` / `FileNotFoundError` returns 400 (atomic).
  - **Status (`_handle_loop_status`, planning loops):** explicit `planning_source`, plus `plan_source: {view, check, sketch_present}` or `revision: {source_loop_id, baseline: {view, check}, approval: {view, check}}`.
    - They are built with `session.fixed_artifact_view` / `verify_fixed_artifact` against FIXED names, and are never added via `_LOOP_STATUS_ALLOWED_KEYS`.
    - Coding sessions get none of these keys.
  - **Artifact allowlist:** gains `architect-plan.md`, `revision-baseline-plan.md` and `revision-baseline-approval.md`. Lookalike names are still refused.
  - **`/prompt`:** one pointer line, never content: "This loop revises <id>: read revision-baseline-plan.md and revision-baseline-approval.md first." or "The plan under review is an Architect-originated draft awaiting Reviewer approval (not approved)."
  - **`/loops`:** planning items gain `planning_source` (`invalid` when malformed).
  - **Pinned by:** `tests/test_dashboard_loops.py::TestPlanSources51`.
! **Known pre-existing edge case:** loop ids are the feature plus a second-resolution timestamp, so two starts of the same feature within one second collide (`FileExistsError` in `init_loop`'s `mkdir`, which this route does not catch). Seen in testing; not changed by #43.
! Events endpoint validates `events.jsonl` against symlink/reparse before reading — `is_symlink()` pre-existence, `_is_reparse_point()` post-existence — then returns the raw event timeline via the existing `read_all_events()` reader; missing events file returns an empty array.
! Artifact endpoint uses `_LOOP_ARTIFACT_ALLOWLIST` plus `_LOOP_ARTIFACT_PATTERNS` — only known markdown artifacts are served (sketch, plan, findings, decision docs). Decision artifact patterns are tightened to match production filenames exactly: `decision-request.decision-<N>.round-<R>.md` and `decision-response.decision-<N>.md` (integer-only IDs, no arbitrary segments). `.tokens.json`, `session.json`, `session.lock`, and `events.jsonl` are never served. Served as `text/plain; charset=utf-8`. Reparse/symlink check on the artifact file itself.
! Timeline "View full artifact" links (2026-10-04 follow-on to #45) are browser-only: they use the event's existing `artifact_path` and open the artifact card, which fetches through this route. No server route or field was added, and the timeline itself never requests artifact content.
! Artifact reads must reflect the file on disk at request time — no server-side caching or memoization. `plan.current.md` / `findings.current.md` are rewritten in place by each submission, and the browser's incremental loop view (#38) refetches them with `cache: "no-store"` after event-log changes, relying on each response being current.
! **Failure contract the UI relies on (#44):** any non-2xx `/status` or `/events` response, or an `/events` body without an `events` array, is a *refresh failure*. The browser keeps the last valid workspace and shows "Refresh failed — retrying." It never treats a failure as an empty history. So the server must report errors with a non-2xx status, never as a 200 with an empty or missing `events` array; a genuine no-events loop returns 200 `{"events": []}`. Changing this contract would silently prune event-derived artifact sections in the UI (pinned by `test_events_failure_never_prunes_artifacts`).

### _dispatch_loop_post() / _handle_loop_start() / _handle_loop_prompt()
File: src/gator_command/scripts/gator-dashboard.py
Route `/api/repo-by-key/<repo_key>/loops/...` POST requests. Start a new loop (with host watcher thread) or return participant prompt text.
<- `do_POST()` via prefix match on `/api/repo-by-key/`
-> `_resolve_repo_by_key()`, `_resolve_loop_dir()`, `loop.host.init_loop()`, `loop.host.acquire_start_lock()`, `_ensure_loop_watcher()`, `loop.session.load_session()`, `loop.session.load_tokens()`
! Start acquires `start.lock` cross-process before scanning for active loops — one active loop per repo enforced by on-disk scan, not just the in-process registry.
! `sketch_path` must resolve inside the registered repo root — rejects traversal to external files.
! Prompt endpoint returns only `draftor` or `reviewer` prompts — never `architect`. Response carries `Cache-Control: no-store` on all paths (success and error).
! Terminal loops reject prompt requests with 410.
! Every participant prompt (both roles, planning and coding) opens with the explicit request "Please join the following loop:" before the `gator loop join` block (Architect direction, 2026-10-22). A pasted block of bare loop facts left the receiving agent asking whether it was meant to join. Pinned by `test_prompt_names_explicit_gator_init_start`.
! Every participant prompt ends its fixed block with the explicit-start pointer "New to Gator in this repo? Run `gator init` first; its handoff names GATOR_INIT.md and the loop protocol." (gator-native entry point, 2026-10-08). Native agent files no longer teach "gator loop join", so the prompt must not rely on them. Pinned by `test_prompt_names_explicit_gator_init_start` in `tests/test_dashboard_loop_brief.py`.

### _resolve_architect_token(repo_key, loop_id, cache_control=None) / _handle_loop_pause() / _handle_loop_interject() / _handle_loop_unblock() / _handle_loop_end()
File: src/gator_command/scripts/gator-dashboard.py
Architect control endpoints. Each resolves `loop_dir` via `_resolve_loop_dir()`, reads the architect token from `.tokens.json`, and delegates to the corresponding `submit.py` handler with `loop_dir=loop_dir`. A malformed or non-object token store is a 404 (`tokens unreadable` / `architect token not found`), never an unhandled 500. `cache_control` passes through to error responses (the liveness routes pass `no-store`).
<- `_dispatch_loop_post()` via action suffix matching (`/pause`, `/interject`, `/unblock`, `/end`; `/extend` and `/renotify` have their own entries below)
-> `_resolve_loop_dir()`, `loop.session.load_tokens()`, `loop.submit.handle_pause()`, `loop.submit.handle_interject()`, `loop.submit.handle_unblock()`, `loop.submit.handle_end()`
! Dashboard never acquires the session lock itself — all writes delegate to `submit.py` handlers.
! **Busy (threaded-server plan, checkpoint 2).** `session.lock` is blocking (`session._lock_exclusive`).
  - **The proven boundary:** on Windows, `msvcrt.locking(LK_LOCK)` gives up under contention after about 9–10 s with `OSError(36, "Resource deadlock avoided")`; errno 36 is `EDEADLOCK`, which equals `EDEADLK` on Windows. This was measured on Windows 10 with Python 3.13, and `test_real_windows_session_lock_contention_maps_to_503` pins it end to end by holding the real lock from another handle (Windows-only). POSIX `flock(LOCK_EX)` waits without a timeout, so it never produces this error.
  - **Mapping:** pause, interject, unblock, end, extend and reopen map exactly that errno, plus `EBUSY` from `session.SessionBusyError` (#61: `session.json` stayed in use past its short retry, nothing written; see `scripts-loop.md`), via `_LOOP_LOCK_BUSY_ERRNOS` / `_loop_lock_busy()`, to 503 `{"error": "loop is busy; retry"}`, with nothing written.
  - **Everything else is unchanged.** Any other `OSError` propagates as before (pinned with `EIO` by `test_other_session_lock_errors_are_not_reported_busy`). An `EACCES` is a `PermissionError`, which these routes already map to 409.
  - **If the platform signal changes**, for example a Python version that raises a different errno, the real-contention test fails. Re-measure, then update `_LOOP_LOCK_BUSY_ERRNOS`. Do not widen the mapping to all `OSError`s.
  - Concurrent same-loop requests are still decided by the Loop locks: one valid transition, and an honest 409 or 503 for the other. Pinned by `TestLoopRaces`.
! `_resolve_architect_token()` is the shared gatekeeper — resolves loop_dir and reads the architect token; returns None (with error response sent) on failure.
! Interject requires non-empty message (400 if absent). Pause and end accept optional message/reason.
! Unblock accepts `message` (string, optional), `no_response` (bool, default false), and `timeout` (optional JSON integer 30..3600 via `_validate_http_turn_timeout()`; strings/floats/bools → 400). The response contract (a pending escalation needs a message or explicit `no_response`) is enforced by `submit.handle_unblock()`, not by the endpoint; its `ValueError` maps to 400 with nothing written, `PermissionError` to 409. An ordinary pause unblocks with no response.

### _validate_http_turn_timeout(value) / _validate_http_round_count(value)
File: src/gator_command/scripts/gator-dashboard.py
Wrap `loop.session.validate_turn_timeout()` / `validate_round_count()` for JSON bodies, additionally rejecting strings. Turn timeout: loop start (`turn_timeout`, default 300) and unblock (`timeout`, optional). Round count: extend (`rounds`, required, 1..20). CLI and Dashboard share one range per field.
<- `_handle_loop_start()`, `_handle_loop_unblock()`, `_handle_loop_extend()`
-> `loop.session.validate_turn_timeout()`, `loop.session.validate_round_count()`
! State machine rejections (PermissionError from handlers) returned as 409.

### _handle_loop_extend(repo_key, loop_id, req)
File: src/gator_command/scripts/gator-dashboard.py
POST `/api/repo-by-key/<key>/loops/<id>/extend` (#39). Body: `rounds` (JSON int 1..20 via `_validate_http_round_count()`) and `message` (required non-blank string) — both checked before any write (400). Resolves the architect token, calls `loop.host.extend_loop(token, rounds, message, loop_dir=...)` (start.lock + single-active guard + `handle_extend()` transaction), then `_ensure_loop_watcher(repo_path, loop_id, loop_dir, retry=True)`. Response 200: `{ok, previous_max_rounds, max_rounds, round, watcher: attached|already_hosted|failed, watcher_detail}`.
<- `_dispatch_loop_post()` via action suffix `/extend`
-> `_resolve_architect_token()`, `_validate_http_round_count()`, `loop.host.extend_loop()`, `_ensure_loop_watcher()`, `loop.session.load_session()`
! Error map: `PermissionError` (wrong stage) -> 409; `RuntimeError` (another active loop / start or extension in progress) -> 409; handler `ValueError` -> 400. Every rejection leaves session/events unchanged and attaches no watcher.
! The extension is durable even when `watcher == "failed"`; the response must report that state honestly — never imply timeout enforcement (legacy) or attention recording (attention-mode, #47) resumed. `already_hosted` (in-process thread or another process holds `host.lock`) never starts a second watcher.

### _handle_loop_liveness(repo_key, loop_id) / _handle_loop_renotify(repo_key, loop_id, req) / _resolve_liveness_loop() / _liveness_modules()
File: src/gator_command/scripts/gator-dashboard.py
Architect-only participant-liveness surface (#36).
- **GET `/api/repo-by-key/<key>/loops/<id>/liveness`**: responds with `Cache-Control: no-store`. Its body is `loop.liveness.observer_view()`, an explicit allowlist `{schema: gator-loop-liveness-view-v1, available, degraded, roles: {draftor, reviewer}: {state (connected|stale|released|closed|not_registered), adapter_kind, last_seen_at, pending, last_notification {kind, created_at, created_by, delivered_at, acked_at, expired_reason}, renotify_eligible, renotify_reason_code}, audit: {renotify_count, last_at, last_actor}}`.
  - A GET never writes, not even quarantine; it uses the lock-free `read()`.
  - Degraded responses are 200 with `available: false`: `degraded: "unavailable"` when there is no Git store, `"retry"` when the transient read retries are exhausted. With `available: true`, `degraded` may be `"corrupt"` (the file is left untouched) or `"session_unreadable"` (eligibility false).
  - A loop_id containing `/` falls through to the artifact route.
- **POST `/renotify`** (via `_LOOP_ACTIONS`; anti-CSRF `X-Gator-Dashboard` enforced by `do_POST`):
  - Body `{role: draftor|reviewer, reason?: string}`. The reason is sanitized to 200 printable characters and defaults to "Architect re-notify".
  - Calls `loop.liveness.renotify()`, which appends one `created_by: "architect"` record plus an audit entry under the liveness leaf lock only.
  - Responses: 200 `{ok, role, kind}`; 400 bad role or reason; 404 unknown repo or loop; 409 `{code: terminal|already_acknowledged|not_actionable}`; 429 `{code: rate_limited}` (one per `(repo_key, loop_id, role)` every 10 s; a refusal or failure does not consume the slot); 503 `{code: unavailable}`. All responses carry `no-store`.
-> `_resolve_liveness_loop()` -> `_resolve_architect_token(cache_control="no-store")` + `loop.session.resolve_token()`; `loop.liveness.open_store()/observer_view()/renotify()`, `loop.session.load_session()`
! **Architect authority (deliberate, for BOTH routes):** the GET view and the POST Re-notify go through the standard `_resolve_architect_token()` resolver AND a nonce check that the stored architect token resolves to the `architect` role for this loop, because Re-notify never calls a `handle_*` that would validate it. Missing, malformed or non-object tokens, or a missing architect entry, give 404; a nonce mismatch gives 403. All carry `no-store`, and nothing is written (a denied Re-notify consumes no rate-limit slot). The anti-CSRF header is not role authority. The token is used only inside the resolver: never passed to `renotify()`, returned, or echoed.
! Re-notify is a communication/audit action only: never writes `session.json` or `events.jsonl`, and never changes deadlines or `next_role`.
! Never add liveness data to participant-visible routes (`/status`, `/events`, `/artifact/*`) or to `_LOOP_STATUS_ALLOWED_KEYS`. Never serialize registration ids, seq lists, state keys, adapter labels, or audit reasons.

### _handle_loop_coding_snapshot(repo_key, loop_id) / _handle_loop_reopen(repo_key, loop_id, req) — coding loops (#41)
File: src/gator_command/scripts/gator-dashboard.py
- **GET `/api/repo-by-key/<key>/loops/<id>/snapshot`:** requires Architect authority through the same `_resolve_liveness_loop()` (architect resolver plus nonce check: 404 / 403), and responds with `Cache-Control: no-store`.
  - A planning loop gets 409.
  - The response, `gator-loop-coding-snapshot-v1`, is `{stage, approval_resolution, live}`. `approval_resolution` is the pure `state_machine.resolve_approval()` result against a fresh `gitsnap.snapshot()`, taken with `approved_head` = the approval's `head` (#85), exactly as the CLI does. `live` holds slim facts (`ok`, HEAD, HEAD tree, staged tree, branch, detached, changed count, residue other/loop counts), or `{ok: false, error}`. #67: `live` adds `guidance` (the `gitsnap.error_guidance(error)` text) only when that returns text (`git_permission_denied`); every other failure stays exactly `{ok: false, error}`.
  - Raw path lists are never served. Git trouble shows as `unknown`, never approved.
  - **#85:** Committed survives later commits, and its `commit` is the historical approval commit (the first first-parent successor), not the current HEAD. Neither `live` nor the response ever carries the raw `approval_history` fact.
- **POST `/reopen`** (via `_LOOP_ACTIONS`; anti-CSRF header enforced by `do_POST`). It mirrors `/extend`:
  - it goes through `_resolve_architect_token()`, and a non-blank `message` is required (400);
  - `host.reopen_loop()` errors map to 409 (`PermissionError` / `RuntimeError`) or 400 (`ValueError`);
  - it then calls `_ensure_loop_watcher(retry=True)`.

  The response is `{ok, stage, round, watcher, watcher_detail}`. The reopen stays durable even when `watcher == "failed"`, and the response says so honestly.
- **Status (`_handle_loop_status`):** a coding session's `coding` block is replaced by the slim allowlisted `submit.coding_status_view()`: ids, counts, review verdicts and approval. The raw path lists in the generations are never shipped on the 3 s poll.
  - **#55 additions** (all additive): `generation` (the latest index, or null); per-generation `generation` and `checkpoint_id`; and `checkpoints` (`_checkpoints_view`) for **declared** manifests only (null otherwise): `{source, current, count, items: [{id, index, title, state, base_tree, accepted_tree (null once invalidated), findings_rounds}]}`.
  - The checkpoint title is plain text. A checkpoint's `scope` and `verify` text are **never** projected.
  - There are no route or allowlist changes: generation-named artifacts fit `implementation.round-N.md` / `findings.round-N.md`.
- **Artifact allowlist:** gains `approved-plan.md`, `implementation.current.md`, and `implementation.round-N.md`.
-> `loop.gitsnap.snapshot()`, `loop.state_machine.resolve_approval()`, `loop.submit.split_residue()` / `coding_status_view()`, `loop.host.reopen_loop()`, `_ensure_loop_watcher()`

### _sweep_liveness(repo_path)
File: src/gator_command/scripts/gator-dashboard.py
Startup retention sweep (`loop.liveness.sweep()`), run for each registry repo at the start of `_adopt_orphaned_loops()`. It projects surviving loops (prune / 7-day terminal retention) and deletes sidecar files whose loop directory is gone. It is best-effort: a failure is a debug diagnostic only and never affects adoption.

### _run_watcher() / _ensure_loop_watcher() / _adopt_orphaned_loops() · _LOOP_HOSTS / _HostEntry
File: src/gator_command/scripts/gator-dashboard.py
Server-local host registry tracking watcher threads, held `host.lock` file descriptors, and entry nonces. Startup adoption scans registered repos for orphaned active loops. `_ensure_loop_watcher(repo_path, loop_id, loop_dir, retry=False)` is the **single attach path** for every Dashboard watcher (start, adoption, and #39 extension) and returns `(state, detail)` with `WATCHER_ATTACHED` / `WATCHER_ALREADY_HOSTED` / `WATCHER_FAILED`.
<- server startup, `_handle_loop_start()`, `_handle_loop_extend()` (M5b)
-> `loop.host.watch_loop()`, `loop.host.acquire_host_lock_with_retry()`, `loop.host.release_host_lock()`
! Invariant: never create a watcher thread outside `_ensure_loop_watcher()`. It (1) returns `already_hosted` if this process already has a live thread for the key, (2) acquires `host.lock` — one attempt for start/adoption, the ~3 s `acquire_host_lock_with_retry()` window when `retry=True` — and returns `already_hosted` if another process still holds it, (3) inserts the nonce-protected `_HostEntry` BEFORE `t.start()`, and (4) on thread-start failure removes the entry only if the nonce matches and releases the fd (`failed`, detail `failed to start host watcher: ...`).
! `host.lock` acquired once and transferred to `_run_watcher` — no release/reacquire gap. OS exclusive lock prevents duplicate watchers.
! `_run_watcher` owns the fd — closes it in `finally`, removes its registry entry only if `entry_nonce` matches (prevents a replacement entry from being deleted by an exiting prior incarnation).
! Adoption decides "terminal" with the mode-aware `state_machine.is_terminal()` (#41), not a hard-coded stage list, so an approved coding loop (`implementation_approved`) is never re-hosted, and a session with an unknown mode is skipped rather than hosted blind.
! Adoption skips loops whose `host.lock` is already held (another host is live). Loop start maps any non-attached result to HTTP 500 (`failed to start host watcher` or `failed to acquire host lock`) — a brand-new loop cannot legitimately be hosted elsewhere.

### do_GET() / do_POST() — DashboardHandler
File: src/gator_command/scripts/gator-dashboard.py
Dispatch API, asset, repository content, update, lifecycle, and loop workspace routes.
<- loopback HTTP server
-> typed request handlers and data adapters
! Every POST calls `_check_post_auth()` before mutation and requires `X-Gator-Dashboard: 1`. A rejected POST first drains its body (`_drain_request_body()`, bounded at `_MAX_DRAIN_BYTES` = 1 MiB; larger bodies close the connection instead), so the 403 is delivered reliably. Closing a socket with unread request data makes Windows reset the connection, which clients saw as an intermittent `ConnectionAbortedError`. Pinned by `test_rejected_post_with_body_is_delivered_reliably` (40 header-less POSTs with a body).
! Do not add permissive CORS. The custom header plus unanswered cross-origin preflight is the local anti-CSRF boundary.
! Debug GET routes return 404 unless `GATOR_DASHBOARD_DEBUG=1` is set for the test process.
! Debug seam `_debug_files_gate_wait()` (threaded-server plan, checkpoint 4). When `GATOR_DASHBOARD_DEBUG=1` **and** `GATOR_DASHBOARD_DEBUG_FILES_GATE=<path>` are both set, a live `/files` listing waits up to 30 s until that file exists. It gives the browser-level concurrency proof a deterministic slow listing. Without both variables it does nothing.

### build_snapshot(fast_data)
File: src/gator_command/scripts/dashboard/snapshot.py
Inline dashboard assets and Tier-1 data into a self-contained offline HTML document.
<- `--snapshot`
! Use callable regex replacement for JavaScript/CSS bytes so backslashes are not interpreted as replacement escapes.
! The data block also inlines `window.GATOR_WELCOME_DOCS` (`_welcome_docs_for_snapshot()`: every name in `WELCOME_DOC_NAMES`, i.e. the Welcome and Docs documents → text or `null`). `_with_csp_meta()` inserts one `<meta http-equiv="Content-Security-Policy">` with `content_policy.html_csp_meta_policy()` immediately after the first `<head…>` tag. A document without `<head>` becomes `null`, never an unprotected document. `_json_script()` escapes every `<`, `>`, `&` as `<` / `>` / `&` (`json.dumps` already escapes non-ASCII), so neither `</script>` nor `<!--` can appear in the inline script. `welcome.js` assigns each text through the `iframe.srcdoc` property, never through an HTML attribute string.
! The data block sets `window.GATOR_SNAPSHOT = true`. It shows the snapshot banner. The banner carries the capture time: `#snapshot-generated-at`, written by `updateTimestamp()` from the inlined `generated_at` (Paper, 2026-10-19). Refresh is hidden: it lives in the strip's `#strip-status`, which `init()` hides with the strip. Beyond that, the flag makes `dashboard.js` `init()` land on **Fleet** instead of Welcome (a snapshot is a fleet report; live loads land on Welcome, see `scripts-dashboard-ui.md` → Landing view). Pinned by `test_welcome_snapshot_frames`.
! The script-tag regex must match every shell script tag in `dashboard.html`: the `views/*.js` tags and the shell modules `workspace.js` (#80) and `dashboard.js`. Adding a script file requires updating both the regex pattern and the inlined scripts block.
  - **Current order:** fleet, history, syntax, repo, updates, **loop-markdown (#45)**, loop, settings, **welcome (#72)**, **docs (2026-10-13)**, **workspace (#80)**, then `dashboard.js`. In the inlined block, the data block sits between docs and workspace.
  - **Pinned by** `tests/test_snapshot.py`, including that `window.GatorLoopMarkdown`, `GatorViews.welcome`, `GatorViews.docs` and `window.GatorWorkspace` are inlined.
! `GATOR_SNAPSHOT` also turns off workspace contexts and keeps shell history entries state-only (no URL argument on `file:` URLs) (#80; see `scripts-dashboard-ui.md`).
! Images are not inlined. In a snapshot, `renderWorkspaceStrip()` returns early (`workspace()` is null), so the strip's `gator-logo.png` mark for repository-less tabs (2026-10-17) is never rendered. Its path appears only as text inside the inlined `workspace.js`. Rendering the strip in a snapshot would add an external image reference. The sidebar `#brand-logo` in `dashboard.html` is already one such reference (pre-existing). Paper only draws it dark with a CSS filter; it adds no image. The builder's regexes still match because the stylesheet `<link>` and every `<script>` tag in `dashboard.html` are unchanged.

### check_for_updates() / upgrade_and_restart() / restart_server()
File: src/gator_command/scripts/dashboard/updates.py
Check PyPI, perform an explicit pipx upgrade in a detached helper, and relaunch the dashboard.
<- update API routes (through `_drain_then()`, below)
! Checking is read-only. Upgrade happens only after an authenticated explicit POST and must not strand the response process mid-write.

### _drain_then(fn) / _start_lifecycle(fn, action, name) / _post_routes(path) · _LifecycleGate / _LIFECYCLE_GATE / _DRAIN_SECONDS / _GATE_EXEMPT_POSTS
File: src/gator_command/scripts/gator-dashboard.py
Restart and upgrade drain (threaded-server plan, checkpoint 3). `do_POST` first runs `_check_post_auth()`, then the gate, then `_post_routes()`, which holds the former `do_POST` dispatch unchanged.
- `_LifecycleGate` counts in-flight POSTs under one condition (`enter` / `leave`). After `start_draining()`, `enter()` refuses, and the route drains the body and returns 503 `{"error": "dashboard is restarting"}`.
- `POST /api/restart` and `/api/updates/upgrade` are in `_GATE_EXEMPT_POSTS`. They are never counted, so the coordinator never waits for the request that triggered it.
- `_start_lifecycle(fn, action, name)` starts the `_drain_then(fn)` coordinator thread **before** the route responds `restarting` / `upgrading`. `start_draining(action)` atomically records which action owns the drain, and only the first caller starts a coordinator.
  - A repeat of the **same** action gets the same success response, idempotently, and starts nothing.
  - A **different** action gets 409 `{"error": "dashboard is already <active>", "status": "<active>"}` and starts nothing. This holds for restart-then-upgrade and for upgrade-then-restart, so no route acknowledges an action that will not run.
- The coordinator waits up to `_DRAIN_SECONDS` (5 s) for in-flight POSTs, via `Condition.wait_for`, which holds no lock while waiting. It then calls the unchanged `restart_server()` / `upgrade_and_restart()`, even if a POST is still in flight after the bound.
<- `do_POST`
-> `restart_server()`, `upgrade_and_restart()` (resolved at request time, so tests may monkeypatch them)
! GETs are read-only and not gated; they keep being served until the process is replaced, and in-flight GETs are abandoned then. Loop watcher threads die with the process as before; the OS releases `host.lock`, and adoption re-hosts after the restart.
! If the coordinator thread cannot start, `cancel_draining()` undoes the drain and the route returns 500. The Dashboard never refuses every POST with no restart coming, and never reports `restarting` falsely.
! `_LIFECYCLE_GATE`'s condition is a leaf; the gate is entered before any route lock (`_repo_action`, the state locks).
! Pinned by `TestRestartDrain` in `tests/test_dashboard_concurrency.py`.

### _heavy_work() / _send_heavy_busy() · DashboardHTTPServer / MAX_WORKERS / HEAVY_WORKERS / _HEAVY_SLOTS / _HEAVY_TIMEOUT
File: src/gator_command/scripts/gator-dashboard.py
The threaded request server (threaded-server plan, checkpoint 4; #70 head-of-line blocking). A slow listing, search, Git call or subprocess no longer delays an unrelated document, API or UI request on the same port.
- `DashboardHTTPServer(socketserver.ThreadingMixIn, HTTPServer)` runs one daemon worker per request (`daemon_threads = True`, `block_on_close = False`, `request_queue_size = 64`).
- `process_request` runs on the `serve_forever` thread. It takes one of `MAX_WORKERS` (16) slots, blocking while all are busy, so excess connections queue in the listen backlog rather than being refused or creating unbounded threads. It then starts a `dashboard-request` thread, which releases the slot in `finally`. If `Thread.start()` fails, it releases the slot and closes the connection.
- `_heavy_work()` admits expensive routes to `HEAVY_WORKERS` (4) shared slots, waiting up to `_HEAVY_TIMEOUT` (60 s) and then sending 503 `{"error": "dashboard busy; retry"}` via `_send_heavy_busy()`. At least 12 workers therefore stay free for small reads.
  - **Heavy routes:** `/files` and per-file `/history` (the parse-once dispatch), the repo-scope `/history`, `/search`, `/check`, `/commits`, Tier-2 `/api/repo/<name>`, `/api/repos/discover`, and `/api/audit/sessions` (taken before `_AUDIT_LOCK`).
  - **Not heavy:** `/file`, `/raw`, `/api/data`, Welcome documents, static assets, and all Loop routes.
<- `main()`; the concurrency tests construct it on port 0.
! TRIPWIRE: `protocol_version` stays HTTP/1.0, so each connection carries one request and one worker. HTTP/1.1 keep-alive would pin workers to idle browser connections and starve the cap.
! The cap values come from browser behavior (at most 6 HTTP/1.x connections per origin), not measurement alone. Re-measure before changing them: see the checkpoint 4 performance record in the loop's implementation artifact.
! Every request is concurrent with every other. Shared state goes through the snapshot helpers, same-repository mutations through `_repo_action`, and POSTs through `_LifecycleGate`. Never add module or class state that a handler mutates without one of those contracts. Lock order: `_LifecycleGate` (POST admission), then `_heavy_work` / `_AUDIT_LOCK` / `_repo_action`, then `_STATE_WRITE_LOCK`, then `_STATE_LOCK`. Loop OS locks and `_LOOP_HOSTS_LOCK` are never taken under a Dashboard state lock.
! A slot is held while the response is written, so a slow client holds its slot. This is bounded by the 16 and 4 caps and by the client socket.
! Pinned by `TestThreadedServer`, `TestConcurrentReads`, `TestContentPolicyUnderConcurrency` and `TestMixedStress` in `tests/test_dashboard_concurrency.py`, and by `tests/test_dashboard_ui/test_request_concurrency_ui.py`.

### main()
File: src/gator_command/scripts/gator-dashboard.py
Load registry/settings, collect initial data, bind loopback, optionally open a browser, or emit a snapshot. It serves with `DashboardHTTPServer` on both bind paths (port 0 and a fixed port).
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
- Keep the two F2 proofs apart: server-discovered paths (listing, search) go through `_iter_live_candidates()`; a client-supplied URL path never goes through `_scanner_target()` and keeps `_contained_repo_path()`.
- Preserve structured per-repo empty states.
- Run backend dashboard tests plus the Playwright content-transport suite when wire or HTML behavior changes.

## Connections

-> [Dashboard UI](scripts-dashboard-ui.md) - wire-schema and interaction consumer
-> [Core Library](scripts-core-library.md) - registry, preferences, and runtime helpers
-> [Fleet Intelligence](scripts-fleet-intelligence.md) - governance data producers
-> [Session Archaeology](scripts-session-archaeology.md) - session evidence
-> [Repo Lifecycle](scripts-repo-lifecycle.md) - update/gatorize actions
-> [Gator Loop](scripts-loop.md) - loop session/event reads for workspace routes
-> [Cross-Cutting](scripts-cross-cutting.md) - shared schemas and path conventions
