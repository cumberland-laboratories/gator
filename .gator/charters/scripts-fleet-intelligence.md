# Charter: Fleet Intelligence

**Covers**: `src/gator_command/scripts/gator-fleet-report.py`, `src/gator_command/scripts/gator-fleet-intel.py`, `src/gator_command/scripts/gator-drift.py`, `src/gator_command/scripts/gator-audit.py`, `src/gator_command/scripts/gator-repo-status.py`, `audit-report.html` (generated output of gator-audit.py)

## Owns

Cross-repo analysis and governance posture reporting. Fleet-report, fleet-intel, drift, and audit are **enterprise-only** — excluded from the Gator Individual public wheel and deploy. They remain in the source tree for development and command-post use:

- `gator-fleet-report.py` owns the per-repo governance status scan: reads registry, visits each repo (local then remote fallback), and reports git state + .gator/ state.
- `gator-fleet-intel.py` owns per-repo intelligence profile generation: synthesizes commit history, charter coverage, thread status, and committed decisions into `gator-command/threads/repo-*.md` files. Observable data only — no LLM inference.
- `gator-drift.py` owns drift detection: compares each repo's governance state against the command post's current generation and policy date, produces severity-ranked findings.
- `gator-audit.py` owns the convergence dashboard: assembles fleet-report, drift, sessions, governance coverage, and trailer intelligence into three output modes (text, JSON, HTML). The `--json` output includes `override_events`, `significance_distribution`, and `governed_commits` derived from direct git log scanning across the fleet.
- `gator-repo-status.py` owns the per-repo deep status scan: charter coverage % (from `**Covers**:` declarations), stale charter detection, recent trailer history, override events, session summary count, and enforcement config (from `.gator/config.json`). Produces the `gator-repo-status-v1` JSON schema consumed by the Dashboard Repo view and Settings view. The Dashboard server (`gator-dashboard.py`) calls these scripts via subprocess — it owns HTTP serving, self-restart, git history endpoints, and file version serving (all git subprocess calls via `_git_run()` with UTF-8 encoding), not governance logic. In standalone dashboard mode, `gator-repo-status --path` is called per repo to build the fleet surface without `gator-fleet-report`. Dashboard restart adds `--no-open` to avoid duplicate browser tabs.

## Does Not Own

- Remote fetch mechanics — that belongs to `gator_remote.py`.
- Session extraction or spool management — that belongs to the session-archaeology cluster.
- Writing to fleet repos — all five scripts are read-only (or write only to `gator-command/threads/` for fleet-intel).
- The org-policy.md content — that is Architect-owned. `gator-drift.py` reads it but never writes it.
- Policy sync state computation — that belongs to `gator-policy-status.py`. Fleet-report and drift import it via `import_sibling()` with graceful fallback.

---

### read_gator_state(repo_path)
File: `src/gator_command/scripts/gator-fleet-report.py`
Reads `.gator/` state from a local repo: generation, policy version, charter count + function count, thread count, issue count, mission summary, hook presence.
Filesystem: `.gator/` directory tree (R)
<- `scan_repo()`
-> filesystem reads only
! This function has a structural parallel in `gator_remote.read_gator_state_remote()`. If you add a new state field here, add it to the remote version too — the audit dashboard merges both without knowing the scan mode.
! Installed-hook detection now probes the managed path set exposed by `gator-update.py` (`.git/gator-hooks` on Windows, legacy `.git/hooks` tolerated). Hook telemetry must stay backward-compatible while the fleet migrates.

### scan_repo(repo_entry, force_remote=False)
File: `src/gator_command/scripts/gator-fleet-report.py`
Scans a single registered repo. Tries local path first; falls back to `scan_repo_remote()` if local is inaccessible and a remote URL is available.
Filesystem: repo path (R), `~/.gator/fleet-cache/` (RW on remote fallback)
<- `scan_fleet()`
-> `read_gator_state()`, `scan_repo_remote()` in `gator_remote`
! The `scan_mode` field ("local" or "remote") propagates through to fleet totals and audit display. Do not merge local and remote scan results without preserving this distinction.

