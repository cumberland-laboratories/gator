# Charter: Session Archaeology

**Covers**: `src/gator_command/scripts/gator-session-aggregator.py`, `src/gator_command/scripts/gator_session_reader.py`

Post-sweep shape (2026-08-16). Seven files retired across the non-Enterprise session cleanup: four in Phase 3 (2026-08-13: `gator-sessions.py`, `gator-session-sink.py`, `gator-session-block.py`, `extract-claude-sessions.py`) and three in the final sweep (2026-08-16: `extract-codex-sessions.py`, `extract-gemini-sessions.py`, `gator-session-common.py`) — content in git history only. The sweep fired once its ratified gate was met: Enterprise-side Codex (Commit L `f7ef4c2`) + Gemini (Commit M `25dbc58`) adapters landed with ≥1 real linked commit each. Base Gator now emits governance metadata (snippets) only; Enterprise owns transcript custody, parsing, and cross-session audit retrieval.

## Owns

Snippet-based session pipeline — the entire surviving surface.

- `gator-session-aggregator.py` owns the snippet-to-summary pipeline: reads v2 JSON snippets from `.gator/session-snippets/*.json`, aggregates by `(repo, session_id)`, caches summaries at `~/.gator/sessions/<path-hash>/`. Importable library — no CLI entry point. Consumers: `gator-dashboard.py` (Audit view API), `gator-audit.py::_handle_sessions()` (CLI `--sessions`).
- `gator_session_reader.py` owns the surviving committed-summary reader contract + machine identity. Three functions: `parse_committed_summary()` (extracted from `gator-sessions.py` in Phase 2A, 2026-08-12), `read_committed_summaries()` (same origin), and `get_machine_identity()` (folded from `gator-session-common.py` in Phase 3F, 2026-08-13; **sole owner since the 2026-08-16 sweep** deleted session-common's duplicate copy). Importable library — no CLI. Consumers: `gator-audit.py` (snippet-based decisions_source + machine identity), `gator-repo-status.py` (recent sessions panel), `tests/test_audit_integration.py`, `tests/test_session_reader.py`.

## Does Not Own

- Machine identity storage — that is `gator-machine-id.py` (standalone CLI); the reader owns the canonical read/create helper.
- Vendor transcript discovery, parsing, and custody — Enterprise-side since the audit-surface tranche: `enterprise/enterprise-cli/gator_enterprise_cli/transcripts_discovery.py` (Claude + Codex + Gemini). See [`scripts-enterprise`](scripts-enterprise.md).
- Fleet-level decision assembly for the audit dashboard — that is `gator-audit.py::assemble_audit_data()`.
- The committed summary read path in the audit — `gator-audit.py` calls `gator_session_reader.read_committed_summaries()`.
- The committed summary read path in repo-status — `gator-repo-status.py::get_session_summaries()` calls `gator_session_reader.read_committed_summaries()` via `import_sibling("gator_session_reader")`.

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

### get_machine_identity()
File: `src/gator_command/scripts/gator_session_reader.py`
Returns `{id, hostname, label}` for the current machine. Creates `~/.gator/machine-id` on first call using `gator-machine-id.py`'s storage format. Folded from `gator-session-common.py:33` in Phase 3F (2026-08-13); sole owner since the 2026-08-16 sweep retired session-common and its duplicate copy.
Filesystem: `~/.gator/machine-id` (R, W on creation)
<- `gator-audit.py::assemble_audit_data()` (data["machine"])

### parse_committed_summary(text, filename="")
File: `src/gator_command/scripts/gator_session_reader.py`
Parses one `.gator/sessions/*.md` committed summary (frontmatter + `## Goal` + `## Decisions`) into a structured dict. Handles both schemas: `gator-session-summary-v1` (legacy archaeology format, still readable) and `gator-commit-summary-v1` (pre-commit hook, primary source). Returns None if no frontmatter.
Filesystem: none
<- `read_committed_summaries()`, `gator-audit.py::_committed_decisions_from_snippets()` (remote-cache path)
! Byte-identical to the original in the retired `gator-sessions.py:1044`. Sole owner post-Phase-3 (the Phase-3-Commit-E sweep removed the legacy copy).

### read_committed_summaries(sessions_dir, since_days=7)
File: `src/gator_command/scripts/gator_session_reader.py`
Reads `.gator/sessions/*.md` in a directory, filters by filename-date against `since_days`, parses each via `parse_committed_summary()`. Returns list of summary dicts. Empty list on missing dir.
Filesystem: `.gator/sessions/` (R)
<- `gator-audit.py::_committed_decisions_from_snippets()`, `gator-repo-status.py::get_session_summaries()`
! Filename-date filter uses the first 10 chars of the filename (`YYYY-MM-DD-...`). Files without a leading date are always parsed (no filename filter possible).

---

## TRIPWIRE: parse_committed_summary() Single-Owner Contract

Post-Phase-3 the parser has exactly one owner (`gator_session_reader.py`) and two consumers (`gator-audit.py`, `gator-repo-status.py`). Any change to the committed-summary schema (frontmatter field names, section headers `## Goal` / `## Decisions`, return dict shape) must land in the single owner. See [`scripts-cross-cutting`](scripts-cross-cutting.md) for the full tripwire.

## Before Changing This Module

- The committed summary format (`gator-session-summary-v1` and `gator-commit-summary-v1` frontmatter) is the contract between summary producers (pre-commit hook, legacy archaeology output) and `parse_committed_summary()`. Adding frontmatter fields is backward-compatible; removing or renaming them breaks the parser and both its consumers.
- Vendor-transcript work belongs Enterprise-side. Do not reintroduce base-Gator vendor-log readers — the 2026-08-16 sweep's whole point was closing that surface. The duplicate-session-ID pathology the retired `make_row_key()` handled for Gemini is now handled by Enterprise's Migration 011 `session_qualifier` (see [`scripts-enterprise`](scripts-enterprise.md) Commit M block).

## Connections

-> [scripts-enterprise](scripts-enterprise.md) — Enterprise-side vendor transcript discovery + custody (successor to the retired extractors)
-> [scripts-fleet-intelligence](scripts-fleet-intelligence.md) — gator-audit.py::assemble_audit_data consumes gator_session_reader
-> [scripts-cross-cutting](scripts-cross-cutting.md) — parse_committed_summary single-owner tripwire, import_sibling pattern
-> [scripts-dashboard](scripts-dashboard.md) — gator-repo-status.py::get_session_summaries populates recent-sessions panel
-> [Index](INDEX.md)
