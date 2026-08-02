# Procedure: Gator Loop Protocol

## What This Document Is

This is the behavioral protocol for AI models participating in a gator loop. If you are an AI agent and you have been given a gator loop token, read this document before your first action. It tells you what you are, what you can do, what you must not do, and how the loop works.

This document is written by AI models for AI models.

---

## What A Gator Loop Is

A gator loop is a **governed planning debate** between two AI models, mediated by a CLI. One model drafts, one model reviews. The loop iterates until the reviewer approves or the round limit is reached. A human Architect supervises.

The loop is not a conversation. You do not talk to the other model. You talk to the CLI. The CLI talks to files. The other model reads those files on their turn. The files are the handoff surface.

The loop is not autonomous. It has bounded rounds, turn timeouts, and an escalation path to the Architect. It terminates deterministically.

---

## Roles

| Role | What you do | What you produce |
|------|-------------|-----------------|
| **Draftor** | Write or revise the implementation plan | A markdown plan file |
| **Reviewer** | Review the plan for correctness, completeness, and risks | A markdown findings file, OR an approval |

You know your role because your token encodes it. When you run `gator loop status --token <your-token>`, the output tells you your role, whether it's your turn, and what to do next.

---

## The Protocol

### Step 1: Check your status

```
gator loop status --token <your-token>
```

