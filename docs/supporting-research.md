# Supporting Research — Why Gator Works

Gator's architectural decisions are grounded in published research, vendor guidance, and measured practitioner results. This note collects the evidence — distinguishing between what is well-supported, what is directionally supported, and what remains unvalidated.

---

## 1. Structured Context Beats Raw Exploration

The claim: a maintained architectural map produces better agent outcomes than letting the agent explore fresh every time.

| Source | Finding | Relevance |
|--------|---------|-----------|
| **RepoRepair** (arxiv 2603.01048, 2026) | Repository-level repair improves when the model gets structured file/function documentation rather than raw local context alone | Direct support for charters as function-level structured summaries |
| **SWE-ContextBench** (arxiv 2602.08316, 2026) | Reusable summarized experience from prior tasks materially helps future tasks | Direct support for charter accumulation across sessions |
| **Repository Intelligence Graph (RIG)** (arxiv 2601.10112, Tel Aviv University, 2026) | Deterministic architectural map as LLM-friendly JSON: +12.2% mean accuracy, -53.9% completion time across 8 repos. Multilingual: +17.7% accuracy, -69.5% time. | Validates the "small map" approach at scale |
| **Aider repo map** (Gauthier, 2023–present) | Graph-ranked concise map (~1K tokens) improves agent orientation vs no map | Established practice; Gator extends with intent, invariants, and maintenance loop |
| **SWEZZE** (arxiv 2603.28119, 2026) | Code context compression retaining fix ingredients reaches 93.8–99.2% of all-baselines union | Compression doesn't lose signal if done intelligently |

---

## 2. Iterative Refinement Beats One-Shot Generation

The claim: the recursive loop (read → change → update → repeat) produces better code than generate-and-accept.

| Source | Finding | Relevance |
|--------|---------|-----------|
| **Self-Refine** (arxiv 2303.17651, 2023) | Iterative self-refinement consistently outperforms one-shot generation across tasks | Core support for the charter update loop |
| **OpenAI: How OpenAI Uses Codex** (2026) | Plan-first flows for larger changes; structure, context, and iteration reduce errors | Vendor validation of plan → execute → validate pattern |
| **Codex Security** (OpenAI, 2026) | Explicit closed loop: build codebase-specific model → validate → patch → revalidate | Same architectural shape as the charter loop |
| **OpenAI: PLANS.md cookbook** (2026) | Structured planning documents improve Codex task execution | Planning grounded in structured context > planning from scratch |

---

## 3. Independent Review Catches What Self-Review Misses

The claim: a different model (enforcer) catches error classes the primary agent cannot see in its own output.

| Source | Finding | Relevance |
|--------|---------|-----------|
| **Anthropic: Advanced Patterns PDF** (2026) | Explicitly moving toward specialized reviewer agents and agent-team code review | Vendor direction aligned with enforcer pattern |
| **OpenAI: Datadog case study** (2026) | System-level review and human-reviewed patches rather than blind auto-merge | Independent review as production practice |
| **Codex Security** (OpenAI, 2026) | Keeps patching reviewable and human-reviewed; validation sandbox before deployment | Review separation as security architecture |
| **Financial audit / FDA / peer review** (institutional) | The person performing the work cannot be the sole reviewer | Centuries of institutional precedent for the independence principle |

---

## 4. Structured Context Is More Token-Efficient Than Exploration

The hypothesis: structured navigation context reduces token consumption compared to unguided exploration, especially when accounting for rework. This is directionally supported but not yet validated in a clean head-to-head comparison against unstructured ("vibe coding") workflows.

| Source | Finding | Evidence strength |
|--------|---------|-------------------|
| **AGENTS.md empirical study** (10 repos, 124 PRs, 2026) | Having maintained repo-level instructions: -28.64% median runtime, -16.58% output tokens | Measured, published — but covers only entry-point instructions, not full charters |
| **FastAPI benchmark** (practitioner report, 800 files) | Pre-structured context vs exploration: -90% tool calls, -63% output tokens, -58% cost per task | Practitioner measurement, not peer-reviewed |
| **CartoGopher** (AST knowledge graph, 2026) | Same or better solve rates with ~20% average token savings, six hours faster | Published research |
| **Anthropic MCP docs** (2026) | Selective tool loading vs all-tools-in-prompt: orders of magnitude consumption reduction | Vendor documentation — the principle (load relevant context, not everything) |
| **Boehm's cost-of-quality curve** (software engineering, decades) | Bug fix cost scales ~10x per stage: design → code → test → production | Analogy, not direct measurement — but the principle (prevention < rework) is well-established |

