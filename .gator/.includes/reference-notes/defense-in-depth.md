# Defense in Depth — Why No Single Failure Breaks Governance

Every objection to AI-assisted coding governance follows the pattern "but what if X fails?" The answer is never "X can't fail." The answer is "four independent layers catch it when it does, and the evidence is in the git history."

## The Layers

| Layer | What it is | What it catches | How it enforces |
|---|---|---|---|
| **Constitutional** | Rules the agent reads and follows | Intent violations, process skips, scope creep | Behavioral — the agent *should* comply |
| **Mechanical (linter)** | `enforcer-review.py` — pattern matching, static analysis | Secrets, SQL injection, dangerous commands, obvious errors | Automated — runs every commit, no judgment needed |
| **Adversarial (enforcer)** | Different model reviews against charters | Semantic drift, logic errors, charter/code disagreement, subtle bugs | Independent — a different model with read-only access |
| **Structural (git hooks)** | Pre-commit hooks, trailers, signed commits | Process bypass, missing metadata, suppressed findings | Process-level — the agent *cannot* circumvent |

## Defense Matrix

| Attack vector | Constitutional | Mechanical | Adversarial | Structural |
|---|---|---|---|---|
| **Charter goes stale** | "Update charters with every code change" | — | Enforcer detects charter/code divergence | `Gator-Charter-Changed: no` on code commit; hook can warn/block |
| **Agent hallucinates** | Charter provides ground truth to check against | Linter catches mechanical errors | Enforcer (different model) cross-checks | Trailers + signed history create verifiable record |
| **Agent skips the loop** | Constitution defines loop as mandatory | — | Enforcer audit catches missing steps | Hook verifies commit draft, trailers present |
| **Enforcer findings suppressed** | "Present to Architect, don't fix silently" | — | Whiteboard.md written by hook, not agent | Hook writes directly — agent never touches output |
| **Standards drift across fleet** | Org policy propagates via thin link | — | Cross-repo enforcer audit | `Gator-Policy-Version` trailer; `gator drift` reads from remotes |
| **Malicious or rogue agent** | Constitution is first defense (behavioral) | Linter catches dangerous patterns | Different model catches semantic issues | Git hooks block commits; signed commits prove provenance |
| **Architect makes a bad decision** | — | Linter catches mechanical risks | Enforcer surfaces steelman arguments | Significance check flags high-impact changes; decision attribution in trailers |

## The Principle

Each layer assumes the others might fail:

- The **constitution** is for honest agents that follow instructions
- The **linter** catches what honest agents miss mechanically
- The **enforcer** catches what the linter can't reason about semantically
- The **git hooks** ensure none of these can be bypassed structurally
- The **trailers** make everything visible after the fact, from any remote

No single layer is perfect. The combination is very hard to defeat. And because the evidence rides in git, it's auditable, portable, signable, and customer-owned.

## The Objection Killer

When someone says "but charters can go stale" or "agents can hallucinate" — the answer is not "our agent is better." The answer is: "we have four independent mechanisms that catch it when they do, the evidence is in the git history, and you can verify it yourself without trusting our backend."

That's a fundamentally different product category from "trust our hosted analytics."

## Connections

→ [Security Model](../active-threads/security-model.md) — access control and sensitivity layers
→ [Gator CLI](../active-threads/gator-cli.md) — git trailers as the structural evidence layer
→ [Coding Standard](../procedures/coding-standard.md) — function tags that charters consume
→ [Git as Governance Transport](../artifacts/2026-05-28-codex-git-as-governance-transport.md) — the full transport architecture
