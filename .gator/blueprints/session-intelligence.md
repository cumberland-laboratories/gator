# Session Intelligence

## What This Page Is

This page explains session intelligence in Gator: the system that extracts, stores, and surfaces AI session history across vendors.

It covers:

- what a session summary is for
- where full transcripts should live
- how data flows from vendor storage into Gator
- what scripts exist today
- what is working, partial, or still missing

If the Architect asks "how do sessions get into the dashboard, and where does the full transcript live?" this page should answer it without source diving.

## Core Position

Session summaries are a discovery index, not an audit artifact.

They exist to make session history searchable, skimmable, and cross-vendor. They help a human find the right session quickly, see what it was about, and decide whether to load the full transcript.

The full transcript is the high-fidelity record.

This distinction matters:

- the summary is small, commit-friendly, and optimized for search
- the transcript is durable, replayable, and optimized for inspection
- vendor-native storage is only the extraction source, not the long-term dependency

## Why This Exists

AI coding sessions are valuable project memory, but vendor tools scatter that memory across private local stores with different formats and retention behavior. Gator's role is to normalize that data into a portable local-first system:

1. a committed search index that travels with the repo
2. a durable transcript archive the user controls
3. a dashboard and CLI surface that can search the first and retrieve the second

That is the product value: not "we can parse vendor logs once," but "we can turn session history into usable local knowledge on your terms."

## Forensic Starting Point

The primary question for session intelligence is:

`What happened?`

Everything else follows from that.

The system should support reconstruction of:

- who was involved
- which agent and vendor were used
- what code or files were touched
- when the session happened
- what commits or outputs followed from it
- whether the full transcript is available

This means the design should be driven by forensic queries, not by the convenience of any one extractor.

### First-Class Forensic Dimensions

Every session record should make these dimensions queryable:

| Dimension | Questions it answers |
|-----------|----------------------|
| `who` | Which architect worked with which agent/model? |
| `when` | When did the session start, end, and produce changes? |
| `what` | What files, tools, branches, and commits were involved? |
| `where` | Which repo, machine, transcript backend, and source location does this map to? |

### Canonical Forensic Questions

The summary index and transcript archive should be designed to answer questions like:

1. Show me every session involving repo `X` during date range `Y`.
2. Which sessions touched file `path/to/file.py`?
3. Which sessions are associated with commit `abc123`?
4. Which architect worked with Codex versus Claude on this repo?
5. Which sessions produced meaningful code changes versus boot/noise?
6. Do we have the full transcript for this session, or only the discovery index?
7. Which machine captured the session, and where is the archived transcript now?
8. What changed immediately before or after a given session?

If the schema or storage model cannot answer these cleanly, it is missing a forensic field.

### Design Consequence

This pushes the system toward a simple split plus a commit seam:

- the summary is the forensic index
- the commit snippet is the forensic commit seam
- the transcript is the forensic record

The summary does not need to contain everything. It needs to contain enough structured metadata and conversation spine to make the right session findable and attributable.

## Design Direction

### The Four-Layer Model

Session intelligence has four layers:

| Layer | Purpose | Durability | Default location | In git? |
|------|---------|------------|------------------|---------|
| Summary | Discovery index | Durable | `.gator/sessions/*.md` | Yes |
| Commit snippet | Commit-to-session traceability seam | Durable | `.gator/session-snippets/*.md` | Yes |
| Transcript | Full session replay | Durable | User-chosen archive backend | Usually no |
| Raw source | Vendor-native storage | Ephemeral | `~/.claude/`, `~/.codex/`, `~/.gemini/` | No |

The rule is simple:

- summaries are for finding sessions
- commit snippets are for mapping session context to a specific commit
- transcripts are for reading sessions
- raw vendor storage is only for extraction and backfill

Gator should not depend on vendor retention after extraction has happened.

### Summary Layer

The summary is the index artifact.

It should be:

- deterministic
- small
- searchable
- safe to commit
- sufficient to decide whether to open the full transcript

It is not expected to stand on its own for audit or forensic reconstruction.

### Transcript Layer

The transcript is the durable full-session artifact.

It should contain the complete extracted session in a stable Gator-owned format, after redaction. This is the thing the dashboard loads for "show me the full session."

The transcript archive is first-class, not an implementation detail.

### Commit Snippet Layer

The commit snippet is a commit-linked session delta.

It captures only the portion of the session since the previous successful commit in the same session. This creates a precise seam between:

- the code change event in Git
- the immediate conversational context that produced it

