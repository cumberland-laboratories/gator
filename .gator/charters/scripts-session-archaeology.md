# Charter: Session Archaeology

**Covers**: `src/gator_command/scripts/extract-claude-sessions.py`, `src/gator_command/scripts/extract-codex-sessions.py`, `src/gator_command/scripts/extract-gemini-sessions.py`, `src/gator_command/scripts/gator-sessions.py`, `src/gator_command/scripts/gator-session-sink.py`, `src/gator_command/scripts/gator-session-aggregator.py`, `src/gator_command/scripts/gator-session-block.py`

## Owns

Session discovery, extraction, and persistence across all AI coding vendors:

- `extract-claude-sessions.py` owns Claude Code session archaeology: reads `~/.claude/projects/` JSONL files, produces normalized turns, delegates all summary formatting to `gator-session-common`.
- `extract-codex-sessions.py` owns Codex CLI session archaeology: reads `~/.codex/sessions/` with the same normalized turn format and delegation pattern.
- `extract-gemini-sessions.py` owns Gemini CLI session archaeology: reads `~/.gemini/tmp/` with the same pattern; Gemini is the only vendor with genuine duplicate session IDs across files — `make_row_key()` handles this.
- `gator-sessions.py` owns the vendor-agnostic orchestration CLI: session discovery index, JSON manifests, spool exports, pending tracking, and the committed summary layer (`read_committed_summaries()`, `parse_committed_summary()`).
- `gator-session-sink.py` owns loading session data into analytical backends: SQLite, DuckDB, and NDJSON command pipe. Two input paths: spool (full turns) and committed summaries (lightweight). Schema version: `gator-session-sink-v2`.
- `gator-session-aggregator.py` owns the snippet-to-summary pipeline: reads v2 JSON snippets from `.gator/session-snippets/*.json`, aggregates by `(repo, session_id)`, caches summaries at `~/.gator/sessions/<path-hash>/`. Importable library — no CLI entry point. Consumers: `gator-audit.py` (CLI `--sessions`), `gator-dashboard.py` (Audit view API).
- `gator-session-block.py` owns session-block companion capture: extracts exact transcript slices per commit interval from vendor session storage. CLI-first, on-demand via `gator session-blocks generate --commit <commit-ish>`. Discovers transcripts by snippet `transcript_session_id`, anchors intervals by short commit hashes in tool output, emits gzip-compressed blocks to `.gator/session-blocks/`. Local-only, same-machine best effort.

## Does Not Own

- Machine identity storage — that is `gator-machine-id.py` and `gator-session-common.py`.
- Summary formatting logic — all vendor extractors delegate to `gator-session-common.format_summary_markdown()` and `format_session_summary_dict()`.
- Fleet-level decision assembly for the audit dashboard — that is `gator-audit.py`.
- The committed summary read path in the audit — `gator-audit.py` calls `gator-sessions.read_committed_summaries()` directly.
- The committed summary read path in repo-status — `gator-repo-status.py` calls `gator-sessions.read_committed_summaries()` via `import_sibling("gator-sessions")` for the recent sessions panel.

---

### discover_projects()
File: `src/gator_command/scripts/extract-claude-sessions.py`
Finds all Claude Code projects with session data in `~/.claude/projects/`. Determines readable project names from session `cwd` fields.
Filesystem: `~/.claude/projects/` (R)
<- `main()`
! Returns project names from the `cwd` field of the first session turn, not from the directory slug. The slug (`C--Users-curator-code2-project`) is opaque; the cwd-derived name (`project`) is human-readable.

### extract_session(session_path)
File: `src/gator_command/scripts/extract-claude-sessions.py`
Reads a Claude Code JSONL session file and returns normalized turns: role, timestamp, content (always string), tool_calls, cwd, branch, session_id.
Filesystem: `~/.claude/projects/<slug>/<uuid>.jsonl` (R)
<- `main()`, `gator-audit.py` (raw vendor fallback path)
! Skips `file-history-snapshot` and `progress` turn types. Content for assistant turns is a list of blocks (text, tool_use, tool_result) — this function flattens them to a single string. The `tool_result` block content is truncated to 200 chars to avoid bloating summaries.

### extract_session_metadata(turns)
File: `src/gator_command/scripts/extract-claude-sessions.py`
Derives session-level metadata from the turn list: timestamps, cwd/branch sets, turn counts, tools used, session ID, repo name.
Filesystem: none
<- `main()`
! Session IDs come from the JSONL `sessionId` field, not from the filename UUID. A session file may contain turns with multiple session IDs (rare but possible after session recovery).

