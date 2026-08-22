---
charter: scripts-enterprise
scope: base-wheel `gator enterprise` thin dispatcher + the consolidated `enterprise/` tree (prototype enterprise-cli package, FastAPI server, migrations). Phase 4e (2026-08-02) consolidated ALL Enterprise prototype code under the top-level `enterprise/` folder; the base wheel now degrades to EX_UNAVAILABLE for every enterprise subcommand.
last-verified: 2026-08-02
---

# Charter: Enterprise CLI Scripts & Consolidated Prototype Tree

## Purpose

The `gator enterprise` subcommand group is the activation surface for
optional Enterprise capability, pattern-matched to `gator loop` per
Decision A of the monorepo product-contract decisions. One base install
(`pipx install gator-command`) preserves the CLI surface; the real
command bodies live in the top-level `enterprise/enterprise-cli/`
package, installed separately as a source-checkout dependency.

Phase 4e (2026-08-02) collapsed the split-brain architecture where some
Enterprise code lived in `src/gator_command/scripts/enterprise_*.py`
(shipped in the base wheel) and other pieces (server, migrations,
crypto) lived under a partly-untracked `enterprise/` tree. Per Architect
direction — "we should have ALL the prototype enterprise code in the
enterprise/ folder ... we should not leave pieces behind in
gator-command at all" — all Enterprise code is now consolidated. The
base wheel ships only the thin dispatcher; it will not exercise real
Enterprise behavior until the enterprise-cli package is installed.

## Files

### Base wheel (ships in `pipx install gator-command`)

| File | Role | Symbols |
|---|---|---|
| `src/gator_command/scripts/gator-enterprise.py` | Thin dispatcher (Phase 4e) | `main(argv=None) → int`, `_build_parser() → ArgumentParser`, `_try_import_enterprise_cli() → module or None`, `_unavailable_notice(verb: str) → int`, `CLIENT_SUBCOMMANDS`, `SERVER_SUBCOMMANDS`, `ALL_SUBCOMMANDS`, `PLAN_REF`, `EX_UNAVAILABLE = 69`, `UNAVAILABLE_SENTINEL = "[gator-enterprise-unavailable]"` |

### Consolidated tree (under `enterprise/` — installed separately)

| Path | Role |
|---|---|
| `enterprise/enterprise-cli/` | Python package `gator_enterprise_cli` — real command bodies for setup/status/sync/audit/disconnect (plus more), the `EnterpriseClient` httpx HTTP client, credential store, vendor-hook installer, activate/auth/blocks/machines/policies/providers/repo_init/reports/repos subcommand modules. Own `pyproject.toml`, own entry point `gator-enterprise` (not the base-wheel dispatcher — a separate binary when this package is installed). |
| `enterprise/enterprise-cli/gator_enterprise_cli/credentials.py` | MACHINE-scoped Enterprise credentials store (moved from `src/gator_command/scripts/enterprise_credentials.py` in Phase 4e). `credentials_path`, `write_credentials`, `read_credentials`, `remove_credentials`, `CREDENTIALS_SUBPATH`. Fail-closed reads, chmod 600 on POSIX, `home=` parameter for testability. |
| `enterprise/enterprise-cli/gator_enterprise_cli/vendor_hooks.py` | MACHINE-scoped SessionStart hook installer (moved from `src/gator_command/scripts/enterprise_vendor_hooks.py` in Phase 4e; includes the Codex Phase 4c-B fix for wrong-shape hooks key). `install_enterprise_vendor_hooks`, `_merge_hooks`. |
| `enterprise/enterprise-cli/gator_enterprise_cli/client.py` | Real httpx-based `EnterpriseClient` + `CliError` (from enterprise-mvp; keeps its httpx dependency isolated to this package, unlike the stdlib client that briefly lived in the base wheel in Phase 4c-C-2 and was deleted in 4e). |
| `enterprise/enterprise-cli/gator_enterprise_cli/main.py` | Delegatee target of the base-wheel dispatcher: `from gator_enterprise_cli.main import main` — takes an argv list. |
| `enterprise/app/` | FastAPI service (models, routes, providers, services, auth, db, admin, cache, config, main, middleware, rate_limit). Includes `routes/crypto.py` — envelope encryption endpoints. Not shipped in the base wheel; runs from a source checkout with the `[enterprise-server]` extra installed. |
| `enterprise/migrations/versions/001-008*.py` | Alembic migration chain 001-008 including `007_encryption_keys.py` and `008_transcript_session_id.py`. Now fully tracked (previously only 008 was tracked as the "schema commitment" marker). |
| `enterprise/tests/` | Test suite for the enterprise-cli package + FastAPI service. Includes `test_credentials.py` and `test_vendor_hooks.py` (moved from `tests/` in Phase 4e). |
| `enterprise/Dockerfile`, `enterprise/alembic.ini`, `enterprise/fly.toml`, `enterprise/requirements.txt`, `enterprise/README.md` | Server deployment scaffolding. |

## Subcommand surface

Help output stayed stable through Phase 4e — the same subcommand names
are listed by `gator enterprise --help` in the base install. What
changed is command-body location: real work now lives in the
enterprise-cli package.

**Client-side** (base install, delegated when enterprise-cli is present):
- `setup`, `status`, `sync`, `audit`, `disconnect` — help lists them
  unchanged. When `gator_enterprise_cli` is importable, the dispatcher
  calls its `main(argv)` and returns its exit code. When not
  importable, prints the degraded-mode notice and returns
  `EX_UNAVAILABLE = 69`.

**Server-side** (require `[enterprise-server]` extra + enterprise-cli):
- `server`, `db`, `policy`, `org`, `fleet` — same delegation path;
  same degraded notice when the enterprise-cli package is missing.

## Invariants (`!`)

- **! CLI surface (help output) is a released contract; command-body
  integration is aspirational post-Phase-4e.** Downstream docs, scripts,
  and completion configs may reference `gator enterprise <subcommand>`
  and rely on the verb names appearing in `--help`. Renaming or
  removing a subcommand from `CLIENT_SUBCOMMANDS` /
  `SERVER_SUBCOMMANDS` is a breaking change and requires a deprecation
  cycle; adding is additive.

  Post-Phase-4e nuance flagged by Codex review (2026-08-02, finding 1):
  the enterprise-mvp port's `gator_enterprise_cli/main.py` registers a
  DIFFERENT verb set (`auth/repos/providers/policies/reports/blocks/
  machines/activate/sync/repo`, and 2026-08-08 MVP added `transcripts` +
  `commits`) than the dispatcher originally advertised. Reconciled
  2026-08-09 (Phase 4 — 3.0 stabilization P1.1 + P2.1): dispatcher's
  `CLIENT_SUBCOMMANDS` rewritten to real developer-side verbs
  (`activate/sync/repo/transcripts/commits`), `SERVER_SUBCOMMANDS`
  rewritten to real operator/admin verbs (`auth/repos/providers/
  policies/reports/machines/blocks`), and `ENTERPRISE_CLI_VERBS`
  extended with `transcripts` + `commits`. Every advertised verb now
  maps to a real enterprise-cli command; the integration-gap notice
  becomes a contributor-error guard rather than an operator-visible
  failure mode. Regression pin: `test_every_advertised_verb_is_mapped`.

  Dispatcher shape (post-2026-08-02 fix): the enumeration of
  enterprise-cli's registered verbs is mirrored as `ENTERPRISE_CLI_VERBS`
  (module-level frozenset) and the pre-check runs BEFORE delegation.
  Three ordered checks, each with a distinct notice: (a) package
  importable → else `_unavailable_notice`; (b) `.main` submodule
  importable → else "incomplete install" stderr; (c) verb in
  `ENTERPRISE_CLI_VERBS` → else `_integration_gap_notice`. All three
  return `EX_UNAVAILABLE = 69`.

  Delegation only runs for verbs enterprise-cli actually handles.
  `SystemExit` raised from the delegated `main()` carries the REAL
  exit code (a mapped verb's runtime failure, or the enterprise-cli's
  own argparse rejecting a bad per-subcommand flag) and must
  propagate unmodified. Do NOT catch-and-translate — the earlier
  fix's blanket `except SystemExit → _integration_gap_notice` masked
  real command failures and was reverted in favor of the pre-check.

  Regression pin: `tests/test_gator_enterprise.py::TestIntegrationGap`.
  Post-reconciliation shape (2026-08-09): 1 monkeypatched test for the
  contributor-error guard (synthesizes the advertised-but-unmapped
  condition by removing `transcripts` from ENTERPRISE_CLI_VERBS at test
  time), 1 for the `sync` overlap (delegates cleanly), 3 for Finding-1
  propagation (SystemExit(1)/SystemExit(2)/SystemExit(None) from mapped
  verbs surface as rc=1/rc=2/rc=0 without gap-notice translation).

  Additional wheel-level regression pin: `tests/test_packaging.py::TestInstalledArtifact::test_gator_enterprise_help` + `::test_gator_enterprise_all_verbs_exit_unavailable_in_base_install` iterate the reconciled verb set against an actually-installed wheel (proves the P2.1 reconciliation survived the packaging round-trip and no verb slipped between the source and the wheel).

  ! Sync obligation: any add/remove in the enterprise-cli registered
  set MUST be mirrored in `ENTERPRISE_CLI_VERBS`. Adding an enterprise-cli
  verb without updating the dispatcher constant means valid verbs get
  routed to the gap notice; removing a verb without updating means
  removed verbs slip past the pre-check and produce a raw argparse
  "invalid choice" error at delegation time.

- **! Base wheel MUST NOT ship enterprise-cli modules.** After Phase 4e,
  `src/gator_command/scripts/enterprise_client.py`,
  `src/gator_command/scripts/enterprise_credentials.py`, and
  `src/gator_command/scripts/enterprise_vendor_hooks.py` are DELETED.
  If they reappear (via well-meaning move-back, PR merge conflict, or
  accidental copy) they must be reverted. Regression pin:
  `tests/test_packaging.py::test_wheel_does_not_ship_enterprise_cli_modules`
  fails the wheel build if any of the three reappear.

- **! Degraded-mode exit code is 69 (EX_UNAVAILABLE) with a stable
  sentinel.** When the enterprise-cli package is not importable, the
  dispatcher returns `EX_UNAVAILABLE = 69` and prints a first line
  beginning with `UNAVAILABLE_SENTINEL = "[gator-enterprise-unavailable]"`.
  Both the exit code and the sentinel are released contracts on the
  same footing as the CLI names — keep them byte-stable across
  releases; do not localize. This replaces the Phase 3a-era
  `STUB_SENTINEL = "[gator-enterprise-stub]"`; any automation that
  matched the old sentinel needs to be updated to accept both during
  the deprecation window (or just the new one going forward).

- **! Dispatcher uses `parse_known_args` + REMAINDER passthrough (not
  strict `parse_args`).** The base-wheel dispatcher does NOT know each
  subcommand's real flags — those are defined inside the enterprise-cli
  package. If the dispatcher used strict parsing at its layer, every
  legitimate per-subcommand flag would be rejected before reaching the
  delegatee. This intentionally REVERSES the Phase 3a-era "strict
  parse_args" invariant (which was correct for that phase, when the
  base wheel owned the real command bodies). Post-Phase 4e, strict
  parsing at the dispatcher layer is a bug, not a feature. The
  enterprise-cli's own argparse (`gator_enterprise_cli/main.py`) does
  strict parsing at its layer.

