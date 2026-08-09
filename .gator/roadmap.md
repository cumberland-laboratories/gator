# Roadmap

Updated 2026-08-09 (post-v2.6.0). Priority-ordered within each track.

**Status key**: Done · Building · Designed · Considering · Deferred

---

## Product

One product: **Gator** — Git-native governance for AI-assisted engineering. Ships as `pipx install gator-command`. Open source under **Apache License 2.0** (see [`LICENSE`](../LICENSE) and [`NOTICE`](../NOTICE); the MIT → Apache 2.0 flip landed in Phase 3c, 2026-08-01). Now at **v2.5.4**, published from the new public monorepo `github.com/cumberland-laboratories/gator`.

Gator includes local repo governance, pre-commit enforcement, dashboard, CLI, and gator loop. **Enterprise capabilities** (API-first fleet management, session evidence, audit reporting, centralized policy) are an optional layer — same codebase, activated by configuration. Monorepo convergence complete (Phase 3b-3, 2026-08-02).

## Current Priority

**Two priorities, in order** (monorepo convergence — the previous #3 — shipped on 2026-08-02):

1. **Gator: ridiculously easy to install and use.** The product must be frictionless from first install through daily use. Dashboard-first UX, one-command install, zero-config governance. Every rough edge in the install/onboard/update flow is a priority bug.

2. **Gator Loop: smooth the rough edges.** The loop works end-to-end — all 12 subcommands shipped including `wait`, `pause`, `interject`, `end`, and round-versioned artifacts. What remains is better Dashboard integration (events timeline rendering, session summary card) and protocol refinements from real-world usage. The loop is the first multi-agent governance primitive — it needs polish before broader adoption.

## Strategic Direction

- **Open source distribution** (Apache 2.0) for both the core CLI and Enterprise capabilities
- **Maximum developer adoption** through frictionless installation
- **Dashboard-first product surface** — CLI commands become internal implementation details
- **Multi-agent governance** — gator loop as the foundation for governed AI collaboration

---

## Gator — Active Development

### Done

| Feature | Version | Notes |
|---------|---------|-------|
| Cross-platform install | v1.0+ | `gatorize.py`, no bash required |
| Pre-commit hook | v1.0+ | Validation, trailers, status.json, charter enforcement, whiteboard |
| Standalone mode | v1.1+ | Repos governed without command post |
| Standalone dashboard | v1.1+ | Machine-local registry, fleet view, repo browser |
| `pipx install gator-command` | v1.2+ | PyPI package, `gator` CLI entry point |
| Git history in dashboard | v1.2+ | File history + branch history dropdowns |
| Dashboard search | v1.2+ | Cross-doc AND/OR boolean, in-doc highlight, copy content |
| Deploy pipeline | v1.2+ | PyPI publish, version stamping, session cleanup |
| Module splits | v1.7.0 | `gator-deploy` (4 modules), `gator-pre-commit` (4 modules) |
| Fleet UX overhaul | v1.7.1 | Inline enforcement, version-based Update, dot-pulse animation |
| Self-upgrade from dashboard | v1.7.3 | PyPI check + `pipx upgrade` with automatic restart |
| How to Use Gator | v1.8.8 | User-facing guide |
| How Gator Works | v1.8.9 | Public technical explainer |
| Dashboard logo | v1.8.11 | Gator-in-motion brand identity |
| Fleet Add Repository | v1.9.0 | Dashboard modal with auto-discovery + manual path input |
| Dashboard mode collapse | v1.9.0 | Single standalone mode, command-post mode retired |
| Gatorize vs Update distinction | v1.9.0 | Fleet rows show blue "Gatorize" for ungoverned repos |
| Registry path normalization | v1.9.0 | MSYS `/c/` paths auto-converted on Windows |
| Hook warning mode | v1.9.3 | Warn instead of blocking on branches without `.gator/` |
| Command-post full retirement | v2.0.0 | Constitution, init, topology, installer, updater, policy-status all retired from Individual |
| Installer safety branch fix | v2.0.0 | All scenarios create `gator-install` branch before mutation |
| **Gator Loop** | v2.1.0 | Governed planning debate between AI models. 12 subcommands (start, status, submit-draft, submit-review, escalate, pause, interject, end, unblock, wait, tail, list), 3-role tokens (draftor, reviewer, architect), round-versioned artifacts |
| **`.includes/` layout (v2)** | v2.1.0 | Shipped content in `.gator/.includes/`, user content at root. Layout resolver, migration command, dual-layout compat |
| **Merge conflict fix** | v2.1.0 | `whiteboard.md`, `commit_draft.md`, `status.json` gitignored |
| **Dashboard loop visibility** | v2.1.0 | Loops browseable in sidebar, `.tokens.json` blocked at server level |
| **Cross-vendor loop orientation** | v2.1.0 | Loop join instructions in all entry points + `/loop-join` slash command |
| **Architect override procedure** | v2.1.0 | Documented `--reason` and `--name` flags for clean override UX |
| **Repo file browser overhaul** | v2.2.0 | Fleet → Repo browser: true nested directory tree, full-width markdown rendering, sidebar state retention across refresh + view-switch, and 5s auto-refresh when new files arrive. [Design record](artifacts/2026-07-28-gator-dashboard-fleet-repo-file-sidebar-and-content-fixes-implementation-plan.md) |
| **Mixed-layout update deadlock fix** | v2.2.1 | `gator update` no longer deadlocks on scaffolding-only shipped dirs in mixed v1/v2 layouts |
| **Charter-verify layout-resolver fix + enforcer trust-boundary docs + justified body text** | v2.2.2 | Repaired `gator charter-verify` crash (passed raw path where layout paths object expected); corrected enforcer trust-boundary docs (behavioral not agent-blind); Fleet → Repo file-content pane now justifies body text (Wikipedia-style) |
| **Local-agent overrides + managed-state layer** | v2.3.0 | New `gator state` CLI (status + repair, six-state vocabulary, schema-versioned JSON); `CLAUDE.local.md` / `AGENTS.local.md` / `GEMINI.local.md` companion files (gitignored, precedence contract); `gator update` refreshes managed blocks with `.pre-gator-update` backups + `"schema": "gator-update-v1"` JSON; constitution drift indicator in `gator init`; shipped `local-agent-skills.md` reference-note. [Design record](artifacts/2026-07-28-local-agent-overrides-and-managed-state-plan.md) — 11 review rounds |
| **Retire `gator-install` branch + update in place** | v2.4.0 | `gatorize` no longer creates or switches to a `gator-install` safety branch — installs on the current branch, in place. New `--yes` flag with per-site opt-in contract. Dashboard "Update" button now calls `gator-update` (not `gatorize`), fixing the silent branch-switch bug. New `POST /api/repo/<name>/gatorize` endpoint for the ungoverned-repo install path. Bash installer chain (`gatorize.sh`, `gatorize-lib.sh`, `gatorize-actions.sh`, `gatorize-post.sh`) retired — ~2400 lines removed. Template `gatorize.py` retired (broken import chain, silently swallowed). Honest scenario-aware recovery messaging replaces the naive `git checkout .` / `git reset --hard` hints. Cross-platform cancel-hint recipe (Windows PowerShell + bash). [Design record](artifacts/2026-07-30-retire-gator-install-branch-implementation-plan.md) — 11 review rounds. Codex enforcer findings on Stages 1, 3, 4, 5 all remediated in-stage. |
| **product-source.json self-heal** | v2.4.1 | Fleet-wide hotfix. v2.4.0's Dashboard-Update-endpoint swap (from `gatorize` to `gator-update`) exposed a latent bug: every gatorized repo captured an absolute `gator_root` path at install time, and a later pipx reinstall (especially editable) invalidated it. `gator-update.py:main()` now self-heals — on "product template source not found" it falls back to `Path(__file__).parent.parent` (the running install), rewrites `product-source.json`, continues the update. Sync-obligation-bound between package and template mirror. |
| **`cli-version` stamps on every successful update** | v2.4.2 | Second fleet-wide hotfix. Under v2.4.0-v2.4.1 `gator-update` only stamped `cli-version` in `.gator-version` when files actually changed — repos already at the current template version never re-stamped after a CLI upgrade, so the Dashboard Fleet Version column stayed on the pre-upgrade CLI forever and the Update button stayed falsely enabled. Semantic split: `cli-version` now stamps unconditionally (records "who last verified"), `updated:` timestamp still gates on file changes (preserves "last modification"). |
| **`gator kill dashboard` + discovery-roots + Dashboard-first docs** | v2.4.3 | New CLI verb `gator kill dashboard [--all \| --port N \| --dry-run]` for killing stale Dashboard processes (cross-platform: Windows `wmic`/`taskkill`, Unix `pgrep`/`SIGTERM`; mutually-exclusive selectors at argparse). New `GATOR_DASHBOARD_DISCOVERY_ROOTS` env var scopes the Add-Repository auto-discovery scan. New sleek-profile Dashboard sidebar logo. Documentation refresh across README + 3 docs, all restructured Dashboard-first with 17 image placeholders wired for the v2.4.5 screenshot pass. |
| **Dashboard History no longer crashes on non-cp1252 git output** | v2.4.4 | Windows hotfix. `gator_core.git()` was using bare `text=True`, decoding subprocess stdout with the platform-default codec (`cp1252` on Windows) — crashed on any git output containing bytes unrepresentable in cp1252 (non-ASCII commit subjects, diacritic author names, trailer content copied from external sources). Symptom: History endpoint returned "Empty reply from server." Fixed with `encoding="utf-8", errors="replace"` — extended to `gator_core.get_version()`'s git subprocess calls and `dashboard/helpers.py::run_text` via a belt-and-suspenders sweep. Charter tripwire added in `scripts-core-library.md`. |
| **HTML file support + Docs view broadening + wide-image sizing + first screenshot tranche + hero banner** | v2.4.5 | `.html`/`.htm` files in `.gator/` now visible in Dashboard file browser and served as `text/html; charset=utf-8` — clicking opens in new tab (`window.open(rawUrl, "_blank", "noopener")`). Auto-load code paths skip HTML to defend against popup-blocker. Opens the governance-HTML-reports channel (mermaid flowcharts, generated audit visualizations). Docs view broadened to list both `.gator/docs/` and repo-root `docs/`. `.repo-content` gets `min-width: 0` + `overflow-x: auto` so wide images shrink-to-fit. Six real Dashboard screenshots landed in `docs/images/` (from a fictional demo workspace) and wire up the README + 2 docs. New hero banner + social card (composed by Gemini from source assets), shields.io badge rows (core + agent-compatibility). YAML Issue Forms replace markdown templates. Dashboard favicon added. First proper GitHub Release since v1.8.10 — catch-up covers v2.3.0 → v2.4.5. `gh release create` folded into `release-and-deploy.md`. |
| **Monorepo cutover** | v2.5.1 | First release from the new public `gator` monorepo. Repository home stays at `github.com/cumberland-laboratories/gator`; the pre-cutover MIT-era history archived at `-legacy-pre-monorepo`. Apache 2.0 across the whole public tree. Same wheel, same install, same CLI. `scripts/monorepo-bootstrap.py` (reproducible source→monorepo staging) + `scripts/monorepo-validate.py` (9-check validation runner with baselined stale-path gates) committed to source for reproducibility. Codex Finding 1 (enterprise dispatcher catch-all masking real failures) fixed with three-ordered-check pre-delegation pattern. 2.5.0 skipped due to TestPyPI filename-permanence policy. Full RC → prod pipeline via OIDC exercised end-to-end. |
| **Hook hardening: change-type enum + migrate_layout duplicates + docs vault** | v2.5.2 | Two governance-hook fixes surfaced by the cutover. (1) `gator-pre-commit.py::validate_hard_rules` now validates `change-type` against the schema enum (`feature\|fix\|refactor\|docs\|test\|release\|maintenance\|review\|governance\|""`); rejects plausible-sounding drift like `bugfix` at commit time with helpful typo hints. Sync obligation with `gator-session-snippet-v2` schema pinned. (2) `gator-update.py::migrate_layout()` Step 5 now mirrors Step 4's duplicate handling — `--migrate-layout` self-repairs the mixed-layout state that required manual cleanup during the monorepo cutover. Regression pins for both. Also vaulted 12 pre-monorepo docs (installation/upgrade/getting-started etc.) that described the retired `gator-engine/scripts/gatorize.sh` install flow. |
| **Hook hardening recovery** | v2.5.3 | Recovery release for v2.5.2. The v2.5.2 wheel was cut from a commit that silently dropped most of the intended hook-hardening files during `git add` (Windows Git Bash trailing-backslash continuation quirk). Only the `migrate_layout` src fix, the version bump, and the docs vault actually landed. v2.5.3 ships the rest — change-type enum validation with typo hints, regression pins for both fixes (`tests/test_precommit_validation.py`, `tests/test_layout.py::TestMigration::test_shipped_dir_duplicates_get_removed`), charter tripwires. Also: `CONTRIBUTING.md ## Branching` section documenting the solo dev→main flow; `.gator/charters/INDEX.md` monorepo refresh; `mkdocs.yml` nav restructured to remove entries pointing at docs vaulted in 2.5.2. First release under the new lightweight dev→main branching flow. |
| **Enterprise transcripts-first MVP + Phase 4 stabilization cleanup + dispatcher reconciliation** | v2.6.0 | The Enterprise transcripts-first MVP substrate lands in-tree (Migration 009 transcript-custody tables + Migration 010 query views + `POST /api/v1/{commits,transcripts}/ingest` + `GET /api/v1/transcripts/*` + `gator-enterprise transcripts pull` end-to-end with Claude Code discovery + upload + `Gator-Machine-Id` trailer emission + multi-vendor `.gator/active-vendor-session.json` v2 schema with PID attribution). Base wheel unchanged in shape; enterprise-cli install stays source-checkout-only for this release (single-pipx path is post-2.6 packaging). Phase 4 stabilization cleanup retires the pre-transcripts-first evidence-in-Git design: `_do_repo_init` no longer creates `.gator/session-blocks/` or un-gitignores it (P1.2); `POST_COMMIT_HOOK` template no longer runs per-commit block generation (P1.3); 4 obsolete Enterprise docs get historical banners (P1.5); `docs/how-gator-works.md` misleading `gator enterprise setup` claim rewritten (P1.4). Base-wheel dispatcher `CLIENT_SUBCOMMANDS` + `SERVER_SUBCOMMANDS` reconciled to reflect real enterprise-cli verbs (P2.1) — `transcripts` + `commits` added to `ENTERPRISE_CLI_VERBS` (P1.1), closing the "MVP unreachable from `gator enterprise <verb>`" gap. `.tmp/` gitignored (P2.3). 12 new regression pins across `tests/test_gator_enterprise.py` and `enterprise/tests/test_activate_atrisk.py`. Version-narrative note: the Phase 4 planning artifacts framed this as "Gator 3.0"; resolved to `2.6.0` under strict semver (API additive, not breaking). Full plan chain: `.gator/vault/artifacts/2026-08-09-gator-3.0-{stabilization-plan,next-steps-sketch,release-readiness}.md` + `2026-08-09-enterprise-{post-mvp-cleanup-plan,architect-smoke-test}.md` + MVP plan/ADR at `2026-08-08-enterprise-transcripts-first-*`. |
| **Session-hook self-heal + migration convergence + drift visibility** | v2.5.4 | Fleet-wide fix set for silent failures at the session-hook seam. Since the v2 `.includes/` split shipped, `gator-session-open.py` had been throwing `AttributeError` on every v2 repo (hardcoded `str(gator_dir / "scripts")` and passed raw `Path` into `ensure_git_hooks()` which expects `GatorPaths`) — swallowed by the silent-hook contract's `except → sys.exit(0)`. Silent self-heal became silent no-op fleet-wide. Fix uses v2-first probe + `get_gator_paths()`. Vendor-hook templates (Claude/Codex/Gemini) now ship v2 script paths so `merge_hooks_into_settings` auto-corrects existing repos on next update. `--migrate-layout` Step 5 handles both-dirs-exist case (closes Issue #6, discovered on `code/donoriq`): `__pycache__/` and legacy `hooks/` get `rmtree`'d, unknown dirs go through new `_merge_dir_files_only()` (dest-wins recursive merge). New `_enumerate_mixed_residue()` prints the specific blocking paths on non-convergence instead of opaque `check conflicts`. `--migrate-layout` auto-refreshes vendor hooks on convergence — single-command v1→v2 upgrade. New `gator_diagnostics.log_hook_event()` writes bounded (200-line) machine-local log to `.gator/diagnostics/hooks.log` (gitignored) on non-happy-path `ensure_git_hooks()` returns — silent regressions at this seam are now visible. 11 regression pins across `tests/test_layout.py::TestMigration` and 8 in new `tests/test_session_hooks.py`. Full plan (with 4 Codex-adversarial review passes): `.gator/vault/artifacts/2026-08-03-update-and-begin-session-bugs-implementation-plan.md`. First release using the release-and-deploy.md procedure rewritten for post-cutover flow. |

### Building — Priority 1: Post-Install Onboarding & UX

The `.exe` installer is deferred — the target audience (developers using AI tools) has Python and CLI fluency. The real gap is what happens after `pipx install gator-command`.

**v2.4.x baseline shift (2026-07-30)**: the retire-gator-install release train (v2.4.0-v2.4.2) collapsed the whole install/update surface into a much simpler shape:

- **`gator gatorize`** — installs on the current branch, in place. Prints a scenario-aware pre-action summary, asks a single Y/n gate, refuses on a dirty tree under `--yes`. No branch-dance, no merge-back-to-dev ritual, no `gator-install` branch to explain in every install doc.
- **Dashboard Update** — invokes `gator-update` on the current branch. Result is exactly what the button label says. No silent branch switches, no cross-branch contamination. Non-interactive fragility is gone (`--yes` propagates cleanly, self-heal recovers from stale `product-source.json`).
- **Dashboard Gatorize** (Fleet-row button, ungoverned repos) — its own dedicated `/api/repo/<name>/gatorize` endpoint. No more self-referential 400s.
- **Fleet Version column** — stamps on every update, so drift is visible and Update-button enable/disable is trustworthy.
- **Recovery messaging** — the safety-branch pattern (`git checkout -b my-gator-experiment` BEFORE running gatorize) is the documented supported clean-undo path. Scoped git-native recipes for uncommitted / committed / untracked-file cases. No overclaiming.
- **Codebase** — ~2400 lines of retired bash / template gatorize.py deleted. Fewer surfaces to audit, fewer scenarios to explain, fewer failure modes to document.

The remaining Priority-1 items below build on this new baseline. Several of them (welcome screen, in-dashboard next-step, getting-started narrative) got materially simpler because the underlying install/update flow no longer has weird edges to warn users about.

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **First-run welcome screen** | Considering | Empty fleet → show welcome with "Add Repo" + "Gatorize" prominently, not empty table |
| 2 | **Getting-started documentation** | Considering | Linear path: install → dashboard → add repo → gator init → first commit → see result. Complements the new `docs/custom-skills-and-team-workflow.md` shipped in v2.4.0 Stage 7 |
| 3 | **In-dashboard next-step guidance** | Considering | After adding a repo, show "Open your AI CLI and type gator init" hint |
| 4 | **Server reuse detection** | Considering | `gator dashboard` finds running instance instead of starting duplicate |
| 5 | **Branding consistency** | Considering | Clean up any stale "Gator" vs "Gator Desktop" vs "Gator Dashboard" inconsistencies in docs |
| 6 | **HTML file support in Dashboard** | Done (v2.4.5) | Shipped as new-tab open (`window.open` on `/raw/`) rather than sandboxed iframe. Iframe was the original plan; new-tab was chosen to sidestep CSP and iframe-sandbox complexity while still delivering the "governance HTML reports render inline" outcome. |

*(Shipped items no longer listed here: "File sidebar auto-refresh" landed in v2.2.0 as part of the Repo file browser overhaul; "Justified body text in Repo content" landed in v2.2.2 — see Done above. "Gatorize `--batch` mode" landed in v2.4.0 as the `--yes` flag with per-site opt-in contract, folded into the retire-gator-install work — see Done above.)*

### Building — Priority 2: Gator Loop Polish

Shipped in v2.1.0: `wait`, `pause`, `interject`, `end`, round-versioned artifacts, architect token, dashboard loop sidebar. What remains is refinement from real usage.

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **Loop dashboard events timeline** | Designed | Render `events.jsonl` as formatted timeline table instead of raw JSON. [Plan](artifacts/2026-07-27-loop-usability-implementation-plan.md) |
| 2 | **Loop dashboard session card** | Considering | Summary card showing loop stage, rounds, join status on Repo overview |
| 3 | **Loop protocol refinement** | Considering | Update protocol and artifact formats based on live trial learnings |
| 4 | **Auto-trigger update after migration** | Considering | `--migrate-layout` could auto-run `gator update` to refresh scripts |

### Done — Monorepo Convergence *(shipped 2026-08-02 as v2.5.1)*

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **Merge assessment** | Done | [Assessment](artifacts/2026-07-16-monorepo-merge-assessment.md) complete |
| 2 | **Convergence plan** | Done | [Plan](artifacts/2026-07-16-monorepo-convergence-plan.md) reviewed through 5 Codex passes; reconciled + release-integrated 2026-08-01 as [implementation plan](artifacts/2026-07-21-monorepo-convergence-implementation-plan.md) |
| 3 | **Phase 1 — Product-contract decisions** | Done | Naming, evidence default, packaging boundary ratified 2026-07-31. [Decisions](artifacts/2026-07-31-monorepo-product-contract-decisions.md) |
| 4 | **Phase 2 — Contracts layer** | Done | `contracts/` at repo root: 4 schemas (2 JSON, 2 markdown), 4 reference docs, 5 pytest suites, 33 checks. Wired into `pytest.ini`. Fresh 2026-08-01. |
| 5a | **Phase 3a — Packaging boundary** | Done | `[project.optional-dependencies].enterprise-server` added to pyproject.toml; `gator enterprise` subcommand group registered in `cli.py`; stub dispatcher at `src/gator_command/scripts/gator-enterprise.py` covering setup/status/sync/audit/disconnect/server/db/policy/org/fleet (all print "coming in Phase 4" and exit 0); charter at `scripts-enterprise.md`; wheel builds clean and `Provides-Extra: enterprise-server` present in METADATA. Fresh 2026-08-01. |
| 5b | **Phase 3b — Release pipeline (GH Actions A/B/C)** | Done (deploy step deferred) | All three workflows shipped, wired but disabled behind `vars.RELEASE_PIPELINE_ENABLED == 'true'`. 3b-1: Workflow A source CI (`.github/workflows/source-ci.yml`) — fast lane (Ubuntu + Windows × Py 3.9 + 3.13, tests + contracts) + packaging lane (Ubuntu × Py 3.13, wheel build + venv install). 3b-2: Workflow C promote-to-PyPI (`.github/workflows/promote-to-pypi.yml`) — approval-gated via `pypi-production` protected environment, OIDC trusted publisher, hard no-rebuild + no-static-token invariants. 3b-3: Workflow B release-candidate (`.github/workflows/release-candidate.yml`) — fires on `vX.Y.Z-rcN` tags, builds wheel once, OIDC-publishes to TestPyPI via `pypi-test` environment (no approval), matrix smoke-tests on Ubuntu + Windows from TestPyPI. Cross-workflow artifact-name coupling contract verified. Deploy-to-public-gator step is a STUB (`exit 78 EX_CONFIG`) until the public monorepo cutover (Option B) picks between same-repo / GitHub App / PAT — that step is the only remaining blocker to full pipeline activation. [Design](artifacts/2026-07-27-public-release-pipeline-design.md) · [Charter](charters/release-pipeline.md) |
| 5c | **Phase 3c — Apache 2.0 mechanical migration** | Done | LICENSE flipped MIT → Apache 2.0 (canonical text); new NOTICE at repo root; `pyproject.toml` `license = "Apache-2.0"` + `License :: OSI Approved :: Apache Software License` classifier; `README.md` + `PYPI_README.md` license references updated; `docs/how-gator-works.md` retired the "Gator Individual/Enterprise" as-products phrasing per Decision A; `constitution.md` + `src/gator_command/templates/gator-starter/constitution.md` glossary refreshed to name Gator as one product with Enterprise as an optional capability; `CONTRIBUTING.md` refreshed with Apache 2.0 inbound-license statement, DCO sign-off requirement, and SPDX source-header policy. Wheel METADATA verified: `License: Apache-2.0`, both LICENSE and NOTICE ship in `dist-info/licenses/`. Provenance sweep (Track E) deferred as a follow-on. 2026-08-01. [Checklist](artifacts/2026-07-18-apache-2-mechanical-migration-checklist.md) |
| 6 | **Phase 4 — Selective Enterprise port** | Done (substrate) | 4a: shared snippet infrastructure ported (`record_commit_and_emit_snippet` et al., `phase_cleanup` guarded emit, Decision B amended). 4b-substrate: `gator_core.is_enterprise_active(gator_dir)` canonical fail-closed reader; `gator-session-block.py` ships. 4c-A: real setup/status/disconnect local-marker commands with credentials-before-marker ordering. 4c-B: `setup --install-hooks` MACHINE-scoped vendor SessionStart install (originally `enterprise_vendor_hooks.py`; moved to enterprise-cli in 4e). 4c-C-1: MACHINE-scoped credential store (chmod 600 on POSIX; moved to enterprise-cli in 4e). 4c-C-2: HTTP client with typed exceptions; real `sync` + `audit` grounded in enterprise-mvp `app/routes/` (stdlib client deleted in 4e; enterprise-cli's httpx client is the sole one going forward). 4d-substrate: server-side Migration 008 tracked — adds `transcript_session_id VARCHAR(255) NULL` column to `commits`, completes the client → server pipe for the snippet field 4a already emits. |
| 6e | **Phase 4e — Enterprise consolidation** | Done | Per Architect direction 2026-08-02 ("we should have ALL the prototype enterprise code in the enterprise/ folder ... we should not leave pieces behind in gator-command at all"): bulk-ported the full `enterprise/` tree from enterprise-mvp (114 files: `app/` FastAPI service including `routes/crypto.py` envelope encryption, `enterprise-cli/` gator_enterprise_cli package including all client-side commands, full Alembic 001-008 migration chain, `tests/`, `docs/`, deployment scaffolding). Moved `enterprise_credentials.py` and `enterprise_vendor_hooks.py` from `src/gator_command/scripts/` into `enterprise/enterprise-cli/gator_enterprise_cli/`; deleted `enterprise_client.py` (the enterprise-cli package's httpx-based `client.py` is authoritative). Refactored `src/gator_command/scripts/gator-enterprise.py` from mixed real/stub dispatcher into a THIN backwards-compat dispatcher that imports `gator_enterprise_cli` and delegates — or prints `[gator-enterprise-unavailable]` + exits 69 (EX_UNAVAILABLE) if the enterprise-cli package isn't installed. Updated `pyproject.toml` to drop the three `enterprise_*.py` entries from `package-data`. Moved tests: `test_enterprise_credentials.py` → `enterprise/tests/test_credentials.py`, `test_enterprise_vendor_hooks.py` → `enterprise/tests/test_vendor_hooks.py`. Shrunk `test_gator_enterprise.py` from 47 tests to ~15 covering only the thin dispatcher. Pruned `test_packaging.py` — deleted 3 end-to-end round-trip tests, added `test_gator_enterprise_all_verbs_exit_unavailable_in_base_install` and `test_wheel_does_not_ship_enterprise_cli_modules` as regression guards. Charter `scripts-enterprise.md` restructured for new tree; INDEX row expanded. Cutover plan artifact updated with Phase 4e addendum. Enterprise integration polish (single-pipx-command install of enterprise-cli, httpx/urllib client reconciliation, envelope encryption UX, green enterprise test suite) is explicitly deferred as post-cutover work per Architect. |
| 7 | **Phase 3b-3 — Public monorepo bootstrap + GitHub cutover** | Done (2026-08-02) | Full sub-phase sequence executed: 3b-3-recon [tree-map + sub-phase plan](artifacts/2026-08-02-monorepo-cutover-plan-and-tree-map.md); 3b-3-A staging skeleton via `scripts/monorepo-bootstrap.py`; 3b-3-B `.gator/` scaffold with `EXCLUDE_KNOWLEDGE_FILES` + `PATH_REWRITES`; 3b-3-C validation via `scripts/monorepo-validate.py` (9 checks, baselined stale-path gates for Codex Finding 2 both categories); 3b-3-D GitHub cutover (legacy repo renamed to `-legacy-pre-monorepo` + archived + private; fresh `cumberland-laboratories/gator` created public+Apache; local dirs swapped; Genesis commit force-pushed). Codex Finding 1 (enterprise dispatcher catch-all masking real failures) fixed with three-ordered-check pre-delegation pattern. First monorepo release **v2.5.1** shipped to production PyPI 2026-08-02 via the release-candidate → promote-to-pypi OIDC pipeline (v2.5.0 skipped due to TestPyPI filename-permanence policy after RC iteration). |
| 8 | **Phase 5 — Source-tree normalization (optional)** | Deferred | Only if packaging/import pain later justifies collapsing `enterprise/` into `src/gator_command/enterprise/`. |

### Considering

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **SonarCloud integration** | Considering | Code quality gates for the public repo |
| 2 | **Branch switching in Repo view** | Considering | Replace static branch label with dropdown |
| 3 | **MCP server** | Considering | Interesting surface for AI tool integration |
| 4 | **Audit view visualizations** | Considering | Session timeline, decision density, file heat map |
| 5 | **Legacy Memex retirement** | Considering | Cognitive cleanup of large legacy surface |

### Deferred

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **Codex model name canonicalization** | Deferred | Quality cleanup for session identity |
| 2 | **In-flight session visibility** | Deferred | Sessions only visible after first commit |
| 3 | **enforcer-review.py split** | Deferred | Architectural hygiene |

---

## Gator Enterprise — Post-MVP Hardening

E1-E8 shipped. Encryption phase complete. The service has 42 endpoints, operator CLI with 10 command groups, envelope encryption for session blocks, and vendor session extraction.

### Done

| Phase | What | Notes |
|-------|------|-------|
| E1 | Foundation | FastAPI skeleton, PostgreSQL schema, Alembic, API token auth, health endpoint |
| E2 | Git provider | GitHub App adapter, webhook receiver, repo sync, scheduled refresh |
| E3 | Policy engine | Policy CRUD, versioning, repo targeting, rollout state machine, PR distribution |
| E4 | Evidence & reporting | Governance artifact ingestion, materialized reports, drift detection |
| E5 | Dashboard API | Fleet status, repo detail, policy compliance, session summaries, audit timeline |
| E6 | Hardening | Error handling, structured logging, rate limiting, operator CLI |
| E7 | Session blocks | Bare clone cache, machine identity, v2 schema — **DEPRECATED as evidence path in v2.6.0** (transcripts-first replaced session-blocks as evidence; code inert-but-in-tree pending post-2.6 retirement) |
| E8 | Encryption | Envelope encryption for session blocks — **DEPRECATED in v2.6.0** (evidence storage is now filesystem/blob-store at storage-layer encryption boundary, not per-block envelope) |
| E9 | Transcripts-first MVP | v2.6.0 | Migration 009 transcript-custody tables + Migration 010 query views; `POST /api/v1/{commits,transcripts}/ingest` + `GET /api/v1/transcripts/*` endpoints; `gator-enterprise transcripts {pull,list,show,get,link}` CLI; `commits <sha> transcripts` reverse-lookup; `Gator-Machine-Id` commit trailer; multi-vendor session-file v2 schema with PID attribution + PID-recycling protection + `GATOR_TRANSCRIPT_{SESSION_ID,VENDOR}` env overrides; base wheel dispatcher reconciled (`transcripts` + `commits` registered, `CLIENT`/`SERVER_SUBCOMMANDS` rewritten to real verb sets); pre-transcripts-first evidence-in-Git design retired from `_do_repo_init` (`_fix_gitignore` deleted, `.gator/session-blocks/` no longer created) and `POST_COMMIT_HOOK` template (block-generation section removed). Enterprise packaging remains source-checkout-only; single-pipx install path deferred. |

### Building

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **Full session-block code retirement** | Considering | Post-2.6 cleanup. Inert-but-in-tree code paths: `enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py`, `bundled_scripts/gator-session-block.py` + trio-copy, `enterprise/app/services/session_blocks.py`, `enterprise/app/routes/session_blocks.py`, `enterprise/app/routes/crypto.py`, `enterprise/app/models/evidence_block.py`, and the dispatcher's `blocks` verb. Bulk retirement, migration test cleanup. |
| 2 | **Single-pipx install path** | Considering | `pipx install "gator-command[enterprise]"` or `pipx install gator-enterprise-command` so enterprise-cli install stops being source-checkout-only. Blocks a public Enterprise announcement. |
| 3 | **Cross-OS blob store defaults** | Considering | `BLOB_STORE_ROOT` default (`/var/lib/gator-enterprise/blobs`) is POSIX; crashes on Windows without manual override. Needs OS-aware default or containerized reference. |
| 4 | **Fresh-machine bootstrap smoke test** | Considering | Current smoke test assumes venv + Postgres + machine-id pre-exist. A truly-fresh-machine protocol would need to include venv creation + Postgres install + first bootstrap on Windows/macOS/Linux. |

### What Enterprise adds

Enterprise capabilities build on top of the core Gator install — they don't replace anything. The activation surface is `gator enterprise` as a CLI subcommand group:

```
gator enterprise activate     — one-time machine setup (creates ~/.gator/enterprise/, installs global git hooks, registers machine)
gator enterprise sync         — pull hook-policy and org policies from Enterprise
gator enterprise repo init    — provision a repo for Enterprise governance
gator enterprise transcripts  — pull/list/show/get/link session transcripts
gator enterprise commits <sha> transcripts  — reverse-lookup: which transcripts touched this commit
```

This keeps Enterprise as a feature of Gator, not a separate product. Same install, same CLI, same repo. Enterprise adds:

- Session evidence capture and storage
- Fleet-scale audit and reporting
- Centralized policy management
- Git provider integrations (GitHub App, webhooks)
- API-first fleet visibility

---

## Connections

-> [Mission](mission.md) — what we're building and why
-> [Product split](artifacts/2026-06-22-gator-individual-vs-enterprise-product-split.md) — boundary decision
-> [Mission](mission.md) — long-form product framing
-> [Monorepo convergence plan](artifacts/2026-07-16-monorepo-convergence-plan.md) — merge assessment + execution plan
-> [Loop usability plan](artifacts/2026-07-27-loop-usability-implementation-plan.md) — wait, artifacts, dashboard visibility
-> [Architect authority plan](artifacts/2026-07-26-architect-loop-authority-plan.md) — pause, interject, end
-> [`.includes/` migration sketch](artifacts/2026-07-27-gator-content-vs-includes-migration-implementation-sketch.md) — v2 layout design
