# Inbox

Keep only open work and current operational context here. Finished work belongs
in Git history, the changelog, and the roadmap.

## READ FIRST - Current handoff (2026-09-08, updated after r6 review)

**Immediate task for the next Opus session: implement Dashboard Plan B1 in
three bounded slices behind Plan A's harness.** The planning phase is closed.
Read `.gator/whiteboard.md` first, then the execution errata, then start
Slice 1.

Authoritative sources, in read order:

1. **Execution errata (authoritative for E1-E5):**
   `.gator/vault/artifacts/2026-09-08-dashboard-b1-execution-errata.md`.
   This document wins on any contradiction with the r6 plan. It carries the
   final five corrections from the 2026-09-08 r6 whiteboard plus one
   non-blocking tightening (the explicit-elif serializer;
   the E3 `parse_qs` fallback was suggested and left as-is per the reviewer's
   own note), and defines the three implementation slices with
   charter-alongside-code sequencing baked in.
2. **B1 r6 plan (frozen design record):**
   `.gator/vault/artifacts/2026-09-07-dashboard-safe-content-transport-b1-plan.md`.
   Frontmatter carries `status: frozen-reference` and `superseded-by` pointing
   at the errata. Read for design intent only; do not amend for implementation
   details.

Current state:

- **Plan A is complete and committed** at `8f2b9c9` (`Plan A: Dashboard UI
  harness foundation`). Its `dashboard-ui` CI acceptance gate passed on Ubuntu
  and Windows.
- **Plan B1 is planning-complete and implementation-ready.** No B1 code or B1
  tests have landed. B1 owns the security-critical server-side content
  transport and authorization layer.
- **The r6 plan cycled through r4 → r5 → r6 reviews.** r6 review declined an
  r7 revision block and directed a concise errata + three-slice
  implementation instead. The errata addresses:
  - E1 (High): `/files` wire schema — one shared `_serialize_listing_entry`
    preserves shipped `path`/`source`/`dir` shape.
  - E2 (Med): parser normalizes `raw_path.rstrip("/") or "/"` to match
    shipped `do_GET`.
  - E3 (Med): version-key detection via `parse_qs` at start (catches
    `%76ersion=abc`).
  - E4 (Med): parser-shape rejects on `/file` are 400; debug-seam pins pinned
    to `dashboard_fleet_debug_off` / `dashboard_fleet`.
  - E5 (Med): `_is_reserved_windows_component` layer 1 strips trailing
    spaces so `NUL .txt`, `COM1 .md`, `CONIN$ .txt` are caught without the
    deprecated stdlib.
- **Three implementation slices, each with charter-alongside-code updates**
  per constitution:
  1. Parser + `content_policy` + Windows-name normalization + response
     helpers + unit tests. Charter updates for `scripts-dashboard.md` helper
     entries, `scripts-cross-cutting.md`, `contracts.md` — landed alongside
     the files.
  2. In-place `do_GET` migration (delete four B1 route blocks; insert parser
     + 4-way dispatch; preserve legacy branches). E1 wire-schema
     live + historical round-trip pins. Charter updates for the `do_GET`
     route inventory and every §12 TRIPWIRE.
  3. Junction/platform tests, POSIX parser-symmetry, final charter
     reconciliation, full Plan A `dashboard-ui` gate green on Ubuntu +
     Windows.
- The `seed_history_commits(repo, name)` harness seam is intentionally part of
  B1; not in committed Plan A. Preserve Plan A's existing
  `seed_sidebar_fixtures` seam.

Dashboard work remains deliberately sequenced:

1. **A - complete:**
   `.gator/vault/artifacts/2026-09-06-dashboard-harness-foundation-plan.md`
2. **B1 - implement in three slices (errata authoritative):**
   `.gator/vault/artifacts/2026-09-08-dashboard-b1-execution-errata.md` +
   frozen r6 plan
   `.gator/vault/artifacts/2026-09-07-dashboard-safe-content-transport-b1-plan.md`
3. **B2 - downstream, not yet reviewed for implementation:**
   `.gator/vault/artifacts/2026-09-07-dashboard-html-preview-b2-plan.md`
4. **C - downstream responsive shell/sidebar work:**
   `.gator/vault/artifacts/2026-09-06-dashboard-responsive-shell-and-sidebar-plan.md`

The monolithic parent
`.gator/vault/artifacts/2026-09-06-dashboard-safe-content-transport-plan.md`
and the earlier
`.gator/vault/artifacts/2026-09-05-dashboard-ux-implementation-plan.md` are
frozen design records. **Do not implement either frozen plan directly.**

Two sibling plans remain open but are not part of the immediate B1 sequence:

- `.gator/vault/artifacts/2026-09-05-field-guides-retirement-implementation-plan.md`
- `.gator/vault/artifacts/2026-09-05-legacy-git-hooks-cleanup-implementation-plan.md`

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
