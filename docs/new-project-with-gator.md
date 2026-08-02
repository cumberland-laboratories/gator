# Build a New Project with Gator

You're starting a project from scratch and want AI governance from day one. Gator sets up the repo, installs the governance layer, and bootstraps the knowledge layer in one flow.

## Step 1: Clone Gator

```bash
git clone https://github.com/cumberland-laboratories/gator.git
cd gator
```

## Step 2: Create the Project

Point `gatorize.sh` at a directory that doesn't exist yet (or is empty):

```bash
bash gator-engine/scripts/gatorize.sh /path/to/my-new-project
```

Gatorize detects there's no git repo and does everything:

1. Creates the directory
2. Runs `git init`
3. Creates `main` and `dev` branches
4. Installs the full governance layer (`.gator/`, constitution, hooks, entry points)
5. Makes an initial commit

You now have a governed repo with zero manual setup.

## Step 3: Open in Your AI Tool

Open the new project in Claude Code, Codex CLI, or Gemini CLI. The agent reads the entry point (`CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`), finds the constitution, and the concierge bootstrap begins.

The concierge asks about your project — what you're building, what matters, what's off-limits. This conversation produces:

- **Mission** — what this project does
- **Identity** — who the Architect is and how to work together
- **Initial charters** — as you start writing code, the agent maps each module

## Step 4: Write Code, Build Charters

As you build, the agent creates charters alongside your code. Each module gets a structured map:

```
### authenticate(email, password)
File: src/auth/login.py
Validates credentials and returns a session token.
← POST /api/login in routes.py
→ create_session() in session_manager.py
! Returns GENERIC "invalid credentials" for both bad email
  and bad password — prevents account enumeration.
```

You don't write charters by hand. The agent authors them from the code, and you review them for accuracy. The pre-commit hook ensures every code change comes with a charter update.

## Step 5: Add to the Fleet (Optional)

If you have multiple governed repos, the new project is automatically registered in your command post's `registry.md`. You can now:

```bash
# See all governed repos
python gator-engine/scripts/gator-fleet-report.py

# Check for drift across the fleet
python gator-engine/scripts/gator-drift.py
```

See [Fleet Governance](fleet-governance.md) for the full fleet model.

## What You Get from Day One

Starting governed means you never have to retrofit governance onto a codebase. From the first commit:

- Every commit carries `Gator-*` trailers (change type, significance, charter status)
- Charter-alongside-code is enforced — no undocumented changes sneak in
- Session logs capture the full development conversation
- You can switch AI tools mid-project and the governance layer carries the context

## Next Steps

- [Getting Started](getting-started.md) — detailed setup and troubleshooting
- [Governance Model](governance-model.md) — how constitutions, charters, and enforcement work
- [Audit & Compliance](audit-compliance.md) — the evidence trail from day one
