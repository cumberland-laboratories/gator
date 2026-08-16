# Inbox

Drop anything here. No formatting needed.

**House rule (2026-08-11)**: keep only OPEN items. Finished work is captured in Git commits, CHANGELOG, and the roadmap. If an item ships or gets promoted to the roadmap, remove it from here.

---

## Where we are (2026-08-15)

**v2.7.0 shipped 2026-08-15** to PyPI + GitHub Release + tag; `main` + `dev` both at `58dc2f3` (dev now ahead by one Phase-3 Codex-adapter commit). Enterprise audit-surface tranche Phase 2 complete (Commits I `044cbdc` + J `604025c` + K `cfbc500`) — Q1-Q5 canonical audit questions all EXISTS with working CLI + API. **CDN-poll fix from v2.6.1 validated end-to-end** on this release's Workflow C post-verify (log: `PyPI CDN sees gator-command==2.7.0 on attempt 1`).

**Phase 3 (Enterprise-side Codex adapter) — COMPLETE 2026-08-15, all §5 exit criteria met.** Core code landed as Commit L `f7ef4c2` on `dev` (unreleased — rides the next MINOR bump): adapter for `~/.codex/sessions/` + `--vendor {codex,openai}` + 16 new discovery tests + charter invariant block; enterprise suite **285 pass + 1 skip**. Closeout landed same day: operator guide gained a Codex section (§3.1a — vendor aliases, `CODEX_TRANSCRIPTS_ROOT` override, missing-root warning, metadata extraction; §0/§3.1/§7.1/§8 refreshed), and the real-corpus smoke passed on this machine — **102/102 Codex transcripts ingested (~151MB, 2026-03→08, all `gpt-5.4`), 0 failed, links by basis `{exact_sha_in_transcript: 1007, strong_machine_repo_time: 972}`, reverse lookup returns Codex rows with correct per-basis confidence**. Evidence: `.gator/vault/artifacts/2026-08-15-phase-3-codex-smoke-evidence.md`. (Earlier "this dev machine has no Codex transcripts" claim was stale — corrected.) DB now holds 107 transcript sessions (5 anthropic + 102 openai) as intentional evidence custody.

