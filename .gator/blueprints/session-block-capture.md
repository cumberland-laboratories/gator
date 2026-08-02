# Session-Block Capture

## What This Page Is

This page explains session-block companion capture: the system that extracts exact transcript slices for each commit interval and stores them as compressed local artifacts.

It covers:

- what a session block is and how it differs from a snippet or summary
- the end-to-end capture flow
- where data comes from and where it lands
- what works today and what is intentionally deferred
- the known fragile edges and design constraints

If the Architect asks "how do I get the actual transcript content for a specific commit?" this page should answer it.

## Core Position

Session blocks are the evidence layer between snippets and full transcripts.

A snippet tells you *which* session produced a commit. A session block tells you *what was said* during that commit's working interval. A full transcript gives you the entire session.

The block is the narrowest useful slice: just the turns between two commit boundaries, with full untruncated content. It is the artifact that answers:

> What conversation and tool output immediately produced this commit?

## Why This Exists

Snippets are metadata-only: they capture identity, files touched, decision tags, and timing. They are excellent for traceability and search but they carry zero conversation content.

Full transcripts carry everything but are large, ephemeral (vendor storage is not durable), and session-scoped rather than commit-scoped. Loading a 2000-turn transcript to understand one commit is like reading an entire book to find one paragraph.

Session blocks bridge this gap. They are:

- **commit-scoped**: one block per commit, covering exactly the turns since the previous commit
- **full-fidelity**: tool results are untruncated, unlike summary-layer extracts
- **compressed**: gzip-compressed JSON, typically 10-50KB per commit interval
- **local-only**: gitignored by default, never committed to repo history
- **on-demand**: CLI-first capture, no hook integration yet

This is the first concrete implementation of what the [Session Intelligence](session-intelligence.md) blueprint calls "Priority 3: commit-linked snippet artifacts" — but with full transcript content rather than abbreviated conversation spines.

## The Four-Layer Model (Updated)

| Layer | Purpose | Content | Durability | In git? |
|-------|---------|---------|------------|---------|
| Snippet | Commit-to-session traceability | Metadata only | Durable | Yes |
| **Session block** | **Commit-scoped transcript slice** | **Full turns** | **Local** | **No** |
| Summary | Discovery index | Abbreviated spine | Durable | Yes |
| Full transcript | Complete session replay | Everything | Vendor-dependent | No |

The session block sits between the snippet (which has no content) and the full transcript (which has too much). It is the right-sized artifact for commit forensics.

## Current State

Status: `MVP — CLI-first, on-demand capture`

What works today:

- `gator session-blocks generate --commit <commit-ish>` captures a block for any commit with a v1.3.0+ snippet
- Claude Code transcript discovery and parsing with full untruncated content
- Codex CLI and Gemini CLI discovery paths wired (vendor names mapped correctly)
- Anchor detection from tool output only (conversational mentions excluded)
- Gzip-compressed `.json.gz` output to `.gator/session-blocks/`
- Idempotent: re-running for the same commit produces identical output
- Gitignore propagation through install, upgrade, and deploy paths
- 33 tests covering all layers

What is intentionally deferred:

- Hook-driven automatic capture at commit time
- Dashboard wiring (block viewer, retrieval API)
- Encryption or promotion workflow
- Template copy for governed repos (not needed until hook-driven capture)
- Historical recovery (this is a same-machine, recent-session tool)

## Prerequisite: The Session Identity Pipeline

Session-block capture depends on the session identity pipeline (v1.3.0+). This pipeline is what puts `transcript_session_id` into snippets — the join key that connects a commit to its vendor transcript. Without it, block generation has no way to find the right transcript file.

### Vendor SessionStart Hooks

When a vendor CLI (Claude Code, Codex CLI, Gemini CLI) starts a session, it fires a `SessionStart` hook with JSON metadata on stdin. Gator installs a handler for this hook in each vendor's settings file:

