---
date: 2026-10-08
type: implementation-sketch
issue: 37
feature: codex-loop-profile-launcher
recommended-path: direct-to-coding-with-review
---

# #37 Follow-up â€” One-Command Codex Loop Profile Launcher

## Goal

Replace the high-friction manual setup for the verified, opt-in Codex routine
participant profile with one explicit Gator command that prepares an isolated
Codex home and launches an interactive Codex session.

Suggested command:

```text
gator loop codex
```

The launched session can then use the normal `gator loop join` and optional
`/goal` workflow. This command does not start, join, or authorize a loop on
the user's behalf.

## Existing Proven Basis

Issue #37 Phase 1 already established the trust model and verified the exact
rule on Codex CLI 0.144.1 / Windows:

- a `prefix_rule` permits only `gator loop status`, `wait`, `submit-draft`,
  `submit-review`, and `submit-implementation`;
- those commands run outside the Codex sandbox, allowing Gator's required
  child Git verification; and
- other commands, including direct Git writes and Architect loop commands,
  remain under normal Codex policy.

See `reference-notes/codex-routine-participant-profile.md` and the #37 spike
evidence. This work packages that established configuration; it must not widen
the command allow-list or claim cross-version/Codex-surface validation.

## Desired UX

From a governed repository:

```text
gator loop codex
```

Gator prints the trust warning, creates or validates its dedicated loop-only
Codex home, validates the rule, and launches `codex` with `CODEX_HOME` set
for that child process only.

On first use, Codex's normal interactive sign-in flow handles authentication
for that dedicated home; the user does not need to run a separate `codex login`
command beforehand. Later uses open the participant session directly. Removing
the adapter state is an explicit separate command or documented directory
removal; ordinary Gator operations never enable it accidentally.

## Scope and Boundaries

- **Opt-in only.** No change to default `gator init`, `gator loop join`, or
  ordinary Codex sessions.
- **No credential copying.** Never copy, read, move, or synthesize
  `auth.json` from the user's normal Codex home. The user authenticates the
  dedicated home through Codex's normal first interactive launch.
- **No inherited broad permissions.** Do not import normal-home rules. Write
  only the verified five-subcommand rule.
- **Process-local activation.** Set `CODEX_HOME` only in the environment of
  the Codex child process. Do not persist a user/machine environment variable.
- **No loop token handling.** Do not accept, store, print, or pass a token.
- **No automatic trust expansion.** Generate only the required trusted-project
  entry for the resolved current repository, after showing it to the user.
- **No silent launch.** Print the trust cost before each launch: allowed Gator
  Loop commands and their children run outside the sandbox with the user's
  rights; everything else remains subject to normal Codex policy.
- **No fake support.** If `codex` is unavailable or the current OS/surface is
  unsupported, fail with the existing manual-profile reference rather than
  attempting a workaround.

## Minimal Design

### Command surface

Add a narrow `gator loop codex` dispatcher command (or the closest existing
CLI namespace that preserves `gator loop`'s semantics). It should require a
governed repository root, but it must not require an active loop: the normal
flow launches Codex *before* `gator loop join`.

Initial flags should stay minimal:

- `--dry-run`: print resolved home, rule, repository trust entry, and launch
  command without writes or launch;
- `--home <path>`: an explicit alternate dedicated home for testing or an
  organizational installation.

Do not add a profile-name, arbitrary command-list, arbitrary config merge, or
token flag in the first pass.

### Dedicated state location

Choose one documented machine-local default, preferably under the existing
Gator machine home, for example:

```text
~/.gator/adapters/codex/loop-home/
```

It is intentionally a `CODEX_HOME`, so it contains Codex's own login, logs,
sessions, config, and rules. Treat it as user-private machine state, never
repository content and never a Gator artifact to commit.

### Idempotent preparation

On each launch:

1. Resolve the repository root and canonicalize its path for Codex's project
   trust configuration.
2. Create the dedicated home and `rules/` directory if absent.
3. Write the exact version-owned rule only if absent or if its known generated
   form needs a Gator-owned update. Do not overwrite an unfamiliar user rule;
   stop with a clear repair/manual-path instruction.
4. Create or update only Gator's named configuration section needed for the
   current repo trust and applicable Windows sandbox setting. Preserve other
   user-managed Codex configuration in this dedicated home.
5. Run `codex execpolicy check` for one covered command and one disallowed
   command. Continue only when the results prove the expected boundary.
6. Print the trust warning and launch Codex as a child with the temporary
   `CODEX_HOME` environment override.

The launcher must use safe subprocess argument lists, not a shell-assembled
string. It must return Codex's exit status and not leave a changed environment
in the parent shell.

## First-Use Authentication

If the dedicated home has no usable Codex login, do not attempt to automate
or pre-fill credentials. Launch interactive Codex normally and print one
concise note:

```text
Codex will ask you to sign in for this isolated Gator Loop profile.
Sign in there, then continue in the same session.
```

If Codex cannot complete sign-in from its normal launch, the launcher reports
the resolved `CODEX_HOME` and points to `codex login` as the manual recovery
command. It is not necessary in the ordinary first-use path.

## Goal Mode

The launcher deliberately does not attempt to activate `/goal`. Goal mode is
an interactive Codex CLI command, and its goal must reuse the role/token
context established only after the participant has completed `gator loop join`.
Launching with a text prompt could describe the goal but would not reliably
enter Goal mode.

Keep the first-pass flow small:

```text
gator loop codex  ->  gator loop join  ->  /goal  ->  paste the participant goal
```

Improve this later, if needed, at the Gator join seam: after a successful
Codex participant join, emit a short, clearly labelled Goal-mode reminder and
copyable goal text. Do not inject a role token into a launch argument, shell
history, command line, or persisted configuration merely to remove this one
interactive action.

## Verification

- `--dry-run` makes no directory, config, rule, environment, or subprocess
  changes and prints the same paths/rule that a real launch would use.
- A fresh dedicated home gets only the expected config/rule files; no normal
  Codex-home file is read or changed.
- A prepared home passes `execpolicy check` for a covered `gator loop status`
  command and has no matching rule for `git write-tree` or `gator loop end`.
- The launcher passes `CODEX_HOME` to the child only; after it exits, the
  caller's environment is unchanged.
- A subsequent launch is idempotent and preserves user-owned unrelated config
  in the dedicated home.
- A modified/generated-rule mismatch fails closed and points to the manual
  profile note; it never silently replaces an unfamiliar permission rule.
- Missing Codex, unsupported platform, not-a-repository, and no-login paths
  are clear and non-destructive.
- Existing #37 stale-candidate and unrelated-command checks remain valid;
  this wrapper does not alter Gator's loop authorization or candidate checks.

## Non-Goals

- Dashboard permission mediation, a generic shell allow-list manager, or
  cross-vendor profiles.
- Persistent system/user environment changes.
- Automatically joining a loop, importing a role token, or entering Goal mode.
- Making tests, builds, `git add`, `git commit`, or arbitrary Gator commands
  bypass the Codex sandbox.
- Replacing the detailed manual setup for unverified Codex versions/surfaces.

## Delivery Guidance

This is small enough for direct coding from the sketch, followed by a focused
review: it wraps an approved, evidence-backed rule and adds a narrow CLI
surface. Keep it to a launcher module, CLI dispatch/argument parsing, the
existing reference note, and focused tests. Escalate to an implementation
planning loop if inspection shows that safely editing Codex TOML or resolving
the machine Gator home would require a new shared configuration framework.
