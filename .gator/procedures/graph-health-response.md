# Procedure: Graph Health Response

## Who Runs This

The **enforcer** (Sonnet-class or equivalent) after running `graph_health.py --json`. The enforcer proposes fixes on a maintenance branch. The chat agent (with the human present) reviews and merges.

This procedure is also used by the **Crawler** background operator when automated.

## Trigger

Run this procedure when:
1. The enforcer runs a scheduled or manual audit
2. The Crawler runs as a background operator
3. The human requests a graph health check

## Step 1: Run the health check

```bash
python src/gator_command/scripts/graph_health.py --json docs/wiki/graph-health.json --image docs/wiki/thread-graph.png
```

Read the JSON output. The model is `v2.1-subway` with 5 scored dimensions.

## Step 2: Triage by dimension

Each dimension has a threshold band. Green = no action. Yellow = flag in report. Red = propose specific fixes.

### Navigability (intra-cluster reachability + soft cross-cluster penalty)

| Band | Score | Action |
|------|-------|--------|
| Green | ≥ 90 | No action. |
| Yellow | 70–89 | Report the intra-cluster violations. Suggest candidate transfer station links. |
| Red | < 70 | Propose specific links to resolve intra-cluster violations. Prioritize by hop distance (worst first). |

**How to fix**: Add a connection between two threads in the same cluster that are >3 hops apart. The connection must be semantically genuine — annotate *why* the link exists. If no genuine semantic bridge exists, note this as a legitimate multi-interest gap (the multi-interest principle) and do not force an artificial connection.

**Cross-cluster violations**: These are informational. Do not propose fixes for cross-cluster distances unless overall navigability drops below 70. The graph is a multi-interest personal network, not a fully connected mesh.

### Resilience (bridge edges)

| Band | Score | Action |
|------|-------|--------|
| Green | 100 | No action. |
| Yellow | 70–99 | Report bridge edges. Propose one redundant path per bridge. |
| Red | < 70 | Propose redundant paths for all bridges. This is urgent — a single deletion could disconnect the graph. |

**How to fix**: For each bridge edge A ↔ B, find a third thread C that is semantically related to both A and B. Add connections A → C and/or C → B so the bridge is no longer the only path. Prefer connections that are semantically real over graph-engineering shortcuts.

### Connectivity (intra-cluster + global orphans)

| Band | Score | Action |
|------|-------|--------|
| Green | ≥ 80 | No action. |
| Yellow | 50–79 | Report intra-cluster orphans. Suggest which cluster neighbor should link to them. |
| Red | < 50 | Propose specific inbound links for all intra-cluster orphans. |

**How to fix**: For each intra-cluster orphan, find the thread within the same cluster that is most semantically related and add an inbound link from that thread. One inbound link per orphan is sufficient.

**Scoring**: Intra-cluster orphans cost 20 points each (breaks local navigation). Global-only orphans cost 10 points each (a thread that has inbound from other clusters but not from its own).

### Efficiency (edge redundancy ratio)

| Band | Score | Action |
|------|-------|--------|
| Green | ≥ 80 (ratio 30–60%) | No action. |
| Yellow (sparse) | ratio < 30% | Flag fragile tree structure. Suggest adding redundant paths to critical routes. |
| Yellow (noisy) | ratio 60–75% | Flag over-linked threads. List the threads with the most redundant connections. |
| Red (noisy) | ratio > 75% | Propose specific pruning candidates. List redundant edges sorted by easiest to prune (alt distance = 2 hops). |

**How to fix over-linking**: Identify threads with the highest redundant edge count. For each, keep only connections that represent the strongest semantic relationships — those that a human would want as "see also" exits. Prune connections where both endpoints are already within 2 hops via stronger paths.

**How to fix sparsity**: Identify nodes with degree ≤ 2 that are not leaf-by-design (application sub-threads, etc.). Add one connection to a semantically related neighbor.

**The pruning rule**: Pruning removes outbound links from `## Connections` sections. Before removing a link, verify:
1. The link is redundant (endpoints within 2 hops via other paths)
2. The link is not an essential edge (>2 hops without it)
3. Removing it does not create an orphan or bridge
4. The thread retains enough outbound links for human navigation (minimum 2)

### Legibility (peripheral access to hubs)

| Band | Score | Action |
|------|-------|--------|
| Green | ≥ 90 | No action. |
| Yellow | 70–89 | Report stranded peripherals. Suggest hub connections. |
| Red | < 70 | Propose specific links from stranded peripherals to their nearest high-betweenness hub. |

**How to fix**: A peripheral node (degree ≤ 3) that cannot reach any hub within 2 hops needs a connection to a high-betweenness node. Prefer the hub that is most semantically related, not the closest by graph distance.

## Step 3: Produce the report

Write findings to a report file following the enforcer audit report format:

```
docs/reports/YYYY-MM-DD-graph-health-response.md
```

Include:
- The v2.1 health score and per-dimension breakdown
- Cluster summary (names and sizes)
- Specific findings per dimension (only yellow/red bands)
- Proposed fixes with semantic justification for each
- Any multi-interest-principle notes (legitimate gaps, do not force)

## Step 4: Propose fixes (Crawler mode)

When running as the Crawler (not a read-only audit):

1. Create a maintenance branch from `dev`
2. Apply proposed fixes (add/remove connections in thread files)
3. Re-run `graph_health.py --json` to verify improvement
4. Open a PR to `dev` with the report as the PR body
5. Never merge without human review

## Principles

**Semantic integrity over graph score.** Every connection must be semantically genuine. A high health score achieved through artificial links is worse than a lower score with honest connections. The annotation on each link must explain *why* the link exists, not just that it improves a metric.

**The multi-interest principle.** A personal Memex serves multiple unrelated interests. A thread about family history has no natural bridge to a thread about Fourier analysis, and that is fine. Do not penalize legitimate multi-interest gaps. When Louvain places unrelated threads in the same cluster, note the artifact and move on.

**Pruning is a proposal, not an action.** The enforcer and Crawler propose pruning candidates. Only the chat agent (with human present) executes pruning. This is because pruning removes human-navigable "see also" links that may have value beyond graph topology.

**Minimum outbound rule.** No thread should have fewer than 2 outbound connections after pruning. A thread with 1 connection is a dead end for human navigation even if the undirected graph is connected.

**Directed vs. undirected.** The health model evaluates an undirected graph (structural analysis). But humans and renderers navigate directed links (the `## Connections` section). When proposing fixes, consider both: does the fix improve the undirected structure AND maintain useful directed navigation?

## Connections

→ [enforcer-audit.md](enforcer-audit.md) — the enforcer runs this procedure as part of or after a standard audit
→ [thread-lifecycle.md](thread-lifecycle.md) — pruning and adding connections must follow lifecycle rules
→ [tooling-roadmap.md](../reference-notes/tooling-roadmap.md) — Crawler operator uses this procedure
→ Constitution: graph connectivity is an invariant (Watts-Strogatz navigability, 3-hop rule)
