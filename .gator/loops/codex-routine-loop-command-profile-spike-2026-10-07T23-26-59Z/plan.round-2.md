# Implementation Plan: Codex Routine Loop-Command Profile Compatibility Spike (#37 Phase 1)

## Executive Summary

- **What:** a version-pinned, evidence-first spike that answers whether Codex can run routine role-scoped `gator loop` commands without recurring host prompts. Two outcomes are allowed: a narrow opt-in profile that has been verified, or a documented negative result. Gator code is not changed.
- **Key design decision:** isolate the exact Git writes Gator's candidate check needs. These are the `write-tree` object writes and `index.lock`, plus the opportunistic index refresh in `git diff`. Test only the documented Codex mechanisms against that need: execpolicy prefix rules, the sandbox writable-roots policy, and named profiles. Do not invent syntax.
- **Main risk:** a rule that lets the Gator command run may also unsandbox it, or let its child Git run with broad write access. Rejecting that as "too broad" is a valid negative result.
- **Verification:** the sketch's six-row matrix, run in a disposable governed fixture outside this repository. Codex runs under an isolated config home, so the Architect's normal Codex sessions never see a spike rule. Each mechanism records its command match, approval behavior, sandbox boundary and child-Git inheritance. The doc copies are guarded by the actual loop identity tests, which are extended to cover the Codex notes.

## Revision Notes (round 2)

- **Finding 1 (Moderate, optional profile-note pair needs a conditional contract): accepted.**
  - The coding loop runs after the spike outcome is known, so only one branch is ever committed. A static pair that is edited only in the pass branch would not break the negative branch.
  - The reviewer's both-or-neither assertion is still the stronger contract. It is fixed before the outcome is known, it is identical in both branches, and it also catches a one-sided copy, for example a note added to `.includes` but not to the starter template.
  - Change 5 therefore adds one small test, `test_codex_routine_profile_copies_both_absent_or_identical`, to `TestArtifactFormatAlignment` and drops the "on a pass only" list edit. `codex-loop-participant.md` stays in the unconditional `test_starter_copies_match` pair list. Checkpoint 4 and Testing are updated to match.

## Revision Notes (round 1)

- **Finding 1 (Major, wrong copy-guard tests): accepted.** `tests/test_layout.py` does not pin these files. The real guards are `TestArtifactFormatAlignment.test_starter_copies_match` and `TestWaitHandoffAlignment.test_protocol_copies_are_identical` in `tests/test_loop.py`, plus the `FORMATS` / `PROTOCOLS` drift lists in `tests/test_loop_context_evidence.py`. None of them covers `codex-loop-participant.md`. Change 5 now adds that note, and the new routine-profile note on a pass, to the `test_starter_copies_match` pair list. Checkpoint 4 runs exactly those tests. See Change 5, Testing, Checkpoint 4 and Context Checked.
- **Finding 2 (Major, no session isolation): accepted.** A new "Configuration isolation protocol" section covers preflight, activation, teardown and post-teardown checks. The spike never edits the Architect's normal Codex config home. If Change 1 cannot find a documented isolated home or a per-session selector, the result is negative. A global rule is never left in place. See Approach, Change 1, Change 4, and Checkpoints 1 and 3.
- **Finding 3 (Moderate, "no prompt" not measurable): accepted.** A required per-mechanism evidence table records four facts: command match, approval behavior, effective sandbox/write boundary, and child-Git inheritance. A "no prompt" observation counts only from a fresh session with no remembered approvals, and with "always allow" offers declined. A probe separates a prompt-only rule from a sandbox-changing rule. See the Approach acceptance rule, Change 3 and Checkpoint 2.

## Summary

The sketch asks for a compatibility spike, not a feature. This plan builds a throwaway governed repository in a temporary directory with a coding loop in `implementation_review`. It reproduces the `.git/index.lock: Permission denied` approval failure under Codex's default workspace policy. It then tries the smallest documented Codex mechanism that lets `gator loop status|wait|submit-*` complete. It proves Gator's stale-candidate rejection still holds and that unrelated commands keep normal policy. The only repository changes are an evidence artifact and, depending on the result, one reference note (mirrored into the starter template) linked from the Loop protocol.

## Context Checked

