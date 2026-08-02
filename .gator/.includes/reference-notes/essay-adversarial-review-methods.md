---
last-touched: 2026-03-18
category: essay
hits: 1
tags: [adversarial-review, turing-test, prompt-caching, methodology, multi-model, context-contamination, essay]
---

> *Memex architecture essay — preserved from this reference instance's earlier development as the Memex about the Memex. Not a working thread for the active project; historical thinking about the architecture itself.*

# Adversarial Review & Assessment Methods

## Summary

How to get honest assessments from LLMs — covering hostile review methodology, Turing test design, and the prompt caching contamination problem. The core challenge: models that have prior context on a subject produce degraded reviews because cached context mixes with fresh analysis. Clean-context enforcement is as important for reviews as clean-model enforcement is for audits.

## Detail

**Prompt caching contamination (observed 2026-03-18):**

ChatGPT's hostile reviews of the Memex degraded across successive attempts. The first review was sharp and specific. Later reviews became a "mish-mash of context" — mixing what ChatGPT read in the repo with what it remembered from prior conversation turns about the repo. The review was no longer purely adversarial; it was partly informed by its own prior conclusions.

Same failure mode observed with Gemini on a Turing test (2026-03-17) — once stuck in a frame, cached context reinforced the frame instead of allowing a reset. The model couldn't get unstuck.

**Why this matters for the Memex:**

The constitution requires the enforcer to be a different model. But the deeper principle is that the enforcer must have *clean context* — no prior relationship with the content. Model independence is necessary but not sufficient; context independence is the actual requirement. A Codex instance that reviewed the Memex ten times would start exhibiting the same contamination as ChatGPT did within a single session.

**Implications for review methodology:**

- **Hostile reviews need fresh sessions.** Don't iterate hostile reviews in the same conversation. Each attempt should be a new session with no prior context on the subject.
- **Turing tests need context isolation.** If the model has seen the test subject before (via caching or conversation history), the test is compromised.
- **The enforcer's value degrades with familiarity.** Rotate enforcer sessions, not just enforcer models. A fresh Codex session is more valuable than a tenth review from the same Codex session.
- **Prompt caching is invisible.** The operator can't tell from the output whether the model is reasoning from the repo or from cached prior context. The contamination is silent.

**Open design question — adversarial review protocol:**

What does a rigorous hostile review look like? Candidate protocol:
1. Fresh model session (no prior context on the subject)
2. Provide only the public artifact (repo URL, document, etc.) — no briefing
3. Request the most hostile credible interpretation
4. Capture verbatim before any follow-up
5. Only then ask for a second pass or specific drill-downs

The first pass is the most valuable because it's the cleanest. Every subsequent turn in the same session degrades the adversarial quality.

## Connections

→ [memex-enhancements.md](essay-memex-enhancements.md) — adversarial review findings drove the enhancement priorities
→ [knowledge-systems-comparison.md](essay-knowledge-systems-comparison.md) — multi-model architecture depends on clean enforcer context
→ [2026-03-18-chatgpt-hostile-review.md](../artifacts/2026-03-18-chatgpt-hostile-review.md) — first (cleanest) hostile review
→ [2026-03-18-chatgpt-hostile-review-2.md](../artifacts/2026-03-18-chatgpt-hostile-review-2.md) — second review showing degradation from context contamination

## Open Questions

- Can you detect prompt caching contamination from the output alone, or is it only visible by comparing successive reviews?
- Is there a way to force a truly fresh context in ChatGPT/Gemini without creating a new account?
- Should the Memex constitution specify a maximum number of enforcer reviews per session before requiring a fresh context?
- How do Turing test results change when the model has vs. hasn't seen the subject before?
- What's the relationship between prompt caching TTL and review quality degradation?
