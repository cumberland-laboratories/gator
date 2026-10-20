---
date: 2026-10-16
type: implementation-sketch
issue: 70
feature: dashboard-listing-and-search-performance
recommended-path: full-planning-loop (security boundary: live containment)
architectural-decision: preserve governance-document search scope; enforce shared live visibility and containment before content search
---

# #70 follow-up — Dashboard file listing and search performance

## Executive Summary

- **The finding:** `/api/repo/<name>/files` is the Dashboard's dominant server cost. It took 85% of all server time in a full local Dashboard UI run (308 calls, 96 s, median 317 ms for a 131-file test repo). Under local CPU and disk contention it reached 1.6–3 s. A parallel stress run measured `/api/repo/<name>/search` at up to 12.5 s.
- **The cause:** `_contained_repo_path()` re-derives per-request invariants for every listed file. Each call resolves the repository root and the namespace root again, walks every path component for reparse points, and resolves the target. For 131 files that is about 2,500 filesystem system calls per listing.
- **The goal:** make one listing cost roughly one containment derivation plus a cheap per-file check, without weakening the containment, reparse-point or visibility guarantees.
- **Decision recorded 2026-10-20:** search remains a governance-document
  search over `.gator/` and `gator-command/`; it does not expand into source
  files. Its candidates must nevertheless pass the same live discovery,
  reparse-point, containment, and visibility gates as a listed file. Search
  is therefore no longer a path or extension-policy bypass.

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
2. **Search (`search_repo_files`):** bound its cost. It currently reads the full content of every `*.md`/`*.json` under `.gator/` and `gator-command/`, in sorted order, on each keystroke-debounced request. Preserve that intentionally narrower governance-document scope, but source its candidates from the guarded live-discovery seam rather than `Path.rglob`.
3. **Tests:** a focused performance-regression check that does not depend on wall-clock time, such as a count of filesystem calls or containment derivations per listing. The existing containment, junction and alias pins in `test_content_transport_slice2.py` and `slice3.py` must all still pass.

## Out of Scope

- `ThreadingHTTPServer` or any server-concurrency change. The data show no head-of-line blocking: no request held the server for ≥ 1 s in the full run.
- Changing timeouts, reruns or CI.
- The historical (`?version=`) listing branch, unless the same helper serves both.

## Constraints

- **Security boundary.** The `_contained_repo_path()` charter tripwires stay true: unresolved components are validated before final resolution; an in-repo alias into denied content is still denied; there is no existence oracle. A significance check is mandatory.
- **Single policy.** Listing, serving, and search use the same logical-path
  visibility policy. Search may be *narrower* by product scope (only
  governance namespaces and searchable text formats); it must never be
  broader by discovering a denied path, extension, alias, junction, symlink,
  or dot-directory that listing/file would exclude.
- **No new per-request state shared across requests.** The server is single-threaded today, but the plan should not add caches whose invalidation is unclear. A per-request derivation is preferred over a cross-request cache.

## Decision: search aligns with the visibility contract

`scripts-dashboard.md` says search uses the same visibility policy as listing
and file reads. The current `dashboard/data.py::search_repo_files()` instead
uses `Path.rglob` over `.gator/` and `gator-command/`, skips only
`sessions/_active/`, and does not call `is_browsable()`, `_iter_scanner_files()`
or `_contained_repo_path()`.

Git history establishes the direction: this `rglob` implementation existed in
the initial monorepo import; the charter assertion was added later during a
Dashboard-charter rewrite without matching code or tests. The governing
charter is the declared contract. **Treat the implementation as
nonconformant.**

The product decision is deliberately narrow:

1. Search remains a governance-document finder over `.gator/` and
   `gator-command/`, restricted to `.md` and `.json`. It does not become a
   full source-code grep.
2. Before search reads content, a candidate must be found by the reparse-aware
   scanner, converted to its canonical logical path, parsed through the normal
   logical-path gate, pass `is_browsable(..., "files")`, and pass live
   containment.
3. A listed but non-searchable namespace or extension is absent by deliberate
   product scope. A denied path, extension, dot-directory, alias, junction,
   symlink, or reparse point is absent everywhere: no snippet, count, error,
   or timing distinction becomes an existence oracle.

## Proposed seam: derive once, consume safely

The planning loop chooses exact names, but should begin from this data flow:

