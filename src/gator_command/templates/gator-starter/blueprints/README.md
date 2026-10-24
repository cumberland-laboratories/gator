# Blueprints

The collection of visual Gator docs that explain how this system works —
architecture overviews, feature walkthroughs, and flow maps — for an
Architect who may be far from the code. Blueprints are optional; create one
when a part of the system benefits from a dedicated, visual explanation.

Blueprints are visual first: one labeled diagram per major part, large
readable type, the code paths and charter for each part, and no meaning
carried by color alone. See "Blueprints are visual first" in the
[authoring procedure](../procedures/authoring-html-artifacts.md).

## HTML is the medium for new blueprints (as of v2.12.0)

New blueprint content is authored in HTML under the `gator-blueprint-html-v1`
protocol. The full requirements are enumerated in the
[authoring procedure](../procedures/authoring-html-artifacts.md); the
canonical contract lives in the Gator source tree and is not shipped to
fleet repos. Two shipped templates cover the two lanes:

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
The metadata block, doc classes, status values, and layout invariants are
enumerated there; the canonical `gator-blueprint-html-v1` contract lives in
the Gator source tree (`contracts/schemas/gator-blueprint-html-v1.md`) and
is not shipped to fleet repos.

## Where blueprints live

- **`.gator/blueprints/`** (tracked): durable blueprints — the visual Gator
  docs for this repo. `charter-map.html` is the canonical inhabitant if this
  repo has one.
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

Do not create new `.md` blueprints. When an older Markdown blueprint is
retired, move it to `.gator/vault/blueprints/` (gitignored) and re-author
the content it still needs in HTML with one of the templates above.

## See also

- [Charter README](../charters/README.md) — charter notation used in function references
- [Authoring procedure](../procedures/authoring-html-artifacts.md) — when + how to choose HTML over markdown, the two-lane triage, storage rules, status labeling; also enumerates the protocol requirements (metadata, layout invariants, doc classes, status values)
