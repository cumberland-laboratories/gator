# Inbox

Keep only open work and current operational context here. Finished work belongs
in Git history, the changelog, and the roadmap.

## Where we are (2026-09-12, post-v2.13.0)

**v2.13.0 shipped.** GitHub Release live at
https://github.com/cumberland-laboratories/gator/releases/tag/v2.13.0.
Nothing on the dashboard-UI sequence is blocking. The pre-v2.13.0
roadmap priorities remain — see `roadmap.md`:

1. Gator + Enterprise polished and ready for lots of users.
2. Blueprints 2.0 Release B (feature-blueprint generation procedure).
3. Gator Loop polish.
4. Normalized transcript index (exploratory).

## Unscheduled open backlog

- Widen the TestPyPI and production PyPI poll windows from 120 seconds to 240
  seconds in release workflows B and C. Historical CDN propagation races
  established this as a real reliability item. **Downgrade watch**: the
  v2.13.0 release train ran fully first-try green on both TestPyPI and
  production PyPI smokes with no reruns. Might mean the existing
  "Wait for TestPyPI CDN to surface the new version" workflow step already
  handles propagation, or it may just be a lucky quiet stretch. Confirm by
  reading the current workflow YAML before deciding whether to widen.
- Improve `precommit_session.py::_extract_note_lines` snippet emission so the
  `notes` field captures the substantive governance narrative instead of the
  first 8 non-empty preamble lines. Options: (a) raise the `limit=8` default;
  (b) prefer the LAST N lines; (c) prefer content under a specific heading
  (`## Outcome` / `## Verdict`) and fall back to first-N when absent; (d)
  extend the schema with an explicit `verdict` / `outcome` field the
  commit_draft populates. Whichever lands, `scripts-cross-cutting.md`
  "Shared Snippet Infrastructure" note about the truncation shape needs a
  matching update.
- Continue hardening session opening if the shipped `gator init` directive does
  not stop models from skipping the constitution: make the entry-point reads
  blunt and explicit, remove the vestigial two-path conditional, and avoid
  rendering unread files as successful checks.
- Define post-runtime-split authority for `product-source.json`. Installed CLI
  templates should be authoritative; consider honoring the file only as an
  explicit development override when its version matches the CLI.
- Clarify agent guidance that `.gator/commit_draft.md` is the commit-message
  source of truth; agents should not invent a separate bespoke `git commit -m`
  message.
- Add a diagnostic when session-snippet emission cannot find a live registry
  identity. The current fallback silently uses the `agent:` value from
  `commit_draft.md` and loses the session ID.
- Stop `gator update` and gatorize overlay copies from shipping
  `__pycache__/*.pyc` files from templates.
- Fix `stale-charter-refs` parsing of compound headings such as
  `AUTO_YES / set_auto_yes(value) / get_auto_yes()`; current false positives
  weaken trust in the warning (fired on every commit across the v2.13.0
  remediation train).
- Fix `new-functions-undocumented` warning firing on test-function names in
  `tests/**`. Every `test_*` in a new test file becomes noise; consider a
  filename-based filter that skips `tests/**` for that warning. (Same round of
  observations as the `stale-charter-refs` item above — fired on every
  Slice 3 commit.)
- `_required_charters_for_files` vs `INDEX.md` preamble cardinality mismatch:
  INDEX.md preamble says a matching row requires "at least one" listed
  charter to be updated; `gator-pre-commit.py::validate_hard_rules` actually
  requires EVERY listed charter to be staged (`missing = required -
  staged_names`). Options: align code to the documented "at least one" rule,
  or update INDEX.md preamble to match the ALL-of-required implementation.
- Rewrite the vaulted pre-monorepo installation, upgrade, getting-started, and
  docs-index pages for the pipx-first monorepo workflow.
- After the Architect archives the legacy
  `cumberland-laboratories/gator-command` GitHub repository, treat the local
  standalone clone as reference-only and remove it after the agreed retention
  period.
- Decide whether the vaulted `scripts-command-post.md` charter should be
  restored for the monorepo or intentionally remain retired.
- Charter line-locator sweep across the OTHER charters. `scripts-dashboard.md`
  is now clean of the prohibited `filename.ext:N` / `line N` / `line ~N` /
  `lines N-M` forms (Slice 3 R6-R8 remediation). Similar debt likely exists in
  neighboring charters (`scripts-cross-cutting.md`, `scripts-repo-lifecycle.md`,
  etc.) — needs a directed sweep to bring the whole `.gator/charters/` tree
  into line with the constitution's "stable, grep-verifiable identifiers"
  rule.
- Deferred Plan C §7 pins (documented in `scripts-dashboard.md` "Forward-
  declaration note" preamble + `test_responsive_shell.py` module docstring):
  `test_fleet_view_scrolls_at_900_400`, `test_fleet_view_scrolls_at_375_667_mobile`,
  initial-load-error preserves sidebar state, polling-refresh preserves
  collapse button, `test_iframe_layout_at_375_667` (250px minimum-usable-size
  distinct from the 400px floor), invalid-persisted-width fallback, mobile
  bounded-shell scroll-owner (`#main-shell` scrolls while `documentElement`
  does not). Legitimate follow-on coverage for a future slice if full §7
  parity is wanted.

## Machine state (persistent operational reference)

This section is reference data for Enterprise development and smoke tests, not
backlog or release history.

- Postgres 18.4 runs on `localhost:5434`; database `gator_enterprise`;
  superuser `postgres`; password `gator123`; Alembic head `011`.
- Repo-root `.env-enterprise-local` is gitignored and contains `DATABASE_URL`,
  `GATOR_ENTERPRISE_URL=http://localhost:8000`, and the machine-local
  `GATOR_ENTERPRISE_TOKEN`. If the one-shot token is lost, delete the
  `bootstrap-admin` row from `api_tokens`, then run
  `python -m app.admin bootstrap`.
- Repo-root `.venv-enterprise-local/` is gitignored. Use executables beneath
  `.venv-enterprise-local/Scripts/` by absolute path; do not activate it.
  `psycopg[binary]` and an editable install of `enterprise/enterprise-cli/`
  are required.
- `~/.gator/machine-id` is
  `c5c707f5-155a-422f-9b1b-d9e8a10fea08`.
- Enterprise-owned hooks are in
  `~/.gator/hooks/{pre,commit-msg,post}-commit`; policy/configuration is in
  `~/.gator/enterprise/`, including `config.json`, `hook-policy.json`,
  `crypto-policy.json`, `keys/*.pem`, and `cli-python-path`.
- Global `core.hooksPath` is `C:\Users\curator\.gator\hooks`. This repository's
  local `core.hooksPath = .git/gator-hooks` takes precedence.
- Enterprise sandbox repository:
  `C:\Users\curator\code2\gator-enterprise-local-sandbox\`.
- The Enterprise API and worker are normally stopped between sessions. Startup
  commands are in the smoke-test protocol section 2.4.
- Set `BLOB_STORE_ROOT` to a Windows-writable path. This machine uses
  `C:\Users\curator\code2\gator\.tmp\enterprise-blobs`; the POSIX default is
  invalid on Windows.
