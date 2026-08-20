# Procedure: Enforcer Review

**Enforcer review is optional and Architect-driven.** The Architect decides when to run one, and at what level. Not every change needs a full charter-grounded review — routine edits might need nothing, or just a quick lint. Critical changes to invariants or cross-cutting patterns might warrant a full model review. The Architect picks the weight.

## Ad Hoc Invocation

The Architect can request a review at any point during a session. The primary agent translates intent to action:

| Architect says | Agent does |
|---------|-----------|
| "run a quick lint" / "check for secrets" | `gator hook enforcer-review --layer 1` |
| "get a review on this" / "run the enforcer" | `gator hook enforcer-review` |
| "have Sonnet check this" | Same script — default config uses Sonnet |
| "run Codex on this" / cross-vendor GPT review | Configure `enforcer-config.json` for `provider: openai`, then `gator hook enforcer-review`. (For the Codex CLI itself, the Architect runs it independently — see Trust Model.) |
| "just the mechanical checks" | `gator hook enforcer-review --layer 1` |
| "full review before we commit" | `gator hook enforcer-review` (all layers) |

**Important**: The primary agent routes **all** enforcement through `gator hook enforcer-review`, which writes findings to `whiteboard.md`, the authoritative Architect-visible record. The trust boundary here is **behavioral**: the agent reads those findings and presents them to the Architect, and does not act on them unprompted. The script also prints findings to stdout, so it is *not* a hard visibility barrier — the agent sees the findings either way. The primary agent must **never** run a CLI enforcer (Codex, Claude, Gemini) directly, because that bypasses the `whiteboard.md` record and the structured review path — not because the script hides anything. A CLI enforcer can still be used — but only when the Architect runs it independently in a separate terminal, which is the only path where the agent never sees the findings. See the Trust Model section below.

The agent should **not** run enforcer reviews unprompted. The Architect controls the cadence.

## Common Setups

Pick your enforcer. Follow the steps. Running in under 5 minutes.

### Sonnet as enforcer

The default config. Cheap, fast, charter-grounded. Works with any primary agent.

```bash
pip install anthropic
```

