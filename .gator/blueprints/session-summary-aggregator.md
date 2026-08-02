# Blueprint: Session Summary Aggregator

## What It Does

Generates session summaries on demand by aggregating session snippets. Shipped in v1.2.0. The aggregator is the middle layer between raw commit-linked snippets (in git) and the Audit view (in the dashboard). It replaces transcript-extracted summaries as the primary session evidence path.

## How Sessions Get Generated

Session summaries appear "magically" because of a pipeline that runs automatically:

1. **Every `git commit`** in a governed repo fires the post-commit hook (`gator-pre-commit.py --phase cleanup`)
2. The hook emits a **session snippet** (`.gator/session-snippets/<date>-<repo>-<hash>.json`) containing the commit's metadata: intent, files touched, decision tags, significance, agent, architect, timestamps
3. Snippets accumulate — one per commit, grouped by `session_id` (which encodes the date + model + start time)
4. When anyone opens the **Audit view** in the dashboard, or runs `gator audit --sessions`, the aggregator reads all snippets, groups them by `(repo, session_id)`, and produces session summaries
5. Summaries are **cached** at `~/.gator/sessions/<path-hash>/` — subsequent views are instant unless new commits have arrived

The Architect never has to "create" a session. Sessions emerge from governed commits.

## Entry Points

There are three ways to trigger aggregation:

### 1. Dashboard Audit view (primary)

Open the Audit tab in `gator dashboard`. The session table loads lazily via `GET /api/audit/sessions?repo=<path-hash>`. If a repo is selected in Fleet/Repo view, the Audit tab shows that repo's sessions. If no repo is selected, it shows fleet-wide sessions.

**Fleet toggle**: The "Fleet" button in the Audit view switches between single-repo and fleet-wide session display. In single-repo mode, it calls `/api/audit/sessions?repo=<path-hash>`. In fleet mode, it calls `/api/audit/sessions?fleet=true`, which iterates all registered repos and merges their sessions.

### 2. CLI

```
gator audit --sessions              # current repo, text output
gator audit --sessions --json       # current repo, JSON output
gator audit --sessions --fleet      # all registered repos
gator audit --sessions --refresh    # force cache regeneration
```

### 3. Cross-document search

The dashboard's cross-document search (`GET /api/repo/<name>/search?q=<query>`) indexes snippet files alongside all other `.gator/` content. Searching for an intent, decision tag, or file path will surface matching snippets. Clicking a search result opens the snippet file in the Repo view.

## Storage Architecture

Session summaries live in the **machine-local Gator home**, not in any repo:

```
~/.gator/
  dashboard-repos.json          ← which repos exist on this machine
  sessions/                     ← what sessions happened on this machine
    ff7b67d04a1b/               ← path-hash key (12 chars of SHA-256)
      _repo.json                ← {"name": "gator-command", "path": "C:/Users/..."}
      44936a-20260619-claude-opus-4-6-223347.json
      44936a-20260620-codex-111312.json
```

### Cache key: path hash, not repo name

Repo names collide. Two clones named `api` or `frontend` on different paths would overwrite each other's summaries. The cache directory uses a **stable hash of the resolved repo path** (first 12 chars of SHA-256), with a `_repo.json` metadata file mapping the hash back to the human-readable name and path.

### Cache filename: compound key

Each cached summary file uses `<repo-hash-6>-<session_id>.json` as the filename — a compound key that prevents collision if two repos share the same `session_id` pattern.

### Three layers, each derived from the one below

| Layer | Location | Nature | Committed |
|---|---|---|---|
| **Snippets** | `.gator/session-snippets/` in each repo | Ground truth, commit-linked | Yes — in git |
| **Session summaries** | `~/.gator/sessions/<path-hash>/` | Derived, machine-local | No — local cache |
| **Enterprise warehouse** | External DB/warehouse | Ingested from machine exports | N/A (future) |

Why machine-local, not in-repo:
- **No repo churn** — viewing Audit never dirties the working tree
- **Cross-repo queries** — dashboard can aggregate sessions across all repos from one directory
- **Sessions are inherently machine-local** — a session happens on a specific machine with a specific model
- **Enterprise seam** — a future pipeline has one place to read from
- **Disposable** — deleting `~/.gator/sessions/` and regenerating from snippets produces identical results

