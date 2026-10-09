# Implementation Plan: Codex Routine Loop-Command Profile Compatibility Spike (#37 Phase 1)

## Executive Summary

- **What:** a version-pinned, evidence-first spike that answers whether Codex can run routine role-scoped `gator loop` commands without recurring host prompts. Two outcomes are allowed: a narrow opt-in profile that has been verified, or a documented negative result. Gator code is not changed.
- **Key design decision:** isolate the exact Git writes Gator's candidate check needs. These are the `write-tree` object writes and `index.lock`, plus the opportunistic index refresh in `git diff`. Test only the documented Codex mechanisms against that need: execpolicy prefix rules, the sandbox writable-roots policy, and named profiles. Do not invent syntax.
- **Main risk:** a rule that lets the Gator command run may also unsandbox it, or let its child Git run with broad write access. Rejecting that as "too broad" is a valid negative result.
- **Verification:** the sketch's six-row matrix, run in a disposable governed fixture outside this repository. Probes are scripted where `codex exec` / `codex sandbox` allow it, and an Architect-run interactive Goal-mode pass confirms the happy path.

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
- `tests/test_layout.py`, for the byte-equal `.includes` ↔ starter-template scaffolding pin around line 347.
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

**Acceptance rule for a mechanism.** It passes only if all four hold:
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
- Why: answers Q1–Q3 and pins the result to one surface (sketch Constraint 4).

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
  - Write the candidate rule or profile under Codex's user-level configuration (or a named profile). The role token never goes into any file.
  - Run `codex execpolicy check` against the five subcommands with a placeholder token and against negative controls: `gator loop end`, `gator gatorize`, `git commit`, `git update-ref`, `powershell -c …`. Record each decision.
  - In a fresh interactive Codex Reviewer session with the profile, run `status`, a bounded `wait`, and `submit-review --approve` of the unchanged candidate.
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
  - **Terminal.** End the loop with `gator loop end`. Confirm Goal mode stops on exit 2, and that the profile contains no loop id, token or path that outlives the loop. Removing the profile is a documented manual step.
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
- **Negative or conditional result:** no new reference note and no protocol change. Add one "Routine-profile status" line to `codex-loop-participant.md` (both copies) pointing to the evidence artifact. The existing Goal-mode workflow stays intact.
- **Both outcomes:** comment on #37 with the outcome and a link to the artifact, after the Architect confirms. That is an outward-facing action.
- Why: sketch Proposed Work §5.

## Dependencies and Ordering

Changes 1 → 2 → 3 → 4 → 5 run strictly in order. Change 3 depends on the Change 2 baseline, because without a reproduced denial a pass proves nothing. Change 5's branch depends on the Change 3/4 verdict. Codex-interactive steps need the Architect to drive a Codex session; the draftor prepares the fixture and the exact prompts, and records the results. The scripted `codex execpolicy check` / `codex sandbox` probes can run without the Architect.

## Assumptions, Risks, and Required Architect Decisions

- **Assumption (non-blocking):** the pinned surface is the Codex CLI `0.144.1` interactive TUI on Windows 10 19045, because that is what is installed and where the failure was seen. Other surfaces (desktop app, IDE, macOS/Linux) are recorded as untested. This will be revised if the Architect names a different surface.
- **Assumption (non-blocking):** the fixture's Codex user config may be changed temporarily during the spike. The original `~/.codex/config.toml` and rules directory are backed up to the scratchpad first and restored at the end, and the artifact records the restoration.
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

There are no new automated tests, because no product code changes. If Change 5 adds a note to the starter template, the existing byte-equal scaffolding pin in `tests/test_layout.py` covers mirror parity. Run `pytest tests/test_layout.py tests/test_packaging.py` at the final checkpoint.

## Charter Impact

None expected: no code under a chartered path changes. The new reference note is scaffolding, not code. If the starter-template mirror is covered by a packaging charter entry that lists reference notes by name, that entry gets the new filename. This is checked during Change 5.

## Coding Checkpoints

1. **Fixture and baseline evidence** — record the pinned environment and the cited Codex documentation (Q1–Q3), build the disposable governed fixture with a coding loop in review, and reproduce and record the approval denial without a profile, including the `write-tree` control probe and the unchanged loop state. Verify: the artifact holds the environment table, citations, verbatim baseline error, and before/after stage, generation and `events.jsonl` counts; no fixture file is inside this repository.
2. **Profile happy path** — configure the smallest documented mechanism for the five `gator loop` subcommands and prove status, wait and each submission complete without a host prompt while Gator's live snapshot still runs. Verify: `codex execpolicy check` decisions for positives and negatives recorded; an approval advances to `implementation_approved` with a matching Reviewed Candidate; the token is in no file.
3. **Safety and rejection** — prove stale-candidate refusal, normal policy for unrelated commands, clean behavior when the profile is removed or unavailable, and no residue at terminal. Verify: each of those four matrix rows has a recorded probe with the expected outcome, and the original Codex configuration is restored.
4. **Result packaging** — publish the verified outcome: on a pass, the routine-profile reference note (both copies) and protocol and Goal-note links; on a negative or conditional result, only the status line in the Goal note, plus an escalation for a conditional pass. Verify: `pytest tests/test_layout.py tests/test_packaging.py` passes, the `.includes` and starter copies are byte-identical, and every setup step in the note matches the verified configuration in the evidence artifact.
