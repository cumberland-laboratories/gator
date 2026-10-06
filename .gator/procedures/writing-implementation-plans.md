# Procedure: Writing Implementation Plans

## When to use

Use this procedure before drafting or reviewing an implementation plan, before
starting a coding loop from an Architect-supplied plan, and when deciding
whether a small change can go directly to coding. It applies to the plan that
guides code changes, not to the concise implementation-evidence artifact
submitted during a coding loop.

## Outcome

Produce the smallest plan that makes its design decisions, ownership
boundaries, risks, and verification legible. A plan is modular when each
module has one independently reviewable responsibility. It is simple when it
adds no abstraction, state, grammar rule, or policy beyond what the feature
needs.

## Steps

1. **Read the evidence first.** Read the sketch and Architect brief, then the
   cross-cutting and relevant module charters, existing code at the likely
   seam, and applicable tests. Record only sources actually consulted in
   `## Context Checked`.

2. **Choose the planning path.** Classify the work before choosing modules.

   | Path | Use when | Required handoff |
   |---|---|---|
   | Direct to coding | One localized behavior at an established seam; no new durable state, public contract, security boundary, or unresolved design choice; the sketch explicitly permits it; and focused acceptance tests are clear. | A concise Architect-supplied implementation plan or sketch that names files, behavior, tests, and charter impact. |
   | One implementation-plan review | A bounded change has two or more meaningful responsibilities, lifecycle/refresh behavior, or non-obvious integration ordering, but its design has one clear direction. | An implementation plan reviewed before coding. |
   | Full planning loop | The change introduces or changes a trust/security boundary, public CLI/API/schema contract, durable state or migration, concurrency/lifecycle invariant, cross-module protocol, competing credible designs, or an Architect-owned decision. | A governed planning loop until an approved plan exists. |

   File count is not the criterion. A one-file security change can need a full
   planning loop; a three-file localized UI change can be direct to coding.

   Whatever the path, a plan that will drive a coding loop declares
   `## Coding Checkpoints`: the ordered, responsibility-based increments the
   coding Reviewer approves one at a time. A single-responsibility change
   declares one checkpoint.

3. **Define modules by responsibility, not by file.** Reuse an existing module
   whenever the change belongs to an established seam. Introduce a module only
   when it owns a stable responsibility, such as parsing, validation, a
   lifecycle boundary, a storage contract, or a reusable policy.

   For each proposed module, state:

   - its one-sentence purpose and the invariant it owns;
   - files/functions changed or created;
   - dependencies and ordering;
   - focused verification; and
   - charter impact.

   Do not make standalone modules for styling, tests, or documentation unless
   they introduce an independent contract. Split a module when it would own
   two unrelated reasons to change, crosses a trust boundary, or cannot be
   reviewed and tested as one coherent behavior.

4. **Apply the simplicity test.** Prefer the smallest established seam that
   meets the requirement. Simplicity is not the fewest lines or files; it is
   the fewest new concepts and rules.

   - Prefer adapting a local, chartered seam over a new framework or generic
     abstraction.
   - Keep a bounded grammar, policy, or allowlist explicitly closed. Unsupported
     cases should have a defined safe fallback rather than quietly expanding
     scope during implementation.
   - Keep state ownership, invalidation, ordering, and failure behavior local
     and explicit.
   - When two credible approaches exist, name the rejected alternative and why
     it is disproportionate or unsafe. Escalate instead when that choice is
     Architect-owned.

5. **Scale verification to the new risk and checkpoint.** Add one focused
   test for each new behavior or invariant. For every proposed test or test
   group, state the behavior, invariant, or regression risk it proves; remove
   or consolidate anything that has no distinct answer. Use integration,
   stale-response, race, mutation, adversarial-path, or compatibility tests
   only when the change creates that kind of risk.

   A coding-loop plan uses a verification ladder:

   - At each coding checkpoint, run the direct unit, contract, and nearest
     integration or UI tests for the responsibility just completed. These
     checks should normally finish in a few minutes, not rerun a broad browser
     or repository suite by default.
   - At final coding-loop approval, run the smallest relevant broad regression
     suite once across the completed change. A longer Dashboard or browser
     suite is appropriate here when the change reaches that surface.
   - Reserve the full repository or release matrix for CI/deployment, unless
     the checkpoint itself changes a cross-cutting contract that genuinely
     requires it.

   Reuse existing broad coverage rather than duplicating it in every module.
   Parameterize equivalent rejection cases instead of turning a validation
   matrix into many near-identical tests. State the focused checks for each
   checkpoint and the broad suite deferred to final approval, including why an
   exception requires broad coverage earlier.

6. **Write or review the plan.** Use the Loop implementation-plan format. In
   `## Approach`, state the selected planning path, the module map, the key
   design decision, and simplicity boundary. In `## Changes`, order work by
   dependency rather than filesystem order. The reviewer checks that every
   module has a real responsibility, every new invariant has verification,
   every proposed test has a distinct risk-based purpose, and the plan neither
   hides an Architect decision nor invents scope. A plan with an exorbitant,
   duplicative, or unexplained test catalogue is not implementation-ready;
   return findings to reduce, consolidate, parameterize, or justify it before
   coding begins.

7. **Checkpoint — decide whether the plan is ready.** The plan is ready when
   another engineer can implement it without filling in material design
   decisions, and when removing any proposed module would leave an unowned
   responsibility or invariant. Otherwise simplify, research, or escalate.

## Review Questions

- Does the plan address every in-scope behavior and respect every exclusion?
- Is each module an independently reviewable responsibility rather than a
  file-shaped task list?
- Does it reuse existing seams where possible and justify every new boundary?
- Are state, trust, ordering, and failure invariants explicit where relevant?
- Is every test tied to a new behavior or risk rather than added by habit?
- Could any listed tests be consolidated through an existing suite or a
  parameterized case without losing distinct risk coverage? If the answer is
  yes, the reviewer requests that reduction before approving the plan.
- Does each coding checkpoint name only its focused verification, while the
  broad Dashboard or regression suite is deferred to final approval? If not,
  is there a stated cross-cutting reason for running it early?
- Is the chosen path—direct coding, one plan review, or a full planning
  loop—proportionate to the actual risk?
- Are the `## Coding Checkpoints` responsibility-based and independently
  reviewable as working, verifiable increments? Reject a multi-responsibility
  plan whose checkpoints are file-shaped or are styling-, docs-, or
  tests-only pseudo-modules; one checkpoint is correct for a
  single-responsibility change.

## Notes

- “Modular” does not mean maximizing the number of modules or tests. It means
  making ownership and change reasons clear.
- “Simple” does not mean omitting safeguards. A small, closed security policy
  with adversarial tests is simpler than a broad renderer whose behavior is
  difficult to audit.
- A coding-loop implementation artifact remains evidence for a staged change;
  follow `loop-artifact-formats.md` for its required `## Commit State` section.

## Connections

→ [Coding Standard](coding-standard.md) — code-level modularity and test
  conventions
→ [Loop Artifact Formats](../.includes/reference-notes/loop-artifact-formats.md)
  — required plan and implementation-artifact headings
→ [Draft - Review - Edit - Draft](draft-review-edit-draft.md) — document
  revision workflow outside a governed Loop
