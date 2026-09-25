# Authoring HTML Artifacts

## When to use

Reach for this procedure when you're about to create — or being asked to
create — an HTML artifact. Two entry points:

**The Architect explicitly asks for HTML.** "I want an HTML that says…",
"make me an HTML report on…", "write this up as HTML." Every governed
model defaults to the same Cumberland master template — see the
constitution's "HTML Documents" section for the routing rule.

**The content is a Blueprint.** Feature flow map, charter map, procedure
visual, or reference explainer conforming to the `gator-blueprint-html-v1`
protocol. Concrete Blueprint triggers:

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
visual structure materially improves comprehension OR when the Architect
explicitly asks.

**Since v2.12.0**: new Blueprint content is authored in HTML. Existing
markdown Blueprints in `.gator/blueprints/` stay put; no bulk conversion.
New Blueprints never go into `.md`.

**Since Codex Sketch 2 (2026-09-12)**: non-Blueprint HTML documents share
the same Cumberland visual grammar via the master template at
`../reference-notes/cumberland-html-document-template.html`. The master's
`<style>` block encloses its full CSS between
`CUMBERLAND-NARRATIVE-STYLE:BEGIN/END` delimiters; the narrative Blueprint
template will link that region byte-for-byte in Slice 3 so the visual
grammar is guaranteed identical across both surfaces.

## Steps

### 1. Pick the template (medium-first triage)

Two questions in order:

**A. Is this a Blueprint?**

A Blueprint is a durable artifact whose content maps naturally to one of
four doc classes AND is worth conforming to the `gator-blueprint-html-v1`
protocol (required `<meta>` tags, schema-check-ready, lives under
`.gator/blueprints/`):

- `charter-map` — repo-wide graph of chartered regions (one per repo)
- `feature-blueprint` — per-feature flow map (many per repo)
- `procedure-visual` — visualized workflow
- `reference-explainer` — architecture overview, capability landscape

**If NO** — the piece is a general HTML document (a report, an explainer,
a design writeup, a status page). → Use the Cumberland master at
[`../reference-notes/cumberland-html-document-template.html`](../reference-notes/cumberland-html-document-template.html).
Skip Step 3 (no Blueprint metadata required). Proceed to Step 2 for storage,
Step 4 for content.

**If YES** — continue to sub-question B.

**B. (Blueprint only) Does the content have a natural node-and-edge
structure that benefits from interactive click-to-isolate exploration?**

- **Yes** — a graph of chartered regions, a feature flow across modules, a
  system-interaction map. → Use
  [`_template.html`](../blueprints/_template.html) (interactive Blueprint,
  map + sidebar + narrative shape). Doc classes: `charter-map`,
  `feature-blueprint`.

- **No** — prose-heavy, step-sequenced, or otherwise not naturally
  graph-shaped. A release workflow, a concept explainer, an architecture
  overview that reads as narrative. → Use
  [`_template-narrative.html`](../blueprints/_template-narrative.html)
  (narrative Blueprint, header + sequential sections, no interactive map).
  Doc classes: `procedure-visual`, `reference-explainer`.

Do NOT force non-graph content into the interactive template. The
interactive click-to-isolate affordance only earns its keep when there's a
real neighborhood to isolate.

**Style vs role vs protocol** — the three are independent concerns.
**Style** = Cumberland visual grammar, shared by all three templates.
**Role** = destination path (Blueprint → `blueprints/`, general HTML →
role-appropriate path per Step 2). **Protocol** = `gator-blueprint-html-v1`
metadata, required for Blueprints only.

### 2. Copy the template to the target location

Storage follows the artifact's role, not its rendering format:

- **`.gator/blueprints/`** (tracked): durable repo-wide Blueprint artifacts.
  - `charter-map.html` — exact filename, one per repo.
  - `<slug>.html` — other durable Blueprints.

- **`.gator/artifacts/`** (tracked): deep records, design docs, research
  writeups. Default for non-Blueprint HTML documents that deserve
  durability.
  - `YYYY-MM-DD-<slug>.html` — matches the existing artifact date-prefix
    convention.

- **`.gator/procedures/`** (tracked): repeatable workflows. Non-Blueprint
  HTML procedures live alongside their markdown peers.
  - `<slug>.html` — non-date-prefixed; procedures name themselves after
    the workflow.

- **`.gator/reference-notes/`** (tracked): reference-explainers and
  cognitive aids. Non-Blueprint HTML reference material lives here.
  - `<slug>.html`.

- **`.gator/threads/`** (tracked): lightweight topic notes (rare in HTML).
  - `<slug>.html`.

- **`.gator/vault/artifacts/`** (gitignored): exploratory or
  question-specific HTML that hasn't earned a durable path yet. Default
  landing zone for on-demand `feature-blueprint` Blueprints AND for
  drafts/sketches of any kind.
  - `YYYY-MM-DD-<slug>.html` — matches the existing vault date-prefix
    convention.

### 3. Fill the `<meta>` block (Blueprints only)

**Skip this step if you're using the Cumberland master.** The master
template intentionally omits the `gator-schema` block — non-Blueprint
HTML documents do not conform to `gator-blueprint-html-v1`. Fill only
the visible `.meta-grid` cells in the header (doc class, audience,
status, updated date, reading time, author).

