# Gator Command

The command post for [Gator](https://github.com/cumberland-laboratories/gator) — AI-assisted engineering governance.

## How to Use This Repo

**Open it in an AI coding assistant.** Claude Code, Codex, Gemini CLI, Cursor — whichever you use. The agent reads the constitution and acts as your concierge: it knows the architecture, the configuration options, the procedures, and the fleet state. Ask it what you need.

Gator is designed to be operated *with* an AI agent, not studied as documentation. The governance layer is markdown that agents read natively. The concierge layer routes your questions to the right procedures and reference material. The agent is the interface.

```
You: "gator init"
You: "Gatorize my project at ~/code/my-app"
You: "Set up an enforcer using GPT as the reviewer"
You: "Check if the charters still match the code"
You: "What's the status of the fleet?"
```

## What Gator Does

Gator governs AI-assisted coding. It keeps human comprehension synchronized with AI-generated code through constitutions, module charters, deterministic commit gates, and cross-model enforcement.

### Use Cases

**Solo developer with one repo** — You want the AI agent to maintain a map of your codebase (charters), enforce that the map stays current (commit gate), and preserve session context across conversations (knowledge layer). Install Gator, bootstrap charters, and the loop runs from there.

**Solo developer with multiple repos** — Same as above, plus: this command post becomes your cross-repo control plane. One org policy propagated to every repo. Fleet status, drift detection, and audit dashboards from one place.

**Team with shared repos** — Gator's knowledge layer travels with the repo via git. When a teammate (human or AI) opens the repo, they get the full architectural context — mission, charters, threads, decisions. The enforcer provides independent review from a different model than the one writing code.

**Compliance and audit** — Every commit carries `Gator-*` trailers (change type, significance, charter status, agent identity). Session summaries provide durable evidence of what was decided and who was supervising. Fleet-wide audit reports aggregate governance health across repos.

### Configurations

Gator is model-neutral and modular. The PI chooses the configuration that fits their stack:

| Decision | Options |
|----------|---------|
| **Primary agent** | Claude Code, Codex CLI, Gemini CLI, Cursor, any markdown-aware AI tool |
| **Enforcer model** | Anthropic Sonnet, OpenAI GPT, Google Gemini, local via Ollama, or none |
| **Review cadence** | Light (lint only), Standard (lint + model review on significant changes), Rigorous (pre-code + post-code review) |
| **Fleet scope** | Single repo (no command post needed), multi-repo (this command post), remote repos (bare cache scanning) |
| **Session archaeology** | Off, local spool, committed summaries (git-tracked audit trail) |

The concierge agent walks you through these choices. You don't need to read configuration docs — tell the agent what you want and it configures the system.

## Quick Start

Install the CLI once (pipx keeps it isolated from your system Python):

```bash
pipx install gator-command
```

Then gatorize any project:

```bash
gator gatorize /path/to/your/project
```

Open that project in your AI assistant — the concierge bootstrap begins.

For fleet operations from this source checkout, the pre-CLI raw-script commands still work — e.g., `python gator-command/scripts/gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`. Downstream users use the [Dashboard](docs/how-gator-works.md) (`gator dashboard`) for fleet views. The bash installer chain (`gatorize.sh` and friends) was retired in v2.4.0 — always use `gator gatorize` or `pipx install gator-command`.

## Architecture at a Glance

```
This repo (command post):
  constitution.md          Governance rules for this command post
  gator-command/           Knowledge graph + machinery + fleet tooling
    scripts/               CLI tooling (gatorize, fleet-report, drift, audit)
    templates/             Starter kit deployed to project repos
    procedures/            Standards and workflows
    reference-notes/       Concierge knowledge (the agent reads these)

Each governed repo:
  .gator/
    constitution.md        Per-repo governance rules
    charters/              Module maps (the intelligent codebase layer)
    scripts/               Hooks + enforcer
    field-guides/          Language pattern references (optional)
    command-post.md        Thin link back to this command post
```

## Multi-Model Architecture

The constitutions are the interface contract. Any model that reads markdown and follows instructions can operate the system.

- **Primary agent**: Reads charters, writes code, updates the knowledge layer
- **Enforcer**: Different model, read-only, audits the agent's work against charters
- **The architecture outlives any individual model** — switch tools mid-project without losing context

## License

Apache License 2.0 — [Cumberland Laboratories](https://github.com/cumberland-laboratories). See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
