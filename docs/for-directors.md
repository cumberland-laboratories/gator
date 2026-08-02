# Gator for Engineering Directors

**Gator gives you cross-repo AI governance visibility using git-native signals, not another hosted platform.**

---

## The Problem

Your teams are using AI coding tools across 10, 20, 50 repos. You know some of them have good practices. You suspect some don't. But you can't answer basic questions:

- Which repos have governance in place?
- Which repos have drifted from standards?
- Are AI-generated commits being reviewed before merge?
- What's actually happening across the fleet — what's being built, what's blocked, what's drifting?
- Can you see this without asking each team lead to self-report?

You don't want another platform to administer. You don't want a dashboard that requires Postgres, Kubernetes, and an FTE to maintain. You want visibility from the signals already in git.

---

## What Gator Does For You

### Fleet Report: One Command, Full Picture

```
$ gator fleet-report

  gator fleet-report
  12 repos registered
  2026-06-15 09:30

  ✓ service-api
    last commit: a4f2c91 Add rate limiting to auth endpoint (2 hours ago)
    branch: dev  |  tree: clean  |  commits (30d): 47
    gen 2  |  policy: 2026-06-10  |  charters: 5 (34 fn)  |  threads: 3
    issues: 1  |  hooks: yes
    trailers: sig: notable | type: feature | charter: yes | agent: claude

  ✓ frontend-app
    last commit: 8bc1e32 Refactor dashboard components (yesterday)
    branch: dev  |  tree: 3 changed  |  commits (30d): 23
    gen 2  |  policy: 2026-06-10  |  charters: 3 (15 fn)  |  threads: 1
    issues: 0  |  hooks: yes
    trailers: sig: routine | type: refactor | charter: yes | agent: codex

  ! data-pipeline (remote)
    last commit: f91c2d0 Fix partition key logic (4 days ago)
    branch: main  |  tree: remote (unknown)  |  commits (30d): 8
    gen 1  |  policy: 2026-05-29  |  charters: 0  |  threads: 0
    issues: 0  |  hooks: no

  fleet totals: 8 charters, 49 functions, 1 issues
  hooks: 11/12 repos  |  trailers: 9/12 repos
  scan: 10 local, 2 remote (thin-fetch)
```

One command. No login. No web UI. Runs from git history and `.gator/` state.

→ *Detail: [Fleet Governance](fleet-governance.md)*

### Drift Detection: Which Repos Need Attention

```
$ gator drift

  gator drift
  command post: gen 2, policy 2026-06-10

  ✓ service-api — CURRENT
  ✓ frontend-app — CURRENT
  ✓ auth-service — CURRENT

  ⚠ mobile-app — WARNINGS
    ⚠ hook-installed: Git hooks not installed: commit-msg. Run gator update.
    ⚠ trailers: No Gator-* trailers in latest dev commit.

  ✗ data-pipeline — DRIFT
    ✗ generation: Generation 1, command post is 2. Run gator update.
    ✗ policy-version: Policy version 2026-05-29, command post updated 2026-06-10.
    ✗ hooks: No governance hooks. Run gator update.
    ⚠ charters: No charters.

  summary: 3 current, 1 warnings, 1 drifted
```

Drift tells you exactly which repos need intervention and why. Generation gaps, stale policy, missing hooks, absent charters — all visible in seconds.

→ *Detail: [Fleet Governance](fleet-governance.md)*

### Remote-Only Fleet Scanning

You have 50 repos. You're not cloning them all onto one machine.

Gator's thin-fetch model registers repos by remote URL and reads governance state via bare git operations — no working tree required:

```
$ gator fleet-report --remote

  ✓ payments-service (remote)
    last commit: 3e2f1a9 Upgrade stripe SDK (3 days ago)
    branch: main  |  commits (30d): 19
    gen 2  |  charters: 2 (11 fn)  |  hooks: sources present
    trailers: sig: routine | type: dependency | charter: no

  ✓ notification-engine (remote)
    ...
```

Register repos by URL in the registry. `fleet-report` fetches just the refs, reads `.gator/` state via `git show`, and extracts trailers from commit history. Fleet governance without `git clone`.

### Audit Dashboard

```
$ gator audit --html > governance-report.html
```

Self-contained HTML report (8 KB, no external dependencies). Shows:

- Fleet governance coverage
- Drift status across repos
- Recent decisions from session logs and committed summaries
- Charter coverage (repos with vs. without)
- Trailer adoption (commits with governance metadata vs. without)

Open it in a browser. Send it to your VP. No login required.

→ *Detail: [Fleet Governance](fleet-governance.md)*

### Registry: Which Repos Are Governed

The registry is a markdown table in your command post:

