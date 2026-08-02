# Gator Command

**Git-native governance for AI-assisted engineering.**

Gator turns your repo into an intelligence surface. The AI agent builds structured maps of your codebase (charters), a strategic operations brief (pulse), and project assessments — all committed to Git. A deterministic pre-commit gate blocks commits when the agent changes code without updating the map.

Local-first. Git-native. Works with Claude Code, Codex, Gemini CLI. Apache 2.0 licensed.

## Install

```bash
pip install pipx        # if you don't have pipx yet
pipx ensurepath         # add to PATH (restart terminal after)

pipx install gator-command
```

## Quick Start

```bash
cd /path/to/your/repo

gator gatorize .        # install governance into this repo
gator init              # start a governed session
gator dashboard         # open the intelligence console
```

The agent reads the governance layer and orients to your project. Your first `git commit` fires the hooks.

## Upgrade

```bash
pipx upgrade gator-command

cd /path/to/your/repo
gator gatorize .        # refresh templates and hooks
```

Your content is always preserved. Only templates and scripts refresh.

## Commands

| Command | What it does |
|---------|-------------|
| `gator gatorize <path>` | Install or upgrade governance in a repo |
| `gator init` | Start a governed session (repairs hooks if needed) |
| `gator dashboard` | Open the intelligence console |
| `gator pulse` | Generate the strategic operations brief |
| `gator audit` | Run governance audit |
| `gator version` | Show installed version |

## What Gator Provides

- **Repo intelligence** — charters map code structure, pulse summarizes momentum, assessments provide AI-generated evaluation. All committed to Git.
- **Governance enforcement** — a deterministic pre-commit hook that blocks commits when code changes without charter updates. No LLM in the gate. Configurable: strict, warn, or off.
- **Dashboard** — a local web console for browsing your governance layer, session history, and project state. Full file history with git version navigation.
- **Session persistence** — the governance layer carries project context across sessions and across models. Switch from Claude to Codex mid-project without losing architectural understanding.

## How It Works

1. `gator gatorize .` installs a `.gator/` folder into your repo with governance scaffolding
2. AI agents read the constitution and charters to understand your codebase
3. Every `git commit` runs a deterministic hook that validates charter-alongside-code
4. Session snippets capture what context produced each commit
5. `gator dashboard` makes it all browsable in a local web UI

## Links

- [Source code](https://github.com/cumberland-laboratories/gator)
- [Apache License 2.0](https://github.com/cumberland-laboratories/gator/blob/main/LICENSE)

---

Built by [Cumberland Laboratories](https://github.com/cumberland-laboratories)