This layer is valuable because many real sessions span multiple commits. A full-session summary answers "what happened in this session?" A commit snippet answers "what session context immediately produced this commit?"

The commit snippet should be:

- small
- deterministic
- commit-linked
- specific to a session interval
- good enough to reconstruct intent around one commit without loading the full transcript

It should not try to replace either the session summary or the full transcript.

### Active Ledger Layer

The current `.gator/sessions/_active/*.md` files should be treated as a live session ledger, not as unfinished summaries.

That distinction matters:

- a rolling ledger is mutable and local
- a snippet is frozen and commit-linked
- a summary is a later projection, not the source of truth

The `_active/` ledger is the right substrate for snippet generation because it already groups commit events into one continuous working session using the staleness timeout.

The intended relationship is:

- `_active/` ledger = in-progress working session log
- snippet = durable artifact emitted from one ledger interval at a commit boundary
- summary = optional later aggregation, not the first consumer

This is a better fit than trying to "promote" `_active/` files into session summaries. The ledger is strongest at commit-boundary forensics, not at reconstructing whole-session conversation meaning.

### Raw Source Layer

Vendor-native storage remains useful for:

- initial extraction
- backfill of old sessions
- recovery if a transcript was never archived

But it is not a reliable product dependency. Vendor formats will drift. Retention may be limited. Files may only exist on one machine.

## User-Controlled Transcript Storage

This is the next structural step.

Gator should let the user decide where full transcripts are stored. The product should not assume one retention model for everyone.

### Storage Backends

Transcript storage should be pluggable. Initial targets:

- local archive directory
- repo-local ignored directory
- external command sink

Future targets:

- object storage
- private database
- enterprise document store

The abstraction should be: Gator produces a normalized transcript artifact and writes it through a configured storage backend.

### Recommended Default

The simplest default is a local archive directory outside repo history, for example:

`~/.gator/session-archive/<row-key>.json.gz`

That gives:

- durability independent of vendor storage
- no repo bloat
- simple backup story
- easy later migration to other backends

### Why Not Commit Full Transcripts by Default

Full transcripts are text and often compress well, so Git can technically store them. The problem is not "Git cannot hold text." The problem is retention shape:

- many sessions across time and repos
- sensitive content becomes hard to purge from history
- a discovery feature becomes an archive policy by accident

So the default should be:

- summaries committed
- transcripts archived outside normal repo history

Committed transcripts can still exist as an opt-in backend for teams that want that tradeoff.

## Retrieval Flow

The intended workflow for a Gator commander:

1. Search session summaries in the dashboard by tag, keyword, date, repo, vendor
2. Open a summary preview and optional assessment
3. If the question is commit-specific, open the commit snippet linked to that commit
4. Load the full transcript from the configured archive backend when more context is needed
5. Fall back to vendor raw storage only if no durable transcript exists

Summaries are the index. Commit snippets are the code-change seam. Transcripts are the document. Vendor storage is the fallback archaeology layer.

## Active Ledger to Snippet Flow

This is the preferred path for commit-boundary traceability.

### Core Reframe

Do not think of `_active/` as "pending summary."

Think of it as:

- a local, mutable session ledger
- append-only within one active working session
- the canonical source for snippet generation

### Flow

1. A successful commit runs the post-commit cleanup hook.
2. The hook appends one normalized entry to the active ledger for the current repo + agent session.
3. The ledger entry captures commit metadata, note bullets from `commit_draft.md`, and session-level identity fields.
4. Gator derives a snippet for the new commit from the current ledger interval.
5. Gator writes that snippet as a durable Git-tracked artifact.
6. The ledger remains local and mutable until the session goes stale.

This yields a clean trust split:

- local ledger for continuity
- durable snippet for evidence at the commit seam

### Session Boundary Rule

The ledger session identity should continue to use the current staleness window:

- if the most recent ledger file for `repo + agent` was updated less than `SESSION_TIMEOUT_HOURS` ago, append to it
- otherwise start a new ledger file with a fresh `session-id`

That means a snippet's `previous-commit-in-session` is defined structurally, not heuristically:

- it is the previous commit entry in the same ledger file
- if none exists, the snippet is the first commit in the session

### Why This Works

This model answers the hardest forensic question cleanly:

`What session context immediately produced this commit?`

Without a ledger-backed snippet, later matching is mostly inference from timestamps and file overlap. With this model, the commit boundary captures the session interval directly.

## Session Ledger Schema v1