**Every Blueprint** carries these `<meta>` tags near the top of `<head>`
(both Blueprint templates provide them with `==TODO==` placeholders):

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

### 4. Write in ASD-STE100-style Simplified Technical English

Apply this standard to all reader-facing prose in the document: headings,
summary callouts, body text, table labels, captions, and warnings. The goal is
clear technical communication, not a shorter document at the cost of omitted
constraints.

- Use direct, concise sentences. Give one instruction or one main idea in each
  sentence.
- Use active voice and direct verbs. Write commands as commands when the
  reader must act.
- Use one consistent term for one concept. Do not rotate through synonyms for
  style.
- Prefer lists or tables for conditions, options, comparisons, and sequences.
- Define a necessary technical term once. Do not replace it later with vague
  references such as “this,” “that,” or “it” when the referent is unclear.
- Remove scene-setting, rhetorical transitions, and repeated conclusions.
- Keep every constraint, risk, exception, and decision that the reader needs.
  Simplification must not reduce technical precision.

This is an ASD-STE100-style authoring requirement. Do not claim that a document
is formally ASD-STE100 compliant unless it has been checked against the
official writing rules and controlled dictionary.

### 5. Fill the content

**Cumberland master** (`cumberland-html-document-template.html`):

- Fill the header (title, subtitle, meta-grid cells, optional metaline).
- Fill the TOC (delete if fewer than four sections).
- Fill the Summary callout — one or two paragraphs that answer the doc's
  question. If the reader stops there, what do they leave knowing?
- Fill the body sections. The template ships one visible example of every
  component (`.figure`, `.diagram`, `.steps`, colored tables, `.pill`
  chips, all six callout variants). Keep the components that serve the
  piece; delete the rest.
- Use `<div class="callout data">` (purple) SPARINGLY — one or two per
  document is the intended cadence for the highest-signal insight moments.

**Interactive Blueprint template** (`_template.html`):

- Populate `NODES` array in the inline `<script>` with the domain data —
  node id, title, kind (subtitle), color (`var(--bp-<letter>)` or hex),
  `x`/`y` in the 1180×880 stage coordinate space, summary, covers (file paths),
  functions (representative function names).
- Populate `EDGES` array — `from` node id, `to` node id, optional `label`.
- Fill the narrative sections: what this shows, why these regions matter,
  reading order, boundaries + tripwires, open questions.

**Narrative Blueprint template** (`_template-narrative.html`):

- Fill the sequential sections: question, executive summary, flow (steps for
  procedure-visual, sequential exposition for reference-explainer), why-it-matters,
  references, open questions.
- Use the `<div class="callout">` blocks for cautions and warnings. Delete
  unused callout blocks.
- The `.diagram` slot is optional — use for static ASCII/SVG diagrams, or
  delete the block.

### 6. Save + announce

Save to the location chosen in step 2. Announce the path to the Architect
so they can open it in the Dashboard's file browser (per-repo file list,
click → opens in new tab).

## Checkpoints

Before you consider the artifact done:

- **Simplified Technical English pass complete.** Reader-facing prose follows
  Step 4. Do not label the document formally ASD-STE100 compliant without an
  official rules-and-dictionary check.
- **All `==TODO==` markers removed.** Applies to every template.
- **Self-contained.** No `<script src="...">` or `<link rel="stylesheet" href="...">`
  pulling from a CDN. All CSS + JS inlined. Applies to every template.
- **Renders in a plain browser.** Open the file directly (`file://...`) —
  it should render correctly with no console errors. Applies to every
  template.

Additionally, for **Blueprints only**:

- **Metadata complete.** No `==TODO==` markers remain in the `<meta>` block.
- **Question specific.** `gator-question` is a real, specific question, not
  a generic label.
- **Compat-ready** if it lives under `.gator/blueprints/`. The Gator source
  repo's compat suite runs `test_blueprint_html_schema.py` against every
  `.gator/blueprints/*.html` (scaffolding templates excluded). Your fleet
  repo won't carry that test, but the checkpoints above cover the same
  contract — meta block complete, question specific, self-contained.

Cumberland-master documents don't need the `<meta>`/`gator-question`/compat
checkpoints — those apply only to files under `.gator/blueprints/`.

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

- [`../reference-notes/cumberland-html-document-template.html`](../reference-notes/cumberland-html-document-template.html) — Cumberland master (default for non-Blueprint HTML)
- [`../blueprints/_template.html`](../blueprints/_template.html) — interactive Blueprint template
- [`../blueprints/_template-narrative.html`](../blueprints/_template-narrative.html) — narrative Blueprint template
- [`../blueprints/README.md`](../blueprints/README.md) — Blueprint directory README with the triage summary
- [`./artifact-freshness.md`](./artifact-freshness.md) — the source of the status label vocabulary
- **Constitution `## HTML Documents`** — the always-read routing rule that
  points here from every session.
- **Protocol** `gator-blueprint-html-v1` — the shape Blueprints conform to;
  the full requirements are enumerated in the "Fill the `<meta>` block"
  section above. Canonical contract lives in the Gator source tree
  (`contracts/schemas/gator-blueprint-html-v1.md`) and is not shipped here.
