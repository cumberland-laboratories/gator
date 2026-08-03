# Inbox

Drop anything here. No formatting needed.

---

- ~~**Vendor SessionStart hook paths silently break on v1→v2 layout migration.**~~ **RESOLVED 2026-08-03** (B2 + A4, commits `a532851` + `2e80730`). Vendor-hook templates now ship v2 paths (`.gator/.includes/scripts/…`); `merge_hooks_into_settings` auto-rewrites drift on every update. `--migrate-layout` now also runs `install_vendor_hooks` at end of successful convergence so v1→v2 migrations flip vendor hooks in the same command.

- ~~**`gator-session-open.py` silently no-ops on v2 layout.**~~ **RESOLVED 2026-08-03** (B1 + B3, commits `83a4f18` + `e47a53e`). Script now uses `get_gator_paths()` layout resolver and passes `GatorPaths` (not raw Path) into `ensure_git_hooks`. Non-happy-path statuses log to `.gator/diagnostics/hooks.log` (bounded, gitignored) so future silent breakage at this seam surfaces as machine-local evidence.

- ~~**`.gator/product-source.json` should target the pipx-installed gator, not the source repo.**~~ **PARTIALLY RESOLVED 2026-08-03** (A3). This repo rebound to source tree (`C:\Users\curator\code2\gator\src\gator_command`) rather than pipx, per Architect decision to avoid a regression trap: rebinding to pipx v2.5.2 would have triggered `merge_hooks_into_settings` to overwrite this repo's v2 vendor-hook paths with v2.5.2's v1-path templates (undoing the turn-2 manual fix), because B2's fix hadn't shipped yet. Once B1-B3 ship as v2.5.3, rebinding to pipx (`gator update --source <pipx-path>`) becomes safe. Follow-up: consider adding a brief "when to rebind product-source" note to a procedure doc — deferred until an actual second occurrence surfaces the need.

- **Move `enterprise/` under `src/gator_command/enterprise/`?** Raised during cutover; deferred to post-2.5.2. Enterprise-cli is a separate installable package (its own `pyproject.toml`), currently at repo root. Consistency-wise, Python source usually lives under `src/`. Moving requires careful `pyproject.toml` `[tool.setuptools]` config to keep the base wheel enterprise-free, plus verifying `test_wheel_does_not_ship_enterprise_cli_modules` still catches accidental inclusion. Roadmap Phase 5 (Deferred). (2026-08-02)

- **Docs rewrite for install/upgrade/getting-started/index/etc.** 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` in v2.5.2. They described the retired `gator-engine/scripts/gatorize.sh` install path. Need fresh versions for the pipx-first monorepo world. Priorities: `installation.md` (`pipx install gator-command` → `gator dashboard`), `upgrade.md` (`pipx upgrade`), `getting-started.md` (dashboard-first walkthrough), `index.md` (Home page for docs site). The vault copies preserve the OLD prose as reference for what to rewrite / what NOT to reintroduce. (2026-08-02)

- ~~**Consider: `migrate_layout` should print WHICH conflicts when it says "check conflicts".**~~ **RESOLVED 2026-08-03** (A2, commit `dc63071`). `migrate_layout`'s mixed-result branch now calls `_enumerate_mixed_residue(gator_dir)` and prints each blocking path with a per-path reason plus a "Suggested next step" hint. Enumerator sync-obligation-bound to `_has_legacy_shipped_content` in `gator_layout.py`.

- **Promote workflow smoke test needs a PyPI-propagation wait.** v2.5.2 promote workflow succeeded but the post-publish smoke step failed with "Could not find gator-command==2.5.2" — PyPI's CDN needs ~30-60 seconds after upload before pip sees the new version. Manual re-run passed. Fix: add a `sleep 60` or a poll-until-visible loop before the smoke install in `promote-to-pypi.yml`. (2026-08-02)

- **Legacy `gator-command` local repo — plan for removal.** The Architect noted they'll archive `cumberland-laboratories/gator-command` (private) on GitHub within the week. Once done, the local `C:\Users\curator\code2\gator-command\` directory becomes reference-only. Contents already vaulted to `.gator/vault/gator-command-archive/`. Safe to `mv` to `gator-command-retired/` at any time; safe to delete after a few weeks of monorepo-only work with no missed content. (2026-08-02)

- **Charter promotion decision from vault.** The vault archive at `.gator/vault/gator-command-archive/charters/` has all source-repo charters (18), while the monorepo has 17 (`scripts-command-post.md` was Cat 3-excluded during bootstrap). Post-cutover charter review is queued anyway — decide then whether to restore/rewrite `scripts-command-post.md` for the monorepo context or leave the coverage gap. (2026-08-02)
