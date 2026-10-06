# Procedure: Gator Loop Protocol

## What This Document Is

This is the behavioral protocol for AI models participating in a gator loop. If you are an AI agent and you have been given a gator loop token, read this document before your first action. It tells you what you are, what you can do, what you must not do, and how the loop works.

This document is written by AI models for AI models.

---

## What A Gator Loop Is

A gator loop is a **governed planning debate** between two AI models, mediated by a CLI. One model drafts, one model reviews. The loop iterates until the reviewer approves or the round limit is reached. A human Architect supervises.

The loop is not a conversation. You do not talk to the other model. You talk to the CLI. The CLI talks to files. The other model reads those files on their turn. The files are the handoff surface.

The loop is not autonomous. It has bounded rounds, Architect oversight, and an escalation path to the Architect. It terminates deterministically.

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
- `1` — it is NOT your turn. If you have a genuine Architect-owned blocker, escalate first (see Rule 6); otherwise run `gator loop wait --token <your-token> --max-seconds 45` to wait until the loop becomes actionable.
- `1` also applies while the loop is **paused or blocked on the Architect**: nobody's turn, so wait. Suspension is not the end of the loop (see "Suspension Is Not Departure" below).
- `2` — the loop ended. Stop.

**Waiting is bounded and resumable.** `gator loop wait --max-seconds 45` returns within about 45 seconds so that it fits inside agent tool-call limits. Its exit codes:
- `0` — it is now your turn. Act immediately.
- `3` — still not your turn. **Reissue the same `wait` command right away.** A completed `wait` call does not end your participation in the loop.
- `2` — the loop ended. Stop and report the status.

A paused or blocked loop never ends a `wait`: it keeps waiting, and a bounded `wait` exits `3` at its limit. Reissue it.

Keep reissuing the bounded `wait` until it returns `0` or `2`. Do not tight-poll `status` instead of `wait`. A human can cancel a `wait` command at any time with the normal interrupt.

**Optional: a background watcher (only if your runtime supports it).** If your runtime can run a command in the background *and automatically starts a new turn for you when that command exits*, you may wait with a watcher instead of repeated `wait` calls:

```
gator loop participant watch --token <your-token> --max-seconds 600 --json
```

Launch it in the background. It registers you with the Architect's Dashboard (which shows you as connected, then released), heartbeats, and exits with exactly one JSON line as soon as something happens. When you are re-invoked, read the **last JSON line** of the watcher's output and act on `wake_reason`:
- `0` / `turn_ready` — it is your turn. Run `gator loop status` and act.
- `2` / `terminal` — the loop ended. Stop; do not relaunch.
- `3` / `still_waiting` — nothing yet. Relaunch the same watcher command. The watcher keeps watching through a pause or block (it stays registered); its JSON adds `"suspended": true` when the loop is suspended.
- `2` / `architect_block` — printed only by older watchers. Relaunch the watcher to wait for the unblock.
- `4` / `superseded` — a newer watcher owns your role. Stop.
- `1` / `error` — read the error; fall back to bounded `wait`.

Supported runtime today: **Claude Code**, with the Bash tool's background mode (`run_in_background: true`) while the session stays open (verified on Claude Code 2.1.283). Any runtime that cannot re-invoke you when a background command exits (Codex CLI today) must keep using bounded `wait`. A watcher cannot resume a session that has already ended, it never submits anything for you, and "acknowledged" means only that the watcher received the notification. The Architect may **Re-notify** you; that only sends a new notification and never changes the loop.

**Finding files:** The status output always prints a `Dir:` line with the full loop directory path. The relevant files are at fixed names within that directory: `sketch.md`, `plan.current.md`, `findings.current.md`. When it's your turn, the status output also shows the specific artifact paths and next-step command.

### Step 2: Read the relevant material

**Architect brief (every role, every turn it is listed).** When `gator loop status` lists an `Architect brief: ... [OK] (required reading)`, read `architect-brief.md` in the loop directory before anything else. It is the Architect's must-read guidance for this loop: which charters, decisions, or constraints to honor. It is immutable residue, not a channel; do not reply to it. If status marks it `[!!]` (missing, digest mismatch, unreadable, or an invalid reference), do not rely on it: escalate to the Architect.

