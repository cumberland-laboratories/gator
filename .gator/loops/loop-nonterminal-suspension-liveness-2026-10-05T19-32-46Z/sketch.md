---
date: 2026-10-05
type: implementation-sketch
feature: loop-nonterminal-suspension-liveness
issues: [53]
recommended-path: planning-loop-then-coding-loop
---

# Feature: Durable Non-Terminal Suspension and Participant Liveness

## Goal

Make a participant's connection to a governed loop survive every
non-terminal suspension. A participant who escalates a blocking question or
whose turn is paused by the Architect must remain a participant, preserve the
correct resume target, and become actionable again when that suspension is
resolved. A terminal loop remains the normal condition that stops a watcher.

This expands #53 from a blocked-state usability repair into one clear lifecycle
contract:

> **Blocked and paused are different governance states, but neither ends the
> participant relationship with an active loop.**

## Why Now

The liveness bridge already provides participant registration, heartbeat,
notification, and acknowledgement mechanics. Live use exposed the remaining
gap: when a loop becomes blocked or paused, a participant can appear to lose
its connection or need a fresh prompt/rejoin to continue. That breaks the
loop's handoff model even when the state transition itself was correct.

This feature should build on the existing liveness store and bounded-wait
fallback. It must not introduce vendor-specific automatic model dispatch.

## Required Behaviour

### Blocked on Architect

- A Draftor or Reviewer may submit a full structured escalation request.
- The session preserves the interrupted stage and role, the request, and the
  intended recipient of the eventual response.
- The participant watcher transitions into a waiting/blocked mode; it does not
  unregister, release itself as complete, or stop because the Architect has
  not responded yet.
- The Architect can read the complete request, provide a multiline response,
  or explicitly cancel/end the loop.
- Resolution is durable evidence and is delivered once to the participant who
  was blocked. The loop then resumes the preserved stage and role.

### Architect Pause

- Pause is an Architect-owned hold, not an escalation and not a decision
  request. It records a reason but requires no participant response artifact.
- The pause preserves the exact interrupted stage and `next_role`.
- A connected watcher waits through the pause. Unblock returns the same role
  to the same actionable stage without copying a prompt, rejoining, or
  manually polling status.
- A repeated pause/unblock cycle must not duplicate notifications, overwrite a
  later Architect message, or revive a stale resume target.

### Common rules

- Existing Architect interjection remains an active-turn communication path;
  do not merge it conceptually or mechanically into paused/blocked state.
- Terminal transitions (approval/ended/max-rounds/other terminal stages) close
  the watcher cleanly. A later explicit loop revival follows its established
  re-engagement rules.
- Liveness acknowledgement means the watcher received a signal, never that a
  model read, followed, or completed it.
- No liveness notification, heartbeat, registration, or acknowledgement may
  mutate `session.json` authority, turns, or normal artifact evidence.

## Architect Workspace UX

- A blocked loop prominently displays the full request, participant role,
  timestamp, and any attached decision-request artifact.
- The Architect response uses a multiline textarea. It should support a
  considered paragraph, not only a one-line reply.
- A paused loop visibly states that it is an Architect hold, names the
  preserved participant/stage, and shows the pause reason. It must not look
  like an unanswered participant escalation.
- Resolved requests and pause/resume actions remain readable in loop evidence
  and history, with no claim that the Dashboard itself resumed model work.
- The view remains incremental: unchanged polling must not erase typed
  response text or flash the workspace.

## Suggested Design Boundaries

1. **Suspension/resume contract** — audit the state-machine fields that carry
   the resume stage and role. Establish a single validated path for preserving
   and restoring them, while retaining separate blocked and paused event
   semantics.
2. **Liveness projection** — define explicit notification/watcher behaviour
   for `blocked_on_architect`, `paused_by_architect`, successful unblock, and
   terminal transitions. Projection must be idempotent across Dashboard or
   watcher restarts.
3. **Architect interaction** — render blocked and paused states distinctly;
   make request and response content readable; preserve form state through
   refresh; and expose only Architect-appropriate liveness details.
4. **Protocol and evidence** — document participant expectations: stay in the
   bounded wait/watch path through non-terminal suspension, resume from status
   rather than a pasted prompt, and use escalation only for a true
   Architect-owned decision.

Prefer adapting the existing session, liveness, Dashboard, and protocol seams
over creating a second suspension store or a new participant transport.

## Out of Scope

- Launching, restarting, or impersonating a vendor model session.
- Solving Codex-specific background wake capability beyond the existing bounded
  wait/watch contract.
- Automatic retry of a participant's work or automatic submission after an
  unblock.
- Automatic stashing, branching, worktree management, or concurrent-change
  recovery (#54 / #57).
- Permission-request mediation (#37) and model provenance (#42).

## Coding Checkpoint Shape to Seek in the Plan

The planning loop should determine the exact modules, but the likely coding
checkpoints are:

1. **Suspension state and resume integrity** — blocked/pause preservation,
   restoration, repeated-transition safety, and durable event/decision
   evidence. Verify: state-machine and submit/host transition tables.
2. **Participant liveness across suspension** — watcher projection,
   notification/ack rules, restart/idempotency behaviour, and terminal close.
   Verify: liveness store/CLI integration and lifecycle tests.
3. **Architect workspace and protocol** — multiline response, distinct paused
   presentation, history/evidence, incremental refresh behaviour, and
   participant guidance. Verify: Dashboard API/UI tests and documentation
   drift checks.

If the design reveals that the state and liveness changes cannot be safely
separated, combine only those two; do not create test-only or styling-only
checkpoints.

## Test Cases and Risks

- Planning and coding loops: pause while Draftor owns the turn, then unblock;
  pause while Reviewer owns the turn, then unblock.
- Blocked Draftor and blocked Reviewer: multiline request and response,
  correct recipient, correct restored stage, exactly-once delivery.
- Repeated block, repeated pause, and mixed sequences: no lost request, no
  stale response, no duplicate wakeup, and no incorrect role restoration.
- Watcher continuity: registered/heartbeat state remains connected or
  intentionally waiting during non-terminal suspension; it closes on terminal
  transition.
- Dashboard restart, sidecar reload, and stale watcher: the loop state remains
  authoritative and notifications are not duplicated.
- UI: long request/response readability, textarea preservation during polling,
  clear blocked-versus-paused wording, keyboard-accessible controls, and
  mutation-free unchanged polls.
- Compatibility: unregistered participants retain the bounded `wait
  --max-seconds` fallback; existing interject, extend, reopen, and attention
  behaviour remain distinct.

## Planning Guidance

Use a full planning loop before coding. This crosses the state machine,
decision evidence, private liveness sidecar, Dashboard API/UI, and participant
protocol. The plan must explicitly audit current blocked, paused, unblock,
end, extend, reopen, and liveness-projection paths before proposing changes.

The coding loop should then review at the responsibility boundaries above,
with a clean working tree and an Architect brief emphasizing: preserve
governance distinctions, keep the participant connected, and never represent
notification as model work.
