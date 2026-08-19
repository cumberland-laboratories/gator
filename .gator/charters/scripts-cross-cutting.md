# Charter: Scripts Cross-Cutting Patterns

This charter documents patterns that span multiple script clusters. Read this before any of the module-specific charters. These are the invariants that break silently if violated.

## Owns

Patterns that cross module boundaries:
- The `resolve_charter_surface()` canonical resolver for charter directory, cross-cutting filename, and INDEX
- The `gator_core` import convention used by all scripts
- The `git()` return contract
- The local → remote fallback pattern (and parallel local/remote scan schemas)
- The `SKIP_FILES` set used consistently across fleet, lint, and intel scripts
- The `ensure_utf8_stdout()` call pattern
- The `import_sibling()` dynamic load pattern and graceful degradation convention
- The plan/execute separation in gator-update
- The `parse_committed_summary()` canonical parser shared across 4+ consumers
- The `source_kind` provenance vocabulary ("command-post", "local-repo", "remote-cache")
- The `X-Gator-Dashboard` header anti-CSRF trust boundary
- The `find_command_post()` + `parse_registry()` registry resolution pattern
- The `"schema"` field convention in all CLI JSON output
- The policy sync graceful import pattern (fleet-report, drift importing policy-status optionally)
- The managed Git hook path migration pattern (Windows `.git/gator-hooks` + `core.hooksPath`, legacy `.git/hooks` fallback)

## Does Not Own

Any single module's implementation — see the module-specific charters for those.

---

## TRIPWIRE: Charter Surface Resolution

`gator_core.resolve_charter_surface(repo_root)` is the single source of truth for which charter directory, cross-cutting charter filename, and INDEX file govern a repo. It returns a dict with `mode`, `charter_dir`, `cross_cutting`, and `index_file`.

Three consumers must use this resolver (or its output) consistently:
1. `precommit_charter.py` — `_resolve_charter_surface()` tries `gator_core` first, falls back to inline heuristic. Used by `gator-pre-commit.py` via import.
2. `enforcer-review.py` — `_resolve_charter_surface()` same pattern
3. The template copy (`src/gator_command/templates/gator-starter/scripts/precommit_charter.py`) — must stay identical to the `.gator/scripts/` version (see Product Boundary below)

Two modes exist, no others:
- **source-command-post**: `.gator/charters/`, cross-cutting is `scripts-cross-cutting.md`
- **governed-repo**: `.gator/charters/`, cross-cutting is `cross-cutting.md`

Do NOT add mode detection via string heuristics in individual tools. Use the resolver. Do NOT hardcode charter filenames — the cross-cutting charter is found by pattern (`"cross-cutting" in filename`).

**Product Boundary: Individual template vs Enterprise live copy.** The template is the **Gator Individual** version — it contains validation, trailers, and basic cleanup (draft reset, whiteboard reset, status.json). The live `.gator/scripts/gator-pre-commit.py` is the **Enterprise** version — it adds snippet emission, session ledger, and vendor session reading on top of the shared Individual base.

**Module structure (since split):** The pre-commit hook is now four files in both locations:
- `gator-pre-commit.py` — orchestrator: git helpers, state readers, classification, override, validation rules, trailers, status, output, phase dispatch
- `precommit_lint.py` — security lint engine: LINT_RULES, diff parsing, context-aware severity, run_layer1_lint
- `precommit_charter.py` — charter discovery and validation: surface resolution, iteration, counting, tripwires, INDEX parsing, function ref checks
- `precommit_session.py` — session audit trail: ledger parsing, commit entry building, block rendering, reassembly, commit summary writing

All four files MUST remain identical between `.gator/scripts/` and `templates/gator-starter/scripts/`. The Enterprise copy adds enterprise-only functions to `gator-pre-commit.py`: `_find_active_session()`, `_read_vendor_session()`, `render_snippet()`, `render_snippet_json()`, `record_commit_and_emit_snippet()`, plus the `record_commit_and_emit_snippet()` call in `phase_cleanup()`. The three submodules have no enterprise-only additions.

After editing shared logic, update BOTH locations (all four files). After editing enterprise-only logic, update only the live `.gator/scripts/gator-pre-commit.py`.

Both copies share the commit-message-from-draft behavior: when `commit_draft.md` has a populated `message` field or non-stub body lines, `phase_trailers` replaces the entire commit message with content assembled from the draft. Both `validate_hard_rules` and `phase_trailers` strip only the exact stub heading `# Session Change Log` — all other `#`-prefixed lines are preserved as real content. These changes must remain synchronized across both copies.

## TRIPWIRE: gator_core Import Convention

Every script that needs shared utilities adds its own scripts directory to `sys.path` and imports from `gator_core`:

```python
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from gator_core import get_version, find_command_post, ...
```

Some scripts omit the `sys.path` insert because they rely on the caller having set it (e.g., when loaded via `import_sibling()`). Standalone scripts must always insert their own scripts directory. Library modules (gator_core.py, gator_remote.py, gator_session_reader.py) do not insert sys.path — they are loaded by their callers.

## TRIPWIRE: git() Return Contract

`gator_core.git()` returns `(stdout: str, success: bool)`. It never raises. Subprocess call uses `encoding="utf-8", errors="replace"` — bare `text=True` on Windows decodes with cp1252 and crashes with `UnicodeDecodeError` on any non-cp1252 bytes in git output (see `scripts-core-library.md` for the v2.4.4 fix details). The dashboard's `_git_run()` follows the same pattern but returns `(stderr, False)` on failure so git error messages are visible to the user. Dashboard `pull_updates()` also runs `git merge --abort` on failed pull to avoid leaving the repo in a conflicted state. The tuple is the full contract:

```python
out, ok = git("log", "-1", "--format=%h", cwd=repo_path)
if not ok:
    return {"error": "git log failed"}
if not out:
    return None  # git succeeded but returned nothing
```

Callers that check only `ok` and not `out` will silently treat "git returned empty string" as a successful non-result. Both must be checked. Fleet-report, drift, and fleet-intel all follow this pattern — preserve it in any new git consumers.

## TRIPWIRE: Local → Remote Fallback Pattern

Both `gator-fleet-report.scan_repo()` and `gator-drift.check_repo_drift()` implement the same three-tier fallback:

1. Local path accessible → full local scan
2. Local path inaccessible AND remote URL available → thin-fetch via `gator_remote`
3. Neither accessible → report as unreachable

This pattern must be preserved together. Changing the fallback logic in one script without the other creates an inconsistency between fleet-report and drift findings for the same repo.