### format_session_markdown(turns, metadata)
File: `src/gator_command/scripts/extract-claude-sessions.py`
Produces a full Markdown transcript of the session turns. Each turn is headed with a timestamp and role label (Architect / Agent).
Filesystem: none
<- `main()` (non-summary, non-JSON mode)
! This is the full transcript formatter — it does NOT delegate to gator-session-common. Only `format_session_summary()` and `format_summary_markdown()` delegate to shared canonical formatters.

### _import_vendor(module_name) / _spool_slug(session_id, source_path)
File: `src/gator_command/scripts/gator-sessions.py`
`_import_vendor()` loads a vendor extractor or `gator-session-common` by filename using `importlib.util.spec_from_file_location()` — file-based dynamic loading, not sys.path manipulation (sys.path is set once at module import time at the top of gator-sessions.py). `_spool_slug()` returns `sha256("{session_id}|{source_path}")[:16]` — the canonical spool filename key.
Filesystem: scripts directory (R for import)
<- all `cmd_*` handlers in `gator-sessions.py`
! `_spool_slug()` must produce byte-identical output to `gator-session-common.make_row_key()` and `gator-session-sink.load_spool_sessions()`. See cross-cutting TRIPWIRE: row_key Formula Duplication.

### load_exported_state() / save_exported_state(exported_ids) / get_pending_sessions(all_sessions)
File: `src/gator_command/scripts/gator-sessions.py`
Tracks which sessions have been exported to spool. `load_exported_state()` reads `~/.gator/session-spool/.exported.json`; `save_exported_state()` writes it; `get_pending_sessions()` filters sessions not in the exported set.
Filesystem: `~/.gator/session-spool/.exported.json` (RW)
<- `cmd_export()`, `cmd_pending()`, `cmd_index()`
! Exported state is keyed by `{vendor}-{spool_slug}`. If the slug formula changes, existing entries go stale and sessions re-export on next run.

### cmd_index(args)
File: `src/gator_command/scripts/gator-sessions.py`
Discovers all sessions and prints a tabular index grouped by vendor. Supports `--since`, `--json`. JSON output includes per-session `row_key`. Text output shows latest 10 per vendor with pending export count.
Filesystem: vendor session dirs (R)
<- `main()` via `sessions index`

### cmd_manifest(args)
File: `src/gator_command/scripts/gator-sessions.py`
Emits a machine-readable JSON manifest (schema: `gator-session-manifest-v1`). Supports `--pending`. Includes machine identity, `row_key`, `spool_path`, and export status per session.
Filesystem: `~/.gator/session-spool/` (R for status check)
<- `main()` via `sessions manifest`
! Designed for enterprise ETL pipelines. The `row_key` in the manifest matches the database deduplication key used by `gator-session-sink.py`.

### cmd_export(args)
File: `src/gator_command/scripts/gator-sessions.py`
Writes normalized session JSON to `~/.gator/session-spool/`. Dispatches to vendor extractors via `_import_vendor()`, applies redaction via `gator-session-common`, tracks exports in `.exported.json`.
Filesystem: vendor session files (R), `~/.gator/session-spool/` (W), `.exported.json` (RW)
<- `main()` via `sessions export`
-> `_import_vendor()` per vendor, `gator-session-common.redact()`
! Per-session errors are caught and logged without aborting the full run. Check output for `!` lines to identify failed extractions.

### cmd_pending(args)
File: `src/gator_command/scripts/gator-sessions.py`
Shows sessions not yet exported to spool. Text output capped at 20 entries. Supports `--json`.
Filesystem: vendor session dirs (R), `.exported.json` (R)
<- `main()` via `sessions pending`

### cmd_commit_summaries(args)
File: `src/gator_command/scripts/gator-sessions.py`
Writes git-tracked session summaries to `.gator/sessions/` using `gator-session-common.format_summary_markdown()`. Filenames are deterministic: `{date}-{project}-{vendor}-{row_key}.md`. Idempotent — skips existing files unless `--force`.
Filesystem: vendor session files (R), `.gator/sessions/` (W)
<- `main()` via `sessions commit-summaries`
-> `gator-session-common.format_summary_markdown()`, `gator-session-common.make_row_key()`
! Summaries written here are the durable committed-summary layer preferred by `gator-audit.py`. They must use the canonical formatter to stay schema-compatible with `parse_committed_summary()` and `gator-session-sink.load_committed_summaries()`.

