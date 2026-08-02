# Enforcer Patterns

The enforcer is one of Gator's most powerful capabilities — and its most flexible. This guide covers what the enforcer is, why it exists, and how to deploy it in your workflow.

---

## What the Enforcer Is

The enforcer is a code reviewer that runs on a **different AI model** than the one writing the code. It reads the same governance layer — constitution, charters, threads — and produces findings for the Architect (the human in the loop) to review.

The enforcer is:

- **A pattern, not a product feature.** Gator provides the shared language (charters, constitution, structured metadata). You choose how to wire the review.
- **Read-only.** The enforcer never edits code, modifies charters, or changes the knowledge layer. It produces reports.
- **Optional.** The governance layer (constitution + charters + pre-commit hooks) works without an enforcer. The enforcer adds a cross-model review wall on top.

The enforcer is NOT:

- A linter or static analysis tool (it uses LLM reasoning, not pattern matching)
- A replacement for human review (findings go to the Architect, not back to the coding agent)
- Required for Gator to function (but strongly recommended for any production codebase)

## Why Different Models

Same-model review is not enforcement. When the same model reviews its own output — even in a separate session — it shares the same training, the same blind spots, and the same tendencies. It's proofreading, not auditing.

Cross-model review means:
- Different training data, different biases, different failure modes
- The reviewer cannot share the coder's motivated reasoning about a shortcut
- Findings surface things the coding model genuinely cannot see about its own output

This is the same principle behind separating the author and reviewer in human code review — except with AI models, the "different perspective" is architecturally guaranteed by using a different model entirely.

## The High-Supervision Philosophy

The enforcer exists because Cumberland Laboratories is betting on a specific vision of AI-assisted development: **the tightly wound Architect/AI relationship wins long-term.**

Two failure modes dominate AI coding today:

1. **Vibe coding** — the Architect rubber-stamps AI output without understanding it. The code ships, but nobody can explain why it works. When it breaks, there's no mental model to debug from.
2. **Hands-free autonomy** — the AI codes unaccounted for across multiple steps, and the Architect reviews only the final result (if at all). Speed goes up. Accountability disappears.

Gator's position: **high supervision is not a tax on productivity — it is the product.** The Architect who understands every commit, who has independent signal from a separate model, who makes deliberate decisions with full context — that Architect ships faster over any meaningful time horizon than one who delegates understanding to the machine.

The enforcer is the mechanism that keeps independent signal flowing to the Architect. It exists so the Architect can trust but verify, with verification coming from a source the primary agent cannot influence.

## The Non-Negotiable

Every enforcer deployment pattern must satisfy one invariant:

> **The primary coding agent has zero control over the enforcer — its invocation, its output, or the interpretation of that output before the Architect reads it.**

If the coding agent can suppress a finding, edit a report, or reframe the enforcer's conclusions before the Architect sees them, you don't have an enforcer. You have a suggestion box.

This invariant is the lens through which every pattern below should be evaluated. When you design your own enforcer workflow — or evaluate a new one someone proposes — ask: *can the primary agent influence what the Architect sees from the enforcer?* If yes, it's broken.

---

## Deployment Patterns

Patterns are ordered by trust separation strength. Choose based on your workflow, team size, and how much infrastructure you want to maintain.

### Pattern 1: Manual Tab Switching

**Setup:** Two terminal sessions open side by side. One runs the coding agent. The other runs the enforcer model.

**How it works:**
1. Code in tab 1 (e.g., Claude Code with Opus)
2. Switch to tab 2 (e.g., Codex CLI, or Claude Code with a different model)
3. Point the enforcer at the repo: "Review the recent changes against the charters"
4. Read the findings directly. Decide what to act on.
5. Switch back to tab 1 and direct the coding agent based on what you learned.

**Trust separation:** Maximum. The Architect is the only bridge between the two models. The coding agent never sees the enforcer's raw output — only the Architect's interpreted instructions.

