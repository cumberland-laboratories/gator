---
message: "Dashboard: readable expanded Loop artifacts with Raw/Rendered views (#45)"
change-type: feature
significance: notable
decision-tags: [dashboard, loop, markdown, security]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Revised implementation plan for #45 (readable expanded Loop artifacts) per the 2026-10-03 revision sketch, rev 2 (P1: a closed display grammar with a complexity budget, flat lists, no nesting, no italics; P2: image syntax handled before links as literal text, with no `a`, `img` or request asserted), rev 1, no code changes: `.gator/vault/artifacts/2026-10-03-loop-artifact-expanded-document-rendering-implementation-plan.md`. It supersedes the approved round-0 loop plan: collapsed cards get no excerpt; the full expanded body is rendered by a Loop-only DOM renderer, chosen over a shared Repository renderer with evidence; Raw is exact; timeline summaries are kept.
- #45 M1+M2 (closed display formatter and wiring; plan rev 2 approved):
  - New `views/loop-markdown.js` (`GatorLoopMarkdown.render` / `safeHref` / `MAX_RENDER_CHARS`): exactly the plan's closed grammar.
    - Line rules: 8, with flat lists, literal numbering and naive tables.
    - Inline rules: one scan, with images as literal text before links, code, links with literal text, and bold with literal content.
    - Output: DOM nodes only, with a fixed element and class allowlist; only http(s) links, with safe `rel`/`target`; a 200k-character bound that throws `TooLarge`. It is 160 non-comment lines, within the budget.
  - `dashboard.html` loads it before `loop.js`. `snapshot.py` reads it, matches its tag in the regex and inlines it. `test_snapshot.py` pins the tag, the external-reference absence and that `window.GatorLoopMarkdown` is inlined.
  - Tests: new `tests/test_dashboard_ui/test_loop_markdown_ui.py` (58): one case per line and inline rule; a 32-column cap; literal unsupported syntax; a safe external link; 11 inert URL forms plus a parenthesised URL fully literal; images (http and https) giving no `img`, `a` or request; an adversarial-corpus allowlist walk; malformed input never throwing; CRLF; the size bound; `safeHref` direct. Four mutants killed.
  - Charters: `scripts-dashboard-ui.md` (Covers, plus the `GatorLoopMarkdown` entry with its grammar, budget and TRIPWIRE); `scripts-dashboard.md` (`build_snapshot` script order).
- #45 M3 (expanded artifact body, plus removal of the collapsed excerpt):
  - `views/loop.js`: the collapsed-excerpt path is removed (`.loop-artifact-summary` node, `loadArtifactSummary`, `isSummaryArtifact`, and both `renderArtifacts` call sites). Collapsed cards never fetch; `extractSummary` is timeline-only.
  - `loadArtifactContent` routes text to the new `renderArtifactBody`:
    - an equality skip;
    - Raw `pre.textContent` and Rendered `GatorLoopMarkdown`, from the same string;
    - a view bar of native buttons with `aria-pressed` and a text caption;
    - a per-section `dataset.view` written only by the buttons;
    - large and failure fallbacks to Raw that never overwrite the choice.
  - "Loading…" resets `_gatorText`.
  - `dashboard.css`: removed the unused `.loop-artifact-summary` / `.loop-summary-*` rules; added view bar and `.loop-md` styles (state not colour-only, contained tables and code, `overflow-wrap: anywhere`); `.loop-artifact-content` `max-height` is 70vh.
  - Tests:
    - `test_loop_markdown_ui.py` gains 9 M3 tests (67 total). `plan.current.md` is served by route interception rather than a seed edit, which is equivalent and lets each test control the text and count requests.
    - `test_loop_workspace.py`: the toggle and escaping tests wait for Raw as `state="attached"` (Raw is hidden by default), and the escaping test also checks for no `img` / `iframe` / `style`. The two artifact-inspector summary tests are re-targeted to timeline summaries, with a no-excerpt assertion. The stale-response test expects only the body fetch, and `NEW-SUMMARY` is asserted on the expanded body. `_open_incremental` waits only on timeline summaries.
    - Five integration mutants are killed.
  - Charter `scripts-dashboard-ui.md`: the TRIPWIRE is replaced; the artifacts, fetch-ordering and summary entries are updated; a new `renderArtifactBody` / view entry is added.
- #45 M4 (final pass):
  - The charter consistency sweep is clean: no stale excerpt or `<pre>`-escape statements remain.
  - CHANGELOG `[Unreleased]` / Changed: the #45 entry.
  - Full `tests/test_dashboard_ui` + `tests/test_snapshot.py`: 407 passed, 11 skipped (run in M3, after the final code change).
- Pre-commit charter-index-gap fix: `scripts-cross-cutting.md` Package and License Surface now records the Dashboard exception. `scripts/dashboard/**/*` ships new `views/*.js` without a `package-data` entry, but each must be added to the `build_snapshot()` regex and inline block (example: `loop-markdown.js`, #45). `tests/test_packaging.py`: 20 passed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
