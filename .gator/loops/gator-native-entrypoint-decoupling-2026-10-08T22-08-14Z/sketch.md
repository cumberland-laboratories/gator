---
date: 2026-10-08
type: implementation-sketch
feature: gator-native-entrypoint-decoupling
recommended-path: full-planning-loop
---

# Gator-Native Repository Entry Point and Optional Agent Adapters

## Goal

Make `.gator/` the only repository-owned Gator surface. A governed session is
explicitly started by `gator init`; that command identifies and hands the
participant to one canonical Gator entry document inside `.gator/`.

Gator must no longer create, modify, back up, refresh, repair, or require
vendor-native instruction files such as `AGENTS.md`, `CLAUDE.md`, or
`GEMINI.md`. Those files remain wholly owned by the repository and its users.
They may be absent, contain a team's own instructions, or optionally contain a
team-authored pointer to Gator.

This removes an avoidable source of merge conflicts and makes Gator a better
citizen in repositories that already have substantial model- or harness-specific
configuration.

## Product Decision

The explicit invocation is the contract:

```text
participant runs `gator init`
  -> Gator resolves its repository layout
  -> Gator names `.gator/GATOR_INIT.md` (or layout-resolved equivalent)
  -> participant reads it, then follows the normal constitution/session opening
```

`GATOR_INIT.md` is a **Gator-owned bootstrap document**, not a replacement for
the constitution. It should be short, stable, and tool-neutral: explain the
boot sequence, name the resolved constitution and initial context reads, point
to loop behavior when applicable, and state that native agent files are outside
Gator's ownership.

The existing constitution, procedures, charters, and session artifacts remain
where they are. The new file is the discoverable front door to those surfaces.

## Why This Is Worth Doing

- A branch changing application code and a branch updating its own `AGENTS.md`
  no longer conflict merely because Gator refreshed a shared managed block.
- Repositories with rich existing `AGENTS.md`/`CLAUDE.md`/skills arrangements
  keep full ownership; no `*_ROLLBACK.md`, pre-Gator section, sentinel block,
  or Gator repair operation is needed.
- Gator becomes genuinely harness-neutral: its required contract is `gator
  init` plus `.gator/`, rather than a list of vendor-specific discovery files.
- The installed machine-level CLI remains the operational runtime; the
  repository contributes only versioned governance and context under `.gator/`.
- An unfamiliar participant that notices `.gator/` has a clear canonical
  document to inspect, while automatic native-file discovery remains an
  optional compatibility layer rather than an architectural dependency.

## Existing Surfaces to Migrate

The current entry-point subsystem is deliberately more than a template write,
so this must be treated as a migration:

- `gatorize.entry_points` renders and installs managed blocks in `CLAUDE.md`,
  `AGENTS.md`, and `GEMINI.md`, including legacy detection and rollback copies.
- `gator update` refreshes those blocks.
- `gator state` reports and repairs their managed state.
- starter-template tests cover create, refresh, append, backup, legacy upgrade,
  repair, and template/package synchronization.
- the `gator init` tail currently directs a participant to the constitution;
  it should make the new canonical handoff unambiguous without duplicating
  instructions.

Existing repositories may contain Gator-managed native files. They are valid
historical state, but must never be silently deleted, rewritten, or converted
by this migration.

## Proposed Design

### 1. Canonical in-repository bootstrap file

Ship `GATOR_INIT.md` in the starter template under the canonical Gator root
(`.gator/` for the current layout; use the layout resolver rather than hard
coding this in runtime behavior).

Its content should be concise and shared across models. Suggested responsibilities:

1. State that the participant was explicitly started with `gator init`.
2. Direct it to read the layout-resolved constitution before responding.
3. Direct it to read the normal mission/roadmap/inbox context chain.
4. Point to the Gator Loop protocol only when joining a supplied loop token;
   do not make every session read loop-specific material.
5. State that native agent instruction files are not managed by Gator and may
   add local/team guidance without changing Gator governance.

Avoid copying the whole constitution or loop protocol into this file. One
canonical source per substantive rule is essential.

### 2. Make `gator init` the authoritative handoff

Extend the boot output (including the machine-readable form if appropriate) so
it names the resolved `GATOR_INIT.md` path first, then the concrete next reads.
It must remain fast, offline, and non-fatal.

The wording needs to be action-oriented enough that models do not mistake a
green status line for completed session opening. The current constitution
handoff solved this class of failure; preserve that behavioral safeguard rather
than merely adding another informational checkmark.

If `GATOR_INIT.md` is missing in a legacy repository, `gator init` should:

- still give a usable legacy session-opening directive;
- report a clear, non-alarming upgrade/migration hint; and
- never create or edit the file merely because a participant opened a session.

### 3. Stop native-file management by default

For new `gator gatorize` installs and ordinary `gator update` runs:

- install and update only `.gator/` Gator content;
- do not create native instruction files;
- do not prompt about pre-existing native files;
- do not create `*_ROLLBACK.md` backups; and
- do not add Gator sentinels to user-owned files.

The default must be safe in a repository where all three native files exist
and are actively maintained by different tools or teams.

### 4. Preserve backward compatibility without perpetuating ownership

Existing Gator-managed native files should be detected for transparent status
reporting, but ordinary update must leave them byte-for-byte unchanged.

Decide explicitly whether to support an opt-in adapter command, for example a
future `gator adapters install <vendor>` / `remove <vendor>`. If retained, it
must be clearly separate from core installation and meet these boundaries:

- explicit Architect/user invocation only;
- narrow vendor-specific pointer rather than a duplicate governance block;
- preserve a non-Gator file unless the user explicitly chooses a documented
  merge/append path;
- have a reversible, well-tested removal path; and
- never be required for Gator correctness.

This adapter is useful compatibility, but it is not required for the first
delivery. The core migration should not wait on defining every vendor's ideal
adapter UX.

### 5. Retire or narrow entry-point state/repair

The managed native-entry-point status, drift, repair, backup, and legacy-upgrade
machinery should cease to be part of the normal Gator health contract.

Choose one of two clean end states during planning:

- remove it from the supported core surface after a compatibility window; or
- retain it only behind an explicit `gator adapters` namespace, with status
  reporting only for adapters Gator was asked to manage.

Do not leave a default `gator state` result implying that a user's untouched
`AGENTS.md` is unhealthy, missing, or needs repair.

## Migration and Compatibility Matrix

| Repository state | `gator init` | `gator update` / gatorize | Native files |
|---|---|---|---|
| New Gator repo | Uses `GATOR_INIT.md` | Creates `.gator/` content only | Untouched / absent is normal |
| Existing repo with Gator-managed blocks | Works; notes canonical bootstrap after migration | Adds `GATOR_INIT.md`; leaves blocks unchanged | Historical files remain valid, not refreshed |
| Repo with team-owned native files | Works from `.gator/` | Never prompts, backs up, or edits them | Fully team-owned |
| Legacy `.gator/` lacking bootstrap file | Preserves legacy handoff + recommends upgrade | Adds the file through explicit update | No native-file side effect |
| Optional adapter user | Core flow still works without it | Only explicit adapter action touches its configured file | Managed only under adapter contract |

## Areas of Concern

### Explicit start must be reliable

This model deliberately trades automatic discovery for lower friction and
ownership clarity. The product must keep `gator init` easy to invoke and make
its output a strong, deterministic handoff. Documentation, Dashboard launch
controls, and loop join prompts should all reinforce the same entry command.

### Avoid split-brain instructions

Gator rules must not be duplicated in `GATOR_INIT.md`, native adapter pointers,
the constitution, and vendor hooks. Each pointer should lead toward the
canonical Gator document; it should not become a divergent second constitution.

### Layout and template synchronization

This repository has current and compatibility layouts plus package/template
mirrors. All changes must use the existing layout resolution seams and keep
the shipped starter template, packaged runtime, and test fixtures synchronized.

### Upgrade semantics

Do not introduce an upgrade that silently removes files from user repositories.
The safest migration is additive inside `.gator/` and non-mutating outside it.
If a future release offers cleanup of historical Gator blocks or rollback
files, that must be a separate explicit, previewable, reversible operation.

### Vendor hooks are separate

Session-start hooks, if supported, are integration configuration and should be
evaluated separately. This sketch removes repository-owned instruction-file
management; it does not assume that every installed vendor hook should vanish
in the same change.

## Suggested Modular Plan

1. **Bootstrap contract and template** — define `GATOR_INIT.md`, add it to the
   template/package mirrors, add layout resolution, and make `gator init`
   print the canonical handoff with legacy fallback.
2. **Default installer/update behavior** — remove native-file creation and
   refresh from normal paths; prove existing native files are untouched.
3. **State/repair compatibility boundary** — narrow or retire default
   native-entry-point state reporting and repair; preserve an explicit,
   non-destructive historical/adapter path as decided.
4. **Documentation and adoption** — update onboarding, gatorize/update
   guidance, Dashboard copy, and migration notes around the explicit
   `gator init` contract.

## Test Cases

- Fresh install creates `GATOR_INIT.md` within `.gator/` and creates no
  `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or rollback files.
- Fresh install beside pre-existing, complex native files leaves their bytes
  unchanged and requires no interactive choice concerning them.
- Re-running `gatorize`/`update` is idempotent for `.gator/GATOR_INIT.md` and
  does not touch native files.
- `gator init` prints the resolved bootstrap path and concrete next steps;
  missing bootstrap file produces a safe legacy handoff and upgrade hint.
- Current and compatibility layouts resolve the correct paths.
- An upgraded repository with old Gator sentinel blocks retains their exact
  bytes across ordinary update; it can still run `gator init` successfully.
- `gator state` does not characterize absent or team-owned native files as
  drift/failure after the migration.
- Package and starter-template outputs remain byte-synchronized where the
  project requires mirror parity.
- Optional adapters, if included, require explicit opt-in, preserve foreign
  content, and can be removed without touching core `.gator/` governance.
- Session opening and loop join still work in a repo with no native agent
  files at all.

## Non-Goals

- Making every AI tool automatically discover Gator without an explicit start.
- Deleting, reformatting, or taking ownership of a user's existing native
  instruction files.
- Replacing the constitution, Gator Loop protocol, charters, or vendor
  session-hook configuration.
- A broad rewrite of Gator's installed machine runtime or Git hook system.

## Delivery Guidance

Use a full planning loop. The desired behavior is simple, but the migration
crosses installer, updater, state/repair, template synchronization, and
session-opening contracts. The plan should first decide the compatibility
window and whether adapters ship in this release or are explicitly deferred.

The best first delivery is likely: canonical bootstrap + `.gator`-only defaults
with legacy files preserved without refresh. Optional vendor adapters and cleanup
of historical blocks can follow once the core path has been proven in real
mixed-tool repositories.