### discover_all_sessions()
File: `src/gator_command/scripts/gator-sessions.py`
Discovers all sessions across all enabled vendors (Claude, Codex, Gemini). Returns a flat list of session dicts with vendor, path, project, and timestamp fields.
Filesystem: `~/.claude/`, `~/.codex/`, `~/.gemini/` (R)
<- `main()`, `gator-audit.py` via import_sibling
! Vendors are imported lazily — a missing vendor directory (no Codex installed) is silently skipped. If a vendor extractor fails to import, that vendor is excluded from the index but others continue.

### filter_sessions_since(sessions, since_dt) / parse_since(since_str)
File: `src/gator_command/scripts/gator-sessions.py`
`parse_since()` converts strings like "7d", "24h", "30d" to a datetime. `filter_sessions_since()` filters sessions to those after the cutoff.
Filesystem: none
<- `main()`, `gator-audit.py`
! `since_dt=None` means no filter (all sessions). Always check for None before calling filter_sessions_since.

### read_committed_summaries(sessions_dir, since_days)
File: `src/gator_command/scripts/gator-sessions.py`
Reads `.gator/sessions/*.md` committed summary files and extracts decisions, repo, vendor, and date from their frontmatter and body.
Filesystem: `.gator/sessions/` (R)
<- `gator-audit.py` (preferred decisions source)
-> `parse_committed_summary()`
! Files starting with `_` are skipped (reserved for index/manifest files). The committed summary layer is the durable, portable read path — preferred over raw vendor logs in all audit contexts.

### parse_committed_summary(text, filename)
File: `src/gator_command/scripts/gator-sessions.py`
Parses a single committed summary markdown file (frontmatter + decisions section). Returns a structured dict or None if the file is not a valid summary. The returned dict includes a `start` field extracted from frontmatter (`start` key, falling back to `timestamp` key) for sub-day sort ordering in dashboard displays.
Filesystem: none
<- `read_committed_summaries()`, `gator-session-sink.load_committed_summaries()` (via import_sibling), `gator-audit.py` (session_summaries), `gator-repo-status.py` (recent_session_summaries)
! Used by both gator-sessions.py and gator-session-sink.py. Any change to the committed summary format (frontmatter keys, section names) must be compatible with both callers.

### get_machine_identity()
File: `src/gator_command/scripts/gator-sessions.py`
Returns stable machine identity dict by delegating to `gator-session-common.get_machine_identity()`, with a hostname-only fallback if the shared module is unavailable.
Filesystem: `~/.gator/machine-id` (R, via gator-session-common)
<- `cmd_manifest()`, `cmd_export()`

### extract_turn_text(turn)
File: `src/gator_command/scripts/gator-sessions.py`
Coerces turn content (string, list of blocks, or other) to a single flat string for indexing and preview.
Filesystem: none
<- `build_turn_record()`

### extract_tool_types(turn)
File: `src/gator_command/scripts/gator-sessions.py`
Returns sorted unique tool names from a turn's `tool_calls` list, checking both `tool` and `name` keys per call.
Filesystem: none
<- `build_turn_record()`

### extract_mentions_files(text)
File: `src/gator_command/scripts/gator-sessions.py`
Extracts file path mentions from text via regex (backtick-quoted, double-quoted, and bare paths with code extensions). Returns deduplicated list, capped at 20.
Filesystem: none
<- `build_turn_record()`

### extract_mentions_functions(text)
File: `src/gator_command/scripts/gator-sessions.py`
Extracts function and method call mentions (e.g. `foo()`, `Class.method()`) from text via regex, filtering language keywords. Returns bare names, capped at 20.
Filesystem: none
<- `build_turn_record()`

### extract_keywords(text, top_n=8)
File: `src/gator_command/scripts/gator-sessions.py`
Returns top-N keywords by frequency from text, tokenizing to 3+ char alphabetic words and excluding a built-in stopword set.
Filesystem: none
<- `build_turn_record()`

### build_turn_record(turn)
File: `src/gator_command/scripts/gator-sessions.py`
Builds a single manifest turn entry from a spool turn, including seq, role, timestamp, char count, tool types, file/function mentions, keywords, and preview.
Filesystem: none
<- `build_turn_manifest()`
-> `extract_turn_text()`, `extract_tool_types()`, `extract_mentions_files()`, `extract_mentions_functions()`, `extract_keywords()`

