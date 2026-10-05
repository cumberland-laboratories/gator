---
date: 2026-08-25
type: implementation-plan
topic: blueprints-2-0
status: draft-r1
model: claude-opus-4-7
---

# Blueprints 2.0 — Implementation Plan (r1)

## Purpose

Turn Blueprints 2.0 from a vault experiment + roadmap wishlist into a productized, Dashboard-native **Architect inspection workbench**. Ship the four-level progressive-disclosure surface incrementally, with the L1 charter map re-founded as the beachhead and L2 (charter→surfaces drill-down) as the immediate next artifact. Do all of this on top of the charter layer we already maintain — that is the head start.

Scope this plan to what gets us to a usable, Dashboard-integrated L1+L2 by the end of the initial ride, with L3+L4 defined enough to not paint us into a corner.

## Strategic anchors (compressed from the vault reviews)

- **Why critical** ([`2026-08-17-why-blueprints-2-0-is-critical.md`](../vault/artifacts/2026-08-17-why-blueprints-2-0-is-critical.md)): Blueprints 2.0 is Gator's differentiator vs. runtime-orchestration competitors (Omnigent-class). It is the visible expression of the **semantic inspection layer** that keeps the human Architect an effective reader of the system while AI writes it. Legacy-codebase safety is the sharpest wedge. Not "diagram generator" — **inspection workbench**.
- **How understanding actually happens** ([`2026-08-14-charter-first-code-understanding-heuristic.md`](../vault/artifacts/2026-08-14-charter-first-code-understanding-heuristic.md)): Effective models (and effective Architects) do not read the codebase — they build a compressed model from charters first, then read source only to verify. Six stages: **Orient → Localize → Verify → Expand → Reconcile → Decide**. Cross-cutting charter FIRST is epistemically correct, not ceremony. Blueprints 2.0 should externalize this path as a UI.
- **What the four levels are** ([`2026-08-09-charter-flowchart-architect-inspection-exploration.md`](../vault/artifacts/2026-08-09-charter-flowchart-architect-inspection-exploration.md)): L1 charter map (intentional architecture) → L2 charter→covered surfaces → L3 curated function map (NOT every helper) → L4 drift map (charter-declared vs code-observed). Core insight: **the charter graph is the intentional model, the code graph is the observed model, and inspection happens at the boundary between them.**

## What the Level 1 experiment taught us

Source: [`.gator/vault/blueprints/charter-flowchart-high-level.html`](../vault/blueprints/charter-flowchart-high-level.html) (822 lines, one file, zero deps).

**Tech pattern (keep as-is for productization)**:
- Vanilla HTML + inline CSS + inline JS. No build step. No CDN. Same architecture rule as Dashboard: framework-free, self-contained.
- Nodes: absolute-positioned `<article class="node">` inside a fixed-size canvas (`1180×880px`). Position stored as `{x, y}` in a JS constant.
- Edges: SVG `<path>` with cubic-Bézier midpoint control (`M x1 y1 C mx y1, mx y2, x2 y2`), marker-based arrowheads, labels via `<textPath>` on the same path.
- Interaction: click node → compute active neighborhood (self + 1-hop in/out) → toggle `active`/`faded` CSS classes on nodes and edges; double-click canvas resets. Detail sidebar re-renders dynamic sections (`Depends On`, `Used By`, `Representative Surface`, `Representative Functions`).

**Data model (both hand-authored today; needs to become charter-derived)**:
```
node  := { id, title, kind, color, x, y, summary, covers[], functions[] }
edge  := { from, to, label }
```

**What is missing today** (all deferred by the L1 experiment on purpose):
- No edge-type distinction (runtime / governance / packaging / conceptual all look the same).
- No tripwire visibility.
- No "does not own" surfacing.
- No coverage-density signal.
- No auto-generation — nodes/edges/positions are hand-authored in the HTML.
- No Dashboard integration — the file only opens via `window.open()` from the Repo file browser (v2.4.5 HTML support).

## Tooltip ideas for L1 (small, high-signal additions)

Design constraint: **don't over-tooltip.** L1's job is orientation. Tooltips are aids for a lingering hover, never a substitute for click-through into L2.

