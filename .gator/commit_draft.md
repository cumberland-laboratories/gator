---
message: "Welcome: \"How Gator works\" tab renders the shipped how-gator-works.md"
change-type: feature
significance: notable
decision-tags: [dashboard, welcome, docs]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Welcome's first tab is renamed "What is Gator?" → "How Gator works" (topic key `how`) and now shows the shipped starter copy of `how-gator-works.md` (the file gatorize installs as `.gator/docs/how-gator-works.md`) instead of a hand-written summary (Architect direction).
- Server: new fixed, read-only `GET /api/welcome/how-gator-works` → `{"text": …}` backed by `dashboard/helpers.read_welcome_doc()` / `WELCOME_DOC_PATH` (package-relative `templates/gator-starter/docs/how-gator-works.md`). No request input selects the file; unavailable → JSON 404.
- Browser: `welcome.js` `loadHowDoc()` fetches it at most once per page load (cached in module state) and `renderHowDoc()` renders it only through the closed `GatorLoopMarkdown` formatter; formatter failure → raw text via `textContent`; fetch failure → a text notice naming `.gator/docs/how-gator-works.md`.
- Snapshot: `build_snapshot()` inlines the document as `window.GATOR_WELCOME_DOC` via `_json_script()` (escapes `</`), so offline snapshots need no server.
- Tests: `test_welcome_ui.py` (topic rename; exactly one fixed document request; rendered shipped doc and once-per-page-load cache, mutation-checked; failure notice; endpoint ignores request input) and `test_snapshot.py` (inlined doc, script-safe JSON).
- Charters: `scripts-cross-cutting.md` (Package surface: the Dashboard's runtime read of a starter-template file depends on the `templates/**/*` package-data glob), `scripts-dashboard.md` (new `read_welcome_doc()` / route entry with fixed-file TRIPWIRE; snapshot data-block note), `scripts-dashboard-ui.md` (Welcome entry: How Gator works loading and rendering).
- Significance check (new HTTP route that reads a file; reverses #72's "Welcome makes no request"). Steelman: (1) a new server route is new attack surface: any future edit that lets request input reach the path would turn it into a file-read oracle; (2) Welcome is no longer request-free, so the #72 "no request" guarantee becomes "one fixed GET"; (3) the shipped template copy can differ from a repo's own (possibly edited) `.gator/docs/how-gator-works.md` and from the longer root `docs/how-gator-works.md`, so the tab shows the product's canonical text, not the repo's; (4) long-form docs now render through the Loop formatter, whose closed grammar flattens numbered lists into bullets and would show images or nested lists literally if the doc gains them; (5) the alternative of embedding the text in JS avoided the route at the cost of duplication. Compatibility: additive route and an additive snapshot global; no schema, CLI or history change. Mitigations: fixed package-relative path with no input (pinned with traversal/query probes), loopback-only server, closed renderer with no innerHTML. Architect chose this option (1) in session.
