# Charter: Session Archaeology

**Covers**: `src/gator_command/scripts/extract-codex-sessions.py`, `src/gator_command/scripts/extract-gemini-sessions.py`, `src/gator_command/scripts/gator-session-aggregator.py`, `src/gator_command/scripts/gator-session-common.py`, `src/gator_command/scripts/gator_session_reader.py`

Post-Phase-3 shape (2026-08-13). The four files retired in Phase 3 (`gator-sessions.py`, `gator-session-sink.py`, `gator-session-block.py`, `extract-claude-sessions.py`) are gone from the source tree — their content is in git history only. Function entries below cover the surviving surface. The two remaining vendor extractors (`extract-codex-sessions.py`, `extract-gemini-sessions.py`) are Phase-4-deferred per parent plan §5 decision 2(b): they retire once Enterprise-side Codex + Gemini adapters ship, and `gator-session-common.py`'s vendor helpers retire with them in the same Phase 4 pass.

## Owns

Snippet-based session pipeline (surviving surface) + Phase-4-deferred vendor extractors.

- `gator-session-aggregator.py` owns the snippet-to-summary pipeline: reads v2 JSON snippets from `.gator/session-snippets/*.json`, aggregates by `(repo, session_id)`, caches summaries at `~/.gator/sessions/<path-hash>/`. Importable library — no CLI entry point. Consumers: `gator-dashboard.py` (Audit view API), `gator-audit.py::_handle_sessions()` (CLI `--sessions`).
- `gator_session_reader.py` owns the surviving committed-summary reader contract + machine identity. Three functions: `parse_committed_summary()` (extracted from `gator-sessions.py` in Phase 2A, 2026-08-12), `read_committed_summaries()` (same origin), and `get_machine_identity()` (folded from `gator-session-common.py` in Phase 3F, 2026-08-13). Importable library — no CLI. Consumers: `gator-audit.py` (snippet-based decisions_source + machine identity), `gator-repo-status.py` (recent sessions panel), `tests/test_audit_integration.py`, `tests/test_session_reader.py`. Byte-identical parse/read/identity behavior to the originals.
- `gator-session-common.py` — **Phase-4-deferred retirement**. Retains 7 vendor-formatting helpers used by the Phase-4-deferred Codex + Gemini extractors: `redact()`, `extract_intelligence()`, `make_row_key()`, `make_transcript_path()`, `format_summary_frontmatter()`, `format_summary_markdown()`, `format_session_summary_dict()`. Also retains a copy of `get_machine_identity()` for internal use by the formatters — same behavior as the reader's copy; both retire in Phase 4. See [`scripts-core-library`](scripts-core-library.md) for the per-function entries.
- `extract-codex-sessions.py` — Codex CLI session archaeology (**Phase-4-deferred retirement**). Reads `~/.codex/sessions/` with normalized turn format; delegates all summary formatting to `gator-session-common`.
- `extract-gemini-sessions.py` — Gemini CLI session archaeology (**Phase-4-deferred retirement**). Reads `~/.gemini/tmp/` with the same delegation pattern. Gemini is the only vendor with genuine duplicate session IDs across files — `make_row_key()` handles this.

## Does Not Own

- Machine identity storage — that is `gator-machine-id.py` (standalone CLI) + the two reader-side canonical copies noted above.
- Summary formatting logic — the Phase-4-deferred vendor extractors delegate to `gator-session-common.format_summary_markdown()` and `format_session_summary_dict()`. See [`scripts-core-library`](scripts-core-library.md).
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
Returns `{id, hostname, label}` for the current machine. Creates `~/.gator/machine-id` on first call using `gator-machine-id.py`'s storage format. Folded from `gator-session-common.py:33` in Phase 3F (2026-08-13).
Filesystem: `~/.gator/machine-id` (R, W on creation)
<- `gator-audit.py::assemble_audit_data()` (data["machine"])
! Duplicate copy exists in `gator-session-common.py:33` during the Phase 3→4 window. Both must stay in sync. Rationale for the duplicate: session-common's internal formatters call `get_machine_identity()`, and retargeting them to the reader would add an `import_sibling` from the retiring file (architecturally backward). Phase 4 sweeps session-common and its copy with the Codex/Gemini extractors. See [`scripts-core-library`](scripts-core-library.md) for the sync obligation.

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

## TRIPWIRE: get_machine_identity() Phase-3→4 Duplicate Copies

`gator_session_reader.get_machine_identity()` and `gator-session-common.get_machine_identity()` are byte-identical during the Phase-3→4 window. Both must stay in sync. Phase 4 sweeps session-common with the Codex/Gemini extractors; the reader's copy becomes sole owner. If a change to machine-id storage lands during this window (e.g. new field in `~/.gator/machine-id`), update BOTH copies in the same commit.

## TRIPWIRE: Vendor Extractor Delegation Contract

The Phase-4-deferred extractors (`extract-codex-sessions.py`, `extract-gemini-sessions.py`) must:
1. Call `gator-session-common.format_summary_markdown()` for summary output (not hand-roll their own)
2. Call `gator-session-common.format_session_summary_dict()` for JSON summary output
3. Produce turns in the normalized format: `{role, content, tool_calls, timestamp, cwd, branch, session_id}`

Violating the delegation contract creates schema divergence that the audit dashboard cannot handle. Contract retires in Phase 4 when both extractors + session-common retire together.

## Before Changing This Module

- The committed summary format (`gator-session-summary-v1` and `gator-commit-summary-v1` frontmatter) is the contract between summary producers (pre-commit hook, legacy archaeology output) and `parse_committed_summary()`. Adding frontmatter fields is backward-compatible; removing or renaming them breaks the parser and both its consumers.
- The Gemini extractor's duplicate session ID problem is solved by the source_path component of `make_row_key()`. Do not simplify the key to session_id-only.
- Phase 4 sweep obligations: when Enterprise-side Codex + Gemini adapters ship, retire `extract-codex-sessions.py`, `extract-gemini-sessions.py`, `gator-session-common.py` (with its duplicate `get_machine_identity()` copy), the "Vendor Extractor Delegation Contract" TRIPWIRE, and the "get_machine_identity() Phase-3→4 Duplicate Copies" TRIPWIRE — all in the same commit for atomic retirement.

## Connections

-> [scripts-core-library](scripts-core-library.md) — gator-session-common (retained vendor formatters, row_key, machine identity duplicate)
-> [scripts-fleet-intelligence](scripts-fleet-intelligence.md) — gator-audit.py::assemble_audit_data consumes gator_session_reader
-> [scripts-cross-cutting](scripts-cross-cutting.md) — parse_committed_summary single-owner tripwire, import_sibling pattern
-> [scripts-dashboard](scripts-dashboard.md) — gator-repo-status.py::get_session_summaries populates recent-sessions panel
-> [Index](INDEX.md)
