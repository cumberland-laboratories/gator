# Enforcer Configuration Guide

This reference note helps a primary agent configure an enforcer for the Architect. When the Architect asks "how do I set up an enforcer?" or hits step 5 for the first time, use this to figure out what they have available and walk them through it.

## The Conversation to Have

Ask the Architect three things:

1. **What's your primary agent?** (Claude, GPT/Codex, Gemini, etc.)
2. **What API keys or CLI tools do you have?** (Anthropic, OpenAI, Google, or none)
3. **How much do you care about cost?** (Determines model choice)

Then match to a config below.

## Decision Tree

```
Do you have any API key or CLI tool?
├─ No → Mechanical lint only (Layer 1). Free, instant, no setup.
│       Consider ollama for free local charter-grounded review.
│
├─ Yes → Is it the same vendor as your primary agent?
│   ├─ Yes → It works, but cross-vendor is stronger.
│   │         Same-vendor review is still better than nothing.
│   └─ No → Ideal. Different training = different blind spots.
│
└─ Multiple → Pick the one that's different from your primary agent.
```

## Configs by Enforcer

### Sonnet (Anthropic)

**Best for**: Primary agent is GPT, Gemini, or any non-Anthropic model. Also fine as same-vendor enforcer when primary is Claude Opus — Sonnet is a different model with different trade-offs.

