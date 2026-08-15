# Inbox

Drop anything here. No formatting needed.

**House rule (2026-08-11)**: keep only OPEN items. Finished work is captured in Git commits, CHANGELOG, and the roadmap. If an item ships or gets promoted to the roadmap, remove it from here.

---

## Where we are (2026-08-15)

**v2.7.0 shipped 2026-08-15** to PyPI + GitHub Release + tag; `main` + `dev` both at `58dc2f3` (dev now ahead by one Phase-3 Codex-adapter commit). Enterprise audit-surface tranche Phase 2 complete (Commits I `044cbdc` + J `604025c` + K `cfbc500`) — Q1-Q5 canonical audit questions all EXISTS with working CLI + API. **CDN-poll fix from v2.6.1 validated end-to-end** on this release's Workflow C post-verify (log: `PyPI CDN sees gator-command==2.7.0 on attempt 1`).

**Phase 3 (Enterprise-side Codex adapter) — core code landed 2026-08-15 as Commit L `f7ef4c2` on `dev`** (unreleased). Adapter for `~/.codex/sessions/` + `--vendor {codex,openai}` + 16 new discovery tests + charter invariant block. Enterprise suite: **285 pass + 1 skip** (was 269 + 1 skip). Not yet released to PyPI — will ride the next MINOR bump.

**Phase 2 smoke-test Run 1 executed 2026-08-15 — 9/9 PASS, zero MVP-code failures.** Full record: `.gator/vault/artifacts/2026-08-15-audit-surface-phase-2-smoke-test-run-1.md`. Phase 2 exit criteria satisfied. 5 protocol-side findings (T3 `--dry-run` can't surface the skip diagnostic; `--json` is a global flag; 7-char prefix floor for T6; Windows icacls/MSYS notes; T9 created-vs-updated baseline variance) + 4 polish observations for the Phase 6 backlog (Windows console `�` em-dash encoding in CLI output; empty session-prefix in the skip line; cumulative pagination summary; `pull --limit N` takes oldest-first discovery order). Net DB delta from the run: zero rows. Post-run whiteboard round: protocol rolled to **r2** (F1-F5 folded into the T3/T5/T6/T9 steps + Windows notes; status flipped to executed) and the run record's tree-identity claim sharpened (run was on `dev` `fe0860d` = v2.7.0 + Commit L; `--vendor claude` paths behaviorally equivalent, accepted as Phase 2 exit evidence rather than strict release-tree evidence).

**Ready to pick up next** (any of these; none are blocking each other):
- **Phase 3 exit-criteria closeout** — operator guide needs a Codex section (parent plan §5 exit criterion 4) + smoke evidence of one real Codex session linked end-to-end on a machine that has both Codex + Gator active (parent plan §5 exit criterion 2). See open item below.
- **Phase 4 (Enterprise-side Gemini adapter)** — parent plan §6. Blocked only on Architect firing. Introduces Migration 011 (widened `vendor_session_id` uniqueness for Gemini duplicate-id-across-files) per §10 item 6 = (b) ratified path.
- **Workflow B CDN-poll wrapper** — small release-hygiene follow-up (see open item below).

Everything else in the roadmap Post-2.6 candidate-work list (items 3-8, 11-12) is still-open + phase-independent.

---

## Open items

- **Docs rewrite for install/upgrade/getting-started/index.** 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` in v2.5.2 described the retired `gator-engine/scripts/gatorize.sh` install path. Need fresh versions for the pipx-first monorepo world. Priorities: `installation.md` (`pipx install gator-command` → `gator dashboard`), `upgrade.md` (`pipx upgrade`), `getting-started.md` (dashboard-first walkthrough), `index.md` (Home page for docs site). Vault copies preserve OLD prose as reference for what to rewrite / NOT reintroduce. (2026-08-02)

- **Legacy `cumberland-laboratories/gator-command` GitHub repo — plan for removal.** Architect will archive on GitHub. Once done, local `C:\Users\curator\code2\gator-command\` becomes reference-only. Contents already vaulted to `.gator/vault/gator-command-archive/`. Safe to `mv` to `gator-command-retired/` anytime; safe to delete after a few weeks of monorepo-only work with no missed content. (2026-08-02)

- **Charter promotion decision from vault.** Vault archive at `.gator/vault/gator-command-archive/charters/` has 18 charters; monorepo has 17 (`scripts-command-post.md` was Cat 3-excluded during bootstrap). Decide whether to restore/rewrite `scripts-command-post.md` for the monorepo context or leave the coverage gap. (2026-08-02)

- **Phase 3 exit-criteria closeout — operator guide + smoke evidence.** Commit L `f7ef4c2` (2026-08-15) landed the core Codex adapter code + tests + charter block, but parent plan §5 has two remaining exit criteria: (1) `enterprise/docs/` operator guide `.gator/vault/artifacts/enterprise-transcripts-mvp-operator-guide.md` needs a Codex section calling out `--vendor codex` + `~/.codex/sessions/` root + `CODEX_TRANSCRIPTS_ROOT` override + Codex-root missing-warning behavior (parallel to the Claude section) — small update, natural next commit. (2) Smoke evidence: on any machine with both Codex CLI transcripts + Gator machine-id present, run `.venv-enterprise-local/Scripts/gator-enterprise transcripts pull --vendor codex` and verify: (a) discovery finds actual rollout files, (b) at least one commit gets linked via `strong_machine_repo_time` basis, (c) `commits transcripts <sha>` reverse-lookup returns the Codex transcript row. Machine that ran the Phase 2 T1-T9 smoke can also run this — same stack + machine-id. Requires Codex CLI to have been used on the target machine (this repo's dev machine `c5c707f5-…-a10fea08` has none; test on a machine that does). (2026-08-15)

- **Workflow B TestPyPI CDN-poll wrapper — release-hygiene follow-up.** Discovered on v2.7.0 RC (Workflow B run `31855182635`, first attempt): the Windows-runner TestPyPI smoke hit the same CDN-lag race that the v2.6.1 CDN-poll fix addressed for Workflow C's production PyPI smoke. Ubuntu passed in 6s; Windows failed in 10s (`ERROR: Could not find a version that satisfies the requirement gator-command==2.7.0`). Retry-with-`gh run rerun --failed` cleared it after CDN warmed. Not urgent since retry unblocks it, but adding a bounded CDN-poll wrapper to `.github/workflows/release-candidate.yml`'s TestPyPI smoke step (parallel to the Workflow C fix at `promote-to-pypi.yml`) would eliminate the retry loop. Reference implementation: search for `Wait for PyPI CDN to surface the new version` in `promote-to-pypi.yml` — same shape, swap the JSON API URL to `test.pypi.org`. Would ride cleanly in a future release-hygiene commit; can't retrofit into v2.7.0-rc1 without burning `-rc2` on TestPyPI (filename permanence). (2026-08-15)

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
