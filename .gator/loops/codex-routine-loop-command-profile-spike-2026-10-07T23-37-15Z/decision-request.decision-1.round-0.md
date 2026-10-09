# Decision Request: Publish the Codex routine profile, given that allowed `gator loop` commands run unsandboxed?

## Decision Needed

Should checkpoint 4 publish the verified Codex routine-participant profile as an opt-in reference note? The alternative is to record it only as "works, not recommended" in a status line. The approved plan makes this choice Architect-owned, because the result is a conditional pass.

## Context

Evidence: `.gator/artifacts/2026-10-08-codex-routine-profile-spike.md` §7–§8, approved through checkpoint 3.

- **Mechanism.** A Codex rule file holds one `prefix_rule(["gator","loop",[status, wait, submit-draft, submit-review, submit-implementation]], decision="allow")`. It must live in a dedicated `CODEX_HOME` that also pre-trusts the repository. Rules are not profile-scoped, so this is the only per-session scope.
- **What works.** A Codex Reviewer approves and a Draftor submits with no host prompt (non-interactive runs). Gator's live staged-tree check still runs, and stale approvals are still refused. Direct `git write-tree`, `git add`, `git commit`, out-of-workspace writes and uncovered `gator` commands stay sandboxed or role-rejected. A broken rule file fails closed. Removing the profile restores the baseline exactly.
- **Trust cost.** Codex documents `allow` as "Run the command outside the sandbox without prompting". Every matched `gator loop …` process, and the Git it spawns, runs with the user's full rights. A tampered or shadowed `gator` on PATH would inherit those rights.
- **Caveats for any published note:**
  - Windows PowerShell 5.1 turns Gator exit codes 2 and 3 into 1, so Codex participants must read Gator's text ("Loop ended.", "Your turn: YES") rather than exit codes.
  - Gator labels a sandbox denial as `git_busy`, which models read as lock contention.
  - The interactive TUI prompt display was not observed; the "no prompt" behavior there rests on the documentation.
  - Only Codex CLI 0.144.1 on Windows 10 was tested.

## Options Considered

1. **Publish as an opt-in (pass branch).** Add `reference-notes/codex-routine-participant-profile.md` (both copies), linked from the Goal-mode note and the protocol. It gives exact setup and removal steps for a dedicated `CODEX_HOME` (the rule, pre-trust, no `--profile`, never the normal home), states the unsandboxed trust cost plainly, and lists the caveats above. This removes routine approval prompts for teams that accept the trade, and keeps the rule auditable and removable.
2. **Record "works, not recommended" (conditional branch).** Add only a status line in `codex-loop-participant.md` (both copies) pointing to the evidence artifact. Participants keep approving the host prompt. No published path runs `gator` unsandboxed by default, but the routine-prompt problem in #37 stays unsolved.

Both options add the copy-guard tests unchanged.

## Recommendation

Option 1, as an explicitly opt-in note that leads with the trust cost. The rule is narrower than the remembered "always allow" rules that already accumulate in normal Codex homes (for example `git add`, `git commit -m` and `gator gatorize` on this machine). The evidence shows Gator, not the host, enforces token, role, turn and candidate freshness. Option 2 is the conservative choice if you would rather wait for the Phase-1b Gator fixes (a permission-specific error code and a wrapper-safe `wait` result) before recommending anything.

## Consequence of Delay

The coding loop stays blocked at checkpoint 4. Checkpoints 1–3 remain approved and staged, and nothing is committed.
