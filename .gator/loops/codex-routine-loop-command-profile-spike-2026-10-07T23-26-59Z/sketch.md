---
date: 2026-10-08
type: implementation-sketch
issue: 37
feature: codex-routine-loop-command-profile-spike
recommended-path: compact-reviewer-gated-plan
---

# #37 Phase 1 — Codex Routine Loop-Command Profile Compatibility Spike

## Goal

Determine whether an opt-in Codex configuration can allow the small,
role-scoped set of normal Gator loop commands needed by an active participant
without repeatedly asking the Architect to approve routine execution.

The immediate problem is not code review: a Reviewer can read a candidate with
`git diff`, but `gator loop submit-review --approve` performs required Git
freshness/tree verification. Git's normal temporary index/object work can be
denied by the Codex sandbox before Gator receives the command, producing an
`.git/index.lock: Permission denied` failure.

This phase proves or disproves a **Codex-specific participant profile**. It
does not implement the future Dashboard permission-request bridge.

## Desired Outcome

An Architect may opt into a narrow profile for one active loop session. The
participant can run ordinary role-scoped loop work—including the submission
commands that perform Git candidate verification—without a recurring host
approval prompt, while unrelated shell, Git, network, and destructive work
remains subject to Codex's normal policy.

## Constraints

- Gator remains authoritative for token, role, stage, turn, candidate
  freshness, and submission validation. A host allow rule must never bypass
  Gator's CLI/state-machine checks.
- Do not grant generic PowerShell execution, arbitrary Git writes, arbitrary
  token/file reads, or broad workspace elevation.
- Do not store role tokens in a repository file, a recurring scheduled-task
  prompt, or a shared profile.
- Do not claim a cross-vendor solution. Record the exact Codex surface,
  version, operating system, sandbox/approval mode, and workspace policy used
  for the result.
- A host-side denial is an `execution-permission` condition, not a code
  finding or an Architect-owned product/design decision. Until Phase 2, it may
  require the runtime's normal prompt, but should be described accurately.

## Existing Context

- `gator loop wait --max-seconds 45` is the portable waiting contract.
- Interactive Codex Goal mode has successfully kept a participant following
  that bounded-wait contract; see
  `.gator/.includes/reference-notes/codex-loop-participant.md`.
- `submit-draft`, `submit-review`, and `submit-implementation` are not
  read-only. Their candidate snapshot/freshness checks need normal Git index
  or object-database activity.
- #37 already separates an opt-in routine-profile layer from a later governed
  Dashboard permission-request bridge. This sketch covers only the former.

## Spike Questions

1. What supported Codex configuration or approval mechanism can express a
   least-privilege allow rule for the actual Gator CLI invocation on the
   selected surface?
2. Does that mechanism permit the child Git work needed by Gator's candidate
   verification, including temporary `.git/index.lock` activity?
3. Can it be scoped to the trusted repository and active interactive session,
   rather than becoming a global shell/Git exemption?
4. How does it behave when a command is denied, expires, or is unavailable?
   Is the failure distinguishable from a Gator token, candidate, or code
   problem?
5. Is a literal command-prefix rule sufficient when the participant supplies a
   role token dynamically, or does the supported surface require a different
   safe invocation pattern?

Do not invent a Codex configuration syntax. Use the currently documented,
available mechanism and record a negative result if it cannot meet the
boundary.

## Proposed Work

### 1. Establish an isolated, version-pinned test fixture

Use a disposable governed repository/worktree with a minimal coding loop and
an approved source plan. Record:

- Codex client/surface and version;
- operating system, sandbox/approval mode, and workspace policy;
- Gator version and the exact loop mode; and
- whether the profile is repository-local, session-local, or user-global.

Never test by loosening the normal project sandbox globally.

### 2. Exercise the baseline denial

Without the profile, capture the expected behavior:

1. Join as Reviewer and enter Goal mode after joining.
2. Read status and the staged candidate with a read-only diff.
3. Attempt a governed approval of an unchanged candidate.
4. Record whether Codex requests approval, denies `.git/index.lock`, or
   completes. Verify Gator did not advance the loop on failure.

### 3. Apply the smallest supported profile and prove the happy path

Configure only the discovered, documented Gator loop command scope. Exercise:

- `status` and bounded `wait`;
- the applicable submission commands (`submit-draft`, `submit-review`, and
  `submit-implementation` where the fixture uses them);
- an approval that requires normal Git freshness verification; and
- a return to Goal-mode bounded waiting after the submission.

The result must show that the command succeeds without a recurring manual
host prompt and that Git verification still occurred.

### 4. Prove safety and rejection behavior

- Change the staged candidate after a submission and prove Gator rejects stale
  approval normally.
- Attempt an unrelated shell/Git operation and prove it is still subject to
  normal Codex policy.
- Exercise denied or removed-profile behavior; verify the loop remains in its
  prior stage, token/registration state does not change, and participant text
  identifies an execution-permission problem rather than a code finding.
- End the loop and confirm the profile does not leave an active-loop token or
  broader permission behind.

### 5. Package only a verified result

If the spike passes, add a small **Codex routine participant profile** reference
note next to `codex-loop-participant.md`, linked from the Loop protocol. It
must include:

- prerequisites and the exact supported Codex surface/version;
- opt-in setup and removal instructions;
- the precise commands it covers and explicitly does not cover;
- the validation transcript/checklist; and
- fallback behavior when unavailable.

If no supported mechanism can meet the boundary, document that negative result
and leave the current Goal-mode + normal-host-approval workflow intact. Do not
add an unsafe workaround or claim support.

## Verification Matrix

| Scenario | Expected result |
|---|---|
| Read-only candidate inspection | Works without expanding shell/Git privilege. |
| Governed submit/approve | Runs required Git freshness verification and advances only on valid candidate. |
| Stale candidate | Gator rejects approval; profile does not weaken the staged-tree binding. |
| Unrelated command | Still receives normal Codex policy treatment. |
| Host denial/profile removal | No Gator transition, nonce change, or false code finding; clear execution-permission diagnosis. |
| Loop terminal | Goal stops per protocol; no persistent loop-specific credential/permission remains. |

## Non-Goals

- Dashboard approval UI, permission-request ledger, or a vendor-neutral
  permission bridge.
- Automatic approval of arbitrary PowerShell, Git, tests, network requests, or
  destructive commands.
- Scheduled-task token handling or background session dispatch.
- Changes to Gator's Git snapshot authority, staged-tree review, or loop
  escalation semantics.

## Delivery Guidance

This phase is small in code but material in trust boundary. Use the new
Architect-originated compact-plan path: the Reviewer approves the spike plan
before testing/configuring a profile. Do not run a full implementation-planning
loop unless the discovery phase shows that Gator needs a new persistent config,
CLI interface, or Dashboard state. A successful documented profile is the
exit criterion; the Dashboard bridge is a separate later phase.
