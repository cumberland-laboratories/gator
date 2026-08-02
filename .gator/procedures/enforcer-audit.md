# Procedure: Enforcer Audit

## Who Runs This

The enforcer — a **different model** than the chat agent. Never the same model that wrote the content being audited.

## Access

**Read-only.** The enforcer does not edit the Memex. It produces an audit report. The primary agent (with the human present) reads the report and decides what to act on.

## Input

The entire Memex: `identity.md`, all active threads, all lightweight threads, `patterns.md` (rhythms), and `constitution.md`. Artifacts loaded as needed for cross-reference verification.

## Output

An audit report written to `docs/reports/YYYY-MM-DD-enforcer-audit.md` with findings organized by category:

### Report Structure

```
# Enforcer Audit — YYYY-MM-DD
Auditor model: [model name]
Threads audited: [count]
Findings: [count]

## Staleness
Threads with `last-touched` older than [threshold] that show no Next Up or recent hits.
- [thread name] — last touched [date], hits: [n], recommendation: demote / compress / flag for human

## Contradictions
Claims in one thread that conflict with another, or with identity.md.
- [thread A] says X; [thread B] says Y — recommendation: reconcile / flag for human

## Bloat
Threads exceeding 60 lines, or always-loaded budget over 400 lines.
- [thread name] — [n] lines, recommendation: split (seam at [section]) / compress / demote

## Cross-Reference Integrity
Broken links, orphaned threads (no inbound references), or missing annotations.
- [thread name] → [broken link] — recommendation: fix path / add annotation

## Graph Health (v2.1)
Run `graph_health.py --json` and follow → [graph-health-response.md](graph-health-response.md) for triage.
Report per-dimension scores and any yellow/red findings.

## Summary
[2-3 sentences: overall health of the Memex, highest-priority action items]
```

## What the Enforcer Does NOT Do

- Edit any Memex file
- Create or delete threads
- Update frontmatter (hits, last-touched, category, tags)
- Modify the constitution or procedures

All of these are chat agent responsibilities, executed with the human in the loop after reviewing the audit report.

## Post-Audit

After an enforcer audit is completed, the chat agent **must** append a summary of the audit to `.gator/commit_draft.md` — model used, finding count, and highest-priority items. The appended bullet should carry an agent suffix in the form `-<agent>` (for example `-codex`). This ensures audit results are captured in the next commit message and visible to future sessions during orientation.

## Cadence

To be determined. Initial runs are manual (human invokes a different model). Target: periodic scheduled runs.
