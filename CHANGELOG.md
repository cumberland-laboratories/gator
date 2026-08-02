# Changelog

All notable changes to Gator are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/). Gator uses [semantic versioning](https://semver.org/).

## [2.5.0] — 2026-08-02

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
