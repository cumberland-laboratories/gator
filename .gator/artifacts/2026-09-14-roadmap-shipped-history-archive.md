---
date: 2026-09-14
type: roadmap-history-archive
scope: roadmap-retention-compaction
---

# Roadmap shipped-history archive

Extracted from `.gator/roadmap.md` on 2026-09-14 during the retention
compaction the Architect directed in `inbox.md` (2026-09-12: keep
roadmap short and human-readable; move durable historical detail to
focused artifacts; rely on Git history / changelog for what doesn't
merit an artifact).

**What lives here**: the shipped-release narrative for Gator versions
that had accumulated in the roadmap's leading paragraph and "Done"
tables. This is not new content — every entry below was already in
`roadmap.md` immediately prior to commit `da0f112`. Consult Git
history on that file for full pre-compaction wording.

**What does NOT live here**:

- Currently-active strategy, priorities, planned work — those stayed
  in `roadmap.md`.
- Cross-cutting design records — those live in
  `.gator/artifacts/<date>-*.md` under their own topics.
- Enterprise Post-2.6 candidate items that are still OPEN — those
  stayed in `roadmap.md` under the Enterprise section.

**How to add to this archive**: when the roadmap accumulates
shipped-version detail beyond what the retention standard admits,
append a section here (dated) instead of expanding the leading
paragraph. Or open a new focused artifact if the release deserves
its own record.

## Recent releases at a glance (post-monorepo-cutover)

| Version | Shipped | Headline |
|---------|---------|----------|
| v2.13.2 | 2026-09-12 | Dashboard read-only Python + SQL syntax highlighting; `source_alias_denied` WARNING → DEBUG demote |
| v2.13.1 | 2026-09-12 | Fleet activity-column stability patch (reserved-slot pattern) |
| v2.13.0 | 2026-09-12 | Dashboard UI arc: Plan A harness + Plan B1 safe content transport + Plan B2 sandboxed HTML preview + Plan C responsive shell/sidebar |
| v2.12.3 | 2026-09-03 | Four HTML blueprints dogfood pass + `.diagram-edge` flex fix |
| v2.12.2 | 2026-09-03 | HTML template + reference-implementation restyle (Cumberland palette + class vocabulary) |
| v2.12.1 | 2026-09-03 | HTML scaffolding routing fix (v2.12.0 same-day patch) |
| v2.12.0 | 2026-09-02 | HTML Artifact Protocol / Blueprints 2.0 Release A |
| v2.11.1 | 2026-08-30 | Blueprints canvas responsive frame + stage split |
| v2.11.0 | 2026-08-30 | Blueprints 2.0 Release A: Dashboard-native L1 charter map |
| v2.10.0 | 2026-08-29 | Machine-scoped Python launcher preference (`gator-preferences-v1`) |
| v2.9.3  | 2026-08-28 | Hook shebang + JSON gate + session-open fixes |
| v2.9.2  | 2026-08-23 | Reference-notes reclassification + dry-run gate + dashboard error surfacing |
| v2.9.1  | 2026-08-23 | Session-opening directive (constitution-skip fix) |
| v2.9.0  | 2026-08-23 | **The runtime split**: machine-scoped runtime + pin + policy channel |
| v2.8.0  | 2026-08-16 | Full Claude+Codex+Gemini audit surface (Migration 011, β fan-out) |
| v2.7.0  | 2026-08-15 | Enterprise audit-surface tranche Phase 2 (Q2/Q4/Q5 new surfaces) |
| v2.6.1  | 2026-08-14 | Non-Enterprise session cleanup Phase 2 + Phase 3 (~5,000 lines removed) |
| v2.6.0  | (Phase 4) | Enterprise transcripts-first MVP substrate |
| v2.5.4  | 2026-08-03 | Session-hook self-heal + migration convergence + drift visibility |
| v2.5.3  | 2026-08-02 | Hook hardening recovery (v2.5.2 wheel had missed files) |
| v2.5.2  | (cutover) | Change-type enum + migrate_layout duplicates + docs vault |
| v2.5.1  | 2026-08-02 | First release from public monorepo |
| v2.4.5  | (July) | HTML file support + Docs view broadening + first screenshot tranche |
| v2.4.4  | | Windows non-cp1252 git output fix |
| v2.4.3  | | `gator kill dashboard` + discovery-roots + Dashboard-first docs |
| v2.4.2  | | `cli-version` stamps on every successful update |
| v2.4.1  | | `product-source.json` self-heal (fleet hotfix) |
| v2.4.0  | | Retire `gator-install` branch — update in place |
| v2.3.0  | | Local-agent overrides + managed-state layer |
| v2.2.2  | | Charter-verify layout-resolver fix + enforcer trust-boundary docs + justified body text |
| v2.2.1  | | Mixed-layout update deadlock fix |
| v2.2.0  | | Repo file browser overhaul |
| v2.1.0  | | **Gator Loop** (12 subcommands, 3-role tokens, round-versioned artifacts); `.includes/` layout (v2); merge-conflict fix |
| v2.0.0  | | Command-post full retirement + installer safety branch fix |
| v1.9.0..v1.9.3 | | Dashboard: Fleet Add Repository, mode collapse, gatorize/update distinction, registry path normalization; hook warning mode |
| v1.7.0..v1.8.11 | | Module splits, Fleet UX overhaul, self-upgrade from dashboard, docs (How-to-Use, How-it-Works), Dashboard logo |
| v1.2+ | | pipx install path, PyPI package, git history, Dashboard search, deploy pipeline |
| v1.0+ | | Cross-platform install, pre-commit hook, standalone mode, standalone dashboard |