### get_policy_link_local(repo_path)
File: `src/gator_command/scripts/gator-fleet-report.py`
Gets policy sync status for a local repo via `gator-policy-status` module. Returns dict with state, authority, and provenance fields. Gracefully returns `{"state": "unavailable"}` if policy-status module is not loaded.
Filesystem: `.gator/governance-source.json` (R), `.gator/policy-link.json` (R), `.gator/policy-cache/` (R)
<- `scan_repo()`
-> `_compute_sync_state()`, `_get_governance_source()` from `gator-policy-status`
! Authority is "authoritative" for states where a source comparison actually happened: synced, behind, diverged, and no-cache only when source_type is "local". Remote-only no-cache is non-authoritative because no freshness comparison occurred.

### get_last_commit(repo_path)
File: `src/gator_command/scripts/gator-fleet-report.py`
Gets the last commit hash, message, age, and date from a repo, trying the `dev` branch first then falling back to the current branch.
Filesystem: git history (R)
<- `scan_repo()`

### get_commit_count(repo_path, days=30)
File: `src/gator_command/scripts/gator-fleet-report.py`
Counts commits in the last N days using `git rev-list --count`.
Filesystem: git history (R)
<- `scan_repo()`

### get_current_branch(repo_path)
File: `src/gator_command/scripts/gator-fleet-report.py`
Returns the current branch name, or "detached" if in detached HEAD state.
Filesystem: `.git/HEAD` (R via git)
<- `scan_repo()`

### get_working_tree_status(repo_path)
File: `src/gator_command/scripts/gator-fleet-report.py`
Returns "clean" or a count of changed files from `git status --porcelain`.
Filesystem: working tree (R via git)
<- `scan_repo()`

### get_latest_trailers(repo_path)
File: `src/gator_command/scripts/gator-fleet-report.py`
Extracts Gator-* trailers from the latest commit, trying `dev` branch first then current branch.
Filesystem: git history (R)
<- `scan_repo()`

### get_policy_link_remote(repo_path)
File: `src/gator_command/scripts/gator-fleet-report.py`
Gets cached policy link info for a remote repo from `policy-link.json`; always non-authoritative since remote repos cannot compute real sync state.
Filesystem: `.gator/policy-link.json` (R via `_load_policy_link`)
<- `scan_repo_remote()` callers

### scan_fleet(repos, force_remote=False)
File: `src/gator_command/scripts/gator-fleet-report.py`
Scans all registered repos. Sequential (no parallelism). Post-processes remote-scanned repos to add policy_link via `_add_remote_policy_link()`.
<- `main()`, `gator-audit.py` via `import_sibling`
-> `scan_repo()` per entry, `_add_remote_policy_link()` for remote repos

### print_fleet_report(reports)
File: `src/gator_command/scripts/gator-fleet-report.py`
Prints a formatted terminal report of all fleet repos including git state, governance info, trailers, missions, and fleet-wide summary totals.
Filesystem: none (stdout only)
<- `main()`

### print_json_report(reports)
File: `src/gator_command/scripts/gator-fleet-report.py`
Outputs the fleet report as a JSON document with per-repo details and a summary object including policy sync counts.
Filesystem: none (stdout only)
<- `main()`

### main()
File: `src/gator_command/scripts/gator-fleet-report.py`
CLI entry point. Args: `--json` (JSON output), `--repo <name>` (single repo filter), `--remote` (force thin-fetch). Finds command post, parses registry, calls `scan_fleet()`, dispatches to text or JSON output.
<- CLI
-> `scan_fleet()`, `print_fleet_report()`, `print_json_report()`

### read_command_post_policy(command_post)
File: `src/gator_command/scripts/gator-drift.py`
Reads the current org policy version from `gator-command/org-policy.md` git history (date of last commit) and any explicit `version:` frontmatter field.
Filesystem: `gator-command/org-policy.md` (R via git log)
<- `main()`, `gator-audit.py` via `import_sibling`
! Policy version comparison uses ISO date strings (YYYY-MM-DD lexicographic sort). If `git log` fails, sets `git_failed=True` so downstream callers can suppress per-repo policy warnings rather than raising false alarms across the fleet.

