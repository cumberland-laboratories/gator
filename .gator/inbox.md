# Inbox

Keep only open work and current operational context here. Finished work belongs
in Git history, the changelog, and the roadmap.

## Dashboard inspection-workspace decisions (Architect-ratified 2026-09-12)

- ~~**Next Dashboard increment: read-only Python and SQL syntax highlighting.**~~
  **Shipped in v2.13.2 on 2026-09-12** — `views/syntax.js` hand-rolled
  Python + SQL tokenizer + `.md-code-block .tok-*` CSS + charter subsection
  with three TRIPWIREs (escape-order, size-cap, snapshot inliner obligation).
  7 new Playwright pins (`test_syntax_highlight.py`), dashboard UI suite now
  199 pass + 11 skip.
- **Document tabs: dropped from current scope.** Hands-on use of the shipped
  sidebar navigation showed that tabs are not necessary right now. The planned
  Phase 2 tab strip and tab-descriptor model should not be implemented unless
  new usage evidence creates a concrete need.
- **`field-guides/` retirement: deferred to lowest priority.** Preserve current
  behavior for now and revisit the staged retirement at a later date.

## Codex sketches — Architect-ratified next work (2026-09-12)

Two Codex-authored sketches under `.gator/vault/artifacts/`. Sketch 1
(Fleet column stability) **shipped in v2.13.1 on 2026-09-12**. Sketch 2
(Cumberland HTML) remains next — now that the read-only Python/SQL
highlighting increment shipped in v2.13.2, Cumberland HTML is the next
scheduled Dashboard-adjacent work.

### ~~1. Dashboard Fleet Update column stability~~ — **shipped in v2.13.1**

Path: `vault/artifacts/2026-09-12-dashboard-fleet-update-column-stability-sketch.md`

Landed as single-commit implementation `7be554f` (reserved-slot pattern:
permanent `<span class="activity-indicator">` inside every `.activity-cell`;
`bindUpdateButtons` / `bindGatorizeButtons` mutate INSIDE the indicator;
20px CSS reservation matches `.dot-pulse` width; new geometry pin +
structural pin in `tests/test_dashboard_ui/test_fleet_layout.py`; new
Fleet-table TRIPWIRE in `scripts-dashboard.md`). Version bump `af60d93`
and rc1/final tags shipped v2.13.1 via a fully first-try green pipeline.

### 2. Cumberland HTML style default + always-read routing rule (cross-cutting)

Path: `vault/artifacts/2026-09-12-cumberland-html-style-sketch.md`

- **Thesis** — when the Architect says "I want an HTML document that says…",
  every governed model should default to a single Cumberland narrative HTML
  master template without needing to remember a filename, slash command, or
  protocol. Promote the visual grammar demonstrated by
  `~/Downloads/2026-09-11-what-gator-is.html` (SHA-256
  `0926F696…D53D9E4`) into a Gator-shipped master + add one short routing
  rule to the always-read constitution.
- **Architect framing (2026-09-12)**: the reference file IS a Gator-built
  artifact. Its styling IS the canonical target for all HTML documents Gator
  produces — this is a style-canonicalization task, not an inspiration point.
  The master template should reproduce the reference's visual grammar
  faithfully.
- **Separation of concerns** — style (Cumberland palette/typography/shell)
  vs role (blueprint/artifact/procedure/policy/reference-note determines
  path) vs protocol (`gator-blueprint-html-v1` metadata is optional when
  the role calls for it). Explicit HTML request → Cumberland master →
  role-appropriate destination.
- **Canonical source**:
  `src/gator_command/templates/gator-starter/reference-notes/cumberland-html-document-template.html`
  with `.gator/.includes/reference-notes/…` as the dogfood mirror.
  Reference-notes location because it's already shipped + layout-resolved
  and constitution-relative links work in both v1 and v2 layouts.
- **Fix** — four slices: (1) establish master from the reference file
  (add to `MIXED_DIRECTORY_SHIPPED_DEFAULTS` in `gator_layout.py` for
  fallback classification); (2) constitution rule + broaden
  `procedures/authoring-html-artifacts.md` from Blueprint-first to
  medium-first triage; (3) reconcile `_template-narrative.html` as a
  Blueprint-protocol specialization of the master with a
  `<!-- CUMBERLAND-NARRATIVE-STYLE:BEGIN/END -->` byte-identical shared
  region + parity check; (4) propagation + visual-invariant tests
  (structural + computed-style, not pixel snapshots — OS font rendering
  variance).
- **Scope** — cross-cutting: shipped template + constitution + procedure +
  narrative-Blueprint template + charter updates in `scripts-repo-lifecycle`
  / `scripts-layout` / `scripts-cross-cutting`. Codex explicitly calls the
  significance check pre-commit even though HTML/CSS is low-risk, because
  it changes the default Architect-request response across every governed
  repo and every supported model.
- **Codex's recommendation** — land after Blueprints 2.0 work settles enough
  to avoid editing the narrative-template + authoring-procedure files
  concurrently. One small cross-cutting feature train.

