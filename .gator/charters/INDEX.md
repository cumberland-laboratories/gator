# Charter Index

Charter dispatch table for the **monorepo `gator`**. When code files in a row change, the pre-commit hook requires at least one of the listed charter files to be updated in the same commit.

Post-monorepo-cutover note: `scripts-command-post.md` was Cat 3-excluded during Phase 3b-3-B (source-repo-specific content — command-post scripts, deploy pipeline, memex) and does not exist in this tree. INDEX rows that previously routed there now route to `scripts-cross-cutting.md` alone; the retired scripts (memex, deploy_*, gator-deploy, gator-enforce) that only lived under that charter are removed from the index because they're not in the monorepo either. Vault preserves the source-repo charter at `.gator/vault/gator-command-archive/charters/scripts-command-post.md` for reference.

| If you're changing... | Read these charters |
|---|---|
| `scripts/release-individual.sh`, `scripts/test-install-cycle.sh`, `scripts/monorepo-bootstrap.py`, `scripts/monorepo-validate.py` | [Cross-Cutting](scripts-cross-cutting.md) |
| `gator_core.py`, `gator-machine-id.py`, `gator_remote.py`, `gator-version.py` | [Core Library](scripts-core-library.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-fleet-report.py`, `gator-fleet-intel.py`, `gator-drift.py`, `gator-audit.py`, `gator-audit-renderers.py` | [Fleet Intelligence](scripts-fleet-intelligence.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-session-aggregator.py`, `gator_session_reader.py` | [Session Archaeology](scripts-session-archaeology.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gatorize.py`, `gatorize/*.py` | [Installer and Boot](scripts-installer.md) |
| `gator-init.py`, `gator-update.py`, `gator-hook.py`, `gator-charter-lint.py`, `gator-charter-draft.py`, `gator-charter-verify.py`, `gator-policy-status.py`, `gator-pulse.py` | [Repo Lifecycle](scripts-repo-lifecycle.md) |
| `.gator/.includes/scripts/enforcer-review.py`, `.gator/.includes/scripts/gator-pre-commit.py`, `.gator/.includes/scripts/precommit_lint.py`, `.gator/.includes/scripts/precommit_charter.py`, `.gator/.includes/scripts/precommit_session.py`, `.gator/.includes/scripts/gator-approve.py` | [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`, `src/gator_command/templates/gator-starter/scripts/precommit_lint.py`, `src/gator_command/templates/gator-starter/scripts/precommit_charter.py`, `src/gator_command/templates/gator-starter/scripts/precommit_session.py`, `src/gator_command/templates/gator-starter/scripts/enforcer-review.py` | [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-session-start.py`, `src/gator_command/templates/gator-starter/scripts/gator-session-start.py` | [Installer and Boot](scripts-installer.md) |
| `gator-repo-status.py`, `gator-dashboard.py`, `dashboard/helpers.py`, `dashboard/updates.py`, `dashboard/snapshot.py`, `dashboard/data.py` | [Fleet Intelligence](scripts-fleet-intelligence.md) · [Dashboard](scripts-dashboard.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator_runtime.py` | [Core Library](scripts-core-library.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/loop/*.py`, `src/gator_command/scripts/gator-loop.py` | [Gator Loop](scripts-loop.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator-enterprise.py` (thin dispatcher only, post-Phase 4e) | [Enterprise CLI](scripts-enterprise.md) · [Contracts](contracts.md) |
| `enterprise/enterprise-cli/**` (gator_enterprise_cli package: credentials.py, vendor_hooks.py, client.py, main.py, commands/*), `enterprise/app/**` (FastAPI service), `enterprise/migrations/versions/*.py` (Alembic 001-009 chain), `enterprise/tests/**` | [Enterprise CLI](scripts-enterprise.md) — Phase 4e consolidation; Migration 009 (2026-08-08) adds transcript-custody tables per transcripts-first MVP |
| `src/gator_command/scripts/gator-state.py` | [Managed State](scripts-managed-state.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator-kill.py` | [Dashboard](scripts-dashboard.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator_layout.py` | [Layout Resolver](scripts-layout.md) |
| `src/gator_command/cli.py`, `src/gator_command/__init__.py`, `pyproject.toml` | [Cross-Cutting](scripts-cross-cutting.md) |
| `contracts/**` (schemas, reference docs, compatibility tests) | [Contracts](contracts.md) |
| `.github/workflows/*.yml` (source-ci, future release-candidate, promote-to-pypi) | [Release Pipeline](release-pipeline.md) |
| `LICENSE`, `NOTICE`, `CONTRIBUTING.md` | [Cross-Cutting](scripts-cross-cutting.md) — license posture (Apache 2.0), provenance, contributor obligations |
