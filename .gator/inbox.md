# Inbox

Keep only open work and current operational context here. Finished work belongs
in Git history, the changelog, and the roadmap.

## Where we are (2026-09-10, post-B2)

**Dashboard UI Plan A + Plan B1 + Plan B2 landed on `main`, unreleased
(slated v2.13.0).** B2 Codex converged after three review rounds — R1
took four findings (HIGH child-frame CSP read hole via postMessage
relay, HIGH production-path pin gap via `_click_file_via_repo_view`,
MEDIUM charter Wasm-audit claim narrowed, LOW copy-btn `setTimeout`
null-deref via synchronous button capture), R2 took four (two-lane
liveness, browser-captured popup CSP, rendered-pixel iframe sizing,
stale cross-cutting/fleet-intel charter reconciliation), R3 took two
LOW (extended `test_copy_path_writes_repo_relative_string` to walk
the full async flow, reconciled the primary Dashboard charter's
CSP-violation detector and iframe sizing TRIPWIREs to match the R2
implementations). Test state on Windows / Python 3.13:
`tests/test_dashboard_ui/` **166 pass + 11 skipped**. Ubuntu CI
exercises the POSIX-only pins.

B2 landed commits (in order):

- `4c8b900` B2 Slice 1: server-side CSP + Vary emit for /raw text/html + fast-matrix unsafe-eval audit
- `a22e311` B2 Slice 2: inline sandboxed iframe rendering + iframe CSS + shipped-blueprint + negative-control fixtures
- `611ca7d` B2 Slice 3: Playwright pins for sandboxed HTML preview + CSP violation detector + shipped-template compat matrix
- `c51a1d9` B2 Codex R1+R2+R3: postMessage-relay + production-path pins + async copy-btn coverage + charter reconciliation

Plans A + B1 commit list (`8f2b9c9` through `6efe9b9`) preserved in
git log.

Next dashboard-UI work — the choice the Architect handoff calls out:

1. **Cut v2.13.0** bundling Plan A + Plan B1 + Plan B2.
2. **Plan C — responsive shell/sidebar:**
   `.gator/vault/artifacts/2026-09-06-dashboard-responsive-shell-and-sidebar-plan.md`.
   Independent of B2; the harness seam `seed_sidebar_fixtures` is
   reserved for it.

The frozen parent plans remain reference-only:
`.gator/vault/artifacts/2026-09-06-dashboard-safe-content-transport-plan.md`,
`.gator/vault/artifacts/2026-09-07-dashboard-html-preview-b2-plan.md`,
and `.gator/vault/artifacts/2026-09-05-dashboard-ux-implementation-plan.md`.
Do not implement any of them directly.

Two sibling plans remain open, not on the dashboard-UI sequence:

- `.gator/vault/artifacts/2026-09-05-field-guides-retirement-implementation-plan.md`
- `.gator/vault/artifacts/2026-09-05-legacy-git-hooks-cleanup-implementation-plan.md`

**Release readiness for v2.13.0**: the Dashboard UI arc's changes are
release-worthy; the next release train can bundle Plan A + Plan B1 +
Plan B2 into v2.13.0 whenever the Architect chooses to cut. Blueprints
2.0 Release B (feature-blueprint generation procedure), previously
slated for v2.13.0, moves to v2.14.0 or later.

## Unscheduled open backlog

- Widen the TestPyPI and production PyPI poll windows from 120 seconds to 240
  seconds in release workflows B and C. Repeated CDN propagation races have
  established this as a real release reliability issue.
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
  weaken trust in the warning.
- Rewrite the vaulted pre-monorepo installation, upgrade, getting-started, and
  docs-index pages for the pipx-first monorepo workflow.
- After the Architect archives the legacy
  `cumberland-laboratories/gator-command` GitHub repository, treat the local
  standalone clone as reference-only and remove it after the agreed retention
  period.
- Decide whether the vaulted `scripts-command-post.md` charter should be
  restored for the monorepo or intentionally remain retired.
- **Post-B1 authoring observations** (nice-to-have, not blocking): (a) the
  `pre-commit charter-index-gap` rule requires ALL charters in a matching
  INDEX row to be updated, not "at least one" as the INDEX.md preamble
  claims — this bit every B1 slice commit and adds friction to changes that
  legitimately only touch one charter's surface; consider aligning
  `_required_charters_for_files` to the documented "at least one" rule, or
  updating INDEX.md's preamble to match the implementation. (b) The
  `new-functions-undocumented` warning fires on test functions (each
  `test_*` in a new test file), which is noise — consider a filename-based
  filter that skips `tests/**` for that warning.

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
