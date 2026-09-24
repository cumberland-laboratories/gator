# Loop Artifact Formats

This document defines the expected format for artifacts produced during a gator loop: the sketch (Architect), the plan (draftor), the findings (reviewer), and optional decision-request and decision-response documents exchanged via `escalate --file` and `unblock --file`. These are the reference templates — models should follow this structure when producing their submissions.

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

## Executive Summary

<Four bullets or ~120 words: what this plan proposes, the key design
decision, the main risk, and the verification approach. This section
is extracted by the Dashboard for at-a-glance inspection — keep it
bounded and self-contained.>

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

## Assumptions, Risks, and Required Architect Decisions

<Classify each uncertainty:

- **Non-blocking** (assumption): State it as an explicit, reversible
  assumption. Example: "Assuming v2 API — will revert if Architect
  directs otherwise." The Architect can interject to correct; no pause.

- **Blocking** (Architect-owned decision): Requires the Architect's
  explicit answer before the plan can proceed. Use
  `gator loop escalate --file <request.md> --reason "..."` to pause
  the loop and attach a structured decision request.

Known risks, edge cases, or constraints that don't fit either
category belong here as general notes.>

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

## Executive Summary

<Four bullets or ~120 words: the verdict, the most important finding,
what looks strong, and whether the plan is ready. Extracted by the
Dashboard for at-a-glance inspection — keep it bounded and
self-contained.>

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
- An ESCALATE verdict MUST be accompanied by `gator loop escalate`. Submitting findings with verdict ESCALATE via `submit-review` (without `--approve`) enters revision, not blocked state. The ESCALATE path is: write your findings document with verdict ESCALATE, then run `gator loop escalate --file <findings.md> --reason "..."` instead of `submit-review`.
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

## Decision Request (written by either model, attached via `escalate --file`)

A decision request is a structured document attached to an escalation when the model needs an Architect-owned decision before continuing. It is copied into the loop directory as `decision-request.decision-{N}.round-{R}.md` and recorded in the `decisions[]` ledger.

```markdown
# Decision Request: <short title>

## Decision Needed

<1-3 sentences: what specific question or authorization the Architect must answer>

## Context

<Relevant constraints, prior decisions, or sketch requirements that frame this decision.
Include enough background that the Architect can decide without re-reading the full plan.>

## Options Considered

1. <Option A> — <tradeoffs>
2. <Option B> — <tradeoffs>

## Recommendation

<Your recommendation, or "No recommendation — this is genuinely the Architect's call."
If you have a preference, say so and explain why.>

## Consequence of Delay

<What happens if the Architect doesn't respond soon — e.g., "the loop will remain
blocked" or "the plan proceeds with Assumption X, which may need reversal.">
```

Submit with:
```
gator loop escalate --token <token> --file request.md --reason "Need decision on ..."
```

---

## Decision Response (optional, written by the Architect, attached via `unblock --file`)

A decision response is an optional structured document the Architect attaches when unblocking. It is copied into the loop directory as `decision-response.decision-{N}.md` and recorded in the decision ledger entry's `response.artifact_path`. Text-only responses via `unblock --message` remain valid — this template is for decisions that benefit from durable documentation.

```markdown
# Decision Response: <decision-N>

## Decision

<The Architect's answer — clear, actionable, unambiguous.>

## Rationale

<Why this decision was made — constraints, preferences, or external factors.
Helps the model understand the reasoning, not just the conclusion.>

## Next Action

<What the model should do with this answer — e.g., "revise the plan to use API v2"
or "proceed with your recommendation.">
```

Submit with:
```
gator loop unblock --token <token> --file response.md --message "Summary of decision"
```

---

## Connections

-> [Loop Protocol](../procedures/gator-loop-protocol.md) — behavioral rules for loop participation