## Implementation

### Core library: `gator-session-aggregator.py`

Importable module with no CLI entry point. All consumers import it.

| Function | What it does |
|----------|-------------|
| `read_snippets(repo_path)` | Reads `.gator/session-snippets/*.json`. Returns `SnippetRecord` dicts with `data`, `raw_bytes`, `path`. Skips legacy `.md` and corrupt files. |
| `aggregate_sessions(snippets, repo_path)` | Groups by `(repo, session_id)`, applies aggregation rules, computes `repo_key`. |
| `derive_goal(intents, commits)` | Derives session goal: prefers non-release/merge/cleanup intents. |
| `snippet_fingerprint(records)` | SHA-256 over raw file bytes. Order-independent. Full-content — any byte change invalidates. |
| `get_session_summaries(repo_path, force_refresh)` | Orchestrator: read → aggregate → check cache → generate/return. |
| `get_fleet_summaries(registry_path, force_refresh)` | Iterates all repos in `~/.gator/dashboard-repos.json`. |
| `session_cache_key(repo_path)` | `sha256(resolved_path)[:12]` — the path-hash. |

### Dashboard endpoint: `GET /api/audit/sessions`

Lazy / on-demand — not part of Tier 1 startup. Query params:
- `repo=<path-hash>` — single repo by 12-char path hash
- `fleet=true` — all registered repos
- `refresh=true` — force cache regeneration

Logic extracted to `_resolve_audit_sessions()` (testable without HTTP).

### CLI: `gator audit --sessions`

Added to existing `gator-audit.py`. `--fleet` and `--refresh` require `--sessions`. Fleet text output groups by repo first, then sorts descending within each repo.

### Dashboard Audit view: `audit.js`

Session table with:
- **Columns**: Session (date range), Model, Commits, Goal, Tags (badges), Status (complete/in-flight)
- **Expandable rows**: click to see commits, files touched, notes, transcript ref
- **Fleet toggle**: switches between single-repo and fleet view
- **Status heuristic**: `ended_at` > 2 hours ago = complete, otherwise in-flight
- **DOM identity**: row/detail IDs use `repo_key-session_id` compound key to prevent cross-repo collisions in fleet mode

Audit tab is visible in both **standalone** and **command-post** modes. Standalone mode shows session summaries from local snippets with governance metric cards at zero.

## Snippet Schema (input)

Only `.json` files with `gator-session-snippet-v2` schema are read. Legacy `.md` snippets (v1) are ignored.

Key fields consumed by the aggregator:

```text
session_id            - groups snippets into a session
commit / short_commit - commit identity
started_at / ended_at - timestamps
intent                - derived from commit message
notes[]               - from commit_draft body
files_touched[]       - files changed
decision_tags[]       - governance tags
change_type           - feature/fix/docs/release/etc.
significance          - routine/minor/high
agent / architect     - who did the work
vendor_inferred / model_inferred - which AI model
machine_label         - which machine
transcript_session_id / transcript_ref - transcript join keys (optional)
repo / branch         - repo and branch context
```

## Aggregation Rules

Group snippets by `(repo, session_id)`. Within each session:

| Output field | Aggregation rule |
|---|---|
| `repo_key` | `session_cache_key(repo_path)` — first-class field throughout the stack |
| `started_at` | min across all snippets |
| `ended_at` | max across all snippets |
| `commit_count` | Count of snippets |
| `commits` | Ordered list of `{commit, short_commit, intent, change_type}` |
| `files_touched` | Union, deduplicated, sorted |
| `decision_tags` | Union, deduplicated, sorted |
| `intents` | Ordered unique non-empty values |
| `goal` | Derived (see Goal Derivation) |
| `significance` | Max (`high` > `minor` > `routine`) |
| `change_types` | Set of all values, sorted |
| `branch`, `vendor`, `model`, `agent`, `machine_label` | From first snippet |
| `architect` | First non-empty (truthy-first pattern) |
| `transcript_session_id`, `transcript_ref` | First non-empty (truthy-first pattern) |
| `notes` | Concatenated from all snippets, preserving order |

