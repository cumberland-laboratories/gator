# Refactor a Codebase with Gator

You have an existing codebase and you want to use AI to reorganize modules, extract shared logic, modernize patterns, or restructure architecture. Gator keeps that process legible and reversible.

---

## Kickoff

Tell the agent what you want to accomplish:

> "I want to refactor the auth module. Right now token management is tangled up with user session logic and it's hard to test either of them in isolation. I want to pull token management out into its own module."

The agent will ask clarifying questions before doing anything:

> "Got it. Before I build a plan, let me orient: where in this repo is the auth code you want to refactor? Are there tests for it today? Is there other code that imports from this module that I should be aware of?"

This is not boilerplate. The agent is mapping the blast radius before touching anything.

## Step 1: Feature Branch

**Tell the agent:**
> "Create a feature branch for this work before we do anything else."

The agent creates the branch and confirms. All refactoring work happens here — branch from `dev`, not from main.

**Or run directly:**
```bash
git checkout dev
git checkout -b refactor/auth-token-extraction
```

## Step 2: Charter the Scope

**Tell the agent:**
> "Read through the code in the refactoring scope — source files and any docs or tests that describe it. Build a charter that maps the current state: what each part does, what calls what, and anything non-obvious that would break if 'fixed'."

The agent reads code, tests, and inline documentation. It proposes a module map, flags tripwires, and asks targeted questions:

> "I see `validate_token()` is called from three places with different timeout assumptions. Is that intentional? If I extract this, the timeout behavior will need to be explicit. Should I preserve current behavior exactly, or is this a chance to normalize it?"

Review the draft charter. Correct it if the agent's reading is wrong. This is your checkpoint — the refactoring plan will be built on top of this understanding.

## Step 3: Plan

**Tell the agent:**
> "Based on the charter, write a refactoring plan. I want to see what's behavior-preserving extraction, what's architectural redesign, what carries migration risk, and where the rollback points are."

The agent produces a structured plan that distinguishes:

- **Behavior-preserving extraction** — moving code without changing semantics (low risk, safe to do in one step)
- **Architectural redesign** — changing how components relate (higher risk, should be staged)
- **Migration risk** — callers that will need to be updated, interfaces that will break
- **Rollback points** — where you can stop and have a working, committable state

**Have a second agent review the plan before execution.** Open a fresh Claude Code instance (or a different model) and ask:

> "Review this refactoring plan against the charter. Does the plan correctly account for all the tripwires? Is the staging logical? Are there risks the plan doesn't acknowledge?"

Same-model review misses things. The second agent's job is to find what the first one rationalized away.

## Step 4: Execute in Increments

**Tell the agent:**
> "Execute the first increment from the plan. Pause when you reach a rollback point, summarize what changed, surface any risks you found, and propose the next increment before continuing."

The agent works through one stage, then stops:

> "Done with increment 1: extracted `TokenStore` into `src/tokens.py`. All existing callers updated. Tests pass. I noticed the session timeout logic in `auth.py` line 142 is now redundant — it was compensating for behavior that `TokenStore` handles directly. I've left it in place to stay behavior-preserving, but flagged it in the charter as a candidate for cleanup. Ready for increment 2?"

The pre-commit hook enforces that charter updates travel with code changes — you cannot commit a code change without a corresponding charter update:

```
  gator pre-commit: BLOCKED

  ✗ charter-alongside-code: Code files changed
    (src/auth.py, src/tokens.py) but no charter was updated.
```

## Step 5: Review

**Tell the agent:**
> "Compare what we actually built against what I originally asked for. Did we accomplish the original intent? What's the governance trail look like?"

The review is against *original intent*, not just whether the governance checks passed.

**Or run directly:**
```bash
# Governance trail for this branch
git log dev..HEAD --format='%s%n  Change-Type: %(trailers:key=Gator-Change-Type,valueonly)  Significance: %(trailers:key=Gator-Significance,valueonly)'

# Full charter review
python .gator/scripts/enforcer-review.py --full
```

---

## Related

- [Getting Started](getting-started.md) — initial setup
- [Governance Model](governance-model.md) — how charters and enforcement work
- [Enforcer Patterns](enforcer-patterns.md) — cross-model review for quality gates
