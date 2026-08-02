---
schema-id: gator-session-summary-v1
kind: markdown-with-yaml-frontmatter
emitter: src/gator_command/scripts/gator-session-common.py::format_summary_frontmatter (canonical); vendor extractors call this rather than hand-rolling
consumer: Enterprise session-ledger pipeline (planned), local session archaeology
version: 1
---

# gator-session-summary-v1

## What it is

A **per-vendor-session** markdown summary — one file per vendor-side AI
session (Claude Code conversation, Codex chat, etc.), written to
`~/.gator/session-transcripts/` on the operator's machine. This is
distinct from `gator-commit-summary-v1`: sessions span many commits;
commit summaries span one.

The canonical writer is `format_summary_frontmatter` +
`format_summary_markdown` in `src/gator_command/scripts/gator-session-common.py`.
Vendor extractors (Claude Code, Codex) call these shared helpers so all
vendors emit the same shape.

## File location and naming

```
~/.gator/session-transcripts/{YYYY-MM-DD}-{repo}-{vendor}-{row_key}.md
```

Where `row_key` is `make_row_key(metadata)` — a stable 16-char digest.

## Frontmatter — required keys

Written in exactly this order by `format_summary_frontmatter`
(gator-session-common.py:249):

| Key | Type | Notes |
|---|---|---|
| `schema` | literal | Must equal `gator-session-summary-v1`. |
| `session-id` | string | Vendor-native session identifier. |
| `date` | string | `YYYY-MM-DD` (first 10 chars of `start`). |
| `start` | string | ISO-8601 UTC. |
| `end` | string | ISO-8601 UTC. |
| `repo` | string | Repo name, or `unknown`. |
| `architect` | string | Human operator identity. Either `architect:` (canonical) or `pi:` (legacy) MUST be present. |
| `agent` | string | Agent name, or `unknown`. |
| `vendor` | string | Vendor slug (anthropic, openai, google, cursor, ...), or `unknown`. |
| `machine-id` | string | UUID from `~/.gator/machine-id`. |
| `machine-label` | string | Human label for the machine. |
| `transcript` | string | Absolute local path to the raw transcript file. NOT committed to git — this schema describes only the machine-local summary. |
| `turns` | string | `"N user, M assistant"` — human-readable turn count. |
| `tools` | string | Comma-joined tool names used in the session. |
| `branch` | string | Git branch at time of session end, or `unknown`. |

## Body — required section headers

```
# Session Summary — {date} {repo} ({agent-or-vendor})

## Goal

<one-line goal extracted from transcript, or *No goal extracted*>

## Decisions

- [{timestamp}] {decision text}
  ...
or  *No decisions extracted*

## Files Changed

- {path}
  ...
or  *No file changes extracted*

## Charters Updated              ← only if intelligence["charters_updated"]

- {path}
  ...

## Evidence Location

- **Machine**: {label} (`{id}`)
- **Transcript**: `{transcript_path}`
- **Raw source**: vendor-specific local storage
```

## Structured (JSON) counterpart

`format_session_summary_dict` in the same module produces a JSON dict
with the same schema tag and equivalent keys (using snake_case:
`machine_id`, `machine_label`, `session_id`). Downstream aggregation
uses the JSON form; the markdown form is the human-readable rendition
of the same data.

## Canonical fixture

See `contracts/compatibility/fixtures/valid_session_summary.md`.
