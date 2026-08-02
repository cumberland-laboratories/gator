# Procedure: Gatorize Permutations

**Scope**: `src/gator_command/scripts/gatorize.py` — installing, upgrading, or morphing `.gator/` in project repos.

## The Rule

**Gatorize installs on the current branch, in place** (as of v2.4.0). Before any filesystem change, it prints a scenario-aware summary of what it will do and asks for a single Y/n confirmation. Under `--yes` it skips the confirmation and refuses to run on a dirty tree.

Users who want an isolated experiment create their own branch first (`git checkout -b my-gator-experiment`) — deleting that branch afterward fully undoes the install. Otherwise, the supported clean-undo path is reviewing the diff before you commit.

Pre-v2.4.0 always created a `gator-install` safety branch. That pattern was retired because it introduced novel failure modes at the interactive-prompt boundary (silent branch switches on Dashboard-triggered installs, cross-branch contamination, stale-branch pickup) without proportional payoff — see [`artifacts/2026-07-30-retire-gator-install-branch-implementation-plan.md`](../artifacts/2026-07-30-retire-gator-install-branch-implementation-plan.md).

## Preflight (all scenarios except Scenario 1)

Every non-scenario-1 invocation runs the same preflight in `gatorize.main()`:

1. **Pre-action summary** — `print_pre_action_summary(target, scenario)` names the current branch (`git rev-parse --abbrev-ref HEAD`), the scenario, the categories of change (`.gator/`, entry-point files, hooks, vendor SessionStart configs, gitignore), and the safety-branch hint.
2. **Dirty-tree gate** — `_check_dirty_tree_and_gate(target)`:
   - Clean tree → proceed silently
   - Dirty + `--yes` → **refuse**: exit 1 with "gatorize refuses to run on a dirty tree in non-interactive mode. Commit or stash your changes first, then re-run."
   - Dirty + interactive → warn and prompt `c` (continue) / `a` (abort). Abort exits 0 cleanly.
3. **Y/n confirmation** — `confirm(..., auto_yes=True)`. Under `--yes` auto-proceeds; interactive `n` exits 0 cleanly.

Scenario 1 (fresh directory, no git yet) skips the dirty-tree gate — there's no git repo to check — but still prints the pre-action summary (with a "no safety-branch pattern applies here" note in place of the safety-branch hint) and runs the confirmation gate.

## Five Scenarios

### Scenario 1: Fresh directory (no git, no memex, no gator)

Target has no `.git/`, no `.memex/` or `memex/`, no `.gator/`.

1. `action_git_init(target)` — `git init`, normalize to git's `init.defaultBranch` (`main` if unset), stage existing files (or empty commit) with message "Initial commit (pre-Gator)". Leaves the caller on the default branch. No safety branch.
2. `action_install_gator(target)` — install `.gator/` from templates (v2 `.includes/` layout: scaffolding at root, shipped content under `.gator/.includes/`).
3. Common tail: `write_gator_version`, `ensure_repo_gitignore`, `action_install_entry_points`, `action_install_outbox`, `action_install_product_source`, `action_register`, `print_summary`.

### Scenario 2: Git repo, clean (no memex, no gator)

Target has `.git/` but no knowledge layer.

1. Install `.gator/` from templates (fresh stubs) on the **current branch**.
2. Common tail.

### Scenario 3: Git repo, has `.gator/` (prior gator install)

Target already has `.gator/` from a previous gatorize run. Detects the **generation** of the existing install and adapts.

#### Generation Detection

Every `.gator/` install is assigned a generation via `.gator/.gator-version`:

| Generation | Signal | Era |
|---|---|---|
| 0 | No `command-post.md`, no `.gator-version` | Pre-installer (manually built) |
| 1 | Has `command-post.md`, no `.gator-version` | Early bash installer chain (retired v2.4.0) |
| 2+ | Has `.gator-version` with `generation:` field | Current |

`CURRENT_GENERATION` lives in `gator_core.py` — single source of truth, imported by the Python installer.

#### Sub-case 3a: Pre-installer builds (gen 0)

These installs pre-date the installer's existence. They may have **more** reference-notes and scripts than the current template. They have no registry entry and no outbox.