Format: `gator-active-session-ledger-v1`

This is the local mutable source used to derive snippets. It is not committed to Git by default.

### Frontmatter Fields

Required:

- `schema`
- `type`
- `status`
- `session-id`
- `repo`
- `agent`
- `architect`
- `branch`
- `started-at`
- `last-updated`
- `commits`

Recommended:

- `machine-id`
- `machine-label`
- `vendor`
- `model`

Example:

```md
---
schema: gator-active-session-ledger-v1
type: active-session-ledger
status: active
session-id: gator-command-claude-opus-4-6-20260616-120311
repo: gator-command
agent: claude-opus-4-6
architect: AG
branch: main
started-at: 2026-06-16T12:03:11Z
last-updated: 2026-06-16T12:14:59Z
commits: 2
machine-id: WS-42
vendor: anthropic
model: claude-opus-4-6
---
```

### Commit Entry Block

Each commit block should have a stable machine-readable shape.

Required fields per block:

- short commit hash in heading
- full commit hash
- timestamp
- branch
- change-type
- significance
- decision-tags
- charter-changed

Recommended fields per block:

- `commit-index`
- `previous-commit-in-session`
- `files-touched`
- `snippet-id`

Optional body:

- `Notes:` bullets copied from the session's `commit_draft.md`

Example:

```md
### 1e36151 - Deploy script auto-populates target commit_draft
- commit-index: 2
- timestamp: 2026-06-16T12:14:59Z
- commit: 1e36151d7c0d...
- previous-commit-in-session: b6e0897d44af...
- branch: main
- change-type: feature
- significance: routine
- decision-tags: deploy,commit-draft
- charter-changed: True
- files-touched: src/gator_command/scripts/gator-deploy.py,tests/test_deploy.py
- snippet-id: snippet-1e36151d7c0d

Notes:
- Deploy now writes a starter commit_draft so governed clones begin with a valid draft.
- This closes the gap between fresh governance install and first commit.
```

### Ledger Invariants

- one active ledger per `repo + agent + freshness window`
- commit entries are append-only within a ledger
- commit order is canonical session order
- `previous-commit-in-session` must match the prior block's full commit hash
- the ledger may be repaired or enriched locally, but snippets emitted from it are frozen

## Session Snippet Schema v1

Format: `gator-session-snippet-v1`

This is the durable Git-tracked artifact. It should live separately from the active ledger, for example:

` .gator/session-snippets/<date>-<repo>-<short-commit>.md `

### Purpose

The snippet answers:

- which session this commit belonged to
- which immediately preceding session interval produced it
- what the architect and agent were doing around that boundary

### Frontmatter Fields

Required:

- `schema`
- `type`
- `snippet-id`
- `session-id`
- `repo`
- `commit`
- `short-commit`
- `previous-commit-in-session`
- `commit-index`
- `agent`
- `architect`
- `branch`
- `started-at`
- `ended-at`

Strongly recommended:

- `vendor`
- `model`
- `machine-id`
- `decision-tags`
- `change-type`
- `significance`
- `charter-changed`

Optional:

- `files-touched`
- `transcript-ref`
- `row-key`

### Body Sections

Recommended body shape:

- `## Interval`
- `## Notes`
- `## Files Touched`
- `## Commit`

Example:

```md
---
schema: gator-session-snippet-v1
type: session-snippet
snippet-id: snippet-1e36151d7c0d
session-id: gator-command-claude-opus-4-6-20260616-120311
repo: gator-command
commit: 1e36151d7c0d...
short-commit: 1e36151
previous-commit-in-session: b6e0897d44af...
commit-index: 2
agent: claude-opus-4-6
architect: AG
branch: main
started-at: 2026-06-16T12:03:10Z
ended-at: 2026-06-16T12:14:59Z
vendor: anthropic
model: claude-opus-4-6
decision-tags: [deploy, commit-draft]
change-type: feature
significance: routine
charter-changed: yes
files-touched:
  - src/gator_command/scripts/gator-deploy.py
  - tests/test_deploy.py
---

## Interval

Session commit 2 of 2. Covers the working interval since `b6e0897`.

## Notes

- Deploy now writes a starter commit_draft so governed clones begin with a valid draft.
- This closes the gap between fresh governance install and first commit.

## Files Touched

- `src/gator_command/scripts/gator-deploy.py`
- `tests/test_deploy.py`

## Commit

- `1e36151` Deploy script auto-populates target commit_draft
```

## Snippet Build Rules

