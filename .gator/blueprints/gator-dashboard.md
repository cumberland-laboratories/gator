# Gator Dashboard

## What This Page Is

This page explains the Gator Dashboard: what it is, what it does at each scale, what's built, and what's coming. It covers the product vision, the current feature surface, and the architecture that connects them.

If the Architect asks "what can the Dashboard do?" or "where is the Dashboard headed?" — this page should answer it.

## The Three Scales

The Dashboard serves three audiences at three scales. The same codebase, the same local server, the same read-only posture — but the questions change as the scope widens.

### Scale 1: Repo Knowledge Console

**Audience**: A developer working in one repo with AI assistance.

**Core question**: What is happening in this repo right now?

At this scale, the Dashboard is where code meets documentation in real (commit) time. Every commit produces governance metadata — charters, trailers, session snippets, status — and the Dashboard makes that metadata readable without leaving the browser. It replaces the need to grep `.gator/` manually.

**What it shows**:
- The knowledge layer as a browsable file tree (`.gator/`, `gator-command/`, source files)
- Pulse: the strategic operations brief — project state in one page
- Charter coverage: which modules have maps, which don't
- Session snippets: what context produced each recent commit
- Committed session summaries: searchable session history
- Enforcement posture: strict, warn, or off — and why

**The value**: A single developer with one gatorized repo opens the Dashboard and sees the full intelligence surface of their project. Not a code editor. Not a terminal. The place you go to understand the state of the project before you start working.

At this scale, the Dashboard starts to occupy territory that ordinary Git UIs do not. GitHub Desktop, GitKraken, and similar tools help a human operate Git: stage, commit, branch, sync, resolve. The Dashboard answers a different class of questions:

- What is happening in this repo?
- Why did this branch move?
- What workstream does this commit belong to?
- Which agent and architect drove these changes?
- What session context produced this commit?

That is the beginning of Gator as an **engineering intelligence surface over Git**, not just a governance dashboard.

### Scale 2: AI-Coding Coordination

**Audience**: A team lead or architect coordinating AI-assisted coding across multiple repos.

**Core question**: Are my repos healthy, current, and governed?

At this scale, the Dashboard becomes a fleet operations console. Multiple repos, potentially multiple AI vendors (Claude, Codex, Gemini), multiple developers — all visible from one surface. The coordinator doesn't need to clone every repo or open every terminal. They see fleet-wide governance posture from registry + git state.

**What it shows**:
- Fleet view: every registered repo with generation, branch, charter count, last commit age, hook status
- Drift detection: which repos are stale, which have outdated hooks or policy
- Session evidence across the fleet: which repos have AI session coverage, which don't
- Governed commits by repo: who is committing governed code, and how much
- Per-repo status drill-down: click any repo to see its full knowledge layer
- Fleet updates: push template/hook updates to repos from the command post

**The value**: An engineering lead with 12 gatorized repos opens the Dashboard and sees governance posture across the fleet in seconds. No cloning, no terminal archaeology. The repos that need attention surface immediately.

### Scale 3: Audit and Compliance Surface

**Audience**: A compliance officer, security reviewer, or acquirer evaluating AI governance practices.

**Core question**: Can you prove human oversight of AI-generated code?

At this scale, the Dashboard is an evidence surface. It doesn't generate the evidence — the pre-commit hooks, session logging, and trailer pipeline already produce it. The Dashboard makes that evidence navigable, queryable, and presentable.

**What it shows**:
- Governed commit metrics: hook coverage %, governed commit count, charter-changed ratio
- Override events: who approved what override, when, and why
- Session evidence table: date, repo, vendor, agent, goal, decision count — with drill-down
- Significance distribution: how many critical/high/medium/low/routine changes over time
- Sessions by vendor: cross-vendor AI usage distribution
- (Planned) EU AI Act Article 14 evidence pack: structured compliance evidence from existing data

**The value**: An auditor opens the Dashboard and sees structured evidence of human oversight across the fleet. Every governed commit links to a session snippet. Every override has an approver. Every session has vendor attribution. The evidence is in Git — the Dashboard just makes it legible.

## Architecture

### Design Principles

1. **Read-only by default.** The Dashboard reads from Git, `.gator/`, and CLI JSON outputs. The few write operations (enforcement level, topology toggle, fleet update) are explicit, guarded, and auditable.

2. **Business logic stays in CLI.** The Dashboard is a thin renderer. `gator-fleet-report`, `gator-drift`, `gator-audit`, `gator-repo-status` — these scripts own the data. The Dashboard calls them, caches results, and renders HTML/JS. No governance logic lives in the frontend.

3. **Local-first, no infrastructure.** `python gator-dashboard.py` starts a local HTTP server. No cloud, no database, no Docker. Data comes from the filesystem and Git. Works air-gapped.

4. **Two-tier data loading.** Tier 1 (fleet + audit + drift) runs at startup — feeds Fleet and Audit views immediately. Tier 2 (per-repo deep status) loads lazily when a repo is clicked — feeds the Repo view on demand. This keeps startup fast even with large fleets.

