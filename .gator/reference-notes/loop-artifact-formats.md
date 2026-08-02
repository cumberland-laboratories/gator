# Loop Artifact Formats

This document defines the expected format for the three artifacts produced during a gator loop: the sketch (Architect), the plan (draftor), and the findings (reviewer). These are the reference templates — models should follow this structure when producing their submissions.

See [gator-loop-protocol.md](../procedures/gator-loop-protocol.md) for the behavioral rules governing how and when to submit these artifacts.

---

## Sketch (written by the Architect)

The sketch is the scope contract. It defines what the loop is about. The draftor expands it into a plan; the reviewer checks the plan against it. Neither model should exceed what the sketch describes.

```markdown
# Feature: <feature name>

## Goal

<1-3 sentences: what this feature does and why it matters>

## Scope

<What is IN scope — specific behaviors, files, modules, or capabilities to deliver>

## Out of Scope

<What is deliberately excluded — prevents scope creep by the draftor>

## Constraints

<Technical or design constraints the plan must respect — existing patterns,
performance requirements, compatibility boundaries, security rules>

## Context

<Optional: pointers to relevant charters, blueprints, or prior artifacts
that the models should read before drafting/reviewing>
```

**Guidelines for the Architect:**
- Be specific about scope boundaries. "Build X" is weaker than "Build X. Do not build Y."
- Constraints are load-bearing — if the draftor ignores one, the reviewer should flag it
- Context pointers save rounds. If there's a charter the models need, link it here.

---

## Plan (written by the draftor)

The plan is the draftor's proposed implementation. It should be specific enough that an engineer (human or AI) could implement it without further design decisions.

```markdown
# Implementation Plan: <feature name>

## Summary

<2-4 sentences: what this plan proposes, grounded in the sketch>

## Approach

<How the feature will be implemented — architecture, module structure,
key design decisions. Reference the sketch's constraints explicitly.>

## Changes

<Ordered list of concrete changes — files to create/modify, functions to
add, modules to touch. Each entry should be specific enough to act on.>

### 1. <change description>
- File: `path/to/file.py`
- What: <what changes in this file>
- Why: <why this change is needed>

### 2. <change description>
...

## Dependencies and Ordering

<Which changes depend on others. What can be parallelized.
What must happen first.>

## Risks and Open Questions

<Known risks, edge cases, or decisions that need Architect input.
If something is unclear in the sketch, flag it here — or escalate.>

## Testing

<How the changes will be verified — what tests to write,
what to check manually, what existing tests might break.>

## Charter Impact

<Which charters will need updating after implementation.
New modules that need new charters.>
```

**Guidelines for the draftor:**
- Address every point in the sketch's Scope section
- Respect every constraint — if you can't, say why and escalate
- Be concrete. "Refactor the module" is not a plan. "Split `render()` into `render_html()` and `render_markdown()` in `dashboard/helpers.py`" is a plan.
- If the reviewer sent findings on a previous round, address every finding explicitly — don't silently drop any

---

## Findings (written by the reviewer)

Findings are the reviewer's assessment. They should be specific, numbered, and actionable. The draftor must address each one by number.

```markdown
# Review: <feature name>

## Verdict

<One of: APPROVE, REVISE, ESCALATE>
<1-2 sentences: overall assessment>

## Findings

### Finding 1: <short title>
**Severity**: High | Medium | Low
**Location**: <which section or change in the plan>
**Issue**: <what is wrong, missing, or risky>
**Suggestion**: <what the draftor should do about it>

### Finding 2: <short title>
...

## Scope Check

<Does the plan stay within the sketch's scope?
Does it miss anything the sketch requires?
Does it add anything the sketch excludes?>

## What Looks Good

<Optional but valuable: what the reviewer thinks is strong
in the plan. Helps the draftor know what to preserve in revision.>
```

**Guidelines for the reviewer:**
- Number every finding — the draftor must reference them by number in revision
- Be specific about location. "The plan is unclear" is not useful. "Change #3 doesn't specify the error handling path for invalid HTML" is useful.
- Severity matters — High means "this will break something or violate a constraint," Medium means "this should be better," Low means "consider this"
- An APPROVE verdict means "this plan is ready to implement as written." Only approve if you mean it.
- Don't invent requirements that aren't in the sketch. Review against the sketch, not your own preferences.

---

## When Approving

When the reviewer approves, the findings file should still exist as a real document — not a stub. Use the same format with `Verdict: APPROVE` and optionally note what looks good or any minor observations that don't require revision.

```markdown
# Review: <feature name>

## Verdict

APPROVE — the plan is ready to implement as written.

## What Looks Good

- Clear separation of the rendering and sanitization steps
- Testing plan covers both happy path and malformed input
- Charter impact section is complete

## Minor Observations (non-blocking)

- Consider adding a performance note about large HTML files (not a finding, just a thought for implementation)
```

Submit with `--approve`:
```
gator loop submit-review --token <token> --file review.md --approve
```

---

## Connections

-> [Loop Protocol](../procedures/gator-loop-protocol.md) — behavioral rules for loop participation
-> [Loop Blueprint](../blueprints/gator-loop.md) — end-to-end usage guide for the Architect
-> [Draft-Review-Edit-Draft](../procedures/draft-review-edit-draft.md) — the underlying revision philosophy