### check_repo_drift(repo_entry, command_post_state)
File: `src/gator_command/scripts/gator-drift.py`
Checks a local repo against command post state. Falls back to `check_repo_drift_remote()` if the repo is inaccessible. Returns findings with severity (ok / warn / drift).
Filesystem: `.gator/` directory (R), git history (R)
<- `main()`, `gator-audit.py`
-> `check_repo_drift_remote()`, `gator_remote` functions
Checks performed: generation, policy-behind/policy-diverged/policy-no-cache (new system, authoritative), policy-version (old system, suppressed when new system is authoritative), hooks (sources + installed), charter presence, commit_draft format, constitution presence, branch, Gator-* trailers.
! Severity is "drift" if any finding is drift-level; "warn" if any finding is warn-level; "ok" only if no findings. "info" findings (policy-cached, policy-unknown on remote repos) do not affect overall severity. The overall severity is what surfaces in the audit dashboard indicator.
! When the new policy-status system returns an authoritative state (synced/behind/diverged, or no-cache with source_type=="local"), the old policy-version check is suppressed to avoid duplicate findings. Remote-only no-cache is not authoritative — the old check continues to run.
! Installed-hook checks must probe the managed hook path set, not just legacy `.git/hooks`, or Windows repos will false-drift after self-heal/update.
! Missing-hook finding message updated in v2.4.0 (retire-gator-install Stage 4): "Run gator update or gator gatorize" (was "Run gator update or gatorize.sh" — bash chain retired).

### check_repo_drift_remote(repo_entry, command_post_state)
File: `src/gator_command/scripts/gator-drift.py`
Checks a remote repo for drift via bare cache, running a subset of the local checks (generation, policy version, hook sources, charters, constitution, policy link).
Filesystem: `~/.gator/fleet-cache/` (R via bare cache)
<- `check_repo_drift()` (fallback when local inaccessible)
-> `ensure_cache()`, `read_gator_state_remote()`, `git_show()` from `gator_remote`

### print_drift_report(results, command_post_state)
File: `src/gator_command/scripts/gator-drift.py`
Prints a formatted terminal drift report with per-repo findings and a summary of current/warning/drifted counts.
Filesystem: none (stdout only)
<- `main()`

### print_json_report(results, command_post_state)
File: `src/gator_command/scripts/gator-drift.py`
Outputs the drift report as a JSON document with command post state, per-repo findings, and summary counts.
Filesystem: none (stdout only)
<- `main()`

### build_profile(name, repo_path)
File: `src/gator_command/scripts/gator-fleet-intel.py`
Synthesizes a complete intelligence profile from git history and .gator/ files. No LLM, no inference beyond commit message theme extraction.
Filesystem: repo `.gator/` (R), git history (R), `.gator/sessions/` (R)
<- `main()`
-> `get_recent_commits()`, `read_charter_names()`, `read_active_threads()`, `read_committed_decisions()`, `read_outbox()`
! Remote-only repos are skipped (returns `accessible: False`). Remote profiling is a documented gap — see thread note in `gator-fleet-intel.py` docstring.

### render_thread(profile)
File: `src/gator_command/scripts/gator-fleet-intel.py`
Renders a profile dict as a markdown thread file for `gator-command/threads/repo-{name}.md`.
Filesystem: none (pure rendering)
<- `main()`
! Output files are tagged "Do not edit manually — regenerated on each run." They are reference threads in the knowledge graph, not active threads.

### assemble_audit_data(since_days=7)
File: `src/gator_command/scripts/gator-audit.py`
Loads fleet-report, drift, and governance coverage via `import_sibling()`. Assembles decisions from committed summaries only (raw-vendor-logs fallback retired in Phase 3, 2026-08-13). Also calls `_collect_trailer_intelligence()` to produce `override_events`, `significance_distribution`, and `governed_commits` for the dashboard Audit view.
! `data["sessions"]` is intentionally `{}` (empty) — the vendor-transcript-derived session counts (`total`, `by_vendor`, `by_repo`, `pending_export`, `exported`) retired in Phase 3 (2026-08-13) per parent plan §5 decision 4 = (i) drop silently. Dashboard consumers default defensively (`sessions.by_vendor || {}`), so empty tiles are the honest degrade.
! Trailer field renamed: `Gator-Architect` (was `Gator-PI`). Reading code accepts both for backward compatibility with git history.
Filesystem: indirectly reads all .gator/ state, bare caches
<- `main()`
-> `import_sibling("gator-fleet-report")`, `import_sibling("gator-drift")`, `import_sibling("gator_session_reader")` (Phase 2A snippet-reader — used at the `decisions_source="committed"` branch and the remote-cache path), `import_sibling("gator-session-common")`, `_collect_trailer_intelligence()`, `_committed_decisions_from_snippets()`