Priority order (top = ship first):
1. **Node hover: kind + first sentence of `summary`** — currently only visible after click. Cheap unlock; hover latency `~200ms` so passive scan doesn't spam.
2. **Node hover: coverage-density line** — `N files · M functions` from the charter body. Helps you see which nodes are dense before clicking.
3. **Node hover: tripwire count badge** — small `!N` corner marker on nodes whose charter has ≥1 `!` entry; hover surfaces titles. Makes "danger zones" visible at L1 without an extra level.
4. **Edge hover: source charter section** — currently the label is on the path (`shared contracts`, `governance obligations`, …); hover could reveal *which charter section declared the connection* (usually `## Connections`), so you can jump straight to the prose behind the edge.
5. **Node hover: "does not own" preview** — bottom of tooltip, one line pulled from the charter's `## Does Not Own`. This is the negative-space signal that raw call graphs cannot give you and that the vault "why critical" note calls out specifically.

Deferred to L2 (do NOT put on L1 tooltips): caller/callee lists, per-function summaries, drift markers. Those exist so L1 stays legible.

## Data source strategy — the head start we already have

The single biggest leverage point: **stop hand-authoring the graph.** Charter files already carry every field a blueprint needs:

| Blueprint field | Charter surface |
|---|---|
| Node title / kind | Charter file `# Charter: <name>` + first line of `## Owns` |
| Covered files | `**Covers**:` header |
| Representative functions | `###` function entries |
| Callers / callees | `←` / `→` markers inside function entries |
| Tripwires | `!` markers inside function entries |
| Boundary / negative space | `## Does Not Own` section |
| Cross-charter edges | `## Connections` (`-> [name](path.md)`) |
| Code→charter routing | `.gator/charters/INDEX.md` dispatch table |

**Proposal**: a new CLI script `gator-blueprint.py --json [--level 1|2|3|4] [--focus <charter-id>]` that parses `.gator/charters/*.md` + `INDEX.md` and emits the same `{nodes, edges}` shape the HTML expects. Dashboard renders JSON; blueprint logic stays in CLI (respects `scripts-dashboard.md` architecture rule: "business logic stays in CLI scripts").

Layout positions are the one thing the parser cannot infer well. Options:
- (a) Hand-tuned overlay committed at `.gator/blueprints/positions.json` (repo-local, survives regenerations).
- (b) Deterministic auto-layout in JS (dagre-like leveled layout, no external lib — a leveled sort by dependency depth is ~100 lines of vanilla JS).
- (c) Hybrid: auto-layout by default, overlay wins where present. **Recommended.**

## Dashboard integration — the biggest payoff

This is where L1 stops being a curiosity and becomes an inspection surface. Concrete design:

### Sidebar placement
Add `Blueprints` as a new item in the sidebar's **Knowledge** group (peer of `Docs`). Requires an active repo (same dimming rule as `Docs` today). Rationale: Blueprints is *about* repo comprehension, and users already know to enter that group after picking a repo from Fleet.

```
Overview
  Fleet
  Repo
  History
Knowledge
  Docs
  Blueprints        ← new
System
  Updates
  Settings
```

### View module
New file `src/gator_command/scripts/dashboard/views/blueprint.js` (shipped, per-CLI-version). Follows the same IIFE + `window.GatorViews.blueprint()` registration pattern as `views/repo.js`. Charter for `scripts-dashboard.md` needs one new `Covers:` entry and one function-level charter row.

### Backend endpoints
Minimal new surface, all thin delegates to the CLI:
- `GET /api/repo/<name>/blueprint?level=1` — returns `{nodes, edges, generated_at}`. Runs `gator-blueprint.py --json --level 1 --path <repo>` via `run_json()`.
- `GET /api/repo/<name>/blueprint?level=2&focus=<charter-id>` — returns L2 payload for one charter (files, function summaries, in-cluster edges).
- `GET /api/repo/<name>/blueprint?level=4` — later; drift payload.

Existing `GET /api/repo/<name>/file/<path>` handles the L3→source drill: click a function name, open the containing file in the same content pane the Repo view already renders.