5. **Dual-mode rendering.** Command-post mode shows the full fleet/audit/updates surface. Standalone/repo mode shows a simplified view driven from registry.md alone. The Dashboard degrades gracefully — a bare gator clone with no command post still works.

### Data Flow

```
Git history + .gator/ state + CLI scripts
        │
        ▼
  Tier 1: gator-fleet-report, gator-drift, gator-audit (startup)
  Tier 2: gator-repo-status (on demand, per repo)
        │
        ▼
  DashboardHandler.fast_data (in-memory cache)
        │
        ▼
  /api/data (Tier 1), /api/repo/<name> (Tier 2)
        │
        ▼
  Frontend JS views (fleet.js, audit.js, repo.js, etc.)
```

### Startup Modes

| Mode | Condition | Tier 1 | Fleet view | Audit view | Updates |
|------|-----------|--------|------------|------------|---------|
| Command-post | `find_command_post()` succeeds | Full | Full fleet table | Full metrics | Active |
| Standalone | No command post, has registry | Skipped | Simplified repo list | Limited | Active |
| Snapshot | `--snapshot` flag | Pre-embedded | Static render | Static render | Disabled |

## What's Built (v1)

### Views

| View | Status | Primary question |
|------|--------|-----------------|
| **Fleet** | Shipped | Which repos are healthy? Which are stale? |
| **Repo** | Shipped | What does this repo's knowledge layer look like? |
| **Audit** | Shipped | Can I show human oversight? Where are the gaps? |
| **Updates** | Shipped | Is my gator install current? |
| **Settings** | Shipped | How should each repo be governed? |

### Key Capabilities

- Markdown file browser with collapsible sidebar, image embedding, copy-path
- Per-repo enforcement level editor (strict / warn / off)
- Per-repo topology selector (policy-synced / standalone)
- Session evidence modal with vendor/agent/goal drill-down
- Significance distribution chart (7-day window)
- Override events table with approver attribution
- Fleet-wide template update push
- Snapshot mode: self-contained HTML export for offline sharing
- Async background refresh
- Cross-platform (Windows CMD, PowerShell, Git Bash, macOS, Linux)

### Backend API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/data` | GET | Fleet + audit + drift data (Tier 1) |
| `/api/repo/<name>` | GET | Per-repo deep status (Tier 2) |
| `/api/repo/<name>/files` | GET | File list for markdown browser |
| `/api/repo/<name>/file/<path>` | GET | Read a specific file |
| `/api/repo/<name>/raw/<path>` | GET | Binary file serving (images) |
| `/api/repo/<name>/config` | POST | Set enforcement level |
| `/api/repo/<name>/topology` | POST | Switch governance topology |
| `/api/repo/<name>/update` | POST | Run gator-update on repo |
| `/api/repo/<name>/check` | GET | Dry-run update check |
| `/api/updates/check` | GET | Check for upstream commits |
| `/api/updates/fetch` | POST | git fetch origin |
| `/api/updates/pull` | POST | Apply upstream updates |
| `/api/session` | POST | Fetch session summary markdown |
| `/api/refresh` | GET | Async refresh Tier 1 data |

## What's Coming

### MVP Priority (by 2026-06-30)

| Feature | Status | What it adds |
|---------|--------|-------------|
| **Session evidence quality** | Building | Fix extraction (goals, file lists), `--repo` filter, empty session filtering |
| **Audit view refinement** | Designed | Evidence pack layout, session-to-commit traceability via snippets |
| **Dashboard search** | New | Full-text search across .gator/ files — find any decision, charter, or session |
| **Git history per file** | New | Dropdown of git versions in the file viewer — see how any file evolved |

### Post-MVP

| Feature | What it adds | Scale |
|---------|-------------|-------|
| **EU AI Act Article 14 evidence pack** | Structured compliance evidence from session + trailer data | Audit |
| **MCP server** | Dashboard data exposed as Claude Code tools — fleet status in-session | Coordination |
| **Session lifecycle** | Explicit open/close semantics, long-session support | Repo |
| **Trailer analytics** | Override rates, significance distribution, review cadence trends across fleet | Audit |
| **Charter quality metrics** | Coverage %, stale charter age, high-churn modules with old charters | Repo |
| **Command Registry API** | `GET /api/commands` — canonical command catalog for agents and MCP | Coordination |
| **Cross-model review handoff** | Review packet (diff + charters + tripwires), findings display | Audit |
| **"Add repo" button** | UI for registering a local repo via gatorize scenario 3 | Coordination |

## What the Dashboard Is Not

- **Not a code editor.** It doesn't write code, doesn't run tests, doesn't manage branches. Agents do that in terminals.
- **Not a hosted platform.** There is no cloud service, no login, no shared URL. It's a local tool that reads local state.
- **Not a CI/CD surface.** It doesn't trigger builds, run pipelines, or deploy. It reads the evidence those systems produce.
- **Not a replacement for Git.** Git is the source of truth. The Dashboard renders what Git already carries.

