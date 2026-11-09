# Charter Index

Authoritative code-path-to-charter routing for the `gator` monorepo. Read [Cross-Cutting](scripts-cross-cutting.md) first, then only the matching domain rows. Follow `## Connections` when a change crosses a boundary.

| If you're changing... | Read these charters |
|---|---|
| `src/gator_command/cli.py`, `src/gator_command/__init__.py`, `pyproject.toml` | [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator_core.py`, `gator_runtime.py`, `gator_remote.py`, `gator-machine-id.py`, `gator-version.py`, starter `gator_core.py` and `gator-version.py` | [Core Library](scripts-core-library.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-fleet-report.py`, `gator-fleet-intel.py`, `gator-drift.py` | [Fleet Status and Drift](scripts-fleet-intelligence.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-audit.py`, `gator-audit-renderers.py`, `gator-repo-status.py` | [Audit and Repo Intelligence](scripts-audit-intelligence.md) · [Session Archaeology](scripts-session-archaeology.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-session-aggregator.py`, `gator_session_reader.py` | [Session Archaeology](scripts-session-archaeology.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gatorize.py`, `src/gator_command/scripts/gatorize/**` | [Gatorize Installer](scripts-installer.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| starter `gator-session-start.py`, `gator-session-open.py`, `gator_diagnostics.py`, and synchronized bundled copies | [Vendor Session Capture](scripts-session-capture.md) · [Session Boot and Hook Dispatch](scripts-repo-lifecycle.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-init.py`, `gator-explain.py`, `gator-hook.py`, starter `gator-init.py` | [Session Boot and Hook Dispatch](scripts-repo-lifecycle.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-update.py`, `gator-policy-status.py`, starter `gator-update.py` | [Repo Update and Policy Sync](scripts-repo-update.md) · [Layout Resolver](scripts-layout.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-charter-lint.py`, `gator-charter-draft.py`, `gator-charter-verify.py`, `charter_covers.py`, `charter_significance.py`, `charter_report.py`, `gator-charters.py` | [Charter Tooling](scripts-charter-tooling.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-pulse.py`, starter `gator-pulse.py` | [Strategic Pulse](scripts-pulse.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-dashboard.py`, `gator-kill.py`, `src/gator_command/scripts/dashboard/*.py` | [Dashboard Server](scripts-dashboard.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/dashboard/dashboard.css` | [Dashboard Shell](scripts-dashboard-shell.md) |
| `src/gator_command/scripts/dashboard/dashboard.html`, `src/gator_command/scripts/dashboard/dashboard.js`, `src/gator_command/scripts/dashboard/workspace.js`, `src/gator_command/scripts/dashboard/*.png` | [Dashboard Shell](scripts-dashboard-shell.md) · [Dashboard Server](scripts-dashboard.md) |
| `src/gator_command/scripts/dashboard/views/fleet.js`, `src/gator_command/scripts/dashboard/views/history.js`, `src/gator_command/scripts/dashboard/views/repo.js`, `src/gator_command/scripts/dashboard/views/syntax.js`, `src/gator_command/scripts/dashboard/views/audit.js`, `src/gator_command/scripts/dashboard/views/updates.js`, `src/gator_command/scripts/dashboard/views/docs.js`, `src/gator_command/scripts/dashboard/views/charters.js`, `src/gator_command/scripts/dashboard/views/welcome.js`, `src/gator_command/scripts/dashboard/views/settings.js` | [Dashboard Views](scripts-dashboard-views.md) · [Dashboard Server](scripts-dashboard.md) |
| `src/gator_command/scripts/dashboard/views/loop.js`, `src/gator_command/scripts/dashboard/views/loop-markdown.js` | [Loop Workspace View](scripts-dashboard-loop-ui.md) · [Dashboard Server](scripts-dashboard.md) |
| Welcome documents `src/gator_command/templates/gator-starter/docs/*.html` | [Dashboard Server](scripts-dashboard.md) |
| `src/gator_command/scripts/loop/session.py`, `src/gator_command/scripts/loop/state_machine.py`, `src/gator_command/scripts/loop/events.py`, `src/gator_command/scripts/loop/__init__.py` | [Loop State](scripts-loop-state.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/loop/submit.py`, `src/gator_command/scripts/loop/cli.py`, `src/gator_command/scripts/loop/gitsnap.py`, `src/gator_command/scripts/gator-loop.py` | [Loop Commands](scripts-loop-commands.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/loop/host.py`, `src/gator_command/scripts/loop/liveness.py`, `src/gator_command/scripts/loop/codex_launcher.py` | [Loop Lifecycle and Hosting](scripts-loop-host.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator-enterprise.py` | [Enterprise Dispatcher](scripts-enterprise.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `enterprise/enterprise-cli/**` | [Enterprise CLI](scripts-enterprise-cli.md) · [Enterprise Dispatcher](scripts-enterprise.md) |
| `enterprise/app/**`, `enterprise/migrations/**`, `enterprise/Dockerfile`, `enterprise/alembic.ini`, `enterprise/fly.toml`, `enterprise/requirements.txt` | [Enterprise Server](scripts-enterprise-server.md) · [Contracts](contracts.md) |
| `src/gator_command/scripts/gator-state.py` | [Managed State](scripts-managed-state.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `src/gator_command/scripts/gator_layout.py`, starter `gator_layout.py` | [Layout Resolver](scripts-layout.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `gator-pre-commit.py`, `precommit_*.py`, `gator-approve.py`, starter copies, the starter and bundled `charter_significance.py`, and synchronized Enterprise bundled copies | [Pre-Commit Governance](scripts-precommit.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `.gator/.includes/scripts/enforcer-review.py` and starter copy | [Cross-Cutting](scripts-cross-cutting.md) |
| `contracts/**` | [Contracts](contracts.md) |
| `.github/workflows/**`, `scripts/release-individual.sh`, `scripts/test-install-cycle.sh` | [Release Pipeline](release-pipeline.md) · [Cross-Cutting](scripts-cross-cutting.md) |
| `LICENSE`, `NOTICE`, `CONTRIBUTING.md` | [Cross-Cutting](scripts-cross-cutting.md) |

## Routing Rules

- Prefer the narrowest matching row; do not load every charter for a local change.
- When one file appears in two rows, read both because that file implements a boundary.
- Path-qualify every glob. The pre-commit hook also matches a glob against the file's basename alone, so a bare `*.js` would claim every JavaScript file in the repository.
- Add or update a row when ownership moves. Do not duplicate this map in `README.md` or another charter.
- Retired source-repo charters remain historical material in the vault and are not active routes.