### Screen layout (L1 view, Dashboard-integrated)
```
┌ topbar: <repo> — Blueprints — L1 charter map ─────────────────┐
├ view-slot ─────────────────────────────────────────────────────┤
│  ┌ canvas (SVG + nodes, click-to-isolate) ──┐  ┌ detail ────┐ │
│  │                                            │  │ kind       │ │
│  │       [nodes and edges as today]           │  │ title      │ │
│  │                                            │  │ summary    │ │
│  │                                            │  │ ───────    │ │
│  │                                            │  │ Covers     │ │
│  │                                            │  │ Functions  │ │
│  │                                            │  │ Depends On │ │
│  │                                            │  │ Used By    │ │
│  │                                            │  │ Tripwires  │ │  ← new
│  │                                            │  │ [Drill L2] │ │  ← new
│  └────────────────────────────────────────────┘  └────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

The vault HTML's own layout is already close to this. Porting into the Dashboard shell mostly means adopting the existing sidebar/topbar chrome, wiring the fetch, and moving from hard-coded `nodes[]`/`edges[]` to the JSON endpoint.

### Screen layout (L2 drill-down)
Right-panel `Drill L2 →` swaps the canvas contents (not a route change — preserve the L1 → L2 → L1 back-flow via a shallow view-state stack). L2 canvas is a **single-cluster expansion**: covered files as nodes, in-cluster function edges. "Escape" or breadcrumb click returns to L1 with the previously-focused node restored.

### Snapshot & offline mode
`build_snapshot()` already inlines JSON as `window.DASHBOARD_DATA`. Extend the snapshot payload with a materialized L1 blueprint so the offline HTML view still shows the charter map. L2+ can be no-ops in snapshot (matches HTML-in-vault current behavior; snapshot is a static report).

## Next-level sketch — L2 (charter → covered surfaces)

The 2026-08-09 exploration nominated `repo-lifecycle` or `fleet-intelligence` as the pilot cluster. **Recommendation: `fleet-intelligence`**. Rationale: it fans out to four scripts (`gator-fleet-report`, `gator-drift`, `gator-audit`, `gator-repo-status`) + is a consumer of `session-archaeology` + is the Dashboard's primary data source, so the L2 view exposes both the "covered files" mechanic AND cross-cluster hand-off edges. `repo-lifecycle` is denser but more homogeneous.

**L2 data model**:
```
file    := { path, role, functions[], tripwire_count }
                                          # role: orchestrator | helper | data | boundary
funcref := { name, callers[], callees[], tripwires[], summary_line }
cluster := { charter_id, title, files[], internal_edges[],
             does_not_own[], out_edges_to[<other_charter>] }
```

**L2 interaction**:
- Files rendered as a second-tier node cluster; functions surface as sub-list items on hover/click.
- Files with `!` (tripwires) get the danger marker inherited from L1.
- `## Does Not Own` becomes a persistent side-note ribbon at the top of the cluster ("Not owned here: X, Y, Z"). This is the negative-space payoff.
- Clicking a file opens it in the Repo content pane (existing endpoint); clicking a function scrolls to the `###` heading in the charter markdown (also existing — Repo view renders charter files today).

**L2 is where the Architect actually starts inspecting.** L1 is orientation; L2 is where "what does this module own, and what does it explicitly not own?" gets answered.

## Later levels (defined, not yet scheduled)

### L3 — curated function map
- Show only architecturally significant functions (public entry points, orchestrators, meaningful seams).
- Curation signal: functions that appear in the charter's function-entry list are "significant"; everything else is elided. That gives us the aggressive curation the 2026-08-09 exploration warned we would need.
- Edges: caller/callee within the L2 cluster; cross-cluster edges as stub arrows to the L2 boundary.

### L4 — drift map (likely the strategically most valuable level)
- Compare `**Covers:**` declaration in charter vs `git ls-files` reality → surface undeclared files under a charter's presumed path AND declared files that no longer exist.
- Compare `←`/`→` charter claims vs `rg`-observable references → surface undeclared cross-boundary calls AND declared callers that no longer exist.
- Surface `!` tripwires with no detectable defensive code as inspection prompts.
- **Framing rule**: drift markers are inspection PROMPTS, not verdicts. Language: "worth checking," not "violation." The vault reviews are explicit about this — we destroy the tool's credibility if it cries wolf.

## Phase plan (effort tiers, not calendar)

| Phase | Deliverable | Effort | Blocks |
|---|---|---|---|
| **P1** | `gator-blueprint.py --json --level 1` parser: reads charters + INDEX, emits `{nodes, edges}` matching the vault-HTML shape. Regression pin: parses this repo without errors, produces ≥14 nodes, ≥20 edges. | small | — |
| **P2** | Dashboard `Blueprints` sidebar item + `views/blueprint.js` + `/api/repo/<name>/blueprint?level=1` endpoint. Ports the vault HTML's L1 rendering into the Dashboard shell. Hand-tuned `positions.json` seeded from the vault HTML's current coords. | small-medium | P1 |
| **P3** | L1 tooltip pack (items 1-3 from tooltip section above): kind+summary, coverage-density, tripwire badges. | small | P2 |
| **P4** | `--level 2 --focus <id>` parser output + L2 in-view rendering (`fleet-intelligence` pilot). Second-tier canvas, does-not-own ribbon, click-through to files. | medium | P1, P2 |
| **P5** | Edge-type visual distinction (runtime / governance / packaging / conceptual). Charter parser infers type from `## Connections` prose OR from a new explicit annotation; four line styles. | small | P4 |
| **P6** | Snapshot integration — inline L1 blueprint in `build_snapshot()` payload so offline HTML retains the charter map. | small | P2 |
| **P7** | L3 curated function map (`--level 3 --focus <id>`). | medium | P4 |
| **P8** | L4 drift map (`--level 4`). Charter-vs-code diff, framed as inspection prompts. | medium-large | P1, P7 |
| **P9** | Cross-repo blueprints in the Fleet view. | large, later | P2 |

