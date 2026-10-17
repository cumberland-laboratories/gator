---
date: 2026-10-17
type: implementation-sketch
feature: dashboard-threaded-request-server
related: 70
recommended-path: planning-loop-required
---

# Dashboard Request Concurrency: Threaded Server Sketch

## Executive Summary

- A browser trace on the Gator repository shows the Dashboard's plain
  single-request `HTTPServer` queue, not a slow HTML viewer: a `/files` request
  took about 4.25 seconds, and an HTML document request that normally takes
  about 43 ms completed immediately behind it at about 4.27 seconds.
- This affects every Dashboard interaction that arrives behind a long listing,
  search, Git operation, or subprocess—not just HTML preview and not just a
  workspace-tab return. Repeating Repo polling can keep a large repository
  server busy for most of its active lifetime.
- A `ThreadingHTTPServer`-style design is the architectural fix, but not a
  mechanical class substitution. It turns previously serialized shared state
  into concurrent state: registry, Fleet snapshot, refresh, lifecycle actions,
  server restart/shutdown, and loop-host adoption all need explicit contracts.
- Deliver browser request ordering and gentler polling as independent small
  relief work if desired. This sketch scopes the proper concurrency change and
  requires a planning loop before implementation.

## Observed Problem

With a large repository selected in Repo view:

```text
single HTTPServer request loop

/files  ─────────────────────────────── 4.25 s
                                         /raw HTML ─ 43 ms
browser observes HTML only after 4.27 s
```

The browser starts an iframe/raw-document request slightly later than its
script-driven `/files` fetch, so the listing reaches the one-request server
first. Markdown can appear responsive only because its `/file` fetch happens
to arrive first. The user-visible distinction is request ordering, not a
fundamental HTML-versus-Markdown rendering difference.

The Repo view also polls its listing. On the observed Gator repository a
listing took roughly 4.4 seconds and the next poll began around 5 seconds
later. Thus the loopback server can be occupied approximately 85–90% of the
time while that Repo view is active. Any unrelated click may wait behind that
work.

This is a broader responsiveness and reliability concern. It is a plausible
contributor to the historical Windows Dashboard UI flakes in #70, though the
new concurrency design must not claim that it alone explains every failure.

## Scope

Replace the Dashboard's single-request serving model with bounded, safe
concurrent request handling, so an expensive read-only request does not impose
head-of-line blocking on an unrelated document, API, or UI request.

The target user promise is modest and concrete:

> A slow repository listing must not make unrelated Dashboard inspection wait
> behind it merely because both requests use the same local Dashboard port.

This does not promise that a slow listing becomes fast; server-side listing
optimization remains separate work.

## Related but Independent Relief Work

These may ship before, after, or alongside the concurrency change. They do not
replace it.

1. **Return-order scheduling.** On a cached Repo-tree return, allow the
   selected document to begin loading before the background `/files` freshness
   check, with a short bounded fallback. This directly improves the observed
   HTML-preview symptom.
2. **Completion-based Repo polling.** Schedule the next live listing check a
   fixed interval after the preceding request completes, rather than on an
   overlapping wall-clock interval. This reduces avoidable request pressure.
3. **Server-side listing performance.** The separate
   `2026-10-16-dashboard-listing-performance-sketch.md` addresses the cost of
   `/files` itself and its containment checks. It improves first visits and
   background refreshes regardless of server concurrency.

No browser scheduling tactic makes the server queue safe or removes blocking
for arbitrary concurrent Dashboard use. No threading change weakens the
security/containment work in the listing path.

## Current Concurrency Boundary

`gator-dashboard.py` currently constructs `HTTPServer`, which calls one
handler at a time. It already uses threads for narrowly scoped work:

- loop host/watcher threads, protected by `_LOOP_HOSTS_LOCK` and OS host locks;
- a background Fleet refresh thread, guarded by `DashboardHandler._refresh_lock`;
- update/gatorize/restart paths that launch background work.

Those narrow threads do not make request handlers concurrent. Replacing
`HTTPServer` with `ThreadingHTTPServer` (or an equivalent bounded subclass)
means two arbitrary GET/POST handlers may now execute at once. All module and
class state previously protected by serialization must be classified and given
an explicit owner/lock/snapshot rule.

## Design Principles

1. **Read concurrency, controlled mutation.** Independent read-only inspection
   requests should proceed concurrently. Mutations must serialize at the
   smallest meaningful scope.
2. **Snapshot under lock; work outside lock.** A registry or Fleet snapshot may
   be copied while protected, but no lock may be held while scanning a
   repository, running Git, waiting for a subprocess, reading a large file, or
   sending a response.
3. **One authority per state domain.** Do not add ad hoc locks at call sites.
   Encapsulate registry/Fleet/refresh state behind helpers with documented
   read-and-mutate contracts.
4. **Existing loop authority remains authoritative.** Threading does not grant
   the Dashboard a new Loop state write path. Loop session locks, role tokens,
   `host.lock`, and start locks remain the authority for Loop transitions.
