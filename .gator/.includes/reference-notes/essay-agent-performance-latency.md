---
last-touched: 2026-03-17
category: essay
hits: 3
tags: [performance, latency, api, llm, tooling, forensics, memex-infrastructure, essay]
---

> *Memex architecture essay — preserved from this reference instance's earlier development as the Memex about the Memex. Not a working thread for the active project; historical thinking about the architecture itself.*

# Agent Performance & Latency

## Summary

Conversational turns with a Memex-using agent average 20+ seconds and can exceed a minute. The latency is a compound of network, API queuing, prompt size, tool-call round trips, and output generation — but there are currently no forensics to attribute delay to cause. The question is whether this is compressible, and if so, where the leverage is.

## Detail

**The latency stack (what contributes, roughly ordered by likely impact):**

1. **Prompt size / time-to-first-token (TTFT).** The biggest lever the Memex controls. Every input token must be processed before the first output token. The constitution mandates always-loading identity + active threads + patterns — currently budgeted at 400 lines. At session open, this plus the constitution, procedures, and system prompt could be 3,000–5,000+ tokens of input before the user's message is even considered. Larger prompts = longer TTFT. This is the one factor the Memex architecture directly influences.

2. **Tool-call round trips.** Each tool use (file read, glob, grep, bash) is a separate API call or at minimum a separate generation cycle. A session-open procedure that reads 5–8 files is 5–8 round trips. Each round trip pays the full TTFT cost again with an even larger prompt (prior turns accumulated). The Memex's read-heavy orientation multiplies this.

3. **Output token generation.** Roughly linear with response length. A detailed thread write-up generates more tokens than a short answer. Models generate ~30–80 tokens/second depending on model and load; a 500-token response is 6–16 seconds of generation alone.

4. **API queuing / server load.** Invisible to the client. Anthropic's API has variable queue times depending on demand, rate tier, and model. No way to measure from the outside except by observing variance between identical-length requests.

5. **Network latency.** Usually small (50–200ms per round trip) but compounds with tool calls. 8 tool calls × 150ms = 1.2 seconds of pure network overhead.

6. **Client-side overhead.** Claude Code itself: parsing responses, rendering, managing context. Likely negligible compared to API time but unmeasured.

**What's known from public research / documentation:**

- Anthropic publishes rate limits and some latency benchmarks but not detailed TTFT-vs-prompt-size curves for production API.
- The general relationship is established: TTFT scales with input token count. The exact curve depends on model architecture, KV cache behavior, and infrastructure.
- **Prompt caching is confirmed active in Claude Code by default.** System prompt, tool definitions, and earlier conversation turns are cached with a 5-minute TTL. Cache hits process at 10% of normal input token cost (and correspondingly reduced latency). Up to 4 cache breakpoints are set automatically. Cache requires exact prefix match — any system prompt change between turns invalidates it.
- This means the always-loaded Memex context (constitution, identity, active threads, patterns) is primarily a **first-turn cost**. Subsequent turns within normal conversational cadence (~5 min between turns) hit the cache and skip reprocessing the prefix.
- Streaming reduces *perceived* latency (first tokens appear faster) but doesn't change total time.
- There's limited public research specifically on "agent loop latency" — the compound effect of multi-step tool use. Most LLM latency research focuses on single-call inference, not agentic workflows with 5–15 sequential calls per turn.

**What forensics would look like:**

- Per-turn breakdown: TTFT, generation time, tool-call count, total round trips, input token count, output token count
- Trend over session: does latency increase as context accumulates?
- Comparison: same question with and without Memex context loaded
- Attribution: what fraction of a 45-second turn was waiting for API vs. generating vs. tool calls?

Claude Code may already have some of this data internally (it shows token counts). The question is whether it's surfaced or loggable.

**Revised assessment (with caching confirmed):**

The always-loaded context is not the bottleneck it appeared to be. After the first turn, the Memex's 400-line budget is cached and nearly free. The remaining latency on turns 2+ is dominated by:

1. **Tool-call round trips** — the primary suspect. Each file read/write is a full API cycle. A session-open that reads 6 files is 6 sequential round trips, each paying its own TTFT on the growing context.
2. **Output generation** — proportional to response length, unavoidable.
3. **API queuing** — still invisible, still unmeasurable.

This reframes the optimization question: the lever isn't "load less context" — it's "make fewer tool calls per turn." Parallel tool calls (when independent) and reducing unnecessary reads would have more impact than shrinking the always-loaded set.

A 15-second research response remains reasonable for substantive work. The gap that matters is between "physics of the stack" and "unnecessary round trips we could eliminate."

**Subagent delegation pattern (future architecture):**

An LLM generates text or tool calls in a single response, then pauses for tool results. It cannot stream text to the user while simultaneously waiting for tool results. This is a fundamental constraint of inference — not a design choice.

However, Claude Code supports background agents (subagents that run independently while the primary conversation continues). This opens a delegation pattern:

- *Primary agent* responds immediately from what's already in context — acknowledges, gives a partial answer, or frames the question.
- *Background subagent* runs the tool-heavy work (file reads, research, Memex housekeeping) in a separate context.
- Primary follows up when the subagent returns.

**Where this saves real time (not just perceived):**

1. **Parallelism across independent work.** If the primary needs to answer the user *and* do Memex housekeeping (update hits, triage inbox, compress a thread), those can run concurrently instead of sequentially. Total session time drops.
2. **Context hygiene.** Tool-call results accumulate in the conversation context. 8 file reads in the primary conversation means 8 tool results inflating every subsequent turn's prompt. If a subagent does those reads in its own context, the primary stays lean — smaller prompt, faster TTFT on subsequent turns, even with caching (the non-cached delta is smaller).
3. **Pipeline overlap.** Human thinking time (reading a response, composing a reply) is currently dead time for the system. Background agents fill it with useful work — a real session-throughput gain.

**What doesn't change:** The tool calls themselves still take the same time. Per-turn latency for tool-heavy work is unchanged. The wins are in session throughput, context size management, and perceived responsiveness.

**Assessment:** Not critical for the prototype (current Memex). Significant architectural consideration for a production version — especially the context hygiene point, which compounds over long sessions.

## Connections

→ [knowledge-systems-comparison.md](essay-knowledge-systems-comparison.md) — the always-loaded budget and compression rules directly affect prompt size, the biggest controllable latency factor
→ [constitution.md](../../constitution.md) — defines the 400-line compression budget and session-opening file loads
→ [tooling-roadmap.md](../reference-notes/tooling-roadmap.md) — Crawler/Spider as background operators would shift work out of interactive sessions

## Open Questions

- ~~Does Claude Code use prompt caching?~~ **Resolved: yes, on by default, 5-min TTL.**
- Can Claude Code emit per-turn latency diagnostics (TTFT, generation time, tool-call count)?
- What's the actual token count of a fully loaded session-open prompt? Is the 400-line budget well-calibrated to latency, or was it set for readability?
- Would lazy-loading active threads (load on first reference, not at session open) meaningfully reduce TTFT for early turns?
- Is there a measurable latency difference between Opus and Sonnet for the same Memex workload? (Relevant to enforcer model choice.)
- How much context bloat do tool-call results add over a typical 30-turn session? Is subagent delegation worth the complexity just for context hygiene?
- Could session-open be restructured as: greet immediately → background agent loads Memex state → follow-up with informed orientation?