### _committed_decisions_from_snippets(reader_mod, sessions_dirs_tagged, has_remote_sessions, data, since_days)
File: `src/gator_command/scripts/gator-audit.py`
Phase 2B extract from `assemble_audit_data()`. Reads committed `.md` summaries across the fleet via `gator_session_reader.read_committed_summaries()` and, if any remote bare caches carry summaries, via `gator_session_reader.parse_committed_summary()` on the fetched markdown. Applies `_is_real_decision()` filter to extract decisions from each summary. Returns `(committed_decisions, summary_items)`. Mutates `data` by popping `_remote_sessions` when the remote path runs.
Filesystem: `.gator/sessions/` (R via reader_mod), bare caches (R via gator_remote)
<- `assemble_audit_data()` (snippet-reader branch — `if has_committed or has_remote_sessions:`)
-> `reader_mod.read_committed_summaries()`, `reader_mod.parse_committed_summary()`, `gator_remote.read_session_summary_remote()`, `_is_real_decision()`
! **SURVIVING** contract. Byte-identical to the pre-Phase-2B inline body — pure extraction, no behavior change. Any change to the snippet-based decisions path lands here.

*(`_committed_decisions_from_raw_vendor_logs()` retired 2026-08-13 in Phase 3 Commit D per parent plan §2.2 — raw-vendor-logs decisions branch removed from `assemble_audit_data()`; the `elif common:` dispatch site also gone. `assemble_audit_data()` now runs only the snippet-reader branch.)*
! Each subsystem import is independently guarded — a broken fleet-report import does not prevent the drift section from rendering. Errors surface in `data["_errors"]` in JSON output.

### _collect_trailer_intelligence(fleet_status, since_days)
File: `src/gator_command/scripts/gator-audit.py`
Scans `git log` across all accessible local fleet repos for Gator-* commit trailers. Produces three datasets: `override_events` (commits with `Gator-Override:` trailer), `significance_distribution` (counts per `Gator-Significance` value), `governed_commits` (per-repo and fleet total of commits with any `Gator-*` trailer).
Filesystem: git history of each accessible local repo path (R)
<- `assemble_audit_data()`
! Do NOT call `str.strip()` on the raw git log block before splitting on `\x1f`. Python's `str.strip()` treats `\x1f` (chr(31), unit separator) as whitespace and removes the leading field separator, collapsing 4 parts to 3. Check `if not block:` instead.
! Use `%at` (Unix timestamp) in the git log format, not `%ai` or `%aI`. `%ai` embeds a local offset; truncating and appending Z produces incorrect UTC times. `%at` is always UTC-unambiguous and converts cleanly via `datetime.fromtimestamp(..., tz=timezone.utc)`.
! `override_events.approver` comes from `Gator-Override-Approved-By`, not `Gator-PI`. The hook writes this from `.override-meta.json` at commit time — it records who ran `gator-approve.py`, which may differ from the session PI.
! This function only scans local repos. Remote-only repos (accessible via bare cache) are skipped — trailer intelligence for remote repos is a documented gap.

### _is_real_decision(text)
File: `src/gator_command/scripts/gator-audit.py`
Filters session choreography (review requests, confirmations, navigation) from governance decisions. Returns False for texts that are short, are tool results, match bare confirmations, or match choreography patterns.
Filesystem: none
<- `assemble_audit_data()` (decisions loop)
! This is a second filter layer on top of `gator-session-common.extract_intelligence()`. Decisions that pass both layers are surfaced in the audit dashboard. The filter errs on the side of exclusion — governance evidence should be unambiguous.

