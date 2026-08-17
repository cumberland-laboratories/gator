# Inbox

Drop anything here. No formatting needed.

**House rule (2026-08-11)**: keep only OPEN items. Finished work is captured in Git commits, CHANGELOG, and the roadmap. If an item ships or gets promoted to the roadmap, remove it from here.

---

## Where we are (2026-08-16)

**Released**: **v2.8.0 on PyPI (2026-08-16)** — full Claude+Codex+Gemini audit surface; the audit-surface tranche is COMPLETE and shipped. `main` = `dev` = `96b0e1a` (tags `v2.8.0-rc1` + `v2.8.0`). GitHub Release published (`--latest`). Pipeline fully green first-try: Workflow B run `31983519052` (new TestPyPI CDN-poll step validated — Windows cell passed without rerun), promote run `31983601397` (production smoke passed attempt 1). Local install upgraded + verified (`gator --version` → 2.8.0). Release detail: roadmap Done table v2.8.0 row + CHANGELOG `[2.8.0]`.

**Next steps** (roadmap Current Priority reset 2026-08-17, Architect-directed): standing order restored — #1 install/onboarding UX, #2 Loop polish, #3 Enterprise evaluator-ready → announceable (single-pipx item 5 is the blocker). The smoke-campaign polish observations are now roadmap Post-2.6 item 17; content-hash skip is item 16. Open work lives in the roadmap tables + GitHub issues #1, #3-8 — nothing queued here.

---

## Open items

- **Session-snippet identity fallback: registry-miss is silent, degrades to commit_draft `agent:` string.** Surfaced 2026-08-16 by enforcer whiteboard finding on the `331f1ef` residue snippet (`session_group_key: null`, `model_inferred: "claude"`). Traced: NOT a code regression — two stacked conditions. (1) `session_group_key`/`transcript_session_id` are null whenever no live PID-matched entry exists in `.gator/active-vendor-session.json` at commit time — pre-existing and intermittent (most 08-10→08-15 snippets are also null); why the 08-16 session had no registry entry is unknowable post-hoc. (2) On registry miss, `render_snippet_json` → `_infer_vendor_from_agent()` (`precommit_session.py:748`) passes the commit_draft `agent:` string through as `model_inferred` verbatim — Opus sessions wrote `claude-opus-4-7` so misses looked precise; Fable sessions wrote `claude` so misses look generic. **Convention adopted 2026-08-16 (Architect-ratified)**: agents write the precise model name in commit_draft `agent:` (e.g. `claude-fable-5`), restoring fallback specificity at zero code cost. **Code fix for a future hook-hardening commit**: emit a `gator_diagnostics.log_hook_event`-style registry-miss diagnostic at snippet-emit time so silent SessionStart-registration failures become visible; optionally enrich the fallback. Rides naturally with the `stale-charter-refs` item below. Audit impact of misses is mitigated — Enterprise still links via `exact_sha_in_transcript` + `strong_machine_repo_time`; only the `session_id_in_snippet` basis is lost. (2026-08-16)

- **Pre-commit `stale-charter-refs` checker: compound `###` headings false-positive.** Surfaced 2026-08-16 on commit `25f2e6e`: warned `AUTO_YES / set_auto_yes` not found in covered files, but all three names in the compound heading `### AUTO_YES / set_auto_yes(value) / get_auto_yes()` (scripts-installer.md) exist in `gatorize/helpers.py`. The checker apparently treats slash-joined heading segments as one identifier instead of splitting on ` / ` and stripping signatures. Warning-only (never blocks), so low urgency — but false positives train agents to ignore the warning, which is how the REAL catch this same day (`memex_formatters` phantom entries) could get missed next time. Fix belongs in `gator-pre-commit.py`'s charter-validation phase; ride a future hook-hardening commit. (2026-08-16)

- **Docs rewrite for install/upgrade/getting-started/index.** 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` in v2.5.2 described the retired `gator-engine/scripts/gatorize.sh` install path. Need fresh versions for the pipx-first monorepo world. Priorities: `installation.md` (`pipx install gator-command` → `gator dashboard`), `upgrade.md` (`pipx upgrade`), `getting-started.md` (dashboard-first walkthrough), `index.md` (Home page for docs site). Vault copies preserve OLD prose as reference for what to rewrite / NOT reintroduce. (2026-08-02)

- **Legacy `cumberland-laboratories/gator-command` GitHub repo — plan for removal.** Architect will archive on GitHub. Once done, local `C:\Users\curator\code2\gator-command\` becomes reference-only. Contents already vaulted to `.gator/vault/gator-command-archive/`. Safe to `mv` to `gator-command-retired/` anytime; safe to delete after a few weeks of monorepo-only work with no missed content. (2026-08-02)

- **Charter promotion decision from vault.** Vault archive at `.gator/vault/gator-command-archive/charters/` has 18 charters; monorepo has 17 (`scripts-command-post.md` was Cat 3-excluded during bootstrap). Decide whether to restore/rewrite `scripts-command-post.md` for the monorepo context or leave the coverage gap. (2026-08-02)

---

## Machine state (persistent operational reference — not backlog, not history)

Kept here so any session has a single lookup surface for the state Enterprise smoke-tests and dev work assume.

- Postgres 18.4 on `localhost:5434`; DB `gator_enterprise`; superuser `postgres`; password `gator123`; alembic head `011` (Migration 011 `session_qualifier` applied 2026-08-15)
- Env file at repo root: `.env-enterprise-local` (gitignored) — has `DATABASE_URL`, `GATOR_ENTERPRISE_URL=http://localhost:8000`, `GATOR_ENTERPRISE_TOKEN=<one-shot admin token>`. Token is machine-local and non-recoverable — if lost, `DELETE FROM api_tokens WHERE label='bootstrap-admin';` then re-bootstrap with `python -m app.admin bootstrap`.
- Enterprise venv: `.venv-enterprise-local/` at repo root (gitignored). Use `.venv-enterprise-local/Scripts/{python,alembic,uvicorn,gator-enterprise}.exe` by absolute path; never activate. `psycopg[binary]` + editable install of `enterprise/enterprise-cli/` both required (smoke-test protocol §2.2).
- `~/.gator/machine-id` = `c5c707f5-155a-422f-9b1b-d9e8a10fea08`.
- `~/.gator/hooks/{pre,commit-msg,post}-commit` (Enterprise-owned machine git hooks); `~/.gator/enterprise/{config,hook-policy,crypto-policy}.json` + `keys/*.pem` + `cli-python-path`.
- Global `core.hooksPath = C:\Users\curator\.gator\hooks`. Monorepo unaffected (local `core.hooksPath = .git/gator-hooks` wins).
- Sandbox repo at `C:\Users\curator\code2\gator-enterprise-local-sandbox\` (provisioned via `gator-enterprise repo init --canonical-id local/gator-enterprise-local-sandbox`).
- Enterprise stack (uvicorn API + worker) tears down at session end. Startup commands are in the smoke-test protocol §2.4 (two terminals: uvicorn.exe on `:8000`, `python -m app.worker`).
- `BLOB_STORE_ROOT` must be set to a Windows-writable path (this machine uses `C:\Users\curator\code2\gator\.tmp\enterprise-blobs`) — the default `/var/lib/gator-enterprise/blobs` is POSIX and crashes on Windows.
