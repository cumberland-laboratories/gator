# Changelog

All notable changes to Gator are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/). Gator uses [semantic versioning](https://semver.org/).

## [2.11.1] — 2026-08-30

Blueprints view canvas hardening — v2.11.0 shipped with the canvas frame pinned at the vault-HTML authored 1180×880 dimensions, which pushed the detail panel off-screen at normal browser zoom on <1500px viewports (the Architect had to reduce browser zoom to ~80% to see the whole surface). Fix restructures the frontend layout so the outer frame is responsive and the fixed dimensions live on an inner stage.

### Fixed

- **Blueprints view canvas is now responsive.** `bp-canvas` becomes a scrollable outer frame that grows/shrinks with available viewport space (`flex: 1 1 auto; min-width: 0; overflow: auto`). New inner `bp-stage` container carries the fixed intrinsic dimensions from the payload's `canvas` field. Nodes and SVG edges live inside the stage. When the stage exceeds the frame's visible area, the frame scrolls internally instead of pushing the detail panel off-screen. Tighter chrome elsewhere (16px gap/padding vs 20px, detail panel fixed at 360px with tighter min/max) so both panels fit at normal zoom on 1440-wide laptop screens. Charter TRIPWIRE added in `scripts-dashboard.md::Blueprints view` naming the canvas-vs-stage split so future edits don't accidentally re-pin fixed dimensions on `bp-canvas`.

### Compatibility

- No breaking changes. Endpoint contract unchanged; only the frontend's DOM structure changed.
- Pre-fix `l1-data.json`/`l1-positions.json` files are unchanged and continue to serve.

## [2.11.0] — 2026-08-30

Blueprints 2.0 Release A — first shipped increment of the roadmap Priority 2 track. A new Dashboard-native `Blueprints` view renders the Gator source repo's Level 1 charter map inside the Dashboard shell, ported from the vault experiment at `.gator/vault/blueprints/charter-flowchart-high-level.html`. This release ships the browse surface, the endpoint, and the shipped data files that the Release B charter parser will supersede without changing the frontend contract.

### Added

- **Dashboard `Blueprints` view** under the Knowledge sidebar group (peer of `Docs`). Renders the L1 charter map as an SVG canvas + absolute-positioned nodes with click-to-isolate 1-hop-neighborhood interaction, a right-side detail panel (summary, covered files, representative functions, depends-on, used-by), and an "experimental" topbar label. New file `src/gator_command/scripts/dashboard/views/blueprint.js`, ~300 lines, plain-callable `window.GatorViews.blueprint = function (data, container, repoName)` matching the actual shell contract.
- **Endpoint** `GET /api/repo/<name>/blueprint?level=1` in `gator-dashboard.py`. Non-1 level returns HTTP 501 (Release B+ ships higher levels). Gator-source-repo detection is on-disk artifact discovery (per plan D3): if `<repo_path>/src/gator_command/scripts/dashboard/blueprint/l1-data.json` exists, the endpoint serves the merged L1 payload. Otherwise it returns a structured empty-state (`{status: "unavailable", reason: "release-b-pending"}`) and the frontend renders an information card explaining Release B is the enabler. The empty-state contract is load-bearing: never falls back to Gator's dataset for a non-Gator repo (whiteboard finding pin — teaching users wrong data at the per-repo Knowledge seam is exactly the failure mode this contract exists to prevent).
- **Shipped data**: `dashboard/blueprint/l1-data.json` (13 nodes / 29 edges, one-time hand-extraction from the vault HTML) + `dashboard/blueprint/l1-positions.json` (hand-tuned `{x, y}` per node id, kept as a separate overlay so the Release B parser can regenerate data without stomping positions).
- **Charter TRIPWIREs**: `scripts-cross-cutting.md` gets a new pattern entry ("Repo-Scoped Dashboard Endpoints — Per-Repo Data or Structured Empty-State") that applies to any future per-repo Dashboard endpoint; `scripts-dashboard.md` gains a Blueprints view function entry with three TRIPWIRE bullets pinning the single-slot invariant, the no-silent-fallback contract, and the empty-state-vs-error-state reason branching.

### Changed

- `dashboard/snapshot.py` — the offline HTML snapshot inliner extended to include the new `views/blueprint.js` in its expected script sequence. Without this, the inliner's regex fell through with no match and produced un-inlined HTML (caught by 4-test regression in `test_snapshot.py` during the release sweep, fixed before commit).
- Sidebar item dimming logic in `dashboard.js` extended so `blueprint-tab` un-dims when a repo is active, matching how `docs-tab` behaves.

### Compatibility

- No breaking changes. Existing Dashboard views (fleet, history, repo, docs, updates, settings) are untouched.
- Machines pipx-upgraded from v2.10.0 gain the new sidebar item automatically. The view is only functionally populated for the Gator source repo in Release A; all other repos see the structured empty-state.
- Snapshot HTML now inlines the blueprint view alongside the others (no change to the snapshot output for non-Gator repos in Release A — the empty-state renders offline the same way it does live).
- Deferred to Release B (v2.12.0): `gator-blueprint.py` charter parser. Deferred to later releases: L1 tooltip pack + edge-type visual distinction + snapshot L1 payload (Release C, v2.13.0); L2 drill-down (Release D, v2.14.0); L3 curated function map + L4 drift map (Release E).

### Notes

- Plan chain: `.gator/vault/artifacts/2026-08-30-blueprints-2-0-implementation-plan.md` (r3, Architect-ratified 2026-08-30) synthesized from the Codex "dashboard-first" sketch (`2026-08-30-blueprints-2-0-dashboard-first-sketch.md`) plus the prior Opus r1 draft (`.gator/artifacts/2026-08-25-blueprints-2-0-implementation-plan.md`). The r2/r3 whiteboard revisions specifically fixed a fabricated view-registration contract (r1 invented `{init, render, cleanup}` and a separate `bp-view` slot that don't exist) and a wrong-data-under-another-repo's-name recommendation that would have shipped had the enforcer not caught it.
- **Post-Release-A whiteboard fix landed pre-bump** (`0100933`): the initial Release A implementation used the same `status: "unavailable"` response shape for both the intentional gate (`reason: "release-b-pending"`) and real degradation (`reason: "shipped-data-unreadable"`), and the frontend collapsed both into the same "Release B ships it" empty-state card. Enforcer flagged this as presenting genuine breakage as a product-progress teaser — misleading + hides the fix path. Fixed by branching on `reason` in the frontend (`views/blueprint.js`), adding a self-contained `message` field to the shipped-data-unreadable payload with actionable copy ("Reinstalling gator-command usually restores them"), and pinning both branches with two regression tests (`TestBlueprintEndpointShippedDataUnreadable::test_shipped_data_unreadable_returns_distinct_reason` + `test_release_b_pending_and_shipped_data_unreadable_are_different_reasons`).

## [2.10.0] — 2026-08-29

Machine-scoped Python launcher preference. First feature release built on the v2.9.3 hook-shebang fix: instead of re-auto-detecting on every hook regeneration, an operator (or agent) can now record a durable machine-local override in `~/.gator/preferences.json` — the file every future machine-preferences feature will extend rather than replace.

### Added

- **Unified machine-preferences file at `~/.gator/preferences.json`** (schema `gator-preferences-v1`, contracts/schemas/gator-preferences-v1.json). Phase 1 of the machine-preferences architecture: this release populates the `python:` section; the schema also reserves a `hooks:` section for a follow-on release, so the file layout is stable before further work extends it. `additionalProperties: true` at every level for additive forward-compat. Contract test: `contracts/compatibility/test_preferences_schema.py` (13 checks).
- **`gator_core.read_preferences()`** returns a discriminated result — `{"state": "absent"}` / `{"state": "malformed", "reason": ...}` / `{"state": "present", "data": {...}}` — never `Optional[dict]`. The distinction is load-bearing: callers can distinguish "no preference set" (safe to fall back) from "user configured something and it's broken" (must be surfaced loudly, never silently ignored). BOM-tolerant. Never raises.
- **`gator_core._validate_launcher_candidate(path, for_shebang=True)`** — the four hook-shebang rules (basename `py.exe`, absolute, spaceless, exists) as a single function returning `(valid, reason)`. Existence checked last so configuration reasons (basename-mismatch, relative-path, spaced-path) surface even when the file is missing.
- **`gator_core.resolve_python_launcher_for_hooks()`** — canonical Windows Python-launcher resolver. Windows only; non-Windows returns `not-applicable`. Preference file wins over auto-detect; a malformed OR invalid user preference refuses loudly with `source="user"` (never silent fallback — falling back would defeat the override the user just wrote). Returns a structured result with a `checked` audit trail listing every tier the resolver tried and why each succeeded or failed.
- **Shipped procedure `procedures/configure-machine-preferences.md`** — operator/agent recovery documentation for setting `~/.gator/preferences.json` by hand. Named for the unified file so the future hook-mode section extends the same document. Available immediately on next `gator update`.

### Changed

- **`gator-update.py::_hook_shebang()` is now a thin wrapper** around `resolve_python_launcher_for_hooks()`. Every existing v2.9.3 behavior on machines without a preferences file is preserved byte-for-byte — the change is that a preferences file, if present, now overrides auto-detection. Refusal messages gain a rendered `checked:` audit trail so operators can see every tier the resolver tried. Both `src/gator_command/scripts/gator-update.py` and its template twin.
- Charter TRIPWIREs: `scripts-cross-cutting.md` Managed Hook Path Migration now names the resolver as the source of truth; `scripts-repo-lifecycle.md::build_git_hook_wrappers` gains a "do not re-inline the shebang probe" invariant so future callers route through the resolver.

### Compatibility

- No breaking changes. Machines without `~/.gator/preferences.json` behave exactly as they did in v2.9.3.
- Existing Windows repos get their hook stubs regenerated on the next `gator update` (content diff — the new refusal-message shape is a rendered `checked:` trail rather than an inline description).
- Deferred to follow-on releases: `gator prefs` CLI (Phase 4); `hooks:` section content and hook-mode resolver (companion `2026-08-29-machine-scoped-hook-mode-and-preferences-sketch.md`); `gator init` boot-payload `hooks.launcher_*` diagnostic fields (Phase 5).

### Notes

- The initial implementation was reviewed pre-release and three whiteboard findings were fixed on the same train before this bump:
  - `5cb4197`: (1) `read_preferences()`'s shape check was tag-only, so a tagged-but-wrongly-shaped payload like `{"schema": "gator-preferences-v1", "python": []}` slipped through as `present` and crashed the resolver's `.get()` chain — now `_validate_preferences_shape()` type-checks every documented section and field, and wrong shape returns `state: "malformed"`; (2) `python.allow_for_hook_shebang` was published in the schema/fixture/procedure but the resolver ignored it — resolver now honors the field (default `true`; `false` opts out and falls through to auto-detect).
  - `3ef16ed`: (3) `python.windows_py_launcher: ""` violated the shipped schema's `minLength: 1` at runtime — the shape validator accepted empty strings (they ARE strings), then the resolver's `if not launcher:` shortcut lumped `""` with the field-missing case and silently fell through to auto-detect. Recreated the silent-fallback class the feature is specifically meant to forbid. Two-layer fix: shape validator now rejects empty `windows_py_launcher` at the reader boundary (returns `state: "malformed"`); resolver replaces `if not launcher:` with `if launcher is None:` so any empty string that ever reaches it routes through the validator (`empty-path`) and refuses loudly with `source: "user"`.
  All three fixes have regression pins.

## [2.9.3] — 2026-08-28

Field-fix trio for Windows hook installation and the v2.9.2 `--dry-run --migrate-layout` JSON contract, with a whiteboard-follow-up so the shebang refusal actually surfaces at session-open.

### Fixed

- **Git hooks no longer silently break on per-user / Microsoft Store Python installs** (field report). The pre-commit / commit-msg / post-commit hook wrappers hardcoded `#!C:/Windows/py.exe -3` in their shebang, and `C:\Windows\py.exe` only exists on system-wide ("install for all users") Python installs — per-user and Microsoft-Store installs put the launcher under `%LOCALAPPDATA%\Programs\Python\Launcher\py.exe`. Git-bash tried to exec the shebang, found no interpreter, and every hook silently failed to invoke, skipping pre-commit governance entirely. `_hook_shebang()` in both `gator-update.py` copies now resolves the launcher dynamically at hook-generation time: `shutil.which("py")` → `%LOCALAPPDATA%\Programs\Python\Launcher\py.exe` → `C:\Windows\py.exe`. Every candidate is space-checked (POSIX shebang syntax cannot quote paths with spaces, and `%LOCALAPPDATA%` under a spaced username would produce a broken shebang). If no tier yields a spaceless launcher, hook install refuses loudly via a new `HookShebangUnresolvable` exception — never silently writes a broken hook. Pins: `tests/test_hooks.py::TestHookShebang` (5 new tests) + `TestUnresolvableShebangRefusal`.
- **`gator update --json --dry-run --migrate-layout` returns structured JSON** instead of the interactive prose it emitted in v2.9.2. The 2026-08-23 gate that refused the flag combination returned unconditionally before the JSON branch could fire, breaking the JSON contract for Dashboard and scripting consumers. The gate now emits `{"schema": "gator-update-v1", "action": "migrate-layout-refused", "reason": ..., "layout": ...}` with exit 0 when `--json` is set; interactive prose path unchanged. Pins: `tests/test_layout.py::TestMigrateDryRunGate` (3 new tests).
- **`ensure_git_hooks()` surfaces the shebang refusal at session-open**. Whiteboard-caught follow-up: `plan_hook_updates()` catches `HookShebangUnresolvable` and returns `[]` to keep the `gator update` path clean, but `[]` is indistinguishable from "no changes needed" at `ensure_git_hooks()`'s call site — so on machines the shebang fix is meant to protect, session-open silently returned `{'status': 'ok'}` instead of the intended loud refusal. `ensure_git_hooks()` (both copies) now probes `_hook_shebang()` directly before calling `plan_hook_updates()`; on `HookShebangUnresolvable` it returns `{'status': 'degraded', 'detail': 'hook shebang unresolvable: ...'}`. Pin: `tests/test_init.py::TestEnsureGitHooks::test_unresolvable_shebang_reports_degraded_not_ok`.

## [2.9.2] — 2026-08-23

Fix trio from a single field case: a repo whose Dashboard Update button silently "did nothing."

### Fixed

- **User reference notes at `.gator/reference-notes/` no longer brick updates.** The docs present root `reference-notes/` as user content, but the layout resolver classified the directory as fully-shipped — one user-authored note at root made the repo resolve as `mixed`, which `gator update` refuses permanently. `reference-notes/` is now a mixed directory like `procedures/`: shipped files are detected per-filename (template-derived, with a bootstrap fallback), user notes at root are valid v2 content, and `--migrate-layout` preserves them at root instead of sweeping them into `.includes/`. Pins: `tests/test_layout.py::TestReferenceNotesReclassification`, rewritten `test_shipped_dir_duplicates_get_removed`.
- **`--dry-run` now actually gates `--migrate-layout`.** Previously `gator update --migrate-layout --dry-run` executed the full migration — real file moves and hook regeneration under a flag that promises no changes. The combination now prints the current layout resolution and how to run for real, and changes nothing. Pin: `TestMigrateDryRunGate`.
- **The Dashboard no longer swallows update/gatorize failures** (issue [#1](https://github.com/cumberland-laboratories/gator/issues/1)). The backend always returned the CLI's output on failure, but the Fleet view hid it in a hover-tooltip on a small red `!`. Both the Update and Gatorize handlers now surface the CLI's actual output in a visible alert (tooltip retained).

## [2.9.1] — 2026-08-23

First machine-side agent-education fix delivered through the 2.9.0 runtime split: one CLI release, zero per-repo diffs.

### Fixed

- **`gator init` banner no longer reads as session-opening completion.** Field observation (Opus 4.7): models took the `✓ constitution … rules in force` existence-check as "constitution loaded" and the closing tagline as "done", skipping the constitution read — and with it the mission/roadmap/inbox reads that chain from it. The banner now ends with an explicit handoff: *"session opening is not finished. Read, in order:"* naming the constitution by its one layout-resolved path (no conditional two-path lookup) plus the three context reads. New `session_opening_directive()` in both `gator-init.py` copies; ordering pinned end-to-end (`tests/test_gator_core.py::test_banner_ends_with_session_opening_directive`).

## [2.9.0] — 2026-08-23

**The runtime split.** Gator-governed repos no longer carry the enforcement runtime — they commit **policy plus a pin**, and the runtime executes from the installed CLI on each machine. This is Git's own `repositoryformatversion` pattern applied to governance: the committed `.gator/runtime-pin.json` records the minimum runtime version the repo's governance requires; an older installed CLI refuses fail-closed with an upgrade instruction, a newer one runs and `gator update` advances the pin. Updating Gator across a fleet becomes one `pipx upgrade` plus a two-file diff per repo, instead of a ~30-file script sync into every repo and branch. Direction, plan, and all six phases Architect-ratified (roadmap item 19; runtime-split plan r9, fleet-wide dogfood on 12 repos).

### Added

- **`gator hook <name>` dispatcher** (`gator-hook.py`): machine-side entry point for `pre-commit | commit-msg | post-commit | session-open | session-start | enforcer-review | approve`. Git hooks are now thin pin-aware stubs — pin present → dispatch to the installed CLI; pin absent → byte-for-byte pre-split repo-script invocation, so old branches and old checkouts behave exactly as they always did. Pins: `tests/test_gator_hook.py`, `tests/test_hooks.py::TestPinAwareWrappers`.
- **`.gator/runtime-pin.json`** (`gator-runtime-pin-v1` contract: schema, fixtures, live-repo conformance tests): wheel-sourced sha256 manifest + `runtime_version`, written by `gator update` and `gator gatorize`. Repos gatorized by a 2.9.0 CLI are born pinned — no scripts tree ever.
- **`gator_core.resolve_governed_runtime()`**: fail-closed version negotiation (`current` / `cli-newer` / `refuse` / `repo-scripts` / `pin-unreadable` / `ungoverned`). Refusal is safe-by-design (`RUNTIME VERSION MISMATCH` + `pipx upgrade gator-command`); a corrupt pin fails OPEN to repo scripts — a broken file must never brick commits. BOM-tolerant pin read (`utf-8-sig`). Pins: `tests/test_gator_core.py::TestResolveGovernedRuntime`.
- **`gator hook approve`**: the Architect override runs from the installed CLI (repo copy of `gator-approve.py` no longer ships). Agent-invocation remains forbidden by governance.
- **Enterprise policy channel** (source-checkout Enterprise installs): Migration 012 `machine_policy_states`; `POST /policy-state/report` with `replace_scopes` full-state-per-scope semantics (retired policies clear automatically); `GET /policy-state` + `GET /policy-state/drift`; `GET /policies/active`; client `gator-enterprise policies pull` / `policies drift`; committed `.gator/policy-pin.json` (`gator-policy-pin-v1` — hashes only, never content). Org-side policy activation flips fleet drift in one query. Base installs are untouched — everything is gated fail-closed behind `~/.gator/enterprise/` activation.
- **Policy staleness nudge** (D6 option c): purely local mtime check on `~/.gator/enterprise/org-policies.json` (7-day default, `GATOR_POLICY_STALE_DAYS`), surfaced in the `gator init` banner and session-open stderr. No network in any session-opening path, ever. Inert for non-Enterprise machines.
- **Shipped procedures for the upgrade experience**: `gator-version-drift.md` (cross-branch Gator merge rules; §0a pinned-repo merge rules; **§0b mid-session orientation** — what an agent sees when the update lands under it mid-session, and the one rule: commit the diff, never restore deleted scripts) + runtime-split note in `committing-gator-files.md`. The v2.7.0 procedure pair (`pre-gator-residue.md`, `committing-gator-files.md`) is also backfilled into the wheel template — it had never actually shipped in the wheel.

### Changed

- **`gator update` sheds the repo-resident runtime**: writes the pin, deletes `.gator/.includes/scripts/` (or v1 `.gator/scripts/`), refreshes pin-aware hook stubs. The scripts-absent-with-pin layout is a valid v2 repo (S1 relaxation). Migration is per-repo and opt-in; un-updated repos and branches keep running their committed scripts indefinitely.
- **Vendor SessionStart hooks** (Claude/Codex/Gemini settings) route via `gator hook session-open` with a four-clause fallback chain (`gator` on PATH → `python` → `python3` → `py -3`); Enterprise-provisioned machine hooks embed the absolute launcher. Fixes the dead v1 script paths Enterprise vendor hooks had carried since the `.includes` split.
- **`enforcer-review`** is cwd-based and machine-side; user config canonicalized at `.gator/enforcer-config.json` (root, with legacy-location probes); whiteboard writes resolve the repo root correctly (fixes a latent v2 bug where findings landed in `.includes/whiteboard.md`).
- **Prose sweep**: constitution, procedures, reference-notes, entry-point templates, README, and operator docs all describe the pinned-runtime model with CLI-first invocations (`gator hook enforcer-review`, `gator hook approve`); `enforcer-prompt.md` relocated to shipped reference-notes.

### Fixed

- **Base-wheel package-data gap** (Post-2.6 item 12, load-bearing under the split): 7 scripts restored to the wheel (`gator-audit`, `gator-audit-renderers`, `gator-drift`, `gator-fleet-intel`, `gator-fleet-report`, `gator-session-aggregator`, `gator_session_reader`) + a self-maintaining disk→wheel guard (`test_packaging.py::test_wheel_ships_every_top_level_script`).
- **Session-open silent no-op on pinned repos**: the wheel copy's sys.path bootstrap now includes the own-directory fallback; repo-root walks in `gator-approve` / `gator-session-open` / `policies pull` uncapped (arbitrary hop limits silently failed on deep working dirs).
- **`gator init` banner nudge dead-code wiring** (undefined name swallowed by a blanket except) — fixed and pinned end-to-end.
- **Enterprise latents caught by the policy-channel work**: policy-version activation flush-order `IntegrityError`; `PolicyVersion` one-active partial index missing `sqlite_where`; Migration 012 server-side timestamp defaults (migration⟷model drift class — SQLite tests structurally can't catch it; real-Postgres smoke required).
- Unreadable-pin degradation unified across malformed-JSON and unparseable-version branches (repo scripts present → fallback; absent → honest `ungoverned`).

### Upgrading

`pipx upgrade gator-command`, then `gator update` in each governed repo (Dashboard → Fleet → Update is the easiest path), one branch at a time — merges converge per `gator-version-drift.md`. **Teams: upgrade every machine's CLI before anyone pushes an updated repo** — a pinned repo refuses older CLIs by design. Repos and branches you don't update keep working unchanged on their committed scripts.

## [2.8.0] — 2026-08-16

Full Claude + Codex + Gemini audit surface. Completes the Enterprise audit-surface tranche (all six phases, Architect-ratified 2026-08-16): the five canonical audit questions (Q1-Q5) now return correct answers against real transcript custody from **all three vendors** — Claude Code, Codex CLI, and Gemini CLI — verified end-to-end by the Phase 6 widened-vendor smoke test (156 sessions, ~2,420 links, 2,025 commits across 13 repos on the smoke machine).

Semver-strict MINOR bump: two new vendor adapters on an existing flag (`--vendor codex|openai|gemini|google`), one additive schema migration (011), one new workflow step. No breaking API changes.

**Operator note (Enterprise): run `alembic upgrade head` (Migration 011) before pulling Gemini transcripts.** Pre-011 schemas collide on Gemini's duplicate raw session IDs; the pull path assumes the widened uniqueness constraint.

### Added

- **Enterprise-side Codex adapter** (`transcripts pull --vendor codex`, alias `openai`). Discovers the `~/.codex/sessions/` rollout tree (`rollout-*.jsonl`), with `CODEX_TRANSCRIPTS_ROOT` env override and a missing-root informative warning matching the Claude pattern. Real-corpus verification on the smoke machine: 102/102 transcripts ingested, 1,979 links across both automatic bases (1,007 `exact_sha_in_transcript` + 972 `strong_machine_repo_time`), reverse lookup verified.
- **Enterprise-side Gemini adapter** (`transcripts pull --vendor gemini`, alias `google`; canonical vendor slug `google`). Single-JSON parser for `~/.gemini/tmp/<project>/chats/session-*.json` with `projects.json` workspace-hint reverse-mapping, `GEMINI_TRANSCRIPTS_ROOT` env override, and the shared degraded-parse contract (whole-file JSON failure keeps raw bytes as evidence; only `OSError` marks unreadable).
- **Migration 011 — `transcript_sessions.session_qualifier`.** Widens the uniqueness constraint to 5 columns and appends `__{qualifier}` to blob keys, so two Gemini files sharing the same raw `sessionId` coexist as two rows + two blobs instead of silently upserting over each other. Closes v2.7.0's "Q5 Gemini answer-completeness gap" known issue. Qualifier = `sha256(source_path)[:16]` for Gemini; empty for other vendors (pre-011 row + blob shapes preserved).
- **β multi-link fan-out contract** on snippet-basis linkage: under duplicate-raw-ID sibling rows, each row links the matching commits (Q1 honestly returns N>1 candidates), with ambiguity signaled by `medium` confidence + `linkage_metadata.raw_id_ambiguous_across: N` on every sibling link, regardless of ingest order.
- **Workflow B TestPyPI CDN-poll step** in `release-candidate.yml`: bounded poll (8×15s) of the TestPyPI JSON API before the smoke install — the TestPyPI twin of v2.6.1's Workflow C production fix, motivated by the v2.7.0-rc1 Windows-cell CDN race. This release's RC run is its first real-world validation.

### Changed

- **`--vendor` choices** now `claude | anthropic | codex | openai | gemini | google | all` (`all` still resolves to claude-only in this release; cross-vendor iteration is follow-on work).
- **`transcripts` CLI help + module docstring** rewritten vendor-accurate: "Claude Code, Codex, Gemini" replaces the stale "MVP: Claude Code only", and the docstring now reflects all six shipped verbs (`pull/list/show/get/link/relink`).
- **Enterprise operator guide** gains §3.1a (Codex pull walkthrough) and Gemini/Migration-011 notes.

### Fixed

- **Order-independent ambiguity metadata on fan-out links** (enforcer finding, 2026-08-16). The retroactive downgrade path previously updated only `linkage_confidence` on the first-ingested sibling's links, leaving `raw_id_ambiguous_across` present only on later siblings — the audit signal depended on ingest order. Now a per-row read-modify-write converges confidence AND metadata on all sibling links, and re-stamps the count when additional siblings arrive (a third duplicate refreshes earlier links from 2 → 3). Pins: `test_transcripts_discovery_gemini.py::TestDuplicateSessionIdAcrossFiles` (metadata parity + third-sibling refresh + no-marker-when-unambiguous).
- **`transcripts list --unlinked` help-string drift** — help text now matches the server-side filter behavior shipped in v2.7.0.
- **`VERSION` file re-synced with `pyproject.toml`** (both now 2.8.0). The byte-consistency rule drifted across 2.6.0 → 2.7.0 (three releases bumped pyproject only; `VERSION` sat at 2.5.4). Harmless in the primary resolution path (`get_version()` reads pyproject first) but the fallback path could serve stale numbers; tripwire updated in `scripts-core-library.md`.

### Removed

- **Base-Gator vendor-transcript extractors retired** (session-cleanup Phase 4 final sweep): `extract-codex-sessions.py`, `extract-gemini-sessions.py`, and `gator-session-common.py` deleted (~1,259 lines), their TRIPWIREs retired, 6 charters swept. `gator_session_reader` is now the sole owner of machine identity. This completes the architectural line ratified in the audit-surface sketch: **base Gator emits a small amount of governance metadata; Enterprise owns transcript custody, parsing, and cross-session audit retrieval.** The retirement gate (real linked commits via the Enterprise-side adapters) was satisfied by the Phase 3+4 smoke evidence before deletion.

### Under the hood

- **Phase 6 widened-vendor smoke run** (2026-08-16, Architect-ratified): Q1-Q5 correct for all three vendors against real custody; zero code failures; cross-vendor Q1 exemplar commit answered with 3 transcripts across 2 vendors in one query. Run artifact + 5-item rough-edges backlog in vault; RE-2 (stateless re-pull re-uploads unchanged bytes) promoted to roadmap Post-2.6 item 16 (content-hash skip).
- **Legacy-Memex charter cleanup**: phantom `graph-wiki`/`memex` entries retired; `INDEX.md` single-sources the charter map.
- **Test suite at release-time**: enterprise **311 passed + 1 skipped** (was 269 + 1 at v2.7.0; +42 net across Codex discovery, Gemini discovery/qualifier/fan-out, and the metadata-parity pins); base + contracts **808 passed**, 2 pre-existing xfails. Zero regressions.

### Known issues

- Same v1 `active-vendor-session.json` compat xfails (roadmap item 8), Enterprise packaging source-checkout-only (item 5), and base-wheel package-data gap (item 12) — all unchanged.
- **Codex re-pull cost**: every `transcripts pull` re-uploads all discovered transcript bytes to learn `status=updated` (>300s for the 102-file corpus). By design (stateless, content-always-converges MVP loop); incremental content-hash skip tracked as roadmap Post-2.6 item 16.
- **`--vendor all` still claude-only** — cross-vendor iteration in one invocation is follow-on work.

## [2.7.0] — 2026-08-14

Enterprise audit-surface tranche. Ships the first evaluator-ready set of audit questions across the transcripts-first substrate: **five canonical audit questions** ("Q1: which transcripts touched commit `<sha>`?"; "Q2: which recent commits in repo `<repo>` have transcript coverage?"; "Q3: which recent transcripts are still unlinked?"; "Q4: which machine produced commit `<sha>`?"; "Q5: which model/vendor sessions touched repo `<repo>` over time?") — all EXISTS post-release with working CLI + API paths. Plus two AI-model-focused shipped procedures for handling v1→v2 upgrade residue and Gator-file commit conventions.

Semver-strict MINOR bump: 3 new API endpoints + 3 new CLI subcommands + 1 extended API endpoint. All additive; no breaking API changes; no removed endpoints; existing request/response shapes preserved. The retired session subcommands from v2.6.1 remain retired.

### Added

- **Q4 audit surface — `commits provenance <sha>`.** New CLI verb + `GET /api/v1/commits/{commit_sha}/provenance?repo_canonical_id=<id>` endpoint returning commit-side provenance from Migration 008's snippet fields (`machine_id`, `machine_label`, `snippet_agent`, `transcript_session_id`, `committed_at`, `author_identity`, `repo_identifier`). 7-40-char SHA prefix matching; multi-match returns all candidates; CLI prints ambiguity table + `--repo` disambiguation hint. New route file `enterprise/app/routes/commits.py`, new router registered in `main.py`.
- **Q2 audit surface — `commits list --repo <id>`.** New CLI verb + `GET /api/v1/repos/{repo_canonical_id:path}/commits?limit=&offset=` endpoint returning per-commit rows shaped like Migration 010's `commits_with_transcript_coverage` view (commit metadata + `linked_transcript_count` + `best_linkage_basis_ranked`). Route-level composition of the view's join (rather than direct `SELECT ... FROM view`) so SQLite in-memory tests work without recreating the view.
- **Q5 audit surface — `repos transcripts <id>`.** New CLI verb + `GET /api/v1/repos/{repo_canonical_id:path}/transcripts?vendor=&since=&limit=&offset=` endpoint doing the 3-way join `TranscriptSession ⨝ CommitTranscriptLink ⨝ Commit` with `DISTINCT` on TranscriptSession (dedupes when one session links N commits in same repo). Ordered by `started_at DESC`.
- **Q3 audit surface — server-side `unlinked=true` filter.** `GET /api/v1/transcripts?unlinked=true` gains a HAVING clause returning only sessions with zero linked commits — was client-side-filter-only pre-v2.7.0. CLI `transcripts list --unlinked` now passes the param through; keeps a defensive client-side filter as fallback for old-server compat. Complements the `unlinked_recent_transcripts` view (Migration 010) — view is bounded to last 7 days, API endpoint is unbounded.
- **New route file `enterprise/app/routes/commits.py`** — companion to `routes/ingest.py` (write side) and `routes/transcripts.py` (which houses the historical co-located `/commits/{sha}/transcripts` reverse-lookup). Owns commit-side reads that don't return transcripts. Router registered in `main.py` alongside the existing 9 routers.
- **Two new shipped procedures in `.gator/.includes/procedures/`** (propagate to every governed repo on next `gator update`, hidden from dashboard file browser by the existing `.includes` whitelist mechanism):
  - **`pre-gator-residue.md`** — for AI models encountering `.pre.gator*` files in the tree after a v1→v2 layout upgrade. Explains the files are safety-net backups from `gator update --migrate-layout`, prescribes vaulting them (`.gator/vault/pre-update-backups/<YYYY-MM-DD>/<original-path>/`), and enumerates the 4 common failure modes without the procedure.
  - **`committing-gator-files.md`** — general guidance on committing `.gator/` files after any Gator-driven modification. Default rule: most `.gator/` changes SHOULD be committed when Gator produced them. Enumerated exceptions: `.pre.gator*` backups, `.gator/vault/`, post-commit residue (`commit_draft.md` + `whiteboard.md`), unrelated session snippets, machine-local operational state. 5-step decision ladder + 5 common failure modes without the procedure.

### Changed

- **`enterprise/enterprise-cli/gator_enterprise_cli/commands/commits.py`** subcommand group extended from 1 → 3 (`transcripts` pre-existing; `list` + `provenance` new).
- **`enterprise/enterprise-cli/gator_enterprise_cli/commands/repos.py`** subcommand group extended from 3 → 4 (`list` + `refresh` + `policies` pre-existing; `transcripts` new).
- **`.gator/.includes/constitution.md`** "The Loop" step 8 note gains cross-references to the two new procedures so agents naturally discover them at the seam where the questions come up.

### Fixed

- **`transcripts pull`: missing `~/.gator/machine-id` fail-fast.** Prior behavior silently uploaded transcripts with `machine_id="unknown"`, collapsing every affected transcript into a single synthesized machine row + breaking the `strong_machine_repo_time` linkage basis fleet-wide. Now exits code 2 with an actionable error message pointing at `gator init` as the fix, at the top of the pull command before any commit or transcript ingest fires.
- **`transcripts pull`: missing `~/.claude/projects/` informative warning.** Prior behavior returned a silent zero-transcript pull. Now prints a warning to stderr explaining that the Claude transcript root is absent (with the `CLAUDE_TRANSCRIPTS_ROOT` env-override hint). Non-fatal — operators may legitimately have no Claude transcripts.
- **`transcripts pull`: malformed-JSONL unreadable-file skip.** New `DiscoveredTranscript.unreadable` boolean, set to `True` when `_parse_jsonl_metadata` catches `OSError` on file open. Records with `unreadable=True` skip upload with a named-file diagnostic to stderr instead of attempting to upload a file the parser never actually read. Non-fatal parse issues (missing sessionId → filename fallback) keep `unreadable=False` — file is still usable evidence.

### Documentation

- **`enterprise/docs/enterprise-blueprint.html`** gains a top-of-file HISTORICAL warning banner. The blueprint is a 2026-07-11 artifact describing the E1-E6 evidence-in-Git architecture superseded 2026-08-08 by the ratified transcripts-first MVP. Banner points at the current ADR + MVP plan + audit-surface plan + relevant migrations. Follows the same pattern as `enterprise/docs/session-block-schema-v2.md` (banner-marked v2.6.0 P1.5).
- **`.gator/roadmap.md`** Current-Priority section reframed per the 2026-08-14 Codex Enterprise-audit-surface next-steps sketch: the audit-surface tranche is now Current Priority #1 for the near-term window; install/UX + Loop polish preserved as #2/#3. Post-2.6 candidate-work list gained items 9-15 mapping the sketch's 6-step tranche (Codex adapter → Gemini adapter → Phase 4 sweep → smoke test) plus items 13/14/15 for the audit-surface tranche's Phase 1/2/6 deliverables.
- **`.gator/inbox.md`** gains two new open items (PyPI-CDN poll validation-pending watch item; audit-surface tranche implementation-plan-authoring-pending) — both surfaced in prior sessions but formalized here.

### Under the hood

- **Audit-surface implementation plan** at `.gator/vault/artifacts/2026-08-14-enterprise-audit-surface-implementation-plan.md` (r10) — 6-phase plan mapping the Codex sketch's 6 steps to roadmap items 13→14→9→10→11→15. Iterated 10 revisions across 8 whiteboard-review rounds. Ratified §10 items 5-8 (Q4 surface = `commits provenance`, Q2 CLI = `commits list --repo`, Q5 CLI = `repos transcripts`, declared-evidence surface = spec-only follow-on). Items 1-7 in §10 remain phase-kickoff-deferrable for later phases.
- **Phase 1 audit-question surface artifact** at `.gator/vault/artifacts/2026-08-14-enterprise-audit-question-surface.md` (r7) — the ratified Phase 1 deliverable + post-Commit-J rollforward showing all 5 questions in EXISTS status. Preserves the historical Phase-1-exit ratification record alongside the current state.
- **Smoke-test protocol** at `.gator/vault/artifacts/2026-08-14-audit-surface-phase-2-smoke-test-protocol.md` — 9 tests (T1-T9) covering all 6 Phase 2 behavior changes; Architect executes locally to fill in Run 1.
- **Operator guide refresh** at `.gator/vault/artifacts/enterprise-transcripts-mvp-operator-guide.md` gains a §10 "Audit-question surface" section mapping Q1-Q5 to CLI/endpoint pairs + Gemini caveat on Q5 + Phase 2 error-message hardening summary.
- **Charter updates**: `.gator/charters/scripts-enterprise.md` gains 3 new invariant blocks (one per Commit I/J/K) with the full delta + regression-pin summary + hand-off notes. `.gator/.includes/constitution.md` gains procedure cross-references.
- **24 new regression pins** across `enterprise/tests/test_ingest_routes.py` (Q3 filter + Q2/Q4/Q5 endpoints — `TestListTranscripts::test_unlinked_filter_*` + `TestCommitProvenance` (7) + `TestRepoCommitsList` (4) + `TestRepoTranscriptsList` (5)) + `enterprise/tests/test_transcripts_discovery.py` (`TestPhase2Hardening` — 5 tests for `unreadable` + `claude_root_path`).
- **Test suite at release-time**: enterprise **269 passed + 1 skipped** (was 245 at v2.6.1 baseline, +24 net Phase 2 tests); base 770 passed + 2 pre-existing xfails (unchanged). Zero regressions.
- **Path-converter fix during implementation**: FastAPI treats slashes in path params as separators by default; both new `/repos/*/*` routes use `{repo_canonical_id:path}` converter to allow slashes in canonical ids (`local/<name>` shape). Caught by 9 initial test failures; all-green post-fix.

### Known issues

- Same v1 `active-vendor-session.json` compat xfails from v2.6.0/v2.6.1 unchanged (`tests/test_multi_session.py::test_v1_file_returns_single_entry_list` and `::test_v1_file_migrates_to_v2_on_write`). Not release-blocking; roadmap item 8.
- **Enterprise packaging still source-checkout-only** — unchanged from v2.6.0/v2.6.1. Single-pipx install path remains post-2.6 work (roadmap item 5).
- **Base-wheel package-data gap** (unchanged from v2.6.1): several session-pipeline scripts missing from `[tool.setuptools.package-data]`. Roadmap item 12.
- **Q5 Gemini answer-completeness gap**: pre-Migration-011 (Phase 4 work, tracked as parent-plan §10 item 6), two Gemini transcript files with the same raw `vendor_session_id` on the same machine collide at ingest — second-file uploads overwrite the first. Q5 for a repo where Gemini was used with duplicate-raw-ID transcripts returns an incomplete history until Phase 4 lands. Q5's shipped surface returns honest partial data for Gemini in the interim; Enterprise-side Codex + Gemini adapters (Phase 3 + Phase 4) address this.
- **PyPI-CDN poll fix from v2.6.1 gets its first real-world test** on this release. The bounded poll (8 attempts × 15s = 120s max) sequenced before the post-publish smoke install lives at `.github/workflows/promote-to-pypi.yml` and is now on `main`; the v2.6.1 promote loaded pre-fix workflow definition. If the poll surfaces the new version in ≤2 attempts, fix landed correctly; if it exhausts, we discover a CDN-lag failure mode we hadn't observed. Either outcome is informative.

## [2.6.1] — 2026-08-13

Post-Enterprise-transcripts-first cleanup release. Retires vendor-transcript archaeology from base Gator (net **~-5,000 lines** across 6 commits) now that the Enterprise transcripts-first substrate is the source of truth for full transcript custody. Plus two paper-cut fixes: PyPI-CDN lag on post-publish smoke, and inverted arg order in the `commits` docstring.

Semver-strict PATCH bump: no breaking API changes, no public CLI verb affected. The retired session subcommands (`sessions {index, manifest, export, pending, commit-summaries, turn-manifest, grep-turns, show-turns}`) were internal-only entry points reachable only via direct script invocation — never registered in `gator_command.cli::COMMANDS`.

### Removed

- **Vendor-transcript archaeology retired from base Gator.** Four whole files deleted: `src/gator_command/scripts/gator-sessions.py` (1,244 lines — vendor-agnostic session orchestrator CLI with `sessions {index, manifest, export, pending, commit-summaries, turn-manifest, grep-turns, show-turns}` subcommands, all internal), `gator-session-sink.py` (831 lines — SQLite/DuckDB/NDJSON sink), `gator-session-block.py` (680 lines — session-block generator, inert since v2.6.0 P1.3), `extract-claude-sessions.py` (489 lines — Claude JSONL archaeology; Enterprise-cli's `transcripts_discovery.py` is the replacement). Plus 3 test files (~97 tests). **Deferred to Phase 4**: `extract-codex-sessions.py` + `extract-gemini-sessions.py` retire once Enterprise-side Codex + Gemini adapters ship (parent plan §5 decision 2(b) — preserves multi-vendor coverage during the transition).
- **`gator-audit.py::assemble_audit_data()` raw-vendor-logs decisions branch retired.** The `elif common: extract-* + extract_intelligence + is_real_decision` fallback path is gone. `data["decisions_source"]` is now always `"committed"` when any summaries exist; no `"raw-vendor-logs"` value survives.
- **`data["sessions"]` vendor-transcript-derived counts retired** (`total`, `by_vendor`, `by_repo`, `pending_export`, `exported`). Per parent plan §5 decision 4 = (i) drop silently; `data["sessions"]` stays as an empty `{}` and dashboard consumers (`audit.js`) default defensively (`sessions.by_vendor || {}`) — empty tiles are the honest degrade.
- **`pyproject.toml [tool.setuptools.package-data]`**: `scripts/gator-session-block.py` removed (the only session-family file that had been listed).

### Added

- **`src/gator_command/scripts/gator_session_reader.py`** — new importable library (no CLI) housing the surviving snippet-based reader contract. Three functions: `parse_committed_summary()` and `read_committed_summaries()` (extracted from `gator-sessions.py` in the deletion-free Phase 2 split), plus `get_machine_identity()` (folded from `gator-session-common.py` in Phase 3F). Byte-identical behavior to the originals. Consumers: `gator-audit.py::assemble_audit_data()` and `gator-repo-status.py::get_session_summaries()`.
- **`gator-audit.py::_committed_decisions_from_snippets()`** — surviving snippet-reader decisions helper, extracted from `assemble_audit_data()` in the Phase 2B split.
- **`tests/test_session_reader.py`** — new 5-test regression pin for the surviving reader contract (migrated from the retired `tests/test_sessions.py::TestReadCommittedSummaries`).

### Fixed

- **`.github/workflows/promote-to-pypi.yml`: bounded PyPI-CDN poll before the post-publish smoke.** v2.5.2, v2.5.3, v2.5.4, and v2.6.0 all failed the immediate post-publish smoke test because PyPI's upload succeeds ~30-60s before its CDN populates all edges — pip installs 404 during that window. New `Wait for PyPI CDN to surface the new version` step polls `https://pypi.org/pypi/gator-command/${version}/json` (8 attempts × 15s = 120s max) before the install step. On timeout, prints an explicit error pointing at `https://status.python.org/` before manual re-run.
- **`enterprise-cli commits`: inverted arg order in docstring + fallback usage message.** The CLI itself has always worked as `commits transcripts <sha>` (verb-first — argparse resolves subcommand groups before positionals), but the module docstring, `handle()` fallback error message, and `main.py` register-comment all quoted the URL shape `commits <sha> transcripts`. Real evaluator-mislead vector caught during v2.6.0 smoke-test Run 1 (Finding #8). Fixed at all 3 sites; fallback also gained the previously-hidden `[--repo <id>]` option.

### Documentation

- **Charter overhaul across the session-pipeline surface** as part of the deletion. `scripts-session-archaeology.md` rewritten from 377 → 138 lines: function entries for the 4 retired files removed; Owns restructured around surviving files with explicit Phase-4-deferred markers on `extract-codex-sessions`, `extract-gemini-sessions`, and `gator-session-common`; new TRIPWIREs for the `parse_committed_summary` single-owner contract and the `get_machine_identity` Phase-3→4 duplicate-copy sync obligation; Before-Changing rewritten with atomic Phase 4 sweep obligations. Companion updates to `scripts-cross-cutting.md` (row-key duplication TRIPWIRE collapsed to single-owner; Session-Block Script Dual Deployment section retired; graceful-degradation note updated), `scripts-core-library.md` (`get_machine_identity` dual-copy note; `format_summary_markdown` callers pruned), `scripts-fleet-intelligence.md` (`assemble_audit_data` entry rewritten; TRIPWIRE Decisions Source Preference renamed to Single Path; `_is_real_decision` entry updated as sole filter), and `INDEX.md` (session-archaeology row rewritten).
- **`.gator/roadmap.md`** rolled forward: new Done row for the cleanup arc with all 6 commit SHAs and both in-flight design decisions (F-partial + (i)-drop-silently); item 4 (session-block retirement) rescoped to Enterprise-side only (base side done); new items 9 (Codex adapter), 10 (Gemini adapter), 11 (Phase 4 sweep, blocked on 9+10), 12 (base-wheel package-data gap).

### Under the hood

- **`gator-audit.py::assemble_audit_data()` restructure**: the two decision-source branches were first extracted into cleanly-separable module-level helpers (`_committed_decisions_from_snippets`, `_committed_decisions_from_raw_vendor_logs`) in the deletion-free Phase 2B pass; Phase 3 Commit D then deleted the vendor-logs helper + its dispatch site as a single mechanical delete. Ordering-required-first: doing file deletes before the audit surgery would have broken the snippet-reader path via a spurious `if sessions_mod:` guard on `sessions_dirs` gathering.
- **6-commit cleanup arc**: Phase 2A (`cafb656`) → 2B (`e5db8f4`) → Phase 3 Commit D (`c9b2496`) → E (`d54d899`) → F (`28422a9`) → charter-drift cleanup (`33e77c8`), plus the two paper-cut fixes G (`94b791e`) and H (`303e42a`). All 8 pre-commit-hook-verified; no `--no-verify` overrides used.
- **Test suite at release-time**: 770 passed, 2 pre-existing xfails. The 97-test drop from v2.6.0's 867 matches the 3 deleted test files exactly (`test_sessions.py` + `test_session_sink.py` + `test_session_block.py`). Zero regressions in surviving tests.
- **F-partial ratification**: mid-Commit-F grep discovered that Phase-4-deferred Codex + Gemini extractors transitively depend on 7 vendor-formatting helpers in `gator-session-common.py`. Fully deleting session-common in Phase 3 would have broken the deferred extractors. Architect ratified F-partial: fold `get_machine_identity` into the reader, keep session-common alive with its 7 vendor helpers + a duplicate copy of `get_machine_identity`; full deletion happens atomically in Phase 4 with the extractor retirement. Documented as a new TRIPWIRE in `scripts-session-archaeology.md`.
- **Whiteboard-flagged charter drift**: Commit F's `scripts-session-archaeology.md` rewrite missed the same class of stale-tripwire content in three neighbor charters. Cleanup commit `33e77c8` swept them. Lesson noted in the consumer-audit artifact r3: on big deletion passes, grep the retiring filenames across ALL charters (especially `scripts-cross-cutting.md`, which tends to have cross-file TRIPWIRE and Pattern sections).

### Known issues

- Same v1 `active-vendor-session.json` compat xfails from v2.6.0 unchanged (`tests/test_multi_session.py::test_v1_file_returns_single_entry_list` and `::test_v1_file_migrates_to_v2_on_write`). Not release-blocking; fix tracked as roadmap item 8.
- **Enterprise packaging still source-checkout-only** — unchanged from v2.6.0. Single-pipx install path remains post-2.6 work (roadmap item 5).
- **Base-wheel package-data gap**: several session-pipeline scripts (`gator-session-aggregator`, `gator-session-common`, `gator_session_reader`, plus `gator-audit`, `gator-fleet-report`, `gator-drift`, `gator-fleet-intel`, `gator-audit-renderers`) are missing from `[tool.setuptools.package-data]`. Pre-existing gap unrelated to this release; under `pipx install gator-command` these degrade to empty output (dashboard audit view shows no session summaries; machine identity absent). Source-checkout install works. Tracked as new roadmap item 12.

## [2.6.0] — 2026-08-09

The Enterprise transcripts-first MVP substrate lands in-tree, and the base wheel's `gator enterprise` dispatcher is reconciled with the real verb set so the MVP is reachable from a `pipx install gator-command` + source-checkout enterprise-cli install. Under-the-hood cleanup retires the actively-harmful vestiges of the pre-transcripts-first evidence design.

**Enterprise packaging remains source-checkout-only** for this release. The base wheel ships the dispatcher; installing enterprise-cli requires `pip install ./enterprise/enterprise-cli/` from a source checkout, plus Postgres + a venv + `.env-enterprise-local`. A single-pipx install path is post-release packaging work.

### Added

- **Enterprise transcripts-first MVP** (6 phases landed 2026-08-08 on `dev`, commits `e784d60` → `de3bbde`). Migration 009 adds `transcript_sessions` + `commit_transcript_links` schema (transcript custody model) plus a `BlobStore` Protocol with a `FilesystemBlobStore` reference implementation. Migration 010 adds three transcript query views (`recent_transcripts`, `commits_with_transcript_coverage`, `unlinked_recent_transcripts`). New ingest APIs at `POST /api/v1/commits/ingest` + `POST /api/v1/transcripts/ingest`; new read surface at `GET /api/v1/transcripts/*`. New enterprise-cli verbs: `transcripts pull|list|show|get|link` and `commits <sha> transcripts`. Claude Code transcript discovery + upload wired end-to-end.
- **Enterprise CLI verbs `transcripts` and `commits` registered in the base dispatcher's `ENTERPRISE_CLI_VERBS`**, closing the gap where the MVP was unreachable from `gator enterprise <verb>` even with enterprise-cli installed. Prior state: `gator enterprise transcripts pull` printed "verb not yet integrated with enterprise-cli" and exited 69.
- **`Gator-Machine-Id` commit trailer emission** in all three copies of `gator-pre-commit.py` (base-wheel, template, enterprise-cli bundled) — the audit chain "this commit followed the AI-governed pipeline on THIS machine" survives even without an Enterprise linkage lookup. Silent no-op when `~/.gator/machine-id` is absent (standalone base-gator use).
- **Multi-vendor `.gator/active-vendor-session.json` v2 schema** with PID attribution and `owner_pid_started_at` PID-recycling protection, plus `GATOR_TRANSCRIPT_SESSION_ID` + `GATOR_TRANSCRIPT_VENDOR` env-var overrides — enables correct session attribution when multiple AI CLIs run in the same repo simultaneously.
- **`_warn_about_at_risk_hooks()` in `gator-enterprise activate`** — before setting global `core.hooksPath`, enumerates known-gatorized repos whose local hooks may stop firing, prompts unless `--yes`. Windows path is informational-only (base-gator sets local `core.hooksPath` on every governed repo, and Git prefers local over global).
- **`.gator/reference-notes/` scaffolding dir** — repo-user reference-notes location per constitution §File Purposes.
- **`.gator/.includes/charters/` scaffolding** — v2 layout scaffolding for shipped charter surfaces.

### Changed

- **Base dispatcher `CLIENT_SUBCOMMANDS` and `SERVER_SUBCOMMANDS` reconciled with reality.** Old lists advertised `setup/status/audit/disconnect` and `server/db/policy/org/fleet` (11 verbs) that never mapped to any enterprise-cli command; `gator enterprise <verb> --help` misled operators. Rewritten to real developer-side verbs (`activate/sync/repo/transcripts/commits`) and real operator/admin verbs (`auth/repos/providers/policies/reports/machines/blocks`). Every advertised verb now maps to a real command; the integration-gap notice becomes a contributor-error guard rather than an operator-visible failure mode.
- **`.gator/docs/how-to-use-gator.md`** rewrites the too-strong "Everything inside `.gator/` is committed to Git (except `vault/`)" into an explicit tracked-vs-gitignored split. Byte-identity mirror kept in `src/gator_command/templates/gator-starter/docs/how-to-use-gator.md`.
- **`docs/how-gator-works.md`**: removed the misleading sentence claiming `gator enterprise setup` connects to an Enterprise server (verb is `activate`, not `setup`; Audit-view claim removed pending real Enterprise availability documentation).
- **`docs/threat-model.md`**: replaced legacy "Gator Command" branding with "Gator Enterprise" (the Enterprise capability of Gator, not a separate product).
- **`.gator/sessions/.gitignore`**: added explicit note explaining why `.gator/session-snippets/` is intentionally NOT gitignored (durable commit-linked artifacts).

### Fixed

- **Enterprise `_do_repo_init` no longer creates `.gator/session-blocks/` or rewrites `.gitignore`.** Prior flow created the directory and called `_fix_gitignore(repo_path)` on every provisioning run to un-gitignore it. Both contradicted the ratified transcripts-first architecture (evidence lives in Enterprise-managed storage, not Git). `_fix_gitignore()` function deleted. Evaluators inspecting `.gitignore` post-`repo init` no longer see governance-driven rewrites.
- **`POST_COMMIT_HOOK` template in `gator-enterprise activate` no longer runs per-commit block generation.** Prior template's 40-line block-gen section invoked `gator_enterprise_cli.block_generate` (via CLI_PYTHON) with a v2-first repo-local script fallback, then `git add`'d the produced `.json.gz` and `.block.json` artifacts. Deleted. New template runs only `--phase cleanup` and returns. Machines that already activated Enterprise before this release still have the old hook until they re-run `gator-enterprise activate --force`.
- **Dashboard favicon refresh** with `?v=3` cache-buster so users on the previous CLI don't get stuck displaying the old icon.
- **Windows non-cp1252 git output crash in Dashboard History** (v2.5.4 baseline pre-fix): confirmed still holding.

### Deprecated

- **Session-block evidence path** — the entire code surface around per-commit `.gator/session-blocks/*.json.gz` artifacts, envelope encryption of session blocks (`gator_enterprise_cli.block_generate`, AES-256-GCM DEK wrapped for RSA-OAEP org key), and the server-side session-blocks routes + services (`enterprise/app/services/session_blocks.py`, `enterprise/app/routes/session_blocks.py`, `enterprise/app/routes/crypto.py`, `enterprise/app/models/evidence_block.py`) is now inert but still in-tree. Retirement is post-2.6 cleanup — the code is not on any active path but has not been physically removed. Base `.gator/session-blocks/` stays gitignored.
- **Dispatcher `blocks` verb** — still registered in the dispatcher's `SERVER_SUBCOMMANDS` while the server surface exists, but the underlying block-ingest server surface is obsolete. Full retirement post-2.6.

### Documentation

- **CHANGELOG + release-and-deploy alignment**: this is the first release after the Phase 4 stabilization pass (`.gator/vault/artifacts/2026-08-09-gator-3.0-stabilization-plan.md` and companion cleanup + smoke-test + release-readiness artifacts). The "3.0" framing in those planning docs was resolved to `2.6.0` per strict semver — no breaking API changes, so MAJOR bump not justified.
- **Historical banners** prepended to 4 obsolete Enterprise docs (`.gator/blueprints/session-block-capture.md`, `.gator/field-guides/enterprise-encryption-tutorial.md`, `.gator/field-guides/enterprise-encryption-patterns.md`, `enterprise/docs/session-block-schema-v2.md`). Each banner cross-references the transcripts-first MVP plan + ADR and instructs readers not to use the doc as guidance for new work.
- **`.gator/blueprints/enterprise-configuration.md`** added (Codex-authored, 407 lines) as reference for the pre-transcripts-first Enterprise configuration model. Also banner-marked historical.
- **`.gitignore`**: added `.tmp/` to prevent accidental commits of local test artifacts and release-notes drafts.

### Under the hood

- **Session-snippet catch-up**: 10 previously-unfilled session snippets from the 2026-08-04 through 2026-08-08 MVP arc committed as evidence bridge between session history and git history.
- **12 new regression pins** across `tests/test_gator_enterprise.py::TestConstants::test_every_advertised_verb_is_mapped`, `enterprise/tests/test_activate_atrisk.py::TestV2FirstScriptDiscovery::test_post_commit_does_not_generate_session_blocks`, and other flipped/updated invariants ensuring reintroduction of retired code paths fails loudly.
- **Test suites at release-time**: `tests/test_gator_enterprise.py` 30 pass, `enterprise/tests/test_repo_init.py` 8 pass, `enterprise/tests/test_activate_atrisk.py` + `test_activate_hooks.py` 47 pass. Full base-gator + enterprise + contracts suites run separately as part of the release cut.

### Known issues

- **`tests/test_multi_session.py::test_v1_file_returns_single_entry_list` and `::test_v1_file_migrates_to_v2_on_write`** marked `xfail` (non-strict) in v2.6.0. Pre-existing failures since `df71e8e` (2026-08-07); the v1→v2 reader + migrator do not currently preserve v1 legacy `active-vendor-session.json` content. Fix tracked as post-2.6 work: either implement a v1 read-shim in `_read_active_vendor_sessions()` and preserve v1 entries on v2 migration, OR delete the tests if v1 is truly out of support. Not release-blocking under the transcripts-first MVP framing (session-capture is Enterprise-only in end-state; v1 session-file compat is transitional-obsolete).

## [2.5.4] — 2026-08-03

Session-hook self-heal is no longer a silent no-op fleet-wide. `--migrate-layout` handles the last real-world non-convergence class (Issue #6). Vendor SessionStart hook drift auto-corrects on next update. When the migration can't converge, the operator finally sees WHICH paths are blocking.

### Fixed

- **`gator-session-open.py` no longer silent-no-ops on v2 layout.** The template-shipped hook script hardcoded `str(gator_dir / "scripts")` (v1 assumption) and passed the raw `.gator/` Path into `ensure_git_hooks()`, which expects a `GatorPaths` dataclass. On every v2 repo since the `.includes/` split landed, that raised `AttributeError` — swallowed by the `__main__` guard's `except → sys.exit(0)` per the silent-hook contract. Fix: v2-first probe for the scripts directory (`.gator/.includes/scripts/` → `.gator/scripts/` fallback), then `get_gator_paths(repo_root)` from `gator_layout`, then pass the resulting `GatorPaths`. Same shape as the v2.2.2 charter-verify layout-resolver bug. Regression pin: `tests/test_session_open.py::TestMain::test_calls_ensure_git_hooks`.
- **Vendor-hook templates (Claude / Codex / Gemini) now ship v2 script paths.** All three `src/gator_command/templates/gator-starter/vendor-hooks/*.json` files still shipped `python .gator/scripts/gator-session-open.py` — the v1 layout path. `merge_hooks_into_settings` compares template-vs-existing and only rewrites on drift; template v1 + existing v1 looked like "no change needed" fleet-wide. Templates now reference `.gator/.includes/scripts/…`; on every governed repo's next `gator update`, the merge sees drift and rewrites the Gator hook group in-place, preserving user hooks. Regression pins: `tests/test_vendor_hooks.py::TestTemplateHookEntries::test_template_has_session_open_and_session_start` and `test_session_open_runs_before_session_start` (both parametrized across all three vendors).
- **`gator update --migrate-layout` Step 5 handles directory conflicts** (Issue #6). Sibling of the v2.5.3 file-conflict fix. When a shipped directory (`scripts/`, `reference-notes/`) exists at BOTH `.gator/<dir>/` and `.gator/.includes/<dir>/`, Step 5's merge loop previously handled files correctly but skipped directory conflicts entirely — leaving `.gator/scripts/__pycache__/` and `.gator/scripts/hooks/` orphaned, `src_dir.rmdir()` failing silently, layout re-detecting as `mixed`, migration never converging. Fix: known-safe legacy names (`__pycache__`, `hooks`) get `shutil.rmtree`'d unconditionally; unknown names go through `_merge_dir_files_only()` (recursive files-only merge, dest wins on collision, non-file/non-dir entries logged into `report["conflicts"]`). Every fleet repo that ever ran a Python script under `.gator/scripts/` (i.e. probably every one) can now migrate without manual pre-cleanup. Regression pins: `test_shipped_dir_pycache_conflict_removed`, `test_shipped_dir_unknown_dir_conflict_merges`.
- **`gator update --migrate-layout` non-convergence report now names the blocking paths.** Prior end-of-run message: `"Result: mixed (migration incomplete — check conflicts)"` with no signal of which paths were the problem. New enumerator `_enumerate_mixed_residue()` walks the three mixed-detection categories (shipped root files, shipped directories with real content, shipped defaults in mixed directories) and prints each blocking path with a per-path reason ("duplicated in .includes/" vs "should have moved to .includes/") plus a "Suggested next step" hint. Sync-obligation-bound to `_has_legacy_shipped_content` in `gator_layout.py`. Regression pins: `test_enumerate_mixed_residue_finds_root_file`, `test_enumerate_mixed_residue_ignores_scaffolding_only_dir`, `test_enumerate_mixed_residue_reports_dir_with_real_content`.

### Added

- **Bounded diagnostic log for session-hook non-happy-path events.** New `.gator/.includes/scripts/gator_diagnostics.py` (template-shipped) exports `log_hook_event(gator_dir, script, status, detail)` — writes one line per event to `.gator/diagnostics/hooks.log`, capped at `MAX_LINES = 200` via oldest-drops truncation, every code path wrapped in try/except so a diagnostic write can never affect the caller's exit code. Wired into `gator-session-open.py::main()` — captures `ensure_git_hooks()`'s return dict, logs any `degraded` / `unavailable` / `error` status. `.gator/diagnostics/` gitignored via `ensure_repo_gitignore()`. The "silent hook" stdout-empty contract stays intact, but fleet-wide silent regressions at this seam now surface as machine-local evidence. Regression pins: 8 tests in `tests/test_session_hooks.py`.
- **`gator update --migrate-layout` auto-refreshes vendor hooks on successful convergence.** Previously the migration exited immediately after Step 11, before `install_vendor_hooks()`. On a v1→v2 migration this left session-hook command strings in `.claude/settings.json` / `.codex/hooks.json` / `.gemini/settings.json` pointing at the just-moved `.gator/scripts/…` paths. Fix: `main()`'s migration branch now calls `install_vendor_hooks(templates_dir, repo_root)` when `report["final_layout"] == "v2"`, wrapped in try/except so vendor-hook failure never masks the migration's own exit code. Single-command v1→v2 upgrade is now the intended path.

### Changed

- **`source-ci.yml` now runs on `dev` pushes** (previously main-only). Lets the fast-forward-to-main gate know the branch is green before the merge.

### Documentation

- **`.gator/procedures/release-and-deploy.md`** rewritten for the post-cutover pipx-first monorepo flow. Includes the 2.5.2 partial-commit incident as a hard-won lesson (staging discipline: `git diff --cached --name-only` after every multi-file `git add`) and the TestPyPI filename-permanence workaround for RC iteration.
- **`.gator/issues.md`** — added and resolved Issue #6 in a single release cycle. Preserved the original report body under the resolution note for context.
- **`.gator/vault/artifacts/2026-08-03-update-and-begin-session-bugs-implementation-plan.md`** — implementation plan for this release's fix set, iterated with a Codex-adversarial review pass (four Codex passes total, all remediated inline).

## [2.5.3] — 2026-08-02

Same intent as 2.5.2 — this release actually ships the code. The 2.5.2 wheel was published from a commit that dropped most of the intended hook-hardening files during `git add` (root cause: a Windows Git Bash trailing-backslash `git add \\` continuation silently skipped several entries). Only the `migrate_layout` src fix, the version bump, and the docs vault landed; the change-type validation, the tests, and the charter tripwires did not. This release is the recovery.

### Fixed

- **Pre-commit hook rejects invalid `change-type` values at commit time.** `gator-pre-commit.py::validate_hard_rules` now validates the `change-type` field in `.gator/commit_draft.md` against the schema-legal enum (`feature | fix | refactor | docs | test | release | maintenance | review | governance | ""`). Bad values fail with a helpful message naming the valid set and common typos (`bugfix` → `fix`, `chore` → `maintenance`, `style` → `refactor`). Previously, plausible-sounding values like `bugfix` passed pre-commit, were emitted verbatim into session snippets, and only got caught by CI schema validation on the emitted snippet — the exact drift class this validation exists to prevent. Sync obligation between `VALID_CHANGE_TYPES` and `contracts/schemas/gator-session-snippet-v2.json` pinned by `tests/test_precommit_validation.py::TestSchemaEnumSyncObligation`.
- **`gator update --migrate-layout` Step 5 now handles duplicates like Step 4.** (This one DID land in 2.5.2's wheel — repeated in these notes for completeness.) When a shipped directory contains a file that exists at BOTH `.gator/<dir>/X.md` AND `.gator/.includes/<dir>/X.md`, the `.includes/` copy is now canonical and the root copy is removed. Regression pin: `tests/test_layout.py::TestMigration::test_shipped_dir_duplicates_get_removed` (newly added in this release; 2.5.2 shipped the fix but not the test).

### Added

- New test files: `tests/test_precommit_validation.py` (3 classes covering the change-type validator + schema-sync check), `tests/test_layout.py::TestMigration::test_shipped_dir_duplicates_get_removed`.
- New charter tripwires: `.gator/charters/scripts-repo-lifecycle.md` (migrate_layout Step 5 duplicate contract), `.gator/charters/scripts-cross-cutting.md` (change-type enum sync obligation).
- `mkdocs.yml` nav restructured to remove entries pointing at the docs vaulted in 2.5.2 — without this, mkdocs 404'd on those nav entries.
- `CONTRIBUTING.md` — new `## Branching` section documenting the lightweight solo dev→main flow: work on `dev`, fast-forward `main` when source-ci is green, tag releases from main. This is the first release cut through that flow.

## [2.5.2] — 2026-08-02

Post-cutover polish: two hook fixes that harden the governance loop
against classes of drift the monorepo cutover surfaced.

### Fixed

- **Pre-commit hook rejects invalid `change-type` values at commit time.** `gator-pre-commit.py::validate_hard_rules` now validates the `change-type` field in `.gator/commit_draft.md` against the schema-legal enum (`feature | fix | refactor | docs | test | release | maintenance | review | governance | ""`). Bad values fail with a message naming the valid set and common typos (`bugfix` → `fix`, `chore` → `maintenance`, `style` → `refactor`). Before this fix, plausible-sounding values like `bugfix` passed pre-commit, were emitted verbatim into session snippets, and only got caught by CI schema validation on the emitted snippet — the exact drift class this validation exists to prevent. Sync obligation between `VALID_CHANGE_TYPES` and `contracts/schemas/gator-session-snippet-v2.json` pinned by `tests/test_precommit_validation.py::TestSchemaEnumSyncObligation`.
- **`gator update --migrate-layout` now converges when shipped directories contain duplicates.** Previously, if a shipped directory (`reference-notes/`, `scripts/`) existed at BOTH the flat `.gator/` root AND `.gator/.includes/`, the migration's Step 5 merge only moved files that didn't yet exist in `.includes/` — leaving root duplicates in place, re-detection as "mixed", and endless "Result: mixed (migration incomplete — check conflicts)". Step 5 now mirrors Step 4's behavior: when both exist, the `.includes/` copy is canonical and the root copy is removed. This state was hit during the monorepo cutover in `.gator/reference-notes/` and required manual cleanup; the fix means `--migrate-layout` self-repairs it. Regression pin: `tests/test_layout.py::TestMigration::test_shipped_dir_duplicates_get_removed`.

### Documentation

- 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` because they describe the retired `gator-engine/scripts/gatorize.sh` install path and `git checkout upstream/main -- gator-engine/` upgrade flow that no longer exist in the pipx-first monorepo world. Would actively mislead new users. `installation.md`, `upgrade.md`, `getting-started.md`, `index.md`, `audit-compliance.md`, `fleet-governance.md`, `session-archaeology.md`, `for-directors.md`, `for-engineers.md`, `for-leadership.md`, `new-project-with-gator.md`, `what-gator-requires-from-a-model.md`. Rewrite queued as a follow-on. `mkdocs.yml` nav restructured accordingly.

## [2.5.1] — 2026-08-02

**Note on the version jump from 2.4.5 to 2.5.1**: 2.5.0 was published to TestPyPI during the cutover pipeline validation. TestPyPI enforces a permanent no-filename-reuse policy — once `gator_command-2.5.0-py3-none-any.whl` was uploaded (even after deletion), that filename cannot be reused. Rather than skip TestPyPI validation for the production publish, we bumped the version to 2.5.1 and re-ran the full pipeline. 2.5.0 is not, and will not be, published to production PyPI. The next contentful release will be 2.5.1 or higher.

### Changed

- **Monorepo cutover.** The public `gator` repo is now a monorepo produced from `gator-command` via `scripts/monorepo-bootstrap.py`. Same wheel (`gator-command`), same install path (`pipx install gator-command`), same CLI. Repository home stays at `github.com/cumberland-laboratories/gator`; the pre-cutover MIT-era history is preserved read-only at `github.com/cumberland-laboratories/gator-legacy-pre-monorepo`. Contributors get a single tree that combines the `gator` core, the `contracts/` compatibility layer, and the optional `enterprise/` capability code — simpler contribution, CI, and release surface. Design record: `.gator/artifacts/2026-08-02-monorepo-cutover-plan-and-tree-map.md` in the monorepo (source repo path: `gator-command/artifacts/`).
- **Apache License 2.0** across the whole public tree (LICENSE + NOTICE at root, `pyproject.toml` `license = "Apache-2.0"`, wheel METADATA `License: Apache-2.0`). MIT-era wheel (v2.4.5 and earlier) is unaffected — existing installs remain under MIT terms. Public repo license flip landed on `main` at the Genesis commit.
- **VERSION file corrected.** Root `VERSION` was stale at 1.8.1 (never updated after early deploys); bumped to 2.5.0 to match `pyproject.toml`. `gator_core.get_version()` reads pyproject first anyway, so most callers were unaffected — but the file existed as a fallback that could confuse readers.

### Fixed

- **Enterprise dispatcher no longer masks real command failures** (Codex whiteboard Finding 1, 2026-08-02). `src/gator_command/scripts/gator-enterprise.py` previously caught any nonzero `SystemExit` from delegation and translated to the "verb not yet integrated" notice — a mapped verb's real runtime error (e.g. `sync` returning `SystemExit(1)` on a network failure) got mislabeled. Fix: new `ENTERPRISE_CLI_VERBS` frozenset filters unmapped verbs upfront via a three-ordered-check pre-delegation pattern (package importable → `.main` importable → verb mapped). Delegation now runs only for verbs enterprise-cli actually handles, and their real exit codes propagate unmodified. 3 new regression tests in `tests/test_gator_enterprise.py::TestIntegrationGap`. Charter: `charters/scripts-enterprise.md` reworded with the sync-obligation tripwire between `ENTERPRISE_CLI_VERBS` and `enterprise-cli/main.py`.

### Added

- **`scripts/monorepo-bootstrap.py`** — reproducible bootstrap for the public monorepo from the source `gator-command` repo. Two phases: `--phase a` copies the include-set (~372 files across product/tests/contracts/enterprise/docs/CI/release), `--phase b` scaffolds `.gator/` via `gator gatorize` and ports curated knowledge dirs with `EXCLUDE_KNOWLEDGE_FILES` filtering (11 source-repo-scoped files dropped) and `PATH_REWRITES` content transforms (`gator-command/scripts/` → `src/gator_command/scripts/`, `gator-command/{knowledge-dir}/` → `.gator/{knowledge-dir}/`, etc.). Not shipped in the wheel — one-time-use cutover tooling.
- **`scripts/monorepo-validate.py`** — Phase 3b-3-C validation runner. Nine checks: git-init + `file://` clone reproduces tree, wheel build, wheel install into a throwaway venv (`gator --version` works), pytest, `gator init` inside staging, license surface (no MIT residue), private-content-manifest cross-check, and two baselined stale-path gates (`EXPECTED_RESIDUAL_HITS` for `gator-command/` prefix drift, `EXPECTED_GATOR_SCRIPTS_HITS` for v1-layout `.gator/scripts/` paths). Baselines exist because a full charter review is scheduled post-cutover; new drift above baseline fails hard.

## [2.4.5] — 2026-07-31

### Added

- **HTML files render in the Dashboard.** `.html`/`.htm` files in `.gator/` (typically under `vault/`) now appear in the Repo/Docs file browser and open in a new tab with `Content-Type: text/html; charset=utf-8`. Clicking an HTML file goes through `loadFile()` in `views/repo.js`, which detects the extension and calls `window.open(rawUrl, "_blank", "noopener")` — the content pane shows a small "Opened X in a new tab" confirmation. Auto-load code paths (Docs first-file, Repo default-file) skip HTML to avoid the popup-blocker that would fire on `window.open()` outside a user gesture. Opens the door for governance HTML reports — mermaid flowcharts, audit visualizations, anything markdown can't render — to live alongside `.gator/` and be readable without leaving the Dashboard.
- **First tranche of Dashboard screenshots** landed in `docs/images/`: `dashboard-add-repo-modal`, `dashboard-fleet-gatorize`, `dashboard-fleet-update-button`, `dashboard-fleet-multi-repo`, `dashboard-repo-view`, `dashboard-docs-view`. The root `README.md`, `docs/how-to-use-gator.md`, and `docs/how-gator-works.md` reference these where prior placeholders lived. The public-repo landing page on GitHub now has real screenshots for the Dashboard-first Quick Start and walkthroughs.
- **Dashboard favicon** (`src/gator_command/scripts/dashboard/favicon.png`, 32×32 sleek-profile gator) — browser tab now shows the Gator mark next to a shortened "Gator" title.

### Changed

- **Dashboard Docs view now lists both `.gator/docs/` and repo-root `docs/`.** Prior filter was hardcoded to `f.dir === "docs"` (only `.gator/docs/*.md`). After the shadow-copy cleanup in 57c1c6b the source `gator-command` repo's Docs view went empty — the real docs live at `docs/` (repo root) and got `dir: "source/docs"`, filtered out. Filter now accepts both. Fleet/user repos with only `.gator/docs/` are unaffected.

### Fixed

- **Wide images in Dashboard content pane render at natural size** on some doc pages (notably `dashboard-repo-view.png` at 1835×965). Root cause: `.repo-content` is a flex item with no `min-width`, so flex-min-content sizing let it grow to fit any wide child; the img's inline `max-width: 100%` then read the expanded parent width. Added `min-width: 0` + `overflow-x: auto` on `.repo-content`, plus an explicit `.repo-content img { max-width: 100%; height: auto }` safety-net rule.

## [2.4.4] — 2026-07-31

### Fixed

- **Dashboard History view no longer crashes on non-cp1252 git output** (Windows). `gator_core.git()` was using bare `text=True` on the subprocess call, which decodes with the platform-default locale codec (`cp1252` on Windows). Any git output containing bytes unrepresentable in cp1252 — commit subjects with non-ASCII, author names with diacritics, trailer content copied from external sources — crashed with `UnicodeDecodeError` mid-response. Symptom: the Dashboard's History endpoint returned "Empty reply from server" (the handler crashed and closed the socket before flushing). Now uses `encoding="utf-8", errors="replace"` — matches the pattern already in `dashboard/helpers.py::git_run` and `dashboard/helpers.py::run_text`. Extended the same fix to `gator_core.get_version`'s git-describe and git-rev-parse subprocess calls, and to `dashboard/helpers.py::run_text` which had the same latent bug.
- Users hitting the Dashboard History "loading..." spinner that never resolves: `pipx upgrade gator-command` to 2.4.4, then `gator kill dashboard --all` and relaunch. History and any other endpoints that read git log output will resolve cleanly.

## [2.4.3] — 2026-07-31

### Added

- **`gator kill dashboard [--all | --port N | --dry-run]`** — new CLI verb for killing stale Gator Dashboard processes. Motivated by an operational failure mode where Dashboard processes accumulate silently during self-upgrade or when launched detached (no visible terminal); the port scanner grabs 8420-8429 sequentially, so a stale process on 8420 forces fresh launches to higher ports while the browser keeps talking to the stale one — env-var overrides don't take effect, in-flight code changes appear ignored, discovery scans yesterday's roots. Cross-platform (Windows `wmic`/`netstat`/`taskkill`; Unix `pgrep`/`lsof`/`SIGTERM`). Nested-subverb shape (`gator kill <target>`) leaves room for `gator kill loop`, `gator kill enforcer`, etc. later. Selector semantics enforced at the CLI boundary: `--all` and `--port` are mutually exclusive; `--dry-run` requires a selector; `--port N` must be within the dashboard's port range.
- **`GATOR_DASHBOARD_DISCOVERY_ROOTS` env var** for scoping the Dashboard's "Add Repository" auto-discovery scan. When unset, unchanged behavior (scans `~/code`, `~/code2`, `~/projects`, `~/repos`, `~/src`, `~/dev`). When set, becomes the EXCLUSIVE list of roots (paths separated by `os.pathsep`). Useful for demo mode, screenshot capture, and users who organize repos outside the default home-relative layout (`~/work`, `/mnt/repos`, etc.).

### Changed

- **New Dashboard sidebar logo** — sleek-profile gator (transparent RGBA on the `#1e1e2e` sidebar). Replaces the previous in-motion logo.
- **Documentation refresh across README + three docs** to reflect v2.4.x reality and pivot to Dashboard-first framing:
  - `README.md` (public repo landing): Dashboard-first Quick Start + Upgrade, honest managed-block / slash-command install notes, five image placeholders for the visual walkthroughs.
  - `docs/how-to-use-gator.md`: Dashboard-first restructure, accurate v2 layout tree (drops the false "everything committed to Git" claim; names `.includes/`, `sessions/`, `docs/`, `CLAUDE.local.md`), new **Session Summaries** and **Multi-Agent Loops** sections under "What You Can Ask For", expanded Dashboard walkthrough, `gator update` (not `gator gatorize .`) as the refresh recipe. Six image placeholders.
  - `docs/how-gator-works.md`: new **Session Summaries — the Governance Trail** section, Multi-Model Review expanded to name the enforcer and Gator Loop primitives concretely, Dashboard section expanded to a five-view walkthrough, "What Gator Feels Like in Practice" weaves the Dashboard in. Five image placeholders.
  - `docs/custom-skills-and-team-workflow.md`: three boundary-visualizing image placeholders (managed-block sentinels in editor, `.pre-gator-update` backup, tracked-vs-local file browser), sharpened cross-references.

### Fixed

- **`tests/test_packaging.py::test_version_flag`** — was asserting `"1." in version` (hardcoded), broke silently on the v2.0.0 bump. Now compares CLI output against `gator_command.__version__` imported from the package. Test survives every future version bump automatically; packaging suite's signal restored.

### Internal

- Roadmap intro bumped to v2.4.2, v2.4.1/v2.4.2 hotfix rows logged, new Priority-1 baseline-shift callout describing what the retire-gator-install release train (v2.4.0-v2.4.2) collapsed for the UX surface.
- Inbox: captured the "optional Snyk CLI in pre-commit hook" idea (Architect-flagged, deferred for later prioritization).
- `gator kill dashboard` Codex remediation on `--all + --port` silent precedence — moved into an argparse mutually-exclusive group, added `--dry-run`-requires-a-selector and `--port` range-guard rules, plus 8-test regression suite (`TestSelectorSemanticsAtCliBoundary`).

## [2.4.2] — 2026-07-30

### Fixed

- **`.gator-version` `cli-version` stamps on every successful `gator-update`.** Second fleet-wide hotfix in the v2.4.x line. Under v2.4.0 / v2.4.1 the version stamp only refreshed when the update actually changed files. Repos already at the current template version never re-stamped `cli-version` after a CLI upgrade, so the Dashboard's Fleet "Version" column showed the pre-upgrade CLI forever, and the Update button stayed falsely enabled — clicks were functionally no-ops. `gator-update.py:main()` now stamps `cli-version` unconditionally on successful runs, recording the CLI that last verified the repo. The `updated:` timestamp still gates on actual file changes (preserves the "last modification" semantic).
- Users hitting the "Update button stays enabled but does nothing" symptom on 2.4.0/2.4.1: `pipx upgrade gator-command` to 2.4.2, then one more click on the affected repo will re-stamp `cli-version` and clear the Update indicator.

### Internal

- `TestVersionStampGateExpression` renamed to `TestUpdatedTimestampGateExpression` (its gate expression now describes only the `updated:` timestamp behavior, not `cli-version:`). New `TestCliVersionAlwaysStamps` class with a subprocess-level regression guard: stamps a stale `cli-version` on a fixture repo pointing at the live install, runs `gator-update.py` via subprocess, asserts the file was re-stamped to the running CLI's version.
- Charter `scripts-repo-lifecycle.md` gains a two-gate tripwire on the `plan_updates` entry documenting the split (`cli-version` unconditional, `updated:` gated) and the byte-for-byte sync obligation between package and template `gator-update.py`.

## [2.4.1] — 2026-07-30

### Fixed

- **`gator-update` self-heal for stale `product-source.json`**. Fleet-wide hotfix for a latent bug that v2.4.0 exposed. Every gatorized repo carries a `.gator/product-source.json` recording the absolute path of the Gator install that gatorized it. When pipx is later reinstalled (in particular, re-installed as an editable install pointing at a dev checkout), that absolute path becomes invalid — and every repo in the fleet ends up pointing at a directory that no longer exists. Pre-v2.4.0 this never surfaced because the Dashboard's "Update" button ran `gatorize` (which resolves templates from its own `SCRIPTS_DIR`, ignoring `product-source.json`). Stage 1 of v2.4.0 swapped that endpoint to `gator-update`, which DOES read `product-source.json` — and every Dashboard-triggered update in the fleet started erroring with "product template source not found."
- The fix: `gator-update.py:main()` now self-heals on the "product template source not found" branch. On failure it falls back to `Path(__file__).resolve().parent.parent` — the running install's own root, which by definition has valid templates alongside for both pipx and source-checkout installs. On successful fallback it prints a "Self-healing" warning, rewrites `product-source.json` so future runs don't need to self-heal (preserving the original `installed` date, refreshing the `updated` date), and continues the update. Applied to both `src/gator_command/scripts/gator-update.py` and its template mirror per the Stage 4b sync obligation. If the running install has no usable templates either (fleet-repo direct invocation of the template mirror at `.gator/scripts/gator-update.py`), the original "run --source" error surfaces unchanged.
- Users on v2.4.0 who saw fleet-wide Dashboard Update failures: `pipx upgrade gator-command` to 2.4.1, then click Update on any affected repo — each one self-heals on first click.

## [2.4.0] — 2026-07-30

### Changed

- **Retired the `gator-install` safety branch** — `gatorize` now installs on the current branch, in place. If you want an isolated experiment branch, create one yourself before running gatorize (`git checkout -b my-gator-experiment`); delete it to fully undo. Otherwise, review the diff before you commit — that's the supported undo path. Existing `gator-install` branches in fleet repos are left alone (Gator never deletes user branches).
- **Dashboard "Update" button** now calls `gator-update` instead of `gatorize`. Updates land on the branch you're viewing. No more silent switches to `gator-install`, no more merge-back-to-dev recovery dance. Ungatorized repos clicked as Update now get a clean error pointing at the Gatorize button.
- **`gatorize --yes` flag** for non-interactive use. Refuses to run on a dirty tree. Interactive `gatorize` prints a pre-action summary and a single Y/n confirmation before proceeding.
- **Dashboard Fleet-row "Gatorize" button** now POSTs to a dedicated `/api/repo/<name>/gatorize` endpoint that invokes `gatorize --yes` on the ungoverned repo. Previously it shared the `/update` endpoint, which fell over on the pre-check added by the Update-endpoint fix.
- **`gatorize` "SUCCESS" banner** rewritten with honest, scenario-aware recovery messaging. The safety-branch pattern (`git checkout -b my-gator-experiment` before running gatorize) is documented as the load-bearing supported clean-undo path; three scoped git-native recipes cover the "ran directly on my working branch" case. No blanket `git checkout .` or `git reset --hard` promises — those aren't what they claimed to be for a fresh install.
- **`gatorize` cancel-branch cleanup hint** rewritten. When a user hits `[x] Cancel` at the entry-point prompt, the hint enumerates the files that may already be on disk with a platform-appropriate remove recipe (PowerShell `Remove-Item -Force` on Windows, `rm -f` elsewhere) plus the safety-branch discard recipe.

### Removed

- **Bash installer chain** (`gatorize.sh`, `gatorize-lib.sh`, `gatorize-actions.sh`, `gatorize-post.sh`) — removed. The Python installer (`gator gatorize`, backed by `gatorize.py`) has been the canonical install path since v1.x; the bash chain was a pre-Python-rewrite artifact that shipped in the wheel but was never invoked by any code path (CLI, Dashboard, or tests) in current versions. Anyone still invoking `bash gatorize.sh` should switch to `gator gatorize`.
- **Template `gatorize.py`** (previously shipped to fleet repos at `.gator/.includes/scripts/gatorize.py`) — removed. The file imported from a `gatorize/` sub-package that was never shipped to the template tree, so every fleet-repo attempt to load it failed at import time (silently swallowed by a try/except in fleet-repo `gator-update.py`). Removing the broken artifact removes the confusion; fleet-repo `import_sibling("gatorize")` calls continue to degrade to a no-op the way they always did in practice. Users should invoke `gator gatorize` via the pipx-installed CLI, which uses the canonical PACKAGE copy.
- **`action_feature_branch()` function** and the `GATOR_BRANCH = "gator-install"` constant — removed from `gatorize.py` with the branch-dance retirement.

### Fixed

- **`gatorize.py` `main` fallback bug** — the "delete and start fresh" branch of the old `action_feature_branch()` did `git checkout dev` followed by an unconditional `git checkout main` labeled as a fallback, which actually ran unconditionally and always left the user on `main` regardless of whether `dev` existed. Deleted with the enclosing function.

### Internal

- New `_git_default_branch()`, `print_pre_action_summary(target, scenario)`, `_check_dirty_tree_and_gate(target)` helpers in `gatorize.py` — scenario-aware installer preflight.
- `helpers.AUTO_YES` module-level sentinel + `set_auto_yes()` / `get_auto_yes()` accessors. `helpers.prompt()` / `helpers.confirm()` gain an `auto_yes=None` opt-in parameter — call sites must explicitly declare their non-interactive answer; sites that don't opt in continue to read stdin exactly as before.
- New `resolve_repo_update()` and `resolve_repo_gatorize()` helpers in `dashboard/data.py` (parallel to the existing `resolve_audit_sessions()` pattern). Dashboard POST endpoints delegate to these testable module-level functions.
- Retired **Invariant #14** of the local-agent-overrides plan — the "`gatorize.py` package/template sync" obligation is gone because the template copy is retired.
- Codex enforcer findings on Stages 1, 3, 4, 5 all remediated in-stage — no findings deferred.

Design record: `gator-command/artifacts/2026-07-30-retire-gator-install-branch-implementation-plan.md` (11 review rounds).

## [2.3.0] — 2026-07-29

### Added

- **`gator state` CLI** — new `status` and `repair` subcommands for inspecting and restoring the managed regions in `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`. `status` reports per-file state using a canonical six-state vocabulary (`clean` / `modified` / `legacy` / `corrupted` / `absent` / `foreign`), companion-file presence, and constitution drift for fleet repos. `repair` restores managed regions per state (with `--dry-run`), never touching `*.local.md` files. Ships schema-versioned JSON (`gator-state-v1`).
- **Local agent companion files** — `AGENTS.local.md`, `CLAUDE.local.md`, `GEMINI.local.md` are supported as per-machine personal notes/skills alongside the tracked entry-point files. `gatorize` and `gator update` gitignore them automatically; Gator never reads, writes, or overrides them. A precedence contract in the managed block teaches the pattern at first encounter.
- **Shipped reference-note** — `.gator/reference-notes/local-agent-skills.md` documents the personal-vs-team-shared decision guide, format examples, and how team-shared skills should travel (through `.gator/procedures/` or `.gator/charters/`, not the entry-point file).
- **Constitution drift indicator** — `gator init` appends `· modified from baseline` to the constitution status line when the repo's constitution diverges from the resolved template baseline. Best-effort, warning-only, exempt on the source repo.

### Changed

- **`gator update` refreshes managed blocks** — the sentinel-delimited region in the three entry-point files is now refreshed alongside the standard template overlay. `modified` files get a `.pre-gator-update` sibling backup before overwrite. `legacy` files upgrade in place preserving `## Pre-Gator Instructions`. `absent` files are created fresh. `corrupted` / `foreign` files are skipped (belong to `gator state repair` / `gatorize`). Entry-point work now feeds `.gator-version` timestamping and the completion summary line.
- **`gator update --json`** — declares `"schema": "gator-update-v1"` at top level (previously undeclared) and adds `entry_point_actions` parallel to the existing `hooks` list. Additive within v1; existing consumers unaffected.

### Fixed

- **Package/template `gatorize.py` sync** — new TRIPWIRE and behavioral parity backstop for the two copies (canonical package + template). Same shape as the pre-commit hook trio's sync obligation.

### Internal

- New `managed_block.py` module encapsulates sentinel parsing (`find_managed_block`, `classify_managed_block`, `detect_legacy_gator_content`, `render_managed_region`, `BlockState` enum, `ManagedBlockLocation` dataclass) — reused across `gator-state.py`, `gator-update.py`, and `entry_points.py`.
- New `upgrade_legacy_entry_point()` helper extracted from `entry_points.py` case-2 — behavior-preserving, now also callable from `gator state repair`.
- `TestTemplateSync` — three-layer backstop for the package/template `gator-update.py` pair: behavioral parity across all six states, JSON-schema parity, and AST-equivalence for inlined parsing helpers.

Design record: `gator-command/artifacts/2026-07-28-local-agent-overrides-and-managed-state-plan.md` (11 review rounds, 12 deferred Stage 6 items).

## [2.2.2] — 2026-07-28

### Fixed

- **Charter verification tool** (`gator charter-verify`) — repaired a layout-resolver regression that crashed the drift-checker on every run (it passed a raw path where the layout paths object was expected).
- **Enforcer trust-boundary docs** — corrected guidance that overstated `enforcer-review.py` as hiding review findings from the primary agent. The trust boundary is behavioral: findings are written to `whiteboard.md` (the authoritative record) and the agent presents them to the Architect; `enforcer-review.py` also prints to stdout, so it is not an agent-blind barrier. Standardized primary-agent enforcement on `enforcer-review.py`, clarified that direct CLI enforcers are Architect-run, and fixed dead links in the shipped constitution and procedures.

### Changed

- **Dashboard** — the Fleet → Repo file-content pane now justifies body text (Wikipedia-style) for a cleaner reading layout.

## [2.2.1] — 2026-07-28

### Fixed

- **Mixed-layout update deadlock** — a v2 (`.includes/`) repo whose `reference-notes/` at the root held only scaffolding (`README.md`, `_template.md`) was misclassified as `mixed`, which permanently blocked `gator update` and the dashboard "Update" button with no recovery path (the suggested `--migrate-layout` re-created the same scaffolding and never converged). The layout resolver now exempts a shipped directory at root that contains only user-visible scaffolding; a shipped directory with any real content at root is still correctly detected as `mixed`. Repos stuck in this state resolve to `v2` and update normally on the next run.

## [2.2.0] — 2026-07-28

### Added

- **Nested directory tree in the Repo file browser** — the Fleet → Repo sidebar now renders a real hierarchical tree. Directories expand progressively one level at a time (e.g. `.gator/loops/<run>/`) instead of appearing as pre-exploded flat rows; folders sort first, files newest-first, with `.gator/` landing docs kept at the top.
- **Live auto-refresh** — newly created files (agent artifacts, gator loop outputs) appear in the sidebar within ~5s with no manual refresh. The poll is silent (re-renders only on an actual change), pauses when the browser tab is hidden, and suspends while viewing file/branch history so it never disturbs a reader.

### Changed

- **Markdown reads at full width** — the file-content pane now flows prose across the available width. The renderer coalesces soft-wrapped source lines into single paragraphs instead of emitting one narrow paragraph per line; tables and code blocks still span full width and preserve formatting.
- **Sidebar state survives navigation** — expanded directories, the selected file, and scroll position are preserved across a manual refresh and when leaving the Repo view (to History/Audit) and returning.

### Fixed

- Retired a latent directory-node id collision in the sidebar (paths differing only in punctuation) and a per-render `popstate` listener leak in the Repo view.

## [2.1.1] — 2026-07-27

### Fixed

- **Scaffolding files stay at user-visible root** — `_template.md` and `README.md` in charters/, blueprints/, procedures/ now stay at `.gator/` root on v2 repos instead of being moved to `.includes/`. Agents find templates where they expect them.
- **Migration preserves scaffolding** — `--migrate-layout` no longer moves `_template.md` and `README.md` to `.includes/`
- **Update routes scaffolding to root** — `gator update` on v2 repos puts scaffolding at root, shipped content in `.includes/`

## [2.1.0] — 2026-07-27

### Added

- **Gator Loop** — governed planning debate between AI models. CLI-mediated draftor/reviewer cycle with bounded rounds, turn timeouts, escalation, and durable session residue. 11 subcommands: `start`, `status`, `submit-draft`, `submit-review`, `escalate`, `pause`, `interject`, `end`, `unblock`, `wait`, `tail`, `list`. Three-role token model (draftor, reviewer, architect) with nonce-validated access control.
- **`gator loop wait`** — blocking primitive that lets model sessions sleep until the loop becomes actionable for their role
- **Round-versioned artifacts** — `plan.round-N.md` and `findings.round-N.md` preserved alongside `*.current.md` so the full debate record survives each round
- **Dashboard loop visibility** — `.gator/loops/` browseable in Repo view sidebar, `.tokens.json` blocked at server level (403)
- **`.includes/` layout (v2)** — fresh installs create a clean ownership boundary: user-authored content at `.gator/` root, shipped Gator-native content in `.gator/.includes/`. Layout resolver (`gator_layout.py`) provides dual-layout compatibility for all scripts.
- **`gator update --migrate-layout`** — explicit migration command converts v1 flat repos to v2 `.includes/` layout. Moves shipped content, preserves user files, regenerates hooks, validates result.
- **Layout resolver** — `gator_layout.py` detects v1/v2/mixed/invalid layouts and resolves all `.gator/` paths correctly. 11 scripts converted to use resolver instead of hardcoded paths.
- **v1 deprecation warning** — scripts emit a one-time stderr warning on v1 repos suggesting `--migrate-layout`
- **Cross-vendor loop orientation** — `gator loop join` instructions in CLAUDE.md, AGENTS.md, GEMINI.md entry points and `/loop-join` slash command
- **Loop protocol and artifact formats** — `procedures/gator-loop-protocol.md` (10 rules for AI participants), `reference-notes/loop-artifact-formats.md` (template formats for sketch, plan, findings)
- **Loop blueprint** — `blueprints/gator-loop.md` (end-to-end usage guide for the Architect)
- **Architect override procedure** — `procedures/architect-override.md` with exact `--reason` and `--name` CLI flags

### Fixed

- **Merge conflicts from hook ephemera** — `whiteboard.md`, `commit_draft.md`, `status.json` now gitignored. Hooks read/write locally, `git add` on gitignored files is a silent no-op.
- **Entry point v2 compatibility** — all CLAUDE.md/AGENTS.md/GEMINI.md managed blocks and slash commands reference both `.gator/` and `.gator/.includes/` paths
- **Hook wrappers layout-aware** — `build_git_hook_wrappers()` and `plan_hook_updates()` resolve script path via layout for v2 repos
- **`gator update` refuses mixed/invalid layouts** — prints clean error directing to `--migrate-layout` instead of silently reinforcing broken state

## [2.0.0] — 2026-07-20

### Removed

- **Command-post architecture retired from Individual** — constitution session-opening step removed, `detect_command_post()` deleted from gator-init, `get_repo_topology()` always returns standalone, thin link creation removed from installer, policy sync removed from updater, `gator-init-command-post.py` deleted, `gator-policy-status.py` excluded from wheel
- **Dead policy sync code** — `get_command_post_policy_date()`, `bump_policy_version()`, `find_templates()`, `--no-policy` flag, Channel 2 policy sync block all removed from gator-update
- **Command-post registry writes** — installer no longer writes to `registry.md`, dashboard-only registration via `~/.gator/dashboard-repos.json`

### Fixed

- **Installer safety branch invariant** — Python scenarios 3 and 5 now create `gator-install` branch before upgrade (matching shell behavior)
- **Shell scenario 3 common tail** — upgraded repos now get entry point refresh, dashboard registration, and product-source update
- **`--no-policy` callers** — removed from dashboard, gatorize, and morph paths after flag retirement
- **Shell entry-point marker** — fix `REPO_ROOT_MARKER` back to `COMMAND_POST_MARKER` for detection

## [1.9.3] — 2026-07-19

### Fixed

- **Hook warning mode on ungoverned branches** — hook wrappers now check if `.gator/scripts/gator-pre-commit.py` exists before calling it. On branches where `.gator/` hasn't been merged, prints a warning and allows the commit instead of hard-blocking with a file-not-found error

## [1.9.2] — 2026-07-19

### Fixed

- **Update endpoint fallback** — fix repo lookup to use standalone data shape (`repos` not `fleet.repos`)
- **Dead test removed** — delete `test_command_post_entry_gets_keyed` which tested removed `inject_command_post()`

## [1.9.1] — 2026-07-19

### Removed

- **Command-post dead code** — remove `inject_command_post()`, `collect_fast_data()`, and `find_command_post`/`parse_registry` imports from dashboard. Simplify session resolution to `local-repo` only

## [1.9.0] — 2026-07-19

### Added

- **Fleet "Add Repository"** — register new repos from the Dashboard Fleet view via modal with auto-discovery of local Git repos and manual path input
- **Dashboard logo** — replace text brand ("Gator") with gator-in-motion logo in sidebar, transparent PNG with proper MIME serving
- **Dashboard static asset MIME support** — extend `_send_file()` to serve `.jpg`, `.jpeg`, `.png`, `.svg` with correct content types
- **Gatorize vs Update row distinction** — Fleet rows show blue "Gatorize" button for ungoverned repos, "Update" for governed repos

### Changed

- **Retire command-post mode** — Dashboard no longer detects or depends on a command-post repo. Single standalone mode for all users. Settings view removes topology controls. Policy-synced topology endpoint returns "no longer supported"
- **Registry path normalization** — MSYS-style `/c/Users/...` paths automatically converted to Windows-native on load

## [1.8.10] — 2026-07-03

### Fixed

- **Public docs deploy** — add how-to-use-gator.md and how-gator-works.md to PUBLIC_DOCS allow-list so they ship to the public repo's docs/ directory

## [1.8.9] — 2026-07-03

### Added

- **How Gator Works** — public-facing technical explainer: constitution, charters, the loop, commit-time enforcement, multi-model review, dashboard. Ships to fleet repos via gator-starter template

## [1.8.8] — 2026-06-30

### Added

- **Docs view in dashboard** — new top-level sidebar section surfaces `.gator/docs/` content for the selected repo without folder-hunting
- **How to Use Gator** — user-facing guide covering install, gatorize, bootstrap, the governance loop, and what you can ask your AI agent to do. Ships to fleet repos via gator-starter template

## [1.8.4] — 2026-06-28

### Added

- **Curated public docs** — only ready docs ship to the public repo (controlled via `PUBLIC_DOCS` list)
- **Auto-stamped VERSION** — deploy writes VERSION from pyproject.toml, not a static file

### Changed

- **Removed active-threads/** — legacy Memex concept not in the Gator constitution
- **Procedures restored** — moved from vault back to `gator-command/procedures/` (safe now that `gator-command/` is no longer deployed)
- **Release procedure updated** — CHANGELOG step added, reflects simplified deploy

## [1.8.1] — 2026-06-28

### Added

- **Knowledge directory templates** — every `.gator/` directory (artifacts, threads, blueprints, policies, procedures, reference-notes, field-guides, vault) ships with a README explaining its purpose and a `_template.md` for new files
- **Gator Dashboard self-upgrade** — Updates view checks PyPI and runs `pipx upgrade gator-command` with automatic server restart
- **Fleet version tracking** — `cli-version` in `.gator-version` shows which Gator version gatorized each repo
- **Inline enforcement dropdown** — change strict/warn/off directly in the Fleet table
- **Dot-pulse activity animation** — non-shifting working indicator for Update actions

### Changed

- **Simplified public repo** — removed `.gator/` and `gator-command/` from deployed repo (command-post retirement). Public repo is now `gator-engine/` + root files only
- **README rewritten** — clear intro explaining what makes Gator different, copyable command blocks, dashboard-first upgrade path
- **Roadmap rewritten** — Individual (July 5 release) and Enterprise (late July MVP) tracks with clear scope
- **Deploy pipeline simplified** — removed `build_command_post_layer()`, `build_self_governance()`, entry point generation
- **Version resolution consolidated** — single canonical `get_version()` in gator_core (pyproject.toml > metadata > git > VERSION)
- **Module splits** — gator-deploy.py (4 modules), gator-pre-commit.py (4 modules) for cleaner architecture
- **Repo browser whitelist** — shows only knowledge base files, hides infrastructure
- **Settings sidebar removed** — enforcement now inline in Fleet table
- **Update button runs gatorize** — full self-heal (templates, hooks, version stamp) instead of template-only overlay
- **Command reference rewritten** — uses `gator` CLI commands, not script paths
- **Architecture doc updated** — removed command-post layout, simplified for Individual model

### Fixed

- **Public repo test alignment** — generic path patching, source-only test exclusions
- **File indentation** — files under folders properly indented in repo sidebar
- **Enforcement persistence** — dropdown changes persist across page refresh
- **Upgrade file lock** — detached helper process releases `gator.exe` before `pipx upgrade` on Windows

## [1.0.0] — 2026-06-01

First public release. Constitutional governance for AI-assisted software development.

- Pre-commit hook with charter-alongside-code enforcement
- Cross-model entry points (Claude Code, Codex, Gemini CLI)
- Fleet governance: gatorize, fleet-report, drift detection
- Session archaeology: cross-vendor extraction
- Audit CLI with text/JSON/HTML output
- `pipx install gator-command` packaging