### render_text(data)
File: `src/gator_command/scripts/gator-audit-renderers.py`
Renders audit data as terminal text. Sections: fleet status, drift, sessions, governance coverage, recent decisions.
Filesystem: none (pure function, returns string)
<- `main()` (via import from gator-audit-renderers)
! Extracted from gator-audit.py to gator-audit-renderers.py as part of B+ to A- Phase 1 cleanup.

### render_html(data)
File: `src/gator_command/scripts/gator-audit-renderers.py`
Renders audit data as a self-contained HTML file: inline CSS, no JavaScript, no external resources. Print-to-PDF and email compatible.
Filesystem: `audit-report.html` (W, via caller)
<- `main() --html` (via import from gator-audit-renderers)
! The HTML file has a hardcoded link to `github.com/cumberland-laboratories/gator`. Keep this consistent with the public repo URL when it changes.
! Extracted from gator-audit.py to gator-audit-renderers.py as part of B+ to A- Phase 1 cleanup.
! Renderer seam protected by 11 structural invariant tests (TestRenderTextInvariants, TestRenderHtmlInvariants) and 3 assembler→renderer end-to-end tests (TestAssemblerRendererSeam) that call real assemble_audit_data() and pass output to both renderers.

### _handle_sessions(args)
File: `src/gator_command/scripts/gator-audit.py`
Handles `--sessions` mode. Imports `gator-session-aggregator` via `import_sibling`, calls `get_session_summaries()` (single repo) or `get_fleet_summaries()` (fleet). Dispatches to JSON or `_render_sessions_text()`.
Filesystem: `.gator/session-snippets/*.json` (R via aggregator), `~/.gator/sessions/` (RW via aggregator)
<- `main() --sessions`
-> `gator-session-aggregator.get_session_summaries()`, `gator-session-aggregator.get_fleet_summaries()`

### _render_sessions_text(summaries, fleet)
File: `src/gator_command/scripts/gator-audit.py`
Renders session summaries as terminal text. In fleet mode, groups by repo first (alphabetical), then sorts descending by started_at within each repo. Shows date range, model, commit count, significance, goal, tags, and commit list per session.
Filesystem: none (stdout only)
<- `_handle_sessions()`
! Fleet mode must group by repo before rendering — the input from get_fleet_summaries() is globally sorted by started_at, which interleaves repos.
! test_handle_sessions_json uses monkeypatch to stub aggregator import — tests the actual _handle_sessions routing, not just JSON serialization.
! Dashboard `/api/audit/sessions` uses the same aggregator as `gator audit --sessions` — both consume `get_session_summaries()` and `get_fleet_summaries()` from `gator-session-aggregator.py`. Endpoint logic is in `_resolve_audit_sessions()` (testable without HTTP). Audit view JS passes `activeRepoKey` (path-hash) from dashboard state for single-repo scoping. Both command-post and standalone fleet data include `repo_key` per repo via `_inject_repo_keys()`. `GET /api/repo/<name>/search` provides server-side full-text search with AND/OR boolean operators across repo files. Dashboard `POST /api/repo/<name>/update` endpoint logic is likewise in `resolve_repo_update()` (module-level, testable) — runs `gator-update --path <repo>` on the current branch in place, pre-checks for a `.gator/` dir and returns HTTP 400 pointing at the Gatorize button when missing. Its sibling `POST /api/repo/<name>/gatorize` (Stage 3 fold-in of retire-gator-install plan) resolves via `resolve_repo_gatorize()` and runs `gatorize --yes <repo>` for the ungoverned-repo install path. The Add Repository modal's `GET /api/repos/discover` endpoint delegates to `resolve_discovery_roots()` — respects the `GATOR_DASHBOARD_DISCOVERY_ROOTS` env var override for scoping the scan (see `scripts-dashboard.md`). The History endpoint's `get_repo_history()` uses `gator_core.git()` under the hood — that helper's subprocess call is `encoding="utf-8", errors="replace"` (v2.4.4 fix) to survive non-cp1252 bytes in git log output on Windows; prior bare `text=True` crashed with UnicodeDecodeError mid-response.

---