**Brief vs. sketch.** The sketch is the approved *scope*; its `## Context` section is optional *background* pointers. The brief is *required reading*. When both exist, the brief governs what you must read; the sketch governs what you may build.

**Charters.** Read the charters for the areas the sketch touches (`.gator/charters/`, found through the charter index) and inspect the existing code the plan will change. Do this before drafting, not after: the plan must say what you consulted (see Context Checked in Step 3).

**If you are the draftor on your first turn:**
- Read the Architect brief if listed, then the sketch file (path shown in status output)
- Read the charters and code the sketch touches
- The sketch is the Architect's approved scope. Do not exceed it.

**If you are the draftor revising:**
- Read the reviewer's findings at `findings.current.md` in the loop directory
- Address every finding. Do not ignore findings.
- Re-read the brief and charters if a finding says context was missed

**If you are the reviewer:**
- Read the Architect brief if listed
- Read the plan at `plan.current.md` in the loop directory
- Read the sketch to verify the plan stays within scope
- Spot-check the charters and code the plan claims to have consulted

### Step 3: Produce your artifact

Write your output to a markdown file. The file must:
- Be non-empty
- Be a real artifact (not a placeholder, not "looks good", not a stub)
- Stand alone as a readable document
- Follow the format in the artifact format reference (see below)

**Draftor output** — an implementation plan:
- `## Executive Summary` (four bullets or ~120 words — extracted by the Dashboard)
- Clear scope statement
- Architecture or approach
- File/module changes with specific paths
- Dependencies and ordering
- Risks or open questions
- Charter impact
- `## Context Checked`: **required** on every draft and revision (see below)
- `## Coding Checkpoints`: **required** on every draft and revision (see below; one checkpoint for a small fix)

**Context Checked (draftor, planning loops).** Every plan includes exactly one `## Context Checked` section listing what you actually consulted: the Architect brief (`architect-brief.md`) when status lists one, the charters you read, and the code or prior artifacts you inspected. When nothing applies, write `None — <short reason>` (e.g. `None — greenfield script, no existing charter or code`). The CLI rejects the submission when the section is missing, duplicated, empty (comments do not count), or a bare placeholder (`None`, `N/A`, `-`, `TBD`). It checks structure only. Listing files you did not read is a protocol violation. This applies to planning loops created since the requirement shipped; older loops are not checked.

**Coding Checkpoints (draftor, planning loops).** Every plan includes exactly one `## Coding Checkpoints` section: the ordered, **responsibility-based** increments the coding loop will review one at a time. Each item is `N. **Title** — scope. Verify: verification.`, numbered 1, 2, 3… (at most 12; continuation lines indented two spaces). A title names a responsibility, never a file. A single-responsibility change declares one checkpoint: `1. **Fix** — <the change>. Verify: <the focused test>.` The CLI rejects a missing, duplicate, empty or malformed section. This applies to planning loops created since the requirement shipped.

**Reviewer output** — findings OR approval:
- `## Executive Summary` (four bullets or ~120 words — extracted by the Dashboard)
- Verdict line (APPROVE, REVISE, or ESCALATE)
- Numbered findings with severity, location, issue, and suggestion
- Scope check against the sketch
- Context check: is the plan's `## Context Checked` credible? It should cover the Architect brief (when one exists) and the charters and code the plan changes. Missing or implausible context is a finding, not a nit.
- Checkpoint check: are the `## Coding Checkpoints` responsibility-based and independently reviewable, each a working, verifiable increment on top of the previous ones? A multi-responsibility plan whose checkpoints are file-shaped, or are styling-, docs- or tests-only pseudo-modules, is a finding. One checkpoint is correct for a single-responsibility change.
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

Check `gator loop status` before doing anything. If exit code is `0`, proceed with your submission. If exit code is `1`, you cannot submit — if you have a genuine Architect-owned blocker, escalate first (see Rule 6); otherwise run `gator loop wait --token <your-token> --max-seconds 45`, and reissue it each time it exits `3`, until the loop becomes actionable. A paused or blocked loop also exits `1`: keep waiting. If exit code is `2`, the loop is over — stop.

### Rule 2: Submit through the CLI only

You must not directly edit `session.json`, `events.jsonl`, `plan.current.md`, or `findings.current.md` in the loop directory. The CLI is the only authorized writer. If you edit these files directly, your changes will be overwritten on the next submission.

