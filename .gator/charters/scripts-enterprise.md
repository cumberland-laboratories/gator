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
  machines/activate/sync/repo`) than the dispatcher advertises. The
  overlap is currently `sync` only.

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
  10 tests for advertised-but-unmapped verbs (each gets the gap
  notice), 1 for the `sync` overlap (delegates cleanly), 3 for
  Finding-1 propagation (SystemExit(1)/SystemExit(2)/SystemExit(None)
  from mapped verbs surface as rc=1/rc=2/rc=0 without gap-notice
  translation).

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

## Called by (`←`)

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