5. **No accidental resource amplification.** Loopback-only access reduces
   exposure but does not make unbounded thread creation desirable. Define the
   request-thread and shutdown behavior deliberately.
6. **Security invariants remain per request.** Request parsing, logical-path
   validation, containment, reparse-point defenses, MIME/CSP selection, and
   token exclusion must produce the same outcome under simultaneous requests.

## Proposed Server Shape

Start from a named server class rather than changing call sites to a standard
library type anonymously:

```text
DashboardHTTPServer
  ThreadingMixIn + HTTPServer
  loopback bind only
  daemon worker policy explicitly chosen
  bounded admission policy explicitly chosen
  predictable shutdown and server_close behavior
```

The planning loop must choose between:

- `ThreadingHTTPServer` with its standard per-request worker behavior; or
- a small bounded worker/admission layer that rejects or queues excess local
  work predictably.

For a local, authenticated-by-origin tool, the standard class may be enough,
but the decision must be evidenced. Do not silently accept unlimited worker
creation merely because ordinary browser traffic is expected to be small.

Each handler gets its own `DashboardHandler` instance; its response writer and
request parse state are naturally request-local. Shared state is not.

## Shared-State Audit

The implementation plan must inventory every mutable/global state read or
written by a request or lifecycle thread. At minimum, address these domains.

| Domain | Current shape | Required threaded contract |
|---|---|---|
| Registered repositories | module-global `_REGISTRY_REPOS`; read by most routes, changed by register/remove | registry lock or state owner; readers take an immutable snapshot; register/remove atomically update durable registry plus in-memory snapshot without readers seeing a half-applied result |
| Fleet/Tier-1 snapshot | `DashboardHandler.fast_data`; background refresh swaps it | build a new snapshot outside the publication lock; publish one complete immutable/copy-on-write value; readers capture a reference and never observe an in-place mutation |
| Refresh admission | `_refresh_lock`, currently with a check-then-start pattern | one non-racy acquire-or-report operation; exactly one refresh runs; lock release is exception-safe; no request waits while a refresh holds the state lock |
| Repository lifecycle actions | update, gatorize, register, remove, and status paths | classify each action; serialize same-repository mutation where underlying tooling is not already authoritative; unrelated repository work must not require a global mutation lock |
| Loop host registry | `_LOOP_HOSTS` and `_LOOP_HOSTS_LOCK` | retain its nonce/lock invariants; audit all readers/writers and adoption iteration; never hold its lock while acquiring a Loop/session/host lock or joining a watcher thread |
| Loop control routes | start, pause, unblock, extend, reopen, approval and other posts | preserve underlying Loop start/session/token locks as authority; make Dashboard-side lookup snapshots safe; no lock-order inversion with registry or host locks |
| Server restart/shutdown | background restart paths plus `serve_forever()` | initiate shutdown from a non-serving coordinator thread; specify whether active request workers drain, are bounded by timeout, or are abandoned safely; never deadlock waiting for the request that requested upgrade/restart |
| Debug/test seams | live registry and refresh observations | keep development-only and test-only views accurate under snapshots; never expose lock internals or unsafe mutable references |

### Registry abstraction

Prefer a small registry-state helper over scattering a new lock around every
`_REGISTRY_REPOS` loop. Its API should make correct usage natural:

```text
registry_snapshot() -> tuple[RepoRecord, ...]
resolve_repo_from_snapshot(snapshot, name/key) -> RepoRecord | None
registry_mutate(operation) -> updated snapshot
```

Handlers obtain a snapshot, release the registry protection, then resolve paths
and do filesystem work from that immutable copy. A remove may make a snapshot
stale; the request must respond honestly to filesystem failure and never fall
back to a different repository.

Do not hold a registry lock while calling `Path.resolve()`, `collect_standalone_data`,
Git, a lifecycle CLI, or a Loop helper.

### Fleet publication

`fast_data` needs a whole-object publication rule. The refresh worker should
collect from one registry snapshot, construct a complete new data object, then
swap the reference under a short publication lock. `/api/data` takes the
reference under that same lock and serializes its own local reference outside
the lock. The old object must not be mutated after publication.

This permits a stale-but-coherent Fleet response during refresh. It must never
produce a partially rebuilt object, a mixed registry/Fleet identity, or an
exception caused by concurrent list mutation.

### Lock ordering

Document a global order before coding. A likely safe direction is:

```text
short Dashboard state lock (registry / Fleet publication)
  -> released
  -> repository, Git, lifecycle, Loop session, or host-specific operation
```

No Dashboard-state lock may be held while acquiring a Loop session lock,
`host.lock`, liveness lock, or waiting for a subprocess. `_LOOP_HOSTS_LOCK`
remains a leaf lock as required by the Loop contract. The planning loop must
verify the actual call graph instead of adopting this diagram as proof.

## Route Classification

Classify and test every route, not just `/files`:

- **Concurrent inspection reads:** dashboard shell/assets, Welcome documents,
  `/api/data`, repository list/file/raw/history/search, Git history, and Loop
  status/events/artifacts. These should be able to run concurrently after a
  short immutable state snapshot.