Bundle P1+P2+P6 as the first shippable slice — that gets us a Dashboard-native L1 with offline parity. P3+P4+P5 as the second slice. P7+P8 as the third. P9 is separate strategic work.

## Open decisions for the Architect

1. **Where does the parser live?** New script `src/gator_command/scripts/gator-blueprint.py` under the Repo Lifecycle charter, or wired into an existing script? Recommendation: standalone, following the `gator-repo-status.py` pattern (thin CLI, JSON-out).
2. **Positions strategy for L1 at first ship** — hand-tuned overlay only (a), auto-layout only (b), or hybrid (c). Recommendation: (c). Hand-tune this repo's coords to match the vault HTML; auto-layout fallback for repos with different charter shapes.
3. **L2 pilot cluster.** Recommendation: `fleet-intelligence`. Alternative: `repo-lifecycle` (roadmap-nominated). Pick one and build against real data; the other becomes the first regression case that stresses the generator.
4. **Where do generated blueprint files live?** Options: (i) never persisted, always live-computed on request; (ii) written to `.gator/blueprints/` on `gator update`, browsable via the file sidebar; (iii) both. Recommendation: (i) for now — thin renderer discipline; move to (ii) only if regeneration cost becomes user-visible.
5. **Snapshot HTML for the vault-experiment cluster** — retire the current standalone HTML once the Dashboard L1 view is live, or keep it as a demo asset? Recommendation: keep for demo/marketing, mark clearly as "generated equivalent of the Dashboard L1 view."
6. **Level 4 framing** — how loudly should drift findings appear? Options: (i) inline dots on L1/L2, (ii) separate L4 "review" view only, (iii) both with L1 dots gated behind a toggle. Recommendation: (iii). Default off — drift as prompts, opt-in as first-class view.

## Non-goals and cautions (carried forward from the vault reviews)

- **Not a call graph.** The value comes from the charter layer's *intentional* model. If we collapse this into automated call-graph rendering, we destroy the differentiator.
- **Not a diagram generator for marketing.** The 2026-08-17 note is explicit: this is an inspection workbench. Marketing renders are a downstream side effect, not the design target.
- **Do not overstate precision.** Runtime, governance, packaging, and conceptual edges must be visually distinguishable no later than P5 — before we start telling users this is an "architecture-truth surface."
- **Do not let L3 become an every-helper graph.** Aggressive curation via the charter's own function-entry list is the mechanism; do not add auto-discovery of unlisted helpers.
- **Drift = prompts, not verdicts.** L4 language ships as "worth checking," never "violation."
- **Preserve the human-reviewed nature of charters.** The generator reads charters; it does not rewrite them, and it does not silently propose charter edits from code observation. Drift surfaces where humans then act.

## Adjacent workstream — Dashboard concierge

Brainstormed separately in [2026-08-25 Dashboard concierge exploration](2026-08-25-dashboard-concierge-exploration.md). Short version: the concierge is a *thin conduit into the gatorized AI CLI the user is already running*, not a rebuilt intelligence stack. It complements Blueprints 2.0 (contextual "Ask about this" on L1/L2 nodes; concierge-abstention feeds L4 gap detection) without re-scoping any of the phases above. No plan changes today — the exploration deliberately leaves the transport axis open.

## Connections

→ [Why Blueprints 2.0 is critical](../vault/artifacts/2026-08-17-why-blueprints-2-0-is-critical.md) — strategic center
→ [Charter-first understanding heuristic](../vault/artifacts/2026-08-14-charter-first-code-understanding-heuristic.md) — the six-stage path this UI externalizes
→ [Charter flowchart exploration](../vault/artifacts/2026-08-09-charter-flowchart-architect-inspection-exploration.md) — the four-level model
→ [Starter experiment (L1 HTML)](../vault/blueprints/charter-flowchart-high-level.html) — 822-line reference implementation
→ [Charter Index](../charters/INDEX.md) — code→charter routing table (primary parser input)
→ [Dashboard charter](../charters/scripts-dashboard.md) — thin-renderer rule + integration surface
→ [Roadmap Priority 2](../roadmap.md#building--priority-2-blueprints-20) — five-item backlog this plan maps to
