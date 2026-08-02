# Gator Dashboard v1

Gator should have a lightweight local dashboard.

Not a platform.
Not a hosted control plane.
Not a separate source of truth.

The dashboard should be a thin local web UI over information that already exists in:

- Git history
- commit trailers
- `.gator/` state in governed repos
- command-post registry and policy state
- existing Gator CLI JSON outputs

## Product Shape

The mental model is:

- `gator dashboard`

This command starts a small local server on `localhost` and opens a browser view of governance state.

The UI should be:

- local-first
- read-only by default
- fast
- driven by existing CLI outputs
- useful for fleet operations, audit questions, and repo triage

## Why This Matters

The dashboard creates a visible governance surface.

That matters for three reasons:

1. It makes Gator legible in seconds.
2. It creates concrete metrics and states to design backward from.
3. It gives users a place to ask audit and compliance questions without introducing a SaaS platform.

## Source of Truth

The dashboard should not invent a new backend.

The source of truth remains:

- Git
- `.gator/`
- `gator-command/`
- existing CLI scripts

The dashboard is only a renderer and coordinator.

## Architecture Rule

Business logic stays in the CLI.

The dashboard should consume JSON from commands like:

- `gator fleet-report --json`
- `gator drift --json`
- `gator audit --json`
- future `gator repo-status --json`
- future `gator dashboard-data --json`

That keeps the architecture clean:

- CLI remains the primary machine interface
- dashboard becomes a thin view layer
- report generation and automation can reuse the same JSON

## Command Surface

### Primary command

`gator dashboard`

Expected behavior:

1. collect current governance data through CLI JSON surfaces
2. start a tiny local HTTP server
3. serve a static or mostly-static web app
4. optionally open the default browser

Suggested flags:

- `--port 8420`
- `--no-open`
- `--snapshot`
- `--remote`
- `--repo <name-or-path>`

### Snapshot mode

`gator dashboard --snapshot > dashboard.html`

This generates a self-contained HTML snapshot, similar to `gator audit --html`, but optimized for interactive browsing rather than static reporting.

## V1 Views

V1 should stay small.

### 1. Fleet View

Purpose:

- answer "what is the governance health of my fleet?"

Display:

- registered repos
- repo generation / governance release
- governance drift status
- charter coverage status
- hook health
- latest governed commit
- latest `Gator-Agent`
- latest `Gator-Architect` (formerly `Gator-PI`)
- override count in recent window

Primary questions:

- which repos are healthy?
- which repos are out of date?
- which repos are missing hooks or charters?
- which repos saw recent significant governed activity?

### 2. Repo View

Purpose:

- answer "what is the state of governance in this repo?"

Display:

- current branch
- latest governed commits
- current charter coverage
- stale charter candidates
- recent significance levels
- recent change types
- override events
- recent enforcer findings summary
- status of committed session summaries

Primary questions:

- is this repo governable right now?
- are charters keeping up with code?
- has anything risky happened recently?
- what changed, and under whose supervision?

### 3. Updates View

Purpose:

- answer "what can I roll out from the command post right now?"

Display:

- latest available governance release
- repos already current
- repos with safe overlay updates
- repos requiring manual review
- repos blocked by drift or local divergence
- compact update notes

Primary questions:

- what can be updated automatically?
- what needs a human look?
- where are rollout bottlenecks?

### 4. Audit View

Purpose:

- answer "what evidence do I have?"

Display:

- governance coverage percentages
- hook coverage
- override history
- significant changes in time window
- agent / Architect counts
- enforcer review counts
- committed session summary coverage

Primary questions:

- can I show human oversight?
- which repos are weak on evidence?
- where are overrides concentrated?

### 5. Pipelines View

This can be v1.5 if needed.

Purpose:

- answer "what happened across model/tool handoffs?"

Display:

- recent handoff artifacts
- plan -> implementation transitions
- diff -> enforcer review transitions
- pending review checkpoints
- blocked or failed governance seams

This depends on formalizing pipeline seam artifacts first.

## Data Model for the Dashboard

The dashboard should normalize around a few key entities.

### Repo

- name
- path
- branch
- remote status
- generation / governance release
- hook status
- charter status
- drift status

### Governed Commit

- commit hash
- timestamp
- repo
- `Gator-Agent`
- `Gator-Architect` (formerly `Gator-PI`)
- `Gator-Change-Type`
- `Gator-Significance`
- `Gator-Charter-Changed`
- charter counts / function counts when available

### Override Event

- repo
- commit
- timestamp
- approver identity when available
- reason
- block type

### Enforcer Event

- repo
- timestamp
- review type
- finding count
- severity summary
- result path or whiteboard reference

### Governance Release

- release id or tag
- publish timestamp
- repo compatibility notes
- safe overlay vs migration-required

## What We Can Already Get from Git + Local State

A surprising amount is already available.

### From Git history

- commit timestamps
- author/committer identity
- branches
- tags
- trailers
- recent change cadence
- governance metadata embedded in commit history

### From trailers

- who the agent was
- who the Architect was
- significance classification
- change type classification
- whether charter updates traveled with code
- counts of changed charters/functions when present

### From governed repos' `.gator/`

- status files
- whiteboard state
- override artifacts
- current constitution / charter presence
- committed session summary presence

### From the command post

- fleet registry
- org policy version / source state
- release metadata
- drift and audit outputs

That means a useful dashboard is already feasible without a new database.

## Compliance and Audit Questions the Dashboard Should Answer

This is the critical design filter.

The dashboard should make these questions easy to answer:

- Which repos are currently governed?
- Which repos are out of policy?
- Which repos are missing hooks or charters?
- Which repos had significant changes this week?
- Which significant changes lacked recent enforcer review?
- Which repos had overrides, and why?
- Who was the supervising Architect for recent governed work?
- Which models are writing code most often?
- Are committed session summaries present where expected?
- What is my current governance coverage across the fleet?

If a dashboard feature does not help answer one of these, it is probably not v1.

## UX Principle

The dashboard should not feel like a giant admin product.

It should feel like:

- a local governance console
- a fleet status wall
- a Git-native audit lens

The first screen should be legible in under 15 seconds.

## Recommended Implementation Order

### Phase 1: JSON hardening

Make sure these outputs are stable and well-structured:

- `gator fleet-report --json`
- `gator drift --json`
- `gator audit --json`

Add:

- `gator repo-status --json`

### Phase 2: Thin local dashboard

Add:

- `gator dashboard`

Use:

- small Python HTTP server
- static HTML/CSS/JS bundle
- no framework or a very small one

### Phase 3: Snapshot export

Add:

- self-contained HTML snapshot
- saved JSON bundle for offline inspection

### Phase 4: Governed pipeline seams

Once seam artifacts exist, add:

- Pipelines view
- handoff health
- review boundary state

## Design Constraints

Keep these constraints explicit:

- no mandatory cloud
- no separate persistent database for v1
- no duplicated business logic in the UI
- read-only by default
- degrade gracefully when some repos are offline

## Best Product Sentence

Use this when needed:

`Gator Dashboard is a local governance console for AI-assisted development, built entirely from Git and repo-native state.`

## Connections

- -> [Gator as the Supervision Layer for AI Autonomy](gator-as-supervision-layer-for-ai-autonomy.md) - why the dashboard matters as a supervision surface
- -> [Gator Layering Over Agent and Spec Stacks](gator-layering-over-agent-and-spec-stacks.md) - why the dashboard should govern rather than replace local stacks
- -> [Repo Layer Charter Authority](repo-layer-charter-authority.md) - avoids confusing source-repo and governed-repo data surfaces