- **Background work admission:** refresh and update/gatorize restart work.
  Their response may return promptly, but their durable state transition needs
  a documented single-flight or per-repository exclusion rule.
- **Registry mutations:** repository register/remove. These change the lookup
  space used by all routes and need atomic publication.
- **Governed Loop mutations:** all Loop POST actions. They may run concurrently
  at the HTTP layer, but their existing protocol/session authorization decides
  whether a transition is valid. Dashboard thread safety must not simulate or
  bypass that authority.

## Verification Strategy

Add a real threaded-server test harness. Browser request interception alone is
not enough because it does not prove server request admission order.

### Essential concurrency pins

1. Block one real `/files` handler with a test-controlled gate. While it is
   blocked, request a small raw/HTML or `/file` response from another client.
   Prove the small response completes before the listing is released.
2. Run concurrent `/files`, `/raw`, `/api/data`, and Loop status reads across
   two repositories. Assert correct repository identity and security headers
   for every response.
3. Trigger refresh concurrently from several clients. Assert one collection is
   admitted, all readers see a coherent old or new snapshot, and no request
   observes partial data.
4. Register/remove while independent reads execute. Assert no crash, no
   cross-repository fallback, and no mixed registry identity. Cover duplicate
   display names and stable repo keys.
5. Race two start/extend/reopen requests against the same Loop and verify the
   existing start/session/host locks preserve one valid outcome with honest
   errors for the other request.
6. Hold a long read while requesting restart/upgrade. Assert shutdown/restart
   does not deadlock, leak an unbounded worker, or report success while the
   server is unusable.
7. Re-run all content transport pins under the threaded server, including
   traversal, symlink/junction, denied override internals, versioned reads,
   CSP, and no-existence-oracle behavior.
8. Stress Windows and Linux with mixed reads plus lifecycle operations. The
   test should have bounded timeouts and report thread/request diagnostics on
   failure; it must not hide races with automatic reruns.

### Performance acceptance checks

- With one intentionally slow listing in progress, an independent small
  document/file response completes within a bounded local responsiveness
  budget without waiting for listing completion.
- The first and steady-state full Dashboard UI suites remain reliable on
  Windows and Linux.
- Concurrent listings do not make a simple local Dashboard unusably CPU or
  disk saturated. Measure and set a conservative admission/worker policy if
  needed.
- Server-side listing optimization remains measurable independently; threading
  must not conceal a regression in `/files` cost.

## Delivery Sequence

1. **Planning loop:** complete the state/route/lock-order audit, choose server
   admission and shutdown behavior, and design the real concurrency harness.
2. **Infrastructure slice:** introduce the named threaded server class and
   registry/Fleet snapshot abstractions with no feature-route behavior change;
   add basic concurrent-read tests.
3. **Mutation hardening slice:** migrate register/remove, refresh, lifecycle,
   and Loop entry points to explicit contracts; add race tests.
4. **Full verification:** content-security, Loop, Dashboard UI, Windows stress,
   and failure diagnostics. Update the server and UI charters immediately as
   each code module changes.
5. **Follow through:** remeasure the original HTML/document symptom and decide
   whether the smaller request-order/poll-cadence changes still add enough
   value to ship.

## Non-goals

- Making `/files` intrinsically faster; that is separate optimization work.
- Weakening logical-path, containment, reparse-point, CSP, token, or
  authorization boundaries.
- Moving Dashboard networking off loopback or creating a remote multi-user
  server.
- Retaining inactive workspace DOM, polls, or Loop timers.
- Treating threading as proof that #70 is closed without the specified tests
  and repeated Windows CI evidence.

## Likely Files

- `src/gator_command/scripts/gator-dashboard.py` — server construction,
  shared-state abstractions, lifecycle/restart behavior, request routes.
- `src/gator_command/scripts/dashboard/data.py` and helpers — snapshot-safe
  data collection boundaries where the audit demonstrates a need.
- `tests/test_dashboard_ui/_harness.py` plus a focused threaded-server test
  module — real server admission and race coverage.
- `tests/test_dashboard_ui/` — browser-level non-blocking document/listing
  proof and regression coverage.
- `.gator/charters/scripts-dashboard.md` and
  `.gator/charters/scripts-dashboard-ui.md` — concurrency, lifecycle, and
  browser scheduling invariants when implementation begins.

## Connections

- GitHub #70 — Windows Dashboard UI reliability record and the original
  shared-harness investigation.
- `2026-10-16-dashboard-listing-performance-sketch.md` — listing/search cost
  optimization, deliberately independent of request concurrency.
- `2026-10-16-dashboard-repo-tree-return-cache-sketch.md` — cached Repo-tree
  return; it reduces repeat-navigation pressure without retaining hidden DOM.
- `scripts-dashboard.md` — Dashboard route, security, and loop-host contracts.
- `scripts-loop.md` — Loop session/host lock ordering and authority rules.