- `sketch.md` for this loop. Status lists no Architect brief.
- GitHub issue #37 and its 2026-10-07 comment, which describe the Phase-1 requirement and the observed `.git/index.lock` failure.
- `.gator/charters/scripts-loop.md`. Relevant sections: `snapshot()` (its Git command table, the `git_busy` error code and the "Filesystem: object database W" pin), `diff_trees()` (read-only, no index lock), and the `handle_submit_review` coding path ("APPROVE is rejected unless the live staged tree AND HEAD still equal the submitted candidate"; "Cannot verify…" when the live snapshot fails).
- `src/gator_command/scripts/loop/gitsnap.py`: `_git`, `_is_busy`, `snapshot`, `_snapshot`. The Git calls include `write-tree` and `diff --name-only` with `retry_busy=True`. Callers: `submit.py:985` (submit-implementation), `submit.py:1459` (review approval), `cli.py:842` (status), `host.py:877` (coding-loop start).
- `.gator/.includes/reference-notes/codex-loop-participant.md`, the existing Goal-mode note that this work extends.
- `.gator/.includes/procedures/gator-loop-protocol.md` (the watcher/runtime paragraph that links the Codex note) and `reference-notes/loop-artifact-formats.md`.
- `.gator/procedures/writing-implementation-plans.md`, used to choose the planning path.
- `tests/test_loop.py`: `TestArtifactFormatAlignment.test_starter_copies_match` (byte-identity pairs for `loop-artifact-formats.md` and `gator-loop-protocol.md`, about line 1308) and `TestWaitHandoffAlignment.test_protocol_copies_are_identical` (about line 3011). `tests/test_loop_context_evidence.py`: the `FORMATS` / `PROTOCOLS` / `LOOP_JOIN` drift-guard lists (about line 305). I confirmed that no test currently pins `codex-loop-participant.md`. This replaces the round-0 claim about `tests/test_layout.py`, which was wrong.
- `findings.current.md` (round 1 review).
- Local Codex CLI surface: `codex --help` and `codex execpolicy --help` on the installed `codex-cli 0.144.1` (Windows 10). These confirm `exec`, `sandbox`, `execpolicy check` and `-c` config overrides exist. I have not yet read Codex's rule or profile documentation; Change 1 does that.

## Approach

**Planning path.** This is the "one implementation-plan review" path that the sketch's Delivery Guidance names. The trust boundary is material, but Gator's code, state and CLI contract do not change. If discovery shows Gator needs a new persistent config, CLI flag or Dashboard state, the plan stops. The finding is recorded and escalated as an Architect decision, and no workaround is built (see Assumptions).

**What Gator actually needs from Git.** This comes from the charter and code, and it is the precise target for the profile:

| Gator command | Git work needing write access | Source |
|---|---|---|
| `status` (coding, Reviewer/Architect view) | `write-tree` writes tree objects under `.git/objects` and may take `.git/index.lock` to refresh the cache-tree. `diff --name-only` may refresh the index opportunistically. | `cli.py:842` → `snapshot()` |
| `submit-implementation` | the same | `submit.py:985` |
| `submit-review --approve` (coding) | the same; a failed snapshot means "Cannot verify…" | `submit.py:1459` |
| `submit-draft`, planning `submit-review`, `wait` | only loop-directory writes under `.gator/loops/` (worktree, not `.git`) | loop charter |
| Reviewer's `git diff <base_tree> <staged_tree>` | none (tree-to-tree) | `diff_trees()` pin |

Hypothesis H1 is that Codex's workspace-write sandbox treats `.git` as protected, read-only metadata even inside a writable root. That would explain why the read-only diff works while the snapshot fails. The baseline in Change 2 confirms or rejects H1 on this surface. The fact that a planning-only submission still works becomes a useful control.

**Candidate mechanisms, tried in order of least privilege.** Each is a hypothesis to check against the Codex documentation for the pinned version. None of their syntax is assumed here.

1. **Command-prefix allow rule** (execpolicy rules, checkable with `codex execpolicy check`) for exactly `gator loop status`, `gator loop wait`, `gator loop submit-draft`, `gator loop submit-review` and `gator loop submit-implementation`. Discovery must establish three things:
   - (a) whether "allow" only skips the prompt or also runs the command outside the sandbox;
   - (b) whether a prefix match covers a trailing dynamic `--token …` argument (sketch Q5);
   - (c) how a rule matches when Codex on Windows wraps the command in PowerShell.
