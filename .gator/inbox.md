# Inbox

Drop anything here. No formatting needed.

**House rule (2026-08-11)**: keep only OPEN items. Finished work is captured in Git commits, CHANGELOG, and the roadmap. If an item ships or gets promoted to the roadmap, remove it from here.

---

## Where we are (2026-08-16)

**Released**: v2.7.0 on PyPI (2026-08-15); `main` at `58dc2f3`. The v2.6.1 CDN-poll fix validated end-to-end on that promote.

**Audit-surface tranche: ALL SIX PHASES COMPLETE + ARCHITECT-RATIFIED (2026-08-16).** Phase 6 widened-vendor smoke Run 1: PASS — Q1-Q5 correct for Claude + Codex + Gemini against real custody, zero code failures; run artifact + 5-item rough-edges backlog in vault (`2026-08-16-audit-surface-widened-smoke-run-1.md`); RE-2 promoted to roadmap Post-2.6 item 16. Per-phase detail: roadmap Current Priority #1 + items 9/10/11/15, vault evidence artifacts, commit bodies.

**`dev` is 8+ commits ahead of `main`, all unreleased** — tranche Phases 3-5 (`f7ef4c2` Codex adapter, `85bbef9` Phase 3 closeout, `25dbc58` Gemini adapter + Migration 011, `eb273f4` session-cleanup sweep, `25f2e6e` Memex charter cleanup) plus 2026-08-16 follow-through (`e28d0bf` snippet-identity governance, `db0bdae` whiteboard Findings 1+2 fix — order-independent fan-out ambiguity metadata + vendor-accurate CLI help, `200c6de` RE-2 roadmap promotion). Test state: enterprise **311 pass + 1 skip**, base+contracts **808 pass**, zero regressions. Local stack: alembic head **011**; custody **156 sessions** (35 anthropic + 102 openai + 19 google).

**Next steps, in recommended order**:
1. **v2.8.0 cut** — FF `main`, tag `v2.8.0-rc1`, Workflow B → promote. MINOR (3 vendors' adapter surface + Migration 011, all additive). First release where the release-notes story is "full Claude+Codex+Gemini audit surface". Operator-facing note for the changelog: Enterprise operators must run `alembic upgrade head` (Migration 011) before pulling Gemini transcripts. The Workflow B TestPyPI CDN-poll wrapper landed on `dev` 2026-08-16 — the rc1 run is its first real-world validation (mirrors how the Workflow C fix validated on the v2.7.0 promote).
2. **Polish-pass backlog** (post-release): Phase 6 RE-1/RE-3/RE-4/RE-5 + Phase 2 Run 1 P1-P4 observations; roadmap item 16 (content-hash skip) when scheduled.

Everything else in the roadmap Post-2.6 candidate-work list (items 3-8, 12, 16) is still-open + phase-independent.

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
