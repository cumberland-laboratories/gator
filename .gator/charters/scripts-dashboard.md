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

### _handle_repo_remove()
File: src/gator_command/scripts/gator-dashboard.py
Remove a single registry entry identified by its exact registered path. Registry-only — no filesystem access to the repo directory.
<- `POST /api/repos/remove` with `{"path": "/abs/path"}` in body
-> `gator_core.remove_dashboard_repo()`
! Identity is the resolved registered path, not the display name. Duplicate display names cannot cause multi-entry removal.
! Cache mutation is synchronous: (1) write registry JSON, (2) filter `_REGISTRY_REPOS`, (3) filter `fast_data["repos"]` — all before the success response.
! Test paths must be resolved through `Path.resolve()` so the `os.path.isabs()` validation passes on both Windows and Linux CI.

### _resolve_repo_by_key(repo_key) / _resolve_loop_dir(repo_key, loop_id)
File: src/gator_command/scripts/gator-dashboard.py
Resolve `repo_key` (path-hash) to registered repo path, then validate `loop_id` and return a containment-safe loop directory Path. Single gatekeeper for all loop-file access.
<- loop workspace route handlers
-> `_REGISTRY_REPOS`, `session_cache_key()` (fallback)
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
! Every participant prompt ends its fixed block with the explicit-start pointer "New to Gator in this repo? Run `gator init` first; its handoff names GATOR_INIT.md and the loop protocol." (gator-native entry point, 2026-10-08). Native agent files no longer teach "gator loop join", so the prompt must not rely on them. Pinned by `test_prompt_names_explicit_gator_init_start` in `tests/test_dashboard_loop_brief.py`.

### _resolve_architect_token(repo_key, loop_id, cache_control=None) / _handle_loop_pause() / _handle_loop_interject() / _handle_loop_unblock() / _handle_loop_end()
File: src/gator_command/scripts/gator-dashboard.py
Architect control endpoints. Each resolves `loop_dir` via `_resolve_loop_dir()`, reads the architect token from `.tokens.json`, and delegates to the corresponding `submit.py` handler with `loop_dir=loop_dir`. A malformed or non-object token store is a 404 (`tokens unreadable` / `architect token not found`), never an unhandled 500. `cache_control` passes through to error responses (the liveness routes pass `no-store`).
<- `_dispatch_loop_post()` via action suffix matching (`/pause`, `/interject`, `/unblock`, `/end`; `/extend` and `/renotify` have their own entries below)
-> `_resolve_loop_dir()`, `loop.session.load_tokens()`, `loop.submit.handle_pause()`, `loop.submit.handle_interject()`, `loop.submit.handle_unblock()`, `loop.submit.handle_end()`
! Dashboard never acquires the session lock itself — all writes delegate to `submit.py` handlers.
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
  - The response, `gator-loop-coding-snapshot-v1`, is `{stage, approval_resolution, live}`. `approval_resolution` is the pure `state_machine.resolve_approval()` result against a fresh `gitsnap.snapshot()`. `live` holds slim facts (`ok`, HEAD, HEAD tree, staged tree, branch, detached, changed count, residue other/loop counts), or `{ok: false, error}`.
  - Raw path lists are never served. Git trouble shows as `unknown`, never approved.
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

### _LOOP_HOSTS / _HostEntry / _run_watcher() / _ensure_loop_watcher() / _adopt_orphaned_loops()
File: src/gator_command/scripts/gator-dashboard.py
Server-local host registry tracking watcher threads, held `host.lock` file descriptors, and entry nonces. Startup adoption scans registered repos for orphaned active loops. `_ensure_loop_watcher(repo_path, loop_id, loop_dir, retry=False)` is the **single attach path** for every Dashboard watcher (start, adoption, and #39 extension) and returns `(state, detail)` with `WATCHER_ATTACHED` / `WATCHER_ALREADY_HOSTED` / `WATCHER_FAILED`.
<- server startup, `_handle_loop_start()`, `_handle_loop_extend()` (M5b)
-> `loop.host.watch_loop()`, `loop.host.acquire_host_lock_with_retry()`, `loop.host.release_host_lock()`
! Invariant: never create a watcher thread outside `_ensure_loop_watcher()`. It (1) returns `already_hosted` if this process already has a live thread for the key, (2) acquires `host.lock` — one attempt for start/adoption, the ~3 s `acquire_host_lock_with_retry()` window when `retry=True` — and returns `already_hosted` if another process still holds it, (3) inserts the nonce-protected `_HostEntry` BEFORE `t.start()`, and (4) on thread-start failure removes the entry only if the nonce matches and releases the fd (`failed`, detail `failed to start host watcher: ...`).
! `host.lock` acquired once and transferred to `_run_watcher` — no release/reacquire gap. OS exclusive lock prevents duplicate watchers.
! `_run_watcher` owns the fd — closes it in `finally`, removes its registry entry only if `entry_nonce` matches (prevents a replacement entry from being deleted by an exiting prior incarnation).
! Adoption decides "terminal" with the mode-aware `state_machine.is_terminal()` (#41), not a hard-coded stage list, so an approved coding loop (`implementation_approved`) is never re-hosted, and a session with an unknown mode is skipped rather than hosted blind.
! Adoption skips loops whose `host.lock` is already held (another host is live). Loop start maps any non-attached result to HTTP 500 (`failed to start host watcher` or `failed to acquire host lock`) — a brand-new loop cannot legitimately be hosted elsewhere.

### DashboardHandler.do_GET() / DashboardHandler.do_POST()
File: src/gator_command/scripts/gator-dashboard.py
Dispatch API, asset, repository content, update, lifecycle, and loop workspace routes.
<- loopback HTTP server
-> typed request handlers and data adapters
! Every POST calls `_check_post_auth()` before mutation and requires `X-Gator-Dashboard: 1`. A rejected POST first drains its body (`_drain_request_body()`, bounded at `_MAX_DRAIN_BYTES` = 1 MiB; larger bodies close the connection instead), so the 403 is delivered reliably. Closing a socket with unread request data makes Windows reset the connection, which clients saw as an intermittent `ConnectionAbortedError`. Pinned by `test_rejected_post_with_body_is_delivered_reliably` (40 header-less POSTs with a body).
! Do not add permissive CORS. The custom header plus unanswered cross-origin preflight is the local anti-CSRF boundary.
! Debug GET routes return 404 unless `GATOR_DASHBOARD_DEBUG=1` is set for the test process.

### build_snapshot(fast_data)
File: src/gator_command/scripts/dashboard/snapshot.py
Inline dashboard assets and Tier-1 data into a self-contained offline HTML document.
<- `--snapshot`
! Use callable regex replacement for JavaScript/CSS bytes so backslashes are not interpreted as replacement escapes.
! The script-tag regex must match every `<script src="views/*.js">` tag in `dashboard.html`. Adding a new view JS file requires updating both the regex pattern and the inlined scripts block. Current order: fleet, history, syntax, repo, updates, **loop-markdown (#45)**, loop, settings, then `dashboard.js`, pinned by `tests/test_snapshot.py` (including that `window.GatorLoopMarkdown` is inlined).

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
-> [Gator Loop](scripts-loop.md) - loop session/event reads for workspace routes
-> [Cross-Cutting](scripts-cross-cutting.md) - shared schemas and path conventions