For per-version detail beyond the headline, consult the corresponding
commit on `main` — the commit-message body carries the change log
that used to live in the roadmap's leading paragraph.

## Cumberland HTML style Sketch 2 arc (closed 2026-09-14)

Not tied to a released version. See commit `da0f112` (the roadmap
roll-forward that preceded this archive) for the full closure
summary, and the round-15 whiteboard note in Git history for
Codex's "no findings, recommend closure" verdict.

Commit range: `fd35d92`..`d986898` (18 commits, three days).
Highlights:

- Slices 1-4 delivered the shipped Cumberland master template +
  narrative Blueprint specialization + parity contract +
  visual-invariant test surface.
- Eleven enforcer rounds accreted a parser-based self-containment
  blacklist.
- Round-12 (`ea6b610`) pivoted to a bounded positive-policy
  validator + pinned Content-Security-Policy `<meta>` in both
  templates. Module dropped 2304 → 937 lines (−1367 net).
- Rounds 13-14 tightened structural CSP validation, narrowed
  Layer 1 to HTML-only, and hardened the CSS-egress boundary
  test with a shared CSP constant + `securitypolicyviolation`
  liveness assertion.

Bounded guarantee: "The two checked-in Cumberland templates contain
only approved passive HTML, carry the pinned CSP that denies
external resource loading, and produce no non-template network
requests during Chromium's initial load."

## Monorepo convergence (shipped 2026-08-02 as v2.5.1)

Full sub-phase sequence executed 2026-07-16 → 2026-08-02:

- 3b-3-recon: tree-map + sub-phase plan.
- 3b-3-A: staging skeleton via `scripts/monorepo-bootstrap.py`.
- 3b-3-B: `.gator/` scaffold with `EXCLUDE_KNOWLEDGE_FILES` +
  `PATH_REWRITES`.
- 3b-3-C: validation via `scripts/monorepo-validate.py` (9 checks,
  baselined stale-path gates).
- 3b-3-D: GitHub cutover (legacy repo renamed
  `-legacy-pre-monorepo` + archived; fresh
  `cumberland-laboratories/gator` created public + Apache).
- Codex Finding 1 (enterprise dispatcher catch-all masking real
  failures) fixed with three-ordered-check pre-delegation pattern.
