# Claude Code Session Storage Format

Reference for building session archaeology scripts. Based on direct inspection of `~/.claude/` directory structure as of Claude Code v2.1.76 (2026-05-26). This format is undocumented and may change between versions.

## Directory Structure

```
~/.claude/
  history.jsonl                 ← Architect prompt history (all projects, flat JSONL)
  settings.json                 ← user settings, hook configurations
  sessions/
    {pid}.json                  ← session metadata per process
  projects/
    {path-encoded-project}/     ← one dir per project (path with -- separators)
      {sessionId}.jsonl         ← FULL SESSION TRANSCRIPT (the gold)
      {sessionId}/
        tool-results/           ← large tool outputs stored separately
          toolu_{id}.txt        ← individual tool result files
          pdf-{id}/             ← PDF read results
        subagents/              ← subagent transcripts (Agent tool calls)
          agent-{id}.jsonl      ← full subagent conversation
          agent-{id}.meta.json  ← metadata (e.g., {"agentType":"general-purpose"})
      memory/                   ← Claude Code's own MEMORY.md and memory files
  file-history/                 ← file backup snapshots (for undo/rollback)
```

### Project directory naming

Project paths are encoded by replacing path separators with `--`:
`C:\Users\curator\code2\gator-command` → `C--Users-curator-code2-gator-command`

### Session identification

Each session gets a UUID (e.g., `9322ea3f-89f7-47b1-9ca7-cc4c7d42b983`). The JSONL file at the project level is the primary transcript. The matching subdirectory holds overflow data (large tool results, subagent transcripts).

## Session JSONL Format

Each line is a self-contained JSON object. Every object has a `type` field.

### Message types observed

| Type | What it is | Frequency |
|---|---|---|
| `user` | Architect prompt or tool result delivery | High |
| `assistant` | Agent response (may contain multiple content blocks) | High |
| `file-history-snapshot` | File backup checkpoint | Medium |
| `system` | System-injected context | Low-medium |
| `progress` | Streaming progress updates | High (noise) |
| `hook_progress` | Hook execution updates | Medium (noise) |
| `agent_progress` | Subagent progress | Medium (noise) |

### Content block types (nested in assistant messages)

| Content type | What it is |
|---|---|
| `text` | Agent's text response |
| `tool_use` | Tool invocation (name, input parameters, caller) |
| `tool_result` | Tool output (paired with tool_use via tool_use_id) |
| `thinking` | Extended thinking block (may be encrypted/signed) |
| `image` / `base64` | Image content |

### Key fields per message type

**User message (`type: "user"`)**:
```json
{
  "type": "user",
  "message": {"role": "user", "content": "the Architect's prompt text"},
  "timestamp": "2026-05-25T15:19:09.033Z",
  "cwd": "C:\\Users\\curator\\code2\\gator-command",
  "sessionId": "9322ea3f-...",
  "version": "2.1.76",
  "gitBranch": "main",
  "uuid": "00cd0a72-...",
  "parentUuid": null
}
```

**Assistant message with tool call (`type: "assistant"`)**:
```json
{
  "type": "assistant",
  "message": {
    "model": "claude-opus-4-6",
    "role": "assistant",
    "content": [
      {"type": "tool_use", "id": "toolu_012mi...", "name": "Read",
       "input": {"file_path": "C:\\...\\constitution.md"},
       "caller": {"type": "direct"}}
    ],
    "usage": {
      "input_tokens": 3,
      "cache_creation_input_tokens": 6639,
      "cache_read_input_tokens": 8777,
      "output_tokens": 35
    }
  },
  "timestamp": "2026-05-25T15:19:12.974Z",
  "uuid": "b3fc2310-...",
  "parentUuid": "00cd0a72-..."
}
```

**Tool result (delivered as user message)**:
```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {"tool_use_id": "toolu_012mi...", "type": "tool_result",
       "content": "     1→# file contents..."}
    ]
  }
}
```

### Message threading

Messages form a tree via `uuid` and `parentUuid`. An Architect prompt has `parentUuid: null`. Each assistant response references its parent. Tool results reference the assistant message that made the tool call. This enables reconstructing the full conversation flow including branching (sidechains).

The `isSidechain` boolean flags messages that are off the main conversation path.

## history.jsonl

Flat file containing every Architect prompt across all projects:

```json
{
  "display": "the Architect's prompt text...",
  "pastedContents": {},
  "timestamp": 1759021055322,
  "project": "C:\\Users\\curator\\code2\\quiz_app"
}
```

Timestamps are Unix milliseconds. The `display` field is the full prompt as shown to the user. `pastedContents` holds any pasted text blocks.

## sessions/*.json

Minimal metadata per process:

