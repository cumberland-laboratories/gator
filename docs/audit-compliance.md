# Audit & Compliance

Gator produces governance evidence from your existing git workflow. No separate reporting tools, no manual documentation — the evidence flows from commit trailers (assembled automatically by the pre-commit hook) and session logs (appended on every commit). Committed summaries for durable audit evidence are generated on demand via `gator sessions commit-summaries`.

## Commit Trailers

Every commit in a governed repo carries `Gator-*` trailers:

```
Gator-Charters: 3
Gator-Functions: 12
Gator-Charter-Changed: yes
Gator-Significance: notable
Gator-Change-Type: feature
Gator-Agent: claude-opus-4
Gator-Architect: alan
```

These are standard git trailers — extractable with `git log --format='%(trailers)'`. No proprietary format. Any tool that reads git history can read governance metadata.

## Audit CLI

Run a governance audit across the fleet:

```bash
# Text output
python gator-engine/scripts/gator-audit.py

# JSON output
python gator-engine/scripts/gator-audit.py --json

# Self-contained HTML dashboard
python gator-engine/scripts/gator-audit.py --html > audit.html
```

The HTML dashboard is a self-contained 8 KB file with no external dependencies. Open it in any browser.

## What the Audit Covers

- **Fleet status** — which repos are governed, their generation and charter coverage
- **Drift detection** — which repos have fallen behind current policy
- **Session archaeology** — AI decisions across vendors, aggregated
- **Override history** — every charter-skip override, when and why
- **Governance coverage** — percentage of repos with active hooks, charters, and current policy

## Evidence for Regulators

The combination of commit trailers, session logs, and audit reports produces a continuous evidence stream. Committed summaries (generated on demand via `gator sessions commit-summaries`) provide the durable, git-tracked layer:

1. **Who made the decision?** — `Gator-Agent` and `Gator-Architect` (formerly Gator-PI) trailers on every commit
2. **Was the code reviewed?** — enforcer audit trail, cross-model review wall
3. **Were standards followed?** — pre-commit hook pass/fail, charter-alongside-code enforcement
4. **Can you prove human oversight?** — Architect identity in trailers, override audit trail, committed session summaries with decision records

All evidence lives in git. Tamper-evident (commit hashes), versioned, auditable.

## EU AI Act Article 14

Gator's audit infrastructure maps directly to Article 14 (human oversight) requirements for AI systems. The committed summary layer and trailer data provide structured evidence that human oversight was maintained throughout AI-assisted development.

*Detailed Article 14 evidence pack: coming in v1.1.*