| Vendor | Settings file | Hook command |
|--------|--------------|--------------|
| Claude Code | `.claude/settings.json` | `python .gator/scripts/gator-session-start.py` |
| Codex CLI | `.codex/hooks.json` | `python .gator/scripts/gator-session-start.py` |
| Gemini CLI | `.gemini/settings.json` | `python .gator/scripts/gator-session-start.py` |

All three use the same script. The templates live at `src/gator_command/templates/gator-starter/vendor-hooks/` and are installed by `gator-update.py`'s `install_vendor_hooks()` during both `gatorize` and `gator update`. The install is merge-safe — it injects Gator's hook into existing vendor settings without clobbering other user configuration (permissions, environment variables, other hooks).

### What the Hook Captures

`gator-session-start.py` reads the vendor's JSON payload from stdin, extracts:

- **`vendor_session_id`** — the session UUID (the critical join key)
- **`vendor`** — which vendor (detected from payload fields or model name hints)
- **`model`** — which model, if provided
- **`transcript_path`** — the local file path where the vendor stores the transcript
- **`started_at`** — session start timestamp

It writes these to `.gator/active-vendor-session.json` (gitignored, machine-local). This file persists across commits within the same session and is overwritten when a new session starts.

Design constraints on the hook script:

- **Always exits 0** — never blocks the vendor session, even on malformed or missing input
- **Never writes to stdout** — vendors may interpret stdout as hook output
- **Atomic write** — uses temp file + rename to prevent partial reads by the pre-commit hook
- **Cross-vendor** — handles flat and nested payload shapes from all three vendors
- **49 unit tests** — covering all vendor payload formats, edge cases, and failure modes

### How the Session ID Reaches the Snippet

At commit time, `gator-pre-commit.py` phase_cleanup reads `.gator/active-vendor-session.json` and writes two fields into the snippet:

- **`transcript_session_id`** — the vendor session UUID (the join key for block generation)
- **`session_group_key`** — `vendor:uuid` format, used by the aggregator to group commits from the same session

The `transcript_path` is deliberately *not* written to the snippet — it's a machine-local path that isn't portable across clones. The snippet carries the UUID; the block generator uses that UUID to re-discover the transcript at generation time.

### Why `gator init` Is Separate

The SessionStart hook runs `gator-session-start.py` only — it does not run `gator init` (the branded boot sequence with status display, hook self-heal, and dashboard registration). This separation is deliberate:

- **Speed**: the SessionStart hook runs on every session start across every repo. It must be fast (< 1 second) and invisible.
- **Safety**: `gator init` writes to stdout and may modify state (hook repair, registry updates). A SessionStart hook that fails visibly or takes too long would train users to disable it.
- **Scope**: session identity capture is infrastructure. The boot sequence is user-facing. Mixing them creates a fragile dependency — a broken boot display would silently break evidence capture.

`gator init` is run by the agent at conversation start (via the constitution's session-opening procedure), not by a vendor hook. The two paths converge at commit time when the snippet is emitted.

## How Capture Works

### Prerequisites

Block generation requires three things to be true simultaneously:

1. The commit has a **v1.3.0+ snippet** with `transcript_session_id` populated (which requires the SessionStart hook to have fired)
2. The vendor transcript **still exists on this machine**
3. The commit's **short hash appears in tool output** within the transcript (Git's `[branch hash]` format)

If any of these fail, the tool exits with a diagnostic message explaining which precondition was not met.

### End-to-End Flow

```
gator session-blocks generate --commit abc1234
```

1. **Resolve commit** — `git rev-parse` normalizes any commit-ish (short hash, HEAD, branch name) to a full 40-char hash.

2. **Find snippet** — Scans `.gator/session-snippets/*.json` for exactly one snippet matching the full hash. Zero → error. Multiple → invariant violation error.

3. **Check identity pipeline** — Reads `transcript_session_id` from the snippet. If null (pre-v1.3.0 snippet), exits with a clear message.

4. **Discover transcript** — Searches vendor-specific local log stores by session UUID:
   - **Claude Code** (`anthropic`): `~/.claude/projects/*/<uuid>.jsonl`
   - **Codex CLI** (`openai`): `~/.codex/sessions/*/*/rollout-*-<uuid>.jsonl`
   - **Gemini CLI** (`google`): `~/.gemini/tmp/*/chats/session-*-<uuid>.json`
   - **Unknown vendor**: searches all three paths

   Zero matches → error. Multiple matches → error with candidate paths listed.