**Phase 2 smoke-test Run 1 executed 2026-08-15 — 9/9 PASS, zero MVP-code failures.** Full record: `.gator/vault/artifacts/2026-08-15-audit-surface-phase-2-smoke-test-run-1.md`. Phase 2 exit criteria satisfied. 5 protocol-side findings (T3 `--dry-run` can't surface the skip diagnostic; `--json` is a global flag; 7-char prefix floor for T6; Windows icacls/MSYS notes; T9 created-vs-updated baseline variance) + 4 polish observations for the Phase 6 backlog (Windows console `�` em-dash encoding in CLI output; empty session-prefix in the skip line; cumulative pagination summary; `pull --limit N` takes oldest-first discovery order). Net DB delta from the run: zero rows. Post-run whiteboard round: protocol rolled to **r2** (F1-F5 folded into the T3/T5/T6/T9 steps + Windows notes; status flipped to executed) and the run record's tree-identity claim sharpened (run was on `dev` `fe0860d` = v2.7.0 + Commit L; `--vendor claude` paths behaviorally equivalent, accepted as Phase 2 exit evidence rather than strict release-tree evidence).

**Phase 4 (Enterprise-side Gemini adapter) — COMPLETE 2026-08-15, all §6 exit criteria met** (Commit M, on `dev`, unreleased). Migration 011 `session_qualifier` (NOT-NULL-default-`''` refinement over the plan's "nullable" prose — Postgres NULLs never collide in unique constraints) + Gemini adapter (`~/.gemini/tmp/<project>/chats/session-*.json`, single-JSON, `--vendor {gemini,google}`, stored slug `google`, `GEMINI_TRANSCRIPTS_ROOT` override, projects.json workspace hints) + **β multi-link fan-out ratified at kickoff (§10 item 7)** with order-independent retroactive confidence downgrade. Smoke on this machine: **19/19 real Gemini transcripts ingested, 4 commits linked (`strong_machine_repo_time`, `local/quiz_app`), and an ORGANIC duplicate-raw-ID pair** (`f5f946c0-…` in 2 files, different content 67,878/18,970 B) demonstrably coexisting as 2 rows + 2 blobs — the exact pre-011 silent-evidence-loss case, prevented with real data. Enterprise suite **310 pass + 1 skip** (+25); base+contracts **808 pass** (base interpreter), zero regressions; local alembic head **011**. Evidence: `.gator/vault/artifacts/2026-08-15-phase-4-gemini-smoke-evidence.md`. Custody now 126 sessions (5 anthropic + 102 openai + 19 google).

**Ready to pick up next** (any of these; none are blocking each other):
- **Phase 5 sweep (non-Enterprise session cleanup Phase 4)** — **NOW UNBLOCKED**: parent plan §7's gate (Phases 3+4 landed + ≥1 real linked commit each for Codex + Gemini) is satisfied as of today. Atomic retirement of `extract-codex-sessions.py` (477) + `extract-gemini-sessions.py` (410) + `gator-session-common.py` (372) + 2 archaeology TRIPWIREs + charter sweep. Recipe: consumer audit r3 §14.5. Small, mechanical.
- **Phase 6 (Architect smoke vs widened vendor set)** — parent plan §8; runs after Phase 5. All three vendors now have real custody on this machine, so the protocol can run entirely locally.
- **Workflow B CDN-poll wrapper** — small release-hygiene follow-up (see open item below).

Everything else in the roadmap Post-2.6 candidate-work list (items 3-8, 11-12) is still-open + phase-independent.

---

## Open items

- **Docs rewrite for install/upgrade/getting-started/index.** 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` in v2.5.2 described the retired `gator-engine/scripts/gatorize.sh` install path. Need fresh versions for the pipx-first monorepo world. Priorities: `installation.md` (`pipx install gator-command` → `gator dashboard`), `upgrade.md` (`pipx upgrade`), `getting-started.md` (dashboard-first walkthrough), `index.md` (Home page for docs site). Vault copies preserve OLD prose as reference for what to rewrite / NOT reintroduce. (2026-08-02)

- **Legacy `cumberland-laboratories/gator-command` GitHub repo — plan for removal.** Architect will archive on GitHub. Once done, local `C:\Users\curator\code2\gator-command\` becomes reference-only. Contents already vaulted to `.gator/vault/gator-command-archive/`. Safe to `mv` to `gator-command-retired/` anytime; safe to delete after a few weeks of monorepo-only work with no missed content. (2026-08-02)

- **Charter promotion decision from vault.** Vault archive at `.gator/vault/gator-command-archive/charters/` has 18 charters; monorepo has 17 (`scripts-command-post.md` was Cat 3-excluded during bootstrap). Decide whether to restore/rewrite `scripts-command-post.md` for the monorepo context or leave the coverage gap. (2026-08-02)

- **Workflow B TestPyPI CDN-poll wrapper — release-hygiene follow-up.** Discovered on v2.7.0 RC (Workflow B run `31855182635`, first attempt): the Windows-runner TestPyPI smoke hit the same CDN-lag race that the v2.6.1 CDN-poll fix addressed for Workflow C's production PyPI smoke. Ubuntu passed in 6s; Windows failed in 10s (`ERROR: Could not find a version that satisfies the requirement gator-command==2.7.0`). Retry-with-`gh run rerun --failed` cleared it after CDN warmed. Not urgent since retry unblocks it, but adding a bounded CDN-poll wrapper to `.github/workflows/release-candidate.yml`'s TestPyPI smoke step (parallel to the Workflow C fix at `promote-to-pypi.yml`) would eliminate the retry loop. Reference implementation: search for `Wait for PyPI CDN to surface the new version` in `promote-to-pypi.yml` — same shape, swap the JSON API URL to `test.pypi.org`. Would ride cleanly in a future release-hygiene commit; can't retrofit into v2.7.0-rc1 without burning `-rc2` on TestPyPI (filename permanence). (2026-08-15)

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
