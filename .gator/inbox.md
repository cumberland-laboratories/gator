# Inbox

Drop anything here. No formatting needed.

**House rule (2026-08-11)**: keep only OPEN items. Finished work is captured in Git commits, CHANGELOG, and the roadmap. If an item ships or gets promoted to the roadmap, remove it from here.

---

## Open items

- **Docs rewrite for install/upgrade/getting-started/index.** 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` in v2.5.2 described the retired `gator-engine/scripts/gatorize.sh` install path. Need fresh versions for the pipx-first monorepo world. Priorities: `installation.md` (`pipx install gator-command` → `gator dashboard`), `upgrade.md` (`pipx upgrade`), `getting-started.md` (dashboard-first walkthrough), `index.md` (Home page for docs site). Vault copies preserve OLD prose as reference for what to rewrite / NOT reintroduce. (2026-08-02)

- **Legacy `cumberland-laboratories/gator-command` GitHub repo — plan for removal.** Architect will archive on GitHub. Once done, local `C:\Users\curator\code2\gator-command\` becomes reference-only. Contents already vaulted to `.gator/vault/gator-command-archive/`. Safe to `mv` to `gator-command-retired/` anytime; safe to delete after a few weeks of monorepo-only work with no missed content. (2026-08-02)

- **Charter promotion decision from vault.** Vault archive at `.gator/vault/gator-command-archive/charters/` has 18 charters; monorepo has 17 (`scripts-command-post.md` was Cat 3-excluded during bootstrap). Decide whether to restore/rewrite `scripts-command-post.md` for the monorepo context or leave the coverage gap. (2026-08-02)

- **PyPI-CDN poll fix — validation-pending watch item for next release.** The v2.6.1 CDN-poll fix (commit `94b791e`) shipped to PyPI + `main` on 2026-08-14, but Workflow C's actual v2.6.1 promote run (run `31763277200`) loaded `promote-to-pypi.yml` from `main` at `cf01805` (pre-fix) — that's how `workflow_dispatch` resolves workflow definitions. The install step passed anyway, either because PyPI's CDN was fast this time or `pip install` retried internally. Now that `main` has the fix (via the 2026-08-14 FF), the next release cycle will actually exercise the new "Wait for PyPI CDN to surface the new version" step. Watch: look for the `PyPI CDN sees gator-command==<version> on attempt <N>` log line in the next Workflow C run's post-verify job; N should typically be 1-2. If N is consistently 8 or the step times out, the poll cadence needs tuning. (2026-08-14)

- **Audit-surface tranche — implementation-plan authoring pending.** The [2026-08-14 Codex next-steps sketch](vault/artifacts/2026-08-14-enterprise-audit-surface-next-steps-sketch.md) is now the current-priority direction (roadmap Current Priority #1 + candidate-work items 9-11, 13-15). Its own §7 says the next artifact is "revised implementation plan for this tranche" — that plan doesn't exist yet. When the Architect ratifies the sketch and hands the tranche to Opus, first deliverable is the implementation plan (parallel to `2026-08-11-non-enterprise-session-cleanup-plan.md`'s shape), starting with sketch Step 1 (the canonical audit-question surface artifact). (2026-08-14)

---

## Machine state (persistent operational reference — not backlog, not history)

Kept here so any session has a single lookup surface for the state Enterprise smoke-tests and dev work assume.

- Postgres 18.4 on `localhost:5434`; DB `gator_enterprise`; superuser `postgres`; password `gator123`; alembic head `010`
- Env file at repo root: `.env-enterprise-local` (gitignored) — has `DATABASE_URL`, `GATOR_ENTERPRISE_URL=http://localhost:8000`, `GATOR_ENTERPRISE_TOKEN=<one-shot admin token>`. Token is machine-local and non-recoverable — if lost, `DELETE FROM api_tokens WHERE label='bootstrap-admin';` then re-bootstrap with `python -m app.admin bootstrap`.
- Enterprise venv: `.venv-enterprise-local/` at repo root (gitignored). Use `.venv-enterprise-local/Scripts/{python,alembic,uvicorn,gator-enterprise}.exe` by absolute path; never activate. `psycopg[binary]` + editable install of `enterprise/enterprise-cli/` both required (smoke-test protocol §2.2).
- `~/.gator/machine-id` = `c5c707f5-155a-422f-9b1b-d9e8a10fea08`.
- `~/.gator/hooks/{pre,commit-msg,post}-commit` (Enterprise-owned machine git hooks); `~/.gator/enterprise/{config,hook-policy,crypto-policy}.json` + `keys/*.pem` + `cli-python-path`.
- Global `core.hooksPath = C:\Users\curator\.gator\hooks`. Monorepo unaffected (local `core.hooksPath = .git/gator-hooks` wins).
- Sandbox repo at `C:\Users\curator\code2\gator-enterprise-local-sandbox\` (provisioned via `gator-enterprise repo init --canonical-id local/gator-enterprise-local-sandbox`).
- Enterprise stack (uvicorn API + worker) tears down at session end. Startup commands are in the smoke-test protocol §2.4 (two terminals: uvicorn.exe on `:8000`, `python -m app.worker`).
- `BLOB_STORE_ROOT` must be set to a Windows-writable path (this machine uses `C:\Users\curator\code2\gator\.tmp\enterprise-blobs`) — the default `/var/lib/gator-enterprise/blobs` is POSIX and crashes on Windows.