5. **Resolve anchors** — Determines the transcript interval boundaries:
   - **End anchor**: current snippet's `short_commit` field
   - **Start anchor**: previous snippet's `short_commit` field (via `previous_commit_in_session`), falling back to `git rev-parse --short` if the previous snippet is missing
   - **First commit**: no start anchor, interval starts at transcript beginning

6. **Parse transcript** — Reads the vendor JSONL/JSON file into raw turn dicts. Unlike `extract-claude-sessions.py`, tool results are **not truncated**. Each turn is tagged with `is_tool_output` for anchor scanning.

7. **Find anchors in tool output** — Scans only `is_tool_output == True` turns for the regex `\[[\w./-]+ ([a-f0-9]{7,})\]` (Git commit output format). Matches against short hashes. Both anchors must be found if both were provided; a missing start anchor is a hard failure, not a silent fallback.

8. **Normalize and render** — Slices the transcript to the anchor range, maps roles to canonical names (`user` → `human`, tool results → `tool_result`), assigns 1-indexed sequence numbers, and builds the `gator-session-block-v1` envelope with all identity fields from the snippet.

9. **Emit** — Gzip-compresses the block JSON and writes to `.gator/session-blocks/<snippet-stem>.json.gz`. Idempotent: identical content is not rewritten.

### Capture Quality

| Scenario | Quality | Meaning |
|----------|---------|---------|
| Both start and end anchors found in tool output | `exact` | The interval is precisely bounded by two commit events |
| First commit in session (no start anchor) | `bounded` | The interval starts at transcript beginning, which may include setup or cross-repo chatter |

There is no `approximate` or `best-effort` quality level in MVP. If anchors cannot be found, capture fails loudly rather than producing unreliable evidence.

## Block Schema

Schema: `gator-session-block-v1`

```json
{
  "schema": "gator-session-block-v1",
  "type": "session_block",
  "target_commit": "full-40-char-hash",
  "short_commit": "abc1234",
  "snippet_id": "snippet-abc1234",
  "session_id": "20260621-claude-opus-4-6-120000",
  "session_group_key": "anthropic:uuid",
  "transcript_session_id": "uuid",
  "repo": "gator-command",
  "branch": "main",
  "commit_index": 3,
  "previous_commit_in_session": "full-hash-or-null",
  "started_at": "ISO-8601",
  "ended_at": "ISO-8601",
  "capture_status": "captured",
  "capture_quality": "exact",
  "capture_method": "commit-hash-anchors",
  "content_policy": "raw",
  "binary_content": "excluded",
  "vendor": "anthropic",
  "model": "claude-opus-4-6",
  "turn_count": 42,
  "turns": [
    {
      "seq": 1,
      "role": "human",
      "ts": "ISO-8601",
      "content": "full untruncated content",
      "tool_calls": [{"tool": "Edit", "input_keys": ["file_path", "old_string", "new_string"]}]
    }
  ],
  "metrics": {
    "human_turns": 5,
    "assistant_turns": 30,
    "tool_result_turns": 7
  },
  "generated_at": "ISO-8601"
}
```

Key design choices:

- **All identity fields come from the snippet**, not from the transcript. The snippet is the authoritative source for commit-session linkage.
- **`content_policy: "raw"`** means content is unredacted. Future encryption or redaction would change this field.
- **`binary_content: "excluded"`** means binary tool results (images, PDFs) are not captured.
- **Roles are canonical**: `human`, `assistant`, `tool_result`, `system` — not vendor-specific.

## Storage and Lifecycle

### Where Blocks Live

`.gator/session-blocks/<snippet-stem>.json.gz`

The filename stem matches the snippet filename, creating a 1:1 naming correspondence:
- Snippet: `.gator/session-snippets/2026-06-21-gator-command-abc1234.json`
- Block: `.gator/session-blocks/2026-06-21-gator-command-abc1234.json.gz`