- Apache 2.0 mechanical migration landed as Phase 3c (LICENSE
  flipped MIT → Apache 2.0, NOTICE added, `pyproject.toml`
  updated).

Design records under `.gator/artifacts/`: monorepo merge assessment
(2026-07-16), convergence plan (2026-07-16), implementation plan
(2026-07-21), product-contract decisions (2026-07-31),
public-release-pipeline design (2026-07-27), apache-2 mechanical
migration checklist (2026-07-18).

## Enterprise audit-surface tranche (shipped v2.7.0 + v2.8.0)

Five canonical audit questions (Q1-Q5) all EXISTS post-tranche;
verified end-to-end by three smoke campaigns:

- Phase 2 smoke Run 1 (2026-08-15): 9/9 PASS.
- Phase 3 Codex smoke (2026-08-15): 102/102 transcripts + 1,979
  links.
- Phase 6 widened smoke (2026-08-16): Q1-Q5 × 3 vendors,
  156-session custody, 2,025 commits, 13 repos.

Substrate lives in Migration 009-011 + FastAPI routes + operator
CLI. Full plan chain preserved in `.gator/vault/artifacts/` (each
plan artifact carries the ratification history + Codex review
passes).

## Enterprise phases E1-E10 summary

| Phase | Shipped in | What |
|-------|------------|------|
| E1 | pre-cutover | Foundation (FastAPI, PostgreSQL, Alembic, API tokens, health) |
| E2 | pre-cutover | GitHub App adapter, webhook receiver, repo sync |
| E3 | pre-cutover | Policy engine (CRUD, versioning, rollout state machine) |
| E4 | pre-cutover | Governance artifact ingestion, materialized reports, drift detection |
| E5 | pre-cutover | Fleet status, repo detail, session summaries, audit timeline APIs |
| E6 | pre-cutover | Hardening (error handling, structured logging, rate limiting, operator CLI) |
| E7 | | Session blocks — DEPRECATED as evidence path in v2.6.0 |
| E8 | | Envelope encryption — DEPRECATED in v2.6.0 |
| E9 | v2.6.0 | Transcripts-first MVP (Migration 009+010, ingest + query endpoints, `transcripts pull` CLI) |
| E10 | v2.7.0 + v2.8.0 | Audit surface (Q1-Q5 canonical questions across three vendors) |

## Historical priorities (superseded)

- **Machine-scoped Gator runtime + policy channel** (roadmap item
  19, Priority #1 as of 2026-08-17) — shipped v2.9.0 across six
  Architect-ratified phases.
- **Blueprints 2.0 Release A** (roadmap Priority #2 as of
  2026-08-17) — shipped v2.11.0 (Dashboard-native experiment) then
  pivoted to v2.12.0 (artifact-first HTML protocol). Dashboard-
  native experiment retired same release.
- **Dashboard UI arc** — Plans A/B1/B2/C shipped v2.13.0.

## Related design records

Under `.gator/artifacts/` (Git-tracked):

- Content vs .includes migration sketch (2026-07-27)
- Local-agent overrides plan (2026-07-28)
- Dashboard Fleet Repo file sidebar plan (2026-07-28)
- Retire gator-install branch plan (2026-07-30)
- Monorepo convergence plan chain (2026-07-16 onward)
- Loop usability plan (2026-07-27)
- Architect authority plan (2026-07-26)
- Charter-first understanding heuristic (2026-08-14)

Under `.gator/vault/artifacts/` (gitignored, machine-local):

- Transcripts-first MVP + v2.6.0 stabilization chain (2026-08-08+)
- Non-Enterprise session cleanup plan chain (2026-08-11+)
- Machine-scoped runtime design + phases (2026-08-17+)
- Blueprints 2.0 supporting artifacts (2026-08-09+)
- Enterprise audit-surface tranche plans (2026-08-14+)
- Normalized transcript index design note (2026-08-17)
- Dashboard UI arc plans (2026-09-06+)
- Cumberland HTML style Sketch 2 (2026-09-12)
