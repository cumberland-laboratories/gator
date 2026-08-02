# Getting Started

This guide takes you from zero to a governed repo in about 3 minutes.

## Prerequisites

| Requirement | Check | Notes |
|------------|-------|-------|
| **Git** 2.30+ | `git --version` | |
| **Python** 3.10+ | `python --version` or `python3 --version` | Hooks and CLI scripts are Python |
| **Bash** | `bash --version` | Native on macOS/Linux. On Windows, install [Git for Windows](https://gitforwindows.org/) — it includes Git Bash |
| **AI coding tool** | | Claude Code, Codex CLI, Gemini CLI, or Cursor |

If any prerequisite is missing, see [Troubleshooting](#troubleshooting) below.

## Step 1: Clone Gator

```bash
git clone https://github.com/cumberland-laboratories/gator.git
cd gator
```

This gives you a working Gator Command post — the control plane for AI governance across your repos.

## Step 2: Gatorize a Git Repo

Point `gatorize.sh` at any existing git repository you want to govern:

```bash
bash gator-engine/scripts/gatorize.sh /path/to/your/repo
```

This installs the `.gator/` governance layer into that repo:

- **Constitution** — rules your AI agents follow
- **Charter directory** — structured maps of your code modules
- **Pre-commit hook** — enforces charter-alongside-code at commit time
- **Model entry points** — `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`

## Step 3: Open in Your AI Tool

Open the governed repo in Claude Code, Codex, or Gemini CLI. The agent reads the entry point, finds the constitution, and the concierge bootstrap begins — it'll ask about your project and start building the knowledge layer.

## Step 4: Your First Commit

Make a code change. When you run `git commit`:

```
  gator pre-commit: PASS

  ✓ charter-alongside-code: code changed, charter updated
  ✓ commit-draft: frontmatter present, significance: notable
  ✓ dangerous-code-lint: no findings

  Trailers assembled:
    Gator-Charters: 3
    Gator-Functions: 12
    Gator-Charter-Changed: yes
    Gator-Significance: notable
    Gator-Change-Type: feature
```

If you changed code without updating a charter, the hook blocks the commit and tells you why.

## What Happens Next

Your AI agent now works within a governance loop:

1. **Session open** — reads constitution, mission, roadmap, active threads
2. **Coding** — reads charters before modifying code, writes and updates charters alongside changes (the agent authors charters, not the human)
3. **Commit** — pre-commit hook validates charter-alongside-code, assembles trailers, appends to session log
4. **Next session** — picks up where you left off, with full context (charters persist the agent's understanding of your code across sessions and across models)

## Troubleshooting

### `gatorize.sh` fails or Bash is not available

`gatorize.sh` requires Bash. There is no Python alternative for the installer.

**Windows**: Install [Git for Windows](https://gitforwindows.org/), which includes Git Bash. Then run the command in Git Bash, not PowerShell or cmd:

```bash
# In Git Bash (not PowerShell)
bash gator-engine/scripts/gatorize.sh /c/Users/you/code/my-repo
```

Note the `/c/Users/...` path style — Git Bash uses Unix-style paths.

**macOS/Linux**: Bash is pre-installed. If you get a permissions error:

```bash
chmod +x gator-engine/scripts/gatorize.sh
bash gator-engine/scripts/gatorize.sh /path/to/your/repo
```

### Python not found or wrong version

The installer runs in Bash, but everything after install (hooks, CLI commands) requires Python 3.10+.

```bash
python --version    # or python3 --version
```

If `python` points to Python 2 or isn't found, check your PATH. On some systems, Python 3 is only available as `python3`. Gator's git hooks use the Python interpreter that was active when `gatorize.sh` ran — if you change your Python installation later, re-run `gator update` to refresh the hooks.

### Paths with spaces

Wrap the repo path in quotes:

```bash
bash gator-engine/scripts/gatorize.sh "/path/to/my repo"
```

### Target directory has no git repo

That's fine — `gatorize.sh` detects this and runs `git init` automatically before installing.

### Hooks don't fire on `git commit`

Check that hooks were installed:

```bash
ls -la /path/to/your/repo/.git/hooks/pre-commit
```

If missing, re-run the installer or update:

```bash
python gator-engine/scripts/gator-update.py --path /path/to/your/repo
```

## Next Steps

- [Installation details](installation.md) — platform-specific guidance, Windows setup, team installs
- [Governance Model](governance-model.md) — how constitutions, charters, and enforcement work
- [Fleet Governance](fleet-governance.md) — governing multiple repos from one command post
