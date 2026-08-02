# Example: tinyagent Memex Instance

A fully populated Memex instance is preserved at git tag `v1-tinyagent-example`. It demonstrates the complete architecture in action for a small Python coding project ("tinyagent" — a minimal Claude-API coding assistant).

## How to View It

```bash
git checkout v1-tinyagent-example
```

## What You'll See

- **identity.md** — a fictional Architect persona ("Ren") with working style, interests, disposition
- **mission.md** — tinyagent's mission, scope boundaries, success criteria
- **roadmap.md** — prioritized feature list with status tracking
- **7 active threads** — agentic loop failure modes, context budget economics, tool grain size, error recovery, session continuity, ask-vs-act thresholds, tool schema ergonomics
- **4 lightweight threads** — history compaction, prompt caching, streaming, subprocess sandboxing
- **5 module charters** — agent-loop, context-budget, tools, infrastructure, cross-cutting (with TRIPWIREs)
- **15 artifacts** — design decisions, hostile reviews, formal models, pivot records
- **19 reference notes** — essays on adversarial review, knowledge systems, agent performance, the role of git, plus vocabulary guides and a syllabus
- **docs/** — systems documentation (architecture, tool protocol, context manager), enforcer audit reports, crawler reports
- **wiki/** — auto-generated wiki render from thread summaries
- **tinyagent/** — the actual Python code the charters describe

This is what a Memex looks like after sustained use. The current clean state is where you start. The tag is where you're headed.

```bash
git checkout dev   # return to clean state
```
