---
date: 2026-08-25
type: exploration
topic: dashboard-concierge
status: brainstorm
model: claude-opus-4-7
---

# Dashboard Concierge — Exploration (brainstorm)

## Thesis in one line

**Don't rebuild the intelligence. Borrow the AI the user is already running in the repo.**

Every Gator user is already sitting in front of a gatorized AI CLI — Claude Code, Codex, or Gemini — that has read the constitution, knows the charter layer, and can grep and read the codebase on demand. The Dashboard concierge's job is to be a good conduit into that intelligence, not a competing brain. The [super-chatbot design](../vault/artifacts/../../../cl-strategy/.gator/artifacts/2026-08-21-super-chatbot-design.html) solves a different problem shape (thousands of unfamiliar documents, users whose vocabulary doesn't match the docs, no curated map). Gator has the curated map. The concierge is the *last mile*, not the whole stack.

## What "the gatorized AI model" actually means here

Not a hosted model Gator provisions. Not an API key we hold. **The AI process the user has open in their terminal, right now, pointed at this repo.** That process already:

- Read the constitution at `gator init` (so it knows the workflow)
- Read the module charters relevant to the surface it was asked about
- Has full filesystem read via its own tools (`Read`, `Grep`, `Glob`, MCP, whatever the CLI ships with)
- Has whatever governance the user has configured (allowlist, hooks, MCP surfaces)

That is a very rich substrate. Gator's job is to give it a clean question and a clean way to route the answer back.

## The design space (three axes)

### Axis 1 — where does intelligence live?
Almost certainly the user's existing CLI. Options that put intelligence *inside* the Dashboard (own model, own key, own tool loop) buy us billing surprise, key handling, model-choice work, and a competing agent that has to be kept aligned with what the user's CLI already believes. Skip.

### Axis 2 — how does the Dashboard hand off to that CLI?
This is the interesting axis. Four candidates, ordered from cheapest to most integrated:

1. **Clipboard handoff.** Dashboard button composes a scoped prompt (charter refs + question) and drops it on the clipboard. User pastes into their CLI. Zero infra. Works with every CLI on day one. Feels janky because it is.
2. **Non-interactive subprocess.** Dashboard spawns `claude -p "..."` (or Codex / Gemini equivalent) with the scoped prompt, streams output back into a Dashboard panel. Real inline UX. Requires we detect which CLI the user has installed, respect model settings, and handle streaming. Assume the executables are on `PATH` and have non-interactive modes; verify per vendor before committing.
3. **MCP server.** Gator ships its own MCP server exposing tools like `charter_for(path)`, `list_charters()`, `blueprint_l1()`, `drift_findings()`, `search_charters(query)`. The user attaches it once in their CLI config. The chat then happens naturally *in the CLI*, not in the Dashboard — the CLI gets Gator-shaped answers because it can call Gator-shaped tools. This is roadmap item "MCP server" (currently Considering) — it slots in exactly here. Dashboard doesn't need a chat panel at all under this model; it stays a read-only inspection surface, and questions live where the user was already going to ask them.
4. **Named session / IPC.** Dashboard sends the prompt directly into a running CLI session over some IPC channel. Nice in theory. Needs each CLI to expose such a channel. Probably not there today; not worth waiting for.

**Personal read**: `1 + 3` together is probably the sweet spot. Clipboard for zero-friction day-one; MCP as the strategic bet. `2` is where the polish is but also where the vendor-specific brittleness lives.

### Axis 3 — what job does the concierge do?
- **(A) Product concierge** — "what does the drift badge mean, what does `gator init` do." Static help, largely.
- **(B) Codebase Q&A** — "why does this function exist," "what would break if I renamed it," "which module owns this behavior." Where charters actually pay off.
- **(C) Governance actions** — "add to inbox," "draft a charter update." Turning the read-only Dashboard into a write surface. Big blast-radius jump. Separate conversation.

Aim at **B** first. That's the workbench the vault reviews keep pointing at, and it's the payoff that ties directly to Blueprints 2.0.

## Interaction sketches

### Sketch A — contextual "Ask about this"
Right-click (or a small `?` chip) on any surface that has a charter behind it: blueprint node, charter file in Repo view, drift finding, function name in Blueprint L3. Opens a modal:

```
Ask about: Fleet Intelligence (charter cluster)

Question: ┌────────────────────────────────────────┐
          │ what happens if I remove              │
          │ gator-repo-status.py?                 │
          └────────────────────────────────────────┘

Prompt preview (auto-composed):
  Read .gator/charters/scripts-fleet-intelligence.md
  and .gator/charters/scripts-cross-cutting.md.
  Answer only from those charters, citing sections.
  Question: what happens if I remove gator-repo-status.py?

[ Copy to clipboard ]  [ Send to Claude Code ]  [ Send via MCP ]
```

