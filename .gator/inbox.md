# Inbox

Open work and current operational context. **GitHub Issues are the
source of truth for bugs, feature requests, and improvements** —
this file carries pointers, non-issue operational context, and
ratified standards that don't belong in the issue tracker.

## Retention standards for roadmap and inbox (Architect direction 2026-09-12; ratified 2026-09-14)

- **Both files are current-facing only.** `roadmap.md` = current
  strategy, priorities, planned work. `inbox.md` = open work +
  operational context.
- **No shipped-release narratives; no historical change log.** Git
  history and commit messages are authoritative for what has shipped.
  Durable historical detail moves to focused artifacts under
  `.gator/artifacts/` when it merits preservation; otherwise Git
  carries it.
- **Soft cap: ~250 lines per file.** Compact or archive before
  adding past that.
- **Roll-forward pattern**: prepend short notes; do not extend dense
  paragraphs.

First-pass compaction landed 2026-09-14 (roadmap 87% reduction;
Codex-sketches section retired; historical detail archived at
`.gator/artifacts/2026-09-14-roadmap-shipped-history-archive.md`).
Mechanical soft-cap check is #24.

## Where we are (2026-09-14, post-v2.13.3)

Cumberland HTML Sketch 2 arc closed and shipped in v2.13.3
(2026-09-14) — Codex round-15 "no findings, recommend closure";
bounded self-containment stop rule in force.

Latest released version is **v2.13.3** (2026-09-14). Five
consecutive fully first-try green pipelines (v2.13.0 →
v2.13.3). The pre-v2.13.0 roadmap priorities are next — see
`roadmap.md`:

1. Gator + Enterprise polished and ready for lots of users.
2. Blueprints 2.0 Release B (feature-blueprint generation procedure).
3. Gator Loop polish.
4. Normalized transcript index (exploratory).

## Open backlog (GitHub Issues)

All open work lives in the issue tracker. Group indices below for
quick session-open scanning; open the issue for full detail.

**Bugs:**