The Dashboard is the intelligence layer made visible. Everything it shows already exists in `.gator/` and `git log`. The Dashboard just makes it legible to humans who don't want to grep for it.

## The Positioning Insight: Engineering Intelligence Over Git

The Dashboard should not be framed as "a better Git GUI." That is the wrong category. Traditional Git surfaces are optimized for transport and code review:

- stage
- commit
- push
- pull
- diff
- merge
- resolve conflicts

The Dashboard is headed toward a different role: the place a human opens to understand **AI-assisted engineering activity expressed through Git**.

Git answers:

- what changed in the files
- what commits exist
- what branches point where

The Dashboard can answer:

- what is happening in this repo right now
- why a branch moved
- which commits belong to the same working arc
- which architect and agent produced a change
- what context produced a governed commit
- which repos, branches, or sessions deserve attention first

That is why session snippets, commit intent, repo time-travel, branch history, governance metadata, and audit evidence all belong in one surface. The Dashboard is not trying to replace Git's source-of-truth role. It is building the missing **intelligence layer above Git**.

## The Positioning Insight: Notion with Git as the Backend

Every Git UI — GitHub, GitLab, VS Code, Sourcetree — is built for *code review*. Diffs, line-by-line changes, merge conflicts. Great when the artifact is code. But when the artifact is *knowledge* — decisions, architecture docs, session logs, roadmaps — diffs are useless. Nobody reviews a roadmap by looking at green/red lines. You read the document.

The Gator Dashboard is a **read-only document console** with Git as the versioning backend. The same mental model as Notion or Confluence — browse documents, read them rendered, navigate between them — but with properties no hosted tool can match:

- **No proprietary backend.** The documents are markdown in Git. The data never leaves the machine.
- **Full version history per file.** Not "last edited by" — actual commits with messages explaining *why* it changed. Every file has a history dropdown showing every commit that touched it.
- **Full repo time-travel.** Not "restore previous version" — see the entire knowledge layer as it existed at any commit. The branch history dropdown lets you browse the repo at any point in its history.
- **No sync conflicts.** Git already solved this.
- **No login, no cloud, no subscription.** `python gator-dashboard.py`.

**The read-only constraint is a feature, not a limitation.** The user is already in Claude Code (or Codex, or Cursor) in another terminal. That's where edits happen — governed by charters, validated by hooks, committed with trailers. The Dashboard doesn't need to be a writing surface. It needs to be the *reading* surface — the place you go to understand what exists, what changed, and when.

**Where this gets powerful**: The combination of rendered markdown + git history + session snippets means an architect can:

1. Open the roadmap → see the current state rendered
2. Click the file history dropdown → see every commit that touched the roadmap
3. Click a historical version → read the roadmap as it was 3 weeks ago
4. Click the branch history dropdown → time-travel the whole repo to that date
5. Browse the session snippets from that period → see what context produced those changes

That's **project archaeology in a browser**. No terminal, no grep, no `git show`. The audience isn't developers reading code — it's architects, leads, and auditors reading *decisions*.

**The competitive gap**: Every competitor's governance or docs tool either (a) runs hosted with a proprietary backend, or (b) shows diffs and blames designed for code, not content. The Dashboard is the first tool that treats the knowledge layer as a *reading experience* — rendered, navigable, versioned, local-first — while the coding tool of choice handles the writing. Over time, that same reading surface becomes the intelligence layer a human uses to understand commits, branches, sessions, and governed change without living inside a generic Git UI.

## Participating Modules

| Module | Role |
|--------|------|
| `gator-dashboard.py` | HTTP server, Tier 1/2 orchestration, snapshot mode |
| `dashboard/dashboard.html` | Shell, navigation, view slots |
| `dashboard/dashboard.js` | Router, state management, refresh, session modal |
| `dashboard/dashboard.css` | Styling |
| `dashboard/views/fleet.js` | Fleet operations surface |
| `dashboard/views/audit.js` | Governance posture and evidence |
| `dashboard/views/repo.js` | Markdown file browser |
| `dashboard/views/updates.js` | Self-update control |
| `dashboard/views/settings.js` | Per-repo governance config |
| `gator-fleet-report.py` | Fleet status data (Tier 1 source) |
| `gator-drift.py` | Drift detection data (Tier 1 source) |
| `gator-audit.py` | Audit metrics data (Tier 1 source) |
| `gator-repo-status.py` | Per-repo deep status (Tier 2 source) |

## Connections

- [Dashboard v1 reference note](../reference-notes/gator-dashboard-v1.md) — founding specification
- [Dashboard charter](../../.gator/charters/dashboard.md) — module ownership and before-changing rules
- [Session Intelligence blueprint](session-intelligence.md) — session snippets and summaries that feed Audit view
- [Hook Pipeline blueprint](hook-pipeline.md) — pre-commit/post-commit hooks that produce governance metadata
- [Roadmap](../roadmap.md) — MVP priorities and post-MVP feature set
- [MCP Server plan](../artifacts/2026-06-04-mcp-server-implementation-plan.md) — Dashboard data exposed as agent tools