**Strengths:**
- Zero infrastructure. Works today with any two AI coding tools.
- The Architect reads every finding firsthand — no filtering, no summarization.
- Most flexible — the Architect controls timing, scope, and depth of review.
- Charters make the review fast and grounded. Both models read the same structured maps, so the enforcer doesn't need to reverse-engineer the architecture.

**Trade-offs:**
- Requires active Architect involvement (this is a feature, not a bug, per the high-supervision philosophy)
- No automation — the Architect must remember to switch tabs and run the review

**Best for:** Solo developers, small teams, anyone who wants maximum control over the review process. This is the recommended starting pattern.

### Pattern 2: Dedicated Review Session

**Setup:** The enforcer opens the repo in its own session, runs the audit procedure, and writes a report file.

**How it works:**
1. Code normally in your primary session
2. At a natural breakpoint, open a separate session with the enforcer model
3. The enforcer follows the repo constitution and the enforcer review procedure: reads the constitution, charters, threads, and recent changes
4. Output goes to `docs/reports/YYYY-MM-DD-enforcer-audit.md`
5. The Architect reads the report at their own pace

**Trust separation:** Strong. The report is a file the primary agent doesn't author. The Architect reads it directly.

**Caution:** If you later ask the primary agent to "look at the enforcer report and fix what it found," the agent is now interpreting the enforcer's findings. This is acceptable only if the Architect has already read the report and is directing specific fixes — not delegating triage to the coding agent.

**Best for:** Deeper reviews at milestones (end of sprint, before merge to main, before release).

### Pattern 3: Pre-Commit Hook Integration

**Setup:** The enforcer runs as part of the git pre-commit hook sequence, after Gator's deterministic checks pass.

**How it works:**
1. Developer commits as normal
2. Gator's deterministic pre-commit hook runs first (charter-alongside-code, trailer assembly, whiteboard findings)
3. If the deterministic checks pass, an optional enforcer step fires: a different model reviews the staged changes against the charters
4. Enforcer findings are written to a file (e.g., `.gator/enforcer-review.md`) that the primary agent does not control
5. The commit proceeds — the enforcer review is advisory, not blocking (unless the Architect configures it to block)

**Trust separation:** Strong, with caveats. The hook is a separate process — the primary agent cannot suppress it. But the Architect must ensure the findings file is read directly, not filtered through the coding agent.

