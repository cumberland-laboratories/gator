# Enforcer Configuration Guide

This reference note helps the primary agent configure an enforcer for the Architect. When the Architect asks "how do I set up an enforcer?" or wants independent review, use this to figure out what they have available.

## The Conversation to Have

Ask the Architect three things:

1. **What's your primary agent?** (Claude, GPT/Codex, Gemini, etc.)
2. **What API keys or CLI tools do you have?** (Anthropic, OpenAI, Google, or none)
3. **How much do you care about cost?** (Determines model choice)

Then match to a setup below.

## Decision Tree

```text
Do you have any API key or CLI tool?
├─ No -> Mechanical lint only (Layer 1 of enforcer-review.py). Free, instant, no setup.
│       Consider ollama for free local charter-grounded review.
│
├─ Yes -> Is it the same vendor as your primary agent?
│   ├─ Yes -> It works, but cross-vendor is stronger.
│   └─ No -> Ideal. Different training = different blind spots.
│
└─ Multiple -> Pick the one that's different from your primary.
```

## Setup Options

### Codex CLI (OpenAI) — Recommended for Claude users

```bash
npm install -g @openai/codex
codex login
codex review "Read .gator/scripts/enforcer-prompt.md for full instructions. Review the uncommitted changes against the charters."
```

`AGENTS.md` is the primary-agent entrypoint, so give Codex the dedicated enforcer prompt explicitly for review work. Review mode is read-only by default. The Architect can run this independently in a separate terminal.

### Claude Code — Recommended for GPT/Gemini users

```bash
# From a separate terminal
claude --print "$(cat src/gator_command/scripts/enforcer-prompt.md)"
```

### Gemini CLI

```bash
gemini < src/gator_command/scripts/enforcer-prompt.md
```

### Mechanical lint only (no model)

```bash
python .gator/scripts/enforcer-review.py --layer 1
```

Checks secrets, SQL dangers, injection risks, TODO markers. No model needed, instant, free. For fleet repos, use `.gator/scripts/enforcer-review.py`. For command-post knowledge layer audits, see the enforcer-audit procedure.

### Local model via ollama (free)

```bash
ollama pull llama3
# Then configure enforcer-config.json: provider "ollama", model "llama3"
```

## Cross-Vendor Principle

The enforcer should ideally be a **different vendor** than the primary agent. Different training, different RLHF, different blind spots. Same-vendor is still better than nothing.

| Primary agent | Recommended enforcer |
|---|---|
| Claude (Opus) | Codex, GPT, or Gemini |
| GPT / Codex | Claude (Sonnet) or Gemini |
| Gemini | Codex or Claude (Sonnet) |

## API Key Safety (CRITICAL for MAX Subscribers)

If the Architect has a Claude Code MAX subscription, **do not set `ANTHROPIC_API_KEY` globally in their shell profile.** Claude Code's auth precedence means a global API key hijacks interactive CLI sessions from MAX (subscription) to API (pay-per-token) billing.

**Safe pattern for automated enforcer:**

1. Store the API key in `~/.gator/enforcer-key` (outside repo, not in git)
2. Set `GATOR_ENFORCER_API_KEY` in `enforcer-config.json` as the `api_key_env`
3. The post-commit hook reads the key file and passes it scoped to the enforcer process only
4. Interactive Claude Code sessions remain on MAX subscription billing

**Verify with `/status`** in Claude Code to confirm which billing route is active.

→ [Enforcer Economics](../artifacts/2026-06-03-enforcer-economics-api-billing.md) — full billing boundary analysis

## What the Agent Should Do

When an Architect asks to set up an enforcer:

1. Ask the three questions above
2. Pick the matching setup
3. **Check if Architect has MAX subscription** — if yes, warn about API key precedence and use `GATOR_ENFORCER_API_KEY`, not `ANTHROPIC_API_KEY`
4. Help the Architect install and configure
5. Run a test review to confirm it works
6. Show the Architect where `whiteboard.md` is so they can verify findings independently