### scan_repo_status(repo_path, repo_name)
File: `src/gator_command/scripts/gator-repo-status.py`
Assembles a complete per-repo status dict: branch, hook_status, charter coverage, stale charters, last governed commit, recent trailers, override events, session summary count, enforcement config (from `.gator/config.json`), topology (from `get_repo_topology()` using `repo_path / ".gator"`), and cli_version (from `.gator/.gator-version`). Registry paths must be normalized before filesystem operations. Dashboard Fleet Update calls `gator-update --path <repo_path>` (operates on the current branch in place; historical `gatorize.py` invocation retired in v2.4.0 per plan `2026-07-30-retire-gator-install-branch-implementation-plan.md`). Standalone fleet data includes `gator_cli_version` for version-based Update button enable/disable. Activity column uses dot-pulse animation during update operations. Config changes update the server cache for immediate page-refresh consistency. Self-update uses PyPI version check + pipx upgrade. Version resolution via `gator_core.get_version()`. Upgrade uses stop-upgrade-relaunch pattern with `CREATE_NO_WINDOW` to avoid Windows file locks and visible CMD windows. `read_gator_state()` now includes `gator_updated` timestamp from `.gator-version` for the Fleet "Last updated" column. Charter health (from `gator-charter-verify`) is included in the Check Status response for Charters column indicators. `gator-pulse.py` generates `.gator/pulse.md` summaries from git history — the default Repo view document. File browser uses per-segment URL encoding for subdirectory paths. Command post repos scan both `.gator/` and `gator-command/` file sources. Command post injected via `_inject_command_post()` helper (real branch, survives refresh). Gator-command/ dir values normalized to prevent double-slash display. File read includes git last-modified timestamp. `_inject_command_post` marks fleet entries matching command post path with `is_command_post`. File listing includes repo source files under `source/` prefix. Binary raw endpoint serves images for dashboard rendering.
Filesystem: `.gator/` (R), `git log` (R), `git ls-files` (R)
<- `main()`
-> `get_hook_status()`, `get_charter_coverage()`, `get_trailer_data()`, `get_session_summaries()`
! Schema version field is `"schema": "gator-repo-status-v1"`. If you add breaking fields, bump the schema version.

### get_charter_coverage(repo_path)
File: `src/gator_command/scripts/gator-repo-status.py`
Computes charter_coverage_pct from `**Covers**:` declarations, detects stale charters.
Filesystem: `.gator/charters/*.md` (R), `git ls-files` (R), `git log -1 %at` per covered file (R)
<- `scan_repo_status()`
-> `_parse_covers()`, `_file_last_commit_ts()`, `_is_source_file()`
! Coverage % = declared covered files ÷ all tracked source files (excluding test/generated patterns). A charter without a `**Covers**:` line contributes 0 to coverage — presence alone does not count.
! Staleness: charter is stale if any file in its `Covers:` list has a git commit timestamp newer than the charter file's own last commit. Uses `%at` (Unix timestamp) — not `%ai`.

### get_trailer_data(repo_path, lookback_days, limit)
File: `src/gator_command/scripts/gator-repo-status.py`
Scans git log for Gator-* trailers. Returns (last_governed_commit, recent_trailers, override_events).
Filesystem: `git log` (R)
<- `scan_repo_status()`
! Uses `\x1f` (chr 31, unit separator) as field separator in git log format. Do NOT call `str.strip()` on the raw block before splitting — Python treats `\x1f` as whitespace and `strip()` will eat the leading separator, collapsing 4 fields to 3. Use `if not block:` to skip empty blocks.
! Uses `%at` (Unix timestamp). Converting via `datetime.fromtimestamp(..., tz=timezone.utc)` gives correct UTC. Never use `%ai` or `%aI` — they embed a local offset and truncating to 19 chars produces incorrect UTC.
! Override approver comes from `Gator-Override-Approved-By`, not `Gator-PI`. The hook writes this from `.override-meta.json` at commit time — it records who ran `gator-approve.py`.

### get_hook_status(repo_path)
File: `src/gator_command/scripts/gator-repo-status.py`
Returns "present" / "missing" / "ungoverned" based on `.gator/` presence and the managed hook probe set exposed by `gator-update.py`.
Filesystem: `.gator/` (R), managed hook probe dirs (R)
<- `scan_repo_status()`
! "ungoverned" = no `.gator/` directory. "missing" = `.gator/` exists but no managed/legacy hook install is present. "present" = any managed probe dir contains the expected installed hooks.