**Important considerations:**
- **Token cost.** Every commit triggers an LLM call. This can be expensive on active repos. Consider limiting to significant commits (e.g., only when `Gator-Significance: high` in trailers).
- **Latency.** Enforcer review adds time to every commit. For interactive development, this friction may be unacceptable. Consider making it async (write findings, don't block the commit).
- **Configuration.** This must be opt-in. The Architect chooses whether to enable it, what scope to review, and whether findings block the commit or are advisory.

**Best for:** Teams that want automated review without a CI/CD pipeline. Solo devs who want a safety net they can't forget to use.

### Pattern 4: PR / Merge Request Hook

**Setup:** The enforcer is triggered by a pull request event (GitHub Actions, GitLab CI, or similar).

**How it works:**
1. Developer pushes a branch and opens a PR
2. CI triggers the enforcer model against the PR diff
3. Enforcer reads charters, reviews changes, posts findings as PR comments or a review
4. The Architect reads findings in the PR interface before merging

**Trust separation:** Strong. The enforcer runs in CI — the primary agent has no access to the CI environment and cannot edit PR comments posted by the enforcer.

**Important considerations:**
- **Infrastructure required.** Needs CI/CD pipeline, API keys for the enforcer model, and configuration for the review scope.
- **Cost and duration.** Enforcer reviews can be lengthy and token-intensive. Budget accordingly. Set timeouts.
- **PR comment volume.** A thorough enforcer review on a large PR can produce substantial findings. Consider structured output (summary + details) rather than inline comments on every file.
- **This is the highest-infrastructure pattern.** Don't start here. Get comfortable with manual tab switching first, then automate once you understand what a good enforcer review looks like for your codebase.

**Best for:** Teams with existing CI/CD, repos where every merge to main must have cross-model review, compliance-driven environments.

### Pattern 5: Scheduled Audit

**Setup:** The enforcer runs on a schedule (daily, weekly) via cron, CI, or a scheduled task.

**How it works:**
1. A scheduled job opens the repo with the enforcer model
2. The enforcer runs a full audit: charter compliance, drift detection, knowledge layer health, session archaeology review
3. Report written to `docs/reports/` or sent to a notification channel
4. The Architect reviews on their own schedule

**Trust separation:** Same as dedicated review session — the report is authored independently.

**Best for:** Fleet-wide governance. A command post operator running weekly audits across 10+ repos to catch drift before it compounds.

---

## Model Pairing Guide

The only hard rule: **the enforcer must be a different model than the coding agent.**

### Known-Good Pairings

| Coding Agent | Enforcer | Notes |
|-------------|----------|-------|
| Claude Opus | OpenAI Codex | Strong complementary strengths. Codex is concise and direct in reviews. Charter-grounded reviews are fast. |
| Claude Opus | Claude Sonnet | Different model, lower cost. Sonnet follows charter structure well. Viable for teams without Codex access. |

### Untested but Plausible

| Coding Agent | Enforcer | Considerations |
|-------------|----------|----------------|
| Claude Opus | Gemini | Can Gemini read and reason about charter notation? Needs hands-on testing. |
| Claude Opus | Mistral | Untested on Gator governance layer. Charter comprehension unknown. |
| Claude Sonnet | Claude Opus | Opus reviewing Sonnet's code — viable, but higher cost for the review than the coding. |

### Evaluating a New Enforcer Model

Before trusting a model as an enforcer, verify that it can:

1. **Read charters.** Give it a charter file. Ask it to explain the access patterns and tripwires. If it can't parse the notation, it can't enforce against it.
2. **Follow the audit procedure.** Point it at the enforcer audit procedure and a real repo. Does it produce structured, actionable findings? Or vague suggestions?
3. **Stay read-only.** Does it attempt to fix what it finds, or does it report to the Architect? An enforcer that edits is not an enforcer.
4. **Disagree with the coder.** Give it code that a different model wrote with a subtle issue. Does it find it? Or does it defer? An enforcer that always says "looks good" is not adding signal.

---

## What the Architect Does With Findings

Enforcer findings are for the Architect. They are never auto-applied.

The decision loop:

1. **Read the findings directly.** Not a summary from the coding agent. The actual enforcer output.
2. **Assess each finding.** Is it valid? Is it actionable now? Is it a real risk or a style preference?
3. **Direct the coding agent.** "Fix the SQL injection the enforcer found in `views_auth.py`." Or: "The enforcer flagged the error handling in `parser.py` — I reviewed it and it's fine, ignore that one."
4. **Dismiss deliberately.** If a finding isn't actionable, that's a legitimate decision. But make it consciously, not by forgetting to read the report.

The Architect's judgment is the final authority. The enforcer provides signal. The Architect decides what to do with it. This is the high-supervision model: the human is never removed from the decision loop.

---

## Choosing Your Pattern

Start simple. You can always add infrastructure later.

```
Solo dev, getting started?
  → Pattern 1 (manual tab switching)

Solo dev, want a safety net?
  → Pattern 1 + Pattern 3 (pre-commit hook, advisory mode)

Team, pre-merge review required?
  → Pattern 4 (PR hook)

Fleet operator, governance at scale?
  → Pattern 5 (scheduled audit)

Any of the above + milestone reviews?
  → Add Pattern 2 (dedicated review session) at release boundaries
```

The patterns compose. Most mature setups will use two or three together: manual tab switching for interactive development, PR hooks for merge gates, and scheduled audits for fleet-wide health.

---

## Opting Out

The enforcer is optional. If you're:

- Learning Gator on a personal project
- Working on a prototype that won't ship
- The only developer and comfortable with your own review process

...you can skip the enforcer entirely. The governance layer (constitution, charters, pre-commit hooks) provides substantial value on its own. The enforcer adds the cross-model review wall — powerful, but not required for every repo.

When you're ready, start with Pattern 1. Open a second terminal. Run a different model. Point it at the charters. See what it finds. That's it — you're running an enforcer.
