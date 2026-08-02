# Coding Standard

**Scope**: All code in repos governed by Gator Command.

**The invariant**: ownership, side effects, tripwires, and negative space must be locally legible — an agent or human reading a function should understand what it touches and what it must not break without tracing the call graph.

**Language adaptation**: The principles below are universal. The syntax examples use Python and JavaScript but the concepts apply to any language. Repos may adapt comment syntax, naming conventions, and file structure to match their language's community idioms (Go exports, Rust modules, SQL migration files, etc.) as long as the invariant holds.

## Why This Standard Exists

Code in governed repos is read by AI agents as much as by humans — often more. An agent that reads a function needs to know what it does, what it touches, and what it must not break, *without* reading the entire file or tracing the call graph. These standards optimize for that reality while keeping the code clean for human readers too.

## Modularity

**Small functions with single responsibilities.** A function should do one thing. If describing what it does requires "and," it's two functions.

- **Target**: functions under 40 lines, files under 300 lines. Not a hard rule — but when you exceed it, ask whether the function is doing two things or the file is holding two concerns.
- **Flat over nested**: prefer early returns, guard clauses, and decomposition over deep nesting. Three levels of indentation is a smell; four is a refactor signal.
- **Module boundaries map to charter boundaries.** If a module gets its own charter, its public API should be obvious from the file structure. If you can't tell where one module ends and another begins, the boundaries aren't real.

## Inline Comments for AI Readability

Comments are not just for junior developers. They are **context injection points** for agents reading the code. An agent arriving at a function for the first time has no call-stack memory, no IDE hover, no "I was here yesterday." Comments bridge that gap.

### What to comment

- **Intent**: *why* this code exists, not *what* it does (the code shows *what*). `# Retry because the upstream API returns 503 under cold-start` not `# retry loop`.
- **Boundaries**: where a module's responsibility starts and stops. `# --- Public API ---` and `# --- Internal helpers ---` section markers in larger files.
- **Non-obvious constraints**: `# Must run before DB migration — depends on old schema`, `# Order matters: auth check must precede data fetch`.
- **Tripwires**: things that will break if changed carelessly. `# WARNING: changing this enum breaks the wire protocol — coordinate with client team`, `# This timeout must exceed the upstream SLA (currently 30s)`.
- **Does Not Own**: what this module explicitly delegates. `# Validation is the caller's responsibility — this function trusts its input`.

### What not to comment

- Obvious code: `x = x + 1  # increment x` — this wastes tokens.
- Changelog entries: that's git's job.
- TODOs without context: `# TODO: fix this` is noise. `# TODO(alan): handle timezone edge case — see issue #42` is useful.

## Function and Class Tags

Tags are structured metadata in docstrings or comments that agents can parse without reading the implementation. They make functions discoverable and charterable.

### Tag vocabulary

Code-level tags cover **local facts** — what this function reads, writes, guards, and delegates. Cross-module graph data (who calls whom, caller/callee maps) lives in **charters**, not in code comments. Duplicating graph data in source creates two maps that disagree on the first refactor.

| Tag | What it captures | Example |
|---|---|---|
| `@reads` | External state this function consumes | `@reads: orders table, payment_gateway config` |
| `@writes` | External state this function modifies | `@writes: transactions table, audit_log` |
| `@tripwire` | Constraint that will break if changed carelessly | `@tripwire: amount validation must happen before this call` |
| `@does-not-own` | What this function explicitly delegates | `@does-not-own: order validation, inventory adjustment` |

```python
def process_payment(order_id: str, amount: Decimal) -> Receipt:
    """Process a payment for the given order.

    @reads: orders table, payment_gateway config
    @writes: transactions table, audit_log
    @tripwire: amount validation must happen before this call
    @does-not-own: order validation, inventory adjustment
    """
```

```javascript
/**
 * Render the hazard overlay on the golf course map.
 *
 * @reads courseData, playerKit
 * @writes canvas context
 * @tripwire z-order must match HAZARD_LAYERS constant
 */
function renderHazards(courseData, playerKit, ctx) {
```

### When to tag

- **Public API functions**: always. These are charter boundaries.
- **Functions that touch external state**: databases, APIs, file system, caches. Tag `@reads` and `@writes`.
- **Functions with constraints**: `@tripwire` when there's a non-obvious way to break it, `@does-not-own` when the delegation boundary matters.
- **Internal helpers**: only when they have constraints worth documenting.

### When not to tag

- Trivial utilities (`def add(a, b): return a + b`).
- Private helpers where the constraint is obvious from the parent function's tags.
- Test functions (the test name is the documentation).
- **Caller/callee relationships** — these belong in charters, not code comments. They change too frequently and create maintenance churn when duplicated in source.

## File Structure

```
# file-level docstring: what this module is, what it owns, what it delegates

# --- Imports ---

# --- Constants / Configuration ---

# --- Public API ---
# (the functions other modules call)

# --- Internal Helpers ---
# (implementation details, not called from outside)

# --- Entry Point (if applicable) ---
```

This structure lets an agent read the first 20 lines and know what the file does without scrolling. The section markers (`# ---`) are cheap and enormously useful for navigation.

## Naming

- **Descriptive over short.** `calculate_hazard_damage` not `calc_dmg`. Tokens are cheap; ambiguity is expensive.
- **Verbs for functions, nouns for data.** `get_player_kit()`, `validate_course()`, `player_scores`, `hazard_registry`.
- **Boolean variables read as assertions.** `is_valid`, `has_permission`, `should_retry` — not `valid`, `perm`, `retry`.
- **Constants are SCREAMING_SNAKE.** `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT_MS`.

## Error Handling

- **Fail fast, fail loud.** Validate inputs at boundaries (API handlers, public functions). Don't pass bad data deep into the stack hoping something will catch it.
- **Errors carry context.** `raise ValueError(f"Invalid course_id: {course_id}")` not `raise ValueError("bad input")`. The error message should let the agent (or human) diagnose without a debugger.
- **Don't catch-and-swallow.** `except: pass` is prohibited. If you catch, log or re-raise with context.

## Testing

- **Test names describe the scenario, not the function.** `test_payment_fails_when_amount_exceeds_balance` not `test_process_payment_3`.
- **One behavior per test.** Each test should verify one scenario or contract. Multiple assertions are fine when they describe different facets of the same behavior — an API contract test that checks status code, response body, and side effect is one test, not three.
- **Tests are documentation.** A new agent should be able to read the test file and understand the module's contract without reading the implementation.

## Charter Alignment

These coding standards exist to make **charters accurate and maintainable**:

- Modular code → clean charter boundaries (one module = one charter section)
- Inline comments → charter summaries can be extracted, not invented
- Function tags → `@reads`, `@writes`, `@tripwire`, `@does-not-own` map directly to charter fields; caller/callee graphs live in charters only
- Section markers → charter "Does Not Own" boundaries are visible in the code

If the code follows this standard, charter maintenance is a mechanical operation. If it doesn't, charters become creative writing — and creative writing drifts.

## Connections

→ [Branching Standard](branching-standard.md) — git workflow for governed repos
→ [Charter Philosophy](../reference-notes/charter-philosophy.md) — why charters exist and how they use function metadata
→ [Charter Lookup](charter-lookup.md) — procedure for consulting charters before code changes