### Rule 3: Respect the sketch boundary

The sketch is the Architect's approved scope. The plan must implement what the sketch describes — not more, not less. If you believe the sketch is wrong or incomplete, escalate. Do not silently expand scope.

### Rule 4: Address all findings

When you receive findings as a draftor, you must address every one in your revision. You may disagree with a finding — but you must state why, explicitly. Silent omission of a finding is a protocol violation.

### Rule 5: Do not rubber-stamp

When you are the reviewer, your job is to find problems. An approval should mean "this plan is ready to implement as written." A plan whose Context Checked omits the brief or the charters it changes is not ready. If you are unsure, submit findings. The round limit exists precisely so that you do not need to approve prematurely.

### Rule 6: Escalate when stuck

If you cannot proceed — the scope is unclear, you need information that isn't available, or you fundamentally disagree with the direction — escalate:

```
gator loop escalate --token <your-token> --reason "why you are stuck"
```

The loop pauses. The Architect will read your reason, and unblock with an optional message that answers your question or grants/denies your request. Check `gator loop status` after the unblock — read the `Architect message:` line before resuming work. See the Escalation section below for the full flow.

### Rule 7: Work at the pace the artifact needs

There is no participant deadline. Take the time the work needs: read the Architect brief, the charters and the code it touches, and verify what you claim. The Architect watches long-running turns and may interject, pause, or end the loop; you do not need to ask for time, estimate a duration, or hurry to fit a window.

Escalate only for a genuine blocker, a scope decision, or missing authority (see Rule 6), never to negotiate time.

*Legacy loops:* loops created before this change may still show a `Turn window` in `status` and can end with `turn_timed_out`. If yours does, submit or escalate before that deadline.

### Rule 8: Do not attempt to communicate with the other model

There is no side channel. You do not share context, leave notes in the plan for the reviewer, or embed instructions in your findings for the draftor. Each artifact should be a self-contained professional document, not a message to your counterpart.

### Rule 9: Do not modify loop infrastructure

Do not create, delete, rename, or move files in `.gator/loops/<loop-id>/`. Do not modify `.tokens.json`. Do not interfere with `session.lock`. The loop directory is managed exclusively by the `gator loop` CLI.

### Rule 10: Terminal means done

When the loop reaches a terminal state (`plan_approved`, `max_rounds_exceeded`, `ended_by_architect`, or `turn_timed_out` in legacy loops), it is over for you. Do not attempt further submissions. The session residue remains for the Architect to inspect.

**One exception belongs to the Architect.** The Architect may extend a loop that ended at `max_rounds_exceeded` (`gator loop extend`), which adds rounds and resumes it at `plan_revision` for the Draftor. The earlier rounds, artifacts, and decisions are kept. Do not wait for or poll for an extension: stop when the loop ends. If the Architect extends the loop, the Architect re-engages you with a fresh join prompt. Then run `gator loop status`, read the `Architect message:` line (the reason for continuing), and proceed. The Draftor revises against `findings.current.md`. No other terminal state can be resumed.

---

## Suspension Is Not Departure

A loop can be suspended without ending: `paused_by_architect` (an Architect hold, no response required from you) or `blocked_on_architect` (an escalation waiting for an Architect decision).

- Stay in the bounded `wait` or the watcher. `status` exits `1` and shows the hold or the pending decision; `wait` keeps waiting. Exit `2` always means the loop ended.
- Resume from `gator loop status`, not from a pasted prompt or a rejoin. When the Architect unblocks, the preserved role and stage come back and the turn owner's `wait` or watcher wakes.
- If your submission is rejected because the loop is blocked, keep your file. Wait, then submit it after the unblock.
- When status shows `Architect response to your escalation: decision-N`, the `Architect message:` line below it is the Architect's answer to your request. It stays visible to you until your next submission, even if it is not your turn.
- Escalate only for a genuine Architect-owned decision (Rule 6).

---

## Planning Sources

A planning loop starts from one of these sources. `gator loop status` names it on a `Plan source:` line; no line means an ordinary sketch.

