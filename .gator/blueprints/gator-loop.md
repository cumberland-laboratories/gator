# Gator Loop

## What This Page Is

This page explains how to run a gator loop — the governed planning debate between two AI models. It covers the end-to-end flow from the Architect's perspective: setup, launch, monitoring, model orientation, and what to expect.

If the Architect asks "how do I actually use gator loop?" this page should answer it.

## Core Position

The gator loop is the first multi-agent governance primitive in Gator. It mediates a structured debate between a draftor model and a reviewer model, producing an implementation plan that has been challenged and refined before any code is written.

The key design choices:

- **CLI-mediated**: models do not talk to each other. They submit artifacts through the CLI. The CLI enforces turn-taking, timeouts, and role boundaries.
- **File-based handoff**: the plan and findings are markdown files in `.gator/loops/<loop-id>/`. Any model that can read files and run shell commands can participate.
- **Vendor-agnostic**: works with Claude Code, Codex, Gemini, or any AI CLI. The orientation is built into all three entry points (CLAUDE.md, AGENTS.md, GEMINI.md).
- **Bounded**: max rounds and turn timeouts prevent runaway loops. Escalation pauses the clock for human intervention.
- **No autonomous Git commits**: the loop leaves durable residue. The Architect decides when and whether to commit it.

## What You Need Before Starting

1. **A feature slug** — a short identifier like `dashboard-html-preview` or `session-block-recovery`
2. **A sketch file** — a markdown file describing what you want built. This is the scope contract. Models cannot exceed what the sketch describes. The sketch can be brief (a few paragraphs) or detailed (a full design sketch) — the draftor will expand it into a plan.
3. **Two terminal sessions** — one for each model. The Architect can also open a third terminal for monitoring (`gator loop tail`).
4. **Models that can run shell commands** — Claude Code, Codex CLI, Gemini CLI, or any agent that can execute `gator loop` subcommands.

## The Flow: Step By Step

### 1. Write the sketch

Create a markdown file anywhere in the repo. This is your scope document.

```markdown
# Feature: Dashboard HTML Preview

Render .html files in a sandboxed iframe in the Repo view.
Only static HTML — no JavaScript execution.
Must work with the existing file sidebar selection model.
```

The sketch is the Architect's voice in the loop. It's what both models measure against. Keep it honest about scope — if something is out of scope, say so.

### 2. Start the loop

From the repo root (in your monitoring terminal):

```
gator loop start --feature dashboard-html-preview --sketch path/to/sketch.md
```

Optional flags:
- `--max-rounds 3` (default: 3 revision rounds before the loop stops)
- `--turn-timeout 300` (default: 300 seconds / 5 minutes per turn)

The host process prints a banner with two tokens and enters watch mode:

```
  gator loop

  Loop: dashboard-html-preview-2026-07-26T14-30-00Z
  Feature: dashboard-html-preview
  Max rounds: 3
  Turn timeout: 5m

  -- Tokens ------------------------------------------------

  DRAFTOR:
    gator loop status --token glp_ZGFzaGJv...

  REVIEWER:
    gator loop status --token glp_ZGFzaGJv...

  -- Watching -----------------------------------------------

  [14:30:01] loop started
  next: draftor (plan_drafting)
  waiting...
```

This terminal stays open for the duration of the loop. It shows every event in real time.

### 3. Orient the draftor model

Open a Claude Code / Codex / Gemini session. Give the model its token.

**Claude Code** (has the slash command):
```
/loop-join glp_ZGFzaGJv...
```

**Codex / Gemini** (follow the entry point instruction):
```
I'm giving you a gator loop token. Follow the "gator loop join" instructions
in your entry point. Your token is: glp_ZGFzaGJv...
```

The model should:
1. Read `procedures/gator-loop-protocol.md` (the behavioral contract)
2. Run `gator loop status --token <token>` (sees it's the draftor, it's their turn)
3. Read the sketch from the loop directory
4. Write a plan and submit it

What the Architect sees in the host terminal after the draftor submits:

```
  [14:33:15] draft submitted (round 0)
  next: reviewer (plan_review)
  waiting...
```

### 4. Orient the reviewer model

Open a second AI session. Give it the reviewer token using the same approach.

The reviewer should:
1. Read the protocol
2. Run status (sees it's the reviewer, it's their turn)
3. Read the plan at `plan.current.md`
4. Read the sketch at `sketch.md` to verify scope compliance
5. Write findings and submit — or approve if the plan is ready

### 5. The revision cycle

If the reviewer submits findings (not approval), the draftor gets another turn:

```
  [14:38:22] revision requested (round 1)
  next: draftor (plan_revision)
  waiting...
```

The draftor reads `findings.current.md`, revises the plan, submits again. The reviewer reviews again. This continues until:

