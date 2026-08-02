# Procedure: Significance Check

**When to use**: After making a code change and updating charters, before committing. The agent runs this check on itself — it does not require Architect prompting.

## Why This Exists

Most changes are routine. Some changes have implications the Architect needs to hear about before committing — not because the code is wrong, but because the change is architecturally significant in ways that aren't obvious from the diff alone.

The agent is in the best position to notice this. It just read the charters, made the change, and updated the charters. It knows what TRIPWIREs exist, what boundaries were crossed, and what the blast radius looks like. The significance check asks the agent to pause and surface what it knows before the Architect commits.

Without this step, the Architect only hears about implications when they think to ask — and on the most dangerous changes, they often won't think to ask because the change looks locally correct.

## When to Trigger

Run a significance check when the change touches any of these:

| Trigger | Why |
|---------|-----|
| **Public API** (exported functions, public classes, documented interfaces) | Consumers depend on the current behavior. Changes may require semver-major, migration paths, or deprecation. |
| **Cross-module invariants** | Patterns that span modules can break in places far from the edit. |
| **TRIPWIRE patterns** | These exist specifically because they're non-obvious. Any change near a TRIPWIRE is significant by definition. |
| **"Does Not Own" boundary crossings** | If the change puts logic where the charter says it shouldn't be, that's a boundary decision, not just an edit. |
| **Data model or schema changes** | Downstream consumers, migrations, and serialization are all affected. |
| **Security-relevant code** (auth, encryption, access control, input validation) | Security changes have outsized blast radius and often need review even when they look small. |

For routine changes (typos, documentation, local refactors within a single module's boundary), skip the significance check.

## What to Do

### 1. Generate the steelman argument

Ask yourself: **"Why might this change be a bad idea?"**

Produce 3-5 concrete counter-arguments. These should be the arguments a skeptical senior maintainer would make — not implementation doubts, but architectural and ecosystem-level concerns:

- What existing behavior changes silently?
- Who depends on the current behavior and doesn't know it's changing?
- What migration path exists (or doesn't)?
- What secondary effects does this change trigger that weren't the stated goal?
- Is there a way to achieve the same goal with less blast radius?

### 2. Flag semver and compatibility implications

For any change to public API:

- Is this backward-compatible? (semver-patch/minor)
- Does this change behavior for existing consumers? (semver-major)
- Does this change the signature, return type, or default behavior of a public function?
- Are there public enum values, constants, or type definitions that changed?
- Would existing user code that worked yesterday produce different results today?

### 3. Surface to the Architect

Present the steelman and compatibility assessment to the Architect before committing. Frame it as:

"This change works — the tests pass and the charters are updated. But before we commit, here's what a skeptical reviewer would say: [steelman]. And here are the compatibility implications: [assessment]. How do you want to proceed?"

The Architect decides:
- **Proceed**: the arguments are noted, the change stands
- **Adjust**: modify the change to reduce blast radius (add opt-in flag, deprecation warning, migration path)
- **Revert**: the steelman convinced the Architect the change shouldn't land
- **Defer**: capture the change as a thread or inbox item for later, with the steelman attached

## What the Agent Should NOT Do

- Don't skip the significance check because the tests pass. Passing tests don't prove architectural correctness.
- Don't suppress the steelman because you believe the change is right. The Architect needs to hear the counter-arguments.
- Don't present the steelman defensively ("here are some minor concerns..."). Present it as the strongest case against the change.
- Don't run the significance check on every trivial edit. Use the trigger table above.
