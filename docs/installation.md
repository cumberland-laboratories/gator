# Installation

## Requirements

| Requirement | Minimum | Notes |
|------------|---------|-------|
| Git | 2.30+ | `git --version` to check |
| Python | 3.10+ | `python --version` to check |
| Bash | 4.0+ | Native on macOS/Linux; Git Bash on Windows |
| AI coding tool | Any | Claude Code, Codex CLI, Gemini CLI, or Cursor |

## Solo Local Install

The simplest setup — one machine, one user.

```bash
git clone https://github.com/cumberland-laboratories/gator.git
cd gator
```

You now have a local command post. Gatorize your projects from here.

## Solo with Remote Backup

Clone Gator, then push to your own private remote for backup and multi-machine access.

```bash
git clone https://github.com/cumberland-laboratories/gator.git
cd gator

# Add your own remote as origin, keep upstream for updates
git remote rename origin upstream
git remote add origin https://github.com/YOUR-ORG/gator-command.git
git push -u origin main
```

Now you have:

- `upstream` — Cumberland's releases (pull updates from here)
- `origin` — your private copy (push your knowledge layer here)

## Windows

Gator works on Windows via Git Bash (included with [Git for Windows](https://gitforwindows.org/)).

```bash
# In Git Bash
git clone https://github.com/cumberland-laboratories/gator.git
cd gator
bash gator-engine/scripts/gatorize.sh /c/Users/you/projects/my-repo
```

!!! note "Windows hooks"
    The installer detects Windows and writes Python-native hook wrappers (using your current `sys.executable`) instead of Bash wrappers. This ensures hooks fire correctly regardless of shell configuration.

## macOS / Linux

No special steps. Clone and gatorize.

```bash
git clone https://github.com/cumberland-laboratories/gator.git
cd gator
bash gator-engine/scripts/gatorize.sh ~/projects/my-repo
```

## Gatorizing a Repo

```bash
bash gator-engine/scripts/gatorize.sh /path/to/your/repo
```

This creates:

```
your-project/
  .gator/                  ← governance layer
    constitution.md        ← rules for AI agents
    charters/              ← structured code maps
    scripts/hooks/         ← pre-commit enforcement
    ...
  CLAUDE.md                ← Claude Code entry point
  AGENTS.md                ← Codex entry point
  GEMINI.md                ← Gemini entry point
```

The project is registered in the command post's `registry.md` and governed immediately.

## Adding More Repos

Run `gatorize.sh` for each project:

```bash
bash gator-engine/scripts/gatorize.sh ~/projects/repo-two
bash gator-engine/scripts/gatorize.sh ~/projects/repo-three
```

Each repo gets its own `.gator/` layer and a thin link back to the command post. Use `gator fleet-report` from the command post to see all governed repos at once.

## Updating Gator

Pull product updates from upstream without losing your knowledge layer:

```bash
# From your gator command post
git fetch upstream
git checkout upstream/main -- gator-engine/
git add gator-engine/
git commit -m "Update gator-engine to latest"
```

The `gator-engine/` directory contains product code (scripts, templates, docs). Your `gator-command/` directory (mission, roadmap, threads, identity) is never touched by updates.

Then propagate to governed repos:

```bash
python gator-engine/scripts/gator-update.py --path /path/to/your/repo
```

This overlays updated templates onto `.gator/` — it never deletes your charters, threads, or artifacts.

## Team Install

For teams sharing a command post:

1. One person clones Gator and pushes to a shared private remote
2. Team members clone from the shared remote
3. Each member gatorizes their local project repos
4. Fleet reports aggregate across all governed repos

!!! note "Access control"
    The command post contains organizational policy and knowledge — treat it like any sensitive repo. Use your platform's access controls (GitHub private repos, GitLab groups, ADO project permissions).