The snippet builder should follow deterministic rules.

### Build Trigger

- default: emit snippet immediately after each successful commit
- fallback: a repair command can regenerate snippets from a ledger if needed

### Source

- source of truth is the active ledger entry just appended during post-commit cleanup
- do not reconstruct from Git log alone if the ledger entry exists

### Interval Semantics

- first commit in a session: snippet interval starts at `started-at`
- later commits: snippet interval starts at the previous commit entry timestamp
- snippet interval ends at the current commit entry timestamp

### Notes Semantics

- copy note bullets exactly as captured from `commit_draft.md`
- do not synthesize new prose in the mechanical snippet builder

### File Semantics

- prefer files explicitly captured in the ledger entry
- if file capture is later enriched from diffstat or transcript data, preserve the original deterministic source

## What Snippets Are Good For

Snippets are the strongest artifact for:

- commit-to-session attribution
- multi-commit session tracing
- answering "what context produced this commit?"
- building later work summaries from commit-grounded evidence

They are not enough, by themselves, for:

- full conversational reconstruction
- non-committed exploration
- rejected alternatives
- transcript search

That is why snippets should be treated as their own layer, not as a replacement for transcripts or discovery summaries.

## Summary Schema v2

Format: `gator-session-summary-v2`

The summary should carry enough metadata to locate and trust the full transcript without pretending to be the full transcript.

### Frontmatter Fields

Required:

- `schema`
- `session-id`
- `row-key`
- `date`
- `start`
- `end`
- `repo`
- `architect`
- `agent`
- `vendor`
- `machine-id`
- `machine-label`

Optional but strongly recommended:

- `turns`
- `tools`
- `branch`
- `transcript-id`
- `transcript-backend`
- `transcript-ref`
- `transcript-sha256`
- `retention`

Interpretation:

- `transcript-id`: stable transcript artifact id, usually the row key or a backend-specific object id
- `transcript-backend`: `local-archive`, `repo-local`, `command`, `s3`, `sqlite`, etc.
- `transcript-ref`: backend-specific locator such as a path, object key, or URI-like reference
- `transcript-sha256`: integrity check for the archived transcript artifact
- `retention`: human-readable note such as `durable`, `local-only`, `best-effort`, `vendor-fallback`

Changes from v1:

- remove `goal`
- remove the misleading `transcript` path field from frontmatter
- replace it with durable transcript provenance fields

### Body Sections

```markdown
## Tags
#session-archaeology #dashboard #storage

## Conversation

### [HH:MM] Architect
Full text of architect message.

### [HH:MM] Agent (abbreviated)
First 10 lines of agent response...
[... N lines omitted ...]
Last 10 lines of agent response.

## Files Changed
- path/to/file.py
- path/to/other.py
```

Notes:

- architect turns remain full because they are often the highest-signal search surface
- agent turns are abbreviated because the summary is for navigation, not replay
- files changed should contain clean repo-relative paths only

### Tags

Tags are part of the discovery layer.

They should be:

- lightweight
- greppable
- dashboard-indexed

They are annotations, not mechanically trusted evidence.

That means the trust boundary must be explicit:

- the extracted conversation spine is mechanical
- tags may be added by the agent or PI after extraction
- tags should not be described as part of the immutable mechanical record

### Naming

Summary filename:

`YYYY-MM-DD-<repo>-<vendor>-<row-key>.md`

Deterministic and idempotent.

## Transcript Artifact

The transcript should be stored in a stable Gator-owned format, independent of vendor raw files.

Suggested wire shape:

```json
{
  "schema": "gator-session-transcript-v1",
  "session_id": "a1b2c3",
  "row_key": "af1088830fb8a1cf",
  "repo": "gator-command",
  "vendor": "claude",
  "machine": {
    "id": "uuid",
    "label": "alan-home-desktop"
  },
  "source": {
    "kind": "vendor-storage",
    "path": "~/.claude/projects/...",
    "captured_at": "2026-06-15T12:00:00Z"
  },
  "turns": [
    {
      "seq": 1,
      "role": "user",
      "timestamp": "2026-06-15T11:10:00Z",
      "content": "..."
    }
  ]
}
```

Compression should be allowed by backend, but the logical format should stay stable.

## Commit Snippet Artifact

The commit snippet is the fourth layer: a compact per-commit artifact carrying the session slice since the previous commit boundary.

This is the traceability bridge between session history and Git history.

### Why It Exists

