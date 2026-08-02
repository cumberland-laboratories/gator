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