- **! Server-side deps stay optional.** The base wheel's
  `[enterprise-server]` extra pulls `fastapi`, `sqlalchemy`, `alembic`,
  `uvicorn[standard]`, `psycopg[binary]`. The base wheel's dispatcher
  MUST NOT import any of them at module scope. The dispatcher only
  attempts `import gator_enterprise_cli`; the enterprise-cli package
  in turn may lazily import server deps inside command bodies that
  need them. Base install without `[enterprise-server]` extra must not
  error on `gator enterprise --help` — help output is generated from
  the dispatcher's own constants, independent of both extras.

- **! Consolidation is one-way.** Enterprise pieces do not migrate
  back into `src/gator_command/scripts/` even for convenience. The
  Architect's Phase 4e direction — "we should not leave pieces behind
  in gator-command at all" — is architectural. If a piece of Enterprise
  code needs shared use with base Gator, refactor it into a proper
  library boundary (a shared package both wheels import from) rather
  than dual-locating the file.

- **! Enterprise integration is explicitly deferred.** Per Architect:
  "the enterprise portions do not need to work right now ... we are
  not requiring it to work out of the gate." The consolidated tree is
  correct as a starting point for future integration; failing tests
  under `enterprise/tests/` do not block base-wheel releases. Base
  wheel CI must pass (`tests/`, `contracts/`); enterprise CI is scoped
  to `enterprise/tests/` and can be red without holding shipping.

- **! Global hook wrappers MUST resolve Python via `$PYTHON`
  (`_PYTHON_RESOLVER` in `enterprise-cli/gator_enterprise_cli/commands/
  activate.py`), never hardcode `python3`. Every candidate MUST be
  sanity-probed with `-V` before it is accepted — presence on PATH is
  not proof of usability.** Stock Windows has no `python3` interpreter:
  the App Execution Alias for `python3` sits on PATH, passes
  `command -v` and `[ -x ]`, but exits non-zero (typically 126
  "Permission denied" or 9009 "command not found") when actually
  invoked. Two failure modes to guard against — both would break every
  governed commit on Windows:
  - **Hardcoded `python3`** anywhere in a template (the original bug
    fixed in `3afe7e3`).
  - **Trusting `command -v python3`** as a bare fallback without
    running `-V` on the result. The `_gator_py_ok` helper in the
    resolver exists to prevent this; do not remove it or short-circuit
    it. The follow-up fix after the enforcer's Finding 1 explicitly
    added this probe.

  Resolution order (each step gated on the `-V` probe): (1) file at
  `~/.gator/enterprise/cli-python-path` if it exists AND its target
  probes clean (written by `_do_activate`, always present after
  `gator-enterprise activate`); (2) `command -v python3` if it probes
  clean; (3) `command -v python` if it probes clean; else fail with a
  clear stderr message that names the Windows-stub pitfall. The three
  templates (`PRE_COMMIT_HOOK`, `COMMIT_MSG_HOOK`, `POST_COMMIT_HOOK`)
  each concat `_PYTHON_RESOLVER` after the `GATOR_SCRIPT` existence
  check and reference `"$PYTHON"` for every Python invocation, including
  the inline `-c` mode-lookup and the `.gator/scripts/gator-session-
  block.py` fallback in POST_COMMIT_HOOK.

  Regression pin: `enterprise/tests/test_activate_hooks.py` (12 tests).
  `TestHookTemplatesUseResolver` asserts every template embeds
  `_PYTHON_RESOLVER`, contains no bare `python3 <arg>` invocation
  patterns, and includes the `_gator_py_ok` probe helper.
  `TestResolverBehavior` executes the resolver in an isolated bash
  shell with mocked HOME and PATH to prove: happy path, Windows-stub
  fall-through, broken `cli-python-path` fall-through, no-candidate
  loud failure. Skipped only when `bash` is unavailable.

  Surfaced during 2026-08-06 Enterprise local bring-up (Phase 5);
  Finding 1 (residual `command -v python3` vulnerability) surfaced
  by the enforcer immediately after the initial fix landed and
  addressed in the follow-up. Plan artifact
  `.gator/vault/artifacts/2026-08-06-enterprise-local-bringup-implementation-plan.md`.

- **! `gator-enterprise activate --force` MUST NOT rotate the machine
  keypair, and MUST NOT wipe `hook-policy.json`.** `--force` is the
  routine gesture for redeploying hook wrappers after a source change
  (see the resolver TRIPWIRE above — every wrapper edit needs a
  `--force` redeploy). Rotating the keypair on every such redeploy
  would (a) invalidate every previously-encrypted session block on this
  machine, (b) leave the server's stored public key stale until re-
  registered, (c) surprise users who reasonably expected `--force` to
  affect what its help text says it affects (hooks + config).

  Two related contracts, both in `_do_activate`:
  1. Keypair regeneration guard is `if not private_key_path.exists()
     or args.regenerate_keys:` — NOT `or args.force`. Rotation is the
     explicit `--regenerate-keys` gesture; nothing else.
  2. `hook-policy.json` init guard is `if not policy_path.exists():` —
     `--force` does not truncate it. Local intent-mode entries written
     by `repo init` (see next TRIPWIRE) MUST survive `--force`.

  Regression pin: `enterprise/tests/test_activate_hooks.py::
  TestActivateKeyPreservation` (5 tests — first-generate; preserve
  without flags; preserve on --force; rotate on --regenerate-keys;
  --force does not wipe hook-policy.json).

  Surfaced during 2026-08-06 bring-up Phase 5, Finding #2 — every
  `activate --force` during Phase 5 desynced the local private key
  from the server-registered public key.