```text
namespace roots -> one per-request derivation -> reparse-aware scanner
-> canonical logical path + parse_logical_path -> is_browsable
-> cheap per-entry proof / F2 containment -> authorized candidate records
   -> listing serializer
   -> search's namespace + .md/.json filter, then content matching
```

Introduce one server-owned, live-only candidate iterator or immutable
per-request context. It exposes only already-authorized logical paths, safe
targets/entries, and metadata needed by listing/search. It is not a
cross-request cache and never exposes resolved paths in a response.
`_handle_files()` consumes it for listing; the search route supplies its
candidates to the data-layer query/snippet formatter. This keeps filesystem
authority in `gator-dashboard.py` and Boolean query semantics in
`dashboard/data.py`, without a reverse import or duplicate policy.

The planner must prove whether the scanner's immediate `DirEntry` reparse
check plus root derivation makes a cheap per-file proof sufficient. The F2
belt-and-suspenders containment check stays unless that proof, the adversarial
tests, and Architect review establish an equivalent replacement. Performance
alone never justifies deleting F2.

## Required planning loop

Run a planning loop before implementation. Its review question is not merely
"is it faster?" but "what exact security claim replaces every removed syscall?"
The approved plan must include:

1. A before/after call graph for live `/files` and `/search`, identifying
   what runs once per request, namespace, and surviving entry.
2. A proof table for repository/namespace containment, unresolved-component
   reparse detection, external escape, in-repo alias into denied content,
   hidden/denied segments, extension policy, missing/unreadable files, and
   the no-oracle response contract.
3. The exact `gator-dashboard.py` / `dashboard/data.py` ownership boundary,
   including why no reverse import or duplicate policy is introduced.
4. A deterministic performance pin: instrument the seam or monkeypatch
   resolve/stat/containment derivation to assert an O(namespaces + survivors)
   budget, never a wall-clock target.
5. A significance check that steelmans the optimization, especially Windows
   junction behavior versus POSIX symlinks.

The planning-loop reviewer should approve only with the containment proof,
test matrix, and explicit F2 disposition. Any containment or visibility
finding goes to the Architect; it is not an autonomous coding-loop fix.

## Required coding loop

Use these checkpoints after plan approval:

1. **Candidate seam:** add per-request/root derivation; preserve `/files`
   schema. Verify existing slice-2/slice-3 containment, junction, symlink,
   alias, and error-taxonomy pins.
2. **Listing + performance pin:** migrate live listing to the seam and add the
   deterministic call-count/derivation test. Keep historical listing separate
   unless the approved plan gives it an equivalent safe consumer.
3. **Search correction:** feed only authorized candidates to search; retain
   AND/OR/phrase ranking, limits, and snippets. Add allowed and denied search
   fixtures, including dotted, denied-basename, alias, and reparse candidates.
4. **Significance evidence:** run focused security and Dashboard suites;
   immediately update Dashboard Server and Cross-Cutting charters with the
   code edits; record the steelman and compatibility result before commit.

No checkpoint may replace a 404/no-result security behavior with a diagnostic
that reveals whether a protected file exists. No cache, timeout increase, or
concurrency work belongs in this sequence.

## Test matrix additions

| Case | `/files` | `/search` |
|---|---|---|
| ordinary allowed `.gator` Markdown/JSON | listed | searchable |
| allowed source or non-searchable extension | listed when policy permits | absent by deliberate product scope |
| `.gator/sessions/_active/**` | absent | absent |
| hidden/denied directory or basename | absent | absent |
| in-repo alias into protected content | absent | absent |
| external symlink/junction/reparse point | absent | absent |
| missing/unreadable candidate | ordinary policy/error behavior | absent; no existence signal |
| historical `?version=` listing | unchanged | not applicable without a new explicit search contract |

Add a behavioral regression assertion that every result returned by search is
a valid live-listing candidate under search's narrower namespace/format
selection. Use real dot-directory, denied-basename, symlink, and Windows
junction fixtures where supported; source-text greps cannot replace these
security tests.

## Connections

- GitHub #70 — flake record and the earlier threading hypothesis (refuted for the local data).
- `.gator/charters/scripts-dashboard.md` — `_contained_repo_path()`, `is_browsable()` / `_iter_scanner_files()`, `search_repo_files()`.
- `tests/test_dashboard_ui/test_content_transport_slice2.py`, `slice3.py` — containment and junction pins.
