# Inbox

Drop anything here. No formatting needed.

---

## STATUS as of 2026-08-08

**Active work: Enterprise Transcripts-First MVP.**

- **Ratified plan**: `.gator/vault/artifacts/2026-08-08-enterprise-transcripts-first-mvp-implementation-plan.md`
- **ADR**: `.gator/vault/artifacts/2026-08-08-enterprise-transcripts-first-adr.md` — D1-D11 durable reference
- **Codex sketch that set the direction**: `.gator/vault/artifacts/2026-08-08-weekend-enterprise-mvp-plan.md`
- **Install/update-surfaces blueprint** (understand the base ↔ Enterprise seam): `.gator/vault/blueprints/gator-install-and-update-surfaces.md`

**Progress:**
- Phase 0 COMPLETE 2026-08-08 (inventory verified; ADR written; plan updated with net-positive scope reductions)
- Phase 1 COMPLETE 2026-08-08 (commit `e784d60`) — Migration 009 + TranscriptSession + CommitTranscriptLink + BlobStore Protocol + FilesystemBlobStore + 34 tests + charter update; ran end-to-end against local Postgres port 5434
- **Phase 2 authorized** — next work: `POST /api/v1/commits/ingest` + `POST /api/v1/transcripts/ingest` + `GET /api/v1/transcripts/*` endpoints; `gator-enterprise transcripts pull` CLI; Claude Code transcript discovery + upload. Est. ~10-14h.

**Recent commit chain** (2026-08-07 through 2026-08-08 on `dev`):
- `da517cb` — enterprise/tests/conftest.py sys.path fix + starlette httpx warning filter
- `5121c4d` — `gator-enterprise repo init --mode` default → `strict`
- `df71e8e` — multi-vendor v2 schema for `.gator/active-vendor-session.json` + PID attribution + env-var overrides (24 tests)
- `e1e09ef` — Codex-findings fixes on `df71e8e`: 3-way byte-identity, PID recycling protection, `GATOR_TRANSCRIPT_VENDOR` (34 tests)
- `e784d60` — Phase 1 of transcripts-first MVP (11 files, 1124+/1-)

**Ratifications enforced across all Enterprise design**:
1. Enterprise repos = same product as gatorized repos + Enterprise features layered on top
2. Enterprise integration is v2-only (`.gator/.includes/` layout); v1 gets detect + refuse + report
3. `~/.gator/` machine-scope is authoritative over `<repo>/.gator/` repo-scope
4. Session capture is Enterprise-only in end-state (clean break from base-gator); MVP transitionally consumes base-gator's session artifacts
5. Evidence stored in Enterprise-managed storage (DB + blob), NOT in Git
6. Enterprise runs entirely inside customer's firewall — nothing to Cumberland at runtime
7. **Transcripts-first**, not session-blocks-first (MVP)