Set your API key (if not already set):
```bash
# macOS/Linux
export ANTHROPIC_API_KEY=sk-ant-...

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

Run the enforcer:
```bash
gator hook enforcer-review
```

That's it. Sonnet reads the charters, reviews the diff, writes findings to `whiteboard.md`. The primary agent presents findings and asks the Architect what to do.

**If the primary agent is Codex**: this is the cleanest Anthropic-based enforcer path. The Python script sends the enforcer prompt directly and does not depend on `CLAUDE.md` role interpretation.

**No API key?** Go to [console.anthropic.com](https://console.anthropic.com) to create one. Sonnet calls are cheap. Or fall back to mechanical lint (see below).

### GPT / Codex as enforcer

Best cross-vendor option when your primary agent is Claude.

**When the primary agent runs it** (findings go to `whiteboard.md`; the agent reads them and presents them to the Architect): configure `enforcer-config.json` for the OpenAI provider, then run the enforcer review script.
```json
{
  "layer2_3": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```
```bash
export OPENAI_API_KEY=sk-...
gator hook enforcer-review
```

**When the Architect runs the Codex CLI independently** (separate terminal, no intermediary at all):
```bash
codex review "Read .gator/.includes/reference-notes/enforcer-prompt.md for full instructions. Review the uncommitted changes against the charters."
```

Setup for the Codex CLI: Install [Codex CLI](https://github.com/openai/codex), run `codex login`. `AGENTS.md` is the primary-agent entrypoint, so Codex should be given the dedicated enforcer prompt explicitly for review work. Review mode runs in a read-only sandbox. The primary agent never invokes the Codex CLI directly — cross-vendor GPT review from the agent goes through `enforcer-review.py` with `provider: openai`.

### Gemini as enforcer

```bash
pip install google-generativeai
```

Edit `.gator/enforcer-config.json`:
```json
{
  "layer2_3": {
    "provider": "google",
    "model": "gemini-2.0-flash",
    "api_key_env": "GOOGLE_API_KEY"
  }
}
```

```bash
export GOOGLE_API_KEY=...
gator hook enforcer-review
```

### Claude Code CLI as enforcer

Possible, but less clean than the Python Anthropic path when the repo's `CLAUDE.md` defines Claude as the primary agent.

**From the primary agent, use the enforcer review script** with Anthropic configured — the trust-boundaried path, findings land in `whiteboard.md`:
```bash
gator hook enforcer-review   # enforcer-config.json → provider: anthropic
```

**When the Architect runs the Claude CLI independently** (separate terminal):
```bash
claude --print "$(cat .gator/.includes/reference-notes/enforcer-prompt.md)"
```

**Why the CLI is a bit awkward**: `CLAUDE.md` is the repo entrypoint for the primary-agent role, while `.gator/.includes/reference-notes/enforcer-prompt.md` defines the read-only enforcer role. In practice the explicit enforcer prompt should dominate, but the role separation is cleaner through `enforcer-review.py` with Anthropic configured directly.

**Recommendation**: if the primary agent is Codex and the Architect wants Anthropic as enforcer, use `gator hook enforcer-review` with `provider: anthropic`. Use the Claude Code CLI only when the Architect specifically wants a separate Claude terminal/session as the reviewer — run independently by the Architect, never from the primary agent session.

### Mechanical lint only (no model, no API key)

Zero setup. Catches secrets, SQL dangers, injection risks — but does not read charters.

```bash
gator hook enforcer-review --layer 1
```

For charter-grounded review without an API key, see the `ollama` option under Option D below (free, local).

### Local model as enforcer (free, offline)

Install [ollama](https://ollama.com), pull a model, no API key needed:

```bash
ollama pull llama3
```

Edit `.gator/enforcer-config.json`:
```json
{
  "layer2_3": {
    "provider": "ollama",
    "model": "llama3"
  }
}
```

```bash
gator hook enforcer-review
```

Free and private, but slower and less capable than cloud models.

---

## Configuration Reference

For the full guide on configuring enforcers — decision tree, config file format, cross-vendor principle, and step-by-step setup for each provider — see [`reference-notes/enforcer-configuration.md`](../reference-notes/enforcer-configuration.md). That's what the agent should read when an Architect asks "how do I set this up?"

## All Options (Reference)

The common setups above cover most cases. Below is the full menu for advanced use or when you want to customize.

### Option A: Mechanical lint only (no model, no API key, instant)

```bash
gator hook enforcer-review --layer 1
```

Checks for hardcoded secrets, SQL dangers, injection risks, TODO markers, `.env` files. No API key needed. Zero setup.

**Limitation**: This only runs hygiene checks. It does **not** read charters, check TRIPWIREs, or verify boundary compliance. For charter-grounded review, use Options B–E.

### Option B: Codex CLI (OpenAI)

```bash
# Explicit enforcer prompt
codex review "Read .gator/.includes/reference-notes/enforcer-prompt.md for full instructions. Review the uncommitted changes against the charters."

# With explicit charter-grounded prompt
codex review "Read .gator/.includes/reference-notes/enforcer-prompt.md for full instructions. Read all charters in .gator/charters/ and .gator/constitution.md. Review the git diff against the charters."

# Review changes since branching from main
codex review --base main

# Review a specific commit
codex review --commit HEAD
```

**Setup**: Install [Codex CLI](https://github.com/openai/codex), run `codex login`. That's it.

Codex reads `AGENTS.md` automatically for its role instructions. Review mode runs in a read-only sandbox by default — the "no edits" rule is enforced at the system level.

### Option C: Claude Code (Anthropic)

```bash
# From a separate terminal (not your primary agent session)
claude --print "$(cat .gator/.includes/reference-notes/enforcer-prompt.md)"
```

Or start an interactive session and paste the enforcer prompt. Claude reads `CLAUDE.md` by default — the enforcer prompt overrides with the read-only audit role.

**Note**: this works, but if `CLAUDE.md` defines Claude as the primary agent for the repo, the cleaner Anthropic enforcer path is still Option D (`enforcer-review.py` with `provider: anthropic`) because it avoids entrypoint-role overlap.

**Setup**: Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code), set `ANTHROPIC_API_KEY`.

### Option D: Python script with API call (any provider)

```bash
# Uses enforcer-config.json to pick provider and model
gator hook enforcer-review

# Review specific files
gator hook enforcer-review --files "src/auth.py,src/store.py"

# Review staged changes only
gator hook enforcer-review --staged
```

**Setup**: Edit `.gator/enforcer-config.json`:

| Provider | Install | API key env | Recommended model |
|----------|---------|-------------|------------------|
| `anthropic` | `pip install anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| `openai` | `pip install openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| `google` | `pip install google-generativeai` | `GOOGLE_API_KEY` | `gemini-2.0-flash` |
| `ollama` | Install ollama, pull a model | None (local) | `llama3` |
| `none` | — | — | Layer 1 only |

### Option E: Gemini CLI (Google)

```bash
# Run the enforcer prompt through Gemini
gemini < .gator/.includes/reference-notes/enforcer-prompt.md
```

**Setup**: Install [Gemini CLI](https://github.com/google-gemini/gemini-cli), authenticate with Google.

## Which Should I Pick?

| Situation | Use |
|-----------|-----|
| Just getting started, no API keys | **Option A** — mechanical lint |
| Primary agent is Claude | **Option B** (Codex) or **Option D** (Gemini/GPT) |
| Primary agent is GPT/Codex | **Option C** (Claude) or **Option D** (Gemini) |
| Primary agent is Gemini | **Option B** (Codex) or **Option C** (Claude) |
| Want the cheapest API option | **Option D** with `gpt-4o-mini` or `gemini-2.0-flash` |
| Want free/local | **Option D** with `ollama` |
| CI/CD pipeline | **Option D** with `--format json` |

**The principle**: different model than your primary agent. Different training = different blind spots = independent verification. Same-model is still better than nothing.

## Prerequisites

Options B–E (charter-grounded review) require **populated charters**. If `.gator/charters/` contains only templates, the enforcer has nothing to check against and will return a clean report — which is misleading. Run the bootstrap procedure first (see `.gator/gator-start-up.md`).

Option A (mechanical lint) works regardless — it doesn't read charters.

## What the Enforcer Checks

### Layer 1 — Mechanical Lint (instant, no model)
- Hardcoded passwords and API keys
- Private key material in source
- `DROP TABLE`, `DELETE FROM` without WHERE, `TRUNCATE`
- SQL string concatenation (injection risk)
- `eval()`, `os.system()`, `subprocess` with `shell=True`
- `TODO`/`FIXME`/`HACK` markers introduced
- `.env` files staged for commit

### Layer 2 — Charter-Grounded Review (model required)
- Code change respects charter "Does not own" boundaries
- TRIPWIRE patterns preserved
- Charter updates reflect actual code changes
- New cross-module dependencies captured in `←`/`→`

### Layer 3 — Blast Radius (model required)
- Changes touching TRIPWIRE patterns in cross-cutting charter
- Synchronized implementations still synchronized
- Data flow changes reflected in cross-cutting docs

## Trust Model

The enforcer exists because the primary agent shouldn't be the sole judge of its own work. But if the primary agent runs the enforcer and controls what the Architect sees, that independence is compromised — even without intentional deception (unconscious filtering, self-serving summarization, or simply not running the review at all).

**The rule: enforcement from the primary agent runs *only* through `enforcer-review.py`, whose output reaches `whiteboard.md` as the authoritative record.**

What enforces this:

1. **The enforcer review script is the single enforcement path for the primary agent** (`gator hook enforcer-review`): it sends the diff + relevant charters to the configured enforcer model and writes findings to `whiteboard.md`. The whiteboard is the authoritative record the Architect checks — not the agent's summary.

2. **The primary agent never runs a CLI enforcer directly.** Running `codex review`, `claude --print`, or `gemini` straight from the primary session bypasses the durable `whiteboard.md` record and the structured review path. This is not because `enforcer-review.py` hides findings — it prints to stdout too, and the agent is *supposed* to read the findings so it can summarize them for the Architect — but because routing through it keeps enforcement structured and leaves the authoritative record the Architect checks. Cross-vendor review from the agent goes through `enforcer-review.py` with the corresponding provider (`openai`, `google`, or `anthropic`) set in `enforcer-config.json`.
   ```bash
   # Correct — findings land on the whiteboard via the review script
   gator hook enforcer-review

   # Wrong — primary agent runs a CLI enforcer directly, bypassing the whiteboard record
   codex review "...review the uncommitted changes against the charters."
   ```

3. **The Architect can always run any enforcer independently** in a separate terminal. That is not a primary-agent action, so no trust boundary applies — the output goes straight to the Architect's eyes.
   ```bash
   codex review "Read .gator/.includes/reference-notes/enforcer-prompt.md for full instructions. Review the uncommitted changes against the charters."
   ```

4. **Spot-check the whiteboard**: After the primary agent says "review is clean," open `whiteboard.md` in your editor and verify. This takes 10 seconds and catches filtering.

For routine changes, trusting the agent's summary is fine. For critical changes — anything touching TRIPWIREs, cross-cutting patterns, or security boundaries — the Architect should see enforcer output directly.

## After Review

1. Findings go to `whiteboard.md` automatically (script default) with a timestamp and review type header:
   ```
   ## Review — 2026-05-15 18:30 — Codex CLI (GPT-5.4)
   ```
2. **Agent presents findings to the Architect with context and suggestions — then asks for direction.** The agent does not start fixing things on its own. The Architect decides what to act on, what to defer, and what to dismiss. This is constitutional (see "Enforcer Findings Are for the Architect").
3. Architect directs next steps:
   - Fix now → agent makes the change, updates charters
   - Defer → capture in `inbox.md` with the finding reference
   - Dismiss → Architect explains why (agent notes it for context)
4. Resolved findings stay on the whiteboard as the review record

## Whiteboard Size Policy

`whiteboard.md` is the review log but it can't grow forever. When it exceeds **100 lines**:
- Archive the oldest reviews to `artifacts/review-log.md` (append, don't overwrite)
- Keep only the most recent 2–3 reviews on the whiteboard
- The whiteboard header and separator stay; only review entries rotate out
