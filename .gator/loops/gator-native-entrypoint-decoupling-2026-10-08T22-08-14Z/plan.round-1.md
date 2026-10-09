# Implementation Plan: Gator-Native Repository Entry Point and Optional Agent Adapters

## Executive Summary

- **Proposal:** ship one Gator-owned bootstrap document, `GATOR_INIT.md`, as a shipped root file that the layout resolver places (`.gator/.includes/` on v2, `.gator/` on v1). `gator init` names it first in its session-opening handoff. When it is missing, `gator init` falls back to the current handoff and prints an upgrade hint, and it never writes the file.
- **Key decision:** `gatorize` and `gator update` stop creating, refreshing, prompting about or backing up `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`. `gator state` stops treating them as managed (schema `gator-state-v2`), and the entry-point renderer and writers are deleted. Optional `gator adapters` are **deferred** and not part of this release.
- **Main risk:** historical Gator blocks in native files go stale. `GATOR_INIT.md` states that Gator content wins over a stale block, and the upgrade never edits those blocks.
- **Verification:** four responsibility checkpoints, each with focused tests. The headline tests prove that native files keep their exact bytes through install, update and state repair. Revision 1 adds two things. One is an inventory of every doc that mentions native files, each classified as revise or preserve, including the enforcer procedure and configuration. The other is a regression test that rejects retired ownership claims in maintained docs. One full suite runs at final approval.

## Summary

The plan implements the sketch's recommended first delivery. It adds a canonical in-repo bootstrap document and makes `gator init` the authoritative handoff to it, with a legacy fallback. It makes install and update `.gator/`-only. It retires native-entry-point state and repair from the core health contract, with a non-destructive compatibility stub. It aligns the loop-join prompt and documentation with the explicit `gator init` contract. Existing native files, including ones that carry historical Gator sentinel blocks, are never deleted, rewritten or converted. Vendor adapters and cleanup of historical blocks are explicitly deferred (sketch: Delivery Guidance).

## Response to Review Findings (round 1)

- **Finding 1 (Medium): documentation inventory is incomplete. Accepted.**
  - Change 9 is now inventory-driven. I ran a documented `grep` over README, `CONTRIBUTING.md`, `docs/`, all starter-template `.md`, all `.gator/.includes/` `.md` and `.claude/commands/`, and classified every hit.
  - **Revise:** 11 surfaces. These include `procedures/enforcer-review.md` and `reference-notes/enforcer-configuration.md`, which were omitted from round 0 and are named in the finding.
  - **Preserve:** research and citations, generic "entry point" false positives, and dogfood-only positioning notes. Each has a stated reason.
  - Checkpoint 4 re-runs the inventory at implementation time.
  - A new regression guard, `tests/test_native_file_guidance.py`, fails on retired ownership claims in the maintained surfaces. It excludes the CHANGELOG and research documents by name and also pins template↔dogfood parity for the revised pairs.
  - No product scope changed.

## Context Checked

- No Architect brief: `gator loop status` lists none for this loop.
- Review findings: `findings.current.md` (round 1).
- Documentation inventory: a `grep -rIE` over `README.md`, `CONTRIBUTING.md`, `docs/`, `src/gator_command/templates/gator-starter/**/*.md`, `.gator/.includes/**/*.md` and `.claude/commands/`.
  - Hit lines were read for every file in the Change 9 tables, and template↔dogfood parity was checked with `cmp` for the four largest pairs.
  - The dogfood-only notes were found absent from the starter template: `gator-layering-over-agent-and-spec-stacks.md`, `gator-positioning-brief.md`, `positioning-hierarchy.md` and `where-gator-is-now-and-where-it-is-going.md`.