2. **A sandbox policy scoped to Git metadata for this one worktree**, such as a documented writable-root or permission entry for the fixture's `.git` directory, carried in a **named profile** that the Architect selects for one session. It is not written to the global `config.toml`. This is a fallback if (1) cannot let the child Git run.
3. If both are rejected, record a negative result. Test **no** mechanism that grants generic shell, full-access sandbox, `approval_policy` "never" with full access, or workspace-wide `.git` write for every repository. These are rejected up front under the sketch constraints.

**Configuration isolation protocol (addresses Finding 2).** Test isolation and the packaged scope are separate questions. The spike must never change the configuration that the Architect's normal Codex sessions read.

1. **Discovery (Change 1).** From the pinned Codex documentation, identify:
   - (a) the supported way to run one Codex process against a separate configuration home, such as a documented config-home environment variable;
   - (b) where rule files and named profiles are loaded from;
   - (c) whether any per-session selector exists, such as `--profile` or `-c` overrides.

   Each one is recorded with a citation. If (a) does not exist **and** the rule location cannot be selected per session, isolation is impossible on this surface. The spike then stops with a negative result, and no global rule is written.
2. **Preflight.**
   - Record a SHA-256 manifest of the normal config home: the config file, the rules directory and the profiles (never the credential file's contents).
   - Run `codex execpolicy check` from the normal home against the five probe commands and record that none has an allow decision.
3. **Activation.**
   - Create a spike config home under the scratchpad (`…\spike-codex-home\`). It must be outside every repository and must not be the normal home.
   - Authenticate it with `codex login` run by the Architect under that home. No credential file is copied.
   - Write the candidate rule or profile **only** there.
   - Start the fixture session with the home selector set for that one process only, never as a persistent user or system environment variable. If a profile flag is also needed, pass it on the same command line.
   - The role token is typed at join time and never written to the spike home.
4. **Teardown**, which also runs after a crash or unexpected client exit:
   - delete the spike config home, including its login;
   - confirm that no persistent environment variable was set (`[Environment]::GetEnvironmentVariable(<name>,'User')` and `'Machine'` both empty).

   The normal home was never written, so a crash cannot leave the rule active in another session. Deleting the spike home finishes the cleanup.
5. **Post-teardown verification.**
   - Recompute the normal-home manifest and confirm it is byte-identical to the preflight manifest.
   - Re-run `codex execpolicy check` from the normal home with the same results as preflight.
   - Start a fresh default-home Codex session and confirm `gator loop submit-review --approve` behaves exactly as in the Change-2 baseline.

   These facts are recorded in the artifact. If any one fails, the spike result cannot be a pass until it is fixed.

**Packaged scope (Q3).** This is reported separately. If the only per-session scope Codex offers is a separate config home, the packaged note must say so plainly and describe that as the opt-in unit. It must not suggest adding the rule to the normal home. If a rule can only take effect in the normal home and applies to every session, the result is **negative** for the sketch's one-session boundary, even if it works.

**Required per-mechanism evidence (addresses Finding 3).** Each mechanism tried gets one row in this table in the artifact. A pass needs every cell filled with an observed fact, not an inference:

| Mechanism | Command match result | Approval behavior | Effective sandbox / write boundary | Child Git inherits? |
|---|---|---|---|---|
| e.g. prefix rule | `codex execpolicy check` decision for each of the 5 positive and 5 negative commands | the prompt observed in a **fresh** session with no remembered approvals, "always allow" offers declined; the second and third invocations too | does the matched command run in the sandbox, in a widened sandbox (which roots?), or unsandboxed? Taken from docs and from probe P-write | Probe P-child |

Probes that fill the last two columns:
- **P-write.** In the profiled session, ask Codex to run `git write-tree` directly in the fixture. It is not one of the five commands.
  - If it is denied while `gator loop status` (which runs `write-tree` internally) succeeds, the mechanism is command-scoped: it elevates the matched process tree and does not widen the session sandbox.
  - If it succeeds, the mechanism widened the session's `.git` write boundary, and the unrelated-command row of the matrix fails.
- **P-child.** Run `gator loop status` (coding Reviewer view) under the mechanism and confirm from the Gator output that a live staged-tree OID was produced. This means child `git write-tree` ran. Then check `git cat-file -t <oid>` from an ordinary shell. Together these show the child Git inherited the permission.

If the approval column shows a remembered or "always" approval was involved, or the boundary column cannot be determined, the mechanism does not pass. It is recorded as inconclusive.

**Acceptance rule for a mechanism.** It passes only if all four hold, the evidence row is complete, and the isolation protocol's post-teardown verification passed:
- it covers the five subcommands and nothing broader;
- it is opt-in per session or profile;
- unrelated Git writes (for example `git commit`, `git update-ref`) and unrelated shell still get normal Codex treatment;
- it works with the token supplied dynamically.

A mechanism that lets the gator command run unsandboxed is also judged on whether that is acceptable. The `gator` process is the Gator CLI, which only writes loop files and Git objects, but this is still a trust question. The spike records the facts. If the only working mechanism is "unsandboxed gator process", the result is reported to the Architect as a conditional pass, not packaged as supported (see Assumptions).

**Simplicity boundary.** No Gator code changes. No new config file, profile installer or helper script in the product. In particular, the spike does not change `gitsnap` to use a temporary `GIT_INDEX_FILE`, even though that would avoid `index.lock`. That is a change to Git snapshot authority and a sketch non-goal. If it turns out to be the only clean path, it is reported as a Phase-1b candidate needing its own planning loop. Fixture setup commands live in the evidence artifact, not in a shipped script.

## Changes

### 1. Discovery record and fixture
- File (new): `.gator/artifacts/2026-10-08-codex-routine-profile-spike.md` (evidence artifact, frontmatter `type: spike-evidence`, `issue: 37`).
- What:
  - Record the environment:
    - Codex surface and version (`codex --version`, CLI vs desktop/IDE);
    - OS build;
    - effective sandbox mode, approval policy and workspace trust, read from `codex doctor` and the session header;
    - Gator version (`gator --version`).
  - Quote or link the Codex documentation sections for rules, sandbox and profiles at that version, with the retrieval date. That answers sketch Q1–Q3 with citations, not recollection.
  - Build the fixture in `%TEMP%\gator-codex-spike-<date>\` (outside every governed repo):
    - `git init`, `gator gatorize`, one commit;
    - a minimal approved planning loop driven through the CLI, one tiny staged change, then `gator loop start --mode coding --from-loop …`;
    - draftor `submit-implementation` run from an ordinary (non-Codex) shell, so that the Codex session only plays Reviewer.
  - Record which settings scope each mechanism uses: repository-local, session/profile, or user-global.
  - Record the isolation discovery (items a–c of the isolation protocol) with citations, and the preflight manifest and `execpolicy check` baseline from the normal home. If isolation is impossible, record the negative result here and skip to Change 5's negative branch.
- Why: answers Q1–Q3, pins the result to one surface (sketch Constraint 4) and establishes isolation before any rule is written (Finding 2).

### 2. Baseline denial (no profile)
- File: same artifact, "Baseline" section.
- What:
  1. Start interactive Codex with default workspace policy in the fixture.
  2. Paste the join prompt and enter Goal mode with the prompt from `codex-loop-participant.md`.
  3. Run `status` and then `git diff <base_tree> <staged_tree>`.
  4. Try `submit-review --approve` with an unchanged candidate.
  5. Record:
     - whether Codex prompted, denied or completed;
     - the verbatim error;
     - from `gator loop status` run in an ordinary shell, that the stage is still `implementation_review`;
     - the generation count and `events.jsonl` line count before and after.
  6. Repeat as a scripted probe with `codex sandbox` (or `codex exec` in workspace-write mode) running only `git write-tree` in the fixture. This isolates the Git write from Gator (control for H1).
  7. Also run `codex execpolicy check` on the command string to see what decision the current policy gives.
- Why: matrix rows "Read-only candidate inspection" and part of "Host denial"; establishes the failure the profile must fix.

### 3. Smallest profile, happy path
- File: same artifact, "Profile" section.
- What:
  - Follow the isolation protocol's activation step: write the candidate rule or profile **only** in the spike config home. The role token never goes into any file.
  - Run `codex execpolicy check` from the spike home against the five subcommands with a placeholder token and against negative controls: `gator loop end`, `gator gatorize`, `git commit`, `git update-ref`, `git write-tree`, `powershell -c …`. Record each decision in the evidence table's command-match column.
  - In a **fresh** interactive Codex Reviewer session with the profile (new process, no resumed session, any "always allow" offer declined), run `status`, a bounded `wait`, and `submit-review --approve` of the unchanged candidate. Record the approval behavior for the first and each later invocation.
  - Run probes P-write and P-child and fill the boundary and inheritance columns.
  - Record from an ordinary shell:
    - no host prompt occurred;
    - the stage became `implementation_approved`;
    - the `## Reviewed Candidate` section carries the reviewed tree;
    - the approval used a live snapshot.
  - To exercise `submit-implementation` and `submit-draft`, run one extra round with Codex as draftor: Codex stages a trivial revision (staging uses `git add`, which is the participant's own work and outside the profile, so it may prompt; record that) and submits. Planning `submit-draft` goes through one short planning loop in the fixture.
  - Return to Goal-mode bounded wait after each submission and confirm `wait` exits 3 / 0 as normal.
- Why: matrix row "Governed submit/approve"; sketch Proposed Work §3; answers Q5.

### 4. Safety and rejection
- File: same artifact, "Safety" section.
- What:
  - **Stale candidate.** After a Codex draftor submission, change the staged tree from an ordinary shell. The Codex Reviewer's `--approve` must be refused by Gator with its normal stale/unchanged-candidate message, and the stage must not change.
  - **Unrelated command.** From the profiled Codex session, ask it to run `git commit --allow-empty -m probe` and a non-gator PowerShell write. Both must get the normal prompt or sandbox denial.
  - **Removed profile.** Remove or disable the profile mid-loop and retry `submit-review --approve`. Expect the baseline behavior: no Gator transition, no change to generation or events, the token still valid (`status` works from an ordinary shell). Capture the exact participant-visible text, which should read as a host execution-permission denial, not a Gator error.
  - **Unavailable mechanism.** If the rule file is malformed or the feature is absent, record what Codex reports.
  - **Terminal.** End the loop with `gator loop end`. Confirm Goal mode stops on exit 2, and that the profile contains no loop id, token or path that outlives the loop.
  - **Teardown and post-teardown verification**, per the isolation protocol:
    - delete the spike config home;
    - check that no user or machine environment variable was set;
    - check that the normal-home manifest is unchanged;
    - re-check the normal home with `execpolicy check`;
    - run a fresh default-home session approval that reproduces the baseline.
- Why: matrix rows "Stale candidate", "Unrelated command", "Host denial/profile removal" and "Loop terminal"; sketch Q4.

### 5. Package the verified result
- **Pass:**
  - New `reference-notes/codex-routine-participant-profile.md` in `.gator/.includes/reference-notes/` and byte-identical in `src/gator_command/templates/gator-starter/reference-notes/`. Sections:
    - prerequisites and pinned surface/version/OS;
    - opt-in setup and removal (exact, quoted from the verified configuration);
    - covered commands and explicitly uncovered ones (`git add`, tests, `end`, `extend`, any non-gator command);
    - a condensed validation checklist that links to the evidence artifact;
    - fallback: Goal mode plus normal host approval;
    - how to recognise an execution-permission denial and what to do (approve the host prompt, or tell the Architect out of band). It must say plainly that this is not a `gator loop escalate` and not a code finding.
  - Add one sentence to `codex-loop-participant.md` §Boundaries and to the protocol's runtime paragraph (both `.includes` and starter copies) linking the new note.
  - The setup section describes the opt-in unit discovered in the spike (for example a dedicated config home launched for the loop session) and never tells the reader to put the rule in their normal config home.
- **Negative or conditional result:** no new reference note and no protocol change. Add one "Routine-profile status" line to `codex-loop-participant.md` (both copies) pointing to the evidence artifact. The existing Goal-mode workflow stays intact.
- **Copy guard (both outcomes, the same test code in either branch).** All in `tests/test_loop.py`, `TestArtifactFormatAlignment`:
  - **Unconditional pair (round-1 Finding 1).** Extend the `pairs` list in `test_starter_copies_match` with `.gator/.includes/reference-notes/codex-loop-participant.md` ↔ `src/gator_command/templates/gator-starter/reference-notes/codex-loop-participant.md`. Every outcome edits this note, and it is currently unguarded.
  - **Optional pair (round-2 Finding 1).** Add one test, `test_codex_routine_profile_copies_both_absent_or_identical`. It resolves the `.includes` and starter paths for `reference-notes/codex-routine-participant-profile.md` and passes in exactly two cases:
    - neither file exists (negative or conditional branch);
    - both exist with identical bytes (pass branch).

    If only one exists, it fails with a message naming the missing copy. If both exist and differ, it fails with the existing "live and shipped copies differ" wording.
  - The protocol pair is already guarded by `test_starter_copies_match` and `test_protocol_copies_are_identical` and needs no change.
- **Both outcomes:** comment on #37 with the outcome and a link to the artifact, after the Architect confirms. That is an outward-facing action.
- Why: sketch Proposed Work §5.

## Dependencies and Ordering

Changes 1 → 2 → 3 → 4 → 5 run strictly in order. Change 3 depends on the Change 2 baseline, because without a reproduced denial a pass proves nothing. Change 5's branch depends on the Change 3/4 verdict. Codex-interactive steps need the Architect to drive a Codex session; the draftor prepares the fixture and the exact prompts, and records the results. The scripted `codex execpolicy check` / `codex sandbox` probes can run without the Architect.

## Assumptions, Risks, and Required Architect Decisions

- **Assumption (non-blocking):** the pinned surface is the Codex CLI `0.144.1` interactive TUI on Windows 10 19045, because that is what is installed and where the failure was seen. Other surfaces (desktop app, IDE, macOS/Linux) are recorded as untested. This will be revised if the Architect names a different surface.
- **Superseded assumption (round 0):** the round-0 "edit the normal config, back up and restore it" approach is withdrawn. The isolation protocol now forbids writing to the normal Codex config home at all.
- **Assumption (non-blocking):** the Architect will run `codex login` under the spike config home, which creates a second login that teardown deletes. This avoids copying a credential file. If the Architect prefers otherwise, that is a one-line change to the activation step.
- **Risk — "allow" may mean "unsandboxed":** if the only working rule runs `gator …` outside the sandbox, the child Git and anything else Gator spawns run with the user's full rights. Within the five subcommands Gator only writes loop files and Git objects, but a hostile or broken `gator` on PATH would inherit the rights. The spike records this explicitly. Whether a conditional pass is acceptable is **Architect-owned**. If that is the result, the draftor of the coding loop escalates with a decision request before Change 5 packages anything.
- **Risk — Windows sandbox maturity:** Codex's Windows sandbox may differ from macOS/Linux (for example in how `.git` is protected or how PowerShell wrapping is parsed). Results are labelled Windows-only, with no cross-OS claim.
- **Risk — Gator-side remedy discovered:** if the clean fix is in Gator (for example `gitsnap` using a temporary index, or running `write-tree` with `GIT_OPTIONAL_LOCKS=0` plus an object-only path), that is out of scope. It is recorded as a Phase-1b recommendation needing its own planning loop.
- **Risk — Codex `git add` prompts remain:** staging by the draftor is outside the sketch's command set. A remaining prompt there is reported, not solved.
- **Non-goal guard:** no Dashboard, permission ledger, scheduled task, or change to escalation semantics.

## Testing

This is a spike; the verification matrix is the test. Each row maps to a recorded probe:

| Sketch matrix row | Probe (Change) | Pass evidence recorded |
|---|---|---|
| Read-only candidate inspection | 2, `git diff <base> <staged>` in both default and profiled sessions | succeeds; no new permission used |
| Governed submit/approve | 3, approve and draftor resubmit | no host prompt; stage advances; Reviewed Candidate tree equals the submitted tree |
| Stale candidate | 4, change the index after submit | Gator refuses approval; stage unchanged |
| Unrelated command | 3 `execpolicy check` negatives + 4 live probe | prompt or denial as in baseline |
| Host denial/profile removal | 2 baseline + 4 removal | stage, generation and `events.jsonl` unchanged; token works; text is a host-permission denial |
| Loop terminal | 4 `gator loop end` | Goal stops on exit 2; no token or loop data in profile; removal steps verified |

Two extra rows go with the matrix:

| Risk | Probe | Pass evidence |
|---|---|---|
| Spike rule leaks into the Architect's normal sessions (Finding 2) | Isolation protocol preflight vs post-teardown | identical normal-home manifest; identical `execpolicy check` results; a fresh default session reproduces the baseline |
| "No prompt" caused by remembered approval or a widened session sandbox (Finding 3) | Fresh session, P-write, P-child | complete evidence-table row; direct `git write-tree` still denied |

**Automated tests.** No product code changes, so no new behavioral tests are needed. Packaging adds one regression risk, mirror-copy drift, and two test changes cover it (Change 5):
- the unconditional `codex-loop-participant.md` pair added to `test_starter_copies_match`;
- `test_codex_routine_profile_copies_both_absent_or_identical` for the outcome-dependent note. It catches a one-sided copy or drift on a pass, and it passes cleanly on a negative result.

Before commit, the coding draftor checks the new test once each way: it fails with only the `.includes` copy present, then passes in the committed state. Final checkpoint command:

```
pytest tests/test_loop.py::TestArtifactFormatAlignment tests/test_loop.py::TestWaitHandoffAlignment tests/test_loop_context_evidence.py
```

This command covers both identity tests named in Finding 1 and the protocol/format drift guards, and the protocol paragraph is checked by every protocol test in those classes. A broad suite is not needed, because there are no code changes. CI runs the full matrix.

## Charter Impact

None expected: no code under a chartered path changes. The new reference note is scaffolding, not code. The test change is in `tests/test_loop.py`, which has no function-level charter entry. If the starter-template mirror is covered by a packaging charter entry that lists reference notes by name, that entry gets the new filename. This is checked during Change 5.

## Coding Checkpoints

1. **Fixture, isolation and baseline evidence** — record the pinned environment and the cited Codex documentation (Q1–Q3, including the isolation discovery), take the normal-home preflight manifest and `execpolicy check` baseline, build the disposable governed fixture with a coding loop in review, and reproduce and record the approval denial without a profile, including the `write-tree` control probe and the unchanged loop state. Verify: the artifact holds the environment table, citations, isolation discovery verdict, preflight manifest, verbatim baseline error, and before/after stage, generation and `events.jsonl` counts; no fixture file is inside this repository.
2. **Profile happy path** — configure the smallest documented mechanism, only in the isolated spike config home, for the five `gator loop` subcommands, and prove status, wait and each submission complete without a host prompt in a fresh session while Gator's live snapshot still runs. Verify: the per-mechanism evidence row is complete (match decisions for positives and negatives, approval behavior across repeated invocations, sandbox/write boundary from probe P-write, child-Git inheritance from probe P-child); an approval advances to `implementation_approved` with a matching Reviewed Candidate; the token is in no file.
3. **Safety, rejection and teardown** — prove stale-candidate refusal, normal policy for unrelated commands, clean behavior when the profile is removed or unavailable, and no residue at terminal, then tear down the spike config home. Verify: each of those four matrix rows has a recorded probe with the expected outcome, and post-teardown checks pass (normal-home manifest identical to preflight, `execpolicy check` unchanged, no persistent environment variable, a fresh default session reproduces the baseline).
4. **Result packaging** — publish the verified outcome: on a pass, the routine-profile reference note (both copies) and protocol and Goal-note links; on a negative or conditional result, only the status line in the Goal note, plus an escalation for a conditional pass. In both cases, add the unconditional `codex-loop-participant.md` pair to `test_starter_copies_match` and add `test_codex_routine_profile_copies_both_absent_or_identical` for the optional note. Verify: the new test fails when only one profile-note copy exists (checked once by hand, then reverted), and `pytest tests/test_loop.py::TestArtifactFormatAlignment tests/test_loop.py::TestWaitHandoffAlignment tests/test_loop_context_evidence.py` passes, and every setup step in the note matches the verified configuration in the evidence artifact.