**Architect-originated draft plan.** The Architect supplied a complete plan. It was checked exactly like a Draftor draft, and the loop starts at `plan_review`, so the **Reviewer acts first**.
- The plan is **not approved**. Review it as you would any draft. Writing it did not approve it, and no Draftor turn exists for it.
- If the Reviewer submits findings, the Draftor owns `plan_revision` and submits a **full replacement plan** (`plan.current.md` shows the plan under revision).
- The Architect's original stays in `architect-plan.md` (read-only, digest-checked). Only Reviewer approval makes the plan eligible for a coding loop.
- With no `sketch.md`, the plan's stated scope and any Architect brief govern. A scope change is Architect-owned: escalate.

**Revision of an approved plan.** Status shows `Revision of: <loop id>`. The loop starts from an approved planning loop and a revision sketch, with ordinary Draftor-first turns.
- Read `revision-baseline-plan.md` (the approved plan) and `revision-baseline-approval.md` (its approving review) first, then `sketch.md` (the revision sketch). These copies are the baseline: read-only and digest-checked. The source loop is never changed and may later be changed or removed.
- The Draftor writes a **full replacement plan**, not a diff. Earlier rounds of the source loop are optional unless the sketch requires them.
- `## Context Checked` records only what you actually consulted; it does not claim the whole source history was read.
- A baseline marked `[!!]` in status must not be relied on: escalate.

---

## State Machine (What You Can See)

| Stage | What's happening | Who acts |
|-------|-----------------|----------|
| `plan_drafting` | First draft needed | Draftor |
| `plan_review` | Plan awaiting review | Reviewer |
| `plan_revision` | Findings received, revision needed | Draftor |
| `blocked_on_architect` | Escalated, waiting for human | Nobody (paused until the Architect unblocks) |
| `paused_by_architect` | Architect paused the loop | Nobody (paused until the Architect unblocks) |
| `plan_approved` | Reviewer approved | Nobody (done, final) |
| `max_rounds_exceeded` | Round limit reached without approval | Nobody (done unless the Architect extends it — see Rule 10) |
| `turn_timed_out` | Legacy loops only: active role did not submit in time | Nobody (done, final) |
| `ended_by_architect` | Architect ended the loop | Nobody (done, final) |

**Active (3):** `plan_drafting`, `plan_review`, `plan_revision`. One of you should be working.
**Paused (2):** `blocked_on_architect`, `paused_by_architect`. Nobody acts, and the loop resumes only when the Architect unblocks it. `status` exits `1` and `wait` keeps waiting: you are still a participant.
**Terminal (4):** `plan_approved`, `max_rounds_exceeded`, `turn_timed_out`, `ended_by_architect`. The loop is over for you, and `status` and `wait` exit `2`. All four are final, except that the Architect alone may extend `max_rounds_exceeded` (Rule 10).

---

## Coding Loops (Implementation Review)

A **coding loop** reviews real code instead of a plan. The Architect starts it from an approved planning loop (`gator loop start --mode coding --from-loop <approved-loop-id>`). `gator loop status` then shows `Mode: coding`, and the loop directory holds an immutable copy of the plan, `approved-plan.md`. Everything else in this protocol still applies: turns, the bounded wait, escalation, pause and unblock. These rules are added:

**The staged tree is the candidate.** The reviewed and approved thing is the exact `git write-tree` of the staged index, captured by the CLI. Your artifact describes it; prose never substitutes for it. Unstaged and untracked files are shown to the Reviewer but are NOT part of the candidate. The loop directory's own files under `.gator/loops/` are expected residue.

**Checkpoints.** When the approved plan declares `## Coding Checkpoints`, the loop works through them in order, and `gator loop status` names the active one: `Checkpoint: 2 of 3 -- <title> (findings round 1 of 3)`. Rules:
- The Draftor stages only the active checkpoint's change on top of the approved earlier checkpoints, and submits with `--checkpoint <id>` (status prints the exact command). Submitting any other checkpoint is rejected.
- The Reviewer reviews exactly that checkpoint: `git diff <checkpoint base> <staged tree>`, which status prints. Paths that an approved earlier checkpoint also changed are marked as revisited; that is information, not a prohibition.
- Approving a checkpoint that is not the last opens the next one. It does **not** authorize a commit, and nothing is committed between checkpoints. Only the final checkpoint's approval leads to the one normal commit of the cumulative staged tree.
- **Two counters.** The *findings round* is per checkpoint and is compared with the round budget (`max_rounds`). The *generation* counts every submission in the loop and names its artifacts (`implementation.round-<generation>.md`, `findings.round-<generation>.md`), so no evidence is ever overwritten. For checkpoint loops, status shows these two instead of `Round: X/Y`.
- Plans from older planning loops without the section get one implicit checkpoint, and status keeps `Round: X/Y`.

