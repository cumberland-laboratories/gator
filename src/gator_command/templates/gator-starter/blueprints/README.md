# Blueprints

Architect-facing inspection artifacts that explain how features, subsystems,
or workflows work end-to-end. Blueprints are optional — create one when a
region of the system benefits from a dedicated, browsable explanation.

## HTML is the medium for new blueprints (as of v2.12.0)

New blueprint content is authored in HTML under the
[`gator-blueprint-html-v1`](../../../../contracts/schemas/gator-blueprint-html-v1.md)
protocol. Two shipped templates cover the two lanes:

| Template | Doc classes | Use when |
|---|---|---|
| [`_template.html`](_template.html) | `charter-map`, `feature-blueprint` | Content has a natural node-and-edge structure that benefits from interactive click-to-isolate exploration (a graph of chartered regions, a feature flow across modules) |
| [`_template-narrative.html`](_template-narrative.html) | `procedure-visual`, `reference-explainer` | Content is prose-heavy or step-sequenced without a natural graph (a release workflow, a concept explainer, an architecture overview that reads as narrative) |

**Triage rule** — before authoring, ask: "does this content have a natural
node-and-edge structure that benefits from click-to-isolate?" If yes → use
the interactive template. If no → use the narrative template. Never force
non-graph content into the interactive shell.

The full authoring procedure is at
[`../procedures/authoring-html-artifacts.md`](../procedures/authoring-html-artifacts.md).

The contract for the metadata block, doc classes, status values, and layout
invariants is at
[`../../../../contracts/schemas/gator-blueprint-html-v1.md`](../../../../contracts/schemas/gator-blueprint-html-v1.md).

## Where blueprints live

- **`.gator/blueprints/`** (tracked): durable repo-wide artifacts.
  `charter-map.html` is the canonical inhabitant if this repo has one. Other
  long-lived blueprints or reference explainers may live here.
- **`.gator/vault/artifacts/`** (gitignored): exploratory or question-specific
  HTML — the default landing zone for `feature-blueprint` doc-class artifacts
  generated on demand.

Storage follows the artifact's role, not its rendering format. A durable
`procedure-visual` explaining the release path can live here even though it
isn't strictly a "blueprint" in the interactive sense.

## Discovery

Open blueprints in the Gator Dashboard's per-repo file browser — any `.html`
file listed there opens in a new tab. There is no dedicated Blueprints
sidebar item (the v2.11.0 experiment was retired in v2.12.0 in favor of the
file-browser approach).

## Legacy markdown blueprints

Blueprints authored before v2.12.0 as `.md` files stay put — no bulk
conversion. If those documents grow enough to benefit from an interactive
map or a richer narrative shell, they can be re-authored in HTML using one
of the two templates above.

For reference, the legacy markdown structure was:

```markdown
# Blueprint: <Feature Name>

## What It Does
[1-2 sentences]

## Flow
1. **<Module>** → `function_name()` — what happens
   → [charter-name](../charters/charter-name.md)

## Key Charters
[Charters involved]

## Invariants
[What must be true for this to work]
```

The [`_template.md`](_template.md) scaffold survives as reference for that
legacy shape. New blueprints should use one of the HTML templates instead.

## See also

- [Charter README](../charters/README.md) — charter notation used in function references
- [Authoring procedure](../procedures/authoring-html-artifacts.md) — when + how to choose HTML over markdown, the two-lane triage, storage rules, status labeling
- [Protocol contract](../../../../contracts/schemas/gator-blueprint-html-v1.md) — required metadata, layout invariants, doc classes, status values