- **Approval**: the reviewer submits with `--approve`. Loop ends successfully.
- **Max rounds**: the revision limit is reached. Loop ends, residue shows how far the debate got.
- **Timeout**: a model doesn't submit in time. Loop ends with `turn_timed_out`.

### 6. Escalation (when needed)

If either model gets stuck — scope is unclear, fundamental disagreement, missing information — they escalate:

```
gator loop escalate --token <token> --reason "Sketch is ambiguous about X"
```

The host terminal shows:

```
  [14:41:00] ESCALATED (Sketch is ambiguous about X)
  blocked — waiting for Architect (gator loop unblock)
```

The loop pauses. No timeout runs. The Architect reads the reason, thinks about it, and unblocks when ready — with an optional message that the resuming model will see in their next status check:

```
gator loop unblock --loop dashboard-html-preview-2026-07-26T14-30-00Z --message "Yes, check the website. Use the v2 API docs."
```

The model's next `gator loop status` will show:

```
  Architect message: Yes, check the website. Use the v2 API docs.
```

The message is cleared after the model submits, so it doesn't persist into later turns. The Architect can also override who goes next:

```
gator loop unblock --loop <id> --stage plan_drafting --next-role draftor --message "Start over with the revised scope."
```

### 7. After the loop ends

The host terminal prints a summary and exits:

```
  [14:45:33] plan APPROVED (round 2)

  -- Summary ------------------------------------------------

  Feature: dashboard-html-preview
  Result: plan_approved
  Rounds: 2/3
  Turns: 5
  Residue: .gator/loops/dashboard-html-preview-2026-07-26T14-30-00Z

  Session files remain for inspection. No Git commit was made.
  -----------------------------------------------------------
```

The loop directory contains everything:

| File | Contents |
|------|----------|
| `session.json` | Full session state, all turns, metadata |
| `events.jsonl` | Complete event log |
| `sketch.md` | The original scope document |
| `plan.current.md` | The final approved plan |
| `findings.current.md` | The last reviewer submission |

No Git commit was made. The Architect decides what to do:
- Read the plan, use it to guide implementation
- Commit the loop residue as an artifact
- Discard it if the loop wasn't useful

## Monitoring

### From the host terminal

The `gator loop start` process shows events as they happen. This is the primary monitoring surface.

### From a second terminal

```
gator loop tail --loop <loop-id>
```

Follows events.jsonl in real time. Useful if the Architect wants to watch from a different terminal than where the host is running.

### Listing all loops

```
gator loop list
```

Shows all loop sessions, their stage, round, and whether blocked.

## What Can Go Wrong

| Situation | What happens | What to do |
|-----------|-------------|------------|
| Model doesn't read the protocol | Submits garbage or edits files directly | Re-orient the model. The protocol is at `procedures/gator-loop-protocol.md` |
| Model times out | Loop enters `turn_timed_out` terminal state | Start a new loop with a longer `--turn-timeout` |
| Max rounds exhausted | Loop enters `max_rounds_exceeded` | Read the final plan + findings. Either increase `--max-rounds` in a new loop, or accept the plan as-is |
| Model escalates | Loop pauses, Architect decides | Read the reason, resolve it, `gator loop unblock` |
| Wrong model gets wrong token | Draftor tries to review or vice versa | CLI rejects: "requires role 'draftor', got 'reviewer'" |
| Model edits loop files directly | Overwrites are lost on next submit | CLI is the only authorized writer. Remind the model of Rule 2 |

## What This Does NOT Cover

- **Code implementation loop** — this is planning only. The plan is the output, not code.
- **Dashboard integration** — loop status is not (yet) visible in the dashboard.
- **Auto-launching agents** — the Architect manually starts each model session.
- **More than two roles** — draftor and reviewer only for now.
- **Deep policy/charter integration** — the loop doesn't enforce charter reads mid-debate.

## Architecture Notes

The loop is a state machine with 7 states (3 active, 1 paused, 3 terminal). Concurrency between submit commands and the host's timeout enforcer is handled by an exclusive file lock with read-after-acquire discipline. Session state is always saved before events are emitted (write ordering invariant).

For internal details: [Loop Charter](../charters/scripts-loop.md). For the implementation plan: [2026-07-25 Implementation Plan](../artifacts/2026-07-25-gator-loop-implementation-plan.md).

## Connections

-> [Loop Protocol](../procedures/gator-loop-protocol.md) — what models read when joining
-> [Loop Charter](../charters/scripts-loop.md) — module ownership, TRIPWIREs, function map
-> [Implementation Plan](../artifacts/2026-07-25-gator-loop-implementation-plan.md) — design rationale, resolved choices
-> [Installer Charter](../charters/scripts-installer.md) — cross-vendor orientation via entry points