**Draftor (`implementation_drafting` / `implementation_revision`):**
1. Read `approved-plan.md` (and `findings.current.md` when revising) and the charters for the files you will touch. Read any Architect brief status lists: a coding loop can show two, `source-architect-brief.md` (the planning brief carried forward) and `architect-brief.md` (a new brief for the coding loop). Read both; where they conflict, the coding brief is newer and wins, and a conflict that matters is an escalation. If status says "Planning brief: not carried forward", the Architect dropped it at coding start; do not go looking for it.
2. Implement the change, update the affected charters and `commit_draft` material, and run the relevant checks.
3. Stage everything that belongs in the commit, including the charter and `commit_draft` files you changed: `git add ...`. Do not commit. Do not create one commit per round.
4. Submit with `gator loop submit-implementation --token <your-token> [--checkpoint <id>] --file <implementation.md>` (`--checkpoint` is required when status shows a `Checkpoint:` line). The artifact needs exactly these level-2 sections: `## Executive Summary`, `## Implementation Summary`, `## Charter Updates`, `## Verification`, and **exactly one** `## Commit State`, which the CLI fills with the captured facts, replacing your text there. A submission with nothing staged is rejected.

**Reviewer (`implementation_review`):**
1. `gator loop status` prints the candidate's staged-tree ID and the exact review command: `git diff <base_tree> <staged_tree>`, or for checkpoint loops `git diff <checkpoint base> <staged_tree>`. That diff is fixed: it shows exactly the submitted candidate even if the index changes later.
2. Read `implementation.current.md`, run the review command, and check the affected charters.
3. Submit findings (`gator loop submit-review --token <your-token> --file <findings.md>`) or approve (`... --approve`). Do not write a `## Reviewed Candidate` section; the CLI appends it. **Approval is refused if the staged tree or HEAD changed after submission.** Submit findings instead, so the Draftor resubmits the current tree.

**After approval (`implementation_approved`): one normal commit.** The Draftor returns to its ordinary session and creates **one** normal Git commit of the approved staged tree, using the repository's existing hooks and the Architect's normal confirmation. There is no loop commit command. Do not stage or change anything else first. `gator loop status` shows the result:
- `[..] PENDING COMMIT` — the approved tree is still staged and not yet committed;
- `[OK] COMMITTED` — the commit contains exactly the approved tree;
- `[!!] STALE` — something changed; the approved tree is no longer the candidate. Stop. The Architect returns the loop to review with `gator loop reopen --token <architect-token> --message "..."`, and the Draftor resubmits;
- `[??] UNKNOWN` — Git facts could not be read; never treat it as approved.

| Stage | What's happening | Who acts |
|-------|-----------------|----------|
| `implementation_drafting` | First implementation needed | Draftor |
| `implementation_review` | Staged candidate awaiting review | Reviewer |
| `implementation_revision` | Findings received, revision needed | Draftor |
| `blocked_on_architect` | Escalated, waiting for human | Nobody (paused until the Architect unblocks) |
| `paused_by_architect` | Architect paused the loop | Nobody (paused until the Architect unblocks) |
| `implementation_approved` | Reviewer approved the staged tree | Draftor makes one normal commit (done unless the Architect reopens it) |
| `max_rounds_exceeded` | Round limit reached without approval | Nobody (done unless the Architect extends it) |
| `turn_timed_out` | Legacy loops only: active role did not submit in time | Nobody (done, final) |
| `ended_by_architect` | Architect ended the loop | Nobody (done, final) |

**Coding Active (3):** `implementation_drafting`, `implementation_review`, `implementation_revision`.
**Coding Paused (2):** `blocked_on_architect`, `paused_by_architect`.
**Coding Terminal (4):** `implementation_approved`, `max_rounds_exceeded`, `turn_timed_out`, `ended_by_architect`. An extension resumes a coding loop at `implementation_revision`.

---

## What Good Participation Looks Like

