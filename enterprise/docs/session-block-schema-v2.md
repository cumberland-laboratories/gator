# Session Block Schema v2

> **HISTORICAL — pre-transcripts-first (2026-08-08).** This schema describes the retired per-commit session-block artifact shape (compressed `.json.gz` files committed to `.gator/session-blocks/`). Under the current transcripts-first MVP, evidence is raw transcripts uploaded to Enterprise-managed storage (DB + blob store), keyed by content hash — schema-less at the storage layer, with metadata in `transcript_sessions` per Migration 009. Retained for architectural context; do NOT use as guidance for new work. See [`../../.gator/vault/artifacts/2026-08-08-enterprise-transcripts-first-mvp-implementation-plan.md`](../../.gator/vault/artifacts/2026-08-08-enterprise-transcripts-first-mvp-implementation-plan.md) for the current design.

**Schema identifier**: `gator-session-block-v2`

## Purpose

A session block is a **lossless transcript slice for one commit interval** — the exact conversation between a developer and an AI model that produced a specific commit. Compressed as `.json.gz`, committed to Git, indexed by Enterprise.

## Naming Contract

```
Snippet:  .gator/session-snippets/<date>-<repo>-<commit13>.json
Block:    .gator/session-blocks/<date>-<repo>-<commit13>.json.gz
```

Given a snippet filename, the block path is deterministic: replace `session-snippets` with `session-blocks`, append `.gz`. This is a hard contract — Enterprise depends on it for lookup.

## Canonicalization

The `content_sha256` hash requires deterministic serialization and a **two-pass process** because the hash is stored inside the document it hashes.

### Writer (generation)

```python
# 1. Build payload with content_sha256 set to empty string
payload["content_sha256"] = ""

# 2. Canonicalize and hash
canonical_bytes = json.dumps(
    payload,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")

content_sha256 = hashlib.sha256(canonical_bytes).hexdigest()

# 3. Insert the computed hash into the payload
payload["content_sha256"] = content_sha256

# 4. Re-canonicalize (now with the hash) and compress
final_bytes = json.dumps(
    payload,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")

compressed = gzip.compress(final_bytes, compresslevel=6)
```

### Reader (verification)

```python
# 1. Decompress and parse the JSON
block = json.loads(gzip.decompress(raw_bytes))

# 2. Extract the expected hash
expected = block["content_sha256"]

# 3. Set content_sha256 to empty string (reproduce writer's step 2)
block["content_sha256"] = ""

# 4. Canonicalize and hash
canonical = json.dumps(block, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
actual = hashlib.sha256(canonical).hexdigest()

# 5. Compare
assert actual == expected
```

### Rules
- UTF-8 encoding
- Sorted JSON keys
- Compact separators (no spaces)
- `ensure_ascii=False` (preserve unicode)
- UTC timestamps with `Z` suffix
- Normalized line endings to `\n`
- `content_sha256` is always set to `""` before hashing, then replaced with the computed hash

## Schema

```json
{
  "schema": "gator-session-block-v2",
  "type": "session_block",
  "content_policy": "raw",

  "target_commit": "abc1234567890abcdef1234567890abcdef1234",
  "short_commit": "abc1234",
  "snippet_id": "snippet-abc1234567890",
  "repo_relpath": ".gator/session-snippets/2026-07-12-my-repo-abc1234567890.json",

  "vendor": "anthropic",
  "vendor_session_id": "provider-native-session-id",

  "capture_mode": "exact",
  "capture_quality": "exact",
  "captured_at": "2026-07-12T14:00:00Z",
  "content_sha256": "sha256-of-canonical-plaintext-bytes",

  "turn_count": 31,
  "interval": {
    "start_anchor": "commit-sha-or-marker",
    "end_anchor": "commit-sha-or-marker",
    "start_time": "2026-07-12T13:30:00Z",
    "end_time": "2026-07-12T14:00:00Z"
  },

  "turns": [
    {
      "role": "user",
      "timestamp": "2026-07-12T13:41:00Z",
      "content": "..."
    },
    {
      "role": "assistant",
      "timestamp": "2026-07-12T13:41:05Z",
      "content": "...",
      "tool_calls": [
        {"tool": "Read", "input_keys": ["file_path"]}
      ]
    },
    {
      "role": "tool_result",
      "timestamp": "2026-07-12T13:41:06Z",
      "content": "..."
    }
  ],

  "attachments": [],

  "source_metadata": {
    "gator_version": "1.8.10",
    "capture_host_id": "machine-id-from-gator",
    "transcript_locator_kind": "claude"
  }
}
```