---

## 5. Navigation as an Emerging Paradigm for AI Agents

The claim: "navigation coding" names a real practice that research is independently converging on.

| Source | Finding | Relevance |
|--------|---------|-----------|
| **CodeCompass** (arxiv 2602.20048, Feb 2026) | Agents fail because navigation and retrieval are different problems; structural navigation materially improves outcomes | Direct support — the "navigation paradox" is exactly what charters solve |
| **Formal Architecture Descriptors as Navigation Primitives** (arxiv 2604.13108, Apr 2026) | Architecture descriptors reduce agent navigation overhead | Charters ARE architecture descriptors for this purpose |
| **Navigational Thinking as an Emerging Paradigm** (arxiv 2603.22133, Mar 2026) | AI-era work involves navigation through structured spaces rather than only symbolic programming | Broader philosophical grounding for the practice name |

---

## 6. Vendor Convergence

Anthropic and OpenAI are converging on pieces of Gator's pattern. Based on their public guidance, neither ships the full combination — though their internal practices may go further than what's publicly documented.

| Source | Direction | Not described in cited public guidance |
|--------|-----------|----------------------------------------|
| **OpenAI: Harness Engineering** (2026) | Short entry files, repo knowledge as system of record, progressive disclosure, agent legibility | Mandatory knowledge-update loop, named invariant markers (TRIPWIRE), enforcer trust boundary |
| **Anthropic: Scaling Agentic Coding** (2026) | CLAUDE.md review in onboarding, iterative focused tasks, code review agents | Constitutional governance as enforcement, explicit "Does Not Own" boundaries, concierge pattern |
| **Anthropic: Claude Code Memory** (2026) | Auto memory, project files, on-demand topic loading | Repo-native-only policy for project knowledge; enforcer independence requirement |
| **OpenAI: Codex workflow** (2026) | Plan-first, scoped tasks, review mode, doc-gardening | Constitutional enforcement (vs recommended practice); charter notation system |

---

## What's NOT Yet Validated

- The **3–6% charter sizing ratio** is measured from one production codebase (75K-line Django app). Needs more data points.
- The **token cost comparison** (structured navigation vs unguided exploration) has directional evidence but no clean head-to-head benchmark yet.
- The **concierge pattern** is validated as uncommon and useful, but no controlled study measures its impact on session continuity.
- The **TRIPWIRE mechanism** has no external validation beyond an internal production refactor (zero regressions across 3 god-function decompositions).

These are candidate experiments, not gaps that undermine the architecture.

---

## Source URLs

- [Self-Refine](https://arxiv.org/abs/2303.17651)
- [RepoRepair](https://arxiv.org/abs/2603.01048)
- [SWE-ContextBench](https://arxiv.org/abs/2602.08316)
- [SWEZZE](https://arxiv.org/abs/2603.28119)
- [CodeCompass](https://arxiv.org/abs/2602.20048)
- [Formal Architecture Descriptors](https://arxiv.org/abs/2604.13108)
- [Navigational Thinking](https://arxiv.org/abs/2603.22133)
- [Repository Intelligence Graph (RIG)](https://arxiv.org/abs/2601.10112)
- [CartoGopher](https://arxiv.org/abs/2504.07572)
- [OpenAI: Harness Engineering](https://openai.com/index/harness-engineering/)
- [OpenAI: How OpenAI Uses Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/)
- [OpenAI: Codex Security](https://help.openai.com/en/articles/20001107-codex-security)
- [OpenAI: PLANS.md Cookbook](https://developers.openai.com/cookbook/articles/codex_exec_plans)
- [OpenAI: Datadog Case Study](https://openai.com/index/datadog/)
- [Anthropic: Claude Code Memory](https://code.claude.com/docs/en/memory)
- [Anthropic: Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Anthropic: Advanced Patterns PDF](https://resources.anthropic.com/hubfs/Claude%20Code%20Advanced%20Patterns_%20Subagents%2C%20MCP%2C%20and%20Scaling%20to%20Real%20Codebases.pdf)
- [Anthropic: Scaling Agentic Coding](https://resources.anthropic.com/hubfs/Scaling%20agentic%20coding%20across%20your%20organization.pdf?hsLang=en)
- [AGENTS.md Empirical Study](https://assets.empirical-software.engineering/pdf/jaws26-agents.md-efficiency.pdf)
- [Aider: Repository Map](https://aider.chat/docs/repomap.html)
