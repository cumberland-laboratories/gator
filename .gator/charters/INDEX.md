# Charter Index

This index is the authoritative script-charter dispatch table for the **source `gator-command` repo**.
It covers the scripts that run this command post, prepare the public `gator` deploy, and define shipped governance behavior.

| If you're changing... | Read these charters |
|---|---|
| `legacy/memex.py`, `legacy/memex_state.py`, `legacy/memex_formatters.py`, `legacy/spawn.py`, `gator-deploy.py`, `deploy_files.py`, `deploy_builders.py`, `deploy_changelog.py`, `gator-enforce.py`, `scripts/release-individual.sh`, `scripts/test-install-cycle.sh`, `scripts/monorepo-bootstrap.py`, `scripts/monorepo-validate.py` | [Command-Post Scripts](scripts-command-post.md) |
| `gator_core.py`, `gator-session-common.py`, `gator-machine-id.py`, `gator_remote.py`, `gator-version.py` | [Core Library](scripts-core-library.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-fleet-report.py`, `gator-fleet-intel.py`, `gator-drift.py`, `gator-audit.py`, `gator-audit-renderers.py` | [Fleet Intelligence](scripts-fleet-intelligence.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `extract-claude-sessions.py`, `extract-codex-sessions.py`, `extract-gemini-sessions.py`, `gator-sessions.py`, `gator-session-sink.py`, `gator-session-aggregator.py`, `gator-session-block.py` | [Session Archaeology](scripts-session-archaeology.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gatorize.py`, `gatorize/*.py` | [Installer and Boot](scripts-installer.md) |
| `gator-init.py`, `gator-update.py`, `gator-charter-lint.py`, `gator-charter-draft.py`, `gator-charter-verify.py`, `gator-policy-status.py`, `gator-pulse.py` | [Repo Lifecycle](scripts-repo-lifecycle.md) |
| `legacy/generate_wiki.py`, `legacy/generate_markdown.py`, `legacy/graph_health.py`, `legacy/crawler.py`, `legacy/memex-lint.py`, `legacy/memex-lint.sh` | [Graph and Wiki](scripts-graph-wiki.md) (legacy) |
| `.gator/scripts/enforcer-review.py`, `.gator/scripts/gator-pre-commit.py`, `.gator/scripts/precommit_lint.py`, `.gator/scripts/precommit_charter.py`, `.gator/scripts/precommit_session.py`, `.gator/scripts/gator-approve.py` | [Command-Post Scripts](scripts-command-post.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`, `src/gator_command/templates/gator-starter/scripts/precommit_lint.py`, `src/gator_command/templates/gator-starter/scripts/precommit_charter.py`, `src/gator_command/templates/gator-starter/scripts/precommit_session.py`, `src/gator_command/templates/gator-starter/scripts/enforcer-review.py` | [Command-Post Scripts](scripts-command-post.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-session-start.py`, `src/gator_command/templates/gator-starter/scripts/gator-session-start.py` | [Installer and Boot](scripts-installer.md) |
| `gator-repo-status.py`, `gator-dashboard.py`, `dashboard/helpers.py`, `dashboard/updates.py`, `dashboard/snapshot.py`, `dashboard/data.py` | [Fleet Intelligence](scripts-fleet-intelligence.md) · [Dashboard](scripts-dashboard.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator_runtime.py` | [Core Library](scripts-core-library.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/loop/*.py`, `src/gator_command/scripts/gator-loop.py` | [Gator Loop](scripts-loop.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator-enterprise.py` (thin dispatcher only, post-Phase 4e) | [Enterprise CLI](scripts-enterprise.md) · [Contracts](contracts.md) |
| `enterprise/enterprise-cli/**` (gator_enterprise_cli package: credentials.py, vendor_hooks.py, client.py, main.py, commands/*), `enterprise/app/**` (FastAPI service), `enterprise/migrations/versions/*.py` (Alembic 001-008 chain), `enterprise/tests/**` | [Enterprise CLI](scripts-enterprise.md) — Phase 4e consolidation |
| `src/gator_command/scripts/gator-state.py` | [Managed State](scripts-managed-state.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator-kill.py` | [Dashboard](scripts-dashboard.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator_layout.py` | [Layout Resolver](scripts-layout.md) |
| `src/gator_command/cli.py`, `src/gator_command/__init__.py`, `pyproject.toml` | [Cross-Cutting](scripts-cross-cutting.md) |
| `contracts/**` (schemas, reference docs, compatibility tests) | [Contracts](contracts.md) |
| `.github/workflows/*.yml` (source-ci, future release-candidate, promote-to-pypi) | [Release Pipeline](release-pipeline.md) |
| `LICENSE`, `NOTICE`, `CONTRIBUTING.md` | [Cross-Cutting](scripts-cross-cutting.md) — license posture (Apache 2.0), provenance, contributor obligations |
