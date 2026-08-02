# Gator for Engineering Leadership

**Gator lets you scale AI coding adoption with a vendor-neutral governance layer, local-first oversight, and portable evidence — without shipping source code into a SaaS governance backend.**

---

## The Problem

Your engineers are using AI coding tools — Claude, Codex, Gemini, Cursor, Copilot. They're productive. But you have no visibility into:

- Whether AI-generated code is being reviewed before merge
- Which repos have governance in place vs. which are ungoverned
- What decisions are being made in AI sessions, and by whom
- Whether your coding standards are actually being followed
- Whether you can produce evidence of human oversight when regulators ask

Existing governance tools require hosted backends, vendor lock-in, or manual process. Gator provides structural governance using infrastructure you already trust: git repos, commit history, and markdown.

---

## What Gator Does Today

### Repo-Level Governance (per project)

Every governed repo gets a deterministic enforcement layer that works at commit time:

- **Constitutional governance** — a machine-readable document that tells AI agents what they can and cannot do in this repo. Every session starts by reading it.
- **Charter-alongside-code enforcement** — a pre-commit hook blocks commits where code changed but no charter (structured module map) was updated. Structural, not behavioral.
- **Portable commit metadata** — every commit carries `Gator-*` trailers: significance, change type, charter status, agent identity, Architect identity. Extractable via standard `git log`.
- **Cross-model support** — Claude Code, Codex CLI, and Gemini CLI all read the same governance layer. Switch models without losing governance context.

→ *Detail: [Governance Model](governance-model.md)*

### Fleet Governance (across repos)

A command post provides cross-repo visibility without a hosted platform:

- **Fleet report** — governance status across all registered repos. Charters, hooks, policy version, recent activity, trailer presence. One command.
- **Drift detection** — which repos are stale, which have diverged from org policy, which are missing hooks or charters.
- **Remote-only scanning** — register repos by remote URL, get governance posture without cloning. Uses bare git clone cache with `git show` and trailer extraction. No local checkouts required for 50+ repo fleets.
- **Audit dashboard** — convergence view in text, JSON, or self-contained HTML. Recent decisions, governance coverage, fleet health.

→ *Detail: [Fleet Governance](fleet-governance.md)*

### Evidence Substrate

Git-native audit trail that travels with the code:

- **Session logs and committed summaries** — rolling session logs appended on every commit to `.gator/sessions/_active/`. Committed summaries generated on demand via `gator sessions commit-summaries` as durable, git-tracked audit evidence in `.gator/sessions/`.
- **Cross-vendor session archaeology** — extracts structured audit records from Claude Code, Codex CLI, and Gemini CLI session storage. Standardized schema, machine identity, redaction.
- **Tamper-evident by construction** — governance metadata lives in git commit trailers and committed files. SHA-1/SHA-256 hash chain provides integrity without additional infrastructure.

→ *Detail: [Audit & Compliance](audit-compliance.md)*

### Security Architecture

- **Local-first** — all governance data stays on your infrastructure. No network calls for governance operations. No source code exfiltration.
- **No hosted backend** — the command post is a git repo. Push it to your private GitHub/GitLab/ADO for backup and team access. Or keep it local-only.
- **Enforcement is structural** — pre-commit hooks are separate processes whose decisions are deterministic and outside the agent's prompt loop. Blocked commits produce attention-spike STOP boxes that are designed to cause the agent to pause for Architect review. The current gate is behavioral; token-based Architect approval is planned for future versions.
- **Cross-model isolation** — the enforcer (code reviewer) is always a different model than the coding agent. Same-model review is not enforcement.

→ *Detail: [Installation — Access Control](installation.md#team-install)*

---

## What's Coming (60-Day Roadmap)

### EU AI Act Article 14 Evidence Pack (2 weeks)

Structured compliance evidence for human oversight of AI-generated code. Packages the existing committed summary layer, trailer data, and session archaeology into a format that answers Article 14 requirements:

- Evidence of human oversight at every AI-generated code change
- Traceability from decision to commit to deployed code
- Cross-vendor proof (not tied to one AI tool's audit log)
- Local-first — evidence generated and stored on your infrastructure

This is the headline procurement asset for EU-regulated buyers.

### MCP Server (3-4 weeks)

Model Context Protocol server that exposes Gator's fleet intelligence as tools any Claude Code session can call:

- `gator_fleet_status` — governance posture across all repos
- `gator_drift_check` — which repos need attention
- `gator_charter_lookup` — read any module's charter from any repo
- `gator_search` — cross-repo knowledge search

Proves layerability: Gator integrates into existing AI workflows rather than replacing them.

### Integration Recipes (5-6 weeks)

Published guides showing Gator layered over other AI coding stacks without conflict. First recipe: "Using Gator alongside Spec Kit." Gator governs; your stack builds.

---

## How It Compares

| Dimension | Gator | Backstage / Cortex | Copilot Audit | SonarQube |
|-----------|-------|-------------------|---------------|-----------|
| Deployment | Local git repo | Hosted web service | Cloud SaaS | Self-hosted server |
| Source code exposure | Never leaves machine | Catalog metadata only | Code sent to API | Code scanned on server |
| AI-session evidence | Cross-vendor archaeology | None | Single-vendor only | None |
| Commit-level governance | Deterministic hooks | None | None | Post-hoc scanning |
| Multi-model support | Claude, Codex, Gemini | N/A | Copilot only | N/A |
| Fleet governance | Git-native, no infra | Requires Postgres + plugins | Per-org dashboard | Per-instance |
| Price (team) | Free (open source) | Free (1+ FTE to maintain) | Enterprise license | $20K+/yr |

---

## Deployment Model

```
Your infrastructure (no external services)
├── Command Post (private git repo)
│   ├── Org policy, fleet registry, audit reports
│   └── Push to private GitHub/GitLab/ADO for team access
├── Governed Repos (your existing project repos)
│   ├── .gator/ — governance layer (hooks, charters, sessions)
│   └── Thin link → command post for policy inheritance
└── AI Tools (your choice)
    ├── Claude Code, Codex CLI, Gemini CLI, Cursor
    └── All read the same governance layer
```

No new servers. No new databases. No new SaaS subscriptions. Git is the transport, the audit trail, and the access control layer.

---

## Getting Started

```bash
# Clone the command post
git clone https://github.com/cumberland-laboratories/gator.git my-command-post
cd my-command-post

# Point to your own private remote
git remote rename origin upstream
git remote add origin <your-private-remote-url>

# Gatorize a project repo
bash gator-engine/scripts/gatorize.sh /path/to/your/project
```

Open the command post in any AI coding tool. The concierge walks you through setup.

→ *Full installation guide: [Getting Started](getting-started.md)*
→ *Team and enterprise setup: [Installation](installation.md#team-install)*

---

## Key Decisions This Implies

If you adopt Gator:

1. **You choose where governance lives.** A private git repo on your existing hosting. You control access, backup, and retention.
2. **You choose which repos are governed.** Registration is per-repo, not all-or-nothing. Start with one, expand as confidence builds.
3. **You don't choose an AI vendor.** Gator works with whatever models your engineers prefer. Governance is model-neutral.
4. **You don't need new infrastructure.** If you have git and Python 3.10+, you have everything Gator needs.
5. **Evidence accumulates with every commit.** Every commit in a governed repo produces governance trailers and session log entries. Committed summaries are generated on demand for durable audit evidence.

---

*Cumberland Laboratories — [github.com/cumberland-laboratories](https://github.com/cumberland-laboratories)*