**Good draftor behavior:**
- Reads the sketch carefully before writing
- Produces a plan that is implementable, not aspirational
- Addresses every finding in revision — explicitly
- Escalates when genuinely stuck rather than producing a weak or speculative plan

**Good reviewer behavior:**
- Reviews against the sketch scope, not personal preferences
- Finds real problems: missing error handling, violated invariants, scope creep, unclear ordering
- Numbers findings clearly so the draftor can address them one by one
- Approves when the plan is genuinely ready, not just when tired of reviewing
- Does not invent requirements that aren't in the sketch

**Bad behavior (either role):**
- Submitting stubs or placeholders instead of finished work
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
| `architect-brief.md` | Optional Architect brief: required reading when status lists it (read-only, digest-checked) |
| `architect-plan.md` | Architect-originated draft plan, when the loop started from one: provenance only, never approval (read-only, digest-checked) |
| `revision-baseline-plan.md` | Revision loops: the approved plan being revised (read-only, digest-checked copy) |
| `revision-baseline-approval.md` | Revision loops: the review that approved the baseline plan (read-only, digest-checked copy) |
| `source-architect-brief.md` | Coding loops only: the planning loop's brief, when carried forward (read-only) |
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

When you escalate, the loop pauses until the Architect responds. The Architect reads your reason, makes a decision, and unblocks.

### Classifying uncertainty

Not every uncertainty requires escalation. Classify before deciding:

**(a) Non-blocking — state an assumption and proceed.** If you face ambiguity that you can resolve with a reasonable default, state it explicitly in the plan as a reversible assumption (e.g., "Assuming v2 API — will revert if Architect directs otherwise"). The Architect can interject to correct the assumption without pausing the loop.

**(b) Blocking — requires an Architect decision, escalate with `--file`.** If the uncertainty is Architect-owned (scope change, external authorization, fundamental direction choice), write a structured decision-request document and escalate:

```
gator loop escalate --token <token> --file request.md --reason "Need Architect decision on API version"
```

The `--file` attaches a durable artifact to the decision ledger. The Architect's response (via `unblock --message` or `unblock --file`) is recorded on the same ledger entry and survives to terminal state.

### What happens after you escalate

1. The loop enters `blocked_on_architect`. Your status will show exit code `1` ("Awaiting Architect decision"). You are still a participant: stay in the bounded `wait` (or the watcher).
2. Wait. Do not poll aggressively. The Architect may take minutes or hours.
3. When the Architect unblocks, they may include a **message** and optionally a **response artifact** — a structured document with the decision, rationale, and next action.
4. On your next `gator loop status` check, you will see:
   - Your turn is `YES` again
   - An `Architect message:` line with the Architect's response (if they sent one)
   - An `Architect response artifact:` line with the path to a durable response document (if the Architect attached one via `unblock --file`)
5. **Read the Architect message and response artifact before doing anything else.** The message is a summary; the artifact (when present) contains the full decision, rationale, and next action. Act on both.
6. The Architect message and response artifact path are cleared after you submit. They are one-turn instructions, not persistent notes. The response artifact file remains in the loop directory for audit.

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
2. Exit 0: proceed. Exit 1 (including paused or blocked): escalate first if blocked on an Architect-owned decision, otherwise `gator loop wait --token <token> --max-seconds 45`. Exit 2: the loop ended; stop.
3. `wait` exit 0: act. Exit 3: reissue the same `wait` (also through a pause or block). Exit 2: the loop ended; stop.
   (Optional, runtimes that re-invoke you when a background command exits, such as Claude Code: `gator loop participant watch --token <token> --max-seconds 600 --json` in the background instead; see Step 1.)
4. Read the Architect brief(s) status lists, then the relevant files (sketch, plan, or findings) and the charters they touch
   (plans need a `## Context Checked` section: what you consulted, or `None — <reason>`;
   and a `## Coding Checkpoints` section: one checkpoint for a small fix)
5. Write your artifact to a file
6. Submit: `gator loop submit-draft` or `gator loop submit-review` (coding loops: `gator loop submit-implementation` with the change staged — see Coding Loops)
7. If stuck at any time: `gator loop escalate --token <token> --reason "..."`

The CLI mediates everything. The files are the handoff. The Architect supervises. The loop terminates deterministically. Do your best work within the bounds.