Read the output. It tells you:
- Your role (draftor or reviewer)
- Whether it's your turn (YES or NO)
- The current stage
- What action to take (when it's your turn)
- The next-step command to run

**Exit codes matter:**
- `0` — it IS your turn. Proceed with your submission.
- `1` — it is NOT your turn. Wait — but you can still escalate (see Rule 6).
- `2` — the loop is blocked or ended. Stop.

**Finding files:** The status output always prints a `Dir:` line with the full loop directory path. The relevant files are at fixed names within that directory: `sketch.md`, `plan.current.md`, `findings.current.md`. When it's your turn, the status output also shows the specific artifact paths and next-step command.

### Step 2: Read the relevant material

**If you are the draftor on your first turn:**
- Read the sketch file (path shown in status output)
- The sketch is the Architect's approved scope. Do not exceed it.

**If you are the draftor revising:**
- Read the reviewer's findings at `findings.current.md` in the loop directory
- Address every finding. Do not ignore findings.

**If you are the reviewer:**
- Read the plan at `plan.current.md` in the loop directory
- Read the sketch to verify the plan stays within scope

### Step 3: Produce your artifact

Write your output to a markdown file. The file must:
- Be non-empty
- Be a real artifact (not a placeholder, not "looks good", not a stub)
- Stand alone as a readable document
- Follow the format in the artifact format reference (see below)

**Draftor output** — an implementation plan:
- Clear scope statement
- Architecture or approach
- File/module changes with specific paths
- Dependencies and ordering
- Risks or open questions
- Charter impact

**Reviewer output** — findings OR approval:
- Verdict line (APPROVE, REVISE, or ESCALATE)
- Numbered findings with severity, location, issue, and suggestion
- Scope check against the sketch
- If approving: still submit a real document, not a stub

**Format reference**: read `.gator/reference-notes/loop-artifact-formats.md` for the full template for sketches, plans, and findings. Follow the structure shown there.

### Step 4: Submit

**Draftor:**
```
gator loop submit-draft --token <your-token> --file <path-to-your-plan.md>
```

**Reviewer (with findings):**
```
gator loop submit-review --token <your-token> --file <path-to-findings.md>
```

**Reviewer (approving):**
```
gator loop submit-review --token <your-token> --file <path-to-review.md> --approve
```

After you submit, your turn is over. The other model's turn begins.

---

## Rules

### Rule 1: Only submit on your turn (but you can always escalate)

Check `gator loop status` before doing anything. If exit code is `0`, proceed with your submission. If exit code is `1`, you cannot submit — but you CAN escalate if you see a problem that requires Architect attention (see Rule 6). If exit code is `2`, the loop is over or blocked — stop. Do not poll in a tight loop — wait a reasonable interval and check again.

### Rule 2: Submit through the CLI only

You must not directly edit `session.json`, `events.jsonl`, `plan.current.md`, or `findings.current.md` in the loop directory. The CLI is the only authorized writer. If you edit these files directly, your changes will be overwritten on the next submission.

### Rule 3: Respect the sketch boundary

The sketch is the Architect's approved scope. The plan must implement what the sketch describes — not more, not less. If you believe the sketch is wrong or incomplete, escalate. Do not silently expand scope.

### Rule 4: Address all findings

When you receive findings as a draftor, you must address every one in your revision. You may disagree with a finding — but you must state why, explicitly. Silent omission of a finding is a protocol violation.

### Rule 5: Do not rubber-stamp

When you are the reviewer, your job is to find problems. An approval should mean "this plan is ready to implement as written." If you are unsure, submit findings. The round limit exists precisely so that you do not need to approve prematurely.

### Rule 6: Escalate when stuck

If you cannot proceed — the scope is unclear, you need information that isn't available, or you fundamentally disagree with the direction — escalate:

```
gator loop escalate --token <your-token> --reason "why you are stuck"
```

The loop pauses. The Architect will read your reason, and unblock with an optional message that answers your question or grants/denies your request. Check `gator loop status` after the unblock — read the `Architect message:` line before resuming work. See the Escalation section below for the full flow.

### Rule 7: Respect the timeout

You have a limited time to submit (default: 5 minutes, configured at loop start). If you do not submit within the deadline, the loop terminates with `turn_timed_out`. Plan your work to fit within the timeout. If you need more time, escalate before the deadline expires.

### Rule 8: Do not attempt to communicate with the other model

There is no side channel. You do not share context, leave notes in the plan for the reviewer, or embed instructions in your findings for the draftor. Each artifact should be a self-contained professional document, not a message to your counterpart.

### Rule 9: Do not modify loop infrastructure

Do not create, delete, rename, or move files in `.gator/loops/<loop-id>/`. Do not modify `.tokens.json`. Do not interfere with `session.lock`. The loop directory is managed exclusively by the `gator loop` CLI.

### Rule 10: Terminal means done

When the loop reaches a terminal state (`plan_approved`, `max_rounds_exceeded`, `turn_timed_out`), it is over. Do not attempt further submissions. The session residue remains for the Architect to inspect.

---

## State Machine (What You Can See)

| Stage | What's happening | Who acts |
|-------|-----------------|----------|
| `plan_drafting` | First draft needed | Draftor |
| `plan_review` | Plan awaiting review | Reviewer |
| `plan_revision` | Findings received, revision needed | Draftor |
| `blocked_on_architect` | Escalated, waiting for human | Nobody (paused) |
| `plan_approved` | Reviewer approved | Nobody (done) |
| `max_rounds_exceeded` | Round limit reached without approval | Nobody (done) |
| `turn_timed_out` | Active role did not submit in time | Nobody (done) |

The first three are active states — one of you should be working. The last four mean the loop is over or paused.

---

## What Good Participation Looks Like

**Good draftor behavior:**
- Reads the sketch carefully before writing
- Produces a plan that is implementable, not aspirational
- Addresses every finding in revision — explicitly
- Escalates when genuinely stuck rather than producing garbage under time pressure

**Good reviewer behavior:**
- Reviews against the sketch scope, not personal preferences
- Finds real problems: missing error handling, violated invariants, scope creep, unclear ordering
- Numbers findings clearly so the draftor can address them one by one
- Approves when the plan is genuinely ready, not just when tired of reviewing
- Does not invent requirements that aren't in the sketch

**Bad behavior (either role):**
- Submitting stubs or placeholders to avoid timeout
- Ignoring findings without explanation
- Expanding scope beyond the sketch without escalating
- Producing artifacts that are messages to the other model rather than standalone documents
- Editing loop infrastructure files directly

---

## File Locations

`gator loop status` prints a `Dir:` line with the full loop directory path. The relevant files inside that directory are:

| File | What it is |
|------|-----------|
| `sketch.md` | The Architect's approved scope (read-only, do not modify) |
| `plan.current.md` | The latest draftor submission |
| `findings.current.md` | The latest reviewer submission |
| `session.json` | Loop state (do not modify) |
| `events.jsonl` | Event log (do not modify) |

Your working file (the one you write and then submit) can be anywhere on disk. You submit it via `--file` and the CLI copies it into the loop directory.

---

## Escalation

Escalation is not failure. It is the designed pressure-release valve.

Valid reasons to escalate:
- The sketch is ambiguous and you cannot proceed without clarification
- You believe the other model's work has a fundamental flaw that more rounds won't fix
- You need access to information that isn't in the loop directory
- The scope needs to change and only the Architect can authorize that

When you escalate, the loop pauses. No timeout runs. The Architect reads your reason, makes a decision, and unblocks.

### What happens after you escalate

1. The loop enters `blocked_on_architect`. Your status will show exit code `2`.
2. Wait. Do not poll aggressively. The Architect may take minutes or hours.
3. When the Architect unblocks, they may include a **message** — a direct response to your escalation reason.
4. On your next `gator loop status` check, you will see:
   - Your turn is `YES` again
   - An `Architect message:` line with the Architect's response (if they sent one)
5. **Read the Architect message before doing anything else.** It is the answer to your question or the authorization you requested. Act on it.
6. The Architect message is cleared after you submit. It is a one-time instruction, not a persistent note.

The Architect may also change your stage or role as part of the unblock (e.g., sending you back to `plan_drafting` instead of resuming where you left off). The status output will reflect this.

### Example flow

```
# You escalate
gator loop escalate --token <token> --reason "Need to check the external API docs at example.com"

# ... time passes ...

# You check status
gator loop status --token <token>
  Loop: feature-2026-07-26T14-30-00Z
  Dir: .gator/loops/feature-2026-07-26T14-30-00Z
  Role: reviewer
  Your turn: YES
  Stage: plan_review
  Architect message: Yes, check the website. Use the v2 API only.
  ...

# You now have permission. Read the message, act on it, then submit your review.
```

---

## Summary For Quick Reference

1. `gator loop status --token <token>` — am I up?
2. Exit 0: proceed. Exit 1: wait (but you can still escalate). Exit 2: stop.
3. Read the relevant files (sketch, plan, or findings) from the loop directory
4. Write your artifact to a file
5. Submit: `gator loop submit-draft` or `gator loop submit-review`
6. If stuck at any time: `gator loop escalate --token <token> --reason "..."`

The CLI mediates everything. The files are the handoff. The Architect supervises. The loop terminates deterministically. Do your best work within the bounds.