```json
{
  "pid": 492,
  "sessionId": "8118aa41-...",
  "cwd": "C:\\Users\\curator\\code2\\trip-service-kata",
  "startedAt": 1778884516269
}
```

## What's extractable for session archaeology

### From `{sessionId}.jsonl` (richest source):
- **Full conversation**: every Architect prompt and agent response, timestamped
- **Every tool call**: tool name, parameters, output — which files read/edited/created
- **Model used**: per-turn model identification and token usage
- **Git context**: branch and working directory at each message
- **Decisions**: embedded in assistant text content blocks
- **Subagent activity**: separate JSONL files in the `subagents/` subdirectory
- **Message threading**: parent-child relationships via UUIDs

### From `history.jsonl`:
- Cross-project Architect prompt history with timestamps
- Useful for "what was the Architect working on this week?" across all repos

### From `sessions/*.json`:
- Session-to-PID mapping, start times, working directories
- Useful for correlating sessions with system-level events

## Extraction strategy

1. Enumerate project dirs under `~/.claude/projects/`
2. For each session JSONL, filter lines by `type`:
   - `user` with string `message.content` → Architect prompts
   - `assistant` → agent responses (parse `message.content[]` for text/tool_use)
   - `user` with array `message.content` containing `tool_result` → tool outputs
3. Extract tool calls: `name` + `input` from `tool_use` content blocks
4. Build timeline: sort by `timestamp`, group into turns
5. Tag each turn with: repo, branch, tools used, files touched, model
6. For subagents: read `subagents/agent-{id}.jsonl` with same parsing logic

### Noise filtering

Skip `type` values: `progress`, `hook_progress`, `agent_progress`, `file-history-snapshot` (unless file-level audit is needed). These are streaming/internal state, not conversation content.

## Prior Art: learnhub Extraction Scripts

Production-quality extraction scripts already exist in the `learnhub` sibling repo (under `scripts/`). These were built in March 2026 as a multi-agent collaboration (Claude, Codex, Gemini each implemented their own extractor).

### Scripts

| Script | Source | Storage location |
|---|---|---|
| `extract_claude_log.py` | `~/.claude/projects/{project}/*.jsonl` | `.claude/logs/` |
| `extract_codex_log.py` | Codex session JSONL (varies) | `.codex/logs/` |
| `extract_gemini_log.py` | `~/.gemini/tmp/{project}/chats/session-*.json` | `.gemini/logs/` |

### Shared Schema

All three scripts produce events in a shared `ToolEvent` schema (`session_log_schema.py`):

```
ToolEvent:
  timestamp     — ISO 8601 UTC
  session_id    — unique session identifier
  agent         — claude | codex | gemini
  event_type    — session_start | session_end | tool_success | tool_failure | delegation_start | delegation_end
  tool_name     — raw tool name from the agent
  summary       — human-readable one-liner (e.g., "read(constitution.md)")
  status        — success | failure
  file_paths    — files touched
  file_classes  — auto-classified file types
  cwd           — working directory
  agent_id      — subagent ID (for delegated calls)
  error         — error message (failures only)
  delegated_to  — delegation description
```

### Supporting modules
- `classify.py` — file path classification (code, config, docs, etc.)
- `analyze_codex_session.py` — Codex-specific shell command classification
- `analyze_latest.py` — cross-tool analysis

### Planning artifacts
Full decision trail at `learnhub/docs/plans/2026-03-10-session-tool-logging/`:
- `decision.md` — approved plan, phase assignments
- `plan-gemini.md`, `plan-codex.md` — per-agent implementation plans
- `report.md`, `status.md` — execution status
- `reviews/codex-review.md` — cross-agent review

### Reuse strategy for Gator Command

These scripts are the starting point for the session archaeology feature described in the session-logging thread. The extraction logic is proven and the shared schema is designed for cross-tool normalization. The work needed:
1. Copy/adapt the scripts into `src/gator_command/scripts/` (or the gator-starter template)
2. Add the tagging/indexing layer that the session-logging thread specifies
3. Add the per-repo thread update logic (session findings → repo intelligence threads)

## Connections

→ [Session Logging thread](../active-threads/session-logging.md) — the design for structured session logs that this data feeds into
→ ECC Competitive Analysis (in cl-memex repo, `memex/artifacts/2026-03-20-ecc-competitive-analysis.md`) — discovered the hook-based session injection pattern and session file format
→ Prior art scripts live in the `learnhub` sibling repo under `scripts/`: `extract_claude_log.py`, `extract_codex_log.py`, `extract_gemini_log.py`, `session_log_schema.py`, `classify.py`
→ Decision trail: `learnhub/docs/plans/2026-03-10-session-tool-logging/` (decision.md, plan-gemini.md, plan-codex.md, report.md, status.md)