Nice property: even if we ship only "Copy to clipboard" in v1, the *prompt-composition* work is what we get to reuse under every other transport later.

### Sketch B — standalone chat panel
Full inline chat, message history, streaming. Higher build cost, higher UX polish. Only worth doing after we've validated Sketch A is the right shape.

### Sketch C — MCP-first (Dashboard doesn't chat at all)
Dashboard stays read-only. Ships an MCP server + a docs page explaining "attach this to your CLI." Chat happens in the CLI the user already has open. Dashboard's contribution: authoritative Gator-shaped tools (charter lookup, blueprint queries, drift, audit surface) that the CLI can call. Cheapest strategic surface. Least in-Dashboard UX. Composes with Sketch A cleanly — the "Ask about this" affordance in the Dashboard can shell out via MCP too.

## What we hand the model along with the question

The moment we're composing prompts on the user's behalf, we get to decide what context we pre-load. This matters more than the transport:

- **Always**: `.gator/charters/scripts-cross-cutting.md` (the epistemically-first read, per the [charter-first heuristic](../vault/artifacts/2026-08-14-charter-first-code-understanding-heuristic.md)).
- **Surface-dependent**: the charter for the currently-viewed thing (Fleet → all charters via INDEX summary; Repo file → the charter that covers that file; Blueprint L1 node → that cluster's charter).
- **When drilling**: for L2 cluster views, also the charters of directly-connected clusters (the `→` edges from the L1 map).
- **Never automatically**: source files. Let the model decide when to read them. The whole point of charters is that reading them first is cheaper and more accurate than opening code.

## Bounded vs open

Two prompt-mode presets worth having:

- **Grounded** — "Answer only from the charters listed above. If the answer is not present, say so and identify the missing charter surface." Perfect for the "explain this" and "what does X own" family. Doubles as a *charter-gap detector*: if the model has to abstain, the concierge quietly logs that as a drift/gap signal for L4.
- **Open** — "You may read any file. Cite what you read." For "what would break if I renamed X" and other traversal questions where the charter surface is the *entry point*, not the whole answer.

Default to Grounded. Let the user promote to Open explicitly.

## What to steal from the super-chatbot doc (short list)

- **Provenance per answer.** Every response cites `charter#section` (and file:line if it opened source). Non-negotiable — matches Gator's Git-native evidence ethos.
- **Abstention as first-class.** "Not in the charter layer" is a valid answer AND a valuable signal. Feeds Blueprints 2.0 L4.
- **L4 flow-memory idea, adapted.** Not "learned retrieval edges," but "which regions of the codebase people keep asking about." That's a charter-underspecified-region detector. Cheap to collect, potentially high-signal.

## What we don't copy, and why

- **Async learning loop.** The loop's whole point is fixing metadata that starts bad. Ours starts good and human-reviewed.
- **Layered edge lifecycle (proposed → verified → active → stale).** Same reason. We don't need to learn retrieval edges from usage when we already have declared cross-charter edges.
- **Negative edges, versioned learned-index, quarantine tiers.** Solving a problem we don't have.
- **Custom vector store.** Overkill at charter-layer scale (dozens of files, not thousands).

## Governance considerations (light pass)

- **Read-only is easy.** The concierge reads files the user could already read. No new trust surface.
- **Any write action goes through the normal Gator commit flow.** No silent edits from concierge conversations — same rule as any other AI edit in the repo.
- **Logging.** Worth thinking about: log Q&A pairs (question + which charters were loaded + whether the model abstained) to `.gator/concierge/` for later gap analysis? Or leave conversations ephemeral? Trade-off is real: capture enables the L4-flow-memory pattern above, but it also creates a new gitignored surface with question text in it. Probably start ephemeral, add opt-in capture later.

## Open questions to think about (no forcing function)

1. **Does MCP composition let us skip a Dashboard chat panel entirely?** If the answer is yes for the codebase-Q&A case, the Dashboard concierge might reduce to (a) an MCP server + (b) "Ask about this" buttons that push a prompt into whatever CLI is open. Elegant. Under-scoped? Not sure yet.
2. **Which CLI(s) do we support first?** Claude Code has the deepest MCP support and non-interactive `-p` mode. Codex and Gemini are catching up but vary. Vendor-neutrality is a Gator value; matching Gator's install stance ("we compose with whatever AI framework you're already using") suggests we build clipboard-first and MCP-first and let the vendor detail sort itself.
3. **Does concierge belong on the Blueprints 2.0 workbench specifically, or Dashboard-wide?** Both, probably — but the initial "Ask about this" affordance likely lives on Blueprint nodes and Repo-view charter files. Fleet and Audit views can add it opportunistically.
4. **Gap capture — worth it?** If we don't log questions, the "which regions get asked about" signal never accumulates. If we do log, we've quietly created a per-repo file that captures what the Architect was confused about. Small privacy consideration; small governance question.
5. **When does a full inline chat panel become worth building?** Probably after the buttons + MCP have run for a while and there's evidence users want the conversation surface, not just the answer. Deliberately not scoping it now.

## Where this touches Blueprints 2.0

The concierge is a *complementary* input to the same inspection workbench, not a re-scoping of it. Concrete touchpoints:

- L1/L2 nodes get "Ask about this" chips.
- L4 drift/gap surfaces get concierge-abstention data (when it exists).
- The prompt composer reuses the same charter-loading logic the L1 renderer uses (single source of truth for "which charters describe this surface").

The Blueprints 2.0 plan does not need to change today. When we're ready to commit direction on Axis 2 (transport), the plan can absorb a §11 that references this exploration.

## Addendum — the framing that landed (Architect, 2026-08-25)

The frame that made the whole thing click, in the Architect's own words:

> This is truly an **inspection workbench for the Architect**. They can drill into the charters, ask questions about features, and quickly get to inspection of actual code to say *"what is this doing and why"* in conversation with a gatorized AI model. **The same way an engineering manager would do a code review with an engineer.** The difference is the speed and the back-and-forth. Most places are using the PR as a point to do a "code review" — but it is really a *one-sided in-desperation code scan* by the architect in those cases. This is literally the same thing that would be done with a human programmer. The big win: the gatorized AI knows scope and context *way* better than non-gatorized situations.

Three sharpenings this framing forces:

- **The AI's role flips from producer to explainer.** The dominant industry narrative is "AI writes, human reviews the output" — a losing setup for the reviewer, who is checking behind an author who wasn't there. This inverts it: **AI explains, human decides**, grounded in charters the human already reviewed. That is a coherent role for the AI to play (assistive, not autonomous) and a coherent role for the Architect to keep (actually inspecting, not rubber-stamping). It is a much less contested product story than most current AI-coding pitches.

- **PR review is the wrong seam.** The PR became "the code review moment" only because it was the only structural moment the workflow offered. What this workbench enables is inspection at *any* time — before the code exists, while it is being written, at commit, at review, weeks later during a refactor. The seam moves from a moment to a surface. The PR becomes just one entry point among many, not the last-and-only chance.

- **The charter-quality feedback loop closes itself.** If the AI's answers come from charters, then a bad charter produces a bad answer, and the Architect notices *during* their inspection. That is the reinforcement mechanism charters have been missing — they have been an obligation with no immediate payback. Under this framing, every inspection session is also a charter-quality audit at zero extra cost. Charters get better because they are being *used*, not because someone finds time to maintain them.

Long-horizon note: this will take time to build out fully, but the path is now visible. Blueprints 2.0 supplies the semantic surface; the gatorized AI supplies the conversational engineer; the charter layer supplies the shared vocabulary between them. That triangle is what makes this different from "AI chatbot bolted onto a code viewer" and from "yet another PR review tool."

## Addendum 2 — the turn-sized hole (Architect, 2026-08-25)

Second framing that landed, in the Architect's own words:

> Right now, Gator works. The Architect can ask very specific, global/local/project questions, and get spot-on answers from the gatorized AI model. Wonderful. The problem is that **the Architect is peering through a *turn-sized hole*, regarding the entire shape of the code.** The Architect can ask for or inspect pieces, but in the turns there is not a good way to browse the codebase meaningfully. At a high level that is the next step for AI-assisted coding — not just for Gator.

Four sharpenings this framing forces:

- **The chat turn is a query interface, not a browse interface.** You can only ask about what you can name. That makes chat powerful for the *known unknowns* — you already suspect where the problem is, you point, you get a great answer — and structurally useless for the *unknown unknowns* — the module you'd have found on a walk, the tripwire you'd have noticed on a scroll. Every AI-coding product on the market today, ours included so far, has converged on the query surface and skipped the browse surface. Chat won so hard nobody noticed the other half was missing.

- **Browsing generates the questions.** Every time an Architect scrolls a charter map, drills into a cluster, hovers a "does not own" boundary, sees a tripwire badge, they are generating candidate questions that only *become* askable because they saw the surface. Chat can never produce those — the priors are not in the model, they are in the terrain. Browse-then-ask is a fundamentally different loop from ask-then-clarify, and the industry has been running the second loop for two years pretending it is the whole thing.

- **Gator is oddly well-positioned to build the browse surface** — because we have spent the last year building the semantic layer under the guise of governance. Every other tool would have to build the map first, then the browser. We have the map. The browser is a small next step from here, not a category rewrite.

- **The composition is the killer, not either half alone.** Browse to *find the region*; chat to *interrogate the region*. Blueprints 2.0 + concierge is the first product that has both surfaces sharing the same underlying map. That is the thing missing from Copilot Chat, Cursor, Windsurf, Claude Code, Codex, Gemini — every one of them has half. The half that is easier to build.

Restated for the pitch deck: **the industry gave everyone a query interface for their codebase and called it done. Nobody built the browser. Gator can, because charters are the map that makes browsing meaningful — and once you have both surfaces sharing the same map, browse-then-ask is a fundamentally more powerful loop than ask-then-clarify.**

## Addendum 3 — the slow-motion walk (Architect, 2026-08-25)

Third framing moment, and the first named future mode. In the Architect's own words:

> This is a very good place to spend a lot of the next 6 months. So many possibilities, like a **"slow motion" walk by a gatorized AI model through how it ascertains how a feature works in the code, step-by-step, with the Architect.** *"First I read the cross-cutting charter, then..."* — the same way a tutor would explain how to solve a problem. Super-powerful.

Five sharpenings this mode forces:

- **It externalizes the reasoning trajectory.** Today, when an AI answers a codebase question, the Architect sees the *conclusion* but not the *path*. The path is where the intellectual value lives. Slow-motion walk renders each stage of the AI's traversal as a visible, pausable step — the Architect learns the heuristic by watching it applied to real code, not by reading a doc about it.

- **It flips "trust the answer" into "review the method."** The Architect doesn't have to trust the final claim; they see the reasoning steps and can intervene at any one. That is materially stronger governance than the "AI said X, I approve/reject" pattern. It also turns hallucinations into visible slips — a wrong intermediate step is obvious in narration in a way it never is in a polished final answer.

- **It is the charter-first heuristic made operational.** The [2026-08-14 heuristic](../vault/artifacts/2026-08-14-charter-first-code-understanding-heuristic.md) laid out six stages — Orient → Localize → Verify → Expand → Reconcile → Decide — as a *description* of how effective models work. Slow-motion walk converts that description into a *UI*. Each stage becomes a rendered step the Architect can pause, redirect, drill into, or replay. The heuristic stops being documentation and becomes a controllable surface.

- **Tutor mode vs. answer mode is a real UX distinction.** Same underlying capability, two very different presentations. Answer mode: *"The function does X."* Tutor mode: *"Let me walk you through how I'd figure that out — first I'd read the cross-cutting charter to see if X is a global concern, then..."* Both are legitimate; the toggle is context-dependent. New Architects and unfamiliar codebases benefit from tutor mode; experienced Architects flip to answer mode when they just want the result. Same engine, two lenses.

- **It compounds the charter-quality feedback loop.** In slow-motion mode, the AI reads charters *aloud* as part of its walk. Bad prose in a charter gets exposed loudly the moment it's narrated back to the Architect — *"wait, that description doesn't actually match what this function does."* That is an *audible* drift detector, on top of the visual one L4 provides. Charter quality improves because charters are being spoken, not just parsed.

Time-horizon note: 6 months is the right frame. Slow-motion walk sits on top of a real stack — Blueprints 2.0 (browse surface), concierge (chat transport), narration UX, and a settled context-loading strategy. Once those exist, adding narration mode is small: the AI already reasons this way; we render its intermediate steps as visible steps. But the stack under it is what the 6 months buys.

Preservation note: the phrases *"turn-sized hole"* (Addendum 2) and *"slow motion walk"* (this addendum) are the two most citable coinages from today's session. Both are pitch-deck ready; both survive out of context. Keep them intact when this material gets lifted into anything public.

## Connections

→ [Blueprints 2.0 plan](2026-08-25-blueprints-2-0-implementation-plan.md) — the workbench this concierge extends
→ [Super-chatbot design](../../../cl-strategy/.gator/artifacts/2026-08-21-super-chatbot-design.html) — the piece we're deliberately NOT copying wholesale, plus the small parts we are
→ [Charter-first understanding heuristic](../vault/artifacts/2026-08-14-charter-first-code-understanding-heuristic.md) — the loading order the concierge should mirror
→ [Roadmap — MCP server (Considering)](../roadmap.md) — item that this exploration would activate as a strategic play