```markdown
| Repo | Local path | Remote | Registered | Status |
|------|-----------|--------|------------|--------|
| service-api | /work/service-api | git@github.com:org/service-api.git | 2026-06-01 | current |
| frontend-app | /work/frontend-app | git@github.com:org/frontend-app.git | 2026-06-01 | current |
| data-pipeline | — | git@github.com:org/data-pipeline.git | 2026-06-10 | current |
```

Repos with local paths get full scans. Repos with only remote URLs get thin-fetch scans. Both show up in fleet-report and drift detection.

Adding a repo: `bash gator-engine/scripts/gatorize.sh /path/to/repo`
The installer registers it in the command post automatically.

---

## What Governance Looks Like Across a Fleet

### Per-Repo Enforcement (Engineers Handle This)

Each governed repo has:
- A constitution (what the AI agent follows)
- Charters (structured module maps, updated alongside code)
- Pre-commit hooks (block ungoverned commits)
- Session logs (rolling activity log per commit, committed summaries on demand)

You don't configure this per-repo. Engineers run `gatorize.sh` and the installer handles structure, hooks, and registration.

### Fleet-Level Visibility (You Handle This)

From the command post, you see:
- Which repos are governed and current
- Which repos have drifted from org policy
- What's being built across repos (from trailers and session logs)
- Whether governance is structural (hooks active) or aspirational (no hooks)

### Policy Propagation

Change org policy in one place (the command post). Engineers pull updates with `gator update`. Drift detection shows who hasn't pulled yet.

No CI/CD required. No webhook infrastructure. Git pull is the sync mechanism.

---

## What's Coming

| Feature | What it means for you | Timeline |
|---------|----------------------|----------|
| Remote-only fleet reporting | Register repos by URL, get governance posture without cloning | Done (shipped today) |
| MCP server | Fleet status as native tools in Claude Code sessions — live governance queries | 3-4 weeks |
| Cross-repo status view | Aggregate what's being built across all repos | Phase 3 |
| Outbox sweep | Cross-repo communication — governed repos send discoveries back to command post | Phase 3 |
| Article 14 evidence pack | EU compliance evidence from your existing fleet data | 2 weeks |
| Premium rule packs | Convention enforcement, dependency scoring, DORA metrics (paid tier) | Later |

---

## Deployment Options

| Scale | Command post | Fleet repos | What you get |
|-------|-------------|-------------|-------------|
| **Try it** | Local only | 1-3 repos, local | Full governance loop, local visibility |
| **Team** | Private remote (GitHub/GitLab/ADO) | 5-20 repos, mixed | Fleet governance, shared policy, drift detection |
| **Department** | Private remote, branch protection | 20-50 repos, mostly remote | Remote scanning, audit dashboard, policy propagation |

The command post is a private git repo. You choose where it lives, who has access, and whether it has a remote. Branch protection and access control use your existing platform (GitHub, GitLab, ADO).

→ *Detail: [Installation — Team](installation.md#team-install)*

---

## Getting Started

```bash
# Set up the command post
git clone https://github.com/cumberland-laboratories/gator.git my-governance
cd my-governance
git remote rename origin upstream
git remote add origin <your-private-remote>

# Gatorize your first repo
bash gator-engine/scripts/gatorize.sh /path/to/first-repo

# See the fleet
python gator-engine/scripts/gator-fleet-report.py
python gator-engine/scripts/gator-drift.py
```

Add more repos one at a time. Each `gatorize.sh` run registers the repo and installs hooks. Fleet report grows with each addition.

→ *Full guide: [Getting Started](getting-started.md)*

---

## FAQ

**How long does fleet setup take?**
Command post: 5 minutes. Each repo: 3 minutes (`gatorize.sh`). A 10-repo fleet is governed in under an hour.

**Do engineers need to change their workflow?**
Minimally. They get a pre-commit hook (fires automatically) and an updated entry point file. The AI agent reads the governance layer — engineers don't have to remember to "follow the process."

**What if a repo doesn't have a local checkout?**
Register it by remote URL. Fleet-report and drift use thin-fetch scanning — bare git operations, no working tree. You lose working-tree status (obviously), but get everything else: charters, hooks, policy version, trailers, session summaries.

**Can I see who's making AI-assisted commits vs. manual ones?**
Yes. `Gator-Agent` trailer in every governed commit identifies which AI tool was used (or `manual` for non-AI commits). Fleet-report and audit show this.

**What about repos on different git hosts?**
Mixed fleets work fine. Some repos on GitHub, some on GitLab, some on ADO — the registry just needs the remote URL. Thin-fetch works against any git remote your machine can reach.

**Does this replace our existing CI/CD or code review?**
No. Gator governs the commit path. Your CI pipeline, PR reviews, and deployment process continue unchanged. Gator adds a governance layer before code reaches your existing quality gates.

---

*Cumberland Laboratories — [github.com/cumberland-laboratories](https://github.com/cumberland-laboratories)*
