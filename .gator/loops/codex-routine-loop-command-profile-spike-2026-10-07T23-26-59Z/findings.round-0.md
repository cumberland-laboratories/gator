# Review: Codex Routine Loop-Command Profile Compatibility Spike (#37 Phase 1)

## Executive Summary

- **Verdict:** REVISE. The proposed evidence-first spike remains within the approved scope and correctly preserves Gator as the authority for loop state and candidate freshness.
- **Strength:** It identifies `gitsnap.snapshot()` and its `git write-tree` side effect as the concrete boundary to test, while retaining a valid negative result as an outcome.
- **Required correction:** The packaging/documentation verification names tests that do not guard the claimed protocol and reference-note copy contracts; the plan must use the actual loop drift/identity tests.
- **Required correction:** The temporary Codex configuration experiment needs an explicit isolation and restore protocol that prevents a user-global rule or profile from remaining effective in another session.

## Verdict

REVISE

## Findings

1. **Major â€” Change 5 / Testing / Coding Checkpoint 4: the verification suite does not cover the copy contracts the plan relies on.**
   - The plan says `tests/test_layout.py` supplies the byte-equal `.includes` â†” starter-template pin and proposes `pytest tests/test_layout.py tests/test_packaging.py` as final verification. `test_layout.py` exercises layout classification; it does not pin the proposed reference-note or protocol copies. The repository's existing loop tests are the relevant guards: `tests/test_loop.py` covers the current protocol/reference template identity checks, and `tests/test_loop_context_evidence.py` declares the live/shipped `loop-artifact-formats.md` and protocol pairs.
   - Revise the testing and checkpoint verification to name and run the precise loop documentation tests that protect every copied file the selected outcome changes. If a new standalone routine-profile note is not covered by an existing guard, the plan must either add a narrow identity test or explicitly state why it is intentionally not shipped as a mirrored template.

2. **Major â€” Changes 1 and 3 / Assumptions: the temporary user-configuration experiment lacks a safe session-isolation procedure.**
   - The plan permits a candidate rule or named profile in user-level Codex configuration, then says the original configuration is backed up and restored. That is not sufficient as written: it does not specify how the active fixture session selects the profile, how the normal project session is kept from inheriting it, or how restoration is verified if the interactive client exits unexpectedly. This is central to the sketch's one-active-session and no-broader-permission boundary.
   - Revise with an explicit preflight, activation, teardown, and post-teardown verification procedure. It must identify the exact supported configuration location and selection mechanism discovered in Change 1, prove the default session has no matching rule before and after the probe, and make failure to obtain that isolation a negative result rather than an invitation to leave a global rule enabled.

3. **Moderate â€” Change 3 / Acceptance rule: "without a recurring manual host prompt" is not operationally measurable enough for a profile that may be prompt-only rather than sandbox-changing.**
   - The plan correctly treats an unsandboxed `gator` process as a trust question, but it does not require recording whether the mechanism changes authorization only, sandbox filesystem rights, or both. The profile can otherwise appear to pass merely because an interactive approval was remembered, while the actual child-Git permission boundary remains unknown.
   - Add a required per-mechanism evidence row: command match result, approval behavior, effective sandbox/write boundary, and whether child Git inherits it. The happy path may pass only when these facts are documented alongside the no-recurrence observation.

## Scope Check

The plan stays within the sketch: it is a Codex-specific, opt-in compatibility spike; it retains Gator's token, stage, and freshness controls; it avoids the Dashboard bridge and does not propose a Gator snapshot workaround. The planned issue comment remains correctly gated on Architect confirmation.

## Context Check

The plan's core loop and Git-snapshot context is credible: `gitsnap.py`, the Loop charter, and the existing Codex participant note are appropriately identified. The documentation-test claim is not credible as written: `tests/test_layout.py` is not the stated byte-identity guard, so the Context Checked section and final test command must be corrected to include the relevant loop documentation tests.

## Checkpoint Check

The four checkpoints are responsibility-based and ordered: baseline evidence, happy path, safety/rejection, then result packaging. Checkpoint 4 needs its verification target corrected per Finding 1. Checkpoints 1 and 2 must also include the isolation evidence from Findings 2 and 3 so that a positive result is independently reviewable.