**Machine state (persistent across sessions):**
- Postgres 18.4 on `localhost:5434`; DB `gator_enterprise`; superuser `postgres`; password `gator123`; alembic head `009`
- Env file at repo root: `.env-enterprise-local` (gitignored) — has `DATABASE_URL`, `GATOR_ENTERPRISE_URL=http://localhost:8000`, `GATOR_ENTERPRISE_TOKEN=<one-shot admin token>`. Token is machine-local and non-recoverable — if lost, `DELETE FROM api_tokens WHERE label='bootstrap-admin';` then re-bootstrap.
- Server venv: `.venv-enterprise-local/` at repo root (gitignored). Use `.venv-enterprise-local/Scripts/{python,alembic,uvicorn}.exe` by absolute path; never activate.
- `~/.gator/hooks/{pre,commit-msg,post}-commit` (Enterprise-owned machine git hooks); `~/.gator/enterprise/{config,hook-policy,crypto-policy}.json` + `keys/*.pem` + `cli-python-path`. Machine-id `c5c707f5-155a-422f-9b1b-d9e8a10fea08`.
- Global `core.hooksPath` = `C:\Users\curator\.gator\hooks`. Monorepo unaffected (has local `core.hooksPath = .git/gator-hooks` that wins).
- Sandbox repo at `C:\Users\curator\code2\gator-enterprise-local-sandbox\` (provisioned via `gator-enterprise repo init --canonical-id local/gator-enterprise-local-sandbox`; useful for testing).

**Enterprise stack (uvicorn API + worker) is likely DEAD** — Claude Code sandbox tears them down at session end. Next session must re-boot:
```
# From /c/Users/curator/code2/gator/enterprise (run_in_background):
DATABASE_URL='postgresql://postgres:gator123@localhost:5434/gator_enterprise' APP_ENV=dev ../.venv-enterprise-local/Scripts/uvicorn.exe app.main:app --port 8000 --host 127.0.0.1
DATABASE_URL='postgresql://postgres:gator123@localhost:5434/gator_enterprise' APP_ENV=dev ../.venv-enterprise-local/Scripts/python.exe -m app.worker
```

**Superseded work** (kept as history, no longer the direction): the 2026-08-06 Enterprise Local Bring-Up plan + the 2026-08-07 session-evidence adapter plan are now historical background. Transcripts-first supersedes both for MVP scope. Adapter architecture may return as post-MVP if a real multi-vendor pressure surfaces. Session-block generation code (`block_generate.py`, `.gator/session-blocks/`, encrypted envelope machinery) is TRANSITIONAL — do not extend; retirement is post-MVP cleanup.

---

## Active backlog (not yet actioned)

- **Docs rewrite for install/upgrade/getting-started/index.** 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` in v2.5.2 described the retired `gator-engine/scripts/gatorize.sh` install path. Need fresh versions for the pipx-first monorepo world. Priorities: `installation.md` (`pipx install gator-command` → `gator dashboard`), `upgrade.md` (`pipx upgrade`), `getting-started.md` (dashboard-first walkthrough), `index.md` (Home page for docs site). Vault copies preserve OLD prose as reference for what to rewrite / NOT reintroduce. (2026-08-02)

- **Promote workflow smoke test needs a PyPI-propagation wait.** v2.5.2 promote succeeded but post-publish smoke failed with "Could not find gator-command==2.5.2" — PyPI's CDN needs ~30-60s before pip sees the new version. Manual re-run passed. Fix: `sleep 60` or poll-until-visible before smoke install in `promote-to-pypi.yml`. (2026-08-02)

- **Legacy `gator-command` local repo — plan for removal.** Architect will archive `cumberland-laboratories/gator-command` (private) on GitHub. Once done, local `C:\Users\curator\code2\gator-command\` becomes reference-only. Contents already vaulted to `.gator/vault/gator-command-archive/`. Safe to `mv` to `gator-command-retired/` anytime; safe to delete after a few weeks of monorepo-only work with no missed content. (2026-08-02)

- **Charter promotion decision from vault.** Vault archive at `.gator/vault/gator-command-archive/charters/` has 18 charters; monorepo has 17 (`scripts-command-post.md` was Cat 3-excluded during bootstrap). Post-cutover charter review is queued — decide whether to restore/rewrite `scripts-command-post.md` for the monorepo context or leave the coverage gap. (2026-08-02)

- **Follow-up: tracked repo-local vendor hook configs** (`.claude/settings.json`, `.codex/hooks.json`, `.gemini/settings.json`) as a merge/conflict surface because `gator update` legitimately rewrites the Gator-managed hook commands inside tracked repo files. **Under the ratified transcripts-first + session-capture-is-Enterprise-only direction, base-gator's `install_vendor_hooks` goes away entirely (post-MVP cleanup arc).** This follow-up will be absorbed by that cleanup rather than solved on its own — no separate action needed for MVP. (2026-08-05, absorbed by post-MVP arc)