1. **Overlay** template files — refresh template-derived files, but **do not delete** extra reference-notes, scripts, or procedures that exist only in the target. Template files overwrite same-named files; everything else is preserved.
2. Add outbox, entry points, register (all new for gen 0).
3. Write `.gator-version` (gen 2).

Note: pre-v2.4.0 command-post-era installs may still have a `.gator/command-post.md` file on disk (that's part of what makes the install "gen 1"), but the current installer neither creates nor refreshes it — thin-link installation was retired with the broader command-post retirement.

#### Sub-case 3b: Early bash-installer install (gen 1)

Templates may have evolved since install.

1. Overlay templates (same overlay-not-replace logic).
2. Re-register if needed.
3. Write `.gator-version` (gen 2).

#### Sub-case 3c: Current generation

Already at latest generation. Refreshes template files to pick up any template changes.

1. Overlay templates.
2. Bump `.gator-version` updated date.

Scenario 3 dispatches to `gator-update.py --path <target> --source <SCRIPTS_DIR.parent>` to run the update rather than a private overlay routine, so the same code path drives both `gator update` and gatorize's upgrade path.

#### The overlay-not-replace principle

Template refresh uses **overlay** semantics: template files overwrite their same-named counterparts in the target, but files that exist only in the target are left untouched. Prevents data loss in repos whose `.gator/` has accumulated project-specific content beyond what the template ships.

### Scenario 4: Git repo, has memex structure, no `.gator/` — the MORPH

Target has `memex/` and/or `.memex/` but no `.gator/`. May also have root-level `constitution.md` or `constitution-core.md`.

1. `action_morph_memex(target, ...)`:
   - Confirm "Proceed with morph?" (auto-yes under `--yes` — Scenario 4 is unambiguous; the strategic morph-vs-upgrade choice happens only in Scenario 5).
   - Rename legacy directories: `memex/` → `memex.pre-gator/`, `.memex/` → `.memex.pre-gator/` (via `git mv` where possible, `shutil.move` fallback).
   - Install fresh `.gator/` from templates.
   - Overlay content from pre-gator directories into `.gator/` per the mapping below.
   - Archive root constitution files into `.gator/legacy-*.md`.
2. Common tail.
3. Leave `memex.pre-gator/` and `.memex.pre-gator/` on the current branch for Architect review. Not deleted — user is expected to review and delete manually when satisfied.

### Scenario 5: Git repo, has both memex and gator

Ambiguous state — prior partial migration or manual setup.

1. Warn the Architect, list what was found (memex/, .memex/, root constitution, `.gator/`).
2. Interactive prompt `[m] Morph / [u] Upgrade / [x] Cancel`.
   - **Under `--yes`**: auto-picks `x` and exits 1 with "Scenario 5 requires an interactive decision. The choice between [m] Morph and [u] Upgrade has permanent data-shape consequences. Re-run without --yes to make the decision interactively." No filesystem mutation happens.
   - `m` → run the Scenario 4 morph path.
   - `u` → refresh `.gator/` templates via `gator-update.py`, ignore memex dirs.
   - `x` → exit 0 cleanly.

The strategic asymmetry between Scenarios 4 and 5 is deliberate: Scenario 4 has no ambiguity (memex present, gator absent → morph), Scenario 5 does (both present → the m/u choice determines whether memex content is folded in or ignored, with permanent data-shape consequences).

## The `--yes` Flag

`--yes` / `-y` is a non-interactive mode for automation (Dashboard-triggered installs, batch scripting). It enables per-site opt-in short-circuits at three call sites — every other prompt continues to read stdin.

| Site | Opt-in | Effect under `--yes` |
|---|---|---|
| `gatorize.main()` dirty-tree | `sys.exit(1)` on dirty | Refuse (exit 1) |
| `gatorize.main()` Y/n confirm | `auto_yes=True` | Auto-proceed |
| `gatorize/entry_points.py:215` foreign entry-point `[1/2/3/x]` | `auto_yes="1"` | Auto-pick Backup & replace |
| `gatorize.py` Scenario 5 `[m/u/x]` | `auto_yes="x"` | Refuse (exit 1) |
| `gatorize/morph.py` "Proceed with morph?" | `auto_yes=True` | Auto-proceed |

The Dashboard's `POST /api/repo/<name>/gatorize` endpoint always invokes `gatorize --yes <path>` because HTTP requests cannot answer prompts.

## Morph Content Mapping

| Legacy source | Gator destination | Strategy |
|---|---|---|
| `memex/mission.md` | `.gator/mission.md` | Copy, overwrites stub |
| `memex/roadmap.md` | `.gator/roadmap.md` | Copy, overwrites stub |
| `memex/identity.md` | `.gator/identity.md` | Copy |
| `memex/inbox.md` | `.gator/inbox.md` | Copy, overwrites stub |
| `memex/issues.md` | `.gator/issues.md` | Copy, overwrites stub |
| `memex/commit_draft.md` | `.gator/commit_draft.md` | Copy, overwrites stub |
| `memex/whiteboard.md` | `.gator/whiteboard.md` | Copy, overwrites stub |
| `memex/patterns.md` (or `patterns/`) | `.gator/patterns.md` (or `patterns/`) | Copy |
| `memex/active-threads/*` | `.gator/threads/` | Demoted to reference tier |
| `memex/threads/*` | `.gator/threads/` | Merge (suffix `-legacy` on collision) |
| `memex/artifacts/*` | `.gator/artifacts/` | Copy |
| `memex/charters/*` | `.gator/charters/` | Preserve user charters, keep gator templates |
| `memex/vault/*` | `.gator/vault/` | Copy |
| `memex/reference-notes/*` | `.gator/reference-notes/` | Legacy copied, gator templates overlay |
| `memex/procedures/*` | `.gator/procedures/` | Replaced by gator procedures |
| `.memex/roles.yaml` | `.gator/roles.yaml` | Copy |
| `.memex/policies/*` | `.gator/policies/` | Copy |
| `.memex/scripts/*` | Skipped | Gator provides its own scripts |
| Root `constitution.md` | `.gator/legacy-constitution.md` | Archived |
| Root `constitution-core.md` | `.gator/legacy-constitution-core.md` | Archived |

## Versioning: `.gator-version`

Every install, upgrade, and morph writes `.gator/.gator-version`:

```
generation: 2
installed: 2026-05-26
updated: 2026-05-26
action: install
cli-version: 2.4.0
```

- `generation` — the template generation number. Increment `CURRENT_GENERATION` in `gator_core.py` when templates change in ways that affect upgrade logic.
- `installed` — date of first install (preserved across upgrades).
- `updated` — date of most recent upgrade/morph.
- `action` — what was done: `install`, `upgrade`, or `morph`.
- `cli-version` — the installer version at install/update time; feeds the Dashboard's Fleet "Version" column.

This file enables future upgrade detection without heuristics. It is not user-edited.

## Recovery

The Stage 5 `print_summary()` banner prints a scenario-aware "Not what you wanted?" recovery paragraph on every successful install. The load-bearing supported clean-undo path is the safety-branch pattern:

- Create your own experiment branch before running gatorize (`git checkout -b my-gator-experiment`).
- If unhappy, switch back and delete the branch: `git checkout <original-branch> && git branch -D my-gator-experiment`.

For "I ran gatorize directly on my working branch, now what?" the summary lists three scoped git-native recipes:

- Uncommitted new files (`.gator/`, entry-point files): `git clean -fd <specific paths>`. Review with `git clean -nd` first — `clean` also removes any OTHER untracked files in the path.
- Uncommitted edits inside existing tracked files: `git checkout -- <path>`.
- Committed changes: `git reset --hard HEAD~<N>`, but only if `HEAD~<N>` is safe to return to.

No bare `git checkout .` recipe — it does not remove untracked new files (which is most of what gatorize adds on a fresh install). No blanket `git reset --hard` — it becomes destructive once Stage 3's dirty-tree continuation is a supported path.

## Connections

→ [Branching Standard](branching-standard.md) — repo-level branching conventions (unaffected by the v2.4.0 in-place shift)
→ [Thin Link Spec](thin-link-spec.md) — historical interface contract from the command-post era; thin-link installation was retired with the broader command-post architecture, but pre-v2.4.0 command-post-era installs may still have a `.gator/command-post.md` file on disk.
→ [Retire gator-install plan (2026-07-30)](../artifacts/2026-07-30-retire-gator-install-branch-implementation-plan.md) — the design rationale for the v2.4.0 in-place install shift
