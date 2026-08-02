# Workflow Profiles

Different projects need different levels of governance. A solo weekend project doesn't need the same rigor as a team production codebase. This reference note describes workflow profiles from lightest to heaviest, so the primary agent can suggest the right one for the Architect's context.

## How to Use This

At bootstrap or when the Architect asks about process, suggest a profile that matches their situation. The Architect can change profiles at any time — or mix and match. These are suggestions, not rules.

---

## Profile 1: Light — Solo, Low-Risk

**Best for**: Personal projects, prototyping, learning, early exploration.

```
Architect gives instruction
  → Agent reads charters
    → Agent codes + updates charters
      → Significance check (if triggered)
        → Mechanical lint (Layer 1)
          → Commit
```

- Significance check runs automatically when a change touches public API, TRIPWIREs, cross-module invariants, or security-relevant code
- Mechanical lint runs before every commit (instant, free, catches secrets and SQL dangers)
- No charter-grounded model review by default
- Architect can still ask for a full enforcer review anytime
- Charters still update with every code change — the loop is non-negotiable

**What you give up**: Charter-grounded independent verification. The agent is judge of its own architectural work. Fine when the stakes are low and the Architect is reading the diffs. You still get deterministic safety checks.

**Strongly discouraged**: Skipping charter updates entirely. That's vibe coding — the map goes stale, comprehension decays, and the agent starts generating code from assumptions. Even at the lightest profile, the loop matters.

---

## Profile 2: Standard — Solo or Small Team, Moderate Risk

**Best for**: Most projects. Solo work on real codebases, small teams, projects that matter but aren't mission-critical.

```
Architect gives instruction
  → Agent reads charters, proposes plan
    → Architect reviews plan, adjusts
      → Agent codes + updates charters
        → Significance check (if triggered)
          → Mechanical lint (Layer 1, automatic)
            → Charter-grounded enforcer review
              → Architect reviews whiteboard, directs fixes
                → Commit
```

- Significance check runs automatically for architecturally significant changes (steelman + compatibility)
- Mechanical lint runs automatically before commit
- Post-code charter-grounded enforcer review before commit
- Architect sees findings via whiteboard.md and decides what to act on
- Plan discussion is conversational — agent proposes, Architect adjusts, no formal gate

**This is the default recommendation.** It catches mistakes without slowing the work significantly.

---

## Profile 3: Careful — Team, Production, or High-Stakes

**Best for**: Team repos, production codebases, public APIs, anything where a mistake is expensive.

```
Architect gives instruction
  → Agent reads charters, proposes plan
    → OPTIONAL: Pre-code enforcer review of the plan
      → Architect/agent discussion, revise plan
        → Agent codes + updates charters
          → Significance check (steelman + compatibility)
            → Post-code enforcer review
              → Architect reviews whiteboard, directs fixes
                → Commit
```

- **Pre-code review**: Before writing code, the enforcer reviews the plan against charters. "Does this plan violate any boundaries? Does it touch TRIPWIREs? Are there cross-cutting implications?" This catches architectural mistakes before they become code.
- **Significance check**: Agent generates steelman and flags compatibility implications for architecturally significant changes. Architect hears counter-arguments before committing.
- **Post-code review**: Standard review of the diff against charters.
- Architect is actively engaged at all checkpoints.

**Pre-code review** reviews a free-text *plan* before any diff exists — so it is **not** a job for `enforcer-review.py`, which reviews charters against an actual diff/code, not a text plan. Pre-code plan review is run by the **Architect** independently in a separate terminal — e.g. `codex review "Read all charters in .gator/charters/. Here is the proposed plan: [plan]. Does this plan violate any charter boundaries, TRIPWIREs, or cross-cutting patterns? Report concerns."` The primary agent never invokes a CLI enforcer directly; its trust-boundaried path — `python .gator/scripts/enforcer-review.py` — is for **post-code** review of an actual diff.

---

## Profile 4: Rigorous — Critical Systems, Compliance, High-Trust Requirements

**Best for**: Regulated industries, security-sensitive code, infrastructure, anything where auditability matters.

```
Architect gives instruction
  → Agent reads charters, proposes plan
    → Pre-code enforcer review of plan
      → Architect/agent discussion, revise plan
        → Agent codes + updates charters
          → Significance check (steelman + compatibility + semver)
            → Post-code enforcer review (full, cross-vendor)
              → Architect reviews whiteboard independently
                → Second enforcer (different model) if warranted
                  → Architect directs fixes
                    → Final lint before commit
                      → Commit
```

- Significance check with full steelman and semver assessment
- Multiple enforcer reviews — pre-code and post-code
- Cross-vendor review recommended (e.g., Claude primary, Codex enforcer, Gemini second opinion)
- Architect reads whiteboard independently (not relying on agent summary)
- Mechanical lint as a final gate before commit
- Commit draft entries include full attribution and decision tags

**This is rare.** Most projects don't need this. But when they do, the infrastructure supports it.

---

## Choosing a Profile

| Situation | Profile |
|-----------|---------|
| Weekend project, learning, prototyping | **Light** |
| Solo project that matters | **Standard** |
| Small team, shared repo | **Standard** or **Careful** |
| Production codebase, real users | **Careful** |
| Touching auth, payments, data migration | **Careful** (at minimum) |
| Regulated industry, compliance requirements | **Rigorous** |
| "I just want to move fast" | **Standard** — the loop is fast; skipping it is where slowdowns come from later |

The Architect can escalate or de-escalate at any time. "This change touches the payment module — let's go careful for this one" is perfectly valid even if the project normally runs at Standard.

## What Never Changes

Regardless of profile, these are constant:

- **The loop**: Read charters → change code → update charters immediately (before the next file). Every profile. Every time.
- **Charter updates are part of the edit, not the commit**: Update the charter right after editing the code file. If you wait until commit time, you will forget. The pre-commit hook catches this, but being caught is a failure — not a workflow.
- **Mechanical lint before commit**: Layer 1 runs by default across all profiles. It's instant, free, and catches things that should never be committed. The Architect can override this, but the default is always-on.
- **Architect authority**: The Architect decides the profile, the cadence, and what to act on.
- **Enforcer findings go to the Architect**: The agent presents and asks, never auto-fixes.
- **Knowledge lives in the repo**: Not in model memory. Across all profiles.

## Pre-Code Review: When and Why

Pre-code enforcer review is the biggest difference between profiles. It asks: "before I write this code, does the *plan* make sense given what the charters say?"

This catches:
- **Boundary violations before they happen**: "The plan puts validation logic in the store module, but the store charter says it doesn't own validation."
- **TRIPWIRE awareness**: "This plan changes the retry logic, but there's a TRIPWIRE about intentional failure signals."
- **Cross-cutting implications**: "This plan touches the auth flow, which has synchronized implementations in three modules."
- **Scope creep**: "This plan adds features the charter's 'Does Not Own' section explicitly excludes."

Pre-code review is cheap — it's reviewing a text plan, not a full diff. The enforcer reads the charters and the plan and flags concerns in 30 seconds. Fixing a plan is cheaper than fixing code.