Sessions often span multiple commits. Without an explicit seam artifact, later reconstruction has to guess which turns corresponded to which commit.

The commit snippet removes that ambiguity by checkpointing the session at commit time.

### Scope

Each snippet should cover:

- turns since the previous successful commit in the same session
- or session start to first commit if no prior commit exists

This makes commit linkage incremental and explicit.

### Suggested Contents

Required metadata:

- `schema: gator-session-snippet-v1`
- `session-id`
- `row-key`
- `commit`
- `previous-commit-in-session`
- `repo`
- `branch`
- `vendor`
- `agent`
- `architect`
- `machine-id`
- `machine-label`
- `start`
- `end`
- `start-turn-seq`
- `end-turn-seq`

Recommended body content:

- abbreviated conversation slice
- files changed in the interval
- tools used in the interval
- transcript pointer or transcript artifact id

### Storage

Default location:

`.gator/session-snippets/<commit>.md`

These should be Git-tracked. They are small enough to commit and useful enough to justify durable linkage.

### Git Linkage

The relationship should be bidirectional:

- the snippet references the commit hash
- the commit metadata should reference the snippet id or path

That allows:

- commit -> snippet
- snippet -> commit
- snippet -> transcript
- transcript -> session summary

This triangulation is likely to be extremely strong for audit and forensic use.

### Design Constraints

Commit snippets should remain:

- compact
- deterministic
- privacy-aware

They should not become mini-transcripts. Their job is to preserve the commit seam, not to duplicate the archive.

## Session Assessment Companion

The assessment remains a separate companion file.

It is useful because summaries are intentionally shallow. The assessment gives a human-readable explanation of what the session really covered without polluting the summary's mechanical spine.

Filename:

`YYYY-MM-DD-<repo>-<vendor>-<row-key>-assessment.md`

Example:

```markdown
---
schema: gator-session-assessment-v1
session-summary: 2026-06-15-gator-command-claude-af1088830fb8a1cf.md
assessed-by: Claude Sonnet 4.6
assessed-date: 2026-06-15
---

# Session Assessment

This is a search aid, not evidence.

[3-4 paragraph assessment]
```

The dashboard should link summary and assessment by schema plus filename convention, not by assuming every markdown file in `.gator/sessions/` is a summary.

## Assessment Procedure

An enforcer or other distinct model reads the full transcript and writes the assessment companion file.

When to run:

- after session close
- as backfill for historical sessions
- never as an in-session self-summary by the working agent

Procedure:

1. Load the durable transcript artifact if available
2. Fall back to vendor raw storage only if no transcript was archived
3. Read the summary for orientation
4. Write a 3-4 paragraph assessment covering:
   - what the session accomplished
   - key decisions and rationale
   - what state the work was left in
   - notable reversals, discoveries, or scope changes
5. Write the companion file to `.gator/sessions/`

## How It Works Today

Status: `Partial`

What exists today:

- vendor extraction for Claude, Codex, and Gemini
- committed summary writing in v1 schema
- dashboard display of committed summaries
- spool and sink paths for richer local exports
- commit-time hook infrastructure that could anchor snippet checkpoints

What does not yet exist cleanly:

- v2 discovery-oriented summary format
- commit-linked snippet artifact generation
- first-class durable transcript archive
- backend choice for transcript storage
- dashboard transcript retrieval by archive reference

## Current Data Flow

Today's manual process:

1. PI runs `python src/gator_command/scripts/gator-sessions.py commit-summaries --path <target>/.gator/sessions`
2. Script discovers sessions across vendors on the machine
3. Vendor extractors parse raw storage into normalized session objects
4. Intelligence extraction pulls files and other summary signals
5. Redaction runs before output
6. Summary markdown is written to `.gator/sessions/`
7. PI commits those summaries

Current weakness:

- this writes the search index
- it does not capture a formal session delta at each commit boundary
- it does not yet guarantee durable transcript archival

That is the main design gap to close.

## Scripts Inventory

### Vendor Extraction

| Script | Vendor | Reads from | Status |
|--------|--------|------------|--------|
| `extract-claude-sessions.py` | Claude Code | `~/.claude/projects/` | Working |
| `extract-codex-sessions.py` | Codex CLI | `~/.codex/sessions/` | Working |
| `extract-gemini-sessions.py` | Gemini CLI | `~/.gemini/tmp/` | Working |
| `(no script)` | Cursor | - | Not built |

These scripts are fragile by nature because vendor formats are undocumented and will change.

### Orchestration