## Field Reference

### Identity

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema` | string | yes | Always `"gator-session-block-v2"` |
| `type` | string | yes | Always `"session_block"` |
| `content_policy` | string | yes | Always `"raw"` for this phase |

### Commit Linkage

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target_commit` | string | yes | Full 40-char SHA of the commit this block describes |
| `short_commit` | string | yes | First 7 chars of the commit SHA |
| `snippet_id` | string | yes | Identifier linking to the corresponding snippet |
| `repo_relpath` | string | yes | Relative path to the snippet file in the repo |

### Vendor

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vendor` | string | yes | `anthropic`, `openai`, `google`, or `unknown` |
| `vendor_session_id` | string | no | Provider-native session ID (if available) |

### Capture

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `capture_mode` | string | yes | Always `"exact"` for this phase |
| `capture_quality` | string | yes | `exact`, `best_effort`, `partial`, `missing_head`, `missing_tail` |
| `captured_at` | string | yes | ISO 8601 timestamp of when the block was generated |
| `content_sha256` | string | yes | SHA-256 hash of canonical plaintext bytes (NOT compressed bytes) |

### Content

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `turn_count` | integer | yes | Number of turns in the `turns` array |
| `interval` | object | yes | Start/end anchors and timestamps for the transcript slice |
| `turns` | array | yes | Ordered list of conversation turns |
| `attachments` | array | yes | Empty array for this phase (reserved for future use) |

### Turns

Each turn in the `turns` array:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | yes | `user`, `assistant`, or `tool_result` |
| `timestamp` | string | no | ISO 8601 timestamp of the turn |
| `content` | string | yes | Turn content (text, code, tool output) |
| `tool_calls` | array | no | Tool invocations (assistant turns only) |

### Source Metadata

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_metadata.gator_version` | string | yes | Gator version that generated the block |
| `source_metadata.capture_host_id` | string | yes | Machine identifier (from `~/.gator/machine-id`) |
| `source_metadata.transcript_locator_kind` | string | yes | `claude`, `codex`, `gemini`, or `other` |

## Capture Quality Values

| Value | Meaning |
|-------|---------|
| `exact` | Start and end anchors found in transcript. Complete interval. |
| `best_effort` | Heuristic boundaries. Likely complete but not guaranteed. |
| `partial` | Some turns missing. Known incomplete. |
| `missing_head` | Start anchor not found. Transcript may begin mid-interval. |
| `missing_tail` | End anchor not found. Transcript may end mid-interval. |

## Changes from v1

| Aspect | v1 | v2 |
|--------|----|----|
| `content_sha256` | absent | required — integrity verification after decompression |
| `capture_mode` | absent | `exact` (reserved for future modes) |
| `capture_quality` | `capture_quality` with fewer values | expanded to 5 values |
| `vendor` | absent | required — `anthropic`, `openai`, `google`, `unknown` |
| `vendor_session_id` | absent | optional — provider-native session ID |
| `repo_relpath` | absent | required — path to corresponding snippet |
| `interval.start_time/end_time` | absent | required — ISO 8601 timestamps |
| `source_metadata.gator_version` | absent | required |
| `source_metadata.capture_host_id` | absent | required — machine identity |
| `session_id` | present | renamed to `snippet_id` for clarity |
| `capture_status` | present | removed (replaced by `capture_quality`) |
| `capture_method` | present | removed (always commit-hash-anchors) |
| `binary_content` | present | removed (always excluded) |
| `metrics` | present | removed (derivable from `turns`) |
