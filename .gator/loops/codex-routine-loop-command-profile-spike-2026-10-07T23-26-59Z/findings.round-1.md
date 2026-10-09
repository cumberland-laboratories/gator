# Review: Codex Routine Loop-Command Profile Compatibility Spike (#37 Phase 1), Round 2

## Executive Summary

- **Verdict:** REVISE. The revised plan resolves the earlier test-selection, session-isolation, and authorization-boundary findings.
- **Strength:** The isolated Codex config home, fresh-session probes, teardown checks, and mechanism evidence table give the spike a credible one-session trust boundary.
- **Remaining issue:** the planned copy guard for a profile note that exists only after a positive result is not executable as described for the negative-result branch.
- **Required correction:** specify a narrow test that asserts the optional profile-note pair is either both absent or byte-identical; the always-edited Goal-mode note remains unconditionally byte-identical.

## Verdict

REVISE

## Findings

1. **Moderate â€” Change 5 / Copy guard: the pass-only profile-note pair needs an explicit conditional test contract.**
   - `TestArtifactFormatAlignment.test_starter_copies_match` uses a static pair list. Adding `codex-routine-participant-profile.md` to that list will fail the intended negative-result branch because neither copy is created; omitting it leaves the positive-result branch unguarded. The plan currently says to add the pair "on a pass only" but does not define how a single committed test suite behaves in both repository states.
   - Revise Change 5 and checkpoint 4 to add a narrow assertion for the optional pair: either both files are absent, or both exist and their bytes are identical. Keep `codex-loop-participant.md` in the existing unconditional pair list because every outcome edits it. This preserves a strict guard without forcing a no-result placeholder into the negative branch.

## Scope Check

The revised plan remains inside the approved Phase-1 spike boundary. It introduces no Gator runtime workaround, Dashboard bridge, generic shell allowance, or cross-vendor claim.

## Context Check

Credible. The revision accurately identifies the existing loop identity and drift guards and explicitly records that `codex-loop-participant.md` is presently unguarded. It also applies the reviewed Git snapshot behavior correctly.

## Checkpoint Check

The checkpoints remain responsibility-based and independently verifiable. Checkpoint 4 must incorporate the optional-pair behavior above so its verification command is valid for either legitimate spike outcome.