### resolve_repo(repo_name, repo_path_arg)
File: `src/gator_command/scripts/gator-repo-status.py`
Resolves a repo to an absolute path. If `--repo` given, looks up registry. If `--path` given, uses directly. Otherwise uses cwd.
Filesystem: registry file (R via `parse_registry()`)
<- `main()`

### get_session_summaries(repo_path, limit=20)
File: `src/gator_command/scripts/gator-repo-status.py`
Reads committed session summaries via the canonical parser (`read_committed_summaries()` from `gator_session_reader.py` — Phase 2A retargeted 2026-08-12; was `gator-sessions.py` until then). Returns `(total_count, recent_items)` where `total_count` is the number of parseable summaries and `recent_items` is up to `limit` items (newest first) with metadata for dashboard display. Both the count and the panel are derived from the same parse pass, ensuring consistency.
Filesystem: `.gator/sessions/` (R)
<- `scan_repo_status()`
-> `import_sibling("gator_session_reader").read_committed_summaries()`
! `import_sibling()` returns `None` when the file is absent. This function guards against `None` and returns `(0, [])` gracefully. Without this guard, `scan_repo_status()` crashes with `AttributeError`, breaking standalone dashboard enrichment.

### render_text(data)
File: `src/gator_command/scripts/gator-repo-status.py`
Renders repo status dict as formatted terminal output: branch, hooks, charter coverage, stale charters, last governed commit, recent trailer table, override events, session count.
Filesystem: none (stdout only)
<- `main()`

### main()
File: `src/gator_command/scripts/gator-repo-status.py`
CLI entry point. Args: `--repo <name>` (registry lookup), `--path <path>` (direct), `--json` (JSON output mode). Resolves repo via `resolve_repo()`, calls `scan_repo_status()`, dispatches to `render_text()` or JSON dump.
<- CLI
-> `resolve_repo()`, `scan_repo_status()`, `render_text()`

---

## TRIPWIRE: Local/Remote Parity

`read_gator_state()` (fleet-report) and `read_gator_state_remote()` (gator_remote) must return structurally identical dicts. The audit dashboard merges results from both scan modes without discriminating. If you add a new field to the local scan, add it to the remote scan too — with an appropriate "cannot determine remotely" default.

## TRIPWIRE: Decisions Source Preference

`assemble_audit_data()` prefers committed summaries (`.gator/sessions/`) over raw vendor logs for the decisions section. The raw vendor log fallback is explicitly labeled "decisions_source: raw-vendor-logs" in JSON output. Never silently mix the two sources — the audit trail value depends on knowing where decisions came from.

## Before Changing This Module

- Fleet-report and drift are both imported by `gator-audit.py` at runtime via `import_sibling()`. Their public function signatures (`scan_fleet()`, `read_command_post_policy()`, `check_repo_drift()`, `parse_registry()`) are part of an implicit API contract with the audit script.
- The severity ladder (ok → warn → drift) in drift is mirrored in the audit dashboard's visual indicators. If you add a new severity level, update both.
- Fleet-intel writes to `gator-command/threads/` — these are knowledge graph nodes. Their frontmatter fields (`title`, `category`, `generated`, `repo-path`) are consumed by `generate_wiki.py` and `graph_health.py`.
- `gator-audit.py`'s HTML output is the CISO-facing artifact. It must remain self-contained and print-safe.

## Connections

-> [scripts-core-library](scripts-core-library.md) — gator_core, gator_remote, gator-session-common
-> [scripts-session-archaeology](scripts-session-archaeology.md) — session discovery and committed summaries consumed by audit
-> [scripts-cross-cutting](scripts-cross-cutting.md) — local/remote parity pattern, import_sibling pattern
-> [scripts-dashboard](scripts-dashboard.md) — dashboard consumes fleet-intelligence data; file list API now includes mtime; file scanner includes `.html`/`.htm` as of v2.4.5 (see scripts-dashboard "HTML file support")
-> [Index](INDEX.md)