- **! `gator-enterprise repo init --mode <X>` MUST write the requested
  mode to `~/.gator/enterprise/hook-policy.json` locally, before or
  regardless of any server-side registration attempt.** The global
  hook wrapper reads `hook-policy.json` at commit time; without a
  local entry for the repo's `canonical_identifier`, the wrapper
  defaults to `strict`. Server-side registration in `_register_hook_
  policy` no-ops for repos the server doesn't know about yet (fresh
  repo, no git provider integration, air-gapped setup), so relying on
  the server round-trip alone silently drops the requested mode.

  Contract: `_write_local_hook_policy_intent(canonical_id, mode)`
  runs first in `_do_repo_init`, always (both when `client` is present
  and when it is None). Server-side registration is best-effort on
  top. `_register_hook_policy` returns a boolean so the caller can
  print truthful diagnostics ("Local intent-mode written: X → Y
  (honored by hooks until server registration succeeds)").

  Sync contract (load-bearing companion): `_do_sync` MERGES server
  hook-policy with local, server winning for overlapping keys. Without
  merge semantics, the very next sync (which `activate` itself runs
  at end) would wipe the just-written intent — reproducing the exact
  bug. Do not revert `_do_sync` to a wholesale replace.

  Regression pins:
  `enterprise/tests/test_repo_init.py` (8 tests — write-intent when
  missing, merge with existing, update-own-entry, corrupt-file
  recovery; `_register_hook_policy` returns False on unknown repo /
  True on PUT-success / False on server error; end-to-end
  `_do_repo_init` writes intent even when server doesn't know the
  repo). `enterprise/tests/test_activate_hooks.py::TestSyncMerge`
  (3 tests — local preserved when server empty; server wins on
  overlap; disjoint local+server both survive).

  Surfaced during 2026-08-06 bring-up Phase 5, Finding #3 — sandbox
  provisioned with `--mode evidence_only` had every commit run in
  strict because no git provider knew the repo.

- **! `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/` is the THIRD copy of the session-capture scripts and MUST stay byte-identical with the shipped and template copies.** `repo_init.py::_install_bundled_scripts()` copies these into every Enterprise-provisioned repo's `.gator/scripts/`. The other two copies are `.gator/.includes/scripts/` (shipped, used by v2 repos gatorized with `gator gatorize`) and `src/gator_command/templates/gator-starter/scripts/` (template, copied by `gatorize`). Drift means Enterprise-provisioned repos and gator-gatorize'd repos run different code — Codex Finding #1 from the 2026-08-07 whiteboard review caught exactly this: a multi-session fix updated the first two but not the third, so freshly `repo init`'d repos still ran v1-only single-session logic. See `scripts-cross-cutting.md::Multi-Session Vendor Attribution` for the authoritative TRIPWIRE and the regression pin (`tests/test_multi_session.py::TestByteIdentityAcrossThreeCopies` — parametrized across both filenames, will fail loudly on any future divergence).

- **! `POST_COMMIT_HOOK` no longer generates session blocks (retired 2026-08-09, Phase 4 P1.3).** The prior template contained a 40-line block-generation section that invoked `gator_enterprise_cli.block_generate` (via CLI_PYTHON) with a fallback to repo-local `gator-session-block.py`, then `git add`'d the produced artifacts. Every commit fired this pipeline. Under the transcripts-first MVP, per-commit block artifacts are not the evidence path — operator-triggered `gator-enterprise transcripts pull` reads the session snippets directly. Retired code removed from `POST_COMMIT_HOOK` in `activate.py`; the hook template now runs only `--phase cleanup` and returns. Regression pin flipped: `enterprise/tests/test_activate_atrisk.py::TestV2FirstScriptDiscovery::test_post_commit_does_not_generate_session_blocks` (formerly `test_post_commit_block_script_uses_v2_first`) now asserts `.gator/.includes/scripts/gator-session-block.py`, `.gator/scripts/gator-session-block.py`, `block_generate`, and `session-blocks` are all ABSENT from POST_COMMIT_HOOK. **Machines already activated** before 2026-08-09 still have the old hook code in `~/.gator/hooks/post-commit`; re-running `gator-enterprise activate --force` rewrites it. This is expected — activate is machine-scoped.

- **! `_do_repo_init` does NOT create `.gator/session-blocks/` or touch `.gitignore` (retired 2026-08-09, Phase 4 P1.2).** Under the transcripts-first MVP, evidence lives in Enterprise-managed storage (DB + blob store), not in Git. The prior flow created `.gator/session-blocks/` and called `_fix_gitignore(repo_path)` to un-gitignore it on every provisioning run — both directly contradicted the ratified architecture. Removed: (a) the `mkdir` at `_do_repo_init` line ~123, (b) the `_fix_gitignore(repo_path)` call at line ~166, (c) the `_fix_gitignore` function definition (lines ~359-380). Consequence: `.gator/session-blocks/` stays gitignored globally, sandbox commits don't accumulate block artifacts, evaluators inspecting `.gitignore` post-`repo init` see no governance-driven rewrites. Post-MVP work (retiring `block_generate.py`, obsolete server surfaces) is bigger scope and deferred per stabilization plan §4 P3.2.

- **! `repo init --mode` default is `strict`, not `evidence_only`.**
  Reverses the pre-2026-08-07 enterprise-cli default (which was
  `evidence_only` with a help-text pointer to Individual for stricter
  ceremony). Per Architect 2026-08-07: "commits should not go silently.
  The commit should record everything it can, forcing the bot, human,
  etc. to explain what is happening with the commit." Strict is the
  only mode that FORCES the explanation (blocks without commit_draft).
  `warning` requires commit_draft too but downgrades block→warning
  (useful for CI/bot repos that can't respond to a block); operators
  should choose it explicitly for those repos. `evidence_only` and
  `off` remain available for explicit opt-out — machine-generated
  evidence continues to flow regardless of mode.

  Choices list widened from `["evidence_only", "warning"]` to
  `["off", "evidence_only", "warning", "strict"]` (all four the
  bundled pre-commit script recognizes; keeping choices narrower
  would let some values through the wrapper's mode lookup but not
  through the `repo init` CLI, which would be confusing).

  Regression pin: `enterprise/tests/test_repo_init.py::
  TestRepoInitIntegration` passes `mode="evidence_only"` explicitly
  — that test verifies the non-default branch and continues to
  demonstrate that explicit opt-out still writes the requested mode
  correctly.

- **! Mode-lookup in hook wrappers MUST compute the policy path with
  Python's `Path.home()` and MUST pass the repo-id via the
  `GATOR_REPO_ID` env var — NEVER shell-interpolate `$HOME` into the
  Python `-c` script.** Surfaced end-to-end verifying Finding #3 during
  the follow-up arc. On Git Bash for Windows, `$HOME` expands to
  `/c/Users/<user>` (MSYS-form) which Windows Python's `open()` cannot
  resolve; the `except: print('strict')` catch in the lookup then
  silently swallows the `FileNotFoundError` and every commit runs in
  the fail-safe `strict` default. Result: `repo init --mode X` for
  X != strict is completely defeated on Windows even with the local
  intent-write in place.

  Contract implemented in `_MODE_LOOKUP` (module-level in activate.py,
  concatenated into all three hook templates after `_PYTHON_RESOLVER`):
  1. Policy path: `Path.home() / '.gator' / 'enterprise' / 'hook-policy.json'`
     inside Python. NO shell path interpolation.
  2. Repo-id: `export GATOR_REPO_ID=<from .gator/repo-id>` in shell,
     read by Python via `os.environ.get('GATOR_REPO_ID', '')`. Quote-safe;
     survives unusual chars in the canonical identifier.
  3. Fail-safe: any exception (missing file, malformed JSON, missing
     env) falls through to `strict`. This is intentional — a broken
     policy state MUST NOT relax enforcement below `strict`.

  Regression pins in `enterprise/tests/test_activate_hooks.py::
  TestModeLookupIsWindowsSafe` (5 tests — each template embeds
  `_MODE_LOOKUP`; uses `Path.home()` not `$HOME`; passes repo-id via
  `GATOR_REPO_ID` env var; defaults to `strict` on error on both the
  Python and shell sides).

  Sync obligation: the resolver TRIPWIRE above and this one share the
  same anti-pattern (Windows path/interop failures around shell-embedded
  Python). Any new inline `python -c` block in a hook wrapper MUST NOT
  interpolate a `$HOME`-derived path — always compute paths inside
  Python via `pathlib`.

- **! `enterprise/tests/conftest.py` must put `enterprise/` and
  `enterprise/enterprise-cli/` on `sys.path` and must filter the
  `StarletteDeprecationWarning` about httpx2.** `enterprise/` is not a
  Python package (no `__init__.py` at that level) and the root
  `pytest.ini` scopes collection to `tests/ + contracts/compatibility/`
  — running enterprise tests via `pytest enterprise/tests/` from repo
  root without the conftest sys.path insert fails at collection with
  `ModuleNotFoundError: No module named 'app'` for every test file
  that imports from `app.*`. The conftest adds both `enterprise/`
  (makes `app` importable) and `enterprise/enterprise-cli/` (makes
  `gator_enterprise_cli` importable) so individual test files don't
  need per-file workarounds.

  The httpx2 warning filter needs BOTH `warnings.filterwarnings()`
  (for the import-time warning that fires before pytest's warning-
  capture takes over) AND a `pytest_configure` hook that registers
  the filter with pytest's own warning system (because pytest re-
  enables warnings via its `catch_warnings` context and would
  otherwise surface the filtered warning in the summary regardless
  of the Python-level filter). Neither alone suffices — do not
  remove either.

  Surfaced during Session 3 (Findings #7 + #8) of the 2026-08-06
  Enterprise local bring-up. Both fixed in the same commit; no
  regression pin (fixing test infrastructure IS the pin).

- **! Diagnostic log for block-generation failures at
  `~/.gator/diagnostics/block-gen.log` (bounded, machine-local).**
  The post-commit shell wrapper suppresses stderr from
  `gator_enterprise_cli.block_generate` via `2>/dev/null` — that
  redirection is intentional (a loud stderr on every commit would
  clutter terminal output) but it makes real failures invisible.
  `block_generate` MUST write structured diagnostic entries to the
  log file on every non-happy-path outcome (subprocess-delegate
  failure, unknown crypto mode, corrupt v2 block, encryption
  failure). Format:
  `<ISO8601-utc> commit=<sha12> event=<slug> [msg=<repr>]` — one
  line per event, ≤~700 chars.

  Bounded rotation contract: log is trimmed to the last
  `_DIAG_LOG_MAX_LINES` (500) whenever it exceeds
  `_DIAG_LOG_ROTATE_TRIGGER` (750). Never grows unboundedly on
  broken repos. `_diag_log` and `_diag_log_rotate` are strictly
  best-effort — they must never raise, since introducing a new
  failure mode to a helper whose whole purpose is exposing hidden
  failures would be the opposite of what the fix is for.

  Regression pins:
  `enterprise/tests/test_block_generate.py` (9 tests). `TestDiagLog`
  (4 — creates parent dir + appends, multiple entries, never raises
  on unwritable path, truncates long messages). `TestDiagLogRotate`
  (3 — no-op below trigger, trims to last 500 above trigger, never
  raises on read failure). `TestMainFlowLogging` (2 — plaintext-
  delegate-failed and unknown-crypto-mode-fallback both write an
  entry with the expected event slug + message).

  Surfaced during 2026-08-06 bring-up Phase 5, Finding #4 — silent
  stderr suppression required manual re-run of the delegated command
  to diagnose why session blocks weren't emitted.

- **! Transcript-custody data model (Migration 009 + models + BlobStore, 2026-08-08 MVP Phase 1).** Enterprise now owns transcript evidence storage per the ratified transcripts-first architecture. See parent plan `.gator/vault/artifacts/2026-08-08-enterprise-transcripts-first-mvp-implementation-plan.md` + ADR `2026-08-08-enterprise-transcripts-first-adr.md` (D1-D11).

  **Migration 009** (`enterprise/migrations/versions/009_transcript_custody.py`) — two new tables, no changes to existing schema:
  - `transcript_sessions` — one row per distinct vendor session ingested from a client machine. Metadata + BlobStore reference (`blob_key`, `blob_sha256`, `blob_size_bytes`); the transcript body itself lives out-of-DB. Idempotency: unique on `(organization_id, machine_id, vendor, vendor_session_id)`.
  - `commit_transcript_links` — many-to-many between `commits` and `transcript_sessions` with `linkage_basis` recording WHY each link exists. Unique on `(commit_id, transcript_session_id, linkage_basis)` — a commit+session pair can be linked by MULTIPLE bases (e.g., both exact-SHA AND session-id-in-snippet), each is an independent audit-signal row. ON DELETE CASCADE from both `commits` and `transcript_sessions`.

  **Models** (`enterprise/app/models/transcript_session.py` + `commit_transcript_link.py`) — mirror the migration schema. Both registered in `enterprise/app/models/__init__.py` so Alembic autogenerate + tests see them.

  **BlobStore contract** (`enterprise/app/services/blob_store.py`) — `Protocol` (runtime_checkable) with 5 operations: `put(key, content) -> str`, `get(key) -> bytes` (raises `BlobNotFound`), `exists(key) -> bool`, `delete(key) -> None` (idempotent), `list(prefix) -> list[str]`. Implementations MUST be reentrant + safe for concurrent use across ingestion workers. `build_blob_key()` helper produces the canonical namespaced key (`transcripts/{org}/{machine_short}/{vendor}/{yyyy-mm-dd}/{session}.jsonl`).

  **Reference implementation** (`enterprise/app/services/blob_store_filesystem.py::FilesystemBlobStore`) — filesystem-backed, suitable for single-node Enterprise deployments. Atomic write via temp-file + `os.replace` with Windows-safe retry loop (PermissionError from concurrent replace is transient; exponential backoff, 6 attempts). Rejects empty keys, traversal (`..` segments), and normalizes backslashes to forward-slashes.

  **Config** (`enterprise/app/config.py::Settings.blob_store_root`) — env var `BLOB_STORE_ROOT`, default `/var/lib/gator-enterprise/blobs`. Not read by the blob-store module directly; ingestion pipeline in Phase 2 will instantiate `FilesystemBlobStore(settings.blob_store_root)` at startup.

  **linkage_basis vocabulary discipline (TRIPWIRE — no DB enum by design)**: the column is a plain `String(64)`, not a Postgres enum, so evolving the vocabulary post-MVP doesn't require a migration. That flexibility comes with an obligation: any add/change/rename to the MVP vocabulary (`exact_sha_in_transcript`, `session_id_in_snippet`, `strong_machine_repo_time`, `orchestrator_declared`) MUST be reflected in the CLI help text for `gator-enterprise transcripts link`, the API docs, and the operator query documentation. Drift means audit queries return unexpected values.

  **Post-MVP deferred columns on `commits`** (verified in Phase 0, not needed for MVP): `branch VARCHAR(255)`, `gator_trailers JSONB`. Added only if Phase 2 ingestion proves them necessary.

  **Post-MVP retired columns/tables** (per plan D10 OBSOLETE list; NOT removed in Phase 1): existing `commit_evidence_blocks` table is Git-carried encrypted-block evidence — transitional, replaced conceptually by the transcript-custody tables. Cleanup happens in a post-MVP arc.

  **Regression pins**: `enterprise/tests/test_transcript_models.py` (SQLite in-memory; uniqueness contracts, FK cascades, linkage_basis vocabulary tolerance). `enterprise/tests/test_blob_store_filesystem.py` (put/get/exists/delete/list; idempotent put; overwrite semantics; traversal rejection; empty-key rejection; multi-thread concurrent-put safety; Windows-safe replace retry). 34 tests total, all pass.

  **Live verification (2026-08-08)**: Migration 009 applied end-to-end against local Postgres on port 5434; `alembic current` → `009 (head)`; `\d transcript_sessions` and `\d commit_transcript_links` confirm expected columns, indexes, unique constraints, and FKs. Downgrade + re-upgrade round-trip verified reversible.

- **! Transcript-custody ingest + read APIs + Claude Code pull CLI (2026-08-08 MVP Phase 2).** The full round-trip from local Claude Code transcripts → Enterprise storage now works end-to-end. See parent plan §7 (endpoints), §8 (linkage), §10 (pull CLI).

  **New routes** (`enterprise/app/routes/ingest.py` + `enterprise/app/routes/transcripts.py`, both registered in `app/main.py`):
  - `POST /api/v1/commits/ingest` — batch upsert of local git commits; idempotent by `(organization_id, repo_identifier, commit_sha)`; returns per-item `created`/`updated`/`unchanged` status. This is D11: local repos with no git-provider integration would otherwise have no `commits` rows to link transcripts against. `_dt_equal` normalizes naive-vs-aware datetime comparison so re-ingest of an already-stored `committed_at` doesn't spuriously report `updated` (SQLite drops tzinfo on round-trip; Postgres preserves it — production is unaffected, but the equality helper is now the invariant).
  - `POST /api/v1/transcripts/ingest` — accepts base64 body with `content_encoding: raw|gzip`; decodes, stores via `BlobStore.put`, computes `blob_sha256`, upserts `transcript_sessions` row, runs the linkage algorithm inline. Idempotent by `(org, machine, vendor, vendor_session_id)`; re-ingest with different content rewrites the blob and refreshes `last_seen_at`.
  - `GET /api/v1/transcripts?<filters>` — paginated list with per-session `linked_commit_count` via left-join to `commit_transcript_links` (`GROUP BY transcript_sessions.id`).
  - `GET /api/v1/transcripts/{id}` — session + links inline.
  - `GET /api/v1/transcripts/{id}/blob` — streams the raw transcript body in 64KB chunks with `X-Blob-Sha256` header for integrity verification.
  - `GET /api/v1/commits/{sha}/transcripts` — reverse lookup, accepts 7-40 char SHA prefix, optional `repo_canonical_id` scope.

  **Linkage algorithm** (Phase 2 implements the ingest-time half of §8): bases `exact_sha_in_transcript` (scan first 4MB of content for `\b[0-9a-f]{7,40}\b`, look up unique-prefix match in `commits`; ambiguous 2+ matches skip rather than link to the wrong one) and `session_id_in_snippet` (match transcript's `vendor_session_id` against `commits.transcript_session_id` populated from snippet-driven commit ingest). Both run in `ingest.py::_run_linkage`. TRIPWIRE: per-call `seen_pairs: set[(commit_id, basis)]` dedup is REQUIRED — a real transcript often mentions the same commit's SHA multiple times (full 40-char plus one or more prefix forms). Without the dedup, the second occurrence passes the DB-side existence check because the first hasn't been flushed yet, then `db.commit()` blows up on the `uq_ctl_commit_session_basis` unique constraint. Regression pin: `test_ingest_routes.py::TestLinkageAlgorithm::test_same_sha_multiple_times_in_transcript_dedups`.

  **Commit model update** (`enterprise/app/models/commit.py`): Migration 008 added the `transcript_session_id` column but the `Commit` ORM class was never updated to include it. Added the mapped column now so writes route through SQLAlchemy instrumentation (rather than `__dict__` bypass) and reads work naturally. No migration needed — column exists in Postgres already from 008.

  **Claude Code discovery** (`enterprise/enterprise-cli/gator_enterprise_cli/transcripts_discovery.py`): reads `~/.claude/projects/<project-hash>/<session-uuid>.jsonl` line-by-line without loading the whole file (individual sessions run 100s of MB). Extracts `sessionId`, `message.model`, `cwd`, timestamp span, turn count from a small set of event types (`user`, `assistant`, `mode`). Malformed lines skip individually rather than fail the whole file. `--since` filter compares against `ended_at or started_at`. Env override: `CLAUDE_TRANSCRIPTS_ROOT` (used by tests). Vendor dispatch through `discover(vendor)`; `claude` and `anthropic` both resolve to the Claude handler. TRIPWIRE: the Claude Code JSONL format is not a documented API — a future format shift could silently break the parser. Discovery flags parse errors on the `DiscoveredTranscript` record rather than raising, so failures surface in the pull summary instead of aborting the batch.

  **Pull CLI** (`enterprise/enterprise-cli/gator_enterprise_cli/commands/transcripts.py`): `gator-enterprise transcripts pull [--vendor claude|anthropic|all] [--since <iso>] [--dry-run] [--limit N] [--commits-per-repo N] [--no-compress]`. Four-step sequence per §10: (1) read `~/.gator/dashboard-repos.json` + `~/.gator/machine-id`, iterate repos with git log + `.gator/session-snippets/*.json`; (2) POST commit batch (`repo_canonical_id = local/<basename>` convention matching the sandbox repo); (3) discover Claude transcripts; (4) upload each transcript (gzip by default). Prints per-transcript status line + summary. Machine-id read from `~/.gator/machine-id` (schema-versioned `id:` line format); snippet hints carry `transcript_session_id`/`machine_id`/`machine_label`/`agent` into the commit payload so `session_id_in_snippet` linkage lights up on the server. Also ships `transcripts list` (paginated read; smoke-test surface for the Phase 2 exit criteria — `show`/`get`/`link`/`relink` land in Phase 3-4). ASCII-only output on Windows (cp1252 stdout can't render `→`; use `->`).

  **Config**: uses existing `BLOB_STORE_ROOT` env / `Settings.blob_store_root` from Phase 1. Ingest handler instantiates `FilesystemBlobStore` per request (cheap — no cached state).

  **Regression pins**: `enterprise/tests/test_ingest_routes.py` (27 tests — commits ingest idempotency + updates + org isolation; transcripts ingest with raw/gzip encoding + reingest semantics; linkage bases including the same-SHA-multiple-times dedup regression; list pagination + vendor filter; get with inline links; blob stream + sha256 header; reverse commit lookup with prefix; auth enforcement). `enterprise/tests/test_transcripts_discovery.py` (11 tests — pure discovery module with synthetic Claude project fixtures via `CLAUDE_TRANSCRIPTS_ROOT`). All 38 pass under in-memory SQLite via the conftest JSONB compile hook.

  **Live verification (2026-08-08)**: booted uvicorn against local Postgres on port 5434; `gator-enterprise transcripts pull --since 2026-08-08` on this development machine ingested 150 commits across 13 gatorized repos and 2 Claude Code transcripts (1.16MB + 6.0MB), producing 23 links across the two implemented bases (`exact_sha_in_transcript: 15`, `session_id_in_snippet: 8`). Re-run reported all commits as `unchanged` — idempotency verified end-to-end.

  **Follow-on hardening (2026-08-08, post-Phase-2 commit)**: `GET /api/v1/commits/{sha}/transcripts` now hex-validates its `commit_sha` path parameter (7-40 chars, `[0-9a-fA-F]` only) before building the `Commit.commit_sha.like(f"{sha}%")` query. SQLAlchemy already parameterizes the LIKE bind so raw injection was never possible, but a `%` or `_` in the caller-supplied prefix would have silently widened the match to unintended commits. Regression pins: `test_ingest_routes.py::TestCommitTranscripts::test_rejects_short_sha` + `test_rejects_wildcard_in_sha`. Pattern to preserve for future SHA-prefix endpoints (`transcripts show`/`get`/`link` in Phase 3): the LIKE-pattern-widening class is why the hex check is not just defense-in-depth but a correctness gate.

- **! Transcript-custody linkage completion + explicit linkage surface (2026-08-08 MVP Phase 3).** Closes out the linkage half of §8 (all four MVP bases now implemented) and adds the operator-facing surface for explicit linkage + relink. See parent plan §8 (algorithm), §9 (CLI), §13 Phase 3.

  **New linkage basis** — `strong_machine_repo_time` (medium confidence) in `ingest.py::_run_linkage` Basis 3. For commits WITHOUT `exact_sha_in_transcript` or `session_id_in_snippet` already claiming them (via `seen_pairs` in-memory dedup + a query against pre-existing high-confidence links on the same transcript), match commits where:
  - Same `machine_id` as the transcript
  - `basename(repo_identifier)` == `basename(workspace_hint)` — MVP workspace→repo mapping is best-effort via trailing path segment (`local/gator` matches `C:\...\code2\gator`; the seam is documented as brittle in `transcripts_discovery.py` and this charter's growth-path section for a Phase 4+ improvement)
  - `committed_at` within `[started_at - 24h, ended_at + 24h]` (or `started_at + 24h` if no end)
  - `Commit.committed_at IS NOT NULL` (nullable-timestamp defence)

  Helper functions `_workspace_basename()` + `_repo_basename()` normalize backslash/forward-slash + strip Windows drive letters + reject empty/root strings. Timestamp comparison uses the same aware-vs-naive normalization pattern as `_dt_equal` from Phase 2 (SQLite drops tzinfo; Postgres preserves it — production is unaffected but the helper keeps in-memory SQLite tests honest).

  **linkage_metadata payload for `strong_machine_repo_time`**: `{commit_sha, matched_workspace_basename, matched_machine_id, commit_committed_at, session_started_at, session_ended_at}` — every input to the match decision recorded so audit consumers can post-hoc reason about false positives without re-running the algorithm.

  **New endpoints** (both in `ingest.py`, mounted under existing `/api/v1/` prefix):
  - `POST /api/v1/transcripts/{id}/link` — orchestrator-declared linkage. Body: `{commit_sha, repo_canonical_id?, linkage_basis="orchestrator_declared", linkage_confidence="high", linkage_metadata?}`. Same hex+length validation as `GET .../transcripts` (`OrchestratorLinkBody` Pydantic model + inline validators). Ambiguous SHA prefix returns 409 `ambiguous_commit` (rather than picking one — matches the ingest-time algorithm's "skip when 2+ match" policy for exact_sha). Idempotent by `(commit_id, transcript_session_id, linkage_basis)` — repeat calls return existing `link_id` with `status: "unchanged"`. The `linkage_metadata` gets `commit_sha` + `declared_at` auto-populated if not provided by the caller.
  - `POST /api/v1/transcripts/{id}/relink` — re-runs the full ingest-time linkage algorithm against the stored blob (reads from `BlobStore.get(ts.blob_key)`, calls `_run_linkage` with the current row's metadata). Discovers NEW links only — `_upsert_link` returns False for pre-existing rows and they don't count. Critical invariant: relink NEVER deletes existing links, so `orchestrator_declared` assertions survive across relinks — that's what makes relink safe to run on any schedule. If the blob is unreachable (retention purge, corrupted BlobStore state), returns 410 `blob_missing` rather than a 500.

  **CLI verbs** (`enterprise/enterprise-cli/gator_enterprise_cli/commands/transcripts.py`):
  - `transcripts show <tid>` — key/value + links table via `GET /api/v1/transcripts/{id}`.
  - `transcripts get <tid> [--output|-o <file>|- ]` — streams the raw blob body via `GET .../blob`. Default output is stdout (binary-safe `sys.stdout.buffer.write` on Windows). File output prints byte count + `blob_sha256` for verification.
  - `transcripts link <tid> --commit <sha> [--repo <id>] [--basis <b>] [--confidence <c>] [--metadata <json>]` — POSTs to the new `/link` endpoint. `--metadata` is a JSON object merged into `linkage_metadata`; non-object or invalid JSON exits 2 with a clear error.
  - `transcripts relink <tid>` — POSTs to `/relink`; prints per-new-link basis.
  - `_resolve_transcript_id()` — accepts 8+ char UUID prefix, expands via `GET /api/v1/transcripts?limit=200` client-side scan. Ambiguous prefix (multiple matches) exits 1 rather than picking one; not-found exits 1 with the supplied prefix quoted. Full 36-char UUIDs pass through untouched — the prefix scan is only paid when a shorter id is supplied.

  **New CLI subcommand** (`enterprise/enterprise-cli/gator_enterprise_cli/commands/commits.py`): `commits transcripts <sha> [--repo <id>]` — reverse-lookup for the transcript custody surface. Verb-first argparse pattern (`commits transcripts <sha>`, not `commits <sha> transcripts`) because argparse resolves subcommand groups before positionals; the API URL contract is unchanged. Registered in `main.py` alongside `transcripts`. **v2.6.1 fix (2026-08-13)**: module docstring + `handle()` fallback usage message + `main.py` register-comment previously quoted the URL shape (`commits <sha> transcripts`) — an evaluator-mislead vector caught in smoke-test Run 1 (Finding #8). All three fixed to the correct verb-first shape; the fallback also gained the `[--repo <id>]` option that had been hidden.

  **Regression pins** (`enterprise/tests/test_ingest_routes.py` — 17 new tests, 46 total in file, all pass):
  - `TestStrongMachineRepoTimeLinkage` (5) — positive match, higher-confidence-wins skip, workspace mismatch, time-outside-window, machine-id mismatch
  - `TestOrchestratorDeclaredLink` (8) — create, idempotent, visible-via-reverse-lookup, prefix-SHA-accepted, ambiguous-409, unknown-commit-404, bad-SHA-400, unknown-transcript-404
  - `TestRelink` (4) — new-link-after-later-commit-ingest, idempotent, preserves-orchestrator-declared, unknown-transcript-404

  **Live verification (2026-08-08)**: booted uvicorn against local Postgres on port 5434. Existing sessions from Phase 2 dogfooding: `76c6bdf2` (6.0MB, ba565a28-171 vendor session, previously 23 `session_id_in_snippet` links); `2ff89e37` (1.16MB, 331a6a12-b57, previously 7 links). Ran `transcripts relink 76c6bdf2` → 1 new `strong_machine_repo_time` link discovered on commit `e784d604` (its snippet had null transcript_session_id so session-id linkage never fired originally, but machine + workspace + time window matched). `commits transcripts e784d604` now shows all three link classes: `exact_sha_in_transcript` (high), `session_id_in_snippet` (high), and `strong_machine_repo_time` (medium) — same commit visible from all applicable evidence angles. `transcripts link 76c6bdf2 --commit e784d604 --metadata '{"note":"live-verify"}'` created an `orchestrator_declared` link; second call returned `unchanged` (idempotency proven end-to-end).

  **Phase 4 residue (explicitly NOT in Phase 3)**: `transcripts list` UX polish + SQL views (`recent_transcripts`, `commits_with_transcript_coverage`, `unlinked_recent_transcripts`); operator guide artifact. Named for scope honesty — `list`/`show`/`get`/`link`/`relink` all functional now, but the guided-tour operator experience is a Phase 4 concern.

- **! Operator query surface — Migration 010 views + list UX polish + operator guide (2026-08-08 MVP Phase 4).** Closes the MVP query surface with three named SQL views, richer `transcripts list` output, and a runnable end-to-end operator guide. See parent plan §9 (view definitions) + §13 Phase 4 (updated scope).

  **Migration 010** (`enterprise/migrations/versions/010_transcript_query_views.py`) — three views over the Phase 1 tables. Views intentionally do NOT filter by `organization_id`; the caller adds `WHERE organization_id = ...` at query time so one DDL works for every tenant.
  - `recent_transcripts` — session metadata joined with `LEFT JOIN commit_transcript_links` + `GROUP BY ts.id` for `linked_commit_count`. Mirrors what the CLI `transcripts list` endpoint returns; useful for interactive `psql` queries.
  - `commits_with_transcript_coverage` — one row per commit with `linked_transcript_count` and `best_linkage_rank`/`best_linkage_basis_ranked`. Rank uses `MIN(CASE linkage_basis WHEN 'exact_sha_in_transcript' THEN 1 ... END)` because the string values don't sort correctly alphabetically. The `_ranked` string column carries the human-readable form. Primary "audit-gap" surface: `WHERE linked_transcript_count = 0 AND snippet_agent IS NOT NULL` finds AI-authored commits with no transcript on file.
  - `unlinked_recent_transcripts` — sessions ingested within the last 7 days with zero links; the "why is this session floating?" investigation queue. Bounded by `ingested_at > NOW() - INTERVAL '7 days'`; older unlinked sessions require the raw table.

  TRIPWIRE — the view definitions reference columns on the underlying tables (`transcript_sessions`, `commit_transcript_links`, `commits`). Any column rename in a future migration MUST be paired with a follow-up view migration or these views break silently at query time. Unique-constraint names are NOT referenced here, so those are safe to rename.

  **`transcripts list` UX polish** (`enterprise/enterprise-cli/gator_enterprise_cli/commands/transcripts.py::_handle_list`):
  - New flags: `--until` (server-side upper bound on `started_at`, complements the existing `--since`), `--offset` (paginate without spamming `--limit`), `--unlinked` (**Phase 2 Q3 promotion, 2026-08-14**: server-side filter via new `?unlinked=true` API query param — was previously client-side-only; the CLI keeps a defensive client-side filter as fallback for old-server compatibility), `--sort {ingested|started|size|links}` (client-side re-sort; ingested is a no-op since the server returns that order), `--wide` (adds Machine + Started columns).
  - Per-vendor summary line auto-appears when >= 2 vendors are visible in the result set.
  - Non-breaking: existing invocations (no new flags) produce byte-identical output.

  **Operator guide** (`.gator/vault/artifacts/enterprise-transcripts-mvp-operator-guide.md`) — end-to-end runthrough for someone approaching the MVP cold: prerequisites, 5-command golden path, per-verb CLI reference, operational plumbing (uvicorn boot, migrations, BlobStore layout, machine-id), five SQL query recipes (recent + coverage + audit gap + investigation queue + storage stats), post-hoc linkage recovery workflow, seven troubleshooting entries covering the failure modes surfaced during Phase 2/3 dogfooding, and an explicit "NOT in MVP" list. Vault artifact (not shipped in git) because it references specific in-firewall deployment shape; a shipped version tuned for public docs is post-MVP.

  **Regression pins**:
  - Migration 010 verified via `alembic upgrade head` + downgrade + re-upgrade round-trip against local Postgres port 5434 (all three views survive the round trip).
  - New test `test_ingest_routes.py::TestListTranscripts::test_until_filters_upper_bound` covers the `until` query param that had been unshipped/untested since Phase 2. Full enterprise suite: 225 passed, 1 skipped.
  - CLI `--wide`, `--sort`, `--unlinked` verified live against the local server on this dev machine (2 real transcripts, 25+7 links).

  **Live verification (2026-08-08)**: all three views populated against the Phase 2/3 dogfooding data. `SELECT ... FROM recent_transcripts` returns the two ingested sessions with correct link counts. `commits_with_transcript_coverage ... ORDER BY best_linkage_rank ASC, committed_at DESC` surfaces commit `e784d604` at the top with 4 links, best basis `1_exact_sha_in_transcript`. `unlinked_recent_transcripts` is empty on this machine (both sessions have links).

  **MVP query surface complete.** Phases 5-6 remain (hook seam cleanup + base-gator `Gator-Machine-Id` trailer); these are minimal deltas that don't touch the transcript custody surface described in this block.

- **! Hook seam cleanup — v2-first script probe + at-risk hook enumeration (2026-08-08 MVP Phase 5).** Two Change items from §11 of the plan. Closes the silent-governance-bypass bug on v2 repos + makes `gator-enterprise activate` honest about the blast radius of setting global `core.hooksPath`.

  **Change 1 — v2-first hook wrapper templates** (`enterprise/enterprise-cli/gator_enterprise_cli/commands/activate.py`): the three global hook wrappers (`PRE_COMMIT_HOOK`, `COMMIT_MSG_HOOK`, `POST_COMMIT_HOOK`) previously hardcoded the v1 script path `.gator/scripts/gator-pre-commit.py`. On a v2 repo, the `[ -f "$GATOR_SCRIPT" ]` guard silently exited 0 and governance did not run — the exact bug §11 Change 2 flagged. New shared snippet `_GATOR_SCRIPT_RESOLVER` probes v2 (`.gator/.includes/scripts/gator-pre-commit.py`) FIRST, falls back to v1 (`.gator/scripts/gator-pre-commit.py`) SECOND, exits 0 only when neither exists (correct behavior for non-gatorized repos). Same v2-first ordering applied to the `gator-session-block.py` fallback in `POST_COMMIT_HOOK`. TRIPWIRE: the v2-first order is load-bearing under the plan's v2-only ratification — reversing it would re-invert the priority on mixed-layout machines. Regression pins: `test_activate_atrisk.py::TestV2FirstScriptDiscovery` (3 tests: v2-before-v1 ordering + variable-assignment shape + block-script parity).

  **Change 2 — at-risk hook enumeration + blocking prompt** (same file, new `_enumerate_at_risk_hooks` + `_warn_about_at_risk_hooks` functions called from `_do_activate` BEFORE any `~/.gator/` state is written). Walks `~/.gator/dashboard-repos.json` and for each repo:
  - Reports non-`.sample` files in `.git/hooks/*` — active hooks that will stop firing once global `core.hooksPath` is set.
  - Detects hook-framework markers in repo root: `.pre-commit-config.yaml`, `.pre-commit-hooks.yaml`, `lefthook.yml`, `lefthook.yaml`, `husky.config.js`. Framework marker alone (no `.git/hooks/*` files) is enough to trigger a warning — the framework installs its hooks lazily.
  - Skips repos with local `core.hooksPath` set — those are immune to the global takeover (Git prefers the local setting) and enumeration is silent for them.

  Behavior on Linux/macOS: prints the per-repo enumeration + a `Proceed with activate? [y/N]:` prompt. Non-affirmative (or empty, or EOF) reply exits 1 with `Aborted by operator.`. `--yes`/`-y` skips the prompt but still prints the warning + notes `--yes was passed; proceeding despite at-risk hooks above.` for the operator's audit trail.

  Behavior on Windows: prints the same enumeration but does NOT prompt. Base-gator's `gatorize` sets local `core.hooksPath` on every repo it installs, so gatorized repos on Windows are immune to the global-hooksPath takeover; the warning is informational for the operator's awareness of non-gatorized-repo impact.

  `--yes`/`-y` argparse flag added to `activate_parser`. Legacy call sites that construct `args` via `types.SimpleNamespace` (test scaffolding) are handled with `getattr(args, "yes", False)` — argparse always supplies the attribute; the fallback keeps unit tests hermetic.

  Regression pins: `test_activate_atrisk.py::TestEnumerateAtRiskHooks` (6 tests — nonexistent repo, no .git, sample-files-ignored, active-hooks-detected, framework-markers, local-hookspath-immunity via subprocess.run monkeypatch); `TestWarnAboutAtRiskHooks` (8 tests — silent-when-clean, silent-when-empty, prints-warning, blocks-on-no, --yes-skips, windows-informational, local-hookspath-repos-not-at-risk, framework-marker-alone-triggers).

  **Non-changes (per §11 Non-changes list)**: base-gator's own local `core.hooksPath` install path is unchanged (Windows immunity flows from THAT install); `install_vendor_hooks` duplicate consolidation deferred post-MVP; session-block generation itself stays in POST_COMMIT_HOOK as TRANSITIONAL per plan D10 (post-MVP retirement arc).

  **Live verification (2026-08-08)**: hook templates verified via full-file rebuild against local fixture repos in `test_activate_atrisk.py`; string-shape assertions confirm `_PYTHON_RESOLVER`, `_GATOR_SCRIPT_RESOLVER`, `_MODE_LOOKUP` all present in each of the three deployed wrappers. On this dev machine (Windows), the enumeration path is informational — verified by running the test fixture directly, output shape matches §11 Change 1's specified prose.

- **! Base-gator `Gator-Machine-Id` trailer (2026-08-08 MVP Phase 6 — MVP COMPLETE).** The final phase closes the transcripts-first MVP by wiring base-gator's commit-msg phase to emit the machine identity that the Enterprise linkage pipeline consumes. Cross-referenced from the base-gator invariant in `scripts-cross-cutting.md::"Gator-Machine-Id trailer (Phase 6 ...)"` — that's where the shipped-code contract lives; this block is the Enterprise-side companion.

  **What ties this to Enterprise**: `enterprise/app/routes/ingest.py::ingest_commits` accepts the trailer bag from `transcripts pull`'s commit ingest, extracts `Gator-Machine-Id`, and populates `commits.machine_id`. The Phase 3 `strong_machine_repo_time` linkage basis matches that column against `transcript_sessions.machine_id` — without the trailer, machine-based linkage on that basis degrades to no-link for commits that happened to lack a snippet at capture time. Phase 6 fills that gap for every commit going forward.

  **Delta from base-gator**: only three lines of production code in `assemble_trailers` (read `_read_machine_id()` — already imported since Phase 2 — and conditionally append) plus the Enterprise-facing comment block explaining the consumer contract. Snippet schema already required `machine_id` per Phase 0 inventory — no schema change. All three copies of `gator-pre-commit.py` were updated to the same anchor (trio-copy contract note in `scripts-cross-cutting.md`).

  **Regression pins**: `tests/test_precommit_validation.py::TestMachineIdTrailer` (3 tests — emitted-when-present + omitted-when-file-missing + omitted-when-id-line-missing; hermetic via `Path.home` monkeypatch). Base-gator suite: pre-existing failures on `dev` are unrelated to Phase 6 (confirmed by stashing Phase 6 edits and re-running — same 6 failures on baseline).

  **MVP status: COMPLETE.** The Enterprise transcripts-first custody surface has all six phases landed: data model + BlobStore (Phase 1), ingest + read + Claude discovery + pull CLI (Phase 2), full linkage algorithm + orchestrator surface (Phase 3), operator query surface with SQL views + guide (Phase 4), hook seam cleanup (Phase 5), machine-id trailer (Phase 6). Post-MVP work (automatic sync, additional vendors, encryption at rest, weak-heuristic linkage, retention engine, web UI, session-block retirement) is enumerated in the plan §13 Phase 7 "Named for scope-honesty" list.

- **! Audit-surface Phase 2 hardening (2026-08-14, Commit I).** First code delivery of the 2026-08-14 Enterprise audit surface implementation plan. Three narrow hardening changes on top of the shipped Claude-first path — no new endpoints or CLI verbs in this commit (those are Commit J).

  **Q3 promotion — server-side `unlinked` filter** (`enterprise/app/routes/transcripts.py::list_transcripts`): new `unlinked: bool = Query(False)` param + HAVING clause on the outerjoin+group_by (`func.count(CommitTranscriptLink.id) == 0`). CLI `transcripts list --unlinked` now passes `?unlinked=true` to the server; the pre-existing client-side filter stays as defensive fallback for old-server compatibility. Complements the `unlinked_recent_transcripts` view (Migration 010) — both surface the same investigation queue, view is bounded to last 7 days, API endpoint is unbounded. Drift closure 2026-08-15 (enforcer-flagged): the `--unlinked` argparse help string still said "(client-side filter)" from the pre-promotion era — corrected to "(server-side filter)"; behavior unchanged.

  **Missing-`~/.gator/machine-id` fail-fast** (`enterprise/enterprise-cli/gator_enterprise_cli/commands/transcripts.py::_handle_pull`): early exit code 2 with an actionable error message pointing at `gator init` as the fix. Prior behavior silently uploaded with `machine_id="unknown"`, collapsing every affected transcript into a single synthesized machine row and breaking the `strong_machine_repo_time` linkage basis fleet-wide.

  **Missing-`~/.claude/projects/` warning** (`_handle_pull` + new `claude_root_path()` accessor in `transcripts_discovery.py`): informative warning when the Claude transcript root is absent, so operators see WHY zero transcripts were discovered instead of a silent zero-item pull. Non-fatal — operators may legitimately have no Claude transcripts.

  **Malformed-JSONL fatal-skip** (`transcripts_discovery.py::DiscoveredTranscript`): new `unreadable: bool` field set to `True` when `_parse_jsonl_metadata` catches `OSError` on file open. CLI `_handle_pull` skips these with a named-file diagnostic instead of attempting to upload a file it never actually read. Non-fatal parse issues (e.g. missing sessionId → filename fallback) keep `unreadable=False` because the file is still usable evidence.

  **Duplicate-ingest verification** — no code change. Existing upsert path at `enterprise/app/routes/ingest.py:536-575` returns `status="updated"` (not 500) on re-ingest; CLI's `_handle_pull` summary distinguishes `transcripts ingested (new)` from `transcripts updated`. Verified informative in Commit I audit; no fix needed.

  **Regression pins**:
  - New `TestListTranscripts::test_unlinked_filter_returns_only_zero_link_sessions` — seeds one linked + one unlinked transcript, asserts `?unlinked=true` returns only the unlinked.
  - New `TestListTranscripts::test_unlinked_filter_false_is_noop` — parity check.
  - New `TestPhase2Hardening` class in `test_transcripts_discovery.py` (5 tests): `unreadable` set on OSError, false on degraded-parse, false on clean-parse; `claude_root_path()` returns default; `claude_root_path()` honors env override.
  - Test suite at commit time: enterprise 253 pass + 1 skip (was 245); base 770 pass + 2 pre-existing xfails (unchanged). No regressions.

  **What Commit J adds next**: the three new Phase-1-gap surfaces per the audit-surface artifact — Q2 `commits list --repo`, Q4 `commits provenance <sha>`, Q5 `repos transcripts <id>`. Commit K adds docs + smoke-test protocol.

- **! Audit-surface Phase 2 Commit J (2026-08-14) — three new audit-question surfaces.** Second code delivery of the 2026-08-14 Enterprise audit surface implementation plan. Adds the three Phase-1-artifact DATA-BUT-NO-SURFACE surfaces (Q2, Q4, Q5); all classifications flip to EXISTS post-commit for Claude/Codex; Q5's Gemini cross-bucket answer-completeness caveat (Migration 011 dependency) stays as documented in Q5's Notes column.

  **Q4 — `commits provenance <sha>`** (`enterprise/app/routes/commits.py` — new file; `enterprise/enterprise-cli/gator_enterprise_cli/commands/commits.py::_handle_provenance`): new endpoint `GET /api/v1/commits/{sha}/provenance?repo_canonical_id=<id>` returning commit-side provenance fields (commit_sha, repo_identifier, author_identity, committed_at, machine_id, machine_label, snippet_agent, transcript_session_id) populated during commit reconciliation from Migration 008's snippet fields. 7-40-char SHA prefix matching mirrors `/commits/{sha}/transcripts`. Multi-match returns all rows in the `commits` array; CLI prints a compact table + `--repo` disambiguation hint when >1 match. Single-match prints full key/value detail via `print_kv`. Ratified as **R3 = (i)** at Phase 1 exit — dedicated verb (not folding into `commits transcripts`).

  **Q2 — `commits list --repo <id>`** (`enterprise/app/routes/repos.py::list_repo_commits`; `commands/commits.py::_handle_list`): new endpoint `GET /api/v1/repos/{repo_canonical_id:path}/commits?limit=&offset=` returning per-commit rows shaped like Migration 010's `commits_with_transcript_coverage` view (commit metadata + linked_transcript_count + best_linkage_basis_ranked). Route-level composition of the same join the view exposes rather than direct `SELECT ... FROM commits_with_transcript_coverage` — keeps the SQLite in-memory test harness working without recreating the view at `Base.metadata.create_all` time. Python-side grouping (dict) keeps SQL portable. New module-level `_LINKAGE_BASIS_RANK` constant kept in sync with Migration 010's CASE ordering. Ratified as **R4 = (a)** at Phase 1 exit — flag-style repo scoping composes better than `repos commits <id>`.

  **Q5 — `repos transcripts <id>`** (`enterprise/app/routes/repos.py::list_repo_transcripts`; `commands/repos.py::_handle_transcripts`): new endpoint `GET /api/v1/repos/{repo_canonical_id:path}/transcripts?vendor=&since=&limit=&offset=` doing the 3-way join `TranscriptSession ⨝ CommitTranscriptLink ⨝ Commit WHERE Commit.repo_identifier = ?` with DISTINCT on TranscriptSession (dedupes when one session links to N commits in the same repo). Ordered by `started_at DESC`. Ratified as **R5 = (b)** — symmetric with `commits transcripts <sha>`. **Gemini answer-completeness caveat** (per Phase 1 artifact §3 Q5 Notes): pre-Migration-011, two Gemini transcript files with same raw `vendor_session_id` collide at ingest; this surface returns honest partial data for Gemini until Phase 4 lands parent plan §10 item 6.

  **Path-converter fix**: FastAPI treats slashes in path parameters as separators by default, so `/repos/local/x/commits` would match `repo_canonical_id=local` and 404 on the tail. Both new `/repos/*` routes use `{repo_canonical_id:path}` converter to allow slashes. Verified via 9 initial test failures pre-fix + all-green post-fix.

  **New router registration**: `enterprise/app/main.py` gains `from app.routes.commits import router as commits_router` + `app.include_router(commits_router, prefix="/api/v1", dependencies=_auth_deps)`. Follows the established pattern (10th router registered).

  **Regression pins** (16 new tests in `enterprise/tests/test_ingest_routes.py`):
  - `TestCommitProvenance` (7 tests): full-SHA return, prefix return, ambiguous-prefix multi-match, `repo_canonical_id` narrowing, empty-for-no-match, short-prefix-rejected-400, nulls-when-snippet-absent.
  - `TestRepoCommitsList` (4 tests): link-count aggregation with best-basis-ranked, recent-first ordering, repo scoping, pagination + total_matched.
  - `TestRepoTranscriptsList` (5 tests): 3-way-join surfaces transcripts, repo scoping, DISTINCT dedupe when one transcript links N commits, vendor filter, empty-for-repo-with-no-activity.
  - Test suite at commit time: enterprise **269 pass + 1 skip** (was 253 + 1 skip pre-commit — 16 net-new); base 770 pass + 2 pre-existing xfails (unchanged). Zero regressions.

  **What Commit K adds next**: `enterprise/docs/` audit for retired-behavior banners + operator guide refresh matching current commands (including the 3 new Q2/Q4/Q5 verbs from this commit + Q3 server-side promotion from Commit I) + smoke-test protocol artifact for Architect to run against the fresh deliverables.

- **! Audit-surface Phase 2 Commit K (2026-08-14) — docs + smoke protocol + Phase 1 artifact rollforward.** Third and final code delivery of the 2026-08-14 Enterprise audit surface implementation plan Phase 2 (Commits I + J + K). No new code paths — pure documentation + operator-facing deliverables to complete Phase 2's exit criteria per parent plan §4.

  **`enterprise/docs/enterprise-blueprint.html` historical banner**: pre-transcripts-first-MVP artifact from 2026-07-11 (E1-E6 evidence-in-Git architecture) gained a top-of-file HISTORICAL warning banner pointing at the current transcripts-first ADR + MVP plan + audit-surface plan + relevant migrations. Follows the same pattern as `enterprise/docs/session-block-schema-v2.md` (banner-marked 2026-08-08). No content rewrite — architectural context retained; reader is now correctly oriented on what's superseded vs current.

  **Vault deliverables (gitignored, not in this commit)**:
  - `.gator/vault/artifacts/2026-08-14-audit-surface-phase-2-smoke-test-protocol.md` — 9-test protocol (T1-T9) for Architect to run against a real local Enterprise stack. Covers all 6 Phase 2 behavior changes (T1 missing-machine-id fail-fast, T2 missing-Claude-root warning, T3 unreadable-file skip, T4 Q3 server-side unlinked filter, T5-T6 Q4 provenance single-match + ambiguous-prefix, T7 Q2 commits list, T8 Q5 repos transcripts, T9 duplicate-ingest verification). Same shape as `2026-08-10-smoke-test-run-1.md` for structural comparability. Includes prerequisites + cleanup + failure signals per test.
  - `.gator/vault/artifacts/2026-08-14-enterprise-audit-question-surface.md` bumped to **r4** — Q2/Q4/Q5 rows rolled forward to reflect Commit J shipping (all three flipped DATA-BUT-NO-SURFACE → EXISTS with the shipped CLI/API paths cited). §4 summary count table now shows post-Commit-J state (5 EXISTS, 0 DATA-BUT-NO-SURFACE) alongside Phase-1-exit historical state for ratification traceability. Q5 Gemini answer-completeness cross-bucket concern preserved per r10 bucket-discipline contract.
  - `.gator/vault/artifacts/enterprise-transcripts-mvp-operator-guide.md` refreshed with a new §10 "Audit-question surface" section mapping Q1-Q5 to CLI/endpoint pairs, Gemini caveat on Q5, and Phase 2 error-message hardening summary. Prior §0-§9 content unchanged.

  **Phase 2 exit criteria per parent plan §4** — verification:
  - Every Phase 1 EXISTS-status question returns a correct answer: Q1 unchanged; Q3 promoted server-side by Commit I (T4 in smoke protocol verifies).
  - Every Phase 1 DATA-BUT-NO-SURFACE question given a CLI+API surface: Q2 (T7), Q4 (T5+T6), Q5 (T8) all shipped in Commit J.
  - Named failure modes surface as informative errors: T1 (machine-id), T2 (Claude-root), T3 (unreadable) all cover the failure-mode audit from parent plan §4.
  - Operator guide walkthrough executable end-to-end: refreshed with §10; existing §0-§9 golden path still accurate.
  - No test regressions: enterprise 269 pass + 1 skip (was 253 pre-Commit-I), base 770 pass + 2 pre-existing xfails (unchanged).
  - Fresh smoke-test run artifact: protocol produced (Architect executes to fill in Run 1 results).

  **Phase 2 status: COMPLETE.** Ready for Phase 3 (Enterprise-side Codex adapter) whenever Architect fires; §10 items 1-7 in the parent plan stay ratified as they were at Phase 1 exit.

- **! Audit-surface Phase 3 Commit L (2026-08-15) — Enterprise-side Codex adapter.** First code delivery of Phase 3 in the 2026-08-14 Enterprise audit surface implementation plan. Widens transcript discovery from Claude-only to Claude + Codex CLI (OpenAI); Q1-Q5 audit-question surfaces begin returning Codex-side rows on the next `transcripts pull --vendor codex`. Extend-in-place decision: `enterprise/enterprise-cli/gator_enterprise_cli/transcripts_discovery.py` was already vendor-dispatched via `_VENDOR_HANDLERS` + `_VENDOR_ALIASES` — a separate `codex_discovery.py` module would have duplicated that dispatch machinery. Single-commit target per parent plan §5 ("1-2 commits").

  **Codex parser** (`transcripts_discovery.py::_parse_codex_jsonl_metadata`): reads `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` line-by-line. Extracts `vendor_session_id` from the first `session_meta.payload.id`, `workspace_hint` from `session_meta.payload.cwd`, `model` from the first `turn_context.payload.model`, `started_at`/`ended_at` from min/max of top-level `timestamp` across all events, `turn_count` from `response_item` events with `payload.role in (user, assistant)`. If `session_meta` is absent, falls back to the last hyphen-separated segment of the filename stem as `vendor_session_id` (same degraded-parse semantics as the Claude parser: parse_error set, `unreadable=False`, file still uploaded as usable evidence). Fatal-parse (OSError on open) sets `unreadable=True` — CLI skips with a named-file diagnostic, matching the Claude Phase 2 hardening contract.

  **Vendor slug = `openai`** (canonical form, per the Enterprise `TranscriptSession.vendor` model contract). CLI accepts both `codex` (product name) and `openai` (canonical) via `_VENDOR_ALIASES["openai"] → "codex"`.

  **Codex root** (`_default_codex_root` + `codex_root_path()` accessor): `~/.codex/sessions/` by default; override via `CODEX_TRANSCRIPTS_ROOT` env var (test-only path, parallel to `CLAUDE_TRANSCRIPTS_ROOT`).

  **Directory layout**: unlike Claude's flat `~/.claude/projects/<hash>/` layout, Codex uses per-day directories `YYYY/MM/DD/`. Discovery uses `Path.rglob("rollout-*.jsonl")` — the filename prefix ensures accidental `.jsonl` drops in the tree are not picked up. Files are sorted by path, which orders by date + timestamp naturally because Codex filenames begin with the ISO timestamp.

  **CLI wire-up** (`commands/transcripts.py::_handle_pull`): `--vendor` choices extended `[claude, anthropic, all]` → `[claude, anthropic, codex, openai, all]`. `--vendor all` still resolves to `claude` only — iteration across all installed vendors is deferred to Phase 4+ per parent plan §5. Codex-root missing-warning added (parallel to Commit I's Claude-root warning): fires when `vendor in ("codex", "openai")` and the resolved root directory is absent — non-fatal (operator may legitimately have never used Codex CLI).

  **Regression pins** (25 new tests in `enterprise/tests/test_transcripts_discovery.py`):
  - `TestParseSingleCodexTranscript` (8 tests): session_meta.id extraction, model from turn_context, session_meta.cwd precedence over turn_context.cwd, turn_count excludes non-user/assistant response_items + event_msg, started/ended span across all events, filename UUID fallback when session_meta absent, malformed-line survival, unreadable-flag on OSError.
  - `TestDiscoverCodex` (5 tests): yields every rollout, `since=` filters older rollouts, empty result when root missing, empty result when root empty, ignores non-`rollout-*.jsonl` files.
  - `TestCodexRootAccessor` (2 tests): default = `~/.codex/sessions`, env override honored.
  - `TestVendorDispatch::test_codex_alias_resolves` — both `codex` and `openai` dispatch to the Codex handler.
  - Test suite at commit time: enterprise **285 pass + 1 skip** (was 269 + 1 skip pre-commit — 16 net-new counting fixture-derived variants; total delta +25 assertions across the new classes). No regressions.

  **What Phase 4 adds next** (per parent plan §6): Gemini adapter — same shape, requires Migration 011 for widened `vendor_session_id` uniqueness (Gemini reuses the same raw id across duplicate-turn edits, colliding at DB + blob-key layer). Retiring the base-Gator `extract-codex-sessions.py` + `extract-gemini-sessions.py` scripts closes the substrate-parity gap. **→ Gemini adapter landed 2026-08-15 as Commit M (next block); the base-side extractor retirement landed 2026-08-16 in the session-cleanup final sweep** (with `gator-session-common.py` — see [`scripts-session-archaeology`](scripts-session-archaeology.md)).

- **! Audit-surface Phase 4 Commit M (2026-08-15) — Enterprise-side Gemini adapter + Migration 011 session qualifier + β fan-out contract.** Delivers parent plan §6 under two Architect ratifications: §10 item 6 = **(b) Migration 011** (server-side substrate widening) and §10 item 7 = **(β) multi-link fan-out** (ratified at Phase 4 kickoff, 2026-08-15). Gemini is the only known vendor whose storage can put the same internal `sessionId` in two different files; pre-011 the second ingest silently upserted over the first (evidence loss at DB + blob-key layers).

  **Migration 011** (`enterprise/migrations/versions/011_transcript_session_qualifier.py`): adds `session_qualifier VARCHAR(255) NOT NULL DEFAULT ''` to `transcript_sessions`; drops + recreates `uq_transcript_sessions_org_machine_vendor_session` as the 5-column constraint. TRIPWIRE — the column is deliberately NOT NULL despite the plan prose saying "nullable": Postgres unique constraints never treat NULLs as colliding, so a nullable qualifier would break upsert idempotency for EVERY vendor. TRIPWIRE — sync obligation triangle: this constraint shape ⟷ `ingest.py::ingest_transcript` upsert lookup (matches all 5 columns) ⟷ `blob_store.py::build_blob_key` (appends `__{qualifier}` when non-empty). Change any one, revisit all three.

  **Gemini parser** (`transcripts_discovery.py::_parse_gemini_json_metadata`): single-JSON files (NOT JSONL) at `~/.gemini/tmp/<project>/chats/session-*.json` — `{sessionId, projectHash, startTime, lastUpdated, messages, kind}`. `vendor_session_id` = internal `sessionId` (canonical; filename stem fallback with parse_error, matching Claude/Codex degraded-parse contract); whole-file JSON parse failure is degraded-parse (raw bytes still evidence), only OSError sets `unreadable=True`. `model` from first `gemini`-type message; `turn_count` counts `user`+`gemini` messages; `workspace_hint` reverse-maps the project dirname through `~/.gemini/projects.json` (`{workspace_path: slug}`, read via `_gemini_projects_file(root)` = `root.parent/projects.json`), falling back to the dirname. **`session_qualifier` = sha256(source_path)[:16]** — the `make_row_key()` insight from base's retiring `gator-session-common.py`, minus the session-id component (already its own column). Non-Gemini records carry `""`.

  **Vendor slug = `google`** (canonical). `_VENDOR_ALIASES["google"] → "gemini"`; `--vendor` choices now `[claude, anthropic, codex, openai, gemini, google, all]`; Gemini-root missing-warning branch parallel to Claude/Codex; `GEMINI_TRANSCRIPTS_ROOT` env override.

  **β fan-out** (`ingest.py::_run_linkage` basis 2): the snippet carries only the RAW vendor session id, so under duplicate-raw-ID rows each row's ingest matches the same commits — one snippet-basis link per row is intentional (honest "all matching transcripts" answer for auditors, Q1 may return N>1). Ambiguity is signaled via confidence AND metadata: when 2+ sibling rows share `(org, machine, vendor, vendor_session_id)`, new snippet-basis links get `medium` (not `high`) plus `linkage_metadata.raw_id_ambiguous_across: N`, and previously-created snippet-basis links on sibling rows are retroactively CONVERGED to the same confidence + count via per-row read-modify-write (2026-08-16 whiteboard Finding 1 fix; the original Commit M bulk UPDATE touched confidence only, leaving the first-ingested sibling's link without the ambiguity marker — order-dependent audit signal). The convergence loop deliberately has NO already-medium skip filter: re-stamping on every ambiguous ingest keeps `raw_id_ambiguous_across` fresh when a third sibling arrives. TRIPWIRE — the JSON `linkage_metadata` column must be reassigned whole (`{**old, ...}`), not mutated in place, or SQLAlchemy won't dirty-track the change. TRIPWIRE — the basis-3 suppression set (`existing_high_conf`) keys on BASIS membership, not confidence, so a medium snippet link still suppresses redundant `strong_machine_repo_time` noise for the same commit — intended.

  **Ingest payload**: `TranscriptIngestBody.session_qualifier: str = ""` (optional, additive — pre-011 clients omit it and behave identically). Upsert lookup + row creation + `build_blob_key` all thread it through.

  **Regression pins** (25 new tests in `enterprise/tests/test_transcripts_discovery_gemini.py`): `TestParseSingleGeminiTranscript` (6 — metadata extraction, stem fallback, malformed-JSON degraded-parse, OSError unreadable, projects.json reverse-map + dirname fallback), `TestGeminiQualifier` (3 — 16-hex shape, distinct-per-file under same raw id, empty for non-Gemini vendors), `TestDiscoverGemini` (6 — cross-project yield, since-filter, no-timestamps-always-yielded, missing root, non-session-file exclusion, projects.json-from-root-parent), `TestGeminiRootAccessor` (2), `TestGeminiVendorDispatch` (1), `TestBuildBlobKeyQualifier` (2 — appended when present, pre-011 shape preserved when empty), `TestDuplicateSessionIdAcrossFiles` (6 — the §6 three-assertion contract: 2 rows / 2 blob keys / 2 medium links order-independent with metadata parity, third-sibling count refresh (`raw_id_ambiguous_across` re-stamped to 3 on all links; added 2026-08-16 with the Finding 1 convergence fix), same-file re-ingest upsert, and non-duplicate-stays-high with no ambiguity marker). One pre-existing pin updated: `TestVendorDispatch::test_unknown_vendor_raises` probe changed `gemini` → `not-a-vendor`. Suite at commit time: enterprise **310 pass + 1 skip** (was 285 + 1); base 770 pass + 2 xfails unchanged (packaging tests verified separately under the base interpreter — they fail spuriously under `.venv-enterprise-local` because that venv ships `gator_enterprise_cli`). Migration 011 applied to local Postgres, `alembic_version` head = 011.

- **! Runtime-split Phase 5a (2026-08-21) — the policy channel's state half (Migration 012).** E3's `Policy`/`PolicyVersion` already own content-addressed policy versioning; 5a adds WHAT-IS-IN-FORCE-WHERE tracking. New model `machine_policy_states` (`app/models/machine_policy_state.py`): one CURRENT row per `(org, machine_id, repo_identifier, policy_id)` — reports upsert in place, history is Git's job via the repo-side policy pin. `repo_identifier VARCHAR(512) NOT NULL DEFAULT ''` — empty = machine-level scope; NOT NULL per the Migration 011 lesson (NULLs never collide in Postgres unique constraints). `machine_id` plain varchar (the `commits.machine_id` precedent — machines may report before key registration). `content_hash` denormalized from the version row for join-free drift comparison. New routes (`app/routes/policy_state.py`, registered in main.py): `POST /api/v1/policy-state/report` (per-entry outcomes, never batch-500; response carries `in_sync` per entry), `GET /api/v1/policy-state` (fleet state + in_sync flags, filters machine_id/repo/policy), `GET /api/v1/policy-state/drift` (the one-query answer; includes applied-but-retired policies; REPORT-BASED — never-reported machines are absent, not in-sync; missing-coverage detection vs machine_keys is a documented follow-on). TRIPWIRE — the report upsert matches exactly the four unique-constraint columns; constraint-shape changes must change that lookup in the same commit. **Killer-property pin**: `test_activation_change_flips_drift_without_new_reports` — activating a new version instantly reclassifies every reported machine as drifted, zero re-reports. **Pre-existing latent limitation fixed en route**: `PolicyVersion`'s one-active partial unique index used only `postgresql_where`, which SQLite create_all IGNORES → degraded to full-unique on policy_id → any second version 500'd in the test environment (no prior test created two versions); `sqlite_where` added, production Postgres unchanged. Suite: enterprise **330 pass + 1 skip** (+15 in `test_policy_state.py`); Migration 012 applied to local Postgres, head=012.

- **! Runtime-split Phase 5b (2026-08-22) — policy channel client half + Git proof surface.** New route `GET /api/v1/policies/active` (in `routes/policies.py`, DECLARED BEFORE `/{policy_id}` — ROUTE-ORDER TRIPWIRE: FastAPI matches in declaration order and `parse_uuid` would 400 on the literal "active"; pinned by `test_active_route_not_shadowed_by_policy_id`): all active-status policies with activated versions INCLUDING content — the one-call pull payload; active policies without an activated version are skipped. Client `commands/policies.py` gains `pull` (fetch → land `~/.gator/enterprise/org-policies.json` → report machine-level state → inside a governed repo also write **`.gator/policy-pin.json`** [schema `gator-policy-pin-v1`, contract at `contracts/schemas/`; hashes ONLY, never content — the hash is the proof, the control plane holds the content] + report repo-scoped state with `--repo-id` override, default `local/<dirname>`) and `drift` (fleet table over `GET /policy-state/drift`). **Latent E3 bug fixed en route**: `services/policy.py::activate_version` set the new version active and deactivated the old in one flush — SQLAlchemy orders same-table UPDATEs by identity (arbitrary with UUID PKs) and the one-active partial unique index is checked PER-STATEMENT on Postgres and SQLite alike → nondeterministic IntegrityError on activation (intermittent test failure was the tell). Fix: `db.flush()` after the deactivation, before activating. Suite: enterprise **335 pass + 2 skip** (+5: active-endpoint 3 + pin-writer 3, activation flake fixed); contracts 53 pass (+8 policy-pin).

- **! Runtime-split Phase 3b (2026-08-19) — machine vendor hooks retargeted + Phase-0 finding F1 fixed.** `gator_enterprise_cli/vendor_hooks.py::HOOK_TEMPLATES` (all three vendors) now command `gator hook session-open` / `gator hook session-start` — routing through the base CLI's dispatcher. This fixes F1: the previous commands used v1 paths (`.gator/scripts/...`) that have been dead on v2 repos since the `.includes` split — machine-hook session registration was silently no-op there (plausibly related to the 2026-08-16 snippet-identity registry-miss inbox item). `_merge_hooks`' Gator-managed predicate is now `_is_gator_hook_command()` (both-generations matching; part of the FOUR-copy sync obligation documented in `scripts-cross-cutting.md`). **Whiteboard 2026-08-19 hardening**: `install_enterprise_vendor_hooks` now resolves the gator launcher via `shutil.which` at install time and `_absolutize_commands()` rewrites bare `gator hook <name>` to `"<abs-launcher>" hook <name>` — machine-level settings are machine-scoped so absolute paths are safe, and the PATH assumption disappears entirely (covers GUI-launched vendor CLIs whose PATH lacks pipx shims). Unresolvable launcher → bare command kept. The absolutized shape is the predicate's third recognized form. Pins: `TestGatorCommandPredicate` (4, incl. migrate-in-place-never-duplicate) + `TestAbsolutizeCommands` (4 — noop-on-None, absolutize+still-recognized, no-template-mutation, user-commands-untouched).

- `src/gator_command/cli.py::COMMANDS` — dispatch entry
  `"enterprise": ("gator-enterprise.py", ...)`.

## Calls out (`→`)

- Attempts `import gator_enterprise_cli` (optional; missing is expected
  in a bare base install and handled by `_unavailable_notice`).
- When present, imports `gator_enterprise_cli.main.main` and delegates.
- `gator_core.ensure_utf8_stdout` — via `try/except ImportError` so the
  script is invocable standalone (matching other `gator-*.py` scripts).

## Growth path

**Post-Phase 4e (the current state).** The initial public monorepo
cutover ships:
- Base wheel with the thin dispatcher (no real Enterprise behavior).
- Full `enterprise/` tree under Apache-2.0 for contributors to work on.
- Enterprise integration polish is a follow-on: making the enterprise-cli
  package installable cleanly, wiring an
  `[enterprise-cli] = ["gator-command[enterprise-cli] = ..."]` extra so
  operators get a single `pipx install "gator-command[enterprise-cli]"`
  path, resolving the httpx/urllib client duplication decisively,
  polishing envelope encryption (`app/routes/crypto.py` + client-side
  AES-256-GCM/RSA-OAEP) with a coherent key-management UX, and getting
  the enterprise test suite green against a real Postgres.

**Migrations 001-008** are now all tracked (previously only 008 was
tracked as the "schema commitment" marker). `alembic upgrade head`
against a fresh database works from the enterprise/ tree.

## Connections

→ [Cross-Cutting](scripts-cross-cutting.md) — CLI dispatch pattern
→ [Contracts](contracts.md) — `.gator/enterprise.json` marker; presence
  detection semantics (`gator_core.is_enterprise_active`).
→ Thread: `../threads/gator-enterprise-cli.md` — the direction that
  shaped Decisions A + C.
→ Plan: `../artifacts/2026-07-21-monorepo-convergence-implementation-plan.md`
  Phase 3 packaging boundary + Phase 4 selective port + Phase 4e
  consolidation.
→ Cutover: `../artifacts/2026-08-02-monorepo-cutover-plan-and-tree-map.md`
  — how `enterprise/` is treated at cutover.