### build_turn_manifest(session_export)
File: `src/gator_command/scripts/gator-sessions.py`
Builds a full `gator-turn-manifest-v1` dict from a spool export dict, computing `row_key` via `_spool_slug()` and calling `build_turn_record()` for each turn.
Filesystem: none
<- `cmd_turn_manifest()`
-> `build_turn_record()`, `_spool_slug()`

### write_turn_manifest(manifest, out_path)
File: `src/gator_command/scripts/gator-sessions.py`
Writes a manifest dict as indented JSON to disk, creating parent directories as needed.
Filesystem: `~/.gator/turn-manifests/<row_key>.turns.json` (W)
<- `cmd_turn_manifest()`

### cmd_turn_manifest(args)
File: `src/gator_command/scripts/gator-sessions.py`
CLI command: generates turn manifests for all spool exports (or a single `--row-key`). Skips already-generated manifests unless `--force`.
Filesystem: `~/.gator/session-spool/` (R), `~/.gator/turn-manifests/` (W)
<- `main()` via `sessions turn-manifest`
-> `_load_spool_sessions()`, `build_turn_manifest()`, `write_turn_manifest()`

### cmd_grep_turns(args)
File: `src/gator_command/scripts/gator-sessions.py`
CLI command: searches turn manifests by file glob, function substring, keyword, vendor, repo, or role. Supports `--json` output.
Filesystem: `~/.gator/turn-manifests/*.turns.json` (R)
<- `main()` via `sessions grep-turns`

### cmd_show_turns(args)
File: `src/gator_command/scripts/gator-sessions.py`
CLI command: shows full turn content from a spool export by `--row-key` and `--seq` (comma-separated sequence numbers), with optional `--context` to include surrounding turns.
Filesystem: `~/.gator/turn-manifests/` (R for spool_file lookup), `~/.gator/session-spool/` (R for full turn content)
<- `main()` via `sessions show-turns`
-> `_load_spool_sessions()` (fallback path)

### load_spool_sessions(include_turns=False)
File: `src/gator_command/scripts/gator-session-sink.py`
Reads all spool JSON exports from `~/.gator/session-spool/`. Constructs `row_key` using the same sha256 formula as `gator-session-common.make_row_key()`.
Filesystem: `~/.gator/session-spool/*.json` (R)
<- `cmd_sink()`, `cmd_command()`
! The `row_key` formula here must remain byte-for-byte identical to `make_row_key()` in `gator-session-common.py`: `sha256("{session_id}|{source_path}")[:16]`. This is the deduplication key across spool and committed summary inputs.

### normalize_turn(turn, seq=None)
File: `src/gator_command/scripts/gator-session-sink.py`
Normalizes a vendor-specific turn to the stable database schema: seq, role, timestamp, content (always string), vendor_type, tool_calls (normalized).
Filesystem: none
<- `_insert_turns_sqlite()`, sink_duckdb turns loop
! Strips vendor-specific fields (cwd, branch, item_type). `content` is coerced to string — Codex uses lists, Claude uses strings. The `vendor_type` field is the stable equivalent of Claude's `type` and Codex's `item_type`.

### sink_sqlite(db_path, sessions, include_turns=False) / sink_duckdb(db_path, sessions, include_turns=False)
File: `src/gator_command/scripts/gator-session-sink.py`
Loads sessions into SQLite or DuckDB. Idempotent: duplicate rows are skipped via `row_key` unique constraint.
Filesystem: database file (RW)
<- `cmd_sink()`
! Schema version is tracked in `sink_metadata` table as `gator-session-sink-v2`. The turns tables (turns, tool_calls) are only created when `--include-turns` is active. Spool-only for turns — committed summaries have no turn data.
! **Input shape coupling**: both sinks access `s["pi"]` directly (SQLite line ~417, DuckDB line ~564) — the sink's INTERNAL shape uses `pi`, not `architect`. The spool-load path (`load_spool_sessions`, line ~179) converts `architect` → `pi` at construction time via `summary.get("architect", summary.get("pi", ""))`. Callers that construct session dicts and pass them to `sink_sqlite`/`sink_duckdb` DIRECTLY (bypassing spool-load) MUST include a `pi` key or they get `KeyError: 'pi'`. Extractors (`extract-{claude,codex,gemini}-sessions.py`) produce `architect`, not `pi` — direct extractor→sink pipelines need the conversion. Post-cutover cleanup opportunity: make the two `s["pi"]` sites defensive with the same `.get(...)` pattern already used in `load_spool_sessions`.