**What the Architect needs**: `ANTHROPIC_API_KEY` from [console.anthropic.com](https://console.anthropic.com)

**Cost**: Low. Sonnet is one of the cheapest capable models.

**Config** (`enforcer-config.json`) — this is the default, no changes needed:
```json
{
  "layer2_3": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "api_key_env": "ANTHROPIC_API_KEY"
  }
}
```

**Setup steps**:
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...          # macOS/Linux
# $env:ANTHROPIC_API_KEY = "sk-ant-..."      # Windows PowerShell
```

**Run**: `python .gator/scripts/enforcer-review.py`

**If the primary agent is Codex**: this is the cleanest way to use Anthropic as enforcer. The Python script applies the enforcer role directly and avoids any ambiguity from Claude CLI also seeing the repo's `CLAUDE.md`.

### GPT (OpenAI) via Python script

**Best for**: Primary agent is Claude or Gemini.

**What the Architect needs**: `OPENAI_API_KEY` from [platform.openai.com](https://platform.openai.com)

**Cost**: `gpt-4o-mini` is very cheap. `gpt-4o` is moderate.

**Config**:
```json
{
  "layer2_3": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```

**Setup steps**:
```bash
pip install openai
export OPENAI_API_KEY=sk-...
```

**Run**: `python .gator/scripts/enforcer-review.py`

### Codex CLI (OpenAI)

**Best for**: Primary agent is Claude or Gemini. Architect wants to run the enforcer independently (no intermediary).

**What the Architect needs**: Codex CLI installed, OpenAI account

**Cost**: Depends on model (configured in `~/.codex/config.toml`)

**No config file changes needed** — but give Codex the dedicated enforcer prompt explicitly, because `AGENTS.md` is the primary-agent entrypoint.

**Setup steps**:
```bash
npm install -g @openai/codex
codex login
```

**Run (primary agent)**: `python .gator/scripts/enforcer-review.py` with `provider: openai` configured. The primary agent always routes enforcement through the review script — it never invokes a CLI enforcer directly. That is not because the script hides findings (it prints to stdout too, and the agent reads them to summarize for the Architect), but because routing through it produces the durable `whiteboard.md` record and keeps enforcement structured. Independent CLI review is the Architect's to run in a separate terminal.

**Run (Architect, independent)**: `codex review "Read .gator/scripts/enforcer-prompt.md for full instructions. Review the uncommitted changes against the charters."`

**Note**: Codex review runs in a read-only sandbox by default. The Architect runs this in a separate terminal for fully independent review (no primary agent involved). The agent may suggest it, but must not run the CLI itself.

### Gemini (Google)

**Best for**: Primary agent is Claude or GPT.

**What the Architect needs**: `GOOGLE_API_KEY` from [aistudio.google.com](https://aistudio.google.com)

**Cost**: `gemini-2.0-flash` is very cheap. `gemini-2.5-pro` is moderate.

**Config**:
```json
{
  "layer2_3": {
    "provider": "google",
    "model": "gemini-2.0-flash",
    "api_key_env": "GOOGLE_API_KEY"
  }
}
```

**Setup steps**:
```bash
pip install google-generativeai
export GOOGLE_API_KEY=...
```

**Run**: `python .gator/scripts/enforcer-review.py`

### Claude Code CLI (Anthropic)

**Best for**: Architect wants a separate Claude terminal/session as the reviewer, rather than using the Python API path.

**What the Architect needs**: Claude Code installed, Anthropic access configured

**Run (Architect, independent)**: the Architect runs this in a separate terminal — it is not a primary-agent path.
```bash
claude --print "$(cat .gator/scripts/enforcer-prompt.md)"
```

**Trade-off**: workable, but less clean than the Python Anthropic path when `CLAUDE.md` in the same repo defines Claude as the primary agent. The explicit enforcer prompt should steer the session correctly, but the role boundary is cleaner through `enforcer-review.py`. The primary agent's own enforcement path is always `enforcer-review.py`, never a direct `claude --print`.

### Local model via ollama (free, offline)

**Best for**: No API keys, cost-sensitive, privacy-sensitive, or offline use.

**What the Architect needs**: [ollama](https://ollama.com) installed

**Cost**: Free. Runs locally.

**Config**:
```json
{
  "layer2_3": {
    "provider": "ollama",
    "model": "llama3"
  }
}
```

**Setup steps**:
```bash
# Install ollama from https://ollama.com
ollama pull llama3
```

**Run**: `python .gator/scripts/enforcer-review.py`

**Trade-off**: Free and private, but slower and less capable than cloud models. Good enough for catching obvious charter violations. Won't match Sonnet/GPT on nuanced boundary analysis.

### Mechanical lint only (no model)

**Best for**: Zero setup, no API keys, no local model. Quick hygiene check.

**What the Architect needs**: Python 3. That's it.

**No config changes needed.**

**Run**: `python .gator/scripts/enforcer-review.py --layer 1`

**Limitation**: Only catches secrets, SQL dangers, injection risks, TODO markers. Does **not** read charters, check TRIPWIREs, or verify boundary compliance. This is hygiene, not architectural review.

## How the Config File Works

The enforcer config lives at `.gator/scripts/enforcer-config.json`. The primary agent edits this file when configuring the enforcer for the Architect.

```json
{
  "layer1": {
    "enabled": true
  },
  "layer2_3": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "api_key_env": "ANTHROPIC_API_KEY"
  }
}
```

- `layer1.enabled` — mechanical lint. Leave this `true`. No reason to disable it.
- `layer2_3.provider` — which API to call: `anthropic`, `openai`, `google`, `ollama`, or `none`
- `layer2_3.model` — the specific model identifier
- `layer2_3.api_key_env` — the environment variable name holding the API key (not the key itself — never put secrets in this file)

Setting `provider` to `"none"` disables charter-grounded review entirely. Layer 1 still runs.

## Cross-Vendor Principle

The enforcer should ideally be a **different vendor** than the primary agent. Different training data, different RLHF, different blind spots. This isn't dogma — same-vendor is still better than nothing — but cross-vendor review is where the real value of independent verification comes from.

| Primary agent | Recommended enforcer |
|---------------|---------------------|
| Claude (Opus) | Sonnet (same vendor, different model), GPT, or Gemini |
| GPT / Codex | Sonnet via `enforcer-review.py`, GPT/Codex via CLI, or Gemini |
| Gemini | Sonnet or GPT |

## What the Agent Should Do

When an Architect asks to set up an enforcer:

1. Ask the three questions above (primary agent, available keys/tools, cost sensitivity)
2. Pick the matching config from this guide
3. Edit `enforcer-config.json` with the right provider/model
4. Help the Architect set the environment variable (show the exact export command)
5. Run a test review to confirm it works
6. Show the Architect where `whiteboard.md` is so they can verify findings independently
