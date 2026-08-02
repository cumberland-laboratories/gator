# Threat Model

What Gator protects against — and what it doesn't. Gator's enforcement is **behavioral, not cryptographic**: it creates friction, visibility, and audit trails that make governed work the path of least resistance. It does not prevent a determined human or a compromised CI pipeline from bypassing controls.

## Four Threat Profiles

| Profile | Assumption | What Gator does | What Gator does NOT do |
|---------|-----------|-----------------|----------------------|
| **Cooperative agent** | Agent follows instructions but forgets, drifts, or loses context across sessions | Pre-commit hooks catch missing charter updates. Trailers create audit trail. Constitution reloads at session start restore intent. Session archaeology reconstructs what happened when context was lost. | — |
| **Sloppy agent** | Agent cuts corners — skips charters, writes code without updating docs, ignores tripwires | STOP boxes in charters create hard friction. Pre-commit hook blocks commits missing charter updates. Enforcer (cross-model) catches what the coding agent rationalized away. Whiteboard findings are visible to the Architect. | Cannot prevent an agent from writing bad code within a file it's allowed to edit. Charter quality is behavioral, not verified. |
| **Adversarial / rogue agent** | Agent actively tries to circumvent governance — suppresses findings, edits hooks, rewrites constitution | **Gator alone is not sufficient.** The agent can edit `.gator/` files, modify hook scripts, or rewrite the constitution. Defense requires external layers: protected branches, CI-enforced hook verification, Architect-held secrets, read-only enforcer access, signed commits. | Cannot prevent an agent with filesystem write access from modifying its own governance files. Cannot detect silent suppression without an external auditor. |
| **Enterprise (multi-actor)** | Multiple developers, multiple agents, compliance requirements, external audit | All of the above, plus: CI/PR gates validate trailers and charter state before merge. Protected branches prevent direct push. Signed commits prove authorship. Central audit dashboard (from Gator Command) provides fleet-wide visibility. Session logs provide evidence for Article 14 (EU AI Act) human oversight requirements. | Cannot enforce hosting-platform access controls (that's GitHub/GitLab/ADO's job). Cannot guarantee session log completeness if vendor storage is cleared. |

## The Layer Cake

Gator's security model is defense in depth. Each layer adds protection the previous layer can't provide:

1. **Constitutional rules** (behavioral) — the agent reads and follows them. Cheapest layer. Sufficient for cooperative agents.
2. **Git hooks** (structural) — separate process, agent can't suppress output. Catches sloppy agents.
3. **Cross-model enforcer** (trust boundary) — different model reviews the work. Same-model review is proofreading; cross-boundary review is enforcement.
4. **CI/CD gates** (external) — platform-enforced validation. Required for adversarial threat model.
5. **Platform controls** (infrastructure) — branch protection, signed commits, access control. Required for enterprise.

## What This Means for You

- **Solo dev, trusted agent**: Tiers 1-2 (constitution + hooks) are sufficient. You're protecting against forgetfulness, not malice.
- **Team with AI agents**: Add Tier 3 (enforcer). The cross-model review catches what no single agent can catch about its own work.
- **Regulated environment**: You need all five layers. Gator provides 1-3 and the audit evidence for 4-5. Your platform provides the enforcement.

## Honest Limitations

- Gator cannot make cryptographic guarantees about agent behavior. No tool can — agents run on the same filesystem they govern.
- Charter quality is self-reported. An agent can write a charter that says "updated" without meaningful content. Charter quality metrics (coverage, staleness, tripwire density) are on the roadmap but not yet built.
- Session logs depend on vendor storage. If Claude/Codex/Gemini session data is deleted before extraction, that evidence is gone.
- The enforcer is as good as the model running it. A weak enforcer model may miss issues a stronger one would catch.

## Connections

→ [Security Model thread](../gator-command/active-threads/security-model.md)
→ [Defense in Depth reference note](../gator-command/reference-notes/defense-in-depth.md)
→ [ChatGPT blind review](../gator-command/artifacts/2026-06-02-chatgpt-blind-review-gator-1.md) — source of the four-profile framework
