# Inbox

Drop anything here. No formatting needed.

---

- **`.gator/product-source.json` should target the pipx-installed gator, not the source repo.** Current monorepo state: `gator_root` points at `C:\Users\curator\code2\gator-command\src\gator_command` — the retired source repo. `gator-update.py` has self-heal (falls back to `Path(__file__).parent.parent` and rewrites), but that's the safety net, not the intent. In monorepo-primary mode, product-source should point at the running pipx install. Small `product-source.json` edit + a note about "when to rebind" in the update docs. (2026-08-02)

- **Move `enterprise/` under `src/gator_command/enterprise/`?** Raised during cutover; deferred to post-2.5.2. Enterprise-cli is a separate installable package (its own `pyproject.toml`), currently at repo root. Consistency-wise, Python source usually lives under `src/`. Moving requires careful `pyproject.toml` `[tool.setuptools]` config to keep the base wheel enterprise-free, plus verifying `test_wheel_does_not_ship_enterprise_cli_modules` still catches accidental inclusion. Roadmap Phase 5 (Deferred). (2026-08-02)

- **Docs rewrite for install/upgrade/getting-started/index/etc.** 12 pre-monorepo docs vaulted to `.gator/vault/docs-not-ready/` in v2.5.2. They described the retired `gator-engine/scripts/gatorize.sh` install path. Need fresh versions for the pipx-first monorepo world. Priorities: `installation.md` (`pipx install gator-command` → `gator dashboard`), `upgrade.md` (`pipx upgrade`), `getting-started.md` (dashboard-first walkthrough), `index.md` (Home page for docs site). The vault copies preserve the OLD prose as reference for what to rewrite / what NOT to reintroduce. (2026-08-02)

- **Consider: `migrate_layout` should print WHICH conflicts when it says "check conflicts".** The old error message ("Result: mixed (migration incomplete — check conflicts)") gave no signal of what to look at. The fix in v2.5.2 solves the specific case; but if migration ever fails to converge for a DIFFERENT reason, the operator gets the same opaque message. Enrich the report with the specific files that block convergence (like the "gator-command/ prefix references" list the bootstrap prints). (2026-08-02)

- **Promote workflow smoke test needs a PyPI-propagation wait.** v2.5.2 promote workflow succeeded but the post-publish smoke step failed with "Could not find gator-command==2.5.2" — PyPI's CDN needs ~30-60 seconds after upload before pip sees the new version. Manual re-run passed. Fix: add a `sleep 60` or a poll-until-visible loop before the smoke install in `promote-to-pypi.yml`. (2026-08-02)

- **Legacy `gator-command` local repo — plan for removal.** The Architect noted they'll archive `cumberland-laboratories/gator-command` (private) on GitHub within the week. Once done, the local `C:\Users\curator\code2\gator-command\` directory becomes reference-only. Contents already vaulted to `.gator/vault/gator-command-archive/`. Safe to `mv` to `gator-command-retired/` at any time; safe to delete after a few weeks of monorepo-only work with no missed content. (2026-08-02)

- **Charter promotion decision from vault.** The vault archive at `.gator/vault/gator-command-archive/charters/` has all source-repo charters (18), while the monorepo has 17 (`scripts-command-post.md` was Cat 3-excluded during bootstrap). Post-cutover charter review is queued anyway — decide then whether to restore/rewrite `scripts-command-post.md` for the monorepo context or leave the coverage gap. (2026-08-02)