| Script | What it does |
|--------|--------------|
| `gator-sessions.py` | Unified CLI for session discovery, export, manifests, pending state, and committed summaries |
| `gator-session-common.py` | Shared utilities: redaction, machine identity, intelligence extraction, summary formatting |

### Storage and Retrieval

| Script | What it does |
|--------|--------------|
| `gator-session-sink.py` | Loads session data into SQLite/DuckDB or pipes to external systems |

This script family is the right place to grow transcript backend support. The sink should become the storage abstraction boundary for full transcripts.

### Active Session Tracking

The post-commit hook appends rolling local session notes into `.gator/sessions/_active/`.

Status: still disconnected from the durable summary/transcript pipeline.

Those files are useful as local incremental capture, but they should not be confused with either:

- committed discovery summaries
- committed commit snippets
- archived full transcripts

## What the Dashboard Should Show

### Repo View

- summary count
- commit snippet presence for recent commits
- recent committed summaries
- summary metadata: date, vendor, agent, start/end, turn count, tools
- assessment presence
- transcript availability status
- "open transcript" action when the configured backend can resolve it

### Audit View

- recent summaries across the fleet
- commit-to-session traceability for governed commits
- provenance of where the summary came from
- whether a durable transcript exists
- whether only vendor fallback exists

### Search

Search should target summaries first:

- tags
- keywords
- repo
- vendor
- date

Search results should tell the user whether the full transcript is actually available before they click through.

## What Works

- cross-vendor extraction for Claude, Codex, Gemini
- deterministic committed summary filenames
- strong potential commit-boundary anchor via hooks
- canonical parser for committed summaries
- dashboard rendering of current summaries
- stable machine identity
- redaction before export
- sink path for external analysis

## What Needs to Change

### Priority 1: Reframe summaries as discovery index

Update docs, schema language, and dashboard labels so summaries are no longer described as full evidence.

### Priority 2: Add durable transcript archival

Extraction should produce or be able to produce a Gator-owned transcript artifact, not just a summary.

### Priority 3: Add commit-linked snippet artifacts

At commit time, generate a compact session delta artifact linked to the commit hash.

### Priority 4: Add transcript storage backends

Let the user choose where transcripts live:

- local archive
- repo-local ignored archive
- external command sink

### Priority 5: Implement summary schema v2

Move from Goal + Decisions to discovery-oriented conversation spine plus transcript provenance fields.

### Priority 6: Build transcript retrieval in dashboard

The dashboard needs a stable "open transcript" path using the configured backend.

### Priority 7: Repo-level filtering

`commit-summaries --repo <name>` so repos do not accumulate unrelated fleet sessions.

### Priority 8: Minimum-session threshold

Filter boot-only or empty sessions before writing summaries.

## Gaps Carried Forward

### `_active/` tracking is disconnected

Rolling local session files are still orphaned from the main pipeline.

### Cross-repo attribution

Command-post sessions about fleet repos still need a way to project relevance into the affected repo.

### Files Changed quality

Tool operation markers should not appear as file paths in the summary.

### Partial snapshots

Running summary extraction during an active session can still create incomplete summaries.

### Cursor extraction

Still not built.

## Participating Modules

| Module | Role |
|--------|------|
| `gator-sessions.py` | Session orchestration CLI |
| `gator-session-common.py` | Shared parsing, identity, redaction, formatting |
| `extract-claude-sessions.py` | Claude extraction |
| `extract-codex-sessions.py` | Codex extraction |
| `extract-gemini-sessions.py` | Gemini extraction |
| `gator-session-sink.py` | Transcript/archive sinks and analysis loading |
| `gator-pre-commit.py` | Rolling local `_active/` session tracking and likely commit-snippet checkpoint anchor |
| `gator-repo-status.py` | Repo view summary reader |
| `gator-audit.py` | Audit view summary reader |
| `gator-dashboard.py` | Session UI and retrieval entry point |

## Connections

- [Session Logging thread](../active-threads/session-logging.md) - design philosophy and storage model
- [Session Schema procedure](../procedures/session-schema.md) - canonical format definition, needs v2 alignment
- [Session Lifecycle procedure](../procedures/session-lifecycle.md) - open/close semantics
- [Session Evidence Pipeline artifact](../artifacts/2026-06-08-session-evidence-pipeline-current-state.md) - prior state snapshot
- [Roadmap](../roadmap.md) - session evidence priorities
- [Hook Pipeline blueprint](hook-pipeline.md) - post-commit `_active/` behavior