- `sketch.md` (this loop).
- Protocol and formats: `.gator/.includes/procedures/gator-loop-protocol.md`, `.gator/.includes/reference-notes/loop-artifact-formats.md`, `.gator/procedures/writing-implementation-plans.md`.
- Charters: `.gator/charters/INDEX.md`; `scripts-cross-cutting.md` (Shipped-Copy Synchronization, CLI/JSON schema compatibility, the #53 note that the live CLAUDE/AGENTS/GEMINI regions change with the protocol); `scripts-installer.md` (`action_install_entry_points`, `render_entry_content`, managed_block API); `scripts-managed-state.md` (six-state status/repair, `gator-state-v1`, Two Baselines TRIPWIRE, `*.local.md` boundary); `scripts-repo-lifecycle.md` (`session_opening_directive`, `print_json`); `scripts-repo-update.md` (`plan_entry_point_updates` / `execute_entry_point_updates`, `print_json_plan` schema); `scripts-layout.md` (single path authority, content-family classification, mixed detection).
- Code:
  - `src/gator_command/scripts/gatorize/entry_points.py` (whole file).
  - `gatorize.py`: `action_install_gator` root-file tuple, `print_pre_action_summary`, `main` common tail.
  - `gator-update.py`: `TEMPLATE_FILES`, entry-point plan/execute, `main` execution and version-stamp gate, `print_json_plan` callers.
  - `gator-state.py`: lines 1–260 plus the parser and repair signatures.
  - `gator-init.py`: `print_boot_sequence`, `session_opening_directive`, `print_json`, `main`.
  - `gator_layout.py`: `SHIPPED_ROOT_FILES`, `GatorPaths`, `_shipped_file`.
  - Starter-template `scripts/gator-init.py`: already diverges, with no drift suffix; it has the same `session_opening_directive`.
  - Starter-template `scripts/gator-update.py`: entry-point copy and inlined helpers.
  - `templates/gator-starter/commands/init.md`.
  - `reference-notes/local-agent-skills.md`.
  - `gator-dashboard.py`: the loop-join prompt builder, around line 2920.
  - `dashboard/updates.py`: no entry-point consumer.
  - `pyproject.toml` package-data: the `scripts/gatorize/**/*` glob.
- Tests located by grep and partially read:
  - `tests/test_template_sync.py`: entry-point parity classes and `TestASTEquivalenceOfInlinedHelpers`.
  - `tests/test_loop.py`: `TestWaitHandoffAlignment` and `TestExecutiveSummaryProducerPaths` pin `render_entry_content` and the live root entry files.
  - `tests/test_init.py`.
  - `tests/test_state.py`, `tests/test_update_entry_points.py` and `tests/test_gatorize.py`: located by grep counts only.

## Approach

**Planning path:** full planning loop, as the sketch requires. The change alters public CLI behavior (`gatorize`, `update`, `state`, `init`), a JSON schema (`gator-state`) and a cross-module install/update/state contract.

**Module map (by responsibility):**

1. **Bootstrap contract**: `GATOR_INIT.md` content, its layout classification, its placement by install and update, and the `gator init` handoff with legacy fallback.
2. **Native-neutral install/update**: `gatorize` and `gator update` touch only `.gator/` (plus the existing `.gitignore`, Git hooks, and vendor-hook config, which are out of scope).
3. **State/repair boundary**: `gator state` reports native files as informational and unmanaged. Repair becomes a no-write compatibility stub. The now-unused renderer and writers are removed.
4. **Explicit-start adoption**: the Dashboard loop-join prompt and user docs teach `gator init` → `GATOR_INIT.md` as the only required entry.

**Key design decisions:**

- **Placement via the resolver, not a new path rule.** `GATOR_INIT.md` joins `SHIPPED_ROOT_FILES`, exactly like `constitution.md`, and `GatorPaths` gains `bootstrap = _shipped_file("GATOR_INIT.md")`. Because it sits next to `constitution.md` and `procedures/` in every layout, the document can say "next to this file" without hard-coding `.includes/`. *Rejected:* pinning it at the visible `.gator/` root on v2. That needs a new content family ("shipped but root-pinned"), new mixed-detection rules and new migration routing, which is disproportionate when `gator init` prints the resolved path.
- **One canonical source per rule.** `GATOR_INIT.md` holds only the boot sequence, pointers and the native-file ownership statement. It does not restate constitution rules, loop wait semantics or Executive Summary requirements. The protocol remains the only source for those.
- **Compatibility window for `gator state`.** We remove native-file management from the core surface now and keep `gator state repair` as a no-write stub that explains the change. Removing the stub is a later, separate decision. This picks the sketch's first end state ("remove from the supported core surface after a compatibility window") because adapters are deferred.
- **Adapters deferred.** No `gator adapters` namespace ships. The sketch says the core migration should not wait on it.
- **Schemas.**
  - `gator-update-v1` keeps the `entry_point_actions` key and its summary count, now always `[]` / `0`. Keys are preserved and consumers that tolerate empty lists are unaffected, so no bump is needed.
  - `gator-state` bumps to **`gator-state-v2`** because the meaning changes: `entry_points` and `entry_point_baseline_kind` are removed and `native_files` is added. The cross-cutting TRIPWIRE requires a bump for removal. Only tests consume the old shape; the Dashboard does not.
  - `gator init --json` gains an additive `session_opening` object.

**Simplicity boundary:**

- No new module or framework, and no file-discovery of other vendor files.
- No edits to `.gitignore` semantics. The `*.local.md` ignore lines stay, as harmless existing behavior.
- No vendor-hook or `.claude/commands/` changes.
- No cleanup of historical blocks or rollback files.

## Changes

### 1. Bootstrap document (new)
- File: `src/gator_command/templates/gator-starter/GATOR_INIT.md` (new) and the dogfood copy `.gator/.includes/GATOR_INIT.md` (byte-identical).
- What: a short, tool-neutral document (~40 lines) with these sections:
  1. *You were started with `gator init`.* This file is Gator's entry point and lives next to `constitution.md` and `procedures/`.
  2. *Before your first response:* read `constitution.md` next to this file. Then read `mission.md`, `roadmap.md` and `inbox.md` at the `.gator/` root (skip any that are absent on a fresh repo). If `charters/` holds only templates, follow `gator-start-up.md` next to this file.
  3. *Joining a loop (only when given a loop token):* read `procedures/gator-loop-protocol.md` next to this file, then run `gator loop status --token <token>`. The protocol is the behavioral contract. Do not read loop material otherwise.
  4. *Native agent files:* Gator does not create, edit, back up or repair `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` or similar files. They belong to the repository and its users and may add team or personal guidance. That guidance may extend but must not override Gator governance. Older Gator versions wrote a `GATOR:BEGIN`/`GATOR:END` block into those files. Gator no longer refreshes that block and it may be stale; where it conflicts with this file or the constitution, these govern. Removing it is the repository owner's choice.
- Why: Sketch §1, the canonical front door, with responsibilities 1–5.

### 2. Layout classification and resolution
- Files: `src/gator_command/scripts/gator_layout.py` and `src/gator_command/templates/gator-starter/scripts/gator_layout.py` (kept in sync).
- What:
  - Add `"GATOR_INIT.md"` to `SHIPPED_ROOT_FILES`.
  - Add `bootstrap: Path` to `GatorPaths`, set by `_shipped_file("GATOR_INIT.md")`.
  - Leave `_has_required_includes_content` unchanged, so a v2 repo without the file stays v2, not invalid.
- Why: Sketch §1 requires layout-resolved placement. The layout charter's TRIPWIREs require classification and resolver authority.
- Effect: a flat-root `GATOR_INIT.md` on a v2 repo classifies as `mixed`, consistent with every other shipped root file. `migrate_layout` / residue enumeration already iterate `SHIPPED_ROOT_FILES`.

### 3. Install/update placement
- Files:
  - `gatorize.py` `action_install_gator`: add the name to the root-file tuple.
  - `gator-update.py` `TEMPLATE_FILES`.
  - The starter-template `gator-update.py` `TEMPLATE_FILES`.
- What: copy `GATOR_INIT.md` into the shipped location, like `constitution.md`. `gator update` therefore adds it to existing repos and refreshes it idempotently.
- Why: Sketch §1 and the matrix row "Legacy `.gator/` lacking bootstrap file → adds the file through explicit update".

### 4. `gator init` handoff
- Files: `src/gator_command/scripts/gator-init.py` and the starter-template `scripts/gator-init.py` (same edit in both, preserving their existing intentional divergence).
- What:
  - `session_opening_directive(repo_root, paths)`, when `paths.bootstrap` is a file, returns:
    ```
      session opening is not finished. Read, in order:
        1. .gator/.includes/GATOR_INIT.md  — Gator's entry point for this session
        2. .gator/.includes/constitution.md  — the rules; read before your first response
        3. .gator/mission.md · roadmap.md · inbox.md  — what · where · open work
    ```
    The paths are resolved, not literal.
  - When the file is absent, it returns the current two-line directive unchanged, plus one line: `note: this repo predates .gator's GATOR_INIT.md — \`gator update\` adds it`.
  - It never writes. It stays inside the existing try/except so it is fast, offline and non-fatal.
  - `print_json` adds `"session_opening": {"bootstrap": <rel path or null>, "bootstrap_present": bool, "reads": [<rel paths in order>]}`.
- Why: Sketch §2 ("names the resolved `GATOR_INIT.md` path first", legacy fallback, never create on open). It keeps the "not finished" safeguard from the repo-lifecycle charter.

### 5. Stop native-file management in install and update
- File: `gatorize.py`.
  - Remove the `action_install_entry_points(...)` call from the common tail, and remove its import and the `render_entry_content` import.
  - In `print_pre_action_summary`, remove both "Install(/refresh) entry-point files" lines and add "Leave CLAUDE.md / AGENTS.md / GEMINI.md untouched (repository-owned)".
  - Update the `post_install.py` cleanup hint (`.gator/, entry-point files` → `.gator/`).
- Files: `gator-update.py` and the starter-template `gator-update.py`.
  - Delete `_ENTRY_POINT_META`, `plan_entry_point_updates`, `execute_entry_point_updates`, the `_ENTRY_POINT_REFRESH_AVAILABLE` import guard and (template copy) the inlined managed-block helpers that only served them.
  - In `main`, drop the entry-point plan/execute, and base `made_changes` on overlay counts only.
  - Simplify `print_plan` / `print_result` to stop rendering entry-point lines.
  - `print_json_plan` keeps emitting `entry_point_actions: []` and `summary.entry_point_actions: 0`, for `gator-update-v1` compatibility.
- Why: Sketch §3. There are no native-file creates, prompts, `*_ROLLBACK.md` files, `.pre-gator-update` backups or sentinels. Existing blocks stay byte-for-byte unchanged (sketch §4).

### 6. `gator state` compatibility boundary
- File: `src/gator_command/scripts/gator-state.py`.
- What:
  - **Schema:** `SCHEMA = "gator-state-v2"`.
  - **`collect_status`:** drops `entry_points` / `entry_point_baseline_kind` and adds `native_files`. That is a list over the three filenames: `{filename, present: bool, managed: false, historical_gator_block: bool, local_companion: "present"|"absent"}`.
    - `historical_gator_block` is a read-only check, true when `find_managed_block(text)` returns a location or `detect_legacy_gator_content(text)` is true.
    - It keeps the version diagnostic and `constitution`.
  - **`render_status_text`:** prints a `native agent files (not managed by Gator):` section. Each file shows `absent`, `present` or `present · historical Gator block (not refreshed)`, and the section never uses drift, failure or repair vocabulary.
  - **`gator state repair`:** accepts the same arguments for compatibility but plans and executes nothing. Text output: "Nothing to repair: Gator no longer manages CLAUDE.md / AGENTS.md / GEMINI.md. Historical Gator blocks are left as-is; edit or remove them yourself." JSON: `{schema, dry_run, actions: [], native_files: "not-managed", constitution: "repair-deferred-v1", local_companions: "preserved"}`. It exits 0.
  - Delete `classify_entry_point`, `plan_repair`, `_plan_action_for_state`, `execute_repair`, `_execute_one`, `_fresh_file_content` and the `render_entry_content` / `upgrade_legacy_entry_point` imports. `*.local.md` stays existence-check only.
- Why: Sketch §5. A default `gator state` must not report an untouched `AGENTS.md` as unhealthy. Historical state is reported transparently (§4).

### 7. Remove the unused renderer and writers
- File: delete `src/gator_command/scripts/gatorize/entry_points.py`.
- What: after changes 5 and 6 it has no callers. `gatorize/managed_block.py` stays: `find_managed_block` / `detect_legacy_gator_content` serve the read-only historical detection. `classify_managed_block` and `render_managed_region` stay with their existing unit tests, which are cheap and keep a future adapter option. Packaging is unchanged because of the `scripts/gatorize/**/*` glob.
- Why: leaving a dead renderer would invite a split-brain second instruction source (sketch: "Avoid split-brain instructions").

### 8. Loop-join prompt reinforces the explicit start
- File: `src/gator_command/scripts/gator-dashboard.py` (loop-join prompt builder).
- What: append one pointer line after the status command: `  New to Gator in this repo? Run \`gator init\` first; its handoff names GATOR_INIT.md and the loop protocol.` This is additive; the existing lines are unchanged.
- Why: Sketch, "Explicit start must be reliable", and the test case "loop join still works in a repo with no native agent files". Today the join prompt relies on the native-file block to teach what "gator loop join" means.

### 9. Documentation and adoption (inventory-driven)
- **Inventory method (done for this revision, re-run at implementation time):**
  - Scope: `README.md`, `CONTRIBUTING.md`, `docs/`, every `.md` under `src/gator_command/templates/gator-starter/`, every `.md` under `.gator/.includes/`, and `.claude/commands/`.
  - Search: `grep -rIE` for `CLAUDE\.md|AGENTS\.md|GEMINI\.md|GATOR:BEGIN|managed block|entry[- ]point|_ROLLBACK|pre-gator-update|Pre-Gator Instructions`.
  - Treatment: every hit is classified below. A hit that appears at implementation time but is missing from this table is classified with the same rules before checkpoint 4 is submitted. The implementation artifact records the re-run.
- **Revise: behavior guidance that states the retired ownership model or makes native files Gator's required entry point.** Template files and their `.gator/.includes/` dogfood copies are edited identically; all of them are byte-identical today.

  | File | Hits | Revision |
  |---|---|---|
  | `README.md` | l.27, l.116 | "Adds or updates CLAUDE.md…" becomes "Adds `.gator/` (including `GATOR_INIT.md`); never edits your CLAUDE.md/AGENTS.md/GEMINI.md". The update paragraph drops the managed-region and `.pre-gator-update` sentence and gains a migration note for historical blocks. |
  | `docs/how-to-use-gator.md` | l.52–54, l.271–272, l.295 | The repo-tree listing shows `.gator/.includes/GATOR_INIT.md`; native files appear only as "optional, yours". The "three surfaces" text becomes "Gator content in `.gator/`, team-owned native files, `*.local.md`". The update paragraph is rewritten like the README's. l.265 ("Dashboard … entry point for restarting") is a false positive; keep it. |
  | `docs/architecture.md` | l.29–31, l.80–82 | Tree: native files become "optional, repository-owned". Model flow becomes "any model: `gator init` → `GATOR_INIT.md` → constitution → charters"; native files may point to `gator init`. |
  | `docs/custom-skills-and-team-workflow.md` | l.12–13, 35–121 | Rewrite the "What happens to your custom instructions" section. The files are fully yours, Gator never edits them, and the `.pre-gator-update` / overwrite troubleshooting entries are replaced with a "historical Gator block" entry. Precedence becomes: Gator governance in `.gator/` → team content (native files, `.gator/procedures/`) → `*.local.md`. The three screenshot TODOs about the managed block and backup are removed; the tracked-vs-local TODO stays. |
  | `procedures/enforcer-review.md` (template + dogfood) | l.50, 78, 104, 116, 192, 201, 203 | Replace "`AGENTS.md`/`CLAUDE.md` is the primary-agent entrypoint" with: "the repository's own `CLAUDE.md`/`AGENTS.md`, if present, is vendor context the CLI reads automatically and may frame the model as the primary agent; Gator sessions start from `gator init`". The enforcer-role guidance is unchanged: use the dedicated enforcer prompt / `enforcer-review.py`. |
  | `reference-notes/enforcer-configuration.md` (template + dogfood) | l.60, 97, 149 | Same rewording as `enforcer-review.md`. |
  | `reference-notes/concierge-responses.md` (template + dogfood) | l.245–268, 372, 386, 400, 466 | The "My CLAUDE.md is really long" answer is rewritten: Gator no longer appends to it, the session starts from `gator init`, and a long native file only competes for attention. l.372/386/466 get the enforcer rewording. l.400 "writes entry points" becomes "installs `.gator/` (with `GATOR_INIT.md`)". |
  | `reference-notes/local-agent-skills.md` (template + dogfood) | 7 hits | Rewritten: native files are repository-owned, `*.local.md` is a user convention that Gator only gitignores, and older Gator blocks are historical. |
  | `reference-notes/what-gator-requires-from-a-model.md` (template + dogfood) | l.25, 75, 83 | "Honor the entry point" becomes "run `gator init` and follow `GATOR_INIT.md`"; the l.83 inventory item becomes `.gator/.includes/GATOR_INIT.md`. l.75 (short entry point) is rewritten for `GATOR_INIT.md`. |
  | `procedures/gator-version-drift.md` (template + dogfood) | l.46, 78 | Drop "modified managed blocks" as a drift category. The l.78 paths list drops entry-point blocks and adds `GATOR_INIT.md` under shipped content. |
  | `procedures/knowledge-capture.md` (template + dogfood) | l.57 | Becomes "If your repo keeps vendor files (`CLAUDE.md`…), a one-line pointer to `gator init` is enough; keep project knowledge in `.gator/`." |
  | `CHANGELOG.md` `[Unreleased]` | new | Changed / Removed / Migration notes. |

- **Preserve: historical, research, or unrelated.** Each row has its reason.

  | File | Reason |
  |---|---|
  | `docs/supporting-research.md` l.53, 80, 117 | Citations of external studies about vendor instruction files; not a Gator behavior claim. |
  | `docs/what-is-navigation-coding.md` l.33, 39, 212 | Research essay and bibliography. |
  | `procedures/authoring-html-artifacts.md` l.6; `reference-notes/example-project.md` l.12, 210; `reference-notes/refactor-approach.md` l.82, 94, 119, 150 | "Entry point" in the generic code/CLI sense; false positives. |
  | `.gator/.includes/reference-notes/where-gator-is-now-and-where-it-is-going.md` l.28, 252 | "Dashboard as entry point" (dogfood-only note); false positive. |
  | `.gator/.includes/reference-notes/positioning-hierarchy.md` l.25; `gator-positioning-brief.md` l.216 | Market positioning against instruction-file tools. This is consistent with the new model; dogfood-only. |
  | `.gator/.includes/reference-notes/gator-layering-over-agent-and-spec-stacks.md` l.97 | "Let `CLAUDE.md` remain the user-facing entrypoint" already matches the repository-owned model; dogfood-only. |
  | `CHANGELOG.md` existing entries | Historical record. |
  | `.claude/commands/*` | No hits. |

- **Not documentation, already covered elsewhere:** this repository's own root `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` are historical state and stay byte-unchanged (Assumptions). The starter `scripts/gator-pre-commit.py` l.118 lists `CLAUDE.md`/`AGENTS.md` as a non-code filename allowlist for charter enforcement; that is behavior-neutral and unchanged.
- Why: Sketch module 4 (documentation and adoption) and Finding 1. The released guidance must not contradict the `gator init` → `GATOR_INIT.md` contract.

## Dependencies and Ordering

- **1 → 2 → 3 → 4:** the bootstrap file must exist and be classified before install, update and init can place or name it.
- **5** depends only on the existing code and can follow 4. It must come before 7.
- **6 before 7:** `gator-state.py` imports `entry_points.py`, so state must stop importing it before deletion.
- **Test retargeting:** `TestWaitHandoffAlignment` / `TestExecutiveSummaryProducerPaths` in `tests/test_loop.py` currently pin `render_entry_content` and the live root native files. They are retargeted in the same checkpoint as 7.
- **8 and 9** are last. They depend on the final behavior they describe.

## Assumptions, Risks, and Required Architect Decisions

- **Assumption (non-blocking):** `GATOR_INIT.md` is a shipped root file resolved through `.includes/` on v2, not pinned at the visible `.gator/` root. Reversible: moving it means changing its classification and one `_shipped_file` call.
- **Assumption (non-blocking):** optional `gator adapters` are deferred out of this release.
- **Assumption (non-blocking):** the `gator state repair` stub is kept for at least this minor series. Removing it later is a separate Architect decision.
- **Assumption (non-blocking):** `gator-state` bumps to v2, and `gator-update-v1` keeps its keys with empty values.
- **Assumption (non-blocking):** this repository's own `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` stay byte-unchanged. Their managed blocks become historical. Whether to trim them is the Architect's separate choice, not part of this change.
- **Assumption (non-blocking):** these stay untouched, because the sketch treats vendor integration as separate:
  - `.claude/commands/*.md` (including `/init`, which already gives its own read chain), and the Claude/Codex/Gemini vendor-hook settings that the `.claude`/`.codex`/`.gemini` install step writes;
  - the `.gitignore` `*.local.md` entries.
  
  A follow-up could make `/init` read `GATOR_INIT.md`.
- **Risk: stale historical blocks.** Existing repos keep a frozen Gator block that will drift from current guidance, including loop-wait wording. Mitigation: `GATOR_INIT.md` states precedence, `gator state` labels the block "not refreshed", and the CHANGELOG migration note tells owners they may remove it.
- **Risk: weaker automatic discovery.** A model that never runs `gator init` in a fresh repo gets no Gator guidance. This is the trade-off the sketch accepts (Non-Goals). Mitigation: change 8 and the docs.
- **Risk: mixed-layout residue.** A user who copies `GATOR_INIT.md` to the flat `.gator/` root on v2 makes the repo `mixed`, the same rule as for `constitution.md`. `--migrate-layout` reports and handles it.
- **No blocking Architect decision identified.**

## Testing

Each test proves one distinct behavior. Equivalent cases are parameterized.

- **Bootstrap contract (checkpoint 1):**
  - `tests/test_layout.py`:
    - `bootstrap` resolves to `.includes/GATOR_INIT.md` on v2 and `.gator/GATOR_INIT.md` on v1, in one parameterized test;
    - a flat-root `GATOR_INIT.md` on v2 → `mixed`;
    - a v2 repo without the file stays `v2`, so the legacy repo is not bricked.
  - `tests/test_init.py`:
    - the directive lists the bootstrap first when present;
    - when absent, the directive is the legacy two-step plus the hint, and the file is still absent afterwards (never created on open);
    - `--json` has `session_opening` with matching `reads`.
  - Install/update placement:
    - one gatorize fresh-install test asserting `.gator/.includes/GATOR_INIT.md` exists;
    - one `gator update` test on a v2 repo lacking it: added on the first run, unchanged on the second (idempotent).
  - Content guard: template vs dogfood byte identity. The file names `constitution.md`, `gator loop status` and `procedures/gator-loop-protocol.md`, and does **not** contain `--max-seconds` or `Executive Summary`, which pins single-source.
- **Native-neutral install/update (checkpoint 2):**
  - One parameterized test runs `gatorize --yes` on a repo with all three native files, using complex foreign, clean-sentinel and legacy fixtures.
    - It asserts their bytes are unchanged, no `*_ROLLBACK.md` exists, and no stdin read happens.
    - A no-native-files variant asserts no native files are created.
  - One parameterized `gator update` test over repos whose native files carry a clean, modified or legacy Gator block. It asserts the bytes are unchanged and no `.pre-gator-update` backup exists.
  - The `print_json_plan` test asserts `entry_point_actions == []` in both copies.
  - Remove the obsolete `tests/test_update_entry_points.py`, the `TestBehavioralParityPlan` / `TestBehavioralParityExecute` classes and the `TestASTEquivalenceOfInlinedHelpers` class (the helpers are gone), plus the entry-point-creation assertions in `tests/test_gatorize.py`.
- **State boundary (checkpoint 3):**
  - `tests/test_state.py` is rewritten:
    - status v2 over absent, team-owned and historical-block files: schema, `managed: false`, `historical_gator_block` and no drift vocabulary in text (parameterized);
    - `repair` (with and without `--dry-run`/filename) leaves every native and `*.local.md` file byte-identical, writes no rollback and exits 0;
    - a `*.local.md` file is never opened.
  - Retarget `TestWaitHandoffAlignment` and `TestExecutiveSummaryProducerPaths` (`tests/test_loop.py`) to drop the `render_entry_content` and live root native-file surfaces. The protocol and `/loop-join` pairs remain pinned.
  - `tests/test_managed_block.py` is unchanged.
- **Adoption (checkpoint 4):**
  - A Dashboard loop-join prompt test asserts the `gator init` pointer line.
  - A session-opening smoke test in a temp repo with no native files: gatorize, then `gator init`, prints the bootstrap path, and the dashboard prompt contains the pointer.
  - **Retired-claim regression guard** (new `tests/test_native_file_guidance.py`, answering Finding 1). This is one parameterized source-inventory test.
    - *Maintained surfaces:* every `.md` under `src/gator_command/templates/gator-starter/` (including `GATOR_INIT.md`), plus `README.md`, `docs/how-to-use-gator.md`, `docs/architecture.md` and `docs/custom-skills-and-team-workflow.md`.
    - *Excluded by name, with the reason in a comment:* `CHANGELOG.md`, `docs/supporting-research.md` and `docs/what-is-navigation-coding.md` (historical or research citations).
    - *Retired-claim patterns* (case-insensitive), any match of which fails with the file and line:
      1. `\.pre-gator-update`
      2. `_ROLLBACK\.md`
      3. `Pre-Gator Instructions`
      4. `primary-agent entry ?point`
      5. `Gator (manages|refreshes|updates) (a |the |its )?(managed )?(block|region)`
      6. `(writes|installs|creates) (the )?entry[- ]points?`
      7. `adds or updates .?(CLAUDE|AGENTS|GEMINI)\.md`
    - Historical mentions such as "older Gator versions wrote a `GATOR:BEGIN` block" stay allowed. Generic code "entry point" wording is not matched.
    - The same file also asserts that each revised template/dogfood pair from Change 9 is byte-identical. The seven starter pairs are `enforcer-review.md`, `enforcer-configuration.md`, `concierge-responses.md`, `local-agent-skills.md`, `what-gator-requires-from-a-model.md`, `gator-version-drift.md` and `knowledge-capture.md`.
    - Before the docs are revised, this test fails on the known hits, which proves it detects them. After the revision it passes.
- **Final approval:** `python -m pytest tests -q` once, plus `contracts/compatibility` if the test runner includes it.

## Charter Impact

- `scripts-layout.md`: `GATOR_INIT.md` in `SHIPPED_ROOT_FILES`, the `GatorPaths.bootstrap` field, and both copies in sync.
- `scripts-repo-lifecycle.md`: the `session_opening_directive` bootstrap-first order, the legacy fallback with the never-write rule, and the `print_json` `session_opening`.
- `scripts-installer.md`:
  - Remove "managed agent-entry blocks" from Owns, and the `render_managed_region() / render_entry_content()` and `action_install_entry_points() / upgrade_legacy_entry_point()` entries.
  - Add the TRIPWIRE "Native agent files are repository-owned: install never creates, prompts about, backs up, or edits them".
  - Note `GATOR_INIT.md` in `action_install_gator`.
  - Keep `find_managed_block()` / `classify_managed_block()` as read-only parsing.
- `scripts-repo-update.md`: remove the `plan_entry_point_updates() / execute_entry_point_updates()` entry and the "entry-point" wording in Owns. Note that `entry_point_actions` stays an always-empty `gator-update-v1` key.
- `scripts-managed-state.md`: largely rewritten. Owns becomes informational native-file reporting, constitution drift and the repair compatibility stub. The schema is `gator-state-v2`. The Two Baselines TRIPWIRE reduces to the constitution baseline. The `*.local.md` TRIPWIRE stays.
- `scripts-cross-cutting.md`: Shipped-Copy Synchronization no longer lists the entry-point renderer or the live CLAUDE/AGENTS/GEMINI regions as pinned surfaces (the #53 note and `TestWaitHandoffAlignment` / `TestExecutiveSummaryProducerPaths` descriptions). Add the `GATOR_INIT.md` template↔dogfood pin, and record the `gator-state-v2` bump.
- `scripts-dashboard.md`: the loop-join prompt gains the `gator init` pointer line.
- `INDEX.md`: no routing change.

## Coding Checkpoints

1. **Bootstrap contract and handoff** — Add `GATOR_INIT.md` (template + dogfood). Classify and resolve it in both `gator_layout.py` copies. Place it through gatorize and both `gator-update.py` `TEMPLATE_FILES`. Make both `gator-init.py` copies name it first, with the never-writing legacy fallback and the `session_opening` JSON. Update the layout, lifecycle and installer charters. Verify: `pytest tests/test_layout.py tests/test_init.py` plus the new placement/idempotence and content-guard tests.
2. **Native-neutral install and update** — Remove entry-point install from the gatorize tail and summary. Remove entry-point plan/execute (and the template copy's inlined helpers) from both `gator-update.py` copies, keeping the always-empty `entry_point_actions` JSON key. Update the installer and repo-update charters. Verify: `pytest tests/test_gatorize.py tests/test_template_sync.py` plus the new parameterized byte-preservation tests for gatorize and update.
3. **State boundary and renderer retirement** — Move `gator state` to `gator-state-v2` with informational `native_files` and a no-write repair stub. Delete `gatorize/entry_points.py`. Retarget the loop handoff/Executive Summary alignment tests away from the renderer and live native files. Update the managed-state and cross-cutting charters. Verify: `pytest tests/test_state.py tests/test_managed_block.py tests/test_loop.py -k "Alignment or ExecutiveSummary or DriftGuards" tests/test_packaging.py`.
4. **Explicit-start adoption** — Add the Dashboard loop-join `gator init` pointer line. Re-run the Change 9 inventory, and revise every "Revise" row (README, the three docs, the seven starter procedure/reference-note files and their dogfood copies) plus the CHANGELOG migration notes. Add the retired-claim regression guard. Update the dashboard charter. Verify: the Dashboard join-prompt test, the no-native-files session-opening smoke test and `pytest tests/test_native_file_guidance.py`; then the final broad `python -m pytest tests -q` once.
