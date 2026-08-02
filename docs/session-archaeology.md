# Session Archaeology

Session archaeology is Gator's cross-vendor audit trail for AI coding sessions. It extracts structured records from your AI tools and produces standardized, searchable summaries.

## Supported Tools

| Tool | Source | Extraction |
|------|--------|-----------|
| Claude Code | `~/.claude/` | `extract-claude-sessions.py` |
| Codex CLI | `~/.codex/` | `extract-codex-sessions.py` |
| Gemini CLI | `~/.gemini/` | `extract-gemini-sessions.py` |

## What Gets Extracted

Each session summary contains:

- **Session ID and timestamps** — when it started, when it ended
- **Agent identity** — which model, which tool
- **Files changed** — what was modified during the session
- **Decisions made** — significant choices captured from the session
- **Machine ID** — which workstation (anonymized)

All summaries follow `schema: gator-session-summary-v1` — a stable contract where fields can be added but never removed.

## Two Layers

### Active Session Logs

`.gator/sessions/_active/*.md` — rolling local logs, appended incrementally by the post-commit hook. Gitignored. Cheap capture for long sessions.

### Committed Summaries

`.gator/sessions/*.md` — explicit committed summaries generated for durable audit use. Git-tracked. These are the portable evidence layer.

Generate committed summaries:

```bash
python gator-engine/scripts/gator-sessions.py commit-summaries
```

## Why It Matters

When a regulator, auditor, or team lead asks "what decisions were made by AI in this codebase?", the answer is in git:

```bash
git log --all -- .gator/sessions/
```

Every session summary is a markdown file with YAML frontmatter. Searchable, diffable, portable. No vendor dashboard required.

## Cross-Vendor Visibility

Switch from Claude to Codex mid-project. The session archaeology layer captures both:

```
.gator/sessions/
  2026-05-28-claude-abc123.md
  2026-05-29-codex-def456.md
  2026-05-30-gemini-ghi789.md
```

The audit CLI aggregates across vendors and repos. One query covers everything.
