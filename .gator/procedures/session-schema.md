# Gator Session Schema v1

The canonical format for normalized AI coding session data. All extraction scripts (Claude, Codex, Gemini, Cursor, future vendors) produce this schema. The session export API emits it. Customer databases receive it.

This is a publishable standard — external tools can produce Gator-compatible session data by conforming to this schema.

## Summary Record (for git storage)

Small, auditable, greppable. ~2-5 KB per session. Committed to git as the signed audit trail. Points to the machine where full evidence lives.

### YAML Frontmatter

```yaml
---
schema: gator-session-summary-v1
session-id: a1b2c3d4-5678-90ab-cdef-1234567890ab
date: 2026-05-30
start: 2026-05-30T14:30:00Z
end: 2026-05-30T16:45:00Z
repo: dangerous-golf
architect: AG
agent: Claude Code (Opus 4.6)
vendor: claude                    # claude|codex|gemini|cursor|other
machine-id: c5c707f5-155a-422f-9b1b-d9e8a10fea08
machine-label: alan-home-desktop
transcript: ~/.gator/session-transcripts/2026-05-30-dangerous-golf-claude.md
turns: 64 user, 78 assistant
tools: [Bash, Read, Write, Edit, Grep]
branch: dev
---
```

### Required Fields

| Field | Type | Description |
|---|---|---|
| `schema` | string | Always `gator-session-summary-v1`. Enables schema evolution |
| `session-id` | UUID | From the vendor's session storage |
| `date` | YYYY-MM-DD | Session start date |
| `start` | ISO 8601 | Session start timestamp |
| `end` | ISO 8601 | Session end timestamp (or last activity) |
| `repo` | string | Repository name (from cwd) |
| `architect` | string | Architect initials |
| `agent` | string | Agent name + model (e.g., "Claude Code (Opus 4.6)") |
| `vendor` | string | Vendor key: `claude`, `codex`, `gemini`, `cursor`, `other` |
| `machine-id` | UUID | From `~/.gator/machine-id` — stable across hostname changes |
| `machine-label` | string | Human-readable machine name (Architect-settable) |
| `transcript` | path | Full path to the local transcript file |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| `turns` | string | "N user, M assistant" — human-readable turn count |
| `tools` | list | Tools/functions used during the session |
| `branch` | string | Git branch at session time |
| `model` | string | Specific model identifier (e.g., "gpt-5.4", "gemini-3-flash-preview") |

### Body Sections

```markdown
## Goal
[First substantive Architect message — why this session started]

## Decisions
- [timestamp] Decision text [#tags] — attribution

## Files Changed
- path/to/file.py

## Charters Updated
- charter-name.md

## Evidence Location
- **Machine**: machine-label (machine-id)
- **Transcript**: full path
- **Raw source**: vendor-specific path
```

## Full Transcript Record (local storage, gitignored)

Every turn, tool call, content block. ~50-300 KB per session. Stays on the originating machine. Re-extractable from raw vendor data.

### Turn Format

```json
{
  "type": "user|assistant|system",
  "role": "user|assistant|system",
  "timestamp": "2026-05-30T14:30:00Z",
  "content": "text content",
  "tool_calls": [
    {"tool": "Read", "input_keys": ["file_path"]}
  ],
  "vendor_type": "original vendor-specific type"
}
```

### Turn Role Mapping

| Vendor | Source Role | Gator Role |
|---|---|---|
| Claude Code | `user` | `user` |
| Claude Code | `assistant` | `assistant` |
| Codex CLI | `user`, `developer` | `user` |
| Codex CLI | `assistant` | `assistant` |
| Codex CLI | `function_call` | `assistant` (tool use) |
| Codex CLI | `reasoning` | `assistant` (thinking) |
| Gemini CLI | `user` | `user` |
| Gemini CLI | `gemini` | `assistant` |
| Gemini CLI | `info`, `error` | `system` |

## Export API Format (JSON)

For `gator session-export --format json`:

```json
{
  "schema": "gator-session-export-v1",
  "exported_at": "2026-05-30T16:45:00Z",
  "machine": {
    "id": "c5c707f5-...",
    "hostname": "DESKTOP-NKSU8RO",
    "label": "alan-home-desktop"
  },
  "sessions": [
    {
      "summary": { ... },
      "turns": [ ... ]
    }
  ]
}
```

## Redaction Rules

Session data frequently contains secrets, internal paths, and customer data. The extraction scripts apply these redaction rules by default:

### Always Redact (in summaries AND transcripts)

| Pattern | Replacement | Why |
|---|---|---|
| API keys (`sk-...`, `AKIA...`, etc.) | `[REDACTED-API-KEY]` | Credentials must never persist in audit records |
| Passwords in assignments (`password = "..."`) | `[REDACTED-PASSWORD]` | Same |
| Private key material (`-----BEGIN...`) | `[REDACTED-PRIVATE-KEY]` | Same |
| Connection strings with credentials | `[REDACTED-CONNECTION-STRING]` | Database passwords embedded in URIs |
| Bearer tokens | `[REDACTED-TOKEN]` | Auth tokens |

### Redact in Summaries Only (full transcripts keep them)

| Pattern | Replacement | Why |
|---|---|---|
| Full file paths with usernames | `~/...` relative form | Privacy — don't embed `/home/jsmith/` in git |
| Environment variable values | `$ENV_VAR` (name only) | Values may be sensitive |

### Never Redact

| Data | Why it stays |
|---|---|
| File names and relative paths | Required for audit trail — "which files were touched" |
| Tool names and operations | Required for audit trail — "what did the agent do" |
| Architect messages (content) | Required for decision attribution — "what was the Architect's intent" |
| Decision tags | Required for queryability |
| Timestamps | Required for timeline |

### Redaction Implementation

The extraction scripts call `redact(text)` on all content before writing. The function is shared across vendors:

```python
import re

REDACTION_PATTERNS = [
    (r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*=\s*["\'][^"\']+["\']',
     r'\1 = "[REDACTED]"'),
    (r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']+["\']',
     r'\1 = "[REDACTED]"'),
    (r'-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----',
     '[REDACTED-PRIVATE-KEY]'),
    (r'(?i)Bearer\s+[A-Za-z0-9_-]{20,}',
     'Bearer [REDACTED-TOKEN]'),
    (r'sk-[A-Za-z0-9]{20,}',
     '[REDACTED-API-KEY]'),
    (r'AKIA[A-Z0-9]{16}',
     '[REDACTED-AWS-KEY]'),
]

def redact(text):
    """Apply redaction patterns to text. Used by all extraction scripts."""
    for pattern, replacement in REDACTION_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
```

## Schema Evolution

The `schema` field in frontmatter and export JSON enables versioned evolution:
- `gator-session-summary-v1` — current version
- Future versions add fields, never remove them
- Consumers check the schema field to know what to expect
- Old summaries remain valid — new fields are optional

## Connections

→ [Session Logging thread](../active-threads/session-logging.md) — tiered storage design
→ [Machine ID](../scripts/gator-machine-id.py) — stable machine identity
→ [Dangerous Patterns](../templates/gator-starter/reference-notes/dangerous-patterns.md) — redaction patterns overlap