Sequence within these two sketches remains **Fleet column stability, then
Cumberland HTML**. Fleet column stability shipped in v2.13.1 and the
read-only Python/SQL highlighting increment shipped in v2.13.2; Cumberland
HTML is pre-implementation and next.

## Where we are (2026-09-12, post-v2.13.2)

**v2.13.2 shipped** with read-only Python + SQL syntax highlighting in
the Dashboard Repo file browser plus a `source_alias_denied` log demote
(WARNING → DEBUG) that removes ~120 spurious warnings per Dashboard
session on a 15-repo fleet. GitHub Release:
https://github.com/cumberland-laboratories/gator/releases/tag/v2.13.2 —
pipeline **fully first-try green** with no CDN-race reruns, making it
three consecutive fully-first-try releases (v2.13.0, v2.13.1, v2.13.2).
Prior releases: v2.13.1 (Fleet activity-column stability) and v2.13.0
(Dashboard UI arc: Plans A/B1/B2/C). Nothing on the dashboard-UI sequence
is blocking. Next scheduled work is **Codex Sketch 2 — Cumberland HTML
style default + always-read routing rule**. The pre-v2.13.0 roadmap
priorities remain — see `roadmap.md`:

1. Gator + Enterprise polished and ready for lots of users.
2. Blueprints 2.0 Release B (feature-blueprint generation procedure).
3. Gator Loop polish.
4. Normalized transcript index (exploratory).

## Unscheduled open backlog

- ~~Widen the TestPyPI and production PyPI poll windows from 120 seconds to
  240 seconds in release workflows B and C.~~ **Likely already resolved
  (2026-09-12)**: v2.13.0, v2.13.1, AND v2.13.2 all ran fully first-try
  green with no CDN-race reruns — three consecutive. The existing
  `Wait for TestPyPI CDN to surface the new version` workflow step in
  `release-candidate.yml` appears to be handling propagation. Keep the
  item watch-only; if a CDN race hits any future release, re-open with the
  actual failing workflow log rather than a preemptive widen.
- **Pre-commit block message points at stale `gator-approve.py` path**
  (2026-09-12): when the pre-commit hook blocks and prints the STOP box, the
  approve instruction reads `python .gator/scripts/gator-approve.py`. Post-
  runtime-split (v2.9.0), the repo carries no `.gator/scripts/` and no such
  file exists there — the operator hits `[Errno 2] No such file or
  directory` on the first attempt. Actual machine-side entry point is
  `gator hook approve --reason "..." --name "..."` (per the routing table in
  `gator-hook.py`, which maps `"approve"` → `gator-approve.py` inside the CLI
  install). The block message text is emitted from
  `templates/gator-starter/scripts/gator-pre-commit.py` (search for the STOP
  box print block); update to point at `gator hook approve` (or add a
  first-class `gator approve` CLI subcommand — the current CLI shows no
  `approve` verb at the top level, only `hook`, so the natural discovery path
  is broken too).
- **`gator-approve.py --help` doesn't work** (2026-09-12): the script reads
  the reason via `input()` BEFORE parsing sys.argv, so `--help` never
  reaches argparse — the operator sees the interactive prompt instead of
  usage. Fix: parse args first (recognize `--help` / `-h` and print usage),
  then only prompt for the reason when it wasn't supplied via `--reason`.
- **`gator kill dashboard` UX** (2026-09-12): bare command LISTS running
  processes but does NOT kill them — kill requires `--all` or `--port N`.
  The imperative verb misleads: multiple times today the operator thought
  they'd killed a stale Dashboard when they'd only enumerated it, causing
  a browser tab to keep serving pre-fix `fleet.js` through the whole
  release cycle. Options: (a) rename bare command to `gator kill dashboard
  list` (list becomes an action, not a default); (b) require an explicit
  `list` / `--all` / `--port N` at parse and refuse the bare form with an
  actionable error; (c) prompt for confirmation on a bare invocation. The
  current shape prioritizes "prevent accidental kill" but the safety
  trade-off costs clarity.
- **Stale-Dashboard-in-browser detection** (2026-09-12): when a fix ships
  and the operator restarts inconsistently, the browser can silently show
  pre-fix state — today the Fleet-column shift kept reproducing because
  the operator's browser tab was pointed at a stale Dashboard on port
  8420 that the bare `gator kill dashboard` did not terminate. Options:
  (a) `_send_dashboard_html` embeds a build hash / commit SHA in a
  `<meta name="gator-dashboard-build" content="...">` tag; frontend
  compares to a per-connection value and shows a "reload — Dashboard
  restarted" banner if they diverge; (b) same but auto-reload on
  divergence with a short-timer debounce; (c) versioned asset URLs
  (`fleet.js?v=<sha>`) so a Dashboard restart forces browsers to bypass
  cache on every asset. (a) is the least disruptive; (c) is closest to
  standard web-app hygiene.
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