- [#1](https://github.com/cumberland-laboratories/gator/issues/1) Dashboard swallows `gator update` errors as bare "!" (dashboard) — partial fix in v2.9.2; broader error-surfacing sweep pending
- [#3](https://github.com/cumberland-laboratories/gator/issues/3) `release-candidate.yml` doesn't inject RC suffix into wheel version (packaging)
- [#13](https://github.com/cumberland-laboratories/gator/issues/13) Pre-commit block message points at stale `gator-approve.py` path (hooks)
- [#14](https://github.com/cumberland-laboratories/gator/issues/14) `gator-approve.py --help` broken — prompts before argparse (hooks)
- [#15](https://github.com/cumberland-laboratories/gator/issues/15) `gator kill dashboard` bare command lists but doesn't kill (dashboard)
- [#16](https://github.com/cumberland-laboratories/gator/issues/16) `stale-charter-refs` false positive on compound headings (hooks)
- [#17](https://github.com/cumberland-laboratories/gator/issues/17) `new-functions-undocumented` fires on `test_*` in `tests/**` (hooks)
- [#18](https://github.com/cumberland-laboratories/gator/issues/18) `_required_charters_for_files` vs `INDEX.md` cardinality mismatch (hooks)
- [#19](https://github.com/cumberland-laboratories/gator/issues/19) `gator update` + gatorize overlay ship `__pycache__/*.pyc` (packaging)

**Enhancements / Features:**

- [#4](https://github.com/cumberland-laboratories/gator/issues/4) Bump `actions/*` past Node.js 20 before GitHub force-fails (packaging, maintenance — deadline-driven)
- [#5](https://github.com/cumberland-laboratories/gator/issues/5) Gator Loop polish (umbrella) (loop)
- [#6](https://github.com/cumberland-laboratories/gator/issues/6) Loop Dashboard events timeline (dashboard, loop)
- [#7](https://github.com/cumberland-laboratories/gator/issues/7) Loop Dashboard session card on Repo overview (dashboard, loop)
- [#8](https://github.com/cumberland-laboratories/gator/issues/8) Loop protocol + artifact-format refinement (loop)
- [#20](https://github.com/cumberland-laboratories/gator/issues/20) Stale-Dashboard-in-browser detection (dashboard)
- [#21](https://github.com/cumberland-laboratories/gator/issues/21) `precommit_session._extract_note_lines` captures preamble not verdict (hooks)
- [#22](https://github.com/cumberland-laboratories/gator/issues/22) Session-snippet emission: diagnostic when no live registry identity (hooks)
- [#23](https://github.com/cumberland-laboratories/gator/issues/23) Session-opening directive hardening (hooks)
- [#24](https://github.com/cumberland-laboratories/gator/issues/24) Retention-standards mechanical check for roadmap/inbox (hooks)
- [#25](https://github.com/cumberland-laboratories/gator/issues/25) Post-runtime-split authority for `product-source.json` (packaging)
- [#26](https://github.com/cumberland-laboratories/gator/issues/26) Deferred Plan C §7 pins — dashboard-UI test coverage (dashboard)
- [#31](https://github.com/cumberland-laboratories/gator/issues/31) Clickable "Representative functions" in `charter-map.html` — click-through to source (dashboard) — Blueprints 2.0 Level-3 step

**Documentation:**

- [#27](https://github.com/cumberland-laboratories/gator/issues/27) Charter line-locator sweep across `.gator/charters/**`
- [#28](https://github.com/cumberland-laboratories/gator/issues/28) Agent guidance: `commit_draft.md` is commit-message source of truth
- [#29](https://github.com/cumberland-laboratories/gator/issues/29) Rewrite vaulted pre-monorepo docs for pipx-first
- [#30](https://github.com/cumberland-laboratories/gator/issues/30) Decide `scripts-command-post.md` charter fate

## Non-issue operational context

The below is intentionally NOT in the tracker — either ratified
decisions with no work-item, watch-only observations, or
machine-local reference material.

### Dashboard inspection-workspace decisions (Architect-ratified 2026-09-12)

- **Document tabs**: dropped from current scope. Hands-on use of the
  shipped sidebar navigation showed tabs are unnecessary. Do not
  implement Phase 2 tab strip / tab-descriptor model unless new
  usage evidence creates a concrete need.
- **`field-guides/` retirement**: deferred to lowest priority.
  Preserve current behavior; revisit later.

### CDN-widen — watch-only

Widening the TestPyPI + production PyPI post-publish poll windows
from 120s → 240s was inboxed after v2.6.0-era CDN races. Five
consecutive fully first-try green pipelines (v2.13.0 → v2.13.3)
suggest the existing `Wait for TestPyPI CDN to surface the new
version` step is handling propagation. **Keep watch-only**; if a
future release hits a real CDN race, open a bug then rather than
preemptively widening.

### Post-legacy-repo cleanup — deferred, no work item

After the Architect archives the legacy
`cumberland-laboratories/gator-command` GitHub repository, treat the
local standalone clone as reference-only and remove it after the
agreed retention period. Not filed as a GitHub issue because it's
Architect-side housekeeping, not a Gator code change.

## Machine state (persistent operational reference)

Reference data for Enterprise development and smoke tests — not
backlog.

- Postgres 18.4 runs on `localhost:5434`; database `gator_enterprise`;
  superuser `postgres`; password `gator123`; Alembic head `011`.
- Repo-root `.env-enterprise-local` is gitignored and contains
  `DATABASE_URL`, `GATOR_ENTERPRISE_URL=http://localhost:8000`, and
  the machine-local `GATOR_ENTERPRISE_TOKEN`. If the one-shot token
  is lost, delete the `bootstrap-admin` row from `api_tokens`, then
  run `python -m app.admin bootstrap`.
- Repo-root `.venv-enterprise-local/` is gitignored. Use executables
  beneath `.venv-enterprise-local/Scripts/` by absolute path; do not
  activate it. `psycopg[binary]` and an editable install of
  `enterprise/enterprise-cli/` are required.
- `~/.gator/machine-id` is `c5c707f5-155a-422f-9b1b-d9e8a10fea08`.
- Enterprise-owned hooks are in
  `~/.gator/hooks/{pre,commit-msg,post}-commit`; policy/configuration
  is in `~/.gator/enterprise/`, including `config.json`,
  `hook-policy.json`, `crypto-policy.json`, `keys/*.pem`, and
  `cli-python-path`.
- Global `core.hooksPath` is `C:\Users\curator\.gator\hooks`. This
  repository's local `core.hooksPath = .git/gator-hooks` takes
  precedence.
- Enterprise sandbox repository:
  `C:\Users\curator\code2\gator-enterprise-local-sandbox\`.
- The Enterprise API and worker are normally stopped between
  sessions. Startup commands are in the smoke-test protocol section
  2.4.
- Set `BLOB_STORE_ROOT` to a Windows-writable path. This machine uses
  `C:\Users\curator\code2\gator\.tmp\enterprise-blobs`; the POSIX
  default is invalid on Windows.