---

### read_snippets(repo_path)
File: `src/gator_command/scripts/gator-session-aggregator.py`
Reads all `.gator/session-snippets/*.json` from a repo. Returns list of SnippetRecord dicts with `data` (parsed), `raw_bytes` (for fingerprinting), `path` (for diagnostics). Skips legacy `.md` snippets and corrupt files.
Filesystem: `.gator/session-snippets/*.json` (R)
<- `get_session_summaries()`

### effective_session_key(snippet)
File: `src/gator_command/scripts/gator-session-aggregator.py`
Returns the canonical grouping key for a snippet. `"group:<repo>:<session_group_key>"` when `session_group_key` is truthy, `"legacy:<repo>:<session_id>"` otherwise. Used for aggregation grouping, cache filenames, and fingerprint lookups.
Filesystem: none (pure computation)
<- `aggregate_sessions()`, `get_session_summaries()`

### aggregate_sessions(snippets, repo_path)
File: `src/gator_command/scripts/gator-session-aggregator.py`
Groups snippets by `effective_session_key()`, applies aggregation rules (min/max timestamps, union of files/tags, goal derivation, max significance, distinct models). Computes `repo_key` from `session_cache_key(repo_path)`. Emits `session_group_key` (from vendor session identity) and `models` (sorted distinct list) in each summary. Legacy `session_id` and `model` preserved from first snippet for backward compatibility.
! `transcript_session_id` and `transcript_ref` use truthy-first pattern (same as `architect`) — empty strings are treated as missing, not as valid values.
! Cache filenames use `sha256(effective_session_key)[:16].json`. The `read_cached_summary()` and `write_cached_summary()` functions take `esk` (effective session key), not `(repo, session_id)`.
! Snippets with different effective keys are never merged, even if timestamps or transcript IDs look similar. Mixed vendor-keyed and legacy snippets stay separate.
Filesystem: none (pure computation)
<- `get_session_summaries()`
-> `effective_session_key()`, `derive_goal()`, `session_cache_key()`

### derive_goal(intents, commits)
File: `src/gator_command/scripts/gator-session-aggregator.py`
Derives a session goal from intents list. Prefers single intent; for multiples, skips release/merge/cleanup change types.
Filesystem: none
<- `aggregate_sessions()`

### snippet_fingerprint(records)
File: `src/gator_command/scripts/gator-session-aggregator.py`
Hashes raw bytes of each SnippetRecord, sorts per-file hashes, produces `sha256:` prefixed fingerprint. Order-independent.
Filesystem: none (operates on in-memory bytes)
<- `get_session_summaries()`
! Fingerprint covers full file contents — any byte change invalidates cache.

### get_session_summaries(repo_path, force_refresh)
File: `src/gator_command/scripts/gator-session-aggregator.py`
Top-level orchestrator. Reads snippets, aggregates, checks cache freshness, writes to `~/.gator/sessions/<path-hash>/`. Returns summaries sorted by started_at descending.
Filesystem: `.gator/session-snippets/*.json` (R), `~/.gator/sessions/<path-hash>/` (RW)
<- `gator-audit.py --sessions`, `gator-dashboard.py /api/audit/sessions`
-> `read_snippets()`, `aggregate_sessions()`, `snippet_fingerprint()`, cache read/write functions

### get_fleet_summaries(registry_path, force_refresh)
File: `src/gator_command/scripts/gator-session-aggregator.py`
Iterates all repos in `~/.gator/dashboard-repos.json`, calls `get_session_summaries()` for each with force_refresh passthrough. Returns merged list sorted by started_at descending. Skips missing repos gracefully.
Filesystem: `~/.gator/dashboard-repos.json` (R), per-repo snippets (R), `~/.gator/sessions/` (RW)
<- `gator-audit.py --sessions --fleet`, `gator-dashboard.py /api/audit/sessions?fleet=true`
-> `get_session_summaries()`

---

### resolve_snippet(gator_dir, full_commit_hash)
File: `src/gator_command/scripts/gator-session-block.py`
Finds exactly one snippet for a commit hash. Enforces one-to-one snippet invariant.
Filesystem: `.gator/session-snippets/*.json` (R)
<- `generate()`
! Raises `SnippetNotFound` (zero matches) or `SnippetInvariantViolation` (multiple matches).

