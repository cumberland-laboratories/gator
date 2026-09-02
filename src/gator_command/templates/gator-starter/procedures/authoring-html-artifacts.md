# Authoring HTML Artifacts

## When to use

Reach for this procedure when you're about to create — or being asked to
create — an artifact where visual structure, interactive exploration, or
richer skimability would help the reader more than a plain markdown file.

Concrete triggers:

- Architect asks for a **blueprint** of a feature, subsystem, or flow.
- You're about to author a **charter map** for a repo (repo-wide node graph
  of chartered regions).
- You're documenting a **procedure** (release path, migration flow, audit
  process) whose steps + branches + tripwires would read better with visual
  chrome than plain prose.
- You're producing a **reference explainer** (architecture overview,
  capability landscape) where the reader benefits from headed sections and
  callouts.

Default is still markdown. HTML is the premium medium — reach for it when
visual structure materially improves comprehension.

**Since v2.12.0**: new blueprint content is authored in HTML. Existing markdown
blueprints in `.gator/blueprints/` stay put; no bulk conversion. New blueprints
never go into `.md`.

## Steps

### 1. Pick the template (two-lane triage)

Ask: **does the content have a natural node-and-edge structure that benefits
from interactive click-to-isolate exploration?**

- **Yes** — a graph of chartered regions, a feature flow across modules, a
  system-interaction map. → Use
  [`_template.html`](../blueprints/_template.html) (interactive blueprint,
  map + sidebar + narrative shape). Doc classes: `charter-map`,
  `feature-blueprint`.

- **No** — prose-heavy, step-sequenced, or otherwise not naturally graph-shaped.
  A release workflow, a concept explainer, an architecture overview that reads
  as narrative. → Use
  [`_template-narrative.html`](../blueprints/_template-narrative.html)
  (non-blueprint narrative, header + sequential sections, no interactive map).
  Doc classes: `procedure-visual`, `reference-explainer`.

Do NOT force non-graph content into the interactive template. The interactive
click-to-isolate affordance only earns its keep when there's a real
neighborhood to isolate.

### 2. Copy the template to the target location

Storage follows the artifact's role, not its rendering format:

- **`.gator/blueprints/`** (tracked): durable repo-wide artifacts.
  - `charter-map.html` — exact filename, one per repo.
  - `<slug>.html` — other durable blueprints or reference explainers.

- **`.gator/vault/artifacts/`** (gitignored): exploratory or question-specific
  HTML. Default landing zone for `feature-blueprint` doc-class artifacts
  generated on demand.
  - `YYYY-MM-DD-<slug>.html` — matches the existing vault date-prefix convention.

- Other roles (e.g. procedure-visual near its markdown procedure) — author's
  discretion; keep the file where a reader will naturally look for it.

### 3. Fill the `<meta>` block

Every conformant artifact carries these `<meta>` tags near the top of `<head>`
(the templates provide them with `==TODO==` placeholders):

```html
<meta name="gator-schema" content="gator-blueprint-html-v1">
<meta name="gator-title" content="How the pre-commit hook validates a commit">
<meta name="gator-repo" content="gator">
<meta name="gator-doc-class" content="feature-blueprint">
<meta name="gator-status" content="generated">
<meta name="gator-updated-at" content="2026-09-02T14:00:00Z">
<meta name="gator-generated-by" content="claude-opus-4-7">
<meta name="gator-question" content="How does the pre-commit hook validate a commit end-to-end?">
```

- `gator-doc-class` — one of `charter-map`, `feature-blueprint`,
  `procedure-visual`, `reference-explainer`. Must match the template you chose.
- `gator-status` — one of `current`, `historical`, `exploratory`, `generated`.
  `charter-map` and `procedure-visual` typically ship `current`; on-demand
  vault artifacts typically ship `generated`.
- `gator-updated-at` — ISO-8601 UTC, seconds precision, `Z` suffix.
- `gator-question` — the load-bearing "why does this artifact exist?" field.
  Never generic ("architecture overview"); always specific to what the artifact
  actually answers.