Sort snippets within a session by `started_at`, then `ended_at`, then `commit`.

## Goal Derivation

1. Single unique non-empty intent → use it
2. Multiple → prefer first whose `change_type` not in `{release, merge, cleanup}`
3. None qualify → first non-empty intent
4. Still empty → `None`

## Freshness Check

Fingerprint-based, not timestamp-based:

1. Read all snippets for the `(repo, session_id)` group
2. Compute `snippet_fingerprint()` — SHA-256 over raw file bytes of each snippet, sorted alphabetically, combined
3. Check cached summary at `~/.gator/sessions/<path-hash>/<repo-hash-6>-<session_id>.json`
4. If cached fingerprint matches → return cached
5. If differs → regenerate and replace
6. If no cache → generate from scratch

## Repo Identity

Repos are identified by **path-hash** (12-char SHA-256 of resolved path) throughout the stack:
- Cache directories: `~/.gator/sessions/<path-hash>/`
- Cache filenames: `<repo-hash-6>-<session_id>.json`
- API: `GET /api/audit/sessions?repo=<path-hash>`
- DOM IDs: `detail-<repo_key>-<session_id>`
- Summary payload: `repo_key` field

Human-readable names are display-only, resolved via `_repo.json` or the dashboard registry. The `repo_key` field is first-class in the summary schema from aggregation through cache, CLI, API, and UI.

Fleet data (both command-post and standalone) includes `repo_key` per repo via `_inject_repo_keys()`.

## Test Coverage

64 tests across the aggregator stack:

- **27 tests** in `test_session_aggregator.py`: snippet reading, aggregation, goal derivation, transcript-ref, fingerprinting, cache freshness, fleet iteration
- **27 tests** in `test_audit.py`: decision filtering, renderer invariants (text + HTML), assembler→renderer seam, session CLI
- **10 tests** in `test_dashboard_sessions.py`: endpoint resolution, repo-hash lookup, refresh propagation, fleet mode, command-post integration

## What Is Shipped (v1.2.0+)

- Aggregator library (`gator-session-aggregator.py`)
- Machine-local cache at `~/.gator/sessions/<path-hash>/`
- Dashboard API endpoint `GET /api/audit/sessions`
- Dashboard Audit view with session table, expandable rows, fleet toggle
- `gator audit --sessions` CLI (text + JSON, fleet, refresh)
- Cross-document search with AND/OR operators (indexes snippets)
- Audit tab visible in standalone mode

## What Is Not Shipped

- `View session` link from snippet file view to Audit (snippet → Audit navigation not wired yet)
- Transcript DB integration (deferred — local transcript lookup from session context)
- Explicit session open/close semantics (uses 2-hour age heuristic)
- Transcript drill-down (waiting for `transcript_ref` population)
- Enterprise export connector (future — reads from `~/.gator/sessions/`)
- Session timeline visualization, decision density, file heat map, significance trend (captured in inbox)

## Invariants

- Snippets (in git) are the single source of truth
- Summaries (at `~/.gator/sessions/`) are always re-derivable from snippets
- Deleting `~/.gator/sessions/` and regenerating produces identical results
- `(repo, session_id)` is the canonical aggregation key
- The aggregator never mutates snippet files — reads snippets, writes to `~/.gator/sessions/`
- The aggregator handles missing or corrupt snippets gracefully (skip, don't crash)
- Freshness is driven by full-content fingerprint, not timestamps or commit hashes alone
- No repo is dirtied by Audit browsing
- `repo_key` is a first-class identity field from aggregation through UI

## Key Charters

- `scripts-session-archaeology` — aggregator functions, SnippetRecord contract, cache identity
- `scripts-cross-cutting` — fingerprint pattern, lazy import pattern, `import_sibling` usage
- `scripts-fleet-intelligence` — `--sessions` CLI, renderer extraction, assembler→renderer seam
- `scripts-dashboard` — `/api/audit/sessions` endpoint, Audit view, search, `_inject_repo_keys`
