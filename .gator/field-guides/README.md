# Field Guides

Condensed pattern references organized by language. Each guide has two sections: an **agent pattern sheet** (concise dispatch table for the agent) and an **Architect tutorial** (real code snippets with rationale for the human).

Field guides are the third layer: constitution ("how to behave"), charters ("what exists"), field guides ("how to work here").

## When to Generate

Field guides are optional. The system never flags their absence, never detects staleness, never prompts for regeneration. Generate one when:

- The Architect wants to restore sharpness on patterns used in this repo
- The agent keeps reinventing patterns that already have established idioms
- A language is covered by ≥2 charters with ≥4 source files

## How to Generate

Follow the procedure: → [field-guide-generation.md](../procedures/field-guide-generation.md)

## File Format

Two files per language:
- `{slug}-patterns.md` — agent pattern sheet (concise, under 80 lines, loaded by the agent)
- `{slug}-tutorial.md` — Architect tutorial (real snippets with rationale, read by the human)

YAML frontmatter tracks generation date, source charters, and cross-references between the pair. Regenerate manually when patterns drift — the `generated` date is the staleness signal.