The full requirements are enumerated above (schema tag, doc classes, statuses,
required fields, ISO-8601 format). This procedure is the authoritative reference
in your repo; the contract's canonical form lives in the Gator source tree
(`contracts/schemas/gator-blueprint-html-v1.md`) and is not shipped to fleet
repos.

### 4. Fill the content

**Interactive template** (`_template.html`):

- Populate `NODES` array in the inline `<script>` with the domain data —
  node id, title, kind (subtitle), color (`var(--bp-<letter>)` or hex),
  `x`/`y` in the 1180×880 stage coordinate space, summary, covers (file paths),
  functions (representative function names).
- Populate `EDGES` array — `from` node id, `to` node id, optional `label`.
- Fill the narrative sections: what this shows, why these regions matter,
  reading order, boundaries + tripwires, open questions.

**Narrative template** (`_template-narrative.html`):

- Fill the sequential sections: question, executive summary, flow (steps for
  procedure-visual, sequential exposition for reference-explainer), why-it-matters,
  references, open questions.
- Use the `<div class="callout">` blocks for cautions and warnings. Delete
  unused callout blocks.
- The `.diagram` slot is optional — use for static ASCII/SVG diagrams, or
  delete the block.

### 5. Save + announce

Save to the location chosen in step 2. Announce the path to the Architect
so they can open it in the Dashboard's file browser (per-repo file list,
click → opens in new tab).

## Checkpoints

Before you consider the artifact done:

- **Metadata complete.** No `==TODO==` markers remain in the `<meta>` block.
- **Question specific.** `gator-question` is a real, specific question, not
  a generic label.
- **Self-contained.** No `<script src="...">` or `<link rel="stylesheet" href="...">`
  pulling from a CDN. All CSS + JS inlined.
- **Renders in a plain browser.** Open the file directly (`file://...`) —
  it should render correctly with no console errors.
- **Compat-ready** if it lives under `.gator/blueprints/`. The Gator source
  repo's compat suite runs `test_blueprint_html_schema.py` against every
  `.gator/blueprints/*.html` (scaffolding templates excluded). Your fleet
  repo won't carry that test, but the checkpoints above cover the same
  contract — meta block complete, question specific, self-contained.

## Notes

- **The compat test only walks `.gator/blueprints/*.html`.** Vault artifacts
  are exploratory-by-design and NOT schema-gated. This is deliberate —
  vault sketches may be intentionally non-conformant. Manual review handles
  vault conformance if needed.
- **Feature-blueprint generation** — for the on-demand "how does X work?"
  case, there's a separate procedure (Release B, `generating-a-feature-blueprint.md`)
  that documents the AI's charter-first walk. That procedure produces
  artifacts using this same authoring flow.
- **Charter maps are authored, not generated.** There is no "generate a
  charter map for me" procedure — charter maps are repo-wide and change on
  architecture shifts. Hand-author (or one-off AI assist) using
  `_template.html`.
- **The Gator source repo's own `charter-map.html`** at `.gator/blueprints/charter-map.html`
  is the reference implementation. It only lives in the Gator source repo
  (not shipped to fleet repos) — same "no wrong data at per-repo seam"
  invariant as v2.11.0's D3 refinement. Fleet repos author their own.
- **Do NOT create new `.md` blueprints under `.gator/blueprints/`.** The 9
  existing legacy markdown blueprints stay (D2 coexist), but new blueprint
  content is HTML.

## Connections

- [`../blueprints/_template.html`](../blueprints/_template.html) — interactive template
- [`../blueprints/_template-narrative.html`](../blueprints/_template-narrative.html) — narrative template
- [`../blueprints/README.md`](../blueprints/README.md) — blueprint directory README with the triage summary
- [`./artifact-freshness.md`](./artifact-freshness.md) — the source of the status label vocabulary
- **Protocol** `gator-blueprint-html-v1` — the shape you're conforming to; the
  full requirements are enumerated in the "Fill the `<meta>` block" section
  above. Canonical contract lives in the Gator source tree
  (`contracts/schemas/gator-blueprint-html-v1.md`) and is not shipped here.