## TRIPWIRE: SKIP_FILES Consistency

The set `{"_template.md", "README.md", "INDEX.md"}` (plus sometimes `.gitkeep`) is used to exclude scaffolding files from counts and analysis in:
- `gator-fleet-report.read_gator_state()` — charter count
- `gator-drift.check_repo_drift()` — charter count
- `gator_remote.read_gator_state_remote()` — charter count
- `gator-fleet-intel.read_charter_names()` — charter name list
- `gator-charter-lint.find_charter_dirs()` / `collect_files()` — lint targets

All must use the same skip set. A discrepancy between fleet-report's charter count and fleet-intel's charter list creates misleading governance telemetry.

## Dashboard POST Endpoints Require X-Gator-Dashboard Header

All dashboard POST endpoints (config, topology, update, gatorize, fetch, pull, restart) require the `X-Gator-Dashboard: 1` header for CSRF protection. The `GET /api/repos/discover` endpoint (Add Repository modal's auto-discovery) uses `resolve_discovery_roots()` from `dashboard/data.py` — respects the `GATOR_DASHBOARD_DISCOVERY_ROOTS` env var override, falls back to a fixed home-relative set (`~/code`, `~/code2`, `~/projects`, `~/repos`, `~/src`, `~/dev`) when unset. See `scripts-dashboard.md` for the full override contract. The update endpoint calls `gator-update.py --path <repo>` — operates on the current branch in place, honors the `.pre-gator-update` backup pattern for entry-point files. The gatorize endpoint (Stage 3 fold-in of the retire-gator-install plan, 2026-07-30) calls `gatorize --yes <repo>` — the install path for ungoverned repos, wired to the Fleet-row "Gatorize" button in fleet.js (`bindGatorizeButtons()` handler, `gatorize-btn` class). Historical behavior of the /update endpoint invoking `gatorize.py` was retired in v2.4.0 (see plan `2026-07-30-retire-gator-install-branch-implementation-plan.md`) because it silently switched branches on Dashboard-triggered updates. Standalone data payload includes `gator_cli_version` for frontend version comparison. Fleet activity indicator uses CSS `dot-pulse` animation (fixed-width, no layout shift). Config POST updates cached `fast_data` in-place for immediate page-refresh consistency. Updates view uses PyPI JSON API for version check and `pipx upgrade` for installation. All version resolution consolidated into `gator_core.get_version()`. Upgrade flow uses detached subprocess (`CREATE_NO_WINDOW`) to release file locks before `pipx upgrade`, relaunches via `gator` CLI entry point. Frontend JS includes this on every POST call. The restart endpoint (`POST /api/restart`) uses `os.execv()` to replace the server process — the response is sent before the process dies, and the frontend polls until the new server responds. `handle_one_request()` suppresses `ConnectionAbortedError` during restart to avoid log noise. `_git_run()` uses `encoding="utf-8"` (not `text=True`) — same fix as gator-deploy.py for Windows cp1252 compatibility. Session snippets are now JSON v2 (`.json` extension, `gator-session-snippet-v2` schema) — immutable once committed. `gatorize.py` ensures standard gitignore rules (vault, .vscode, __pycache__), tracks `origin/dev` when creating the dev branch, and writes `cli-version` to `.gator-version` (resolved from `gator_core.get_version()`) so the dashboard Fleet view can display what CLI version gatorized each repo.

## TRIPWIRE: change-type + significance Enum Sync (pre-commit ↔ snippet schema)

`gator-pre-commit.py::validate_hard_rules` rejects any `change-type` value in `.gator/commit_draft.md` that is not in the `VALID_CHANGE_TYPES` frozenset (`feature | fix | refactor | docs | test | release | maintenance | review | governance | ""`). That set MUST stay byte-consistent with `properties.change_type.enum` in `contracts/schemas/gator-session-snippet-v2.json` — both are read by the same schema validator (`contracts/compatibility/test_snippet_schema.py::test_live_repo_snippets_conform`). Drift means a bad value passes pre-commit but fails CI on the emitted session snippet — the exact regression this validation exists to prevent. Regression pin: `tests/test_precommit_validation.py::TestSchemaEnumSyncObligation::test_enum_matches_schema` reads both surfaces and asserts equality. If either changes, change both in the same commit. Added 2026-08-02 after the monorepo cutover committed several snippets with `change-type: bugfix` — plausible-sounding, not in the enum, blocked CI. The template + `.gator/.includes/scripts/gator-pre-commit.py` must also stay byte-consistent per the module-structure invariant above.

**Added 2026-08-10 (v2.6.0)**: identical sync obligation for `significance`. `VALID_SIGNIFICANCE` frozenset (`low | minor | routine | notable | high | critical | architectural | ""`) mirrors `properties.significance.enum` in the same schema. `architectural` was added to the enum in v2.6.0 to formalize a value that had been in de facto use for cross-module invariant changes; the gate itself prevents future drift. Regression pin: `tests/test_precommit_validation.py::TestSchemaEnumSyncObligation::test_significance_enum_matches_schema` plus 11 test methods in `TestSignificanceValidation`. Trigger: the Phase 4 (3.0 stabilization) smoke-test run surfaced 5 pre-existing snippets with `significance: medium` (typo for `notable`) and 8 with `architectural`; contracts test caught them at release-time regression check.

**Enterprise-cli bundled `gator-pre-commit.py` — pre-existing divergence**: `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/gator-pre-commit.py` (~1515 lines vs the shipped copy's ~1507) does NOT have EITHER the change-type or the significance gate. Per MVP plan §D2 the byte-identity contract was explicitly relaxed for `gator-pre-commit.py`. Syncing the bundled copy is post-3.0 cleanup (§4 P3.2 in the stabilization plan) — new enterprise-provisioned repos ship with an older gate-less pre-commit until then.

## Shared Snippet Infrastructure (Phase 4a — 2026-08-01)

`precommit_session.py` (in both `.gator/scripts/` and the shipped template at `src/gator_command/templates/gator-starter/scripts/`) exposes the canonical snippet-emission surface: `record_commit_and_emit_snippet(gator_dir, status, git_fn=None)` is the orchestrator; `render_snippet_json(entry, session_meta, vendor_session=None)` renders the JSON; `_read_active_vendor_session(gator_dir)` and `_read_vendor_session(gator_dir)` enrich snippets with vendor session identity when `.gator/active-vendor-session.json` is present; `_atomic_write(target_path, content, parent_dir)` handles the temp-file-and-rename write. `build_commit_entry` gains a `git_fn=None` parameter — the single surgical injection point for mock testability. Per the ratified Decision B of the monorepo plan, this is **shared Desktop infrastructure**, not Enterprise-gated — every governed repo emits snippets to `.gator/session-snippets/*.json` on commit, regardless of Enterprise configuration. Gator-Enterprise integration (session block emission, ledger writes gated behind `.gator/enterprise.json`) belongs to Phase 4b and is a separate concern from this shared layer. `gator-pre-commit.py::phase_cleanup` calls `record_commit_and_emit_snippet` inside a guarded `try/except` — snippet-emission failure MUST NEVER block a successful commit, and MUST NEVER corrupt the session ledger (tested by `test_snippet_failure_preserves_ledger`). Contract-side validation lives in `contracts/schemas/gator-session-snippet-v2.json` (the required-fields + enum contract for every emitted snippet). `render_snippet_json`'s `started_at` field uses a three-tier fallback — `vendor_session["started_at"] → session_meta["started-at"] → now` — so non-vendor sessions preserve the schema's "when the session group began" semantics via the ledger-frontmatter's session-start rather than resetting per-commit (Codex Phase 4a review fix). Live snippets in `.gator/session-snippets/*.json` are exercised by `contracts/compatibility/test_snippet_schema.py::test_live_repo_snippets_conform` with a filename-date grandfather cutoff of 2026-07-01. The port from `enterprise-mvp` explicitly did NOT bring over that branch's `phase_validate` simplification (which removed v1.9.3's hook-warning-mode print block) — "main wins" per the plan's Phase 4 conflict rule. Phase 4b-substrate (2026-08-01) adds the canonical Enterprise-marker reader `gator_core.is_enterprise_active(gator_dir)` — fail-closed against missing/malformed/`enabled != true` markers; every Phase 4 Enterprise gating call site MUST use this helper rather than re-implement the check (`scripts-core-library.md` + `contracts.md` codify the invariant; `TestIsEnterpriseActive` pins semantics). Per amended Decision B, the base-Gator snippet-emission call in `phase_cleanup` does NOT consult the marker — base behavior is unconditional, the marker gates only the additive Enterprise layer landing in 4c/4d.

## `Gator-Machine-Id` trailer (Phase 6 — 2026-08-08 transcripts-first MVP)

`gator-pre-commit.py::assemble_trailers` emits `Gator-Machine-Id: <id>` sourced from `~/.gator/machine-id`'s `id:` line (via `precommit_session.py::_read_machine_id`). Silent no-op when the file is absent — standalone base-gator use on a machine that never activated Enterprise (or that predates the file) still commits successfully; the trailer just doesn't get added. Enterprise-side consumer: `enterprise/app/routes/ingest.py::ingest_commits` reads the trailer bag to populate `commits.machine_id`, which the linkage algorithm's `strong_machine_repo_time` basis (Phase 3) matches against `transcript_sessions.machine_id`. Snippet schema already carries `machine_id` per Phase 0 inventory — no schema change needed. Trio-copy contract note: the Phase 6 edit was applied to all three copies of `gator-pre-commit.py` (`.gator/.includes/scripts/`, `src/gator_command/templates/gator-starter/scripts/`, `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/`) at the same anchor. Byte-identity across the trio was NOT extended to `gator-pre-commit.py` — those three copies pre-drifted for reasons unrelated to Phase 6 (line counts 1480/1465/1500 as of 2026-08-08), and full byte-identity would fail on pre-existing differences. Reconciling that trio drift is a follow-up cleanup, not Phase 6 scope. Regression pins: `tests/test_precommit_validation.py::TestMachineIdTrailer` (3 tests — emitted-when-present, omitted-when-file-missing, omitted-when-id-line-missing; uses `Path.home` monkeypatch for hermeticity).

## TRIPWIRE: Multi-Session Vendor Attribution (v2 schema)

**Filename stays `.gator/active-vendor-session.json` (singular) but CONTENT is a container of sessions, not a single entry.** Since 2026-08-07 (Issue B of the 2026-08-06 Enterprise Local Bring-Up), `precommit_session.py` reads and `gator-session-start.py` writes a v2 schema — `{"schema": "gator-active-vendor-sessions-v2", "sessions": [...]}` — that lets multiple vendor CLIs (Codex + Opus + Gemini, etc.) coexist in the same repo without overwriting each other's identity. The filename stays singular for backwards compat with `gator_layout.py`'s file registry and gitignore templates.

**Attribution priority in `_pick_session_for_commit`** (highest first):
1. `GATOR_TRANSCRIPT_SESSION_ID` env var — orchestrators, cross-repo commits, test harnesses can set this to override inference. If the env id isn't in the file's session list, a minimal synthesized entry with `source: "env-override"` is returned so callers can still emit the id.
2. PID tree walk match — if the git hook's ancestor process PIDs (bounded depth 10) include a session's `owner_pid`, hard match. Only walked when 2+ entries; short-circuits below.
3. Single entry — after freshness cleanup, if only one session in the file, use it (no PID walk needed — common case).
4. Transcript mtime fallback — pick the session whose `transcript_path` was most recently modified.
5. None — snippet's `transcript_session_id` stays null; Finding #4 diagnostic log at `~/.gator/diagnostics/block-gen.log` captures the fall-through.

**Cross-platform PID walking** via subprocess: PowerShell `Get-CimInstance Win32_Process` on Windows (~150ms/hop, slow but correct), `ps -o ppid=` on Unix. `_walk_parent_pids(start_pid=None, max_depth=10)` bounds the walk. `owner_pid_started_at` timestamp (captured at SessionStart) protects against PID recycling — a later process reusing the same PID number won't match if its start time differs.

**Backwards compat**: readers accept BOTH `gator-active-vendor-session-v1` (legacy single-entry, wrapped as list-of-one) and the new `-sessions-v2` (multi-entry container). Writers always emit v2 — v1 files auto-migrate to v2 on the next SessionStart write. No migration script needed; the file self-heals in place.

**Cleanup semantics**: on both read and write, drop entries where `started_at > 24h ago` (`_AVS_MAX_AGE_SECONDS = 86400`). Entries without a parseable `started_at` are preserved (defensive — better to keep a maybe-stale entry than silently drop a valid one). CWD filter (entry's `cwd` field must match this repo) applies on read only — file itself is shared across all sessions on the machine that happen to have the same repo mounted.

**Sync obligation — THREE-WAY (was originally documented as two-way; Codex Finding #1 from 2026-08-07 review surfaced the missing third)**: `precommit_session.py` and `gator-session-start.py` exist in THREE locations that MUST stay byte-identical:

1. `.gator/.includes/scripts/` — SHIPPED for v2-layout repos gatorized with `gator gatorize`.
2. `src/gator_command/templates/gator-starter/scripts/` — TEMPLATE, copied INTO new repos by `gatorize`'s `_install_scripts` step.
3. `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/` — copied INTO new repos by `gator-enterprise repo init`'s `_install_bundled_scripts` step (`enterprise/enterprise-cli/gator_enterprise_cli/commands/repo_init.py:135-145`).

Missing any one of these means one class of provisioning gets stale code. Codex Finding #1 caught exactly this: the multi-session commit updated 1+2 but not 3, so freshly `gator-enterprise repo init`'d repos still ran the old v1-only path. Every future edit to either file MUST land in all three.

**PID recycling protection**: `_walk_parent_pids()` returns `[(pid, started_at_or_none), ...]` tuples. `_pick_session_for_commit()` matches BOTH the ancestor PID number AND the session's `owner_pid_started_at` (via `_pid_start_times_match` — fuzzy string compare with graceful degradation when either side is None). Windows especially recycles PIDs aggressively; a session that recorded `owner_pid=1234` at SessionStart shouldn't match a different process that happens to have PID 1234 now. Codex Finding #2 caught the earlier code where the writer captured `owner_pid_started_at` but the reader ignored it.

**Cross-repo vendor identity (GATOR_TRANSCRIPT_VENDOR companion env var)**: `GATOR_TRANSCRIPT_SESSION_ID` names the session; `GATOR_TRANSCRIPT_VENDOR` names its vendor. When only the ID is set, the synthesized entry has `vendor: None` (not `"unknown"`) — `render_snippet_json` then preserves the agent-inferred vendor rather than clobbering with `unknown`. `session_group_key` fallback: explicit `vendor_session["vendor"]` → agent-inferred `vendor_inferred` → `"unknown"` (last resort). Codex Finding #3 caught the earlier code where synthesized `vendor: "unknown"` was authoritative in `render_snippet_json`, producing `vendor_inferred: unknown` and `session_group_key: unknown:<id>` exactly in the cross-repo case the env override was designed to enable.

**Regression pins**: `tests/test_multi_session.py` (now 34 tests) — reader v1+v2, cwd filter, freshness filter, corrupt/missing/unknown-schema resilience; picker env var / PID / single / mtime / none, PID+started_at recycling detection (Finding #2), env-var vendor override (Finding #3); PID walker returns tuples (bounded + cross-platform + started-at match helper); writer fresh + preserve + upsert + v1→v2 migration + stale-drop; render_snippet_json vendor fallback (Finding #3); byte-identity across all three copies (Finding #1 regression pin — `TestByteIdentityAcrossThreeCopies`).

**Known issue (v2.6.0)**: `test_v1_file_returns_single_entry_list` and `test_v1_file_migrates_to_v2_on_write` are `@pytest.mark.xfail(strict=False)` as of 2026-08-10 — v1 backwards-compat is NOT implemented in the current v2 reader/writer, so v1 legacy entries silently drop rather than being preserved on migration. Post-2.6 work will either implement the v1 read-shim (preserving legacy entries) or delete the tests entirely if v1 is truly out of support under the transcripts-first + Enterprise-owned-session-capture end-state. See CHANGELOG `[2.6.0] Known issues`.

**Blast radius**: base gator code, ships in every gatorized repo AND every Enterprise-provisioned repo. Attribution accuracy changes for every governed commit. Old repos with v1 files continue working on read; get upgraded to v2 on the next SessionStart write.

## License Posture and Contribution Policy

The project ships under **Apache License 2.0** (`LICENSE` at repo root, canonical text). `NOTICE` at repo root carries the copyright + license grant and is bundled into the wheel automatically at `dist-info/licenses/NOTICE` via setuptools' `License-File` convention (both LICENSE and NOTICE appear as `License-File:` lines in wheel METADATA). `pyproject.toml` declares `license = {text = "Apache-2.0"}` and `License :: OSI Approved :: Apache Software License` in classifiers — both surfaces kept in sync per PEP 639 while retaining the classifier for older tooling. Phase 3c (2026-08-01) flipped the source repo from MIT to Apache 2.0 per the ratified plan; the flip covers packaging-visible surfaces (LICENSE, NOTICE, pyproject, README, PYPI_README, docs/how-gator-works.md) and contributor-facing surfaces (CONTRIBUTING.md with DCO sign-off requirement, SPDX source-header recommendation for new files). Historical artifacts under `.gator/artifacts/` and vestigial `.gator/charters/` are preserved as historical record — the Track F sweep from the mechanical checklist deliberately leaves those in place. Contributor obligations: **DCO sign-off required** on every commit (`git commit -s`) — no separate CLA. New source files SHOULD carry an SPDX identifier line where practical (`# SPDX-License-Identifier: Apache-2.0`); a full Apache header on every file is not required (Track D deferred, checklist recommendation). Any existing MIT installs from prior PyPI releases keep MIT terms — the flip is not retroactive. The current public MIT repo remains on MIT until the public monorepo bootstrap (Phase 3b-3 / GitHub Option B cutover); Phase 3c prepares the source posture so the new public tree starts life already Apache.

## Package CLI Entry Point

`src/gator_command/cli.py` is the thin CLI dispatcher installed by `pip install gator-command`. Scripts and templates are now canonical at `src/gator_command/scripts/` and `src/gator_command/templates/` — no junctions, no copies. The CLI resolves scripts in priority order: package-bundled (`cli_dir/scripts/`), source-checkout (`src/gator_command/scripts/`), public-clone (`gator-engine/scripts/`). `pyproject.toml` declares package-data globs for scripts and templates. `gator_runtime.py` provides the resolver layer for runtime mode detection. v1.1.0 adds `gator gatorize` and `gator update` to the CLI dispatch. v2.0.0 adds `gator loop` — a multi-file package (`scripts/loop/`) dispatched via the same subprocess model through `gator-loop.py`. Loop modules use `sys.path`-based imports (not relative imports) because `scripts/` is package data, not an importable sub-package. All loop `.py` files are listed individually in `pyproject.toml` package-data. v2.2.3 adds `gator state` — a two-subcommand orchestrator (`status`, `repair`) for the managed-state layer covering entry-point files and constitution drift; dispatched through `gator-state.py` and covered by `scripts-managed-state.md`. v2.4.3 adds `gator kill` — a nested-subverb orchestrator (currently `dashboard [--all | --port N | --dry-run]`) for killing stale Gator processes; dispatched through `gator-kill.py` and covered by `scripts-dashboard.md`. Phase 3a (post-v2.4.5) adds `gator enterprise` — a subcommand-group stub with ten subcommands split client-side (setup/status/sync/audit/disconnect, base install) and server-side (server/db/policy/org/fleet, requires the new `[enterprise-server]` optional-dependencies extra with fastapi/sqlalchemy/alembic/uvicorn/psycopg); dispatched through `gator-enterprise.py` and covered by `scripts-enterprise.md`. Strict `parse_args` at the top level: unknown flags on a stub subcommand fail visibly (argparse exit 2), same as every other `gator <verb>`. Every stub body — mutating and read-only — exits 69 (EX_UNAVAILABLE) with a `[gator-enterprise-stub]` sentinel on the first stdout line, so shell chains like `gator enterprise setup && do_next_thing` short-circuit instead of proceeding on a fake success. An earlier Phase 3a draft returned 0 and used `parse_known_args` for passthrough leniency; both were reversed after Codex flagged them as traps for automation and typos respectively. The nested `gator kill <target>` shape is deliberate — leaves room for `gator kill loop`, `gator kill enforcer`, etc. without CLI restructure. Selector-semantics rules (`--all` and `--port` mutually exclusive at the argparse layer; `--dry-run` requires a selector; `--port` must be inside the dashboard port range) are enforced BEFORE any process discovery runs — see `scripts-dashboard.md` for the full contract and the `TestSelectorSemanticsAtCliBoundary` regression suite. Standalone dashboard mode uses `~/.gator/dashboard-repos.json` instead of command-post registry. Versioning: patch bumps for incremental releases, minor bumps at Architect-decided milestones. `pyproject.toml` readme points to `PYPI_README.md` (user-facing, no command-post references) not `README.md` (developer-facing). `_restart_server()` adds `--no-open` to avoid duplicate browser tabs on restart. v1.1.3. `tests/test_packaging.py` verifies CLI dispatch, script resolution, wheel contents (scripts, dashboard, templates), and end-to-end installed-artifact behavior (builds wheel, creates temp venv, installs, verifies `gator.exe` entry point exists, runs `gator -V`, `gator --help`, and `gator version` subcommand dispatch via the real console-script entry point). `test_version_flag` compares the CLI output against `gator_command.__version__` (imported live) rather than a hardcoded string — the assertion survives every version bump. Prior form hardcoded `"1."` and broke silently on the v2.0.0 bump; the fix restores the packaging suite's signal.

## TRIPWIRE: ensure_utf8_stdout() Call Pattern

Every CLI entry-point script calls `ensure_utf8_stdout()` at the top of `main()` before any `print()`. This is required on Windows where the default encoding is not UTF-8 and causes UnicodeEncodeError for the ASCII art and emoji characters in the boot display.

Library modules (gator_core.py, gator_remote.py, gator_session_reader.py) must not call this — they are imported by scripts that have already set up stdout.

## Pattern: import_sibling() for Runtime Module Loading

`gator-audit.py` loads peer scripts at runtime using `gator_core.import_sibling()` rather than static imports:

```python
fleet_mod = _import_script("gator-fleet-report")
if fleet_mod:
    reports = fleet_mod.scan_fleet(repos)
```

This pattern:
1. Prevents a broken fleet-report from killing the entire audit
2. Avoids circular import issues between scripts in the same directory
3. Handles hyphenated filenames that Python's import machinery can't handle natively

Each subsystem import is guarded with try/except ImportError. Do not convert these to static imports — the graceful degradation is intentional.

## Pattern: Plan/Execute Separation (gator-update)

`gator-update.plan_updates()` is read-only: it compares files, builds a diff list, and returns a plan without touching the filesystem. `gator-update.execute_updates()` performs the writes.

This separation enables accurate dry-run (`--dry-run` shows exact changes without side effects) and JSON output (`--json` emits the plan without executing). Any new update logic must maintain this boundary — if it creates directories, it belongs in `execute_updates()`.

## TRIPWIRE: Managed Hook Path Migration

Gator now has one authoritative managed hook strategy:

- Windows: install active hooks in `.git/gator-hooks`, set `core.hooksPath=.git/gator-hooks`, use a direct `#!C:/Windows/py.exe -3` shebang
- Unix-like: install active hooks in the default `.git/hooks`

Three clusters must stay aligned:
1. `gator-update.py` — defines the managed path helpers and performs install/repair
2. `gatorize.py` / boot self-heal — delegate to the same installer rather than writing hooks independently
3. Fleet readers (`gator-fleet-report.py`, `gator-drift.py`, `gator-repo-status.py`) — probe the managed path set and tolerate legacy `.git/hooks`

If one of these changes without the others, the likely failures are:
- `git commit` still launching through Git-for-Windows `env.exe`
- fleet/drift false negatives or false positives on Windows repos
- dry-run/update output pointing at the wrong destination

## Pattern: Snippet Fingerprint (session-aggregator)

`snippet_fingerprint()` in `gator-session-aggregator.py` hashes the full raw bytes of each snippet file (SHA-256 per file, sorted alphabetically, combined SHA-256, prefixed `sha256:`). This is the cache invalidation key for session summaries at `~/.gator/sessions/<path-hash>/`. Any byte change in any snippet invalidates the cached summary. The fingerprint is order-independent — same set of files always produces the same result regardless of discovery order.

! `session_cache_key()` uses `sha256(resolved_repo_path)[:12]` as the directory name. This is distinct from the snippet fingerprint — the cache key identifies the repo, the fingerprint validates the content.
! `_atomic_write()` uses fd_closed flag to track file descriptor state — do not call os.get_inheritable() or os.close() on an already-closed fd in the error path.
! Cache filenames use `sha256(effective_session_key)[:16].json`. The `effective_session_key()` helper returns `"group:<repo>:<session_group_key>"` when vendor session identity is present, `"legacy:<repo>:<session_id>"` otherwise. This is the single canonical grouping key used for aggregation, cache filenames, and fingerprint lookups. Aggregation, cache, and fingerprint code must all use this helper — never ad hoc `(repo, session_id)` tuples.

## TRIPWIRE: parse_committed_summary() Canonical Parser

`gator_session_reader.parse_committed_summary(text, filename)` is the sole parser for committed session summary markdown. Post-Phase-3 (2026-08-13) it has exactly one owner and two consumers.

**Owner:**
- `gator_session_reader.py` — defines it, uses it in `read_committed_summaries()`.

**Consumers via `import_sibling()`:**
- `gator-audit.py` — fleet-wide decision extraction + session_summaries (via `_committed_decisions_from_snippets()`).
- `gator-repo-status.py` — per-repo recent sessions display (via `get_session_summaries()`).

The parser handles two schema types: `gator-session-summary-v1` (legacy archaeology format, still readable) and `gator-commit-summary-v1` (from pre-commit hook). Returns dict with: date, repo, vendor, agent, goal, decisions, source_file, start. Returns None for unparseable files.

Any change to frontmatter field names, section headers (`## Goal`, `## Decisions`), or the return dict shape breaks the consumers. Adding new return fields is safe; removing or renaming existing ones is not.

*(Prior state: `gator-sessions.py` was the definer, with `gator-session-sink.py` as a fourth consumer via `import_sibling`. Phase 2A extracted the parser into `gator_session_reader.py`; Phase 3 Commit E retired `gator-sessions.py` and `gator-session-sink.py`, collapsing back to one owner.)*

## TRIPWIRE: source_kind Provenance Vocabulary

Session summaries carry a `source_kind` field with exactly three valid values:

- `"command-post"` — read from the command post's `.gator/sessions/`
- `"local-repo"` — read from a local fleet repo's `.gator/sessions/`
- `"remote-cache"` — read from a remote bare cache via `gator_remote`

Used by:
- `gator-audit.py` — tags each summary at collection time
- `gator-repo-status.py` — always tags as `"local-repo"`
- `gator-dashboard.py` — `_find_session_content()` dispatches file resolution by `source_kind`
- Dashboard JS (audit.js, repo.js) — passes `source_kind` to the drill-down modal

A misspelling or new value that the dashboard doesn't handle breaks the evidence drill-down with a 400 error.

## TRIPWIRE: X-Gator-Dashboard Header (Anti-CSRF Trust Boundary)

All POST endpoints in `gator-dashboard.py` require the custom header `X-Gator-Dashboard: 1`. The server validates this in `_check_post_auth()` before processing any POST.

This is the security boundary. Browsers cannot send custom headers on simple form POSTs, `<img>` embeds, or navigations. A cross-origin `fetch()` with custom headers triggers a CORS preflight OPTIONS request, which this server does not answer — blocking the request.

Rules:
- Every new POST endpoint must call `_check_post_auth()` first
- Every new JS `fetch()` to a POST endpoint must include `headers: { "X-Gator-Dashboard": "1" }`
- Do NOT weaken this to Origin-only checking — Origin can be absent on some browser form POSTs
- Do NOT add CORS headers to the server — no cross-origin access is intentional

## Pattern: Two-Channel Update Architecture

`gator-update.py` separates product updates from org-policy sync:

- **Channel 1** (all repos): template overlay from gator clone via `product-source.json`. Uses `resolve_template_source()` from `gator_core.py`.
- **Channel 2** (policy-synced repos only): org-policy sync via thin link. Skipped gracefully for standalone repos.

**TRIPWIRE: product-source.json self-heal.** `gator-update.py:main()` self-heals a stale `product-source.json` (where `gator_root` points at a nonexistent path — common failure mode when the fleet-repo captured an absolute pipx venv path and pipx later rebuilt the venv or was reinstalled editable). On resolution failure the caller falls back to `Path(__file__).resolve().parent.parent` — the running install's own root, which by definition contains valid templates for the pipx and source-checkout cases. On successful fallback: prints a "Self-healing" warning, rewrites `product-source.json` so future runs don't need to self-heal, continues the update. If the fallback root has no `templates/gator-starter/` either (fleet-repo direct invocation of the template mirror at `.gator/scripts/gator-update.py`), the original "run --source" error surfaces unchanged. Self-heal is package-and-template-mirror sync-obligation-bound: any change to the fallback logic must land in BOTH `src/gator_command/scripts/gator-update.py` AND `src/gator_command/templates/gator-starter/scripts/gator-update.py`. Shipped in v2.4.1 (2026-07-30) — Stage 1 of v2.4.0 exposed the latent bug fleet-wide by swapping the Dashboard Update endpoint to `gator-update`.

`product-source.json` is gitignored machine-local state. `--source` CLI arg rebinds it. Topology (`get_repo_topology()`) determines whether channel 2 runs. Three-state model: policy-synced (active thin link), standalone (all policy artifacts absent), inconsistent (partial artifacts remain — needs repair). Registry paths must be normalized via `normalize_path()` before use with `Path.is_dir()` — MSYS-style `/c/` paths fail on Windows otherwise. Dashboard Fleet Update passes `--no-policy` so the action model is: Fleet = template updates, Audit = policy sync (future). Fleet "Check Status" uses dry-run JSON to detect available updates AND `gator-charter-verify --json` for charter health before offering the action. Repo view is a markdown file browser over `.gator/` — `gator-pulse.py` generates the default document (`pulse.md`). File paths in URLs use per-segment encoding (preserve slashes) with server-side `unquote()`. File paths starting with `gator-command/` resolve against the repo root (not `.gator/`). Command post is injected into fleet data via `_inject_command_post()` (survives refresh). Dir values for gator-command/ files stripped of trailing slashes. File view includes git last-modified date. Command post identified by `is_command_post` flag (path-matched). Source file paths use `source/` prefix mapped to repo root. Binary files served via `/api/repo/<name>/raw/<path>` for inline image rendering. Template sync tripwire validated: gator-update.py and gator_core.py drifted (--no-policy, topology, product-source functions missing from templates).

## Pattern: Single Command-Post Detection Predicate

`find_command_post()` in `gator_core.py` is the canonical predicate for detecting whether a command post exists. All consumers must use this single definition. Do not invent alternative detection heuristics.

Consumers: `gator-dashboard.py` (standalone vs command-post startup), `gatorize.py` (has-command-post flag for conditional thin link and entry-point text), `gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`, `gator-repo-status.py`. Historical: the retired bash chain (`gatorize.sh` et al) called this via `python3 -c "from gator_core import find_command_post; ..."` — that shell-bridge pattern went away with the bash chain in v2.4.0.

## TRIPWIRE: find_command_post() + parse_registry() Registry Resolution

All fleet-level scripts bootstrap via a two-step registry lookup from `gator_core`:

1. `find_command_post(start_path)` — walks up directories looking for `.gator/mission.md`
2. `parse_registry(command_post)` — reads `gator-command/registry.md`, returns list of repo entries with `name`, `path`, `remote`, `status`

Used by: `gator-fleet-report.py`, `gator-drift.py`, `gator-audit.py`, `gator-repo-status.py`, `gator-dashboard.py`, `gator-policy-status.py`.

The registry format (markdown table in `registry.md` with pipe-delimited columns) is the contract. Changes to column order, header names, or the path resolution heuristic in `find_command_post()` break every fleet-level script simultaneously.

## Pattern: Machine-Local Dashboard Registry — Single Write Helper

`ensure_dashboard_registry_entry(repo_path, source)` in `gator_core.py` is the canonical write path for the machine-local dashboard registry (`~/.gator/dashboard-repos.json`). All callers — `gator-init.py` (auto-register on session start), `gatorize.py` (via `add_dashboard_repo()`), `gator-dashboard.py` (`--add-repo`) — must go through this helper. It is idempotent by resolved path and returns a structured `{status, detail}` result.

! Do not add repos to the registry by writing the JSON directly. The helper handles path resolution, deduplication, and error isolation.

## TRIPWIRE: Trailer Backward Compatibility (Gator-Architect / Gator-PI)

The commit trailer `Gator-Architect:` (formerly `Gator-PI:`) carries the human role attribution. All code that reads trailers from git history must accept both names:

```python
architect = trailer_dict.get("Gator-Architect", trailer_dict.get("Gator-PI", ""))
```

Old commits have `Gator-PI:` and that history does not change. New commits use `Gator-Architect:`. The frontmatter field in `commit_draft.md` is `architect:` (formerly `pi:`); the hook also accepts `pi:` for backward compatibility.

Consumers: `gator-pre-commit.py` (trailer assembly), `gator-repo-status.py` (trailer reading), dashboard `repo.js` (column display).

## TRIPWIRE: Schema Versioning in CLI JSON Output

All CLI scripts that produce JSON include a top-level `"schema"` field declaring the format version:

- `gator-audit.py` → `"schema": "gator-audit-v1"`
- `gator-repo-status.py` → `"schema": "gator-repo-status-v1"`

*(Historical: `gator-session-common.py` → `"gator-session-summary-v1"` retired with the vendor extractors in the 2026-08-16 sweep; `parse_committed_summary()` still READS that schema from previously committed summaries.)*

Every new CLI script with JSON output must include `"schema": "<name>-v<N>"` at the top level. This enables:
- Downstream consumers to detect incompatible versions
- Dashboard to guard against missing fields introduced in newer versions
- Database schema migrations

## Pattern: Graceful import_sibling() Degradation

Multiple scripts optionally import peer modules for enriched output, with graceful fallback when the module is unavailable:

```python
try:
    _ps = import_sibling("gator-policy-status")
    _compute_sync_state = _ps.compute_sync_state
    _HAS_POLICY = True
except Exception:
    _HAS_POLICY = False
```

Used by:
- `gator-audit.py` — imports fleet-report, drift, gator_session_reader (3 optional modules). Machine identity comes from `gator_session_reader.get_machine_identity()` (folded from session-common in Phase 3F, 2026-08-13; session-common itself retired in the 2026-08-16 sweep).
- `gator-fleet-report.py` — imports policy-status optionally
- `gator-drift.py` — imports policy-status optionally
- `gator-repo-status.py` — imports `gator_session_reader` optionally (Phase 2A, 2026-08-12 — was `gator-sessions` until then; the reader module is the surviving snippet-reader per parent plan)
- `gator-update.py` — imports policy-status optionally
- `gator-init.py` — imports gator-state optionally for the Stage 5 constitution-drift suffix on the boot line; failure yields no suffix, never breaks session opening

The rule: a broken or missing optional module degrades that section's output (empty or `{"error": "..."}`) but never kills the entire script. Each import is independently guarded. Do not consolidate these into a single try/except block.

! `import_sibling()` returns `None` when the file doesn't exist — it does NOT raise. A `try/except` around the import call will not catch this case. Callers must guard against `None` before calling methods on the returned module. Base-wheel package-data currently omits several session-pipeline scripts (`gator-session-aggregator`, `gator_session_reader`, `gator-audit`, `gator-fleet-report`, `gator-drift`, `gator-fleet-intel`, `gator-audit-renderers`) — a pre-existing gap unrelated to the session cleanup (`gator-session-common` was also on this list until its 2026-08-16 retirement removed the question). Under `pipx install gator-command` these scripts return `None` at runtime and their features degrade to empty output; an editable/source-checkout install has them. Adding them to package-data is a separate follow-on task.

## Pattern: Parallel Local/Remote Scan Schemas

Functions that read governance state from local repos have a parallel remote counterpart that must return the same schema:

| Local function | Remote counterpart | Schema must match |
|---|---|---|
| `fleet-report.read_gator_state()` | `gator_remote.read_gator_state_remote()` | charter count, hooks, status fields |
| `fleet-report.scan_repo()` | `gator_remote.scan_repo_remote()` | full repo scan with `scan_mode` field |

Adding a field to the local function without the remote counterpart creates inconsistent data in fleet-report and audit — some repos show the field, others don't, with no indication of why.

## Pattern: Individual/Enterprise Product Boundary

The source tree contains both Individual and Enterprise code in one repo. The product boundary is enforced at build/deploy time, not at runtime:

1. **PyPI wheel**: `pyproject.toml` uses explicit `package-data` file lists. Enterprise scripts are not listed, so they do not enter the wheel. `include-package-data = false` prevents auto-inclusion.
2. **Public git repo**: `gator-deploy.py` uses `ENTERPRISE_ONLY_SCRIPTS`, `ENTERPRISE_ONLY_TESTS`, `ENTERPRISE_ONLY_TEMPLATES`, and `ENTERPRISE_ONLY_TEMPLATE_DIRS` exclude sets.
3. **PyPI release**: `scripts/release-individual.sh` is the canonical release path. Deletes sdist before upload — only wheel ships.

Enterprise scripts remain importable from `scripts/` for development, testing, and command-post dogfooding. They are never shipped to end users via the public package or repo.

**Package-data completeness (roadmap item 12, fixed 2026-08-18).** `pyproject.toml` `[tool.setuptools.package-data]` is an explicit list (`include-package-data = false`) — a top-level script absent from it silently vanishes from pipx installs, `import_sibling()` returns None, and features degrade to empty (dashboard audit view, machine identity, fleet reports). Seven session-pipeline/fleet scripts were missing pre-fix (`gator-audit`, `gator-audit-renderers`, `gator-drift`, `gator-fleet-intel`, `gator-fleet-report`, `gator-session-aggregator`, `gator_session_reader`); three stale entries pruned (`gator-deploy.py`, `gator-init-command-post.py` — both retired; `scripts/legacy/**/*` — dir never existed; setuptools ignores missing patterns silently, which is exactly why the list rotted). ! TRIPWIRE — load-bearing for the runtime split (Variant A): the wheel IS the runtime, so a script missing from package-data is no longer rescued by a repo-resident copy. Self-maintaining guard: `tests/test_packaging.py::test_wheel_ships_every_top_level_script` compares disk → built wheel (not disk → pyproject text), so any future script added without a package-data entry fails CI. Named pins for the seven in `test_wheel_has_session_pipeline_scripts`.

**Package/template sync obligations.** Several files ship in two locations that must stay behaviorally consistent:

- Pre-commit hook trio (`gator-pre-commit.py`, `precommit_lint.py`, `precommit_charter.py`, `precommit_session.py`) — see "Product Boundary: Individual template vs Enterprise live copy" above. Runtime-split Phase 2 (2026-08-18): template `gator-pre-commit.py::main()` gained the flag-gated (`GATOR_RUNTIME_RESOLVER=1`) fail-closed version-negotiation check — validate phase ONLY (refusing mid-commit at trailers/cleanup would strand a half-finished commit); guarded import + broad except so the gate adds no new failure modes; flag-off default = pre-Phase-2 behavior exactly. The Enterprise bundled copy does NOT carry the gate (byte-identity already relaxed per MVP plan §D2; reconcile at item 3 or bundled-scripts retirement).
- `gatorize.py` — **template copy retired in v2.4.0** (retire-gator-install plan Stage 4, 2026-07-30). Only the package copy at `src/gator_command/scripts/gatorize.py` remains; there is no template mirror to sync. Invariant #14 of the local-agent-overrides plan (2026-07-28) is retired with the file. See the "TRIPWIRE: gatorize.py Package/Template Copy Sync — RETIRED" note in `scripts-installer.md` for the fleet-repo `import_sibling("gatorize")` degradation contract.
- `gator_core.py` — runtime-split Phase 1 (2026-08-18): `write_runtime_pin` + `_read_machine_id_value` added to BOTH the package copy and the template copy. The two copies are NOT byte-identical overall (the template variant is deliberately leaner) but these two functions must stay behaviorally consistent — the template copy exists so a repo-resident `gator-update.py` standalone run emits the same pin shape the CLI does. Contract: `contracts/schemas/gator-runtime-pin-v1.json` is the single arbiter of the emitted shape; drift between copies surfaces as a contract-test failure on the live pin, not silently. Phase 2 (same day) added `resolve_governed_runtime` + `_version_tuple` to both copies via block-mirroring, and the BOM-hardening follow-up (`utf-8-sig` pin read) landed in all three locations (wheel, template, this repo's `.includes`) in one commit — the mirror rule for these functions is: edit wheel first, block-mirror to template, let `gator update` carry `.includes`. The 2026-08-19 unreadable-pin degradation fix (whiteboard Findings 1+2 — unparseable-version branch now matches the malformed-JSON branch's repo-scripts-present check) followed the same three-copy rule.
- `gator-update.py` — runtime-split Phase 1 (2026-08-18): both copies gained the identical best-effort `write_runtime_pin` call in `main()` (after the `.gator-version` stamp, before `print_result`); try/except by contract — pin failure never fails an update. Stage 4b added entry-point managed-block refresh (`plan_entry_point_updates`, `execute_entry_point_updates`, `entry_point_actions` in JSON, `"schema": "gator-update-v1"`). The template copy inlines `find_managed_block`, `classify_managed_block`, `detect_legacy_gator_content`, `render_managed_region`, `BlockState`, `ManagedBlockLocation`, and the sentinel/fingerprint constants so it runs standalone without the `gatorize/` sub-package. `render_entry_content` and `upgrade_legacy_entry_point` are guarded imports — when unavailable (fleet-repo template copy invoked directly), `_ENTRY_POINT_REFRESH_AVAILABLE = False` and `plan_entry_point_updates()` returns an empty list. Enforced by `tests/test_template_sync.py`: behavioral parity for the update pipeline, JSON-schema parity (`"schema": "gator-update-v1"` + `entry_point_actions`), and AST-equivalence for the three inlined helper functions (`ast.dump` of their bodies must match the canonical `gatorize/managed_block.py`).

## Connections

-> [scripts-core-library](scripts-core-library.md) — gator_core, gator_remote, normalize_path
-> [scripts-fleet-intelligence](scripts-fleet-intelligence.md) — local/remote fallback, import_sibling consumers, registry resolution
-> [scripts-session-archaeology](scripts-session-archaeology.md) — row_key duplication, parse_committed_summary canonical parser
-> [scripts-repo-lifecycle](scripts-repo-lifecycle.md) — plan/execute separation, SKIP_FILES, policy sync import
-> [scripts-dashboard](scripts-dashboard.md) — X-Gator-Dashboard header, source_kind vocabulary, session drill-down, file refresh button, mtime sort
! `gator-audit.py --sessions` and `gator-dashboard.py /api/audit/sessions` both import `gator-session-aggregator` via `import_sibling()` — follows the same graceful degradation pattern as other cross-script imports. `--fleet` and `--refresh` flags are rejected without `--sessions` via `parser.error()` to prevent silent no-ops. Dashboard endpoint logic extracted to `_resolve_audit_sessions()` for testability — handler is a thin delegate. Repos identified by path-hash only (no repo_name param) — consistent with plan's stable identity model. `_inject_repo_keys()` ensures both command-post and standalone fleet data include `repo_key` — the `session_cache_key()` call is the single source of truth for this identity. Cross-doc search uses server-side `_search_repo_files()` endpoint with AND/OR boolean operators — never fetches files individually from JS.
! `gator-audit.py` imports renderers from `gator-audit-renderers.py` via lazy `import_sibling()` — loaded on first call to `render_text()` or `render_html()`, not at module import time. This means `--sessions` and `--json` paths work even if the renderers file is missing. Raises explicit `ImportError` with diagnostic if the file is not found.
! `gator-dashboard.py` file-listing scan (v2.4.5) accepts `.html`/`.htm` in `.gator/` alongside `.md`/`.json`/`.jsonl`. The raw endpoint's MIME map serves them as `text/html; charset=utf-8`. Extension whitelist stays exhaustive — no wildcard, no "any text file" fallback. Same discipline applies whenever a new file kind needs Dashboard visibility: add it to both the scan and the MIME map together, or the file lists but downloads instead of rendering.