### Why Local-Only

Session blocks contain full untruncated transcript content, which may include:

- file contents read by the agent
- tool output with system paths and environment details
- conversational context that is useful for forensics but inappropriate for public repos

Gitignore rules are propagated through all three paths:
- `gatorize.py` `ensure_repo_gitignore()` (install and upgrade)
- `gator-update.py` gitignore convergence (normal update cycles)
- `gator-deploy.py` `ROOT_GITIGNORE` (public clone deployment)

### Retention

Session blocks are retained indefinitely on the local machine. There is no automatic cleanup. The user can delete `.gator/session-blocks/` at any time without affecting governance state.

Future work may add:
- promotion to a durable archive backend
- encryption at rest
- retention policies

## Known Constraints and Fragile Edges

### Vendor Transcript Discovery Is Best-Effort

Vendor log directory layouts are not stable APIs. They may change after a CLI update. The discovery layer is a provisional local-machine heuristic, not a guaranteed resolution.

Expected failure cases:
- Transcript cleaned up by vendor (retention policies, disk space)
- Commit was made on a different machine than where `generate` is run
- Vendor CLI updated and changed its log directory layout

These all produce loud failures with diagnostic messages, not silent data loss.

### Anchor Detection Requires Tool Output

The anchor scanner only matches commit hashes in `is_tool_output == True` turns. This means:

- A commit hash mentioned in conversation (e.g., "I just committed abc1234") is **not** an anchor
- A commit made outside the transcript (e.g., manual `git commit` in another terminal) will not have an anchor

This is a deliberate design choice: anchors must come from evidence of execution, not discussion.

### One-to-One Snippet Invariant

Each commit must have exactly one snippet. Multiple snippets for the same commit hash is treated as an invariant violation and fails loudly. This invariant is enforced by the hook pipeline and validated here.

### Pre-v1.3.0 Snippets

Snippets from before the session-identity pipeline (v1.3.0) have `transcript_session_id: null`. Block generation is not possible for these commits. The error message explains why and directs the user to the version requirement.

## Participating Modules

| Module | Role |
|--------|------|
| `gator-session-start.py` | Vendor SessionStart hook — captures session UUID to `active-vendor-session.json` |
| `gator-pre-commit.py` | Reads `active-vendor-session.json` at commit time, writes `transcript_session_id` into snippet |
| `gator-session-block.py` | Extraction engine and CLI entry point — reads `transcript_session_id` from snippet |
| `cli.py` | Registers `session-blocks` subcommand |
| `gator-update.py` | Installs vendor hook configs via `install_vendor_hooks()`, propagates gitignore rule |
| `gatorize.py` | Propagates gitignore rule on install/upgrade |
| `gator-deploy.py` | Includes gitignore rule in public clone template |

Vendor hook templates:
- `src/gator_command/templates/gator-starter/vendor-hooks/claude-settings.json`
- `src/gator_command/templates/gator-starter/vendor-hooks/codex-hooks.json`
- `src/gator_command/templates/gator-starter/vendor-hooks/gemini-settings.json`

The block script is deployed to two locations:
- `src/gator_command/scripts/gator-session-block.py` — package/CLI copy
- `.gator/scripts/gator-session-block.py` — command-post dogfooding copy

These must stay in sync (documented in [scripts-cross-cutting charter](../charters/scripts-cross-cutting.md)).

## Connections

- [Session Intelligence](session-intelligence.md) — parent blueprint, four-layer model, forensic dimensions
- [Commit Pipeline](commit-pipeline.md) — the commit event that produces snippets, which blocks are derived from
- [Hook Pipeline](hook-pipeline.md) — git hooks (pre-commit/commit-msg/post-commit) that emit snippets; future hook-driven automatic capture would integrate here
- [Session Summary Aggregator](session-summary-aggregator.md) — the aggregation layer that groups snippets by `session_group_key`
- [Install And Upgrade](install-and-upgrade.md) — vendor hook installation and gitignore propagation paths