### discover_transcript(vendor, transcript_session_id)
File: `src/gator_command/scripts/gator-session-block.py`
Searches vendor-specific local log stores by session ID. Provisional local-machine best-effort layer — vendor log directory layouts are not stable APIs.
Filesystem: `~/.claude/projects/` (R), `~/.codex/sessions/` (R), `~/.gemini/tmp/` (R)
<- `generate()`
! Raises `TranscriptNotFound` (zero) or `MultipleTranscriptsFound` (ambiguous — user must resolve manually).

### parse_claude_transcript(transcript_path)
File: `src/gator_command/scripts/gator-session-block.py`
Reads Claude Code JSONL. Returns raw turn dicts with **full, untruncated** content. Key difference from `extract-claude-sessions.py`: tool results are NOT truncated to 200 chars. Marks `is_tool_output` for anchor scanning.
Filesystem: transcript JSONL file (R)
<- `extract_interval()`

### find_commit_anchors(raw_turns, start_short_hash, end_short_hash)
File: `src/gator_command/scripts/gator-session-block.py`
Scans tool output turns only (`is_tool_output == True`) for Git commit hashes in `[branch hash]` format. Matches against short hashes from snippet metadata.
Filesystem: none
<- `extract_interval()`
! Raises `AnchorNotFound` if end hash cannot be found. Conversational text is explicitly excluded.

### extract_interval(transcript_path, vendor, start_short_hash, end_short_hash)
File: `src/gator_command/scripts/gator-session-block.py`
Dispatcher: vendor parser → `find_commit_anchors` → `normalize_turns`. Returns `(turns, capture_quality, capture_method)`.
Filesystem: transcript file (R)
<- `generate()`
-> `parse_claude_transcript()`, `find_commit_anchors()`, `normalize_turns()`

### render_session_block(turns, capture_quality, capture_method, snippet)
File: `src/gator_command/scripts/gator-session-block.py`
Builds `gator-session-block-v1` dict. All identity fields read from snippet — the snippet is the authoritative source.
Filesystem: none
<- `generate()`

### emit_session_block(gator_dir, block_data, snippet_filename_stem)
File: `src/gator_command/scripts/gator-session-block.py`
Gzip-compresses block JSON, writes to `.gator/session-blocks/`. Idempotent: no-op if identical content exists.
Filesystem: `.gator/session-blocks/` (RW)
<- `generate()`

---

## TRIPWIRE: row_key Formula Duplication

The `row_key` is computed identically in two places:
- `gator-session-common.make_row_key()`: `sha256("{session_id}|{source_path}")[:16]`
- `gator-session-sink.load_spool_sessions()`: inline hashlib code

These must remain identical. A mismatch causes the sink's deduplication to fail silently — the same session gets inserted twice with different keys.

## TRIPWIRE: Vendor Extractor Delegation Contract

All vendor extractors (`extract-claude-sessions.py`, `extract-codex-sessions.py`, `extract-gemini-sessions.py`) must:
1. Call `gator-session-common.format_summary_markdown()` for summary output (not hand-roll their own)
2. Call `gator-session-common.format_session_summary_dict()` for JSON summary output
3. Produce turns in the normalized format: `{role, content, tool_calls, timestamp, cwd, branch, session_id}`

Violating the delegation contract creates schema divergence between vendors that the audit dashboard cannot handle.

## Before Changing This Module

- The committed summary format (`gator-session-summary-v1` frontmatter) is the contract between the extraction layer and the audit/sink consumers. Adding frontmatter fields is backward-compatible; removing or renaming them breaks `parse_committed_summary()` and `gator-session-sink.load_committed_summaries()`.
- `gator-sessions.py`'s `parse_committed_summary()` is imported by `gator-session-sink.py` via `import_sibling`. It is not a pure library function — it's shared between two entry-point scripts. Test both consumers when changing the parser.
- The Gemini extractor's duplicate session ID problem is solved by the source_path component of `make_row_key()`. Do not simplify the key to session_id-only.
- `--include-turns` in the sink adds two tables (turns, tool_calls). These tables do not exist in databases loaded without this flag — don't assume they're present in downstream SQL.

## Connections

-> [scripts-core-library](scripts-core-library.md) — gator-session-common (canonical formatters, row_key, machine identity)
-> [scripts-fleet-intelligence](scripts-fleet-intelligence.md) — gator-audit.py consumes discover_all_sessions, read_committed_summaries
-> [scripts-cross-cutting](scripts-cross-cutting.md) — row_key duplication tripwire, import_sibling pattern
-> [Index](INDEX.md)
