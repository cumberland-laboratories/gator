---
date: 2026-10-16
type: implementation-sketch
issue: 70
feature: dashboard-listing-and-search-performance
recommended-path: full-planning-loop (security boundary: live containment)
---

# #70 follow-up — Dashboard file listing and search performance

## Executive Summary

- **The finding:** `/api/repo/<name>/files` is the Dashboard's dominant server cost. It took 85% of all server time in a full local Dashboard UI run (308 calls, 96 s, median 317 ms for a 131-file test repo). Under local CPU and disk contention it reached 1.6–3 s. A parallel stress run measured `/api/repo/<name>/search` at up to 12.5 s.
- **The cause:** `_contained_repo_path()` re-derives per-request invariants for every listed file. Each call resolves the repository root and the namespace root again, walks every path component for reparse points, and resolves the target. For 131 files that is about 2,500 filesystem system calls per listing.
- **The goal:** make one listing cost roughly one containment derivation plus a cheap per-file check, without weakening the containment, reparse-point or visibility guarantees.
- **One charter discrepancy needs an Architect decision first:** search does not apply the listing's visibility policy, although its charter says it does. See below.

## Evidence (2026-10-15/16, Windows desktop, local)

| Measurement | Result |
|---|---|
| Full suite, per-request server timing (temporary probe, not committed) | 6,786 requests; none ≥ 1 s; `/files` 96.2 s of server time, median 317 ms, max 589 ms; all other endpoints median 1–9 ms |
| `live_listing` profile (131 files) | 289 ms wall; `_contained_repo_path` 0.33 s cumulative under cProfile; 399 `resolve()`, 1,509 `stat`, 797 `_getfinalpathname` |
| Contention (median/max, 8 samples) | idle 295/304 ms; CPU 455/598; filesystem churn 928/1,417; both 1,627/1,870 ms |
| Four parallel suites + churn | `/files` median 1,325 ms, p95 1,995, max 3,001; `/search` up to 12,554 ms; one 10 s search-results timeout |
| Fresh vs warm repo | no first-listing penalty locally (~300 ms each) |

Not reproduced: a `/files` call over 15 s. Windows CI runners are slower than this desktop (2 vCPU; Defender's cost there is unmeasured), so the hypothesis is that the same per-file cost occasionally crosses 15 s there. The separate init/landing race (the other confirmed #70 cause) is fixed independently.

## Scope

1. **Listing (`_handle_files`, live branch):** compute the per-request invariants once per listing: the resolved repository root, each namespace root's resolution and reparse status, and its containment. Then give each file a check proportional to its own path.
   - `_iter_scanner_files()` already rejects reparse-point directories and files during a top-down `scandir` walk inside the namespace root. The plan must decide, with argument, which per-file checks that walk already establishes and which must remain. The F2 belt-and-suspenders target containment must stay unless the plan proves the scanner makes it redundant and the Architect agrees.
2. **Search (`search_repo_files`):** bound its cost. It currently reads the full content of every `*.md`/`*.json` under `.gator/` and `gator-command/`, in sorted order, on each keystroke-debounced request.
3. **Tests:** a focused performance-regression check that does not depend on wall-clock time, such as a count of filesystem calls or containment derivations per listing. The existing containment, junction and alias pins in `test_content_transport_slice2.py` and `slice3.py` must all still pass.

## Out of Scope

- `ThreadingHTTPServer` or any server-concurrency change. The data show no head-of-line blocking: no request held the server for ≥ 1 s in the full run.
- Changing timeouts, reruns or CI.
- The historical (`?version=`) listing branch, unless the same helper serves both.

## Constraints

- **Security boundary.** The `_contained_repo_path()` charter tripwires stay true: unresolved components are validated before final resolution; an in-repo alias into denied content is still denied; there is no existence oracle. A significance check is mandatory.
- **Single policy.** Listing and serving keep using the same `is_browsable` predicate.
- **No new per-request state shared across requests.** The server is single-threaded today, but the plan should not add caches whose invalidation is unclear. A per-request derivation is preferred over a cross-request cache.

## Architect Decision Needed Before Planning

**Search versus its charter.** `scripts-dashboard.md` says: "Search uses the same visibility policy as listing and file reads; it is not a bypass around denied paths or extensions." The code (`dashboard/data.py` `search_repo_files`) does the following:
- uses `Path.rglob` over `.gator/` and `gator-command/`;
- skips only `sessions/_active/`;
- does not call `is_browsable()`, `_iter_scanner_files()` or `_contained_repo_path()`.

Its snippets come from files the listing might not show, for example dot-directories or denied basenames. Per the constitution's charter-alignment rule, this needs a decision before code changes. Either the charter drifted (search is intentionally broader), or the code drifted. In the second case, routing search through the listing's scanner and policy would also deliver most of the Scope 2 speed-up.

## Connections

- GitHub #70 — flake record and the earlier threading hypothesis (refuted for the local data).
- `.gator/charters/scripts-dashboard.md` — `_contained_repo_path()`, `is_browsable()` / `_iter_scanner_files()`, `search_repo_files()`.
- `tests/test_dashboard_ui/test_content_transport_slice2.py`, `slice3.py` — containment and junction pins.
